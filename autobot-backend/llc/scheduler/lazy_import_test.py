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

from tests.helpers._fresh_interpreter import assert_import_leaks_nothing

# Names a package import of llc.scheduler must never load (#13332).
_SCHEDULER_PREFIX = "llc.scheduler"
_BLOCKED_PREFIXES = ("llm_shared", "llc.kb")

# The modules whose eager import Celery task registration depends on, and the
# beat task name each one registers (celery_app.py beat_schedule). A new task
# module must be added HERE as well as to the package __init__ -- that is the
# point of this set: the isolation assertion below treats anything eagerly
# imported and not listed here as a leak, so a task module cannot be added to
# __init__ silently, and a module listed here cannot quietly stop registering.
_EAGER_TASK_MODULES = {
    "llc.scheduler.attachment_file_sweep": "llc.scheduler.attachment_file_sweep.run_attachment_file_sweep",
    "llc.scheduler.project_disposal_sweep": "llc.scheduler.project_disposal_sweep.run_disposal_sweep",
    "llc.scheduler.sprint_autoclose": "llc.scheduler.sprint_autoclose.run_daily_check",
    "llc.scheduler.stalled_run_sweep": "llc.scheduler.stalled_run_sweep.run_stalled_run_sweep",
    "llc.scheduler.trigger_secret_audit": "llc.scheduler.trigger_secret_audit.run_trigger_secret_audit",  # pragma: allowlist secret
    "llc.scheduler.workspace_lease_sweep": "llc.scheduler.workspace_lease_sweep.run_workspace_lease_sweep",
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


def test_package_import_does_not_import_llm_shared_or_llc_kb() -> None:
    """Acceptance criterion (#13332, #21596): importing llc.scheduler must not
    reach the LLM/vector stack.

    Run in a FRESH interpreter. The earlier in-process version removed only the
    ``llc.scheduler.*`` modules from ``sys.modules`` and refused new imports of
    the blocked names through a meta-path finder -- but a module already loaded
    by an earlier test is never re-imported, so the finder never saw it and the
    test passed while the package reached both stacks:

        llc.scheduler -> workspace_lease_sweep -> llc.services.approval
            -> llc.kb.decision_log (and the llc.kb package __init__)
        llc.services.approval -> approval_hooks -> agent_hire_service
            -> accessors -> budget -> llm_shared.pricing.sync_cache
            (llm_shared/__init__ probes PyTorch/CUDA)

    A fresh process has nothing cached, so sys.modules after the import is the
    complete set of modules the package import reaches.
    """
    assert_import_leaks_nothing("import llc.scheduler", _BLOCKED_PREFIXES)


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
