# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Nodes API Routes
"""

import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Node, NodeStatus
from models.schemas import (
    HeartbeatRequest,
    NodeCreate,
    NodeListResponse,
    NodeResponse,
    NodeUpdate,
)
from services.auth import get_current_user
from services.database import get_db
from services.reconciler import reconciler_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=NodeListResponse)
async def list_nodes(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> NodeListResponse:
    """List all nodes with optional status filter."""
    query = select(Node)

    if status_filter:
        query = query.where(Node.status == status_filter)

    query = query.order_by(Node.hostname)

    count_result = await db.execute(select(Node.id).where(query.whereclause or True))
    total = len(count_result.all())

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    nodes = result.scalars().all()

    return NodeListResponse(
        nodes=[NodeResponse.model_validate(n) for n in nodes],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    node_data: NodeCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """Register a new node."""
    existing = await db.execute(
        select(Node).where(Node.ip_address == node_data.ip_address)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Node with this IP address already exists",
        )

    node_id = str(uuid.uuid4())[:8]
    node = Node(
        node_id=node_id,
        hostname=node_data.hostname,
        ip_address=node_data.ip_address,
        roles=node_data.roles,
        status=NodeStatus.PENDING.value,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)

    logger.info("Node registered: %s (%s)", node.hostname, node.ip_address)
    return NodeResponse.model_validate(node)


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """Get a node by ID."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    return NodeResponse.model_validate(node)


@router.patch("/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: str,
    node_data: NodeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """Update a node."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    update_data = node_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            if field == "status" and hasattr(value, "value"):
                value = value.value
            setattr(node, field, value)

    await db.commit()
    await db.refresh(node)

    logger.info("Node updated: %s", node_id)
    return NodeResponse.model_validate(node)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Delete a node."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    await db.delete(node)
    await db.commit()

    logger.info("Node deleted: %s", node_id)


@router.post("/{node_id}/heartbeat", response_model=NodeResponse)
async def node_heartbeat(
    node_id: str,
    heartbeat: HeartbeatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NodeResponse:
    """Receive heartbeat from node agent."""
    node = await reconciler_service.update_node_heartbeat(
        db,
        node_id,
        heartbeat.cpu_percent,
        heartbeat.memory_percent,
        heartbeat.disk_percent,
        heartbeat.agent_version,
        heartbeat.os_info,
        heartbeat.extra_data,
    )

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    return NodeResponse.model_validate(node)


@router.post("/{node_id}/enroll", response_model=NodeResponse)
async def enroll_node(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """Start node enrollment process."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    if node.status != NodeStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot enroll node in status: {node.status}",
        )

    node.status = NodeStatus.ENROLLING.value
    await db.commit()
    await db.refresh(node)

    logger.info("Node enrollment started: %s", node_id)
    return NodeResponse.model_validate(node)
