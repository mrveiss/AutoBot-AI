# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Code Sync API Routes (Issue #741).

Provides endpoints for code version tracking and sync operations.
"""

import asyncio
import functools
import getpass
import hashlib
import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy import or_ as sa_or
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from autobot_shared.db_url import assemble_postgres_url
from config import settings
from models.database import CodeSource, CodeStatus
from models.database import ComponentSyncJob as ComponentSyncJobModel
from models.database import FleetSyncJob as FleetSyncJobModel
from models.database import FleetSyncNodeState as FleetSyncNodeStateModel
from models.database import Node, NodeRole, Setting, UpdateSchedule
from models.schemas import (
    CodeSyncRefreshResponse,
    CodeSyncStatusResponse,
    CodeVersionNotification,
    CodeVersionNotificationResponse,
    ComponentSyncJobStatus,
    DriftResolveJobResponse,
    DriftResolveRequest,
    DriftResolveResponse,
    FileDriftReport,
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
from services.deploy_artifacts import rsync_artifact_excludes
from services.drift_checker import (
    ALLOWED_COMPONENTS,
    build_drift_report,
    get_default_deployed_dir,
    get_default_source_dir,
)
from services.fleet_sync_guard import assert_no_running_sync, fleet_sync_lock
from services.git_tracker import DEFAULT_BRANCH, DEFAULT_REPO_PATH, get_git_tracker
from services.playbook_executor import get_playbook_executor
from services.ssh_utils import _ssh_key_usable
from services.sync_orchestrator import get_sync_orchestrator

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
    message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class FleetSyncJob:
    """Fleet sync job state (Issue #741 Phase 8)."""

    job_id: str
    strategy: str
    batch_size: int
    restart: bool
    nodes: Dict[str, NodeSyncState] = field(default_factory=dict)
    status: str = "pending"  # pending, running, completed, failed
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


# In-memory tracking for running asyncio tasks only (not job state)
_running_tasks: Dict[str, asyncio.Task] = {}

# fleet_sync_lock and assert_no_running_sync live in services/fleet_sync_guard.py
# so schedule_executor.py can also import them without a circular dependency (#1979).


async def reconcile_stale_fleet_sync_jobs() -> int:
    """Mark stale 'running' fleet sync jobs as failed on startup (#1729).

    Called during SLM backend lifespan init. Any job left in 'running'
    status from a prior process crash is marked 'failed' with a message
    explaining it was interrupted by a service restart.

    Returns:
        Number of stale jobs reconciled.
    """
    from services.database import db_service

    async with db_service.session() as db:
        result = await db.execute(select(FleetSyncJobModel).where(FleetSyncJobModel.status == "running"))
        stale_jobs = result.scalars().all()
        count = len(stale_jobs)

        for job in stale_jobs:
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            job.failure_reason = "reconciled: server restarted while job was running"
            logger.warning(
                "Reconciled stale fleet sync job %s " "(was 'running', marked 'failed')",
                job.job_id,
            )

        if count:
            await db.commit()

    return count


async def reconcile_stale_component_sync_jobs() -> Tuple[int, List[Tuple[str, str]]]:
    """Reconcile stale component sync jobs on startup (#11303, #11437).

    Jobs left 'running' (or 'queued' — a requeue whose re-run never started)
    by a prior process death are re-queued ONCE so their post-steps (incl. DB
    migrations) are not silently skipped; a job interrupted twice is failed
    permanently with success=False.

    Returns:
        (number of stale jobs reconciled, list of (job_id, component) requeued).
    """
    from services.database import db_service

    async with db_service.session() as db:
        result = await db.execute(
            select(ComponentSyncJobModel).where(ComponentSyncJobModel.status.in_(["running", "queued"]))
        )
        stale_jobs = result.scalars().all()
        count = len(stale_jobs)

        requeued: List[Tuple[str, str]] = []
        for job in stale_jobs:
            if job.message and job.message.startswith("requeued"):
                # Second interruption — do not loop forever (#11437).
                job.status = "failed"
                job.success = False
                job.completed_at = datetime.now(timezone.utc)
                job.message = "failed: interrupted twice by server restarts"
                logger.warning("Component sync job %s interrupted twice — marked failed", job.job_id)
            else:
                # #11437: the interruption was a restart racing the job, not a
                # job failure — re-queue it so post-steps (incl. migrations)
                # actually run instead of being silently skipped.
                job.status = "queued"
                job.message = "requeued after server restart"
                requeued.append((job.job_id, job.component))
                logger.warning(
                    "Reconciled stale component sync job %s (was 'running', re-queued)",
                    job.job_id,
                )

        if count:
            await db.commit()

    return count, requeued


async def _run_component_resolve_job(job_id: str, component: str) -> None:
    """Background executor for an async component drift/resolve job (#11303).

    Runs rsync + post-sync steps (pip/build/alembic) then commits the job row
    to DB BEFORE triggering the service restart.  This guarantees the status is
    durable even if the restart kills this process (the autobot-slm-backend
    self-resolve case).
    """
    from services.database import db_service

    try:
        # Requeued jobs arrive as 'queued' — mark running for status pollers (#11437).
        async with db_service.session() as db:
            result = await db.execute(select(ComponentSyncJobModel).where(ComponentSyncJobModel.job_id == job_id))
            job_row = result.scalar_one_or_none()
            if job_row and job_row.status != "running":
                job_row.status = "running"
                await db.commit()
        try:
            source_dir = get_default_source_dir(component)
        except ValueError as exc:
            async with db_service.session() as db:
                result = await db.execute(select(ComponentSyncJobModel).where(ComponentSyncJobModel.job_id == job_id))
                job_row = result.scalar_one_or_none()
                if job_row:
                    job_row.status = "failed"
                    job_row.success = False
                    job_row.message = f"Failed to determine source path: {exc}"
                    job_row.completed_at = datetime.now(timezone.utc)
                    await db.commit()
            logger.error("component resolve job %s: source path error: %s", job_id, exc)
            return

        deployed_dir = get_default_deployed_dir(component)
        source_root = str(Path(source_dir).parent)

        excludes_map = {comp: excl for comp, excl in _SLM_COMPONENTS}
        excludes = excludes_map.get(
            component,
            [],  # artifacts excluded universally at the rsync chokepoint (#11459)
        )

        logger.info(
            "component resolve job %s: rsync source=%s/%s deployed=%s",
            job_id,
            source_root,
            component,
            deployed_dir,
        )

        # #11611: autobot_shared-first — sync the shared library BEFORE this
        # component's own rsync + restart so a newly-added `from autobot_shared.X`
        # import resolves at startup and the control plane cannot crash-loop on a
        # half-deployed shared tree. Fail the job if it cannot be synced.
        shared_ok, shared_msg = await _ensure_autobot_shared_synced(component)
        if not shared_ok:
            async with db_service.session() as db:
                result = await db.execute(select(ComponentSyncJobModel).where(ComponentSyncJobModel.job_id == job_id))
                job_row = result.scalar_one_or_none()
                if job_row:
                    job_row.status = "failed"
                    job_row.success = False
                    job_row.message = shared_msg
                    job_row.completed_at = datetime.now(timezone.utc)
                    await db.commit()
            logger.error("component resolve job %s: %s", job_id, shared_msg)
            return

        ok, msg = await _rsync_component_local(source_root, component, excludes)

        if not ok:
            async with db_service.session() as db:
                result = await db.execute(select(ComponentSyncJobModel).where(ComponentSyncJobModel.job_id == job_id))
                job_row = result.scalar_one_or_none()
                if job_row:
                    job_row.status = "failed"
                    job_row.success = False
                    job_row.message = msg or "rsync failed"
                    job_row.completed_at = datetime.now(timezone.utc)
                    await db.commit()
            logger.error("component resolve job %s: rsync failed: %s", job_id, msg)
            return

        deps_changed, post_steps, pip_ok = await _run_post_sync_steps(
            component, source_dir, deployed_dir, restart=False
        )

        # Commit the job row BEFORE the restart — the whole point of this async
        # path.  If the restart kills this process the row is already durable.
        async with db_service.session() as db:
            result = await db.execute(select(ComponentSyncJobModel).where(ComponentSyncJobModel.job_id == job_id))
            job_row = result.scalar_one_or_none()
            if job_row:
                job_row.status = "completed" if pip_ok else "failed"
                job_row.success = pip_ok
                job_row.deps_changed = deps_changed
                job_row.post_steps = "\n".join(post_steps)
                if pip_ok:
                    job_row.message = f"Resynced {component} from code_source"
                else:
                    job_row.message = "pip install failed — see post_steps"
                job_row.completed_at = datetime.now(timezone.utc)
                await db.commit()

        if not pip_ok:
            logger.error("component resolve job %s: pip install failed", job_id)
            return

        logger.info(
            "component resolve job %s: completed; triggering deferred restart for %s",
            job_id,
            component,
        )
        # Deferred restart — may kill this process for autobot-slm-backend; that
        # is fine because the job row is already committed above.
        steps2: List[str] = []
        await _restart_component_services(component, steps2)

    except Exception as exc:
        logger.error("component resolve job %s: unexpected error: %s", job_id, exc, exc_info=True)
        try:
            from services.database import db_service as _db_svc

            async with _db_svc.session() as db:
                result = await db.execute(select(ComponentSyncJobModel).where(ComponentSyncJobModel.job_id == job_id))
                job_row = result.scalar_one_or_none()
                if job_row:
                    job_row.status = "failed"
                    job_row.message = str(exc)
                    job_row.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception as inner:
            logger.error("component resolve job %s: failed to persist error state: %s", job_id, inner)
    finally:
        _running_tasks.pop(job_id, None)


async def _persist_fleet_sync_job(
    job: FleetSyncJob,
) -> None:
    """Persist a fleet sync job and its node states to DB (#1707)."""
    from services.database import db_service

    async with db_service.session() as db:
        db_job = FleetSyncJobModel(
            job_id=job.job_id,
            strategy=job.strategy,
            batch_size=job.batch_size,
            restart=job.restart,
            status=job.status,
            total_nodes=len(job.nodes),
            completed_nodes=0,
            failed_nodes=0,
            created_at=job.created_at,
        )
        db.add(db_job)

        for ns in job.nodes.values():
            db.add(
                FleetSyncNodeStateModel(
                    job_id=job.job_id,
                    node_id=ns.node_id,
                    hostname=ns.hostname,
                    ip_address=ns.ip_address,
                    status=ns.status,
                )
            )

        await db.commit()


async def _update_job_status_db(
    job_id: str,
    *,
    status: str | None = None,
    completed_at: datetime | None = None,
    failure_reason: str | None = None,
) -> None:
    """Update fleet sync job status in DB (#1707, #1980)."""
    from services.database import db_service

    async with db_service.session() as db:
        result = await db.execute(select(FleetSyncJobModel).where(FleetSyncJobModel.job_id == job_id))
        db_job = result.scalar_one_or_none()
        if not db_job:
            return

        if status is not None:
            db_job.status = status
        if completed_at is not None:
            db_job.completed_at = completed_at
        if failure_reason is not None:
            db_job.failure_reason = failure_reason[:500]

        # Recalculate node counts from node_states
        ns_result = await db.execute(select(FleetSyncNodeStateModel).where(FleetSyncNodeStateModel.job_id == job_id))
        node_states = ns_result.scalars().all()
        db_job.completed_nodes = sum(1 for n in node_states if n.status == "success")
        db_job.failed_nodes = sum(1 for n in node_states if n.status == "failed")

        await db.commit()


async def _update_node_state_db(
    job_id: str,
    node_id: str,
    *,
    status: str | None = None,
    message: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    """Update a single node's sync state in DB (#1707)."""
    from services.database import db_service

    async with db_service.session() as db:
        result = await db.execute(
            select(FleetSyncNodeStateModel).where(
                FleetSyncNodeStateModel.job_id == job_id,
                FleetSyncNodeStateModel.node_id == node_id,
            )
        )
        ns = result.scalar_one_or_none()
        if not ns:
            return

        if status is not None:
            ns.status = status
        if message is not None:
            ns.message = message[:500] if message else None
        if started_at is not None:
            ns.started_at = started_at
        if completed_at is not None:
            ns.completed_at = completed_at

        await db.commit()


async def _load_job_status_from_db(
    job_id: str,
) -> FleetSyncJobStatus | None:
    """Load fleet sync job status from DB (#1707)."""
    from services.database import db_service

    async with db_service.session() as db:
        result = await db.execute(select(FleetSyncJobModel).where(FleetSyncJobModel.job_id == job_id))
        db_job = result.scalar_one_or_none()
        if not db_job:
            return None

        ns_result = await db.execute(select(FleetSyncNodeStateModel).where(FleetSyncNodeStateModel.job_id == job_id))
        node_states = ns_result.scalars().all()

        return FleetSyncJobStatus(
            job_id=db_job.job_id,
            status=db_job.status,
            strategy=db_job.strategy,
            total_nodes=db_job.total_nodes,
            completed_nodes=db_job.completed_nodes,
            failed_nodes=db_job.failed_nodes,
            failure_reason=db_job.failure_reason,
            nodes=[
                FleetSyncNodeStatus(
                    node_id=ns.node_id,
                    hostname=ns.hostname,
                    status=ns.status,
                    message=ns.message,
                    started_at=ns.started_at,
                    completed_at=ns.completed_at,
                )
                for ns in node_states
            ],
            created_at=db_job.created_at,
            completed_at=db_job.completed_at,
        )


async def _list_jobs_from_db(limit: int = 10) -> List[FleetSyncJobStatus]:
    """List recent fleet sync jobs from DB (#1707)."""
    from services.database import db_service

    async with db_service.session() as db:
        result = await db.execute(select(FleetSyncJobModel).order_by(FleetSyncJobModel.created_at.desc()).limit(limit))
        db_jobs = result.scalars().all()

        jobs = []
        for db_job in db_jobs:
            ns_result = await db.execute(
                select(FleetSyncNodeStateModel).where(FleetSyncNodeStateModel.job_id == db_job.job_id)
            )
            node_states = ns_result.scalars().all()

            jobs.append(
                FleetSyncJobStatus(
                    job_id=db_job.job_id,
                    status=db_job.status,
                    strategy=db_job.strategy,
                    total_nodes=db_job.total_nodes,
                    completed_nodes=db_job.completed_nodes,
                    failed_nodes=db_job.failed_nodes,
                    nodes=[
                        FleetSyncNodeStatus(
                            node_id=ns.node_id,
                            hostname=ns.hostname,
                            status=ns.status,
                            message=ns.message,
                            started_at=ns.started_at,
                            completed_at=ns.completed_at,
                        )
                        for ns in node_states
                    ],
                    created_at=db_job.created_at,
                    completed_at=db_job.completed_at,
                )
            )

        return jobs


async def _get_tracker_for_db(db: AsyncSession):
    """Return a GitTracker configured from the active CodeSource DB record.

    Falls back to DEFAULT_REPO_PATH / DEFAULT_BRANCH when no active
    source is configured.  Issue #1185.
    """
    result = await db.execute(select(CodeSource).where(CodeSource.is_active.is_(True)))
    source = result.scalar_one_or_none()
    repo_path = source.repo_path if source else DEFAULT_REPO_PATH
    branch = source.branch if source else DEFAULT_BRANCH
    return get_git_tracker(repo_path=repo_path, branch=branch)


@router.get("/status", response_model=CodeSyncStatusResponse)
async def get_sync_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CodeSyncStatusResponse:
    """
    Get current code sync status.

    Returns the latest version, local version, and count of outdated nodes.
    """
    tracker = await _get_tracker_for_db(db)

    # Get latest version from settings
    result = await db.execute(select(Setting).where(Setting.key == "slm_agent_latest_commit"))
    latest_setting = result.scalar_one_or_none()
    latest_version = latest_setting.value if latest_setting else None

    # Get local version
    local_version = await tracker.get_local_commit()

    # Count total nodes and outdated nodes
    total_result = await db.execute(select(func.count(Node.id)))
    total_nodes = total_result.scalar() or 0

    # Issue #1605: count outdated + service-failed as needing attention.
    # #11439: currency uses the SAME live signal as has_update (#9996-B:
    # code_version != latest), not the heartbeat-lagged code_status stamp —
    # otherwise the endpoint could report has_update=true with
    # outdated_nodes=0 (contradictory operator signal).
    if latest_version:
        outdated_result = await db.execute(
            select(func.count(Node.id)).where(
                sa_or(
                    Node.code_version.is_(None),
                    Node.code_version != latest_version,
                    Node.code_status == CodeStatus.CODE_CURRENT_SERVICE_FAILED.value,
                )
            )
        )
    else:
        outdated_result = await db.execute(
            select(func.count(Node.id)).where(
                Node.code_status.in_(
                    [
                        CodeStatus.OUTDATED.value,
                        CodeStatus.CODE_CURRENT_SERVICE_FAILED.value,
                    ]
                )
            )
        )
    outdated_nodes = outdated_result.scalar() or 0

    # Check if local repo has updates
    has_update = local_version is not None and latest_version is not None and local_version != latest_version

    return CodeSyncStatusResponse(
        latest_version=latest_version,
        local_version=local_version,
        last_fetch=tracker.last_fetch,
        has_update=has_update,
        outdated_nodes=outdated_nodes,
        total_nodes=total_nodes,
    )


@router.get("/drift", response_model=FileDriftReport)
async def get_file_drift(
    _: Annotated[dict, Depends(get_current_user)],
    component: str = "autobot-slm-backend",
) -> FileDriftReport:
    """
    Compare file checksums between code_source and the deployed directory (Issue #2834).

    Detects files that have drifted due to manual patches or incomplete Ansible deploys.
    For backend components Python/config/script files are compared; for frontend
    components (.vue/.ts/.css etc.) frontend source files are also included (Issue #10120).
    node_modules, dist, build, __pycache__, venv, and .git are always excluded.

    Query params:
        component: Sub-directory to compare (default: autobot-slm-backend).
                   Must be one of the allowed components (Issue #3427).

    Returns a FileDriftReport with a list of drifted files and their checksums.
    """
    if component not in ALLOWED_COMPONENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid component '{component}'. Must be one of: {sorted(ALLOWED_COMPONENTS)}",
        )

    try:
        source_dir = get_default_source_dir(component)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Failed to determine component path") from exc
    deployed_dir = get_default_deployed_dir(component)

    logger.info("drift check: comparing source=%s deployed=%s", source_dir, deployed_dir)

    report = await asyncio.get_running_loop().run_in_executor(
        None,
        functools.partial(build_drift_report, source_dir, deployed_dir, component),
    )

    logger.info(
        "drift check: %d drifted files out of %d compared",
        len(report["drifted_files"]),
        report["total_compared"],
    )

    return FileDriftReport(**report)


@router.post("/drift/resolve", response_model=DriftResolveResponse)
async def resolve_drift(
    request: DriftResolveRequest,
    _: Annotated[dict, Depends(get_current_user)],
) -> DriftResolveResponse:
    """
    Resync a single component from code_source/ to /opt/autobot/<component>/ (#7149, #9982).

    Uses `_rsync_component_local()` to pull files from the local code_source
    checkout and overwrite the deployed copy.  Used by the CodeSyncView
    "Resync from Source" button to clear drift in one click.

    After a successful rsync the handler runs component-appropriate post-steps
    (#9982) so that the synced code is immediately live:
      - Python backend components: pip install -r requirements.txt + service restart
      - Frontend components: npm ci + npm run build + nginx restart
      - Library components (autobot_shared): restart every dependent service so
        the new shared code is loaded (#10248)

    Body:
        component: Sub-directory under /opt/autobot/. Must be in ALLOWED_COMPONENTS.

    Returns DriftResolveResponse with success flag, rsync output, deps_changed
    flag, and a log of post-sync steps performed.
    """
    if request.component not in ALLOWED_COMPONENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid component '{request.component}'. Must be one of: {sorted(ALLOWED_COMPONENTS)}",
        )
    if _restart_is_pending():
        raise HTTPException(
            status_code=409,
            detail="A service restart from a previous resolve is in flight — retry in a few seconds (#11437)",
        )

    try:
        source_dir = get_default_source_dir(request.component)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Failed to determine source path") from exc
    deployed_dir = get_default_deployed_dir(request.component)

    # source_dir = /opt/autobot/code_source/<component>; _rsync_component_local
    # constructs `{source_path}/{component}/` so pass the parent.
    source_root = str(Path(source_dir).parent)

    excludes_map = {comp: excl for comp, excl in _SLM_COMPONENTS}
    excludes = excludes_map.get(
        request.component,
        [],  # artifacts excluded universally at the rsync chokepoint (#11459)
    )

    logger.info(
        "drift resolve: rsync source=%s/%s deployed=%s",
        source_root,
        request.component,
        deployed_dir,
    )

    # #11611: autobot_shared-first — sync the shared library BEFORE this
    # component's own rsync + restart so a newly-added `from autobot_shared.X`
    # import resolves at startup and the control plane cannot crash-loop on a
    # half-deployed shared tree. Fail the resolve if it cannot be synced.
    shared_ok, shared_msg = await _ensure_autobot_shared_synced(request.component)
    if not shared_ok:
        return DriftResolveResponse(
            success=False,
            component=request.component,
            message=shared_msg,
            source_dir=source_dir,
            deployed_dir=deployed_dir,
        )

    ok, msg = await _rsync_component_local(source_root, request.component, excludes)

    if not ok:
        return DriftResolveResponse(
            success=False,
            component=request.component,
            message=msg or "rsync failed",
            source_dir=source_dir,
            deployed_dir=deployed_dir,
        )

    # --- Post-sync: install deps / rebuild / restart so synced code goes live (#9982) ---
    deps_changed, post_steps, pip_ok = await _run_post_sync_steps(request.component, source_dir, deployed_dir)

    if not pip_ok:
        return DriftResolveResponse(
            success=False,
            component=request.component,
            message="Resynced from code_source but pip install failed — see post_steps",
            source_dir=source_dir,
            deployed_dir=deployed_dir,
            deps_changed=deps_changed,
            post_steps=post_steps,
        )

    return DriftResolveResponse(
        success=True,
        component=request.component,
        message=f"Resynced {request.component} from code_source",
        source_dir=source_dir,
        deployed_dir=deployed_dir,
        deps_changed=deps_changed,
        post_steps=post_steps,
    )


@router.post("/drift/resolve-async", response_model=DriftResolveJobResponse, status_code=202)
async def resolve_drift_async(
    request: DriftResolveRequest,
    _: Annotated[dict, Depends(get_current_user)],
) -> DriftResolveJobResponse:
    """
    Kick off an async per-component drift/resolve job (#11303).

    Identical validation to POST /drift/resolve but returns immediately with a
    job_id.  The rsync + post-sync steps (pip/build/alembic) run in the
    background.  Job status is persisted to DB so it survives the SLM backend
    restarting itself when autobot-slm-backend is the resolved component.

    Poll GET /drift/resolve/status/{job_id} to track progress.
    """
    if request.component not in ALLOWED_COMPONENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid component '{request.component}'. Must be one of: {sorted(ALLOWED_COMPONENTS)}",
        )
    if _restart_is_pending():
        raise HTTPException(
            status_code=409,
            detail="A service restart from a previous resolve is in flight — retry in a few seconds (#11437)",
        )

    from services.database import db_service

    job_id = uuid.uuid4().hex

    async with db_service.session() as db:
        db.add(
            ComponentSyncJobModel(
                job_id=job_id,
                component=request.component,
                status="running",
            )
        )
        await db.commit()

    task = asyncio.create_task(_run_component_resolve_job(job_id, request.component))
    _running_tasks[job_id] = task

    logger.info(
        "drift resolve-async: spawned job %s for component %s",
        job_id,
        request.component,
    )
    return DriftResolveJobResponse(job_id=job_id, component=request.component, status="running")


@router.get("/drift/resolve/status/{job_id}", response_model=ComponentSyncJobStatus)
async def get_component_resolve_status(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ComponentSyncJobStatus:
    """
    Return the status of an async component drift/resolve job (#11303).

    Raises 404 if job_id is unknown.
    """
    result = await db.execute(select(ComponentSyncJobModel).where(ComponentSyncJobModel.job_id == job_id))
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail=f"No component sync job found for id '{job_id}'")

    return ComponentSyncJobStatus(
        job_id=row.job_id,
        component=row.component,
        status=row.status,
        success=row.success,
        deps_changed=bool(row.deps_changed),
        message=row.message,
        post_steps=row.post_steps.split("\n") if row.post_steps else [],
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _refresh_message(has_update: bool) -> str:
    """Message for POST /refresh (#11439).

    ``/refresh`` only re-fetches version *metadata* (git fetch) — it does NOT deploy
    code. The old "Version updated successfully" wording read as if a deploy had
    happened, so operators could believe a pending fix was live when nothing had
    been synced. Word it as a metadata refresh and surface whether an update awaits.
    """
    if has_update:
        return "Version metadata refreshed — an update is available (run resolve/update to deploy it)"
    return "Version metadata refreshed — already up to date"


@router.post("/refresh", response_model=CodeSyncRefreshResponse)
async def refresh_version(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CodeSyncRefreshResponse:
    """
    Manually trigger a git fetch and update the latest version.
    """
    tracker = await _get_tracker_for_db(db)

    try:
        result = await tracker.check_for_updates(fetch=True)

        if result["remote_commit"]:
            # Update the setting
            setting_result = await db.execute(select(Setting).where(Setting.key == "slm_agent_latest_commit"))
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
                message=_refresh_message(result["has_update"]),
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
            detail="Failed to refresh version",
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
    setting_result = await db.execute(select(Setting).where(Setting.key == "slm_agent_latest_commit"))
    latest_setting = setting_result.scalar_one_or_none()
    latest_version = latest_setting.value if latest_setting else None

    # Get nodes needing attention: outdated or code-current-but-service-failed
    # Issue #1605: include service-failed nodes so operators see them
    result = await db.execute(
        select(Node)
        .where(
            Node.code_status.in_(
                [
                    CodeStatus.OUTDATED.value,
                    CodeStatus.CODE_CURRENT_SERVICE_FAILED.value,
                ]
            )
        )
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


# Components synced by the SLM code-sync flow. Per-component exclude lists are
# empty: every build/deploy artifact (__pycache__, *.pyc, .git, node_modules,
# dist, build, venv/.venv, *.egg-info, *.log, …) is now excluded universally at
# the rsync chokepoint from the canonical vocabulary (#11459,
# services/deploy_artifacts.py). A component only needs an entry here if it must
# exclude something that is NOT a standard artifact.
_SLM_COMPONENTS: List[Tuple[str, List[str]]] = [
    ("autobot-slm-backend", []),
    ("autobot-slm-frontend", []),
    ("autobot_shared", []),
]


# #9970: secret/runtime paths that must survive every sync. The deployed .env
# is the systemd EnvironmentFile (#2824) and exists only in the deployment --
# a delete-style sync without these excludes removes it and the service cannot
# start ("Failed to load environment files"). `data` holds per-service runtime
# state with the same property. Applied at the rsync chokepoint so no caller
# or future component list can forget them.
_PROTECTED_EXCLUDES: List[str] = [".env", "data"]


def _rsync_exclude_args(excludes: List[str]) -> List[str]:
    """Build --exclude args from caller excludes, canonical build/deploy
    artifacts, and protected runtime paths.

    Canonical artifact excludes (#11459) are injected here — the single rsync
    chokepoint — so every sync ignores exactly what the drift checker skips
    (shared source: services/deploy_artifacts.py). This keeps rsync and drift in
    lockstep: previously ``*.egg-info`` etc. were drift-skipped (#11440) but
    still deleted-and-resynced, churning the deployed tree. Protected paths
    (#9970) must survive every delete-style sync.
    """
    merged = list(dict.fromkeys([*excludes, *rsync_artifact_excludes(), *_PROTECTED_EXCLUDES]))
    return [f"--exclude={exc}" for exc in merged]


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
    ssh_opts = f"ssh -i {ssh_key} -o StrictHostKeyChecking=accept-new"
    cmd = [
        "rsync",
        "-avz",
        "--delete",
        "-e",
        ssh_opts,
        "--rsync-path=sudo rsync",  # source may need root to read e.g. /home/${USER:-autobot}/  # noqa
    ]
    cmd.extend(_rsync_exclude_args(excludes))
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


async def _rsync_component_local(
    source_path: str,
    component: str,
    excludes: List[str],
) -> Tuple[bool, str]:
    """Rsync a component locally when code source is on the same host (#1191).

    Used when source_ip matches the SLM server's own IP — no SSH needed.
    """
    cmd = ["rsync", "-avz", "--delete", "--no-group", "--no-owner"]
    cmd.extend(_rsync_exclude_args(excludes))
    cmd.append(f"{source_path}/{component}/")
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
            logger.error("local rsync failed for %s: %s", component, output[:500])
            return False, f"local rsync failed for {component}: {output[:200]}"
        logger.info("local rsync succeeded for %s", component)
        return True, ""
    except asyncio.TimeoutError:
        return False, f"local rsync timed out for {component}"
    except Exception as exc:
        return False, f"local rsync error for {component}: {exc}"


# =============================================================================
# Per-component post-sync steps (#9982)
# =============================================================================

# Maps component name → (pip_req_path, pip_bin_path) for Python components.
# Source of truth for venv/requirements paths per deployment layout.
_COMPONENT_PIP_PATHS: Dict[str, Tuple[str, str]] = {
    "autobot-backend": (
        "/opt/autobot/autobot-backend/requirements.txt",
        "/opt/autobot/autobot-backend/venv/bin/pip",
    ),
    "autobot-slm-backend": (
        "/opt/autobot/autobot-slm-backend/requirements.txt",
        "/opt/autobot/autobot-slm-backend/venv/bin/pip",
    ),
}

# Target CPython interpreter per backend component (#11323).
# NPU worker uses py3.11 (OpenVINO ABI); every other Python service uses py3.14.
# This is the single authoritative mapping — do not hardcode elsewhere.
_COMPONENT_PYTHON_TARGET: Dict[str, str] = {
    "autobot-backend": "python3.14",
    "autobot-slm-backend": "python3.14",
    "autobot-npu-worker": "python3.11",
}

# Ansible assets that provision the target interpreter on THIS host (#11343).
# Derived from the code_source layout (DEFAULT_REPO_PATH) so a non-standard
# SLM_REPO_PATH works without editing these — never hardcode /opt/autobot here.
# These paths MUST match the sudoers grant created by
# ansible/playbooks/configure-python-provision-permissions.yml.
_ANSIBLE_DIR: Path = Path(DEFAULT_REPO_PATH) / "autobot-slm-backend" / "ansible"
_PROVISION_PYTHON_PLAYBOOK: Path = _ANSIBLE_DIR / "playbooks" / "provision-local-python.yml"
# #11403: ansible resolves roles via roles_path in ansible.cfg, which it only reads
# from its cwd (or via ANSIBLE_CONFIG). Run from an arbitrary cwd, roles_path
# defaults to playbooks/roles/ and the python314 role (at ansible/roles/) is not
# found → play fails. We pass cwd=_ANSIBLE_DIR — it survives sudo's env_reset,
# whereas changing the command args would break the exact-match NOPASSWD sudoers
# rule. ANSIBLE_CONFIG is also set as a fallback (honored only if sudoers keeps it).
_ANSIBLE_CONFIG: Path = _ANSIBLE_DIR / "ansible.cfg"

# Deployed path for the top-level constraints/ dir (#11322).
# `autobot-backend/requirements.txt` uses `-c ../constraints/shared.txt` so the
# relative path resolves to /opt/autobot/constraints/ at runtime.  Code-sync
# only rsyncs component subdirs, so the constraints dir must be deployed
# explicitly before pip runs.
_CONSTRAINTS_SOURCE_SUBDIR: str = "constraints"

# Repo-root files referenced via `-r ../X` in component requirements (#11336).
# `autobot-backend/requirements.txt` uses `-r ../requirements.txt` which from
# /opt/autobot/autobot-backend/ resolves to /opt/autobot/requirements.txt — a
# path code-sync never writes.  This tuple lists the bare filenames (relative to
# the repo root) that must be copied to /opt/autobot/ before pip runs.
_REPO_ROOT_REQUIREMENT_FILES: tuple[str, ...] = ("requirements.txt",)

# Maps component name → deployed frontend directory for npm rebuild.
_COMPONENT_FRONTEND_DIRS: Dict[str, str] = {
    "autobot-frontend": "/opt/autobot/autobot-frontend",
    "autobot-slm-frontend": "/opt/autobot/autobot-slm-frontend",
}

# Timeout (seconds) for `npm ci` (dependency install).  Windows-generated
# package-lock.json on WSL can be slow; 300 s default matches pip (#11351).
_NPM_INSTALL_TIMEOUT: float = float(os.environ.get("AUTOBOT_NPM_INSTALL_TIMEOUT", "300"))

# Timeout (seconds) for `npm run <build>` (vite build step) (#11351).
_NPM_BUILD_TIMEOUT: float = float(os.environ.get("AUTOBOT_NPM_BUILD_TIMEOUT", "300"))

# Marker file stored inside node_modules after a successful npm ci.  Holds the
# sha256 hex-digest of the package-lock.json that was installed (#11351).
_NPM_LOCK_HASH_MARKER: str = ".autobot-lock-hash"

# npm build script per frontend component. The SLM frontend is co-located under
# /slm and MUST bake VITE_API_URL=/slm (via `build:slm`), or its API calls hit
# the root user backend instead of /slm/api — breaking login and every action
# (#11310). vite.config.ts hard-errors on a co-located build without it.
_COMPONENT_BUILD_SCRIPT: Dict[str, str] = {
    "autobot-slm-frontend": "build:slm",
}

# Maps component name → systemd service names to restart after sync.
# #11437: components whose restart set includes autobot-slm-backend itself.
# While such a restart chain is in flight this process is about to die; new
# resolve jobs accepted in that window get killed mid-run and (pre-#11437)
# were reconciled to failed with their migrations silently skipped.
_SELF_KILLING_COMPONENTS = frozenset({"autobot-slm-backend", "autobot_shared"})
# #11496: the systemd unit THIS process runs under. Restarting it kills this
# process (#11460), so restart chains must schedule it last — anything after it
# in a restart sequence never runs when the self-restart lands.
_SELF_SERVICE_NAME = "autobot-slm-backend"
_restart_pending: bool = False


def _restart_is_pending() -> bool:
    """True while a self-killing restart chain is in flight (#11437)."""
    return _restart_pending


_COMPONENT_SERVICES: Dict[str, List[str]] = {
    "autobot-backend": ["autobot-backend"],
    "autobot-slm-backend": ["autobot-slm-backend"],
    "autobot-frontend": ["nginx"],
    "autobot-slm-frontend": ["nginx"],
    # #10248: autobot_shared is imported by every Python service, so syncing it
    # must restart them all (else they keep running the old shared code and may
    # ImportError on a newly-referenced symbol). Restarts tolerate absent units
    # (distributed nodes won't have every service) — failures are logged, not fatal.
    # #11496: our own unit (_SELF_SERVICE_NAME) is deliberately LAST — its restart
    # kills this process (#11460), so any service listed after it would never be
    # restarted and no post-restart health verification could run.
    "autobot_shared": [
        "autobot-backend",
        "autobot-ai-stack",
        "autobot-celery",
        "autobot-celery-beat",
        "autobot-npu-worker",
        "autobot-slm-backend",
    ],
}


async def _deploy_constraints_dir(source_root: str, steps: List[str]) -> None:
    """Rsync top-level constraints/ to /opt/autobot/constraints/ before pip (#11322).

    autobot-backend/requirements.txt uses `-c ../constraints/shared.txt` so the
    relative reference resolves to /opt/autobot/constraints/shared.txt at deploy
    time. Code-sync only rsyncs component subdirs, so this helper deploys the
    constraints dir explicitly — preventing the silent pip failure that occurred
    when the file was absent.
    """
    src = f"{source_root}/{_CONSTRAINTS_SOURCE_SUBDIR}/"
    dst = f"/opt/autobot/{_CONSTRAINTS_SOURCE_SUBDIR}/"
    if not Path(src).exists():
        steps.append(f"constraints: source {src} not found — skipped")
        return
    steps.append(f"constraints: deploying {src} -> {dst}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "rsync",
            "-avz",
            "--delete",
            src,
            dst,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        _, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        if proc.returncode == 0:
            steps.append("constraints: deployed ok")
        else:
            steps.append(f"constraints: rsync failed (rc={proc.returncode})")
    except Exception as exc:
        steps.append(f"constraints: deploy error: {exc}")


async def _deploy_repo_root_requirements(source_root: str, steps: List[str]) -> None:
    """Copy top-level repo-root files to /opt/autobot/ before pip (#11336).

    autobot-backend/requirements.txt uses `-r ../requirements.txt` so the
    relative reference resolves to /opt/autobot/requirements.txt at deploy time.
    Code-sync only rsyncs component subdirs, so each file listed in
    _REPO_ROOT_REQUIREMENT_FILES is copied explicitly from source_root.
    Skips gracefully when the source file is absent (non-fatal).
    """
    base = _get_deploy_base()
    for filename in _REPO_ROOT_REQUIREMENT_FILES:
        src = Path(source_root) / filename
        dst = base / filename
        if not src.exists():
            steps.append(f"root-reqs: {src} not found — skipped")
            continue
        steps.append(f"root-reqs: copying {src} -> {dst}")
        try:
            proc = await asyncio.create_subprocess_exec(
                "cp",
                "--",
                str(src),
                str(dst),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            _, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            if proc.returncode == 0:
                steps.append(f"root-reqs: {filename} deployed ok")
            else:
                steps.append(f"root-reqs: cp {filename} failed (rc={proc.returncode})")
        except Exception as exc:
            steps.append(f"root-reqs: {filename} deploy error: {exc}")


async def _run_python_provision_playbook(target: str, steps: List[str]) -> bool:
    """Run the python314 role on localhost to install *target* (#11343).

    Invokes ansible-playbook via an ARG LIST (never a shell string) under sudo.
    The command matches the NOPASSWD sudoers grant from
    configure-python-provision-permissions.yml. Returns True on rc==0.
    """
    # ARG LIST only — never a shell string. Matches the NOPASSWD sudoers grant.
    # Use an inline localhost inventory ("localhost,") rather than the fleet
    # inventory + "--limit localhost": the fleet inventory has no localhost host,
    # so "--limit localhost" left ansible with no hosts to target (#11352). The
    # playbook is `hosts: localhost` / `connection: local`.
    cmd = ["sudo", "ansible-playbook", str(_PROVISION_PYTHON_PLAYBOOK)]
    cmd += ["--tags", "python314", "-i", "localhost,", "--connection", "local"]
    steps.append(f"python-provision: installing {target} via {_PROVISION_PYTHON_PLAYBOOK.name}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(_ANSIBLE_DIR),
            env={**os.environ, "ANSIBLE_CONFIG": str(_ANSIBLE_CONFIG)},
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=600.0)
        out = stdout.decode(errors="replace") if stdout else ""
        if proc.returncode == 0:
            logger.info("drift resolve: provisioned interpreter %s", target)
            steps.append(f"python-provision: {target} install ok")
            return True
        logger.error("drift resolve: interpreter provision failed (%d): %s", proc.returncode, out[-400:])
        steps.append(f"python-provision: FAILED (rc={proc.returncode}): {out[-200:]}")
        return False
    except asyncio.TimeoutError:
        logger.error("drift resolve: interpreter provision timed out for %s", target)
        steps.append("python-provision: timed out after 600s")
        return False
    except Exception as exc:
        logger.error("drift resolve: interpreter provision error for %s: %s", target, exc)
        steps.append(f"python-provision: error: {exc}")
        return False


async def _ensure_target_python_installed(component: str, steps: List[str]) -> None:
    """Install the target interpreter when missing, BEFORE venv recreation (#11343).

    Runs the Ansible python314 role (deadsnakes) scoped to localhost when the
    interpreter mapped in _COMPONENT_PYTHON_TARGET is absent from PATH. Preserves
    the #11323 safety guard: on provision failure it appends a clear step and
    RETURNS without touching the venv, so a running service is never bricked.
    The target is looked up from the trusted map — never a user-derived name.
    """

    target = _COMPONENT_PYTHON_TARGET.get(component)
    if target is None:
        return
    if shutil.which(target):
        steps.append(f"python-provision: {target} already present — skipped")
        return
    if not _PROVISION_PYTHON_PLAYBOOK.exists():
        steps.append(f"python-provision: playbook {_PROVISION_PYTHON_PLAYBOOK} not found — skipped")
        return
    ok = await _run_python_provision_playbook(target, steps)
    if not ok:
        return
    if shutil.which(target):
        steps.append(f"python-provision: {target} now on PATH")
    else:
        steps.append(f"python-provision: {target} STILL not on PATH after install")


async def _ensure_venv_python(component: str, steps: List[str]) -> bool:
    """Recreate the venv if its Python version doesn't match the target (#11323).

    Returns True when the venv was (re)created from scratch — a fresh interpreter
    cold-starts slowly, so the caller extends the post-restart health-poll window
    (#11458). Returns False when the venv was left intact (version ok, or skipped
    because the target interpreter is absent).

    Mirrors the ensure_venv_version Ansible role: runs `<venv>/bin/python --version`,
    compares against _COMPONENT_PYTHON_TARGET, and if mismatched removes the venv
    so the subsequent `pythonX.Y -m venv` call rebuilds it on the right interpreter.

    Safety: verifies the target interpreter is present on PATH (shutil.which) BEFORE
    removing anything. If absent, the existing venv is left intact and a skip step is
    recorded — the service stays running; operators must provision the interpreter
    first (Ansible python314 role). (#11327 review)
    """

    target = _COMPONENT_PYTHON_TARGET.get(component)
    paths = _COMPONENT_PIP_PATHS.get(component)
    if target is None or paths is None:
        return False
    _, pip_bin = paths
    venv_python = str(Path(pip_bin).parent / "python")
    if not Path(venv_python).exists():
        if not shutil.which(target):
            logger.warning("drift resolve: %s not on PATH — skipping venv create for %s", target, component)
            steps.append(
                f"venv: {venv_python} missing and {target} not installed"
                " — skipping recreation; provision the interpreter first (Ansible python314 role)"
            )
            return False
        steps.append(f"venv: {venv_python} missing — will create with {target}")
        await _recreate_venv(component, target, pip_bin, steps)
        return True
    try:
        proc = await asyncio.create_subprocess_exec(
            venv_python,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        version_out = stdout.decode(errors="replace").strip() if stdout else ""
        expected_fragment = target.replace("python", "")  # "3.14" or "3.11"
        if expected_fragment not in version_out:
            if not shutil.which(target):
                logger.warning(
                    "drift resolve: venv mismatch for %s (have %s, need %s) "
                    "but %s not on PATH — leaving existing venv intact",
                    component,
                    version_out,
                    expected_fragment,
                    target,
                )
                steps.append(
                    f"venv: mismatch (have '{version_out}', need {expected_fragment})"
                    f" but {target} not installed — skipping recreation;"
                    " provision the interpreter first (Ansible python314 role)"
                )
                return False
            steps.append(f"venv: mismatch (have '{version_out}', need {expected_fragment}) — recreating")
            venv_dir = str(Path(pip_bin).parents[1])
            shutil.rmtree(venv_dir, ignore_errors=True)
            await _recreate_venv(component, target, pip_bin, steps)
            return True
        steps.append(f"venv: python version ok ({version_out})")
    except Exception as exc:
        logger.error("drift resolve: venv version check failed for %s: %s", component, exc)
        steps.append(f"venv: version check error: {exc}")
    return False


async def _recreate_venv(component: str, python_bin: str, pip_bin: str, steps: List[str]) -> None:
    """Create a fresh venv using the target python interpreter (#11323)."""
    venv_dir = str(Path(pip_bin).parents[1])
    steps.append(f"venv: creating with {python_bin} at {venv_dir}")
    try:
        proc = await asyncio.create_subprocess_exec(
            python_bin,
            "-m",
            "venv",
            venv_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        if proc.returncode == 0:
            logger.info("drift resolve: recreated venv for %s with %s", component, python_bin)
            steps.append(f"venv: recreated ok ({python_bin})")
        else:
            out = stdout.decode(errors="replace")[:200] if stdout else ""
            logger.error("drift resolve: venv create failed (%d) for %s: %s", proc.returncode, component, out)
            steps.append(f"venv: create failed (rc={proc.returncode}): {out}")
    except Exception as exc:
        logger.error("drift resolve: venv create error for %s: %s", component, exc)
        steps.append(f"venv: create error: {exc}")


async def _install_pip_deps_for_component(component: str, steps: List[str]) -> bool:
    """Install Python deps from the component's requirements.txt into its venv (#9982).

    Unconditional — pip is fast when nothing changed (same rationale as #1603).
    Appends human-readable step notes to *steps*.
    Returns True on success, False when pip exits non-zero so callers can surface
    the failure (previously the non-zero rc was swallowed — #11322).
    """
    paths = _COMPONENT_PIP_PATHS.get(component)
    if paths is None:
        return True
    req_path, pip_bin = paths
    if not Path(req_path).exists():
        steps.append(f"pip: no requirements.txt at {req_path} — skipped")
        return True
    steps.append(f"pip: installing {req_path} into {Path(pip_bin).parent}")
    try:
        proc = await asyncio.create_subprocess_exec(
            pip_bin,
            "install",
            "-r",
            req_path,
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode == 0:
            logger.info("drift resolve: pip install ok for %s", component)
            steps.append("pip: install succeeded")
            return True
        out = stdout.decode(errors="replace")[:300] if stdout else ""
        logger.error("drift resolve: pip install failed (%d) for %s: %s", proc.returncode, component, out)
        steps.append(f"pip: install failed (rc={proc.returncode}): {out[:150]}")
        return False
    except asyncio.TimeoutError:
        logger.error("drift resolve: pip install timed out for %s", component)
        steps.append("pip: install timed out after 300s")
        return False
    except Exception as exc:
        logger.error("drift resolve: pip install error for %s: %s", component, exc)
        steps.append(f"pip: install error: {exc}")
        return False


# Components whose deployed tree ships Alembic migrations, keyed to the
# alembic.ini path RELATIVE to the deployed dir. `upgrade heads` (plural)
# tolerates multiple heads from parallel branch migrations.
_COMPONENT_MIGRATION_CONFIG: Dict[str, str] = {
    "autobot-backend": "migrations/alembic.ini",
}

# --- #11376: pg_dump before migrations -----------------------------------------
# Directory where pg_dump backups are stored; override with AUTOBOT_DB_BACKUP_DIR.
_DB_BACKUP_DIR: str = os.environ.get("AUTOBOT_DB_BACKUP_DIR", "/opt/autobot/db-backups")
# Maximum number of backups to retain per component; older ones are pruned.
_DB_BACKUP_KEEP: int = int(os.environ.get("AUTOBOT_DB_BACKUP_KEEP", "5"))

# --- #11378: post-restart health polling ---------------------------------------
# Total seconds to wait for a component to become healthy after restart. The
# window is adaptive (#11458): a freshly-recreated py3.14 venv cold-starts slowly
# — first-run bytecode compilation of the whole dependency tree can take >60s, so
# a short window falsely reported a healthy service as unhealthy and tripped the
# #11377 rollback (default 180s, #11413). A resync that did NOT recreate the venv
# restarts onto warm bytecode and is ready far sooner, so it uses the shorter FAST
# window and no longer burns the full 180s of dead wait on a silent hang. Both are
# env-overridable. Note: this only bounds how long we WAIT before proceeding on a
# non-failed unit — rollback is gated on a genuine systemd 'failed' state, not on
# the timeout (see _wait_component_healthy), so the shorter window cannot cause a
# false rollback of a slow-but-healthy deploy.
_DEFAULT_HEALTH_POLL_TIMEOUT_S = "180"
_HEALTH_POLL_TIMEOUT: float = float(os.environ.get("AUTOBOT_HEALTH_POLL_TIMEOUT", _DEFAULT_HEALTH_POLL_TIMEOUT_S))
# Fast window for restarts that did NOT recreate the venv (warm interpreter).
_FAST_HEALTH_POLL_TIMEOUT_S = "60"
_FAST_HEALTH_POLL_TIMEOUT: float = float(
    os.environ.get("AUTOBOT_HEALTH_POLL_TIMEOUT_FAST", _FAST_HEALTH_POLL_TIMEOUT_S)
)
# Per-attempt connect timeout (seconds) when probing the health endpoint.
_HEALTH_POLL_CONNECT_TIMEOUT: float = 3.0
# Per-component health URLs (localhost only — never egress).
_COMPONENT_HEALTH_URLS: Dict[str, str] = {
    "autobot-backend": "http://127.0.0.1:8001/api/health",
    "autobot-slm-backend": "http://127.0.0.1:8000/slm/api/code-sync/status",
    "autobot-frontend": "http://127.0.0.1/",
    "autobot-slm-frontend": "http://127.0.0.1/slm/",
}


def _load_env_file(env_path: Path) -> Dict[str, str]:
    """Parse a deployed KEY=VALUE .env into a dict (for subprocess env)."""
    env: Dict[str, str] = {}
    if not env_path.exists():
        return env
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _prune_old_backups(backup_dir: Path, component: str, max_keep: int) -> None:
    """Delete oldest pg_dump files for *component* beyond *max_keep* (#11376)."""
    prefix = f"{component}_"
    dumps = sorted(backup_dir.glob(f"{prefix}*.dump"), key=lambda p: p.stat().st_mtime)
    for old in dumps[:-max_keep] if max_keep > 0 else dumps:
        try:
            old.unlink()
            logger.info("pg_dump prune: removed %s", old)
        except OSError as exc:
            logger.warning("pg_dump prune: failed to remove %s: %s", old, exc)


_PG_COMPONENT_KEYS = (
    "AUTOBOT_POSTGRES_HOST",
    "AUTOBOT_POSTGRES_PORT",
    "AUTOBOT_POSTGRES_USER",
    "AUTOBOT_POSTGRES_PASSWORD",
    "AUTOBOT_POSTGRES_DB",
)


def _resolve_pg_db_url(env_vars: Dict[str, str]) -> str:
    """Resolve the Postgres connection URL from env vars (#11431, #11466).

    Resolution order (mirrors migrations/db_url.py and alembic env.py):
      1. AUTOBOT_DATABASE_URL  — explicit full URL (set by db-credentials.env.j2)
      2. DATABASE_URL          — bare alias some deployments use
      3. AUTOBOT_POSTGRES_*   — component vars from backend.env.j2 / os.environ

    Returns an empty string when no DB config can be found at all, which the
    caller treats as "proceed with warning" rather than "abort deploy".
    """
    # 1. Explicit full URL written by db-credentials.env.j2
    url = env_vars.get("AUTOBOT_DATABASE_URL") or os.environ.get("AUTOBOT_DATABASE_URL", "")
    if url:
        return url
    # 2. Bare DATABASE_URL alias
    url = env_vars.get("DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if url:
        return url
    # 3. Assemble from AUTOBOT_POSTGRES_* component vars (backend.env.j2 style).
    # Merge env_vars (higher precedence) over os.environ; filter empty strings so
    # assemble_postgres_url falls back to its per-key defaults correctly (#11466).
    merged = {k: v for k in _PG_COMPONENT_KEYS if (v := env_vars.get(k) or os.environ.get(k, ""))}
    return assemble_postgres_url(
        merged,
        default_user="autobot_app",
        default_db="autobot_users",
    )


async def _pg_dump_before_migration(component: str, deployed_dir: str, steps: List[str]) -> Optional[str]:
    """Take a pg_dump of the component DB before running migrations (#11376, #11431).

    Resolves the DB URL via _resolve_pg_db_url() which mirrors alembic env.py /
    migrations/db_url.py — checking AUTOBOT_DATABASE_URL, DATABASE_URL, and
    AUTOBOT_POSTGRES_* component vars in order.

    If no DB config is found at all, logs a warning and returns the sentinel
    "NO_BACKUP" so the caller PROCEEDS with migration rather than aborting.
    This keeps deploys working on boxes that have no DB configured for this
    component. Returns None only on a genuine pg_dump execution failure.
    """
    env_vars = _load_env_file(Path(deployed_dir) / ".env")
    db_url = _resolve_pg_db_url(env_vars)
    if not db_url:
        msg = "pg_dump: no DB config found (AUTOBOT_DATABASE_URL/AUTOBOT_POSTGRES_*) — skipping backup, proceeding"
        steps.append(msg)
        logger.warning("pg_dump: %s: %s", component, msg)
        return "NO_BACKUP"

    try:
        parsed = urlparse(db_url)
    except Exception as exc:
        steps.append(f"pg_dump: failed to parse DATABASE_URL: {exc}")
        return None

    backup_dir = Path(_DB_BACKUP_DIR)
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        steps.append(f"pg_dump: cannot create backup dir {backup_dir}: {exc}")
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dump_path = backup_dir / f"{component}_{ts}.dump"

    cmd = ["pg_dump", "--format=custom", f"--file={dump_path}"]
    if parsed.hostname:
        cmd += ["-h", parsed.hostname]
    if parsed.port:
        cmd += ["-p", str(parsed.port)]
    if parsed.username:
        cmd += ["-U", parsed.username]
    db_name = (parsed.path or "").lstrip("/") or parsed.username or ""
    if db_name:
        cmd.append(db_name)

    env = dict(os.environ)
    if parsed.password:
        env["PGPASSWORD"] = parsed.password
    env.update(env_vars)

    steps.append(f"pg_dump: backing up {component} DB to {dump_path}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        out = stdout.decode(errors="replace") if stdout else ""
        if proc.returncode != 0:
            logger.error("pg_dump FAILED (rc=%d) for %s: %s", proc.returncode, component, out[-400:])
            steps.append(f"pg_dump: FAILED (rc={proc.returncode}): {out[-200:]}")
            if dump_path.exists():
                dump_path.unlink(missing_ok=True)
            return None
        logger.info("pg_dump: backup ok for %s at %s", component, dump_path)
        steps.append(f"pg_dump: backup ok → {dump_path}")
        _prune_old_backups(backup_dir, component, _DB_BACKUP_KEEP)
        return str(dump_path)
    except asyncio.TimeoutError:
        logger.error("pg_dump: timed out for %s", component)
        steps.append("pg_dump: timed out after 300s")
        return None
    except Exception as exc:
        logger.error("pg_dump: error for %s: %s", component, exc)
        steps.append(f"pg_dump: error: {exc}")
        return None


async def _run_alembic_migrations(component: str, deployed_dir: str, steps: List[str]) -> bool:
    """Apply Alembic migrations (`upgrade heads`) so the schema matches synced code (#11255).

    Takes a pg_dump BEFORE running migrations (#11376, #11431).
    pg_dump returns None on execution failure (connection refused etc.) → migration
    ABORTED.  pg_dump returns "NO_BACKUP" when no DB config is found → migration
    PROCEEDS with a logged warning so the deploy is never blocked by a missing URL.
    Returns True on successful migration, False on abort or failure.
    """
    cfg_rel = _COMPONENT_MIGRATION_CONFIG.get(component)
    paths = _COMPONENT_PIP_PATHS.get(component)
    if cfg_rel is None or paths is None:
        return True
    _, pip_bin = paths
    alembic_bin = str(Path(pip_bin).with_name("alembic"))
    cfg_path = str(Path(deployed_dir) / cfg_rel)
    if not Path(alembic_bin).exists() or not Path(cfg_path).exists():
        steps.append(f"alembic: binary or config missing for {component} — skipped")
        return True

    # #11376/#11431: take a pg_dump BEFORE mutating the schema.
    # None = genuine pg_dump failure (connection failed etc.) → abort.
    # "NO_BACKUP" = no DB config found → proceed with warning (don't block deploy).
    dump_path = await _pg_dump_before_migration(component, deployed_dir, steps)
    if dump_path is None:
        steps.append("alembic: ABORTED — pg_dump failed; schema not migrated")
        logger.error("drift resolve: alembic aborted for %s — pg_dump failed", component)
        return False
    # Normalise: treat NO_BACKUP as None for display only; migration still runs.
    display_dump = dump_path if dump_path != "NO_BACKUP" else None

    # alembic env.py resolves DATABASE_URL from the environment; load the
    # component's deployed .env so migrations hit the right database.
    env = dict(os.environ)
    env.update(_load_env_file(Path(deployed_dir) / ".env"))
    env.setdefault("PYTHONPATH", deployed_dir)

    steps.append(f"alembic: upgrade heads ({cfg_rel})")
    try:
        proc = await asyncio.create_subprocess_exec(
            alembic_bin,
            "-c",
            cfg_path,
            "upgrade",
            "heads",
            cwd=deployed_dir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        out = stdout.decode(errors="replace") if stdout else ""
        if proc.returncode == 0:
            logger.info("drift resolve: alembic upgrade ok for %s", component)
            steps.append("alembic: upgrade succeeded")
            return True
        logger.error(
            "drift resolve: alembic upgrade FAILED (%d) for %s: %s",
            proc.returncode,
            component,
            out[-400:],
        )
        _backup_ref = f" — DB backup at {display_dump}" if display_dump else ""
        steps.append(f"alembic: upgrade FAILED (rc={proc.returncode}): {out[-200:]}{_backup_ref}")
        return False
    except asyncio.TimeoutError:
        logger.error("drift resolve: alembic upgrade timed out for %s", component)
        _backup_ref = f" — DB backup at {display_dump}" if display_dump else ""
        steps.append(f"alembic: upgrade timed out after 300s{_backup_ref}")
        return False
    except Exception as exc:
        logger.error("drift resolve: alembic upgrade error for %s: %s", component, exc)
        _backup_ref = f" — DB backup at {display_dump}" if display_dump else ""
        steps.append(f"alembic: upgrade error: {exc}{_backup_ref}")
        return False


def _lockfile_hash(frontend_dir: str) -> Optional[str]:
    """Return the sha256 hex-digest of <frontend_dir>/package-lock.json, or None if absent."""
    lock_path = Path(frontend_dir) / "package-lock.json"
    if not lock_path.exists():
        return None
    return hashlib.sha256(lock_path.read_bytes()).hexdigest()


def _lockfile_unchanged(frontend_dir: str) -> bool:
    """Return True when node_modules exists and its lock-hash marker matches the current lockfile.

    False means a fresh ``npm ci`` is needed (node_modules missing, marker absent,
    or package-lock.json changed since the last successful install).
    """
    node_modules = Path(frontend_dir) / "node_modules"
    if not node_modules.is_dir():
        return False
    marker = node_modules / _NPM_LOCK_HASH_MARKER
    if not marker.exists():
        return False
    stored = marker.read_text(encoding="utf-8").strip()
    current = _lockfile_hash(frontend_dir)
    return current is not None and stored == current


async def _npm_install_if_needed(frontend_dir: str, component: str, steps: List[str]) -> bool:
    """Run ``npm ci --prefix <frontend_dir>`` only when the lockfile changed or node_modules is missing.

    Writes a sha256 marker to node_modules/.autobot-lock-hash after success so
    subsequent runs with an unchanged lockfile skip the install entirely (#11351).
    Returns True on success (or skip), False on failure.
    """
    if _lockfile_unchanged(frontend_dir):
        steps.append("npm ci: skipped (node_modules up-to-date)")
        logger.info("drift resolve: npm ci skipped for %s — lockfile unchanged", component)
        return True
    steps.append(f"npm ci: installing deps in {frontend_dir}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "npm",
            "ci",
            "--prefix",
            frontend_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_NPM_INSTALL_TIMEOUT)
        if proc.returncode != 0:
            out = stdout.decode(errors="replace")[:300] if stdout else ""
            logger.warning("drift resolve: npm ci failed (%d) for %s: %s", proc.returncode, component, out)
            steps.append(f"npm ci: failed (rc={proc.returncode}): {out[:150]}")
            return False
    except asyncio.TimeoutError:
        logger.error("drift resolve: npm ci timed out for %s (%.0fs)", component, _NPM_INSTALL_TIMEOUT)
        steps.append(f"npm ci: timed out after {_NPM_INSTALL_TIMEOUT:.0f}s")
        return False
    except Exception as exc:
        logger.warning("drift resolve: npm ci error for %s: %s", component, exc)
        steps.append(f"npm ci: error: {exc}")
        return False
    # Persist the lockfile hash so the next run can skip reinstall.
    current_hash = _lockfile_hash(frontend_dir)
    if current_hash:
        marker = Path(frontend_dir) / "node_modules" / _NPM_LOCK_HASH_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(current_hash, encoding="utf-8")
    steps.append("npm ci: succeeded")
    return True


async def _ensure_dist_writable(frontend_dir: str, steps: List[str]) -> None:
    """Chown dist/ to the running service user so vite's emptyOutDir can rimraf it (#11364).

    Root-owned files (from a prior Ansible build) cause EACCES; chown normalises
    ownership without destroying the live bundle.  Service user = getpass.getuser()
    (never hardcoded). Failure is non-fatal — step recorded, build still attempted.
    """
    dist_dir = Path(frontend_dir) / "dist"
    if not dist_dir.exists():
        steps.append("dist: no dist/ directory — ownership check skipped")
        return
    service_user = getpass.getuser()
    owner_spec = f"{service_user}:{service_user}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "chown",
            "-R",
            owner_spec,
            str(dist_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        _, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        if proc.returncode == 0:
            logger.info("dist: chown -R %s %s ok", owner_spec, dist_dir)
            steps.append("dist: normalized ownership")
        else:
            logger.warning("dist: chown -R %s %s rc=%d", owner_spec, dist_dir, proc.returncode)
            steps.append(f"dist: chown failed (rc={proc.returncode}) — attempting build anyway")
    except Exception as exc:
        logger.warning("dist: chown error for %s: %s", dist_dir, exc)
        steps.append(f"dist: chown error: {exc} — attempting build anyway")


async def _build_npm_frontend_for_component(component: str, steps: List[str]) -> bool:
    """Install deps (if needed) then run the npm build script for a frontend component (#9982, #11351).

    Returns True when the build succeeds, False on any failure.
    Appends human-readable step notes to *steps*.
    """
    frontend_dir = _COMPONENT_FRONTEND_DIRS.get(component)
    if frontend_dir is None:
        return True
    steps.append(f"npm: building {frontend_dir}")
    await _ensure_dist_writable(frontend_dir, steps)
    install_ok = await _npm_install_if_needed(frontend_dir, component, steps)
    if not install_ok:
        return False
    build_script = _COMPONENT_BUILD_SCRIPT.get(component, "build")
    try:
        proc = await asyncio.create_subprocess_exec(
            "npm",
            "run",
            build_script,
            "--prefix",
            frontend_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_NPM_BUILD_TIMEOUT)
        if proc.returncode == 0:
            logger.info("drift resolve: npm build (%s) succeeded for %s", build_script, component)
            steps.append("npm build: succeeded")
            return True
        out = stdout.decode(errors="replace")[:300] if stdout else ""
        logger.warning("drift resolve: npm build failed (%d) for %s: %s", proc.returncode, component, out)
        steps.append(f"npm build: failed (rc={proc.returncode}): {out[:150]}")
        return False
    except asyncio.TimeoutError:
        logger.error("drift resolve: npm build timed out for %s (%.0fs)", component, _NPM_BUILD_TIMEOUT)
        steps.append(f"npm build: timed out after {_NPM_BUILD_TIMEOUT:.0f}s")
        return False
    except Exception as exc:
        logger.warning("drift resolve: npm build error for %s: %s", component, exc)
        steps.append(f"npm build: error: {exc}")
        return False


async def _restart_component_services(component: str, steps: List[str], services: Optional[List[str]] = None) -> None:
    """Restart the systemd service(s) associated with a deployed component (#9982).

    *services* overrides the _COMPONENT_SERVICES lookup so a caller can restart
    a subset (#11496: the autobot_shared path restarts non-self dependents first,
    health-verifies them, then restarts our own unit last).

    Appends human-readable step notes to *steps*.
    """
    global _restart_pending
    if services is None:
        services = _COMPONENT_SERVICES.get(component, [])
    if component in _SELF_KILLING_COMPONENTS:
        # #11437: this chain will restart autobot-slm-backend itself — reject
        # new resolve jobs until the process dies (flag resets on boot).
        _restart_pending = True
    for service in services:
        steps.append(f"restart: {service}")
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
            if proc.returncode == 0:
                logger.info("drift resolve: restarted %s", service)
                steps.append(f"restart {service}: ok")
            else:
                logger.warning("drift resolve: restart %s failed (rc=%d)", service, proc.returncode)
                steps.append(f"restart {service}: failed (rc={proc.returncode})")
        except asyncio.TimeoutError:
            logger.warning("drift resolve: restart %s timed out", service)
            steps.append(f"restart {service}: timed out")
        except Exception as exc:
            logger.warning("drift resolve: restart %s error: %s", service, exc)
            steps.append(f"restart {service}: error: {exc}")

    # #11460 review: reaching this line means the self-restart did NOT land
    # (systemctl restart of our own unit blocks until this process dies, so a
    # successful self-restart never returns here). Disarm the guard, or every
    # future resolve would 409 forever after a failed restart chain.
    _restart_pending = False


# =============================================================================
# #11377 — Component snapshot / rollback helpers
# =============================================================================


_SNAPSHOT_BASE_DIR: str = os.environ.get("AUTOBOT_SNAPSHOT_DIR", "/opt/autobot/snapshots")
_SNAPSHOT_KEEP: int = int(os.environ.get("AUTOBOT_SNAPSHOT_KEEP", "3"))


def _prune_old_snapshots(snap_base: Path, component: str, max_keep: int) -> None:
    """Remove oldest snapshot dirs for *component* beyond *max_keep* (#11404)."""
    prefix = f"{component}_"
    dirs = sorted(
        (d for d in snap_base.iterdir() if d.is_dir() and d.name.startswith(prefix)),
        key=lambda d: d.stat().st_mtime,
    )
    for old in dirs[:-max_keep] if max_keep > 0 else dirs:
        try:
            shutil.rmtree(old, ignore_errors=True)
            logger.info("snapshot prune: removed %s", old)
        except OSError as exc:
            logger.warning("snapshot prune: failed to remove %s: %s", old, exc)


async def _snapshot_component(component: str) -> Optional[str]:
    """Rsync the deployed dir to a timestamped backup before mutation (#11404).

    Deployed dirs are rsync copies — not git repos — so `git rev-parse HEAD`
    always fails, leaving snapshot=None and rollback printing "manual recovery".
    Instead: rsync the deployed dir to a snapshot under _SNAPSHOT_BASE_DIR,
    prune old snapshots, and return the backup path.

    Returns the backup dir path string on success, None on failure.
    """
    deployed_dir = get_default_deployed_dir(component)
    snap_base = Path(_SNAPSHOT_BASE_DIR)
    try:
        snap_base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("snapshot: cannot create %s: %s", snap_base, exc)
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = snap_base / f"{component}_{ts}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "rsync",
            "-a",
            "--delete",
            f"{deployed_dir}/",
            f"{backup_dir}/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        if proc.returncode != 0:
            out = stdout.decode(errors="replace") if stdout else ""
            logger.warning("snapshot: rsync failed for %s (rc=%d): %s", component, proc.returncode, out[-200:])
            return None
        logger.info("snapshot: %s backed up to %s", component, backup_dir)
        _prune_old_snapshots(snap_base, component, _SNAPSHOT_KEEP)
        return str(backup_dir)
    except asyncio.TimeoutError:
        logger.warning("snapshot: rsync timed out for %s", component)
        return None
    except Exception as exc:
        logger.warning("snapshot: error for %s: %s", component, exc)
        return None


async def _rollback_component(
    component: str,
    snapshot: Optional[str],
    steps: List[str],
    dump_path: Optional[str] = None,
) -> None:
    """Restore *component* from the filesystem snapshot after a failed post-sync step (#11404).

    Rsyncs from the backup dir created by _snapshot_component() back over the
    deployed dir, then restarts services.  Does NOT restore the DB — operators
    use the pg_dump at *dump_path*.

    No-op (logs warning) when *snapshot* is None.
    """
    if snapshot is None:
        steps.append("rollback: no snapshot available — manual recovery required")
        logger.warning("rollback: no snapshot for %s — cannot auto-revert", component)
        return

    deployed_dir = get_default_deployed_dir(component)
    steps.append(f"rollback: restoring {component} from {snapshot}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "rsync",
            "-a",
            "--delete",
            f"{snapshot}/",
            f"{deployed_dir}/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        out = stdout.decode(errors="replace") if stdout else ""
        if proc.returncode == 0:
            steps.append(f"rollback: restored from {snapshot}")
            logger.info("rollback: %s restored from %s", component, snapshot)
        else:
            steps.append(f"rollback: rsync restore failed (rc={proc.returncode}): {out[:200]}")
            logger.error("rollback: rsync restore failed for %s: %s", component, out[-300:])
            return
    except asyncio.TimeoutError:
        steps.append("rollback: rsync restore timed out after 120s")
        logger.error("rollback: rsync restore timed out for %s", component)
        return
    except Exception as exc:
        steps.append(f"rollback: rsync restore error: {exc}")
        logger.error("rollback: rsync restore error for %s: %s", component, exc)
        return

    await _restart_component_services(component, steps)
    if dump_path and dump_path != "NO_BACKUP":
        steps.append(f"rollback: DB backup available at {dump_path} for manual restore")


# =============================================================================
# #11378 — Post-restart health polling helper
# =============================================================================


async def _is_systemd_unit_failed(service: str) -> bool:
    """Return True only when systemd reports the unit is definitively failed (#11413).

    A unit in 'activating' (still starting) or 'inactive' states is NOT failed.
    Used to gate rollback: a slow cold-start must not be reverted.
    """
    services = _COMPONENT_SERVICES.get(service, [service])
    primary = services[0] if services else service
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "is-failed",
            primary,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        state = (stdout.decode(errors="replace") if stdout else "").strip()
        return state == "failed"
    except Exception:
        return False


async def _wait_component_healthy(component: str, steps: List[str], *, slow_start: bool = False) -> bool:
    """Poll the component health URL until healthy or timeout (#11378, #11413).

    Returns True when the endpoint responds 2xx within the timeout window, OR
    when the timeout expires WITHOUT a confirmed systemd failure — a slow cold
    start (py3.14 venv bytecode compilation can exceed 60s) must not trigger a
    rollback of an otherwise-successful deploy.

    Returns False ONLY when the systemd unit enters the 'failed' state during
    the polling window (crashloop, activation error, etc.).

    slow_start selects the adaptive timeout window (#11458): True when the restart
    is expected to be slow — a just-recreated venv (cold py3.14 interpreter) or a
    fresh frontend asset swap — using the full _HEALTH_POLL_TIMEOUT; False for a
    warm pip-backend restart, using the shorter _FAST_HEALTH_POLL_TIMEOUT. Either
    way rollback is gated on a genuine systemd failure, not on the timeout, so the
    fast window only trims dead wait — it never rolls back a slow-but-healthy
    deploy.

    Components with no health URL are considered healthy immediately.
    """
    try:
        import httpx
    except ImportError:
        steps.append("health: httpx not available — skipping health check")
        return True

    url = _COMPONENT_HEALTH_URLS.get(component)
    if url is None:
        steps.append(f"health: no health URL configured for {component} — skipped")
        return True

    timeout = _HEALTH_POLL_TIMEOUT if slow_start else _FAST_HEALTH_POLL_TIMEOUT
    deadline = asyncio.get_event_loop().time() + timeout
    attempt = 0
    while asyncio.get_event_loop().time() < deadline:
        attempt += 1
        # Check for a definitive systemd failure FIRST — fail fast on crashloop.
        if await _is_systemd_unit_failed(component):
            steps.append(f"health: {component} unit entered 'failed' state — rolling back")
            logger.error("health: %s systemd unit failed during startup poll", component)
            return False
        try:
            async with httpx.AsyncClient(timeout=_HEALTH_POLL_CONNECT_TIMEOUT) as client:
                resp = await client.get(url)
            if resp.status_code < 400:
                steps.append(f"health: {component} healthy (HTTP {resp.status_code}) after {attempt} attempt(s)")
                logger.info("health: %s healthy at %s (attempt %d)", component, url, attempt)
                return True
        except Exception:
            pass
        await asyncio.sleep(2.0)

    # Timeout reached but no systemd failure — the unit may still be starting
    # (e.g. py3.14 venv cold-start). Warn but do NOT roll back (#11413).
    if await _is_systemd_unit_failed(component):
        steps.append(f"health: {component} unit failed after {timeout:.0f}s — rolling back")
        logger.error("health: %s systemd unit failed after polling", component)
        return False
    steps.append(
        f"health: {component} did not respond within {timeout:.0f}s"
        " — unit not failed; deploy treated as successful (check {url} manually)"
    )
    logger.warning("health: %s timeout after %.0fs but unit not failed — proceeding", component, timeout)
    return True


async def _restart_dependents_with_health(component: str, snapshot: Optional[str], steps: List[str]) -> bool:
    """Restart *component*'s dependent services with post-restart verification (#11496).

    A shared-lib (autobot_shared) sync fans out to restart BOTH backends — an
    import-heavy cold start — yet previously had zero post-restart health
    verification. Restart every dependent EXCEPT this process's own unit first,
    health-poll each (slow_start=True — cold re-import), and roll back the
    component dir when any dependent fails. Dependents without an HTTP health
    URL are verified via systemd state: a broken shared import surfaces as a
    'failed' unit. Only when all others are healthy is our own unit restarted
    last (which kills this process when it lands — #11437/#11460).

    Returns True when all verified dependents are healthy; False after rollback.
    """
    global _restart_pending
    dependents = _COMPONENT_SERVICES.get(component, [])
    others = [s for s in dependents if s != _SELF_SERVICE_NAME]
    await _restart_component_services(component, steps, services=others)
    # The chain is still in flight — its final step (or a rollback) restarts our
    # own unit. Keep the #11437 guard armed through the verification window (the
    # surviving return above disarmed it, #11460) so resolve jobs accepted while
    # we poll aren't killed mid-run by the upcoming self-restart.
    self_restart_ahead = _SELF_SERVICE_NAME in dependents
    if self_restart_ahead:
        _restart_pending = True
    unhealthy: List[str] = []
    for dep in others:
        if dep in _COMPONENT_HEALTH_URLS:
            if not await _wait_component_healthy(dep, steps, slow_start=True):
                unhealthy.append(dep)
        elif await _is_systemd_unit_failed(dep):
            steps.append(f"health: {dep} unit entered 'failed' state after {component} restart")
            unhealthy.append(dep)
    if unhealthy:
        await _rollback_component(component, snapshot, steps, None)
        steps.append(
            "post-sync: rolled back to last-known-good due to unhealthy "
            f"dependents after {component} restart: {', '.join(unhealthy)}"
        )
        # Still alive ⇒ no self-restart landed (rollback restarted us last and
        # failed, or errored before restarting). Disarm so recovery resolves
        # aren't 409-blocked forever (#11460).
        _restart_pending = False
        return False
    if self_restart_ahead:
        # All other dependents verified healthy — restart ourselves last. When
        # this lands the process dies inside the call; a surviving return means
        # the self-restart failed (and disarmed the guard, #11460).
        await _restart_component_services(component, steps, services=[_SELF_SERVICE_NAME])
    return True


# Python backend components that embed an autobot_shared symlink (#10912).
_BACKEND_COMPONENTS = frozenset(_COMPONENT_PIP_PATHS.keys())


def _get_deploy_base() -> Path:
    """Return the installation base directory from config (AUTOBOT_BASE_DIR, default /opt/autobot).

    Reads the value at call time so that tests can monkeypatch the environment
    variable or the config object without needing to patch a module-level string.
    Avoids importing autobot_shared.ssot_config at module load (bootstrap safety).
    """
    try:
        from autobot_shared.ssot_config import get_config as _get_config

        return Path(_get_config().path.base_dir)
    except Exception:
        # ssot_config unavailable at bootstrap — fall back to the env var directly.
        import os

        return Path(os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot"))


async def _ensure_autobot_shared_symlink(component: str, steps: List[str]) -> None:
    """Restore <AUTOBOT_BASE_DIR>/<component>/autobot_shared → <AUTOBOT_BASE_DIR>/autobot_shared (#10912).

    The deploy rsync uses --delete, which removes the symlink because it is not
    present in the code_source tree. Without it the backend process crashes on
    import with ModuleNotFoundError. This helper recreates the symlink so the
    component restarts cleanly.

    The base directory is read from AUTOBOT_BASE_DIR via PathConfig so that
    non-standard deployments (e.g. AUTOBOT_BASE_DIR=/srv/autobot) work without
    any code change (#10912 follow-up).

    Only acts on Python backend components (autobot-backend, autobot-slm-backend).
    Non-fatal: errors are logged and a step note is appended, but the sync is not
    aborted — a missing symlink is survivable until the next restart.
    """
    if component not in _BACKEND_COMPONENTS:
        return
    base = _get_deploy_base()
    shared_target = base / "autobot_shared"
    if not shared_target.exists():
        steps.append(f"symlink: {shared_target} not found — skipped")
        return
    link_path = base / component / "autobot_shared"
    try:
        if link_path.is_symlink() and link_path.resolve() == shared_target.resolve():
            steps.append(f"symlink: {link_path} already correct")
            return
        if link_path.is_symlink() or link_path.exists():
            link_path.unlink()
        link_path.symlink_to(shared_target)
        logger.info("drift resolve: restored autobot_shared symlink for %s", component)
        steps.append(f"symlink: {link_path} -> {shared_target} (restored)")
    except Exception as exc:
        logger.error("drift resolve: symlink restore failed for %s: %s", component, exc)
        steps.append(f"symlink: restore failed for {component}: {exc}")


async def _ensure_autobot_shared_synced(component: str) -> Tuple[bool, str]:
    """Resync autobot_shared from code_source BEFORE a dependent backend deploys (#11611).

    #11611 root cause: autobot_shared is a component deployed by its OWN
    drift/resolve — it is NOT pulled in when a dependent (autobot-slm-backend /
    autobot-backend) is resolved. When a resync of a backend deployed new code
    that imports a freshly-added shared module (e.g. `from autobot_shared.db_url
    import assemble_postgres_url`, #11583) and then restarted the service while
    /opt/autobot/autobot_shared still held the OLD tree, the import failed at
    startup and the control plane crash-looped (taking the code-sync API offline —
    a chicken-and-egg that needed a manual recovery).

    Enforce autobot_shared-first ordering at the per-component deploy sites: for a
    Python backend component, rsync the shared library from code_source ahead of
    the component's own rsync + restart so every new shared import resolves. No-op
    (returns success) for autobot_shared itself and for frontends — they either ARE
    the shared component or do not import it at start.

    Returns (ok, message). On rsync failure the caller must fail-safe (do NOT
    restart the backend onto a half-deployed shared tree).
    """
    if component not in _BACKEND_COMPONENTS:
        return True, ""
    try:
        shared_source = get_default_source_dir("autobot_shared")
    except ValueError:
        # code_source layout unavailable — leave the existing tree in place rather
        # than blocking the resolve; the symlink restore still runs downstream.
        return True, "autobot_shared source path unavailable — left as-is"
    source_root = str(Path(shared_source).parent)
    excludes_map = {comp: excl for comp, excl in _SLM_COMPONENTS}
    excludes = excludes_map.get("autobot_shared", [])
    ok, msg = await _rsync_component_local(source_root, "autobot_shared", excludes)
    if ok:
        logger.info("autobot_shared-first: resynced ahead of %s (#11611)", component)
        return True, f"autobot_shared-first: resynced ahead of {component} (#11611)"
    logger.error("autobot_shared-first: resync FAILED before %s: %s (#11611)", component, msg)
    return False, f"autobot_shared-first: resync failed before {component}: {msg} (#11611)"


async def _run_post_sync_steps(
    component: str,
    source_dir: str,
    deployed_dir: str,
    restart: bool = True,
) -> Tuple[bool, List[str], bool]:
    """Run dep-install / rebuild / restart after a per-component rsync (#9982).

    Returns (deps_changed, steps_log, pip_ok).
    pip_ok is False when pip or npm exits non-zero so resolve_drift can surface
    the failure via success=False rather than silently returning success=True
    (#11322, #11351).

    #11377: Captures a git snapshot BEFORE any mutation so that on failure the
    deployed dir can be reverted.  Rollback is triggered when pip/alembic/build
    fails or when the post-restart health poll (#11378) reports unhealthy.
    The DB is NOT rolled back automatically — operators use the pg_dump (#11376).

    restart=False defers the final service restart so the async job path (#11303)
    can commit the job row to DB before restarting (surviving a self-restart of
    autobot-slm-backend).  All other steps still run; restart=True (default) keeps
    the existing synchronous behaviour for all current callers.

    Component routing:
      - Python backend (autobot-backend, autobot-slm-backend):
          constraints deploy (#11322) + venv version check (#11323) +
          pip install + symlink restore (#10912) + alembic + restart + health
      - Frontend (autobot-frontend, autobot-slm-frontend): npm ci (conditional) + build + nginx reload + health
      - autobot_shared: restore BOTH backends' symlinks (#10912) + restart
          dependents (self last) + per-dependent health + rollback (#11496)
    """
    steps: List[str] = []
    pip_ok = True

    # Compute deps_changed post-rsync (source == deployed now; any prior delta
    # is gone, so this is always False after a successful rsync — but we check
    # pre-rsync via the existing hash helper using deployed_dir as the reference).
    # For the response we report whether deps files existed and were touched.
    deps_changed = await _compute_deps_changed(component)

    # #11377: snapshot the deployed dir BEFORE any mutation for rollback.
    snapshot = await _snapshot_component(component)
    # Track the last pg_dump path for rollback failure messages (#11376+#11377).
    last_dump_path: Optional[str] = None

    if component in _COMPONENT_PIP_PATHS:
        source_root = str(Path(source_dir).parent)
        await _deploy_constraints_dir(source_root, steps)
        await _deploy_repo_root_requirements(source_root, steps)
        await _ensure_target_python_installed(component, steps)
        venv_recreated = await _ensure_venv_python(component, steps)
        pip_ok = await _install_pip_deps_for_component(component, steps)
        if not pip_ok:
            await _rollback_component(component, snapshot, steps, last_dump_path)
            return deps_changed, steps, False
        alembic_ok = await _run_alembic_migrations(component, deployed_dir, steps)
        # Extract the dump path recorded during _run_alembic_migrations for rollback msg.
        last_dump_path = next(
            (s.split("→")[-1].strip() for s in steps if "pg_dump: backup ok" in s),
            None,
        )
        if not alembic_ok:
            await _rollback_component(component, snapshot, steps, last_dump_path)
            return deps_changed, steps, False
        await _ensure_autobot_shared_symlink(component, steps)
        if restart:
            await _restart_component_services(component, steps)
            # #11458: a just-recreated venv cold-starts slowly → full health-poll
            # window; a warm restart uses the shorter fast window.
            healthy = await _wait_component_healthy(component, steps, slow_start=venv_recreated)
            if not healthy:
                await _rollback_component(component, snapshot, steps, last_dump_path)
                steps.append("post-sync: rolled back to last-known-good due to unhealthy post-restart")
                pip_ok = False
        else:
            steps.append("post-sync: restart deferred")
    elif component in _COMPONENT_FRONTEND_DIRS:
        npm_ok = await _build_npm_frontend_for_component(component, steps)
        if not npm_ok:
            await _rollback_component(component, snapshot, steps, None)
            pip_ok = False
        elif restart:
            await _restart_component_services(component, steps)
            # Frontend keeps the full health-poll window (#11458 review): the fast
            # window is only for warm pip-backend restarts. A fresh nginx worker
            # after a large asset swap can lag past 60s, and the generous window
            # avoids logging an otherwise-healthy frontend as "check manually".
            healthy = await _wait_component_healthy(component, steps, slow_start=True)
            if not healthy:
                await _rollback_component(component, snapshot, steps, None)
                steps.append("post-sync: rolled back to last-known-good due to unhealthy post-restart")
                pip_ok = False
        else:
            steps.append("post-sync: restart deferred")
    elif component in _COMPONENT_SERVICES:
        # Library component (autobot_shared): no build step, but every service
        # that imports it must restart so the new shared code is loaded (#10248).
        # Restore both backends' symlinks first so services start cleanly (#10912).
        for backend in sorted(_BACKEND_COMPONENTS):
            await _ensure_autobot_shared_symlink(backend, steps)
        if restart:
            # #11496: was the only sync path with no post-restart health poll
            # or rollback — a shared-lib change that broke a backend import
            # restarted onto a dead service undetected.
            if not await _restart_dependents_with_health(component, snapshot, steps):
                pip_ok = False
        else:
            steps.append("post-sync: restart deferred")
    else:
        steps.append(f"post-sync: no service or build step for {component}")

    return deps_changed, steps, pip_ok


async def _build_slm_frontend() -> None:
    """Run npm ci + npm run build for the SLM frontend.

    Issue #1607: The Ansible path builds the frontend; the self-sync
    path was missing this step, serving stale dist/ files.
    Issue #1624: Fix ownership before build — Ansible deploys as root.
    """
    frontend_dir = "/opt/autobot/autobot-slm-frontend"
    try:
        # Fix ownership — Ansible may have created root-owned files (#1624)
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "chown",
            "-R",
            "autobot:autobot",
            frontend_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30.0)

        # npm ci — install exact lockfile deps
        proc = await asyncio.create_subprocess_exec(
            "npm",
            "ci",
            "--prefix",
            frontend_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode != 0:
            logger.warning(
                "SLM self-sync: npm ci failed (%d): %s",
                proc.returncode,
                stdout.decode(errors="replace")[:500],
            )
            return

        # npm run build
        proc = await asyncio.create_subprocess_exec(
            "npm",
            "run",
            "build",
            "--prefix",
            frontend_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode == 0:
            logger.info("SLM self-sync: frontend build complete")
        else:
            logger.warning(
                "SLM self-sync: npm build failed (%d): %s",
                proc.returncode,
                stdout.decode(errors="replace")[:500],
            )
    except Exception as exc:
        logger.warning("SLM self-sync: frontend build failed: %s", exc)


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


async def _install_slm_pip_dependencies() -> None:
    """Install Python dependencies from requirements.txt into the SLM venv.

    Runs unconditionally after rsync — pip is fast when nothing changed (#1603).
    """
    req_path = "/opt/autobot/autobot-slm-backend/requirements.txt"
    pip_bin = "/opt/autobot/autobot-slm-backend/venv/bin/pip"

    if not Path(req_path).exists():
        logger.debug("No requirements.txt at %s — skipping pip install", req_path)
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            pip_bin,
            "install",
            "-r",
            req_path,
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode == 0:
            logger.info("SLM pip install completed successfully")
        else:
            output = stdout.decode(errors="replace")[:500] if stdout else ""
            logger.error("SLM pip install failed (rc=%d): %s", proc.returncode, output)
    except asyncio.TimeoutError:
        logger.error("SLM pip install timed out after 300s")
    except Exception as exc:
        logger.error("SLM pip install error: %s", exc)


async def _fetch_code_source_connection_info(
    db_service,
) -> Tuple[str, str, str] | None:
    """Helper for _sync_slm_from_code_source. Ref: #1088, #1209.

    Read code source connection details from DB.

    Returns:
        Tuple of (source_ip, source_user, repo_path)
        or None if the required records are missing.
    """
    from models.database import CodeSource, Node  # avoid circular import

    try:
        async with db_service.session() as db:
            source_result = await db.execute(select(CodeSource).where(CodeSource.is_active.is_(True)))
            source = source_result.scalar_one_or_none()
            if not source:
                logger.error("SLM self-sync failed: no active code source")
                return None

            node_result = await db.execute(select(Node).where(Node.node_id == source.node_id))
            source_node = node_result.scalar_one_or_none()
            if not source_node:
                logger.error("SLM self-sync failed: code source node not found in DB")
                return None

            return (
                source_node.ip_address,
                source_node.ssh_user or "autobot",
                source.repo_path,
            )
    except Exception as db_err:
        logger.error("SLM self-sync failed: DB read error: %s", db_err)
        return None


async def _mark_slm_node_up_to_date(db_service, node_id: str) -> None:
    """Helper for _sync_slm_from_code_source. Ref: #1088, #1209.

    Persist UP_TO_DATE status for the SLM node after a successful rsync.
    Uses git_tracker.get_local_commit() for the actual code_source HEAD
    instead of the potentially-stale CodeSource.last_known_commit.
    """
    from models.database import Node  # avoid circular import

    git_tracker = get_git_tracker()
    current_commit = await git_tracker.get_local_commit()
    if not current_commit:
        logger.warning("SLM self-sync: could not determine current commit")
        return

    try:
        async with db_service.session() as db:
            slm_result = await db.execute(select(Node).where(Node.node_id == node_id))
            slm_node = slm_result.scalar_one_or_none()
            if slm_node:
                slm_node.code_version = current_commit
                slm_node.code_status = CodeStatus.UP_TO_DATE.value
                logger.info(
                    "SLM self-sync: marked %s as up-to-date at %s",
                    node_id,
                    current_commit[:12],
                )
    except Exception as db_err:
        logger.warning("SLM self-sync: could not update node status: %s", db_err)


async def _sync_slm_from_code_source(node_id: str) -> None:
    """Pull SLM components from the code source node and restart services.

    Used when the GUI triggers a sync for the SLM server itself (#913).
    The Ansible playbook cannot be used because it runs rsync FROM the
    controller (SLM server) but the source path only exists on the dev machine.
    This function reverses the direction: SLM server PULLS from the code source.

    NOTE: Must create its own DB session — the request-scoped session passed
    from sync_node is closed by FastAPI before this background task runs.
    """
    from services.database import db_service  # own session to avoid closed-session bug

    # --- Phase 1: gather connection info from DB ---
    conn_info = await _fetch_code_source_connection_info(db_service)
    if conn_info is None:
        return
    source_ip, source_user, repo_path = conn_info

    # Detect if code source is on the same host — skip SSH entirely (#1191, #2759)
    from autobot_shared.network_utils import is_local_ip

    is_local_source = is_local_ip(source_ip)

    if is_local_source:
        logger.info("SLM self-sync: code source is local at %s, using direct rsync", repo_path)
    else:
        ssh_key = os.environ.get("SLM_SSH_KEY", "/home/autobot/.ssh/autobot_key")  # noqa: ssot-path
        if not _ssh_key_usable(ssh_key):
            logger.error("SLM self-sync failed: SSH key not usable at %s", ssh_key)
            return
        logger.info("SLM self-sync: pulling from %s@%s:%s", source_user, source_ip, repo_path)

    # --- Phase 2: rsync components ---
    all_ok = True
    for component, excludes in _SLM_COMPONENTS:
        if is_local_source:
            ok, msg = await _rsync_component_local(repo_path, component, excludes)
        else:
            ok, msg = await _rsync_component(source_user, source_ip, repo_path, component, excludes, ssh_key)
        if not ok:
            logger.error("SLM self-sync component %s failed: %s", component, msg)
            all_ok = False

    if not all_ok:
        logger.error("SLM self-sync had failures; services NOT restarted")
        return

    # --- Phase 2b: install Python dependencies if requirements.txt changed (#1603) ---
    await _install_slm_pip_dependencies()

    # --- Phase 2c: rebuild SLM frontend (#1607) ---
    await _build_slm_frontend()
    # --- Phase 3: mark up-to-date in DB before restarting (#1209) ---
    await _mark_slm_node_up_to_date(db_service, node_id)

    # --- Phase 4: restart services ---
    await _restart_slm_service("autobot-slm-backend")
    await _restart_slm_service("nginx")
    logger.info("SLM self-sync complete and services restarted")
    # NOTE: Post-restart health is monitored by heartbeat (#1604/#1605).
    # The restarted process reports crash-loop/service-failed status
    # if it fails to come up, so code_status will reflect the true state.


async def _execute_node_playbook(
    executor,
    node: Node,
    node_id: str,
    request: NodeSyncRequest,
    progress_callback,
    db: AsyncSession,
) -> NodeSyncResponse:
    """Helper for sync_node. Ref: #1088.

    Build playbook params, run the playbook, update the node version in DB,
    and return the NodeSyncResponse for the normal (non-SLM-self) path.
    """
    # Use node_id (maps to slm_node_id in Ansible inventory) not hostname —
    # hostname is user-editable and can drift from inventory host names (#921)
    # Issue #1091: Include localhost so Play 0 (archive build) runs
    limit = ["localhost", node.node_id]
    tags = []
    if not request.restart:
        tags.append("!restart")  # Skip restart tasks

    playbook_result = await executor.execute_playbook(
        playbook_name="update-all-nodes.yml",
        limit=limit,
        tags=tags if tags else None,
        progress_callback=progress_callback,
    )

    if playbook_result["success"]:
        await _update_node_version_after_sync(db, node, node_id)

    return NodeSyncResponse(
        success=playbook_result["success"],
        message=(
            playbook_result["output"] if playbook_result["success"] else f"Playbook failed: {playbook_result['output']}"
        ),
        node_id=node_id,
    )


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


async def _update_node_version_after_sync(db: AsyncSession, node: Node, node_id: str) -> None:
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

    # Progress callback for WebSocket broadcasts (Issue #880)
    async def progress_callback(progress: Dict[str, str]) -> None:
        await _broadcast_sync_progress(node_id, progress)

    # Check if this is the SLM server itself (Issue #867)
    # When syncing the SLM server, we can't wait for the playbook to complete
    # because the backend will restart during execution, causing HTTP 502 errors
    # Detect by IP (not by name — names are user-editable) (#921)
    slm_own_ip = urlparse(settings.external_url).hostname or ""
    is_slm_server = bool(slm_own_ip) and node.ip_address == slm_own_ip

    if is_slm_server and request.restart:
        # Use Ansible to update all deployed roles on this machine (#9073).
        # Covers backend, frontend, shared, agent, plugins, workers, etc.
        logger.info("SLM self-update via Ansible: queuing (fire-and-forget)")
        asyncio.create_task(_ansible_self_update(node_id))
        return NodeSyncResponse(
            success=True,
            message=(
                "SLM update queued: Ansible will update all roles on this machine and restart services. "
                "Check backend health in ~60s."
            ),
            node_id=node_id,
        )

    # Normal execution - wait for result with progress updates
    return await _execute_node_playbook(executor, node, node_id, request, progress_callback, db)


async def _ansible_self_update(node_id: str) -> None:
    """Run update-all-nodes.yml against this machine to update all deployed roles (#9073).

    Covers every role Ansible knows about (backend, frontend, shared, agent,
    plugins, npu-worker, browser-worker, etc.) — not just the SLM components.
    Fire-and-forget: the SLM service restarts mid-run so this coroutine dies.
    ``detach=True`` runs the ansible-playbook process in its own systemd
    transient scope (#11492) so it — unlike this coroutine — survives that
    restart and completes Play 1's tail plus Play 2/3; callers must poll
    health rather than await a result.

    Issue #9224: Update node version in DB after successful sync.
    C2-a: Clear the resume plan on playbook failure (before restart) so stale
          plans do not auto-fire forever.
    """
    executor = get_playbook_executor()
    limit = ["localhost", node_id]
    try:
        result = await executor.execute_playbook(
            playbook_name="update-all-nodes.yml",
            limit=limit,
            detach=True,
        )
        if not result["success"]:
            logger.error("Ansible full-machine update failed for %s: %s", node_id, result["output"][:500])
            # C2-a: playbook failed before restart — clear plan so it never auto-fires
            await _clear_resume_plan()
        else:
            logger.info("Ansible full-machine update complete for %s", node_id)
            # Update node version in DB (Issue #9224)
            await _update_fleet_node_version(node_id)
    except Exception as exc:
        logger.error("Ansible full-machine update error for %s: %s", node_id, exc)
        await _clear_resume_plan()


@router.post("/self-update", response_model=NodeSyncResponse)
async def self_update(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeSyncResponse:
    """Trigger an Ansible-based update of the SLM server itself (#9073).

    Looks up the SLM's own node record by matching the external_url IP,
    then runs update-all-nodes.yml against it as a fire-and-forget task
    (the service restarts mid-run, so the caller should poll health).
    Returns immediately with a queued message.
    """
    slm_own_ip = urlparse(settings.external_url).hostname or ""
    if not slm_own_ip:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cannot determine SLM IP from external_url setting",
        )

    result = await db.execute(select(Node).where(Node.ip_address == slm_own_ip))
    slm_node = result.scalar_one_or_none()
    if not slm_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No node found with IP {slm_own_ip} — ensure this server is registered",
        )

    logger.info("Full machine update via Ansible: queuing for node %s", slm_node.node_id)
    asyncio.create_task(_ansible_self_update(slm_node.node_id))

    return NodeSyncResponse(
        success=True,
        message=(
            "Full update queued: Ansible will update all roles on this machine"
            " and restart services. Check backend health in ~60s."
        ),
        node_id=slm_node.node_id,
        job_id=None,
    )


async def _sync_regular_nodes(executor, job: FleetSyncJob, regular_nodes: list) -> None:
    """Phase 1: sync all regular nodes via Ansible batches.

    Helper for _run_fleet_sync_job (#1707 refactor).
    """
    batch_size = job.batch_size
    for i in range(0, len(regular_nodes), batch_size):
        batch = regular_nodes[i : i + batch_size]

        tasks = []
        for node_state in batch:
            node_state.status = "syncing"
            node_state.started_at = datetime.now(timezone.utc)
            await _update_node_state_db(
                job.job_id,
                node_state.node_id,
                status="syncing",
                started_at=node_state.started_at,
            )
            task = asyncio.create_task(_sync_single_node(executor, node_state, job.restart, job.job_id))
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)
        await _update_job_status_db(job.job_id)

        if job.strategy == "rolling" and i + batch_size < len(regular_nodes):
            await asyncio.sleep(5)


async def _sync_slm_self_node(executor, job: FleetSyncJob, slm_self_node: NodeSyncState) -> None:
    """Phase 2: sync SLM self-node LAST (#1209).

    Helper for _run_fleet_sync_job. Persists final status to DB before
    the self-sync restart kills this process (#1707).
    """
    slm_self_node.status = "syncing"
    slm_self_node.started_at = datetime.now(timezone.utc)
    await _update_node_state_db(
        job.job_id,
        slm_self_node.node_id,
        status="syncing",
        started_at=slm_self_node.started_at,
    )

    if job.restart:
        logger.info(
            "Fleet sync %s: starting SLM self-sync for %s",
            job.job_id,
            slm_self_node.node_id,
        )
        # Persist final status BEFORE self-sync restart kills
        # this process (#1707).
        failed_count = sum(1 for n in job.nodes.values() if n.status == "failed")
        pre_status = "failed" if failed_count == len(job.nodes) else "completed"
        await _update_node_state_db(
            job.job_id,
            slm_self_node.node_id,
            status="success",
            completed_at=datetime.now(timezone.utc),
        )
        await _update_job_status_db(job.job_id, status=pre_status, completed_at=datetime.now(timezone.utc))
        # Fire-and-forget — restart kills this process,
        # but all nodes are already done and persisted.
        # Detect topology: local vs remote code source (#9195)
        from services.database import db_service

        conn_info = await _fetch_code_source_connection_info(db_service)
        if conn_info:
            source_ip, _, _ = conn_info
            from autobot_shared.network_utils import is_local_ip

            is_local_source = is_local_ip(source_ip)
            if is_local_source:
                await _ansible_self_update(slm_self_node.node_id)
            else:
                await _sync_slm_from_code_source(slm_self_node.node_id)
        else:
            # No code source — fall back to Ansible
            await _ansible_self_update(slm_self_node.node_id)

        slm_self_node.status = "success"
        slm_self_node.completed_at = datetime.now(timezone.utc)
    else:
        await _sync_single_node(executor, slm_self_node, restart=False, job_id=job.job_id)


async def _run_fleet_sync_job(job: FleetSyncJob) -> None:
    """Background task to execute fleet sync job using Ansible playbooks.

    Processes nodes according to the specified strategy and batch size.
    Issue #1209: SLM self-node synced LAST (restart kills process).
    Issue #1707: All state persisted to DB for restart survival.
    """
    executor = get_playbook_executor()
    job.status = "running"
    await _update_job_status_db(job.job_id, status="running")

    # Separate SLM self-node from regular nodes (#1209)
    slm_own_ip = urlparse(settings.external_url).hostname or ""
    regular_nodes: list[NodeSyncState] = []
    slm_self_node: NodeSyncState | None = None

    for ns in job.nodes.values():
        if slm_own_ip and ns.ip_address == slm_own_ip:
            slm_self_node = ns
        else:
            regular_nodes.append(ns)

    if slm_self_node:
        logger.info(
            "Fleet sync %s: %s is SLM self-node — will sync last",
            job.job_id,
            slm_self_node.node_id,
        )

    failure_reason: str | None = None
    try:
        await _sync_regular_nodes(executor, job, regular_nodes)

        if slm_self_node:
            await _sync_slm_self_node(executor, job, slm_self_node)

        failed_count = sum(1 for n in job.nodes.values() if n.status == "failed")
        job.status = "failed" if failed_count == len(job.nodes) else "completed"

    except Exception as e:
        logger.error("Fleet sync job %s failed: %s", job.job_id, e)
        job.status = "failed"
        failure_reason = str(e)

    job.completed_at = datetime.now(timezone.utc)
    await _update_job_status_db(
        job.job_id,
        status=job.status,
        completed_at=job.completed_at,
        failure_reason=failure_reason,
    )
    _running_tasks.pop(job.job_id, None)  # Prevent memory leak (#1928)
    logger.info(
        "Fleet sync job %s completed: %d/%d successful",
        job.job_id,
        sum(1 for n in job.nodes.values() if n.status == "success"),
        len(job.nodes),
    )


async def _sync_single_node(
    executor,
    node_state: NodeSyncState,
    restart: bool,
    job_id: str | None = None,
) -> None:
    """Sync a single node using Ansible playbook and update its state.

    Issue #1209: Also updates node version in DB on success so the
    code-sync GUI reflects the correct status.
    Issue #1707: Persists node state to DB for restart survival.
    """
    try:
        # Build playbook parameters
        # Use node_id (maps to slm_node_id in Ansible inventory) not hostname (#921)
        # Issue #1091: Include localhost so Play 0 (archive build) runs
        limit = ["localhost", node_state.node_id]
        tags = []
        if not restart:
            tags.append("!restart")  # Skip restart tasks

        # Execute update playbook
        result = await executor.execute_playbook(
            playbook_name="update-all-nodes.yml",
            limit=limit,
            tags=tags if tags else None,
        )

        if result["success"]:
            node_state.status = "success"
            node_state.message = result["output"][:500]
            # Update node version in DB (#1209)
            await _update_fleet_node_version(node_state.node_id)
        else:
            node_state.status = "failed"
            node_state.message = f"Playbook failed: {result['output'][:500]}"

        node_state.completed_at = datetime.now(timezone.utc)

    except Exception as e:
        node_state.status = "failed"
        node_state.message = "Operation failed"
        node_state.completed_at = datetime.now(timezone.utc)
        logger.error("Node sync failed for %s: %s", node_state.node_id, e)

    # Persist node state to DB (#1707)
    if job_id:
        await _update_node_state_db(
            job_id,
            node_state.node_id,
            status=node_state.status,
            message=node_state.message,
            completed_at=node_state.completed_at,
        )


async def _update_fleet_node_version(node_id: str) -> None:
    """Update a node's code_version in DB after successful fleet sync.

    Issue #1209: The fleet sync path (_sync_single_node) was not updating
    the DB, so nodes stayed 'outdated' even after successful Ansible runs.
    """
    from models.database import Node as NodeModel
    from services.database import db_service

    git_tracker = get_git_tracker()
    current_commit = await git_tracker.get_local_commit()
    if not current_commit:
        logger.warning("Fleet sync: cannot determine commit for %s", node_id)
        return

    try:
        async with db_service.session() as db:
            result = await db.execute(select(NodeModel).where(NodeModel.node_id == node_id))
            node = result.scalar_one_or_none()
            if node:
                node.code_version = current_commit
                node.code_status = CodeStatus.UP_TO_DATE.value
                logger.info(
                    "Fleet sync: marked %s as up-to-date at %s",
                    node_id,
                    current_commit[:12],
                )
    except Exception as db_err:
        logger.warning("Fleet sync: could not update %s version: %s", node_id, db_err)


class MarkSyncedRequest(BaseModel):
    """Request to mark a node as synced without running rsync."""

    version: str | None = None  # commit hash; defaults to slm_agent_latest_commit


class MarkSyncedResponse(BaseModel):
    """Response for mark-synced endpoint."""

    success: bool
    node_id: str
    version: str


@router.post("/nodes/{node_id}/mark-synced", response_model=MarkSyncedResponse)
async def mark_node_synced(
    node_id: str,
    request: MarkSyncedRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> MarkSyncedResponse:
    """Mark a node as up-to-date without triggering rsync.

    Called by Ansible after it has synced code to a node externally,
    so the SLM DB reflects the actual state of the fleet.
    """
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = node_result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    version = request.version
    if not version:
        setting_result = await db.execute(select(Setting).where(Setting.key == "slm_agent_latest_commit"))
        setting = setting_result.scalar_one_or_none()
        version = setting.value if setting else ""

    node.code_version = version
    node.code_status = CodeStatus.UP_TO_DATE.value
    await db.commit()

    logger.info("Marked node %s as synced at %s", node_id, version[:12])
    return MarkSyncedResponse(success=True, node_id=node_id, version=version)


def _build_fleet_sync_job_from_nodes(nodes: List[Node], request: FleetSyncRequest) -> FleetSyncJob:
    """Helper for sync_fleet. Ref: #1088.

    Construct a FleetSyncJob with one NodeSyncState per node.
    """
    job_id = str(uuid.uuid4())[:16]
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
    return job


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
    # Lock covers check-through-persist to prevent TOCTOU race (#1937)
    async with fleet_sync_lock:
        await assert_no_running_sync(db)

        # Get target nodes
        if request.node_ids:
            result = await db.execute(select(Node).where(Node.node_id.in_(request.node_ids)))
        else:
            result = await db.execute(select(Node).where(Node.code_status == CodeStatus.OUTDATED.value))

        nodes = result.scalars().all()

        if not nodes:
            return FleetSyncResponse(
                success=True,
                message="No nodes to sync",
                job_id="",
                nodes_queued=0,
            )

        # Create job with node states and persist to DB (#1707)
        job = _build_fleet_sync_job_from_nodes(nodes, request)
        await _persist_fleet_sync_job(job)

    if request.strategy != "manual":
        task = asyncio.create_task(_run_fleet_sync_job(job))
        _running_tasks[job.job_id] = task

    logger.info("Fleet sync job %s queued for %d nodes", job.job_id, len(nodes))

    return FleetSyncResponse(
        success=True,
        message=f"Sync queued for {len(nodes)} node(s)",
        job_id=job.job_id,
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
    Reads from DB so results survive service restarts (#1707).
    """
    job_status = await _load_job_status_from_db(job_id)

    if not job_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return job_status


@router.get("/fleet/jobs", response_model=List[FleetSyncJobStatus])
async def list_fleet_sync_jobs(
    _: Annotated[dict, Depends(get_current_user)],
    limit: int = 10,
) -> List[FleetSyncJobStatus]:
    """
    List recent fleet sync jobs (Issue #741 Phase 8).

    Reads from DB so results survive service restarts (#1707).
    """
    return await _list_jobs_from_db(limit=limit)


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
    setting_result = await db.execute(select(Setting).where(Setting.key == "slm_agent_latest_commit"))
    setting = setting_result.scalar_one_or_none()

    if setting:
        setting.value = commit
    else:
        setting = Setting(
            key="slm_agent_latest_commit",
            value=commit,
        )
        db.add(setting)


async def _mark_outdated_nodes(db: AsyncSession, node_id: str, commit: str) -> List[Node]:
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


async def _broadcast_code_version_update(notification: CodeVersionNotification, outdated_count: int) -> None:
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
                    "timestamp": (notification.timestamp.isoformat() if notification.timestamp else None),
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

    base = base or datetime.now(timezone.utc)
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
    result = await db.execute(select(UpdateSchedule).order_by(UpdateSchedule.created_at.desc()))
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
    result = await db.execute(select(UpdateSchedule).where(UpdateSchedule.id == schedule_id))
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
    result = await db.execute(select(UpdateSchedule).where(UpdateSchedule.id == schedule_id))
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
    result = await db.execute(select(UpdateSchedule).where(UpdateSchedule.id == schedule_id))
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


async def _get_schedule_target_nodes(db: AsyncSession, schedule: UpdateSchedule) -> List[Node]:
    """
    Get target nodes based on schedule configuration.

    Helper for run_schedule (Issue #665).
    """
    if schedule.target_type == "all":
        nodes_result = await db.execute(select(Node).where(Node.code_status == CodeStatus.OUTDATED.value))
    elif schedule.target_type == "specific" and schedule.target_nodes:
        nodes_result = await db.execute(select(Node).where(Node.node_id.in_(schedule.target_nodes)))
    else:
        nodes_result = await db.execute(select(Node).where(Node.code_status == CodeStatus.OUTDATED.value))

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
    result = await db.execute(select(UpdateSchedule).where(UpdateSchedule.id == schedule_id))
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

    # Guard: prevent overlapping fleet sync jobs (#1979)
    async with fleet_sync_lock:
        await assert_no_running_sync(db)

        job = _create_fleet_sync_job(nodes, schedule)
        await _persist_fleet_sync_job(job)
        task = asyncio.create_task(_run_fleet_sync_job(job))
        _running_tasks[job.job_id] = task

    # Update schedule last_run
    schedule.last_run = datetime.now(timezone.utc)
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
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Pull code from code-source to SLM cache (Issue #779).

    Fetches the latest code from the designated code-source node
    and caches it locally for distribution to fleet nodes.

    Issue #1209: Also updates slm_agent_latest_commit so the GUI
    "Latest Version" header matches immediately after pulling.
    """
    orchestrator = get_sync_orchestrator()
    success, message, commit = await orchestrator.pull_from_source()

    if success and commit:
        await _update_version_setting(db, commit)
        await db.commit()

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
    result = await db.execute(select(CodeSource).where(CodeSource.is_active == True))  # noqa: E712
    source = result.scalar_one_or_none()

    if not source or not source.last_known_commit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No code version available. Pull from source first.",
        )

    return source.last_known_commit


async def _get_role_nodes(db: AsyncSession, role_name: str, node_ids: List[str] | None = None) -> List[NodeRole]:
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
        role_result = await db.execute(select(NodeRole).where(NodeRole.role_name == role_name))

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
    node_ids: List[str] | None = None,
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
    results, success_count = await _sync_nodes_for_role(orchestrator, node_roles, role_name, commit, restart)

    logger.info(
        "Role sync complete: %s - %d/%d successful",
        role_name,
        success_count,
        len(node_roles),
    )

    return {  # codeql[py/stack-trace-exposure]
        "success": success_count > 0,
        "message": f"Synced {success_count}/{len(node_roles)} nodes",
        "role_name": role_name,
        "commit": commit,
        "nodes_synced": success_count,
        "results": results,
    }


# =============================================================================
# One-Click Full-Pipeline Update (Issue #9971)
# =============================================================================

import json as _json  # noqa: E402

_UPDATE_ALL_RESUME_KEY = "slm_update_all_resume"
_DEPS_FILES = ["requirements.txt", "package-lock.json"]
_RESUME_PLAN_VERSION = 1
_RESUME_PLAN_TTL_SECONDS = 7200  # 2 hours (C2-b)

# Known secret extra-var key prefixes — values are redacted from log lines (Security).
_SECRET_EXTRA_VAR_PREFIXES = (
    "password",
    "secret",
    "token",
    "key",
    "pass",
    "credential",
    "cert",
    "private",
)

# In-memory slot for the active orchestration job (at most one at a time).
# Holds the last job even after it completes so GET /status keeps returning it (C3-a).
_active_update_all: Dict[str, Any] = {}

# Module-level references to tasks created by the update-all pipeline (M3).
_update_all_task: Optional[asyncio.Task] = None
_resume_task: Optional[asyncio.Task] = None


class _StageStatus:
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CURRENT = "current"  # C4: already at target commit


class UpdateAllStage(BaseModel):
    """State of one pipeline stage."""

    name: str  # github_fetch | code_source_pull | slm_self_update | fleet_nodes
    status: str = _StageStatus.PENDING
    message: Optional[str] = None
    sha: Optional[str] = None  # git SHA relevant to this stage
    deps_changed: bool = False
    log_lines: List[str] = []
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class UpdateAllJob(BaseModel):
    """Full orchestration job state for update-all."""

    job_id: str
    status: str = "pending"  # pending | running | completed | failed | already_current | partial
    stages: List[UpdateAllStage] = []
    total_fleet_nodes: int = 0
    completed_fleet_nodes: int = 0
    failed_fleet_nodes: int = 0
    skipped_fleet_nodes: int = 0  # non-operational nodes skipped (#11511)
    created_at: str = ""
    completed_at: Optional[str] = None
    failure_reason: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_sha(sha: Optional[str]) -> Optional[str]:
    return sha[:12] if sha else None


def _make_stage(name: str) -> UpdateAllStage:
    return UpdateAllStage(name=name)


def _mask_secret_extra_vars(extra_vars: Dict[str, str]) -> Dict[str, str]:
    """Return a copy of extra_vars with secret values replaced by '***' (Security)."""
    masked: Dict[str, str] = {}
    for k, v in extra_vars.items():
        lower_k = k.lower()
        if any(lower_k.startswith(pfx) or pfx in lower_k for pfx in _SECRET_EXTRA_VAR_PREFIXES):
            masked[k] = "***"
        else:
            masked[k] = v
    return masked


async def _check_deps_changed(code_source_dir: str, deployed_dir: str, dep_file: str) -> bool:
    """Compare a dependency file between code_source and deployed directories.

    Returns True if the file differs (by content hash) or exists only in one location.
    """
    import hashlib

    def _hash_file(path: str) -> Optional[str]:
        p = Path(path)
        if not p.exists():
            return None
        try:
            return hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            return None

    loop = asyncio.get_running_loop()
    src_path = f"{code_source_dir}/{dep_file}"
    dep_path = f"{deployed_dir}/{dep_file}"
    src_hash, dep_hash = await asyncio.gather(
        loop.run_in_executor(None, _hash_file, src_path),
        loop.run_in_executor(None, _hash_file, dep_path),
    )
    if src_hash is None and dep_hash is None:
        return False
    return src_hash != dep_hash


async def _compute_deps_changed(component: str) -> bool:
    """Return True if any watched dependency file differs for a component."""
    try:
        source_dir = get_default_source_dir(component)
        deployed_dir = get_default_deployed_dir(component)
    except ValueError:
        return False
    except Exception:
        return False
    for dep_file in _DEPS_FILES:
        if await _check_deps_changed(source_dir, deployed_dir, dep_file):
            return True
    return False


def _get_update_all_job() -> Optional[UpdateAllJob]:
    """Return the last known orchestration job (running or terminal) or None (C3-a)."""
    raw = _active_update_all.get("job")
    if raw is None:
        return None
    if isinstance(raw, UpdateAllJob):
        return raw
    return None


def _set_update_all_job(job: UpdateAllJob) -> None:
    _active_update_all["job"] = job


def _clear_update_all_job() -> None:
    # Do NOT pop — keep the last job for GET /status (C3-a).
    # Caller sets job.status to terminal before this is called.
    pass


def _get_stage(job: UpdateAllJob, name: str) -> UpdateAllStage:
    for s in job.stages:
        if s.name == name:
            return s
    raise KeyError(f"Stage {name} not in job")


def _stage_log(stage: UpdateAllStage, msg: str) -> None:
    stage.log_lines.append(msg)
    if len(stage.log_lines) > 200:
        stage.log_lines = stage.log_lines[-200:]
    logger.info("[update-all:%s] %s", stage.name, msg)


async def _persist_resume_plan(
    job: UpdateAllJob,
    remaining_node_ids: List[str],
    target_commit: str,
) -> None:
    """Write resume plan to Settings so a fresh SLM process can continue fleet stage.

    Includes target_commit (C1) and version sentinel (M2).
    Always called even when remaining_node_ids is empty (C5).
    """
    from services.database import db_service

    plan = {
        "version": _RESUME_PLAN_VERSION,  # M2
        "job_id": job.job_id,
        "remaining_node_ids": remaining_node_ids,
        "target_commit": target_commit,  # C1
        "created_at": job.created_at,
    }
    async with db_service.session() as db:
        result = await db.execute(select(Setting).where(Setting.key == _UPDATE_ALL_RESUME_KEY))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = _json.dumps(plan)
        else:
            db.add(Setting(key=_UPDATE_ALL_RESUME_KEY, value=_json.dumps(plan)))
        await db.commit()
    logger.info(
        "update-all: persisted resume plan for %d fleet nodes (target=%s)",
        len(remaining_node_ids),
        _short_sha(target_commit),
    )


async def _clear_resume_plan() -> None:
    """Remove resume plan from Settings after fleet stage completes."""
    from services.database import db_service

    try:
        async with db_service.session() as db:
            result = await db.execute(select(Setting).where(Setting.key == _UPDATE_ALL_RESUME_KEY))
            setting = result.scalar_one_or_none()
            if setting:
                await db.delete(setting)
                await db.commit()
    except Exception as exc:
        logger.warning("update-all: failed to clear resume plan: %s", exc)


async def _get_slm_deployed_commit() -> Optional[str]:
    """Return the commit hash currently deployed on this SLM instance (C1).

    Reads from git_tracker (git rev-parse HEAD) with DB fallback — the same
    source used by the /code-sync/status endpoint's local_version field.
    """
    git_tracker_inst = get_git_tracker()
    return await git_tracker_inst.get_local_commit()


async def _run_github_stage(job: UpdateAllJob, db_service_ref) -> Optional[str]:
    """Stage 1: git fetch + persist slm_agent_latest_commit.

    Returns the remote commit SHA on success, None on failure.
    Sets job.status='failed' and returns None on any error.
    """
    stage = _get_stage(job, "github_fetch")
    stage.status = _StageStatus.RUNNING
    stage.started_at = _now_iso()
    _stage_log(stage, "Fetching latest commit from GitHub ...")
    try:
        async with db_service_ref.session() as db:
            tracker = await _get_tracker_for_db(db)
            result = await tracker.check_for_updates(fetch=True)
            remote_commit = result.get("remote_commit")
            if not remote_commit:
                stage.status = _StageStatus.FAILED
                stage.message = "git fetch returned no remote commit"
                stage.completed_at = _now_iso()
                job.status = "failed"
                job.failure_reason = stage.message
                job.completed_at = _now_iso()
                return None
            setting_result = await db.execute(select(Setting).where(Setting.key == "slm_agent_latest_commit"))
            setting = setting_result.scalar_one_or_none()
            if setting:
                setting.value = remote_commit
            else:
                db.add(Setting(key="slm_agent_latest_commit", value=remote_commit))
            await db.commit()
        stage.sha = _short_sha(remote_commit)
        stage.status = _StageStatus.SUCCESS
        stage.message = f"Latest commit: {_short_sha(remote_commit)}"
        stage.completed_at = _now_iso()
        _stage_log(stage, f"Fetched remote commit {_short_sha(remote_commit)}")
        return remote_commit
    except Exception as exc:
        stage.status = _StageStatus.FAILED
        stage.message = str(exc)[:300]
        stage.completed_at = _now_iso()
        job.status = "failed"
        job.failure_reason = f"GitHub fetch failed: {exc}"
        job.completed_at = _now_iso()
        return None


async def _run_pull_stage(job: UpdateAllJob, db_service_ref) -> Optional[str]:
    """Stage 2: pull code_source and return pulled commit SHA (or None on failure).

    Sets job.status='failed' and returns None on any error.
    """
    stage = _get_stage(job, "code_source_pull")
    stage.status = _StageStatus.RUNNING
    stage.started_at = _now_iso()
    _stage_log(stage, "Pulling code_source from source node ...")
    try:
        slm_deps_before = await _compute_deps_changed("autobot-slm-backend")
        orchestrator = get_sync_orchestrator()
        success, message, commit = await orchestrator.pull_from_source()
        if not success:
            stage.status = _StageStatus.FAILED
            stage.message = message or "pull_from_source returned failure"
            stage.completed_at = _now_iso()
            job.status = "failed"
            job.failure_reason = f"code_source pull failed: {stage.message}"
            job.completed_at = _now_iso()
            return None
        stage.deps_changed = slm_deps_before or await _compute_deps_changed("autobot-slm-backend")
        stage.sha = _short_sha(commit)
        stage.status = _StageStatus.SUCCESS
        stage.message = message or f"Pulled {_short_sha(commit)}"
        stage.completed_at = _now_iso()
        _stage_log(stage, f"Pulled commit {_short_sha(commit)}, deps_changed={stage.deps_changed}")
        if commit:
            async with db_service_ref.session() as db:
                await _update_version_setting(db, commit)
                await db.commit()
        return commit
    except Exception as exc:
        stage.status = _StageStatus.FAILED
        stage.message = str(exc)[:300]
        stage.completed_at = _now_iso()
        job.status = "failed"
        job.failure_reason = f"code_source pull error: {exc}"
        job.completed_at = _now_iso()
        return None


# Managed application services that run co-located on the SLM-Manager node in a
# single-box install. update-all's slm_self_update stage covers only the SLM
# control plane and the fleet stage skips the self-node, so these were updated by
# NEITHER stage whenever the SLM commit was already current — the one-click update
# reported success while autobot-backend/-frontend stayed stale (#11605). They are
# resolved via the SAME per-component drift/resolve path as the manual
# "Resync from Source" button (rsync + _run_post_sync_steps).
_COLOCATED_MANAGED_COMPONENTS: Tuple[str, ...] = ("autobot-backend", "autobot-frontend")


async def _component_has_file_drift(component: str) -> bool:
    """Return True when *component* is deployed on this host AND drifts from code_source.

    A missing deployed dir means the component is not co-located here (e.g. a pure
    SLM control-plane box) — treated as "no drift" so we never try to resolve a
    component that does not run on this node.
    """
    try:
        source_dir = get_default_source_dir(component)
    except ValueError:
        return False
    deployed_dir = get_default_deployed_dir(component)
    if not Path(deployed_dir).exists():
        return False
    report = await asyncio.get_running_loop().run_in_executor(
        None,
        functools.partial(build_drift_report, source_dir, deployed_dir, component),
    )
    return len(report.get("drifted_files", [])) > 0


async def _resolve_colocated_managed_services(stage: UpdateAllStage) -> None:
    """Resolve co-located managed services on the SLM-Manager node (#11605).

    Runs the per-component drift/resolve path (rsync + _run_post_sync_steps, which
    handles pip/build/migrate/restart + health + rollback) for each co-located
    managed component that (a) is actually deployed on this host and (b) has file
    drift.

    #11611: autobot_shared-first ordering is enforced HERE explicitly — this loop
    is a THIRD deploy site (alongside resolve_drift and _run_component_resolve_job).
    _run_post_sync_steps only recreates the autobot_shared SYMLINK; it does NOT
    sync the shared tree CONTENT, so without an explicit _ensure_autobot_shared_synced
    call this path could rsync + restart autobot-backend onto a STALE autobot_shared
    and crash-loop it (the exact #11611 failure, on the one-click co-located update).
    So we call _ensure_autobot_shared_synced BEFORE the component rsync and skip the
    component (fail-safe, no restart) when the shared tree cannot be synced.

    Per-component failures are logged and do not abort the pipeline.
    """
    for component in _COLOCATED_MANAGED_COMPONENTS:
        if component not in ALLOWED_COMPONENTS:
            continue
        try:
            if not await _component_has_file_drift(component):
                _stage_log(stage, f"co-located {component}: no drift — skipped (#11605)")
                continue
            _stage_log(stage, f"co-located {component}: drift detected — resolving (#11605)")
            # #11611: sync autobot_shared BEFORE this component's rsync + restart so
            # a newly-added `from autobot_shared.X` import resolves at startup. Skip
            # the component (no restart) if the shared tree cannot be synced.
            shared_ok, shared_msg = await _ensure_autobot_shared_synced(component)
            if not shared_ok:
                _stage_log(stage, f"co-located {component}: {shared_msg} — skipped (#11611)")
                continue
            source_dir = get_default_source_dir(component)
            deployed_dir = get_default_deployed_dir(component)
            source_root = str(Path(source_dir).parent)
            excludes_map = {comp: excl for comp, excl in _SLM_COMPONENTS}
            excludes = excludes_map.get(component, [])
            ok, msg = await _rsync_component_local(source_root, component, excludes)
            if not ok:
                _stage_log(stage, f"co-located {component}: rsync failed: {msg} (#11605)")
                continue
            _, _post_steps, pip_ok = await _run_post_sync_steps(component, source_dir, deployed_dir)
            _stage_log(stage, f"co-located {component}: resolved (ok={pip_ok}) (#11605)")
        except Exception as exc:
            _stage_log(stage, f"co-located {component}: resolve error: {exc} (#11605)")


async def _run_slm_stage(
    job: UpdateAllJob,
    remote_commit: str,
    outdated_node_ids: List[str],
    db_service_ref,
) -> bool:
    """Stage 3: SLM self-update (fire-and-forget before restart).

    C4: Skip when deployed commit already equals remote_commit.
    C5: Always persist resume plan when this stage fires.
    Returns True if the stage fired (caller must return immediately).
    Returns False if the stage was skipped (no SLM node or already current).
    Sets job.status='failed' on error.
    """
    stage = _get_stage(job, "slm_self_update")
    stage.status = _StageStatus.RUNNING
    stage.started_at = _now_iso()
    _stage_log(stage, "Starting Ansible SLM self-update ...")
    try:
        slm_own_ip = urlparse(settings.external_url).hostname or ""
        async with db_service_ref.session() as db:
            slm_result = await db.execute(select(Node).where(Node.ip_address == slm_own_ip))
            slm_node = slm_result.scalar_one_or_none()

        if slm_node is None:
            stage.status = _StageStatus.SKIPPED
            stage.message = "SLM node not found in DB — skipping self-update"
            stage.completed_at = _now_iso()
            _stage_log(stage, stage.message)
            return False

        # C4: compare deployed commit to target
        deployed_commit = await _get_slm_deployed_commit()
        if deployed_commit and deployed_commit == remote_commit:
            stage.status = _StageStatus.CURRENT
            stage.sha = _short_sha(remote_commit)
            stage.message = f"SLM already at {_short_sha(remote_commit)} — no restart needed"
            # #11605: the SLM control plane is current, so no Ansible self-update
            # fires — but co-located managed services (autobot-backend/-frontend)
            # can still carry file drift that neither this stage nor the self-node-
            # skipping fleet stage would otherwise resolve. Resolve them here via
            # the per-component drift/resolve path so the one-click update actually
            # brings the whole co-located box current.
            await _resolve_colocated_managed_services(stage)
            stage.completed_at = _now_iso()
            _stage_log(stage, stage.message)
            return False

        stage.deps_changed = await _compute_deps_changed("autobot-slm-backend")
        stage.sha = _short_sha(remote_commit)

        # C5: Always persist resume plan before firing (even empty remaining list)
        await _persist_resume_plan(job, outdated_node_ids, remote_commit)

        _stage_log(stage, f"Firing Ansible self-update for {slm_node.node_id} (fire-and-forget)")
        stage.message = "Ansible SLM self-update queued; service will restart"
        asyncio.create_task(_ansible_self_update(slm_node.node_id))
        return True

    except Exception as exc:
        stage.status = _StageStatus.FAILED
        stage.message = str(exc)[:300]
        stage.completed_at = _now_iso()
        job.status = "failed"
        job.failure_reason = f"SLM self-update error: {exc}"
        job.completed_at = _now_iso()
        await _clear_resume_plan()
        return False


def _fail_fleet_stage(
    job: UpdateAllJob,
    stage: UpdateAllStage,
    reason: str,
) -> None:
    """Mark fleet stage and job as failed with a common reason string."""
    stage.status = _StageStatus.FAILED
    stage.message = reason[:300]
    stage.completed_at = _now_iso()
    job.status = "failed"
    job.failure_reason = reason[:300]
    job.completed_at = _now_iso()


_NON_OPERATIONAL_STATUSES = frozenset({"degraded", "offline", "error", "pending", "enrolling", "decommissioned"})


def _is_node_operational(node: Node) -> bool:
    """Return True only when a node is in a state where a deploy is safe (#11511).

    Nodes that are degraded, have never sent a heartbeat, or whose status is
    anything other than online/maintenance are not targeted — attempting an
    Ansible deploy against them will always fail and should not affect the
    overall job result.
    """
    if node.last_heartbeat is None:
        return False
    return node.status not in _NON_OPERATIONAL_STATUSES


def _extract_ansible_fatal(output: str) -> str:
    """Return the first meaningful ansible error line from playbook output (#11511).

    Filters out [DEPRECATION WARNING] / [WARNING] noise so the reported
    failure message reflects the real fatal: / FAILED! / msg: line rather
    than an unrelated deprecation notice.  Falls back to the tail of the
    output when no fatal line is found.
    """
    fatal_keywords = ("fatal:", "FAILED!", "msg:", "ERROR!")
    skip_prefixes = ("[DEPRECATION WARNING]", "[WARNING]", "DEPRECATION WARNING")
    for line in output.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(pfx) for pfx in skip_prefixes):
            continue
        if any(kw in stripped for kw in fatal_keywords):
            return stripped[:300]
    return output.strip()[-300:] if output.strip() else "playbook failed (no output)"


async def _sync_fleet_node(
    executor,
    node_id: str,
    job: UpdateAllJob,
    stage: UpdateAllStage,
    slm_own_ip: str,
) -> bool:
    """Sync one fleet node. Returns True to continue loop, False to halt.

    M1: node-not-found halts (returns False, caller clears plan).
    Non-operational nodes (degraded/no-heartbeat) are skipped without
    failing the job (#11511).
    """
    from services.database import db_service

    async with db_service.session() as db:
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = result.scalar_one_or_none()

    if node is None:
        # M1: node-not-found halts the stage
        job.failed_fleet_nodes += 1
        _stage_log(stage, f"Node {node_id} not found in DB — aborting fleet stage")
        _fail_fleet_stage(job, stage, f"Fleet node {node_id} not found in DB")
        return False

    if slm_own_ip and node.ip_address == slm_own_ip:
        _stage_log(stage, f"Node {node_id} is SLM self-node — already handled, skipping")
        job.completed_fleet_nodes += 1
        return True

    # Skip non-operational nodes rather than attempting a deploy that will fail (#11511).
    if not _is_node_operational(node):
        reason = (
            f"status={node.status}, last_heartbeat={'none' if node.last_heartbeat is None else node.last_heartbeat}"
        )
        _stage_log(stage, f"Node {node_id} ({node.hostname}) skipped — not operational ({reason})")
        job.skipped_fleet_nodes += 1
        return True

    playbook_result = await executor.execute_playbook(
        playbook_name="update-all-nodes.yml",
        limit=["localhost", node_id],
    )
    if playbook_result["success"]:
        await _update_fleet_node_version(node_id)
        job.completed_fleet_nodes += 1
        _stage_log(stage, f"Node {node_id} updated successfully")
        return True

    error_msg = _extract_ansible_fatal(playbook_result["output"])
    job.failed_fleet_nodes += 1
    _stage_log(stage, f"Node {node_id} FAILED: {error_msg}")
    _fail_fleet_stage(job, stage, f"Fleet node {node_id} playbook failed: {error_msg}")
    return False


async def _run_fleet_stage(job: UpdateAllJob, node_ids: List[str]) -> None:
    """Execute stage 4: sequential full update of each outdated fleet node.

    Runs nodes SEQUENTIALLY (playbook executor is a singleton resource).
    Marks job completed/failed/partial when done. Clears the resume plan.
    M1: node-not-found is treated as stage failure (halts pipeline).
    Non-operational nodes are skipped and counted in skipped_fleet_nodes
    without failing the job (#11511).
    """
    stage = _get_stage(job, "fleet_nodes")
    stage.status = _StageStatus.RUNNING
    stage.started_at = _now_iso()
    job.total_fleet_nodes = len(node_ids)
    job.completed_fleet_nodes = 0
    job.failed_fleet_nodes = 0
    job.skipped_fleet_nodes = 0

    executor = get_playbook_executor()
    slm_own_ip = urlparse(settings.external_url).hostname or ""

    for node_id in node_ids:
        _stage_log(stage, f"Syncing fleet node {node_id} ...")
        try:
            cont = await _sync_fleet_node(executor, node_id, job, stage, slm_own_ip)
        except Exception as exc:
            job.failed_fleet_nodes += 1
            _stage_log(stage, f"Node {node_id} error: {exc}")
            _fail_fleet_stage(job, stage, f"Fleet node {node_id} error: {exc}")
            cont = False
        if not cont:
            await _clear_resume_plan()
            return

    skipped = job.skipped_fleet_nodes
    summary = f"Updated {job.completed_fleet_nodes}/{job.total_fleet_nodes} nodes"
    if skipped:
        summary += f" ({skipped} skipped — not operational)"

    stage.status = _StageStatus.SUCCESS
    stage.message = summary
    stage.completed_at = _now_iso()
    job.status = "partial" if skipped else "completed"
    job.completed_at = _now_iso()
    _stage_log(stage, f"Fleet stage complete: {summary}")
    await _clear_resume_plan()


async def _collect_outdated_node_ids(job: UpdateAllJob, remote_commit: str, db_service_ref) -> List[str]:
    """Query DB for nodes that need updating and annotate fleet stage.

    Uses code_version != remote_commit as the currency signal (#9996-B).
    code_status is set by heartbeat and lags behind stage-1/2 updates to
    slm_agent_latest_commit — relying on it here causes nodes that are truly
    outdated to appear current (heartbeat hasn't fired since the new commit
    was fetched).

    Also explicitly includes the co-located self-node when its code_version
    differs from remote_commit (#9996-A).  The heartbeat-driven code_status
    on the SLM host may still show UP_TO_DATE because slm_agent_latest_commit
    was just updated in stage 1 and the heartbeat cycle hasn't re-evaluated
    the node.  _sync_fleet_node already skips the self-node during fleet
    execution (marks it completed), so including it here only fixes the
    currency count — it does not cause a double-update.
    """
    try:
        slm_own_ip = urlparse(settings.external_url).hostname or ""
        seen_ids: set = set()
        outdated_node_ids: List[str] = []

        async with db_service_ref.session() as db:
            # B: use version comparison — reliable immediately after stages 1-2
            nodes_result = await db.execute(
                select(Node)
                .where((Node.code_version != remote_commit) | Node.code_version.is_(None))
                .order_by(Node.hostname)
            )
            version_outdated = nodes_result.scalars().all()

            for n in version_outdated:
                seen_ids.add(n.node_id)
                outdated_node_ids.append(n.node_id)

            # A: self-node inclusion — ensure the co-located SLM host is counted
            # even when heartbeat hasn't yet updated its code_status to OUTDATED.
            if slm_own_ip:
                slm_result = await db.execute(select(Node).where(Node.ip_address == slm_own_ip))
                slm_node = slm_result.scalar_one_or_none()
                if slm_node and slm_node.node_id not in seen_ids:
                    # Self-node is not captured by version comparison (e.g. no
                    # code_version recorded yet); include it so the pipeline
                    # does not report "everything current" prematurely.
                    logger.info(
                        "update-all: self-node %s not in version-outdated list "
                        "(code_version=%s vs remote=%s) — adding explicitly (#9996-A)",
                        slm_node.node_id,
                        _short_sha(slm_node.code_version),
                        _short_sha(remote_commit),
                    )
                    outdated_node_ids.append(slm_node.node_id)

        stage_fleet = _get_stage(job, "fleet_nodes")
        stage_fleet.sha = _short_sha(remote_commit)
        if outdated_node_ids:
            stage_fleet.deps_changed = await _compute_deps_changed("autobot-backend")
        _stage_log(
            _get_stage(job, "slm_self_update"),
            f"Collected {len(outdated_node_ids)} outdated fleet node(s)",
        )
        return outdated_node_ids
    except Exception as exc:
        logger.warning("update-all: could not collect outdated nodes: %s", exc)
        return []


async def _run_fleet_stage_or_already_current(
    job: UpdateAllJob,
    outdated_node_ids: List[str],
    remote_commit: str,
) -> None:
    """Stage 4 dispatch: run fleet updates or mark already_current (C4)."""
    if outdated_node_ids:
        await _run_fleet_stage(job, outdated_node_ids)
        return

    stage_fleet = _get_stage(job, "fleet_nodes")
    stage_fleet.status = _StageStatus.SKIPPED
    stage_fleet.message = "No outdated fleet nodes"
    stage_fleet.completed_at = _now_iso()

    # C4: already_current when SLM is also at target
    deployed = await _get_slm_deployed_commit()
    slm_stage = _get_stage(job, "slm_self_update")
    is_already_current = deployed == remote_commit or slm_stage.status in (_StageStatus.CURRENT, _StageStatus.SKIPPED)
    if is_already_current:
        job.status = "already_current"
        _stage_log(stage_fleet, "Everything already current — pipeline complete")
    else:
        job.status = "completed"
        _stage_log(stage_fleet, "No outdated nodes — pipeline complete")
    job.completed_at = _now_iso()


async def _run_update_all_orchestration(job: UpdateAllJob, db_service_ref) -> None:
    """Background task: run the 4-stage one-click update pipeline (M4).

    Stage order:
      1. github_fetch      — git fetch + update slm_agent_latest_commit setting
      2. code_source_pull  — pull code_source from the source node
      3. slm_self_update   — Ansible self-update of SLM (fire-and-forget before restart)
      4. fleet_nodes       — sequential Ansible playbook per outdated node

    C4: SLM stage skipped if already at target commit.
    C5: Resume plan always persisted before stage 3 fires (even empty fleet list).
    """
    job.status = "running"

    remote_commit = await _run_github_stage(job, db_service_ref)
    if remote_commit is None:
        return

    pulled_commit = await _run_pull_stage(job, db_service_ref)
    if pulled_commit is None:
        return

    outdated_node_ids = await _collect_outdated_node_ids(job, remote_commit, db_service_ref)

    slm_fired = await _run_slm_stage(job, remote_commit, outdated_node_ids, db_service_ref)
    if job.status == "failed":
        return
    if slm_fired:
        return  # process restarts; resume hook handles fleet stage

    await _run_fleet_stage_or_already_current(job, outdated_node_ids, remote_commit)


async def _read_and_validate_resume_plan() -> Optional[Dict[str, Any]]:
    """Read, version-check, and staleness-gate the resume plan.

    Returns the plan dict if valid, None if no plan or plan should be discarded.
    Clears the plan in Settings when it is discarded (M2, C2-b).
    """
    from services.database import db_service

    try:
        async with db_service.session() as db:
            result = await db.execute(select(Setting).where(Setting.key == _UPDATE_ALL_RESUME_KEY))
            setting = result.scalar_one_or_none()
            if not setting:
                return None
            plan = _json.loads(setting.value)
    except Exception as exc:
        logger.warning("update-all resume: could not read plan: %s", exc)
        return None

    # M2: version check
    if plan.get("version") != _RESUME_PLAN_VERSION:
        logger.warning(
            "update-all resume: unknown plan version %s (expected %d) — discarding",
            plan.get("version"),
            _RESUME_PLAN_VERSION,
        )
        await _clear_resume_plan()
        return None

    # C2-b: staleness gate
    plan_created_at_str = plan.get("created_at", "")
    if plan_created_at_str:
        try:
            plan_ts = datetime.fromisoformat(plan_created_at_str)
            if plan_ts.tzinfo is None:
                plan_ts = plan_ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - plan_ts).total_seconds()
            if age > _RESUME_PLAN_TTL_SECONDS:
                logger.warning(
                    "update-all resume: plan is %.0fs old (TTL=%ds) — discarding stale plan",
                    age,
                    _RESUME_PLAN_TTL_SECONDS,
                )
                await _clear_resume_plan()
                return None
        except (ValueError, TypeError) as exc:
            logger.warning("update-all resume: could not parse plan created_at: %s", exc)

    return plan


async def _resume_verify_slm_stage(job: UpdateAllJob, target_commit: Optional[str]) -> bool:
    """C1: Verify deployed commit == target_commit before touching the fleet.

    Returns True if verification passes (or no target_commit to check).
    Returns False and marks job failed if mismatch detected.
    """
    if not target_commit:
        return True
    deployed_commit = await _get_slm_deployed_commit()
    if deployed_commit == target_commit:
        return True
    err_msg = (
        f"SLM deployed commit {_short_sha(deployed_commit)} " f"!= target {_short_sha(target_commit)} — stage 3 failed"
    )
    logger.error("update-all resume: %s", err_msg)
    stage_slm = _get_stage(job, "slm_self_update")
    stage_slm.status = _StageStatus.FAILED
    stage_slm.message = err_msg
    stage_slm.completed_at = _now_iso()
    job.status = "failed"
    job.failure_reason = err_msg
    job.completed_at = _now_iso()
    await _clear_resume_plan()
    return False


async def _execute_resume(
    job: UpdateAllJob,
    target_commit: Optional[str],
    remaining: List[str],
) -> None:
    """C2-c: Inner resume execution — always clears plan on any exception.

    C1: verifies deployed commit; C2-c: try/except wraps everything.
    """
    global _resume_task
    try:
        if not await _resume_verify_slm_stage(job, target_commit):
            return

        stage_slm = _get_stage(job, "slm_self_update")
        stage_slm.status = _StageStatus.SUCCESS
        stage_slm.message = f"SLM restarted at {_short_sha(target_commit)}"
        stage_slm.sha = _short_sha(target_commit)
        stage_slm.completed_at = _now_iso()

        if not remaining:
            stage_fleet = _get_stage(job, "fleet_nodes")
            stage_fleet.status = _StageStatus.SKIPPED
            stage_fleet.message = "No fleet nodes to update"
            stage_fleet.completed_at = _now_iso()
            job.status = "completed"
            job.completed_at = _now_iso()
            await _clear_resume_plan()
            return

        await _run_fleet_stage(job, remaining)
    except Exception as exc:
        logger.error("update-all resume: unhandled error: %s", exc, exc_info=True)
        job.status = "failed"
        job.failure_reason = f"Resume error: {exc}"
        job.completed_at = _now_iso()
        await _clear_resume_plan()
    finally:
        _resume_task = None


async def resume_update_all_orchestration() -> None:
    """Called on SLM startup to continue a fleet stage interrupted by SLM restart.

    C1: Verifies the now-running SLM's deployed commit matches target_commit.
    C2-b: Discards stale plans (older than _RESUME_PLAN_TTL_SECONDS).
    C2-c: Wraps execution in try/except to always clear plan on failure.
    M2: Rejects unknown plan versions.
    """
    global _resume_task

    plan = await _read_and_validate_resume_plan()
    if plan is None:
        return

    target_commit: Optional[str] = plan.get("target_commit")
    remaining: List[str] = plan.get("remaining_node_ids", [])
    job_id: str = plan.get("job_id", str(uuid.uuid4())[:16])
    plan_created_at_val: str = plan.get("created_at", _now_iso())

    logger.info(
        "update-all resume: found plan job=%s target=%s fleet_nodes=%d",
        job_id,
        _short_sha(target_commit),
        len(remaining),
    )

    job = UpdateAllJob(
        job_id=job_id,
        status="running",
        created_at=plan_created_at_val,
        stages=[
            UpdateAllStage(name="github_fetch", status=_StageStatus.SUCCESS, message="completed before restart"),
            UpdateAllStage(name="code_source_pull", status=_StageStatus.SUCCESS, message="completed before restart"),
            UpdateAllStage(name="slm_self_update", status=_StageStatus.RUNNING, message="SLM restarting ..."),
            _make_stage("fleet_nodes"),
        ],
    )
    _set_update_all_job(job)
    _resume_task = asyncio.create_task(_execute_resume(job, target_commit, remaining))


async def _check_persisted_plan_exists() -> bool:
    """Return True if a resume plan is currently stored in Settings (C3-b)."""
    from services.database import db_service

    try:
        async with db_service.session() as db:
            result = await db.execute(select(Setting).where(Setting.key == _UPDATE_ALL_RESUME_KEY))
            return result.scalar_one_or_none() is not None
    except Exception:
        return False


@router.post("/update-all", status_code=202)
async def start_update_all(
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateAllJob:
    """Start the one-click full-pipeline update (#9971).

    Stages: GitHub fetch -> code_source pull -> SLM self-update -> fleet nodes.
    Returns 409 if an orchestration job is already running OR a persisted plan
    exists (self-update in flight) — prevents double-orchestration race (C3-b).
    Returns 202 Accepted with the initial job state (polling via GET /update-all/status).
    """
    global _update_all_task

    existing = _get_update_all_job()
    if existing and existing.status in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An update-all job is already running (job_id={existing.job_id})",
        )

    # C3-b: also block when a persisted resume plan is present (restart in flight)
    if await _check_persisted_plan_exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SLM self-update is in flight (persisted resume plan found) — wait for restart to complete",
        )

    job_id = str(uuid.uuid4())[:16]
    job = UpdateAllJob(
        job_id=job_id,
        status="pending",
        created_at=_now_iso(),
        stages=[
            _make_stage("github_fetch"),
            _make_stage("code_source_pull"),
            _make_stage("slm_self_update"),
            _make_stage("fleet_nodes"),
        ],
    )
    _set_update_all_job(job)

    from services.database import db_service as _db_svc

    async def _run() -> None:
        global _update_all_task
        try:
            await _run_update_all_orchestration(job, _db_svc)
        except Exception as exc:
            logger.error("update-all orchestration unhandled error: %s", exc, exc_info=True)
            job.status = "failed"
            job.failure_reason = str(exc)[:300]
            job.completed_at = _now_iso()
            await _clear_resume_plan()
        finally:
            _update_all_task = None

    _update_all_task = asyncio.create_task(_run())
    logger.info("update-all orchestration started: job %s", job_id)
    return job


@router.get("/update-all/status")
async def get_update_all_status(
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateAllJob:
    """Return status of the current or most-recently-completed update-all job (#9971).

    C3-a: Returns the last job even after it completes (terminal jobs stay visible).
    When no in-memory job exists but a persisted plan does (SLM restarting after
    stage 3), synthesizes a status response so polling during the restart window
    gets a meaningful stage-3-running response instead of 404.
    Returns 404 only when no job has ever run this process AND no plan exists.
    """
    job = _get_update_all_job()
    if job is not None:
        return job

    # C3-a: check for persisted plan — synthesize status for restart window
    from services.database import db_service

    try:
        async with db_service.session() as db:
            result = await db.execute(select(Setting).where(Setting.key == _UPDATE_ALL_RESUME_KEY))
            setting = result.scalar_one_or_none()
            if setting:
                plan = _json.loads(setting.value)
                job_id = plan.get("job_id", "unknown")
                target_commit = plan.get("target_commit")
                return UpdateAllJob(
                    job_id=job_id,
                    status="running",
                    created_at=plan.get("created_at", _now_iso()),
                    stages=[
                        UpdateAllStage(
                            name="github_fetch",
                            status=_StageStatus.SUCCESS,
                            message="completed before restart",
                        ),
                        UpdateAllStage(
                            name="code_source_pull",
                            status=_StageStatus.SUCCESS,
                            message="completed before restart",
                        ),
                        UpdateAllStage(
                            name="slm_self_update",
                            status=_StageStatus.RUNNING,
                            sha=_short_sha(target_commit),
                            message="SLM restarting",
                        ),
                        _make_stage("fleet_nodes"),
                    ],
                )
    except Exception as exc:
        logger.debug("update-all status: could not read plan for synthesis: %s", exc)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No update-all job found. POST /code-sync/update-all to start one.",
    )
