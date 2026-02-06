# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Maintenance Window API Routes

Provides endpoints for scheduling and managing maintenance windows.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import (
    EventSeverity,
    EventType,
    MaintenanceWindow,
    Node,
    NodeEvent,
    NodeStatus,
)
from models.schemas import (
    MaintenanceWindowCreate,
    MaintenanceWindowListResponse,
    MaintenanceWindowResponse,
    MaintenanceWindowUpdate,
)
from services.auth import get_current_user, require_admin
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("", response_model=MaintenanceWindowListResponse)
async def list_maintenance_windows(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    include_completed: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> MaintenanceWindowListResponse:
    """List maintenance windows with optional filters."""
    query = select(MaintenanceWindow)

    # Filter by node (include global windows)
    if node_id:
        query = query.where(
            or_(
                MaintenanceWindow.node_id == node_id,
                MaintenanceWindow.node_id.is_(None),
            )
        )

    # Filter by status
    if status_filter:
        query = query.where(MaintenanceWindow.status == status_filter)
    elif not include_completed:
        query = query.where(MaintenanceWindow.status.in_(["scheduled", "active"]))

    # Get total count
    count_result = await db.execute(
        select(MaintenanceWindow.id).where(query.whereclause or True)
    )
    total = len(count_result.all())

    # Apply pagination and ordering
    query = query.order_by(MaintenanceWindow.start_time.asc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    windows = result.scalars().all()

    return MaintenanceWindowListResponse(
        windows=[MaintenanceWindowResponse.model_validate(w) for w in windows],
        total=total,
    )


@router.get("/active", response_model=MaintenanceWindowListResponse)
async def get_active_windows(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = Query(None),
) -> MaintenanceWindowListResponse:
    """Get currently active maintenance windows."""
    now = datetime.utcnow()

    query = select(MaintenanceWindow).where(
        and_(
            MaintenanceWindow.status == "active",
            MaintenanceWindow.start_time <= now,
            MaintenanceWindow.end_time >= now,
        )
    )

    if node_id:
        query = query.where(
            or_(
                MaintenanceWindow.node_id == node_id,
                MaintenanceWindow.node_id.is_(None),
            )
        )

    result = await db.execute(query)
    windows = result.scalars().all()

    return MaintenanceWindowListResponse(
        windows=[MaintenanceWindowResponse.model_validate(w) for w in windows],
        total=len(windows),
    )


@router.get("/{window_id}", response_model=MaintenanceWindowResponse)
async def get_maintenance_window(
    window_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> MaintenanceWindowResponse:
    """Get a specific maintenance window."""
    result = await db.execute(
        select(MaintenanceWindow).where(MaintenanceWindow.window_id == window_id)
    )
    window = result.scalar_one_or_none()

    if not window:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance window not found",
        )

    return MaintenanceWindowResponse.model_validate(window)


@router.post(
    "", response_model=MaintenanceWindowResponse, status_code=status.HTTP_201_CREATED
)
async def create_maintenance_window(
    window_data: MaintenanceWindowCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(require_admin)],
) -> MaintenanceWindowResponse:
    """Create a new maintenance window (admin only)."""
    # Validate time range
    if window_data.end_time <= window_data.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End time must be after start time",
        )

    # Validate node exists if specified
    if window_data.node_id:
        node_result = await db.execute(
            select(Node).where(Node.node_id == window_data.node_id)
        )
        if not node_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Node not found",
            )

    # Determine initial status
    now = datetime.utcnow()
    if window_data.start_time <= now <= window_data.end_time:
        initial_status = "active"
    elif window_data.start_time > now:
        initial_status = "scheduled"
    else:
        initial_status = "completed"

    window = MaintenanceWindow(
        window_id=str(uuid.uuid4())[:16],
        node_id=window_data.node_id,
        start_time=window_data.start_time,
        end_time=window_data.end_time,
        reason=window_data.reason,
        auto_drain=window_data.auto_drain,
        suppress_alerts=window_data.suppress_alerts,
        suppress_remediation=window_data.suppress_remediation,
        status=initial_status,
        created_by=user.get("username"),
    )
    db.add(window)

    # If window is active and applies to a specific node, set node to maintenance status
    if initial_status == "active" and window_data.node_id:
        await _set_node_maintenance_status(
            db, window_data.node_id, True, window.window_id
        )

    await db.commit()
    await db.refresh(window)

    logger.info(
        "Maintenance window created: %s for node %s (%s - %s)",
        window.window_id,
        window.node_id or "all nodes",
        window.start_time,
        window.end_time,
    )

    return MaintenanceWindowResponse.model_validate(window)


@router.put("/{window_id}", response_model=MaintenanceWindowResponse)
async def update_maintenance_window(
    window_id: str,
    window_data: MaintenanceWindowUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> MaintenanceWindowResponse:
    """Update a maintenance window (admin only)."""
    result = await db.execute(
        select(MaintenanceWindow).where(MaintenanceWindow.window_id == window_id)
    )
    window = result.scalar_one_or_none()

    if not window:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance window not found",
        )

    # Apply updates
    if window_data.start_time is not None:
        window.start_time = window_data.start_time
    if window_data.end_time is not None:
        window.end_time = window_data.end_time
    if window_data.reason is not None:
        window.reason = window_data.reason
    if window_data.auto_drain is not None:
        window.auto_drain = window_data.auto_drain
    if window_data.suppress_alerts is not None:
        window.suppress_alerts = window_data.suppress_alerts
    if window_data.suppress_remediation is not None:
        window.suppress_remediation = window_data.suppress_remediation
    if window_data.status is not None:
        old_status = window.status
        window.status = window_data.status

        # Handle status transitions
        if old_status != window_data.status:
            if window_data.status == "active" and window.node_id:
                await _set_node_maintenance_status(
                    db, window.node_id, True, window.window_id
                )
            elif window_data.status in ["completed", "cancelled"] and window.node_id:
                await _set_node_maintenance_status(
                    db, window.node_id, False, window.window_id
                )

    # Validate time range
    if window.end_time <= window.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End time must be after start time",
        )

    await db.commit()
    await db.refresh(window)

    logger.info("Maintenance window updated: %s", window_id)
    return MaintenanceWindowResponse.model_validate(window)


@router.delete("/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_maintenance_window(
    window_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> None:
    """Delete a maintenance window (admin only)."""
    result = await db.execute(
        select(MaintenanceWindow).where(MaintenanceWindow.window_id == window_id)
    )
    window = result.scalar_one_or_none()

    if not window:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance window not found",
        )

    # If window is active, restore node status
    if window.status == "active" and window.node_id:
        await _set_node_maintenance_status(db, window.node_id, False, window.window_id)

    await db.delete(window)
    await db.commit()

    logger.info("Maintenance window deleted: %s", window_id)


@router.post("/{window_id}/activate", response_model=MaintenanceWindowResponse)
async def activate_maintenance_window(
    window_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> MaintenanceWindowResponse:
    """Manually activate a scheduled maintenance window (admin only)."""
    result = await db.execute(
        select(MaintenanceWindow).where(MaintenanceWindow.window_id == window_id)
    )
    window = result.scalar_one_or_none()

    if not window:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance window not found",
        )

    if window.status != "scheduled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot activate window in status: {window.status}",
        )

    window.status = "active"
    window.start_time = datetime.utcnow()

    if window.node_id:
        await _set_node_maintenance_status(db, window.node_id, True, window.window_id)

    await db.commit()
    await db.refresh(window)

    logger.info("Maintenance window activated: %s", window_id)
    return MaintenanceWindowResponse.model_validate(window)


@router.post("/{window_id}/complete", response_model=MaintenanceWindowResponse)
async def complete_maintenance_window(
    window_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> MaintenanceWindowResponse:
    """Manually complete an active maintenance window (admin only)."""
    result = await db.execute(
        select(MaintenanceWindow).where(MaintenanceWindow.window_id == window_id)
    )
    window = result.scalar_one_or_none()

    if not window:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance window not found",
        )

    if window.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete window in status: {window.status}",
        )

    window.status = "completed"
    window.end_time = datetime.utcnow()

    if window.node_id:
        await _set_node_maintenance_status(db, window.node_id, False, window.window_id)

    await db.commit()
    await db.refresh(window)

    logger.info("Maintenance window completed: %s", window_id)
    return MaintenanceWindowResponse.model_validate(window)


async def _set_node_maintenance_status(
    db: AsyncSession, node_id: str, entering_maintenance: bool, window_id: str
) -> None:
    """Set or clear maintenance status for a node."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        return

    if entering_maintenance:
        # Store previous status and set to maintenance
        old_status = node.status
        node.extra_data = {
            **(node.extra_data or {}),
            "pre_maintenance_status": old_status,
            "maintenance_window_id": window_id,
        }
        node.status = NodeStatus.MAINTENANCE.value

        # Create maintenance start event
        event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=node_id,
            event_type=EventType.MANUAL_ACTION.value,
            severity=EventSeverity.INFO.value,
            message=f"Node {node.hostname} entered maintenance mode",
            details={"window_id": window_id, "previous_status": old_status},
        )
        db.add(event)

        logger.info("Node %s entered maintenance mode", node_id)
    else:
        # Restore previous status
        pre_maintenance_status = (node.extra_data or {}).get(
            "pre_maintenance_status", NodeStatus.ONLINE.value
        )
        node.status = pre_maintenance_status

        # Clear maintenance data
        if node.extra_data:
            extra_data = dict(node.extra_data)
            extra_data.pop("pre_maintenance_status", None)
            extra_data.pop("maintenance_window_id", None)
            node.extra_data = extra_data

        # Create maintenance end event
        event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=node_id,
            event_type=EventType.MANUAL_ACTION.value,
            severity=EventSeverity.INFO.value,
            message=f"Node {node.hostname} exited maintenance mode",
            details={"window_id": window_id, "restored_status": pre_maintenance_status},
        )
        db.add(event)

        logger.info("Node %s exited maintenance mode", node_id)


async def is_node_in_maintenance(db: AsyncSession, node_id: str) -> bool:
    """Check if a node is currently in a maintenance window."""
    now = datetime.utcnow()

    result = await db.execute(
        select(MaintenanceWindow)
        .where(
            and_(
                MaintenanceWindow.status == "active",
                MaintenanceWindow.start_time <= now,
                MaintenanceWindow.end_time >= now,
                or_(
                    MaintenanceWindow.node_id == node_id,
                    MaintenanceWindow.node_id.is_(None),
                ),
            )
        )
        .limit(1)
    )

    return result.scalar_one_or_none() is not None


async def should_suppress_remediation(db: AsyncSession, node_id: str) -> bool:
    """Check if remediation should be suppressed for a node."""
    now = datetime.utcnow()

    result = await db.execute(
        select(MaintenanceWindow)
        .where(
            and_(
                MaintenanceWindow.status == "active",
                MaintenanceWindow.start_time <= now,
                MaintenanceWindow.end_time >= now,
                MaintenanceWindow.suppress_remediation.is_(True),
                or_(
                    MaintenanceWindow.node_id == node_id,
                    MaintenanceWindow.node_id.is_(None),
                ),
            )
        )
        .limit(1)
    )

    return result.scalar_one_or_none() is not None
