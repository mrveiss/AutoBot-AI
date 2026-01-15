# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Updates API Routes
"""

import logging
import uuid
from typing import Optional

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import EventSeverity, EventType, Node, NodeEvent, UpdateInfo
from models.schemas import (
    UpdateApplyRequest,
    UpdateApplyResponse,
    UpdateCheckResponse,
    UpdateInfoResponse,
)
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/updates", tags=["updates"])


async def _create_node_event(
    db: AsyncSession,
    node_id: str,
    event_type: EventType,
    severity: EventSeverity,
    message: str,
    details: dict = None,
) -> NodeEvent:
    """Helper to create a node event."""
    event = NodeEvent(
        event_id=str(uuid.uuid4())[:16],
        node_id=node_id,
        event_type=event_type.value,
        severity=severity.value,
        message=message,
        details=details or {},
    )
    db.add(event)
    await db.commit()
    return event


@router.get("/check", response_model=UpdateCheckResponse)
async def check_updates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = Query(None),
) -> UpdateCheckResponse:
    """Check for available updates."""
    query = select(UpdateInfo).where(UpdateInfo.is_applied == False)

    if node_id:
        query = query.where(
            or_(UpdateInfo.node_id == node_id, UpdateInfo.node_id.is_(None))
        )

    query = query.order_by(UpdateInfo.severity.desc(), UpdateInfo.created_at.desc())

    result = await db.execute(query)
    updates = result.scalars().all()

    return UpdateCheckResponse(
        updates=[UpdateInfoResponse.model_validate(u) for u in updates],
        total=len(updates),
    )


@router.post("/apply", response_model=UpdateApplyResponse)
async def apply_updates(
    request: UpdateApplyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateApplyResponse:
    """Apply updates to a node."""
    result = await db.execute(select(Node).where(Node.node_id == request.node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    updates_result = await db.execute(
        select(UpdateInfo).where(UpdateInfo.update_id.in_(request.update_ids))
    )
    updates = updates_result.scalars().all()

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No valid updates found",
        )

    job_id = str(uuid.uuid4())[:16]

    await _create_node_event(
        db,
        request.node_id,
        EventType.DEPLOYMENT_STARTED,
        EventSeverity.INFO,
        f"Applying {len(updates)} update(s)",
        {"job_id": job_id, "update_ids": request.update_ids},
    )

    logger.info("Update job started: %s for node %s", job_id, request.node_id)

    return UpdateApplyResponse(
        success=True,
        message=f"Update job started for {len(updates)} package(s)",
        job_id=job_id,
    )
