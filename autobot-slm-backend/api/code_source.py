# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Source API Routes (Issue #779).

Manages the code-source node assignment and git notifications.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import CodeSource, Node, NodeRole, RoleStatus
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/code-source", tags=["code-source"])


class CodeSourceResponse(BaseModel):
    """Code source configuration response."""

    node_id: str
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    repo_path: str
    branch: str
    last_known_commit: Optional[str] = None
    last_notified_at: Optional[datetime] = None
    is_active: bool

    class Config:
        from_attributes = True


class CodeSourceAssign(BaseModel):
    """Assign code-source to a node."""

    node_id: str
    repo_path: str = "/home/kali/Desktop/AutoBot"
    branch: str = "main"


class CodeNotification(BaseModel):
    """Git commit notification from code-source."""

    node_id: str
    commit: str
    branch: str = "main"
    message: Optional[str] = None
    is_code_source: bool = True


class CodeNotificationResponse(BaseModel):
    """Response to code notification."""

    success: bool
    message: str
    commit: str
    outdated_nodes: int = 0


@router.get("", response_model=Optional[CodeSourceResponse])
async def get_active_code_source(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> Optional[CodeSourceResponse]:
    """Get the active code source configuration."""
    result = await db.execute(select(CodeSource).where(CodeSource.is_active.is_(True)))
    source = result.scalar_one_or_none()

    if not source:
        return None

    # Get node info
    node_result = await db.execute(select(Node).where(Node.node_id == source.node_id))
    node = node_result.scalar_one_or_none()

    return CodeSourceResponse(
        node_id=source.node_id,
        hostname=node.hostname if node else None,
        ip_address=node.ip_address if node else None,
        repo_path=source.repo_path,
        branch=source.branch,
        last_known_commit=source.last_known_commit,
        last_notified_at=source.last_notified_at,
        is_active=source.is_active,
    )


@router.post("/assign", response_model=CodeSourceResponse)
async def assign_code_source(
    data: CodeSourceAssign,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CodeSourceResponse:
    """Assign a node as code-source."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == data.node_id))
    node = node_result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node not found: {data.node_id}",
        )

    # Deactivate any existing code-source
    existing_result = await db.execute(
        select(CodeSource).where(CodeSource.is_active.is_(True))
    )
    for existing in existing_result.scalars().all():
        existing.is_active = False

    # Check if this node already has a code-source record
    source_result = await db.execute(
        select(CodeSource).where(CodeSource.node_id == data.node_id)
    )
    source = source_result.scalar_one_or_none()

    if source:
        source.is_active = True
        source.repo_path = data.repo_path
        source.branch = data.branch
    else:
        source = CodeSource(
            node_id=data.node_id,
            repo_path=data.repo_path,
            branch=data.branch,
            is_active=True,
        )
        db.add(source)

    # Add code-source role to node
    role_result = await db.execute(
        select(NodeRole).where(
            NodeRole.node_id == data.node_id,
            NodeRole.role_name == "code-source",
        )
    )
    node_role = role_result.scalar_one_or_none()

    if not node_role:
        node_role = NodeRole(
            node_id=data.node_id,
            role_name="code-source",
            assignment_type="manual",
            status=RoleStatus.ACTIVE.value,
        )
        db.add(node_role)

    await db.commit()
    await db.refresh(source)

    logger.info("Assigned code-source to node: %s", data.node_id)

    return CodeSourceResponse(
        node_id=source.node_id,
        hostname=node.hostname,
        ip_address=node.ip_address,
        repo_path=source.repo_path,
        branch=source.branch,
        last_known_commit=source.last_known_commit,
        last_notified_at=source.last_notified_at,
        is_active=source.is_active,
    )


@router.delete("/assign")
async def remove_code_source(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Remove the active code-source assignment."""
    result = await db.execute(select(CodeSource).where(CodeSource.is_active.is_(True)))
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active code-source",
        )

    source.is_active = False
    await db.commit()

    logger.info("Removed code-source from node: %s", source.node_id)
    return {"success": True, "message": "Code-source removed"}


@router.post("/notify", response_model=CodeNotificationResponse)
async def notify_new_commit(
    notification: CodeNotification,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CodeNotificationResponse:
    """
    Receive notification of new commit from code-source.

    Called by git post-commit hook. No authentication - uses node_id.
    """
    # Verify this is from an active code-source
    source_result = await db.execute(
        select(CodeSource).where(
            CodeSource.node_id == notification.node_id,
            CodeSource.is_active.is_(True),
        )
    )
    source = source_result.scalar_one_or_none()

    if not source:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Node is not an active code-source",
        )

    # Update source with new commit
    source.last_known_commit = notification.commit
    source.last_notified_at = datetime.utcnow()

    # Update node's code_version
    node_result = await db.execute(
        select(Node).where(Node.node_id == notification.node_id)
    )
    node = node_result.scalar_one_or_none()
    if node:
        node.code_version = notification.commit

    await db.commit()

    logger.info(
        "Code notification received: commit=%s from node=%s",
        notification.commit[:12],
        notification.node_id,
    )

    # Broadcast via WebSocket
    try:
        from api.websocket import ws_manager

        await ws_manager.broadcast(
            {
                "type": "code_source.new_commit",
                "data": {
                    "commit": notification.commit,
                    "branch": notification.branch,
                    "message": notification.message,
                    "node_id": notification.node_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }
        )
    except Exception as e:
        logger.debug("Failed to broadcast commit notification: %s", e)

    return CodeNotificationResponse(
        success=True,
        message=f"Commit {notification.commit[:12]} recorded",
        commit=notification.commit,
        outdated_nodes=0,
    )
