# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Events API — receives buffered events from node agents (#1106).
"""

import logging
import uuid
from typing import Any, Dict, List

from database import get_db
from fastapi import APIRouter, Depends
from models.database import EventSeverity, Node, NodeEvent
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

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
        node_result = await db.execute(
            select(Node.id).where(Node.node_id == evt.node_id)
        )
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
