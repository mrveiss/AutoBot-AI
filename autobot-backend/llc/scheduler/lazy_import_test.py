# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for the llc.scheduler split import policy (#13332).

``llc/scheduler/__init__.py`` had the same eager-import-everything shape that
#13057 fixed for ``llc/services/__init__.py``, but it could not take the same
fix wholesale: Celery's ``autodiscover_tasks([... "llc.scheduler"],
related_name=None)`` imports this package ``__init__`` and nothing else, so the
``@shared_task`` decorators in ``project_disposal_sweep`` and ``sprint_autoclose``
only run because that ``__init__`` imports those two modules (GH#12318).

That is the trap #13332 names explicitly: **a test that only checks import
isolation would pass while breaking Celery.** A PEP 562 conversion of the task
modules makes every isolation assertion in this file greener, and silently
unregisters two beat jobs — the worker then logs "Received unregistered task of
type ..." and drops them, which is the exact defect #12318 fixed.

So this module asserts both halves against each other:

  * the *eager* half — the two task modules are imported by package import, and
    their beat names resolve to real callables in the Celery registry;
  * the *lazy* half — package import pulls in nothing else, and in particular
    never reaches ``llm_shared`` (PyTorch/CUDA probing at import) or ``llc.kb``.

Making either half pass by weakening the other fails this module.
"""

import sys

import pytest

_SCHEDULER_PREFIX = "llc.scheduler"

# The two modules whose eager import Celery task registration depends on, and
# the beat task name each one registers (celery_app.py beat_schedule).
_EAGER_TASK_MODULES = {
    "llc.scheduler.project_disposal_sweep": "llc.scheduler.project_disposal_sweep.run_disposal_sweep",
    "llc.scheduler.sprint_autoclose": "llc.scheduler.sprint_autoclose.run_daily_check",
}

# Scheduler classes that must NOT be imported by package import (PEP 562).
_LAZY_SUBMODULES = {
    "llc.scheduler.base",
    "llc.scheduler.budget_watchdog",
    "llc.scheduler.liveness_monitor",
    "llc.scheduler.session_checkpointer",
}


@pytest.fixture
def isolated_llc_scheduler():
    """Force a fresh import of llc.scheduler* then restore the originals.

    Save-and-restore rather than drop-and-forget, for the reason documented on
    the sibling fixture in ``llc/services/lazy_import_test.py``: handing later
    tests re-executed module and class objects silently breaks ``isinstance``
    checks and any ``unittest.mock.patch`` target resolved before this ran.

    Scoped to ``llc.scheduler`` only — deliberately not ``llc.kb``/``llc.services``,
    whose fresh import has its own unrelated order-dependent fragility.
    """
    saved = {name: mod for name, mod in sys.modules.items() if name.startswith(_SCHEDULER_PREFIX)}
    for name in saved:
        del sys.modules[name]
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name.startswith(_SCHEDULER_PREFIX) and name not in saved:
                del sys.modules[name]
        sys.modules.update(saved)


class _RejectImport:
    """Meta-path finder that fails any import of a name under ``blocked``.

    Presence-in-sys.modules cannot prove causation in a full pytest session —
    ``llm_shared`` may already be cached by an earlier, unrelated test, in which
    case Python never re-executes it and a presence assertion would be
    order-dependent. This intercepts the *attempt* instead, so the result does
    not depend on what any other test already imported.

    Implements ``find_spec``, not the legacy ``find_module``: the latter was
    removed from the finder protocol in Python 3.12, so on this repo's 3.14 a
    ``find_module``-only finder is silently skipped and the guard would pass
    vacuously without ever blocking anything.
    """

    def __init__(self, blocked: tuple[str, ...]) -> None:
        self._blocked = blocked

    def find_spec(self, name, path=None, target=None):  # noqa: ANN001, ANN201 — importlib protocol
        if any(name == b or name.startswith(b + ".") for b in self._blocked):
            raise ImportError(f"BLOCKED: {name} must not be imported by llc.scheduler (#13332)")
        return None


# ---------------------------------------------------------------------------
# The eager half — Celery registration must survive the laziness (GH#12318)
# ---------------------------------------------------------------------------


def test_package_import_eagerly_imports_the_celery_task_modules(isolated_llc_scheduler) -> None:
    """Importing the package must import both @shared_task modules.

    This is the assertion that makes the lazy half safe. Converting either task
    module to a lazy attribute would leave every isolation test in this file
    passing while beat silently dispatched to an unregistered task.
    """
    import llc.scheduler  # noqa: F401

    missing = sorted(name for name in _EAGER_TASK_MODULES if name not in sys.modules)
    assert not missing, (
        f"llc/scheduler/__init__.py no longer eagerly imports {missing!r}. "
        "Celery autodiscovery imports only this package __init__, so their "
        "@shared_task decorators never run and beat dispatches to a worker that "
        "drops the job as 'Received unregistered task of type ...' (GH#12318)."
    )


def test_beat_task_names_resolve_to_real_callables(isolated_llc_scheduler) -> None:
    """Each llc.scheduler beat name must resolve to a callable Celery task.

    Presence of a key is not the same as a dispatchable job, so this asserts the
    registry entry is callable and carries a ``run`` — an entry that existed but
    could not be executed would still drop the job at dispatch time.
    """
    import llc.scheduler  # noqa: F401

    celery_app_mod = sys.modules.get("celery_app")
    assert celery_app_mod is not None, "celery_app module missing — check conftest.py"
    registry = celery_app_mod.celery_app.tasks

    for module_name, task_name in _EAGER_TASK_MODULES.items():
        assert task_name in registry, f"{task_name!r} (from {module_name}) is not registered on the Celery app"
        task = registry[task_name]
        assert callable(task), f"{task_name!r} is registered but not callable: {task!r}"
        assert callable(getattr(task, "run", None)), f"{task_name!r} has no callable .run: {task!r}"


# ---------------------------------------------------------------------------
# The lazy half — package import must not boot the world (#13332)
# ---------------------------------------------------------------------------


def test_package_import_does_not_import_llm_shared_or_llc_kb(isolated_llc_scheduler) -> None:
    """Acceptance criterion (#13332): importing llc.scheduler must not reach the
    LLM/vector stack.

    Before the fix the package eagerly imported ``sprint_autoclose``, which
    imported ``SprintAutoCloseService`` at module level:

        llc.services.sprint_autoclose -> llc.kb.sprint_summarizer
            -> llm_shared.types   (probes PyTorch/CUDA at import)
            -> llc.kb.collections (ChromaDB / knowledge stack)

    so importing even ``llc.scheduler.base`` — three stdlib imports — booted all
    of it, because Python initialises a parent package before its submodule.
    """
    guard = _RejectImport(("llm_shared", "llc.kb"))
    sys.meta_path.insert(0, guard)
    try:
        import llc.scheduler  # noqa: F401
    finally:
        sys.meta_path.remove(guard)


def test_package_import_does_not_import_the_scheduler_classes(isolated_llc_scheduler) -> None:
    """Package import must pull in the two task modules and nothing else."""
    import llc.scheduler  # noqa: F401

    imported = {m for m in sys.modules if m.startswith(_SCHEDULER_PREFIX + ".")}
    unexpected = imported - set(_EAGER_TASK_MODULES)
    assert not unexpected, f"importing llc.scheduler eagerly pulled in unrelated submodules: {sorted(unexpected)}"


def test_lazy_attribute_resolves_and_caches(isolated_llc_scheduler) -> None:
    """__getattr__ resolves __all__ names on first access and caches them."""
    import llc.scheduler as pkg

    assert "BudgetWatchdog" not in pkg.__dict__
    from llc.scheduler import BudgetWatchdog

    assert pkg.__dict__["BudgetWatchdog"] is BudgetWatchdog, "must cache on the package module"
    assert pkg.BudgetWatchdog is BudgetWatchdog


def test_every_lazy_submodule_is_reachable_only_on_attribute_access(isolated_llc_scheduler) -> None:
    """Each lazily-mapped class imports exactly its own submodule on access."""
    import llc.scheduler as pkg

    for name, submodule in pkg._LAZY_ATTRS.items():
        target = f"{_SCHEDULER_PREFIX}.{submodule}"
        assert target in _LAZY_SUBMODULES, f"unexpected lazy target {target!r}"
        assert getattr(pkg, name) is not None
        assert target in sys.modules, f"accessing {name!r} did not import {target!r}"


def test_unknown_attribute_raises_attribute_error(isolated_llc_scheduler) -> None:
    import llc.scheduler as pkg

    with pytest.raises(AttributeError):
        pkg.DoesNotExist  # noqa: B018


def test_all_exported_names_are_resolvable(isolated_llc_scheduler) -> None:
    """Every name the eager __init__ used to export must still resolve, so any
    existing ``from llc.scheduler import X`` call site keeps working."""
    import llc.scheduler as pkg

    for name in pkg.__all__:
        assert getattr(pkg, name) is not None
