# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Emergency-stop reporting (#16843).

``POST /system/emergency-stop`` used to return a fixed ``"Emergency stop
activated"`` success string regardless of whether anything was actually
running, and requested the takeover without telling it which tasks to pause
(``affected_tasks`` defaulted to empty). A caller could not tell "there was
nothing to stop" from "something was running and this call did nothing about
it" -- the same collapsed-signal shape as #17141's silent approval trail and
#17118's ``is_shallow_repository`` boolean.

This enumerates the tasks ``TaskExecutionTracker`` considers active at call
time, passes them to the takeover request so ``_pause_affected_tasks``
actually has something to pause, and reports exactly that list back --
plus whether the pause was recorded durably (Redis) or only in the
requesting worker's memory. ``takeover_manager`` latches to an in-process
fallback for the rest of the worker's life the first time Redis fails
(its own H1 comment); that fallback always "succeeds" from the caller's
point of view, so silently reporting it as a normal pause would collapse
two materially different outcomes into one response, the same defect
class as the fixed string this replaces. ``TakeoverManager.is_durable()``
exposes that latch.

Scope note: this reports what was *registered as paused*, not that the
underlying work was forcibly halted -- ``takeover_manager`` has no execution
interrupt today, only pause bookkeeping. Real halt/interrupt semantics are a
separate, deferred decision (#16843); nothing here should be read as
attesting to it.
"""

from __future__ import annotations

from typing import List

from autobot_shared.logging_manager import get_logger
from memory import TaskPriority  # canonical enum (#10626)
from takeover_manager import TakeoverTrigger, get_takeover_manager
from task_execution_tracker import get_task_tracker

logger = get_logger(__name__)


async def execute_emergency_stop(requesting_agent: str = "emergency_system") -> dict:
    """Request an emergency takeover and report which tasks it actually covered."""
    manager = get_takeover_manager()
    tasks_paused: List[str] = list(get_task_tracker().get_active_tasks().keys())

    request_id = await manager.request_takeover(
        trigger=TakeoverTrigger.CRITICAL_ERROR,
        reason="Emergency stop activated",
        requesting_agent=requesting_agent,
        affected_tasks=tasks_paused,
        priority=TaskPriority.CRITICAL,
        auto_approve=True,
    )
    durable = manager.is_durable()

    if not tasks_paused:
        message = "Emergency stop activated: no active tasks were running"
    elif durable:
        message = f"Emergency stop activated: paused {len(tasks_paused)} active task(s)"
    else:
        message = (
            f"Emergency stop activated: paused {len(tasks_paused)} active task(s) "
            "IN-MEMORY ONLY -- the durable store was unavailable, so this pause "
            "will not survive a worker restart and is invisible to other workers"
        )

    logger.warning("Emergency stop activated: %s (%s)", request_id, message)
    return {
        "success": True,
        "message": message,
        "takeover_request_id": request_id,
        "tasks_paused": tasks_paused,
        "durable": durable,
    }
