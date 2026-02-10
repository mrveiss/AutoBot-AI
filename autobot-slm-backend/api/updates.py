# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Updates API Routes

Provides update management with job tracking and status polling.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from models.database import (
    EventSeverity,
    EventType,
    Node,
    NodeEvent,
    UpdateInfo,
    UpdateJob,
    UpdateJobStatus,
)
from models.schemas import (
    FleetUpdateSummaryResponse,
    NodeUpdateSummary,
    UpdateApplyRequest,
    UpdateApplyResponse,
    UpdateCheckResponse,
    UpdateInfoResponse,
    UpdateJobListResponse,
    UpdateJobResponse,
)
from services.auth import get_current_user
from services.database import get_db
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/updates", tags=["updates"])

# Track running update tasks
_running_jobs: Dict[str, asyncio.Task] = {}


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
    await db.flush()
    return event


async def _broadcast_job_update(
    job_id: str, status: str, progress: int, message: str = None
) -> None:
    """Broadcast job update via WebSocket."""
    try:
        from api.websocket import ws_manager

        await ws_manager.broadcast(
            "events:global",
            {
                "type": "update_job_progress",
                "data": {
                    "job_id": job_id,
                    "status": status,
                    "progress": progress,
                    "message": message,
                },
                "timestamp": asyncio.get_event_loop().time(),
            },
        )
    except Exception as e:
        logger.debug("Failed to broadcast job update: %s", e)


async def _get_update_job_data(
    db: AsyncSession, job_id: str, node_id: str, update_ids: List[str]
) -> Optional[tuple]:
    """
    Helper for _run_update_job (Issue #665).

    Fetch job, node, and updates from database. Returns tuple of (job, node, updates)
    or None if validation fails. Sets job to FAILED status if node or updates not found.
    """
    result = await db.execute(select(UpdateJob).where(UpdateJob.job_id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        logger.error("Update job not found: %s", job_id)
        return None

    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = node_result.scalar_one_or_none()

    if not node:
        job.status = UpdateJobStatus.FAILED.value
        job.error = "Node not found"
        job.completed_at = datetime.utcnow()
        await db.commit()
        return None

    updates_result = await db.execute(
        select(UpdateInfo).where(UpdateInfo.update_id.in_(update_ids))
    )
    updates = updates_result.scalars().all()

    if not updates:
        job.status = UpdateJobStatus.FAILED.value
        job.error = "No valid updates found"
        job.completed_at = datetime.utcnow()
        await db.commit()
        return None

    return (job, node, updates)


async def _process_single_update(
    db: AsyncSession,
    job: UpdateJob,
    node: Node,
    update: UpdateInfo,
    output_lines: List[str],
    completed: int,
    total: int,
) -> bool:
    """
    Helper for _run_update_job (Issue #665).

    Install one package via SSH, update progress, and broadcast status.
    Returns True if installation succeeded, False otherwise.
    """
    step_msg = f"Installing {update.package_name} ({update.available_version})"
    job.current_step = step_msg
    await db.commit()

    progress = int((completed / total) * 100)
    await _broadcast_job_update(job.job_id, "running", progress, step_msg)

    ssh_user = node.ssh_user or "autobot"
    ssh_port = node.ssh_port or 22

    success = await _install_package_via_ssh(
        node.ip_address, ssh_user, ssh_port, update.package_name, output_lines
    )

    if success:
        update.is_applied = True
        update.applied_at = datetime.utcnow()

    job.output = "\n".join(output_lines[-100:])
    await db.commit()
    return success


async def _finalize_update_job(
    db: AsyncSession,
    job: UpdateJob,
    node_id: str,
    completed: int,
    failed: int,
    total: int,
) -> None:
    """
    Helper for _run_update_job (Issue #665).

    Set final job status and create completion event.
    """
    if failed > 0:
        job.status = UpdateJobStatus.FAILED.value
        job.error = f"Failed to install {failed} package(s)"
    else:
        job.status = UpdateJobStatus.COMPLETED.value

    job.progress = 100
    job.current_step = "Completed"
    job.completed_at = datetime.utcnow()
    await db.commit()

    await _broadcast_job_update(
        job.job_id, job.status, 100, f"Completed: {completed}/{total} updates applied"
    )

    event_type = (
        EventType.DEPLOYMENT_COMPLETED if failed == 0 else EventType.DEPLOYMENT_FAILED
    )
    severity = EventSeverity.INFO if failed == 0 else EventSeverity.WARNING

    await _create_node_event(
        db,
        node_id,
        event_type,
        severity,
        f"Update job {job.job_id} completed: {completed}/{total} applied",
        {"job_id": job.job_id, "applied": completed, "failed": failed},
    )
    await db.commit()


async def _run_update_job(job_id: str, node_id: str, update_ids: List[str]) -> None:
    """Execute update job in background."""
    from services.database import db_service

    async with db_service.session() as db:
        job_data = await _get_update_job_data(db, job_id, node_id, update_ids)
        if not job_data:
            return

        job, node, updates = job_data

        job.status = UpdateJobStatus.RUNNING.value
        job.started_at = datetime.utcnow()
        job.total_steps = len(updates)
        await db.commit()

        await _broadcast_job_update(job_id, "running", 0, "Starting update process...")

        output_lines = []
        failed_updates = []
        completed = 0

        try:
            for update in updates:
                success = await _process_single_update(
                    db, job, node, update, output_lines, completed, len(updates)
                )
                if success:
                    completed += 1
                    job.completed_steps = completed
                else:
                    failed_updates.append(update.update_id)

            await _finalize_update_job(
                db, job, node_id, completed, len(failed_updates), len(updates)
            )

        except asyncio.CancelledError:
            job.status = UpdateJobStatus.CANCELLED.value
            job.completed_at = datetime.utcnow()
            await db.commit()
            logger.info("Update job cancelled: %s", job_id)
            raise

        except Exception as e:
            logger.error("Update job failed: %s - %s", job_id, e)
            job.status = UpdateJobStatus.FAILED.value
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            await _broadcast_job_update(job_id, "failed", job.progress, str(e))


async def _install_package_via_ssh(
    ip_address: str,
    ssh_user: str,
    ssh_port: int,
    package_name: str,
    output_lines: List[str],
) -> bool:
    """Install a package on remote node via SSH."""
    try:
        # Use apt-get with non-interactive mode
        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=30",
            "-o",
            "BatchMode=yes",
            "-p",
            str(ssh_port),
            f"{ssh_user}@{ip_address}",
            f"sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {package_name}",
        ]

        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        output = stdout.decode("utf-8", errors="replace")
        output_lines.extend(output.strip().split("\n"))

        if proc.returncode == 0:
            logger.info("Installed %s on %s", package_name, ip_address)
            return True
        else:
            logger.warning(
                "Failed to install %s on %s: exit code %d",
                package_name,
                ip_address,
                proc.returncode,
            )
            return False

    except asyncio.TimeoutError:
        logger.warning("Timeout installing %s on %s", package_name, ip_address)
        output_lines.append(f"ERROR: Timeout installing {package_name}")
        return False
    except Exception as e:
        logger.error("Error installing %s on %s: %s", package_name, ip_address, e)
        output_lines.append(f"ERROR: {e}")
        return False


@router.get("/check", response_model=UpdateCheckResponse)
async def check_updates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = Query(None),
) -> UpdateCheckResponse:
    """Check for available updates."""
    query = select(UpdateInfo).where(UpdateInfo.is_applied.is_(False))

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


def _build_node_summaries(
    nodes: list, updates_by_node: dict, global_count: int
) -> list:
    """Build per-node update summaries.

    Helper for get_fleet_update_summary (#682).
    """
    summaries = []
    for node in nodes:
        sys_count = len(updates_by_node.get(node.node_id, []))
        sys_count += global_count
        code_outdated = (node.code_status or "") == "outdated"
        total = sys_count + (1 if code_outdated else 0)
        summaries.append(
            NodeUpdateSummary(
                node_id=node.node_id,
                hostname=node.hostname,
                system_updates=sys_count,
                code_update_available=code_outdated,
                code_status=node.code_status or "unknown",
                total_updates=total,
            )
        )
    return summaries


@router.get(
    "/fleet-summary",
    response_model=FleetUpdateSummaryResponse,
)
async def get_fleet_update_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetUpdateSummaryResponse:
    """Get update summary for all fleet nodes (#682)."""
    nodes_result = await db.execute(select(Node))
    nodes = nodes_result.scalars().all()

    updates_result = await db.execute(
        select(UpdateInfo).where(UpdateInfo.is_applied.is_(False))
    )
    all_updates = updates_result.scalars().all()

    # Partition: node-specific vs global updates
    updates_by_node: dict = {}
    global_updates = []
    for upd in all_updates:
        if upd.node_id:
            updates_by_node.setdefault(upd.node_id, []).append(upd)
        else:
            global_updates.append(upd)

    summaries = _build_node_summaries(nodes, updates_by_node, len(global_updates))

    # Unique total: per-node specific + global (not per-node * global)
    total_sys = sum(len(v) for v in updates_by_node.values()) + len(global_updates)
    total_code = sum(1 for s in summaries if s.code_update_available)
    needing = sum(1 for s in summaries if s.total_updates > 0)

    return FleetUpdateSummaryResponse(
        nodes=summaries,
        total_system_updates=total_sys,
        total_code_updates=total_code,
        nodes_needing_updates=needing,
    )


@router.post("/apply", response_model=UpdateApplyResponse)
async def apply_updates(
    request: UpdateApplyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateApplyResponse:
    """
    Apply updates to a node.

    Creates an update job that runs in the background. Use the job_id
    to poll for status via GET /updates/jobs/{job_id}.
    """
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

    # Create update job
    job_id = str(uuid.uuid4())[:16]
    job = UpdateJob(
        job_id=job_id,
        node_id=request.node_id,
        status=UpdateJobStatus.PENDING.value,
        update_ids=request.update_ids,
        total_steps=len(updates),
    )
    db.add(job)

    await _create_node_event(
        db,
        request.node_id,
        EventType.DEPLOYMENT_STARTED,
        EventSeverity.INFO,
        f"Update job started: {len(updates)} package(s)",
        {"job_id": job_id, "update_ids": request.update_ids},
    )

    await db.commit()

    # Start background task
    task = asyncio.create_task(
        _run_update_job(job_id, request.node_id, request.update_ids)
    )
    _running_jobs[job_id] = task

    logger.info(
        "Update job created: %s for node %s (%d updates)",
        job_id,
        request.node_id,
        len(updates),
    )

    return UpdateApplyResponse(
        success=True,
        message=f"Update job started for {len(updates)} package(s)",
        job_id=job_id,
    )


@router.get("/jobs/{job_id}", response_model=UpdateJobResponse)
async def get_job_status(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateJobResponse:
    """
    Get status of an update job.

    Use this endpoint to poll for job progress and completion.
    """
    result = await db.execute(select(UpdateJob).where(UpdateJob.job_id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Update job not found",
        )

    return UpdateJobResponse.model_validate(job)


@router.get("/jobs", response_model=UpdateJobListResponse)
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
) -> UpdateJobListResponse:
    """List update jobs with optional filters."""
    query = select(UpdateJob)

    if node_id:
        query = query.where(UpdateJob.node_id == node_id)
    if status_filter:
        query = query.where(UpdateJob.status == status_filter)

    query = query.order_by(UpdateJob.created_at.desc()).limit(limit)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return UpdateJobListResponse(
        jobs=[UpdateJobResponse.model_validate(j) for j in jobs],
        total=len(jobs),
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """Cancel a running update job."""
    result = await db.execute(select(UpdateJob).where(UpdateJob.job_id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Update job not found",
        )

    if job.status not in [UpdateJobStatus.PENDING.value, UpdateJobStatus.RUNNING.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in status: {job.status}",
        )

    # Cancel the task if running
    if job_id in _running_jobs:
        _running_jobs[job_id].cancel()
        del _running_jobs[job_id]

    job.status = UpdateJobStatus.CANCELLED.value
    job.completed_at = datetime.utcnow()
    await db.commit()

    logger.info("Update job cancelled: %s", job_id)

    return {"success": True, "message": "Job cancelled"}
