# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Heartbeats API

REST endpoints for agent heartbeat handling.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.services.slm.db_service import SLMDatabaseService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm", tags=["SLM Heartbeats"])

# Singleton database service
_db_service: Optional[SLMDatabaseService] = None


def get_db_service() -> SLMDatabaseService:
    """Get or create database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = SLMDatabaseService()
    return _db_service


class HeartbeatRequest(BaseModel):
    """Request model for heartbeat."""
    node_id: str
    health: Dict
    timestamp: str


class HeartbeatResponse(BaseModel):
    """Response model for heartbeat."""
    accepted: bool
    node_state: str


class EventSyncRequest(BaseModel):
    """Request model for event sync."""
    id: int
    type: str
    data: Dict


@router.post("/heartbeats", response_model=HeartbeatResponse)
async def receive_heartbeat(heartbeat: HeartbeatRequest):
    """Receive heartbeat from node agent."""
    db = get_db_service()
    node = db.get_node(heartbeat.node_id)

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{heartbeat.node_id}' not found",
        )

    # Parse timestamp
    try:
        heartbeat_time = datetime.fromisoformat(heartbeat.timestamp)
    except ValueError:
        heartbeat_time = datetime.utcnow()

    # Update health
    db.update_node_health(
        node_id=heartbeat.node_id,
        health_data=heartbeat.health,
        heartbeat_time=heartbeat_time,
    )

    logger.debug(
        "Heartbeat received from %s (cpu=%.1f%%, mem=%.1f%%)",
        node.name,
        heartbeat.health.get("cpu_percent", 0),
        heartbeat.health.get("memory_percent", 0),
    )

    return HeartbeatResponse(
        accepted=True,
        node_state=node.state,
    )


@router.post("/events/sync", status_code=status.HTTP_200_OK)
async def sync_events(events: List[EventSyncRequest]):
    """Sync buffered events from node agent."""
    logger.info("Received %d buffered events for sync", len(events))

    for event in events:
        logger.debug("Processing buffered event: type=%s, id=%d", event.type, event.id)

    return {"synced": len(events)}
