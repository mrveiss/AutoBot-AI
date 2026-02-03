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

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

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
    UpdateApplyRequest,
    UpdateApplyResponse,
    UpdateCheckResponse,
    UpdateInfoResponse,
    UpdateJobListResponse,
    UpdateJobResponse,
)
from services.auth import get_current_user
from services.database import get_db

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


async def _broadcast_job_update(job_id: str, status: str, progress: int, message: str = None) -> None:
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


async def _run_update_job(job_id: str, node_id: str, update_ids: List[str]) -> None:
    """Execute update job in background."""
    from services.database import db_service

    async with db_service.session() as db:
        # Get the job
        result = await db.execute(select(UpdateJob).where(UpdateJob.job_id == job_id))
        job = result.scalar_one_or_none()

        if not job:
            logger.error("Update job not found: %s", job_id)
            return

        # Get the node
        node_result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = node_result.scalar_one_or_none()

        if not node:
            job.status = UpdateJobStatus.FAILED.value
            job.error = "Node not found"
            job.completed_at = datetime.utcnow()
            await db.commit()
            return

        # Get updates to apply
        updates_result = await db.execute(
            select(UpdateInfo).where(UpdateInfo.update_id.in_(update_ids))
        )
        updates = updates_result.scalars().all()

        if not updates:
            job.status = UpdateJobStatus.FAILED.value
            job.error = "No valid updates found"
            job.completed_at = datetime.utcnow()
            await db.commit()
            return

        # Start the job
        job.status = UpdateJobStatus.RUNNING.value
        job.started_at = datetime.utcnow()
        job.total_steps = len(updates)
        await db.commit()

        await _broadcast_job_update(job_id, "running", 0, "Starting update process...")

        # Execute updates via SSH
        output_lines = []
        failed_updates = []
        completed = 0

        try:
            ssh_user = node.ssh_user or "autobot"
            ssh_port = node.ssh_port or 22

            for update in updates:
                step_msg = f"Installing {update.package_name} ({update.available_version})"
                job.current_step = step_msg
                await db.commit()

                progress = int((completed / len(updates)) * 100)
                await _broadcast_job_update(job_id, "running", progress, step_msg)

                # Run apt-get install via SSH
                success = await _install_package_via_ssh(
                    node.ip_address,
                    ssh_user,
                    ssh_port,
                    update.package_name,
                    output_lines,
                )

                if success:
                    update.is_applied = True
                    update.applied_at = datetime.utcnow()
                    completed += 1
                    job.completed_steps = completed
                else:
                    failed_updates.append(update.update_id)

                # Update job output
                job.output = "\n".join(output_lines[-100:])  # Keep last 100 lines
                await db.commit()

            # Job completed
            if failed_updates:
                job.status = UpdateJobStatus.FAILED.value
                job.error = f"Failed to install {len(failed_updates)} package(s)"
            else:
                job.status = UpdateJobStatus.COMPLETED.value

            job.progress = 100
            job.current_step = "Completed"
            job.completed_at = datetime.utcnow()
            await db.commit()

            await _broadcast_job_update(
                job_id,
                job.status,
                100,
                f"Completed: {completed}/{len(updates)} updates applied"
            )

            # Create completion event
            await _create_node_event(
                db,
                node_id,
                EventType.DEPLOYMENT_COMPLETED if not failed_updates else EventType.DEPLOYMENT_FAILED,
                EventSeverity.INFO if not failed_updates else EventSeverity.WARNING,
                f"Update job {job_id} completed: {completed}/{len(updates)} applied",
                {"job_id": job_id, "applied": completed, "failed": len(failed_updates)},
            )
            await db.commit()

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
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=30",
            "-o", "BatchMode=yes",
            "-p", str(ssh_port),
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
            logger.warning("Failed to install %s on %s: exit code %d",
                         package_name, ip_address, proc.returncode)
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
    task = asyncio.create_task(_run_update_job(job_id, request.node_id, request.update_ids))
    _running_jobs[job_id] = task

    logger.info("Update job created: %s for node %s (%d updates)",
               job_id, request.node_id, len(updates))

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
