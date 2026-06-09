# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Events API — receives buffered events from node agents (#1106).
"""

import logging
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import EventSeverity, Node, NodeEvent
from services.database import get_db

logger = logging.getLogger(__name__)

# This router is intentionally unauthenticated: node agents post to /sync
# without a bearer token and are identified by node_id validated in the
# endpoint body against the Node table (#3193).  Network-layer access control
# (VPN / firewall) provides the perimeter guard.
router = APIRouter(prefix="/events", tags=["events"])


class BufferedEvent(BaseModel):
    """Single event from an agent's local buffer."""

    id: int
    type: str
    data: Dict[str, Any]
    node_id: str


class EventSyncResponse(BaseModel):
    """Response to an event sync request."""

    accepted: int
    rejected: int


@router.post("/sync", response_model=EventSyncResponse)
async def sync_events(
    events: List[BufferedEvent],
    db: AsyncSession = Depends(get_db),
) -> EventSyncResponse:
    """
    Receive buffered events from node agents (#1106).

    Agents buffer heartbeat-failure events locally and sync
    them in batches when connectivity is restored.
    """
    accepted = 0
    rejected = 0

    for evt in events:
        node_result = await db.execute(select(Node.id).where(Node.node_id == evt.node_id))
        if not node_result.scalar_one_or_none():
            rejected += 1
            continue

        node_event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=evt.node_id,
            event_type=evt.type,
            severity=EventSeverity.INFO.value,
            message=f"Buffered {evt.type} event synced from agent",
            details=evt.data,
        )
        db.add(node_event)
        accepted += 1

    if accepted:
        await db.commit()

    logger.info("Event sync: accepted=%d rejected=%d", accepted, rejected)
    return EventSyncResponse(accepted=accepted, rejected=rejected)
