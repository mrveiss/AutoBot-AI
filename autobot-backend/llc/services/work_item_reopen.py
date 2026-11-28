# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reopening a work item out of ``done`` is recorded in the activity log (#20508, owner decision 2026-11-21)."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from ..models.enums import ActivityEventType, WorkItemStatus
from .actor import audit, resolve_actor


async def record_reopen(
    log: Any, session: Any, item: Any, before: WorkItemStatus, acting_user: Optional[uuid.UUID]
) -> None:
    """Write the "status changed" row for a move out of ``done``; any other move writes nothing here.

    The row names the verified person who reopened it (the system when no person did) and carries the
    before and after status, so a finished task coming back is never silent.
    """
    if before != WorkItemStatus.DONE or item.status == WorkItemStatus.DONE:
        return
    actor = resolve_actor(user_id=str(acting_user) if acting_user else None)
    await audit(
        log,
        session,
        company_id=str(item.company_id),
        actor_type=actor.type,
        actor_id=actor.id,
        metadata=actor.metadata(),
        event_type=ActivityEventType.WORK_ITEM_STATUS_CHANGED,
        entity_type="work_item",
        entity_id=str(item.id),
        before={"status": before.value},
        after={"status": WorkItemStatus(item.status).value, "reopened": True},
    )
