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
_REGISTRY_PATH = Path(__file__).parent.parent.parent / "services" / "scheduler_registry.py"
_spec = importlib.util.spec_from_file_location("services.scheduler_registry", _REGISTRY_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["services.scheduler_registry"] = _mod  # register before exec so @dataclass resolves
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
REGISTRY = _mod.REGISTRY
ScheduledJob = _mod.ScheduledJob

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
    valid = {"asyncio_per_worker", "celery_beat", "leader_elected", "apscheduler"}
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

# Runtimes whose jobs are launched from initialization/lifespan.py. celery_beat jobs
# are launched by the Celery beat schedule instead, so they are exempt.
_LIFESPAN_RUNTIMES = {"asyncio_per_worker", "leader_elected", "apscheduler"}

_LIFESPAN_PATH = _BACKEND_ROOT / "initialization" / "lifespan.py"


def test_lifespan_jobs_declare_startup_or_inertness() -> None:
    """Every lifespan-run job declares exactly one of startup_marker / inert_reason.

    Registration never made a job run. SkillHealthScheduler and MeshBrainScheduler were
    both registered, described, and dead — the fact buried in prose in `description`,
    where nothing could enforce it. Forcing an explicit declaration makes "registered
    but silently inert" a test failure instead of a discovery months later.
    """
    for job in REGISTRY:
        if job.runtime not in _LIFESPAN_RUNTIMES:
            continue
        declared = [f for f in (job.startup_marker, job.inert_reason) if f]
        assert len(declared) == 1, (
            f"REGISTRY entry '{job.name}' ({job.runtime}) must declare exactly one of "
            f"startup_marker or inert_reason, got {len(declared)}. "
            "Set startup_marker to the symbol that starts it in initialization/lifespan.py, "
            "or set inert_reason to state why it deliberately does not run."
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
        if job.runtime in _LIFESPAN_RUNTIMES and job.startup_marker and job.startup_marker not in source
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
