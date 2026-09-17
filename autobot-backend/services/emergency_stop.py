# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Enumerate what an emergency stop actually pauses, and request the takeover.

#16843: ``request_takeover`` was never given ``affected_tasks``, so it always
defaulted to an empty list -- the "stop" paused nothing while still reporting
success. This enumerates what is running at the moment of the call and reports
what it found, so an empty result means "nothing was running" rather than
silently meaning nothing was ever checked.

**What this does not do.** It marks tasks paused for audit and visibility; it
does not interrupt in-flight execution, because no code path currently checks
paused-task state before continuing work. That is the still-open question on
#16843 and is stated here rather than implied by a function named "stop".

Extracted from ``api/advanced_control.py`` (#16854): that module is
grandfathered in the file-size ratchet at 626 lines and every line of slack it
has is inside route docstrings, which FastAPI publishes as OpenAPI
``description`` text and which therefore reach
``autobot-frontend/src/types/generated/api.ts``. Reflowing those to buy space
would have rewritten the published API schema to satisfy a line count. Moving
the logic out instead keeps the reasoning next to the code it explains and
makes the enumeration testable without standing up the route.

This is also why the rationale lives here as a module docstring rather than in
the route's own docstring: an endpoint description is client-facing, and no
place to describe how to defeat a safety control (#16827).
"""

from __future__ import annotations

from typing import List, Tuple

from memory import TaskPriority  # canonical enum (#10626)
from takeover_manager import TakeoverTrigger, get_takeover_manager
from task_execution_tracker import get_task_tracker


async def request_emergency_stop() -> Tuple[str, List[str]]:
    """Request a critical takeover over everything currently running.

    Returns ``(request_id, affected_task_ids)``. ``affected_task_ids`` is empty
    only when nothing was running -- never because the query was skipped.
    """
    affected_task_ids = list(get_task_tracker().get_active_tasks().keys())
    request_id = await get_takeover_manager().request_takeover(
        trigger=TakeoverTrigger.CRITICAL_ERROR,
        reason="Emergency stop activated",
        requesting_agent="emergency_system",
        affected_tasks=affected_task_ids,
        priority=TaskPriority.CRITICAL,
        auto_approve=True,
    )
    return request_id, affected_task_ids
