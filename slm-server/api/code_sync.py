# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Sync API Routes (Issue #741).

Provides endpoints for code version tracking and sync operations.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import CodeStatus, Node, Setting
from models.schemas import (
    CodeSyncRefreshResponse,
    CodeSyncStatusResponse,
    PendingNodeResponse,
    PendingNodesResponse,
)
from services.auth import get_current_user
from services.database import get_db
from services.git_tracker import get_git_tracker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/code-sync", tags=["code-sync"])


@router.get("/status", response_model=CodeSyncStatusResponse)
async def get_sync_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CodeSyncStatusResponse:
    """
    Get current code sync status.

    Returns the latest version, local version, and count of outdated nodes.
    """
    tracker = get_git_tracker()

    # Get latest version from settings
    result = await db.execute(
        select(Setting).where(Setting.key == "slm_agent_latest_commit")
    )
    latest_setting = result.scalar_one_or_none()
    latest_version = latest_setting.value if latest_setting else None

    # Get local version
    local_version = await tracker.get_local_commit()

    # Count total nodes and outdated nodes
    total_result = await db.execute(select(func.count(Node.id)))
    total_nodes = total_result.scalar() or 0

    outdated_result = await db.execute(
        select(func.count(Node.id)).where(Node.code_status == CodeStatus.OUTDATED.value)
    )
    outdated_nodes = outdated_result.scalar() or 0

    # Check if local repo has updates
    has_update = (
        local_version is not None
        and latest_version is not None
        and local_version != latest_version
    )

    return CodeSyncStatusResponse(
        latest_version=latest_version,
        local_version=local_version,
        last_fetch=tracker.last_fetch,
        has_update=has_update,
        outdated_nodes=outdated_nodes,
        total_nodes=total_nodes,
    )


@router.post("/refresh", response_model=CodeSyncRefreshResponse)
async def refresh_version(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CodeSyncRefreshResponse:
    """
    Manually trigger a git fetch and update the latest version.
    """
    tracker = get_git_tracker()

    try:
        result = await tracker.check_for_updates(fetch=True)

        if result["remote_commit"]:
            # Update the setting
            setting_result = await db.execute(
                select(Setting).where(Setting.key == "slm_agent_latest_commit")
            )
            setting = setting_result.scalar_one_or_none()

            if setting:
                setting.value = result["remote_commit"]
            else:
                setting = Setting(
                    key="slm_agent_latest_commit",
                    value=result["remote_commit"],
                )
                db.add(setting)

            await db.commit()

            return CodeSyncRefreshResponse(
                success=True,
                message="Version updated successfully",
                latest_version=result["remote_commit"],
                has_update=result["has_update"],
            )
        else:
            return CodeSyncRefreshResponse(
                success=False,
                message="Failed to fetch remote version",
                latest_version=None,
                has_update=False,
            )

    except Exception as e:
        logger.error("Failed to refresh version: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh version: {e}",
        )


@router.get("/pending", response_model=PendingNodesResponse)
async def get_pending_nodes(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> PendingNodesResponse:
    """
    Get list of all nodes that need code updates.
    """
    # Get latest version
    setting_result = await db.execute(
        select(Setting).where(Setting.key == "slm_agent_latest_commit")
    )
    latest_setting = setting_result.scalar_one_or_none()
    latest_version = latest_setting.value if latest_setting else None

    # Get outdated nodes
    result = await db.execute(
        select(Node)
        .where(Node.code_status == CodeStatus.OUTDATED.value)
        .order_by(Node.hostname)
    )
    nodes = result.scalars().all()

    pending_nodes = [
        PendingNodeResponse(
            node_id=node.node_id,
            hostname=node.hostname,
            ip_address=node.ip_address,
            current_version=node.code_version,
            code_status=node.code_status,
        )
        for node in nodes
    ]

    return PendingNodesResponse(
        nodes=pending_nodes,
        total=len(pending_nodes),
        latest_version=latest_version,
    )
