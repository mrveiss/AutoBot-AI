# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Sync API Routes (Issue #741).

Provides endpoints for code version tracking and sync operations.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import CodeStatus, Node, Setting
from models.schemas import (
    CodeSyncRefreshResponse,
    CodeSyncStatusResponse,
    FleetSyncRequest,
    FleetSyncResponse,
    NodeSyncRequest,
    NodeSyncResponse,
    PendingNodeResponse,
    PendingNodesResponse,
)
from services.auth import get_current_user
from services.code_distributor import get_code_distributor
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


@router.post("/nodes/{node_id}/sync", response_model=NodeSyncResponse)
async def sync_node(
    node_id: str,
    request: NodeSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeSyncResponse:
    """
    Trigger code sync on a specific node.
    """
    # Get node
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    distributor = get_code_distributor()

    success, message = await distributor.trigger_node_sync(
        node_id=node.node_id,
        ip_address=node.ip_address,
        ssh_user=node.ssh_user or "autobot",
        ssh_port=node.ssh_port or 22,
        restart=request.restart,
        strategy=request.strategy,
    )

    return NodeSyncResponse(
        success=success,
        message=message,
        node_id=node_id,
    )


@router.post("/fleet/sync", response_model=FleetSyncResponse)
async def sync_fleet(
    request: FleetSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetSyncResponse:
    """
    Trigger code sync across multiple nodes.

    If node_ids is None, syncs all outdated nodes.
    """
    # Get target nodes
    if request.node_ids:
        result = await db.execute(
            select(Node).where(Node.node_id.in_(request.node_ids))
        )
    else:
        result = await db.execute(
            select(Node).where(Node.code_status == CodeStatus.OUTDATED.value)
        )

    nodes = result.scalars().all()

    if not nodes:
        return FleetSyncResponse(
            success=True,
            message="No nodes to sync",
            job_id="",
            nodes_queued=0,
        )

    # Create a job ID for tracking
    job_id = str(uuid.uuid4())[:16]

    # TODO(Issue #741 Phase 8): Implement actual background job queue
    # For now, this is a stub that acknowledges the request
    # Queue the sync operations (in a real implementation, this would be async)
    logger.info("Fleet sync job %s queued for %d nodes", job_id, len(nodes))

    return FleetSyncResponse(
        success=True,
        message=f"Sync queued for {len(nodes)} node(s)",
        job_id=job_id,
        nodes_queued=len(nodes),
    )


@router.get("/nodes/{node_id}/package")
async def get_code_package(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """
    Get the code package for a node to download.

    Returns a tarball of the agent code with the latest version.
    """
    distributor = get_code_distributor()

    # Build or get cached package
    package_path = await distributor.build_package()

    if not package_path or not package_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build code package",
        )

    return FileResponse(
        path=package_path,
        media_type="application/gzip",
        filename=package_path.name,
    )
