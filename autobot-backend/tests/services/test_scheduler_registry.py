# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Enforcement test: every *scheduler*.py in the backend must be in REGISTRY (GH#6594).

This test discovers all scheduler files on disk and asserts each is referenced
by at least one entry in REGISTRY.owner_file, preventing silent scheduler additions.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Import scheduler_registry directly to avoid services/__init__.py pulling in
# ai_stack_client (which transitively imports autobot_shared modules that require
# Python 3.11+ when using the | union syntax without 'from __future__ import annotations').
#
# #13361: the sys.modules registration below is bracketed by a try/finally so it
# lasts exactly as long as the module body needs it.
_REGISTRY_PATH = Path(__file__).parent.parent.parent / "services" / "scheduler_registry.py"
_REGISTRY_KEY = "services.scheduler_registry"

_MISSING = object()


def _load_registry_module():
    """Execute scheduler_registry.py and leave ``sys.modules`` as it was found.

    The entry has to exist *while* the module executes — ``@dataclass`` resolves
    ``ScheduledJob``'s annotations through ``sys.modules[__name__]`` — but not one
    moment longer. Leaving it behind replaced whatever the backend conftest had
    registered under this name for the rest of the session, which is the escape
    #13361 is about; the module object this returns keeps working either way,
    because every name the tests use is read off it directly below.
    """
    spec = importlib.util.spec_from_file_location(_REGISTRY_KEY, _REGISTRY_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    prior = sys.modules.get(_REGISTRY_KEY, _MISSING)
    sys.modules[_REGISTRY_KEY] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        if prior is _MISSING:
            sys.modules.pop(_REGISTRY_KEY, None)
        else:
            sys.modules[_REGISTRY_KEY] = prior  # type: ignore[assignment]
    return mod


_mod = _load_registry_module()
REGISTRY = _mod.REGISTRY
ScheduledJob = _mod.ScheduledJob
# GH#12836: pulled from the registry so the valid-runtime set and the
# lifespan-managed subset have exactly one definition.
SCHEDULER_RUNTIMES = _mod.SCHEDULER_RUNTIMES
LIFESPAN_RUNTIMES = _mod.LIFESPAN_RUNTIMES
NON_LIFESPAN_RUNTIMES = _mod.NON_LIFESPAN_RUNTIMES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).parent.parent.parent


# Modules whose filename matches the *scheduler* glob but which are not themselves
# scheduled jobs — support code about schedulers rather than an implementation of one.
# Deliberately an explicit list: anything added here must be justified, so the discovery
# net cannot be quietly widened to hide a real unregistered scheduler.
_NOT_SCHEDULER_IMPLEMENTATIONS = {
    # GH#12820: resolves each registered job's effective on/off state. It owns no loop
    # and runs no job; registering it would assert a scheduler that does not exist.
    "services/scheduler_toggles.py",
}


def _discover_scheduler_files() -> list[str]:
    """Return background scheduler implementation paths relative to the backend root.

    Excludes __pycache__, test files (test_*.py and *_test.py), api/ endpoint
    modules, Alembic migrations (migrations/versions/*scheduler*.py are DB
    migrations, not scheduler implementations), the registry file itself, and the
    support modules in ``_NOT_SCHEDULER_IMPLEMENTATIONS`` — only actual scheduler
    implementations.
    """
    return [
        rel
        for p in _BACKEND_ROOT.rglob("*scheduler*.py")
        if "__pycache__" not in str(p)
        and not p.name.startswith("test_")
        and not p.name.endswith("_test.py")
        and "autobot-backend/api/" not in str(p).replace("\\", "/")
        and "/migrations/" not in str(p).replace("\\", "/")
        and p.resolve() != _REGISTRY_PATH.resolve()
        and (rel := str(p.relative_to(_BACKEND_ROOT)).replace("\\", "/")) not in _NOT_SCHEDULER_IMPLEMENTATIONS
    ]


# ---------------------------------------------------------------------------
# Registry shape tests
# ---------------------------------------------------------------------------


def test_registry_is_nonempty() -> None:
    assert len(REGISTRY) > 0, "REGISTRY must contain at least one entry"


def test_registry_entries_are_scheduled_jobs() -> None:
    for job in REGISTRY:
        assert isinstance(job, ScheduledJob), f"REGISTRY entry is not a ScheduledJob: {job!r}"


def test_registry_names_are_unique() -> None:
    names = [job.name for job in REGISTRY]
    duplicates = [n for n in names if names.count(n) > 1]
    assert not duplicates, f"Duplicate names in REGISTRY: {set(duplicates)}"


def test_registry_runtimes_are_valid() -> None:
    valid = SCHEDULER_RUNTIMES  # GH#12836: imported, never restated
    for job in REGISTRY:
        assert job.runtime in valid, (
            f"REGISTRY entry '{job.name}' has unknown runtime '{job.runtime}'. " f"Valid values: {valid}"
        )


# ---------------------------------------------------------------------------
# Enforcement test: all scheduler files must be registered
# ---------------------------------------------------------------------------


def test_all_scheduler_files_registered() -> None:
    """Every *scheduler*.py on disk must appear in REGISTRY.owner_file.

    If this test fails, add the new scheduler file to
    autobot-backend/services/scheduler_registry.py before merging.
    """
    registered_owner_files = {job.owner_file for job in REGISTRY}
    discovered = _discover_scheduler_files()

    unregistered = [f for f in discovered if f not in registered_owner_files]

    assert not unregistered, (
        "The following scheduler files are NOT registered in "
        "services/scheduler_registry.REGISTRY:\n"
        + "\n".join(f"  - {f}" for f in sorted(unregistered))
        + "\n\nAdd an entry for each file to autobot-backend/services/scheduler_registry.py."
    )


# ---------------------------------------------------------------------------
# Enforcement test: a registered job must actually start (GH#12810)
# ---------------------------------------------------------------------------

# GH#12836: imported from the registry rather than re-listed here. A hand-kept
# copy of this subset meant a new runtime could be added to the type and silently
# skipped by the gate below.
_LIFESPAN_RUNTIMES = LIFESPAN_RUNTIMES

_LIFESPAN_PATH = _BACKEND_ROOT / "initialization" / "lifespan.py"


def _marker_symbol(marker: str) -> str:
    """The symbol a startup_marker names, tolerating a ``path::symbol`` qualifier.

    Both spellings are in use — a bare ``_init_x`` and a qualified
    ``initialization/lifespan.py::_init_x`` (#12816) — and both identify the same
    function. Only the symbol is searched for, so a marker is validated by what it
    points at rather than by how it was written.
    """
    return marker.rsplit("::", 1)[-1]


def test_lifespan_jobs_declare_startup_or_inertness() -> None:
    """Every lifespan-run job declares a startup_marker, an inert_reason, or both.

    Registration never made a job run. SkillHealthScheduler and MeshBrainScheduler were
    both registered, described, and dead — the fact buried in prose in `description`,
    where nothing could enforce it. Forcing an explicit declaration makes "registered
    but silently inert" a test failure instead of a discovery months later.

    Both fields together is a legitimate state, not a contradiction (#12816 + #12820):
    a job can be genuinely wired into lifespan *and* deliberately default-off, where
    `default_enabled=False` carries the off-ness and `inert_reason` explains why. This
    check originally demanded exactly one, which forbade that combination — the wiring
    gap and the enable decision are separate facts, and a job is allowed to state both.
    """
    for job in REGISTRY:
        if job.runtime not in _LIFESPAN_RUNTIMES:
            continue
        assert job.startup_marker or job.inert_reason, (
            f"REGISTRY entry '{job.name}' ({job.runtime}) declares neither startup_marker "
            "nor inert_reason. Set startup_marker to the symbol that starts it in "
            "initialization/lifespan.py, and/or inert_reason to state why it does not run."
        )


def test_declared_startup_markers_exist_in_lifespan() -> None:
    """A declared startup_marker must actually appear in initialization/lifespan.py.

    Guards the failure this whole check exists for: a job claiming to be started by a
    function nobody ever calls, or one renamed out from under the registry.
    """
    source = _LIFESPAN_PATH.read_text(encoding="utf-8")

    missing = [
        (job.name, job.startup_marker)
        for job in REGISTRY
        if job.runtime in _LIFESPAN_RUNTIMES and job.startup_marker and _marker_symbol(job.startup_marker) not in source
    ]

    assert not missing, (
        "These REGISTRY entries name a startup_marker absent from initialization/lifespan.py:\n"
        + "\n".join(f"  - {name}: '{marker}'" for name, marker in sorted(missing))
        + "\n\nEither wire the scheduler up in lifespan.py or correct the marker."
    )


def test_inert_jobs_cite_a_tracking_issue() -> None:
    """An inert job must point at an issue, so the decision stays revisitable.

    An inert_reason with no tracking issue is how a dead scheduler becomes permanent.
    """
    for job in REGISTRY:
        if not job.inert_reason:
            continue
        assert "#" in job.inert_reason, (
            f"REGISTRY entry '{job.name}' is declared inert without citing a tracking issue. "
            f"Add the issue number to inert_reason: {job.inert_reason!r}"
        )


# ---------------------------------------------------------------------------
# GH#12836: the runtime sets must stay exhaustive and disjoint
# ---------------------------------------------------------------------------


def test_every_runtime_is_classified_as_lifespan_or_not() -> None:
    """A new runtime must be explicitly classified, not silently exempted.

    _LIFESPAN_RUNTIMES gates the #12810 startup-enforcement check. Before this,
    that subset was a hand-kept copy: adding a runtime to the type and forgetting
    the subset meant every job using it was skipped by the gate, with all tests
    still green — the exact failure the gate exists to prevent.
    """
    classified = LIFESPAN_RUNTIMES | NON_LIFESPAN_RUNTIMES
    unclassified = SCHEDULER_RUNTIMES - classified

    assert not unclassified, (
        f"Runtime(s) {sorted(unclassified)} are declared in SchedulerRuntime but not "
        "classified in scheduler_registry. Add each to LIFESPAN_RUNTIMES (launched "
        "from initialization/lifespan.py) or NON_LIFESPAN_RUNTIMES (launched "
        "elsewhere, e.g. Celery beat) — otherwise the GH#12810 startup check "
        "silently skips every job using it."
    )


def test_runtime_classifications_do_not_overlap() -> None:
    overlap = LIFESPAN_RUNTIMES & NON_LIFESPAN_RUNTIMES
    assert not overlap, f"Runtime(s) {sorted(overlap)} are in both classifications"


def test_classified_runtimes_are_all_real() -> None:
    """Neither classification may name a runtime the type does not declare."""
    unknown = (LIFESPAN_RUNTIMES | NON_LIFESPAN_RUNTIMES) - SCHEDULER_RUNTIMES
    assert not unknown, f"Unknown runtime(s) in classification sets: {sorted(unknown)}"
