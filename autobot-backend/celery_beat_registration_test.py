# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every Celery beat-scheduled task must be registered on a worker (GH#12318).

Background
----------
``celery_app.autodiscover_tasks(["tasks", "workers"])`` defaulted to
``related_name="tasks"``, so Celery tried to import ``tasks/tasks.py`` and
``workers/tasks.py`` — neither exists — and the call was a silent no-op. Only
task modules that celery_app.py imported *explicitly* actually registered.
Beat happily dispatched the other scheduled names (credential reconcile,
snapshot cleanup, LLC sprint auto-close, audit daemons, trajectory
consolidation) to workers that had never registered them, so the worker logged
``Received unregistered task of type ...`` and dropped the job. Four scheduled
maintenance jobs had never run on the deployment.

The fix switches discovery to ``related_name=None`` (imports each package
``__init__`` so its re-exported task modules load) over
``["tasks", "workers", "llc.scheduler"]`` and wires the two ``llc.scheduler``
task modules into that package's ``__init__``.

What this test does
-------------------
It parses every ``"task": "<name>"`` from celery_app.py's ``beat_schedule``,
imports the exact registration surface celery_app.py loads at startup (the
autodiscovered packages plus ``services.pricing_refresh``), and asserts every
scheduled task name is present in the Celery task registry. A scheduled task
whose module is not wired in fails here loud and immediate, instead of silently
in production.

Infrastructure stubs (celery_app, redis, logging) come from the top-level
``conftest.py``; ``sys.modules["celery_app"].celery_app`` is the shared
in-process Celery app the task decorators register against.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
_CELERY_APP_SRC = (_BACKEND_DIR / "celery_app.py").read_text(encoding="utf-8")

# Registration surface celery_app.py loads at worker/beat startup: the packages
# passed to autodiscover_tasks(..., related_name=None) plus the one task module
# that lives outside them (services/, GH#6480).
_REGISTRATION_IMPORTS = ["tasks", "workers", "llc.scheduler", "services.pricing_refresh"]

# GH#12318: the exact names that were silently dropped as unregistered — an
# explicit floor so the guard is meaningful even if the beat_schedule parse
# ever regresses.
_KNOWN_DROPPED = {
    "tasks.reconcile_credentials",
    "tasks.cleanup_expired_snapshots",
    "llc.scheduler.sprint_autoclose.run_daily_check",
    "workers.audit_testgaps",
    "workers.audit_dead_code",
    "workers.audit_claims",
    "memory.consolidate_trajectories",
}


def _scheduled_task_names() -> set[str]:
    """Task names celery_app.py's beat_schedule dispatches (parsed from source).

    celery_app.py is heavy and pytest-stubbed (#7766), so the schedule is read
    from source text rather than by importing the real module — the same
    approach as celery_queue_coverage_test.py.
    """
    names = set(re.findall(r'"task":\s*"([\w.]+)"', _CELERY_APP_SRC))
    assert names, "no beat_schedule task names parsed from celery_app.py"
    return names


def _registered_task_names() -> set[str]:
    """Import the startup registration surface and return the Celery registry."""
    for module in _REGISTRATION_IMPORTS:
        importlib.import_module(module)
    celery_app_mod = sys.modules.get("celery_app")
    assert celery_app_mod is not None, "celery_app stub missing — check conftest.py"
    return set(celery_app_mod.celery_app.tasks)


def test_known_dropped_tasks_are_registered():
    """The GH#12318 tasks that never ran must now be in the registry."""
    registered = _registered_task_names()
    missing = sorted(_KNOWN_DROPPED - registered)
    assert not missing, f"GH#12318 tasks still unregistered (would be dropped by workers): {missing!r}"


def test_autodiscover_imports_task_packages_not_dot_tasks():
    """celery_app.py must autodiscover with related_name=None over every package.

    Guards the root-cause fix directly: the default related_name="tasks" imports
    "<pkg>.tasks" (non-existent) and registers nothing. Reverting to that default
    or dropping a package from the list would silently re-break discovery, so
    assert the call keeps related_name=None and covers the three task packages.
    """
    match = re.search(r"autodiscover_tasks\(\s*(\[[^\]]*\])\s*,\s*related_name=None\s*\)", _CELERY_APP_SRC)
    assert match, "autodiscover_tasks must be called with related_name=None (GH#12318 root cause)"
    packages = set(re.findall(r'"([\w.]+)"', match.group(1)))
    for required in ("tasks", "workers", "llc.scheduler"):
        assert required in packages, f"autodiscover_tasks must include the {required!r} package; got {packages!r}"


def test_every_beat_scheduled_task_is_registered():
    """Every beat_schedule task must resolve to a registered Celery task.

    Guards the whole schedule: a task added to beat_schedule whose module is not
    wired into the discovered packages (or services) fails here rather than
    silently as 'Received unregistered task of type ...' in production.
    """
    scheduled = _scheduled_task_names()
    registered = _registered_task_names()
    missing = sorted(scheduled - registered)
    assert not missing, (
        f"beat_schedule dispatches tasks no worker registers: {missing!r}\n"
        f"Fix: ensure each task's module is imported at worker startup — add its "
        f"package to celery_app.autodiscover_tasks (related_name=None) or import "
        f"it explicitly, and re-export it from that package's __init__.py."
    )
