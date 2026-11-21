# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one activity row for an agent's heartbeat being switched (#15907).

Shared by the single-agent toggle (``ControlsService.set_agent_heartbeat``) and the
company soft-delete, so the same operation leaves the same row on every route.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import ActivityEventType
from .activity_log import LLCActivityLogService


async def record_heartbeat_set(
    activity_log: LLCActivityLogService,
    session: AsyncSession,
    company_id: str,
    node_id: uuid.UUID,
    actor_user_id: Optional[str],
    before: dict[str, Any],
    after: dict[str, Any],
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Append ``CONTROL_AGENT_HEARTBEAT_SET`` in the caller's transaction.

    The activity log keys ``entity_id`` as a UUID, so this takes the agent node's primary
    key, never its ``agent_id`` slug.
    """
    await activity_log.record(
        session=session,
        company_id=company_id,
        actor_type="user" if actor_user_id else "system",
        actor_id=actor_user_id,
        event_type=ActivityEventType.CONTROL_AGENT_HEARTBEAT_SET,
        entity_type="agent",
        entity_id=str(node_id),
        before=before,
        after=after,
        metadata=metadata,
    )
