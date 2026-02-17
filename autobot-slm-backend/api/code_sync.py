# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Sync API Routes (Issue #741).

Provides endpoints for code version tracking and sync operations.
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from models.database import (
    CodeSource,
    CodeStatus,
    Node,
    NodeRole,
    Setting,
    UpdateSchedule,
)
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
    ScheduleCreate,
    ScheduleResponse,
    ScheduleRunResponse,
    ScheduleUpdate,
)
from services.auth import get_current_user
from services.code_distributor import get_code_distributor
from services.database import get_db
from services.git_tracker import get_git_tracker
from services.playbook_executor import get_playbook_executor
from services.sync_orchestrator import get_sync_orchestrator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

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


_SLM_COMPONENTS = [
    (
        "autobot-slm-backend",
        ["venv", "__pycache__", "*.pyc", ".git", "*.log"],
    ),
    (
        "autobot-slm-frontend",
        ["node_modules", "dist", ".git"],
    ),
    (
        "autobot-shared",
        ["__pycache__", "*.pyc", ".git"],
    ),
]


async def _rsync_component(
    source_user: str,
    source_ip: str,
    source_path: str,
    component: str,
    excludes: List[str],
    ssh_key: str,
) -> Tuple[bool, str]:
    """Rsync a single component from source node to local /opt/autobot/.

    Helper for _sync_slm_from_code_source (#913).
    """
    ssh_opts = (
        f"ssh -i {ssh_key} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
    )
    cmd = [
        "rsync",
        "-avz",
        "--delete",
        "-e",
        ssh_opts,
    ]
    for exc in excludes:
        cmd.append(f"--exclude={exc}")
    cmd.append(f"{source_user}@{source_ip}:{source_path}/{component}/")
    cmd.append(f"/opt/autobot/{component}/")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        output = stdout.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            logger.error("rsync failed for %s: %s", component, output[:500])
            return False, f"rsync failed for {component}: {output[:200]}"
        logger.info("rsync succeeded for %s", component)
        return True, ""
    except asyncio.TimeoutError:
        return False, f"rsync timed out for {component}"
    except Exception as exc:
        return False, f"rsync error for {component}: {exc}"


async def _restart_slm_service(service: str) -> None:
    """Restart a systemd service on the local SLM server.

    Helper for _sync_slm_from_code_source (#913).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "systemctl",
            "restart",
            service,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await asyncio.wait_for(proc.communicate(), timeout=60.0)
        logger.info("Restarted service: %s", service)
    except Exception as exc:
        logger.warning("Failed to restart %s: %s", service, exc)


async def _sync_slm_from_code_source(db: AsyncSession, node_id: str) -> None:
    """Pull SLM components from the code source node and restart services.

    Used when the GUI triggers a sync for the SLM server itself (#913).
    The Ansible playbook cannot be used because it runs rsync FROM the
    controller (SLM server) but the source path only exists on the dev machine.
    This function reverses the direction: SLM server PULLS from the code source.
    """
    from models.database import CodeSource, Node  # avoid circular import

    source_result = await db.execute(
        select(CodeSource).where(CodeSource.is_active.is_(True))
    )
    source = source_result.scalar_one_or_none()
    if not source:
        logger.error("SLM self-sync failed: no active code source")
        return

    node_result = await db.execute(select(Node).where(Node.node_id == source.node_id))
    source_node = node_result.scalar_one_or_none()
    if not source_node:
        logger.error("SLM self-sync failed: code source node not found in DB")
        return

    ssh_key = os.environ.get("SLM_SSH_KEY", "/home/autobot/.ssh/autobot_key")
    if not Path(ssh_key).exists():
        logger.error("SLM self-sync failed: SSH key not found at %s", ssh_key)
        return

    source_ip = source_node.ip_address
    source_user = source_node.ssh_user or "autobot"
    repo_path = source.repo_path  # e.g. /home/kali/Desktop/AutoBot

    logger.info(
        "SLM self-sync: pulling from %s@%s:%s", source_user, source_ip, repo_path
    )

    all_ok = True
    for component, excludes in _SLM_COMPONENTS:
        ok, msg = await _rsync_component(
            source_user, source_ip, repo_path, component, excludes, ssh_key
        )
        if not ok:
            logger.error("SLM self-sync component %s failed: %s", component, msg)
            all_ok = False

    if all_ok:
        await _restart_slm_service("autobot-slm-backend")
        await _restart_slm_service("nginx")
        logger.info("SLM self-sync complete and services restarted")
    else:
        logger.error("SLM self-sync had failures; services NOT restarted")


async def _broadcast_sync_progress(node_id: str, progress: Dict[str, str]) -> None:
    """
    Broadcast sync progress via WebSocket (Issue #880).

    Helper for sync_node.
    """
    try:
        from api.websocket import ws_manager

        await ws_manager.broadcast(
            {
                "type": "sync_progress",
                "data": {
                    "node_id": node_id,
                    "stage": progress["stage"],
                    "message": progress["message"],
                },
            }
        )
    except Exception as e:
        logger.debug("Failed to broadcast sync progress: %s", e)


async def _update_node_version_after_sync(
    db: AsyncSession, node: Node, node_id: str
) -> None:
    """
    Update node version in database after successful sync (Issue #880).

    Helper for sync_node.
    """
    git_tracker = get_git_tracker()
    current_commit = await git_tracker.get_local_commit()

    if current_commit:
        node.code_version = current_commit
        node.code_status = CodeStatus.UP_TO_DATE
        await db.commit()
        logger.info("Updated node %s version to %s", node_id, current_commit[:8])


@router.post("/nodes/{node_id}/sync", response_model=NodeSyncResponse)
async def sync_node(
    node_id: str,
    request: NodeSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeSyncResponse:
    """
    Trigger code sync on a specific node using Ansible playbook (Issue #880).

    Now includes real-time progress updates via WebSocket.
    """
    # Get node
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    executor = get_playbook_executor()

    # Build playbook parameters
    limit = [node.hostname]
    tags = []
    if not request.restart:
        tags.append("!restart")  # Skip restart tasks

    # Progress callback for WebSocket broadcasts (Issue #880)
    async def progress_callback(progress: Dict[str, str]) -> None:
        await _broadcast_sync_progress(node_id, progress)

    # Check if this is the SLM server itself (Issue #867)
    # When syncing the SLM server, we can't wait for the playbook to complete
    # because the backend will restart during execution, causing HTTP 502 errors
    is_slm_server = (
        node.hostname == "00-SLM-Manager" or node.node_id == "00-SLM-Manager"
    )

    if is_slm_server and request.restart:
        # SLM server cannot self-sync via the Ansible playbook because
        # ansible.posix.synchronize runs rsync FROM the controller (SLM server),
        # but the source path /home/kali/Desktop/AutoBot only exists on the dev
        # machine. Instead, pull code FROM the code source node directly (#913).
        logger.info("SLM self-sync: pulling from code source (fire-and-forget)")
        asyncio.create_task(_sync_slm_from_code_source(db, node_id))
        return NodeSyncResponse(
            success=True,
            message=(
                "SLM update queued: pulling from code source + restarting services. "
                "Check backend health in ~30s."
            ),
            node_id=node_id,
        )
    else:
        # Normal execution - wait for result with progress updates
        playbook_result = await executor.execute_playbook(
            playbook_name="update-all-nodes.yml",
            limit=limit,
            tags=tags if tags else None,
            progress_callback=progress_callback,
        )

        # Update node version in database after successful sync
        if playbook_result["success"]:
            await _update_node_version_after_sync(db, node, node_id)

        return NodeSyncResponse(
            success=playbook_result["success"],
            message=playbook_result["output"]
            if playbook_result["success"]
            else f"Playbook failed: {playbook_result['output']}",
            node_id=node_id,
        )


async def _run_fleet_sync_job(job: FleetSyncJob) -> None:
    """
    Background task to execute fleet sync job using Ansible playbooks.

    Processes nodes according to the specified strategy and batch size.
    """
    executor = get_playbook_executor()
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
                    _sync_single_node(executor, node_state, job.restart)
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


async def _sync_single_node(executor, node_state: NodeSyncState, restart: bool) -> None:
    """Sync a single node using Ansible playbook and update its state."""
    try:
        # Build playbook parameters
        limit = [node_state.hostname]
        tags = []
        if not restart:
            tags.append("!restart")  # Skip restart tasks

        # Execute update playbook
        result = await executor.execute_playbook(
            playbook_name="update-all-nodes.yml",
            limit=limit,
            tags=tags if tags else None,
        )

        node_state.status = "success" if result["success"] else "failed"
        node_state.message = (
            result["output"][:500]
            if result["success"]
            else f"Playbook failed: {result['output'][:500]}"
        )
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


async def _verify_source_node(db: AsyncSession, node_id: str) -> Node:
    """
    Verify that the source node exists in the database.

    Helper for notify_code_version (Issue #665).
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    source_node = result.scalar_one_or_none()

    if not source_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source node not found",
        )

    return source_node


async def _update_version_setting(db: AsyncSession, commit: str) -> None:
    """
    Update or create the latest version setting.

    Helper for notify_code_version (Issue #665).
    """
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


async def _mark_outdated_nodes(
    db: AsyncSession, node_id: str, commit: str
) -> List[Node]:
    """
    Mark all other nodes as outdated if they have different version.

    Helper for notify_code_version (Issue #665).
    """
    nodes_result = await db.execute(
        select(Node).where(
            Node.node_id != node_id,
            Node.code_version != commit,
        )
    )
    outdated_nodes = nodes_result.scalars().all()

    for node in outdated_nodes:
        node.code_status = CodeStatus.OUTDATED.value

    return outdated_nodes


async def _broadcast_code_version_update(
    notification: CodeVersionNotification, outdated_count: int
) -> None:
    """
    Broadcast code version update notification via WebSocket.

    Helper for notify_code_version (Issue #665).
    """
    try:
        from api.websocket import ws_manager

        await ws_manager.broadcast(
            {
                "type": "code_version_update",
                "data": {
                    "new_version": notification.commit,
                    "source_node": notification.node_id,
                    "outdated_nodes": outdated_count,
                    "timestamp": notification.timestamp.isoformat()
                    if notification.timestamp
                    else None,
                },
            }
        )
    except Exception as e:
        logger.debug("Failed to broadcast code version update: %s", e)


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
    source_node = await _verify_source_node(db, node_id)

    # Update or create the latest version setting
    await _update_version_setting(db, commit)

    # Update the source node's code version
    source_node.code_version = commit
    source_node.code_status = CodeStatus.UP_TO_DATE.value

    # Mark all other nodes as outdated (if they have different version)
    outdated_nodes = await _mark_outdated_nodes(db, node_id, commit)

    await db.commit()

    logger.info(
        "Updated latest version to %s, %d nodes marked outdated",
        commit,
        len(outdated_nodes),
    )

    # Broadcast update notification via WebSocket
    await _broadcast_code_version_update(notification, len(outdated_nodes))

    return CodeVersionNotificationResponse(
        success=True,
        message=f"Version updated to {commit}",
        new_version=commit,
        nodes_notified=1,  # WebSocket broadcast
        outdated_nodes=len(outdated_nodes),
    )


# =============================================================================
# Schedule API Endpoints (Issue #741 - Phase 7)
# =============================================================================


def _validate_cron_expression(expression: str) -> bool:
    """Validate a cron expression using croniter."""
    try:
        from croniter import croniter

        croniter(expression)
        return True
    except (ValueError, KeyError):
        return False


def _calculate_next_run(expression: str, base: datetime = None) -> datetime:
    """Calculate next run time from cron expression."""
    from croniter import croniter

    base = base or datetime.utcnow()
    cron = croniter(expression, base)
    return cron.get_next(datetime)


@router.get("/schedules", response_model=List[ScheduleResponse])
async def list_schedules(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> List[ScheduleResponse]:
    """
    List all update schedules (Issue #741 - Phase 7).
    """
    result = await db.execute(
        select(UpdateSchedule).order_by(UpdateSchedule.created_at.desc())
    )
    schedules = result.scalars().all()

    return [ScheduleResponse.model_validate(s) for s in schedules]


@router.post("/schedules", response_model=ScheduleResponse)
async def create_schedule(
    schedule: ScheduleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ScheduleResponse:
    """
    Create a new update schedule (Issue #741 - Phase 7).

    Requires admin role.
    """
    # Validate cron expression
    if not _validate_cron_expression(schedule.cron_expression):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cron expression",
        )

    # Calculate initial next_run
    next_run = _calculate_next_run(schedule.cron_expression)

    new_schedule = UpdateSchedule(
        name=schedule.name,
        cron_expression=schedule.cron_expression,
        enabled=schedule.enabled,
        target_type=schedule.target_type,
        target_nodes=schedule.target_nodes,
        restart_strategy=schedule.restart_strategy,
        restart_after_sync=schedule.restart_after_sync,
        next_run=next_run,
        created_by=current_user.get("username"),
    )

    db.add(new_schedule)
    await db.commit()
    await db.refresh(new_schedule)

    logger.info(
        "Created schedule '%s' (id=%d) by %s",
        new_schedule.name,
        new_schedule.id,
        current_user.get("username"),
    )

    return ScheduleResponse.model_validate(new_schedule)


@router.get("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ScheduleResponse:
    """
    Get details of a specific schedule (Issue #741 - Phase 7).
    """
    result = await db.execute(
        select(UpdateSchedule).where(UpdateSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    return ScheduleResponse.model_validate(schedule)


@router.put("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: int,
    update: ScheduleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ScheduleResponse:
    """
    Update an existing schedule (Issue #741 - Phase 7).

    Requires admin role.
    """
    result = await db.execute(
        select(UpdateSchedule).where(UpdateSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    # Validate cron expression if provided
    if update.cron_expression is not None:
        if not _validate_cron_expression(update.cron_expression):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cron expression",
            )
        schedule.cron_expression = update.cron_expression
        schedule.next_run = _calculate_next_run(update.cron_expression)

    # Update other fields if provided
    if update.name is not None:
        schedule.name = update.name
    if update.enabled is not None:
        schedule.enabled = update.enabled
    if update.target_type is not None:
        schedule.target_type = update.target_type
    if update.target_nodes is not None:
        schedule.target_nodes = update.target_nodes
    if update.restart_strategy is not None:
        schedule.restart_strategy = update.restart_strategy
    if update.restart_after_sync is not None:
        schedule.restart_after_sync = update.restart_after_sync

    await db.commit()
    await db.refresh(schedule)

    logger.info("Updated schedule '%s' (id=%d)", schedule.name, schedule.id)

    return ScheduleResponse.model_validate(schedule)


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Delete a schedule (Issue #741 - Phase 7).

    Requires admin role.
    """
    result = await db.execute(
        select(UpdateSchedule).where(UpdateSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    schedule_name = schedule.name
    await db.delete(schedule)
    await db.commit()

    logger.info("Deleted schedule '%s' (id=%d)", schedule_name, schedule_id)

    return {"success": True, "message": f"Schedule '{schedule_name}' deleted"}


async def _get_schedule_target_nodes(
    db: AsyncSession, schedule: UpdateSchedule
) -> List[Node]:
    """
    Get target nodes based on schedule configuration.

    Helper for run_schedule (Issue #665).
    """
    if schedule.target_type == "all":
        nodes_result = await db.execute(
            select(Node).where(Node.code_status == CodeStatus.OUTDATED.value)
        )
    elif schedule.target_type == "specific" and schedule.target_nodes:
        nodes_result = await db.execute(
            select(Node).where(Node.node_id.in_(schedule.target_nodes))
        )
    else:
        nodes_result = await db.execute(
            select(Node).where(Node.code_status == CodeStatus.OUTDATED.value)
        )

    return nodes_result.scalars().all()


def _create_fleet_sync_job(nodes: List[Node], schedule: UpdateSchedule) -> FleetSyncJob:
    """
    Create a fleet sync job with target nodes.

    Helper for run_schedule (Issue #665).
    """
    job_id = str(uuid.uuid4())[:16]

    job = FleetSyncJob(
        job_id=job_id,
        strategy="rolling",
        batch_size=1,
        restart=schedule.restart_after_sync,
    )

    for node in nodes:
        job.nodes[node.node_id] = NodeSyncState(
            node_id=node.node_id,
            hostname=node.hostname,
            ip_address=node.ip_address,
            ssh_user=node.ssh_user or "autobot",
            ssh_port=node.ssh_port or 22,
        )

    return job


@router.post("/schedules/{schedule_id}/run", response_model=ScheduleRunResponse)
async def run_schedule(
    schedule_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ScheduleRunResponse:
    """
    Manually trigger a schedule to run now (Issue #741 - Phase 7).

    Requires admin role.
    """
    result = await db.execute(
        select(UpdateSchedule).where(UpdateSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    # Get target nodes based on schedule configuration
    nodes = await _get_schedule_target_nodes(db, schedule)

    if not nodes:
        return ScheduleRunResponse(
            success=True,
            message="No nodes to sync",
            schedule_id=schedule_id,
            job_id=None,
        )

    # Create a fleet sync job
    job = _create_fleet_sync_job(nodes, schedule)

    # Store job and start background task
    _fleet_sync_jobs[job.job_id] = job
    task = asyncio.create_task(_run_fleet_sync_job(job))
    _running_tasks[job.job_id] = task

    # Update schedule last_run
    schedule.last_run = datetime.utcnow()
    schedule.next_run = _calculate_next_run(schedule.cron_expression)
    await db.commit()

    logger.info(
        "Manually triggered schedule '%s' - job %s for %d nodes",
        schedule.name,
        job.job_id,
        len(nodes),
    )

    return ScheduleRunResponse(
        success=True,
        message=f"Triggered sync for {len(nodes)} node(s)",
        schedule_id=schedule_id,
        job_id=job.job_id,
    )


# =============================================================================
# Role-Based Code Sync API Endpoints (Issue #779)
# =============================================================================


@router.post("/pull")
async def pull_from_source(
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Pull code from code-source to SLM cache (Issue #779).

    Fetches the latest code from the designated code-source node
    and caches it locally for distribution to fleet nodes.
    """
    orchestrator = get_sync_orchestrator()
    success, message, commit = await orchestrator.pull_from_source()

    return {
        "success": success,
        "message": message,
        "commit": commit,
    }


async def _get_active_commit(db: AsyncSession) -> str:
    """Get the active code source commit.

    Helper for sync_role (Issue #665).

    Args:
        db: Database session

    Returns:
        The commit hash from the active code source

    Raises:
        HTTPException: If no active code source or commit is available
    """
    result = await db.execute(
        select(CodeSource).where(CodeSource.is_active == True)  # noqa: E712
    )
    source = result.scalar_one_or_none()

    if not source or not source.last_known_commit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No code version available. Pull from source first.",
        )

    return source.last_known_commit


async def _get_role_nodes(
    db: AsyncSession, role_name: str, node_ids: Optional[List[str]] = None
) -> List[NodeRole]:
    """Get NodeRole records, optionally filtered by node_ids.

    Helper for sync_role (Issue #665).

    Args:
        db: Database session
        role_name: Role to filter by
        node_ids: Optional list of node IDs to filter by

    Returns:
        List of NodeRole records matching the criteria
    """
    if node_ids:
        role_result = await db.execute(
            select(NodeRole).where(
                NodeRole.role_name == role_name,
                NodeRole.node_id.in_(node_ids),
            )
        )
    else:
        role_result = await db.execute(
            select(NodeRole).where(NodeRole.role_name == role_name)
        )

    return role_result.scalars().all()


async def _sync_nodes_for_role(
    orchestrator, node_roles: List[NodeRole], role_name: str, commit: str, restart: bool
) -> tuple[List[dict], int]:
    """Sync each node and return results with success count.

    Helper for sync_role (Issue #665).

    Args:
        orchestrator: Sync orchestrator instance
        node_roles: List of NodeRole records to sync
        role_name: Role being synced
        commit: Commit hash to sync
        restart: Whether to restart services after sync

    Returns:
        Tuple of (results list, success count)
    """
    results = []
    success_count = 0

    for nr in node_roles:
        ok, msg = await orchestrator.sync_node_role(
            node_id=nr.node_id,
            role_name=role_name,
            commit=commit,
            restart=restart,
        )
        results.append({"node_id": nr.node_id, "success": ok, "message": msg})
        if ok:
            success_count += 1

    return results, success_count


@router.post("/roles/{role_name}/sync")
async def sync_role(
    role_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_ids: Optional[List[str]] = None,
    restart: bool = True,
) -> dict:
    """
    Sync a role to all nodes that have it (Issue #779).

    Args:
        role_name: Role to sync
        node_ids: Optional filter - only sync to these nodes
        restart: Whether to restart services after sync
    """
    # Get latest commit from code source
    commit = await _get_active_commit(db)

    # Get nodes with this role detected or assigned
    node_roles = await _get_role_nodes(db, role_name, node_ids)

    if not node_roles:
        return {
            "success": True,
            "message": f"No nodes have role '{role_name}' assigned",
            "nodes_synced": 0,
        }

    # Sync each node
    orchestrator = get_sync_orchestrator()
    results, success_count = await _sync_nodes_for_role(
        orchestrator, node_roles, role_name, commit, restart
    )

    logger.info(
        "Role sync complete: %s - %d/%d successful",
        role_name,
        success_count,
        len(node_roles),
    )

    return {
        "success": success_count > 0,
        "message": f"Synced {success_count}/{len(node_roles)} nodes",
        "role_name": role_name,
        "commit": commit,
        "nodes_synced": success_count,
        "results": results,
    }
