# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one activity row for an agent's heartbeat being switched (#15907).

Shared by the single-agent toggle (``ControlsService.set_agent_heartbeat``) and the
company soft-delete, so the same operation leaves the same row on every route.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import ActivityEventType
from .activity_log import LLCActivityLogService


async def record_heartbeat_set(
    activity_log: LLCActivityLogService,
    session: AsyncSession,
    company_id: str,
    agent_id: str,
    actor_user_id: Optional[str],
    before: dict[str, Any],
    after: dict[str, Any],
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Append ``CONTROL_AGENT_HEARTBEAT_SET`` in the caller's transaction."""
    await activity_log.record(
        session=session,
        company_id=company_id,
        actor_type="user" if actor_user_id else "system",
        actor_id=actor_user_id,
        event_type=ActivityEventType.CONTROL_AGENT_HEARTBEAT_SET,
        entity_type="agent",
        entity_id=agent_id,
        before=before,
        after=after,
        metadata=metadata,
    )
