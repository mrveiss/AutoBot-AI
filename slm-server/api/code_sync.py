# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Sync API Routes (Issue #741).

Provides endpoints for code version tracking and sync operations.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import CodeStatus, Node, Setting
from models.schemas import (
    CodeSyncRefreshResponse,
    CodeSyncStatusResponse,
    CodeVersionNotification,
    CodeVersionNotificationResponse,
    FleetSyncJobStatus,
    FleetSyncNodeStatus,
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


# Fleet sync job tracking (Issue #741 Phase 8)
@dataclass
class NodeSyncState:
    """State tracking for individual node sync."""

    node_id: str
    hostname: str
    ip_address: str
    ssh_user: str
    ssh_port: int
    status: str = "pending"  # pending, syncing, success, failed
    message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class FleetSyncJob:
    """Fleet sync job state (Issue #741 Phase 8)."""

    job_id: str
    strategy: str
    batch_size: int
    restart: bool
    nodes: Dict[str, NodeSyncState] = field(default_factory=dict)
    status: str = "pending"  # pending, running, completed, failed
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# Module-level job tracking
_fleet_sync_jobs: Dict[str, FleetSyncJob] = {}
_running_tasks: Dict[str, asyncio.Task] = {}


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


async def _run_fleet_sync_job(job: FleetSyncJob) -> None:
    """
    Background task to execute fleet sync job (Issue #741 Phase 8).

    Processes nodes according to the specified strategy and batch size.
    """
    distributor = get_code_distributor()
    job.status = "running"

    node_list = list(job.nodes.values())
    batch_size = job.batch_size

    try:
        # Process nodes in batches
        for i in range(0, len(node_list), batch_size):
            batch = node_list[i : i + batch_size]

            # Start sync for all nodes in batch concurrently
            tasks = []
            for node_state in batch:
                node_state.status = "syncing"
                node_state.started_at = datetime.utcnow()

                task = asyncio.create_task(
                    _sync_single_node(distributor, node_state, job.restart)
                )
                tasks.append(task)

            # Wait for batch to complete
            await asyncio.gather(*tasks, return_exceptions=True)

            # If rolling strategy, wait between batches
            if job.strategy == "rolling" and i + batch_size < len(node_list):
                await asyncio.sleep(5)  # Brief pause between batches

        # Calculate final status
        failed_count = sum(1 for n in job.nodes.values() if n.status == "failed")
        if failed_count == len(job.nodes):
            job.status = "failed"
        elif failed_count > 0:
            job.status = "completed"  # Partial success
        else:
            job.status = "completed"

    except Exception as e:
        logger.error("Fleet sync job %s failed: %s", job.job_id, e)
        job.status = "failed"

    job.completed_at = datetime.utcnow()
    logger.info(
        "Fleet sync job %s completed: %d/%d successful",
        job.job_id,
        sum(1 for n in job.nodes.values() if n.status == "success"),
        len(job.nodes),
    )


async def _sync_single_node(
    distributor, node_state: NodeSyncState, restart: bool
) -> None:
    """Sync a single node and update its state."""
    try:
        success, message = await distributor.trigger_node_sync(
            node_id=node_state.node_id,
            ip_address=node_state.ip_address,
            ssh_user=node_state.ssh_user,
            ssh_port=node_state.ssh_port,
            restart=restart,
            strategy="graceful",
        )

        node_state.status = "success" if success else "failed"
        node_state.message = message
        node_state.completed_at = datetime.utcnow()

    except Exception as e:
        node_state.status = "failed"
        node_state.message = str(e)
        node_state.completed_at = datetime.utcnow()
        logger.error("Node sync failed for %s: %s", node_state.node_id, e)


@router.post("/fleet/sync", response_model=FleetSyncResponse)
async def sync_fleet(
    request: FleetSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetSyncResponse:
    """
    Trigger code sync across multiple nodes (Issue #741 Phase 8).

    If node_ids is None, syncs all outdated nodes.
    Supports rolling, immediate, graceful, and manual strategies.
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

    # Create job with node states
    job = FleetSyncJob(
        job_id=job_id,
        strategy=request.strategy,
        batch_size=request.batch_size,
        restart=request.restart,
    )

    for node in nodes:
        job.nodes[node.node_id] = NodeSyncState(
            node_id=node.node_id,
            hostname=node.hostname,
            ip_address=node.ip_address,
            ssh_user=node.ssh_user or "autobot",
            ssh_port=node.ssh_port or 22,
        )

    # Store job and start background task
    _fleet_sync_jobs[job_id] = job

    if request.strategy != "manual":
        task = asyncio.create_task(_run_fleet_sync_job(job))
        _running_tasks[job_id] = task

    logger.info("Fleet sync job %s queued for %d nodes", job_id, len(nodes))

    return FleetSyncResponse(
        success=True,
        message=f"Sync queued for {len(nodes)} node(s)",
        job_id=job_id,
        nodes_queued=len(nodes),
    )


@router.get("/fleet/jobs/{job_id}", response_model=FleetSyncJobStatus)
async def get_fleet_sync_job_status(
    job_id: str,
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetSyncJobStatus:
    """
    Get status of a fleet sync job (Issue #741 Phase 8).

    Returns detailed status including per-node sync progress.
    """
    job = _fleet_sync_jobs.get(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Build node status list
    node_statuses = [
        FleetSyncNodeStatus(
            node_id=ns.node_id,
            hostname=ns.hostname,
            status=ns.status,
            message=ns.message,
            started_at=ns.started_at,
            completed_at=ns.completed_at,
        )
        for ns in job.nodes.values()
    ]

    # Calculate counts
    completed_count = sum(1 for n in job.nodes.values() if n.status == "success")
    failed_count = sum(1 for n in job.nodes.values() if n.status == "failed")

    return FleetSyncJobStatus(
        job_id=job.job_id,
        status=job.status,
        strategy=job.strategy,
        total_nodes=len(job.nodes),
        completed_nodes=completed_count,
        failed_nodes=failed_count,
        nodes=node_statuses,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/fleet/jobs", response_model=List[FleetSyncJobStatus])
async def list_fleet_sync_jobs(
    _: Annotated[dict, Depends(get_current_user)],
    limit: int = 10,
) -> List[FleetSyncJobStatus]:
    """
    List recent fleet sync jobs (Issue #741 Phase 8).
    """
    jobs = sorted(
        _fleet_sync_jobs.values(),
        key=lambda j: j.created_at,
        reverse=True,
    )[:limit]

    result = []
    for job in jobs:
        node_statuses = [
            FleetSyncNodeStatus(
                node_id=ns.node_id,
                hostname=ns.hostname,
                status=ns.status,
                message=ns.message,
                started_at=ns.started_at,
                completed_at=ns.completed_at,
            )
            for ns in job.nodes.values()
        ]

        completed_count = sum(1 for n in job.nodes.values() if n.status == "success")
        failed_count = sum(1 for n in job.nodes.values() if n.status == "failed")

        result.append(
            FleetSyncJobStatus(
                job_id=job.job_id,
                status=job.status,
                strategy=job.strategy,
                total_nodes=len(job.nodes),
                completed_nodes=completed_count,
                failed_nodes=failed_count,
                nodes=node_statuses,
                created_at=job.created_at,
                completed_at=job.completed_at,
            )
        )

    return result


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


@router.post("/notify", response_model=CodeVersionNotificationResponse)
async def notify_code_version(
    notification: CodeVersionNotification,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CodeVersionNotificationResponse:
    """
    Receive code version notification from code-source agent (Issue #741).

    This endpoint is called by the SLM agent on the code-source node
    when a new commit is made. It updates the latest version setting
    and marks all other nodes as outdated.

    No authentication required - agent uses node_id for identification.
    """
    commit = notification.commit
    node_id = notification.node_id

    logger.info(
        "Code version notification from %s: %s",
        node_id,
        commit,
    )

    # Verify this is from a known code-source node
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    source_node = result.scalar_one_or_none()

    if not source_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source node not found",
        )

    # Update or create the latest version setting
    setting_result = await db.execute(
        select(Setting).where(Setting.key == "slm_agent_latest_commit")
    )
    setting = setting_result.scalar_one_or_none()

    if setting:
        setting.value = commit
    else:
        setting = Setting(
            key="slm_agent_latest_commit",
            value=commit,
        )
        db.add(setting)

    # Update the source node's code version
    source_node.code_version = commit
    source_node.code_status = CodeStatus.UP_TO_DATE.value

    # Mark all other nodes as outdated (if they have different version)
    nodes_result = await db.execute(
        select(Node).where(
            Node.node_id != node_id,
            Node.code_version != commit,
        )
    )
    outdated_nodes = nodes_result.scalars().all()

    for node in outdated_nodes:
        node.code_status = CodeStatus.OUTDATED.value

    await db.commit()

    logger.info(
        "Updated latest version to %s, %d nodes marked outdated",
        commit,
        len(outdated_nodes),
    )

    # Broadcast update notification via WebSocket
    try:
        from api.websocket import ws_manager

        await ws_manager.broadcast(
            {
                "type": "code_version_update",
                "data": {
                    "new_version": commit,
                    "source_node": node_id,
                    "outdated_nodes": len(outdated_nodes),
                    "timestamp": notification.timestamp.isoformat()
                    if notification.timestamp
                    else None,
                },
            }
        )
    except Exception as e:
        logger.debug("Failed to broadcast code version update: %s", e)

    return CodeVersionNotificationResponse(
        success=True,
        message=f"Version updated to {commit}",
        new_version=commit,
        nodes_notified=1,  # WebSocket broadcast
        outdated_nodes=len(outdated_nodes),
    )
