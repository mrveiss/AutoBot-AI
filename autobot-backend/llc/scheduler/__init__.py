# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC scheduler package."""

from .base import PollLoopScheduler
from .budget_watchdog import BudgetWatchdog
from .liveness_monitor import LivenessMonitor

# GH#12318: re-export the Celery task modules so Celery's autodiscover_tasks
# (called with related_name=None in celery_app.py) imports them via this
# package __init__ and registers their @shared_task decorators. Without these,
# beat dispatched llc.scheduler.sprint_autoclose.run_daily_check /
# run_disposal_sweep to a worker that never registered them ("Received
# unregistered task of type ...").
from .project_disposal_sweep import run_disposal_sweep
from .session_checkpointer import SessionCheckpointer
from .sprint_autoclose import run_daily_check

__all__ = [
    "PollLoopScheduler",
    "BudgetWatchdog",
    "LivenessMonitor",
    "SessionCheckpointer",
    "run_disposal_sweep",
    "run_daily_check",
]
