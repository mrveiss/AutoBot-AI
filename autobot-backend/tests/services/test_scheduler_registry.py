# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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


def _discover_scheduler_files() -> list[str]:
    """Return background scheduler implementation paths relative to the backend root.

    Excludes __pycache__, test files (test_*.py and *_test.py), api/ endpoint
    modules, and the registry file itself — only actual scheduler implementations.
    """
    return [
        str(p.relative_to(_BACKEND_ROOT))
        for p in _BACKEND_ROOT.rglob("*scheduler*.py")
        if "__pycache__" not in str(p)
        and not p.name.startswith("test_")
        and not p.name.endswith("_test.py")
        and "autobot-backend/api/" not in str(p).replace("\\", "/")
        and p.resolve() != _REGISTRY_PATH.resolve()
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
