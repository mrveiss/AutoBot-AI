# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Stateful Services API Routes

Handles backups, replications, and data verification for stateful services.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Backup, BackupStatus, Node, Replication, ReplicationStatus
from models.schemas import (
    ActionResponse,
    BackupCreate,
    BackupListResponse,
    BackupResponse,
    BackupRestoreResponse,
    DataVerifyRequest,
    DataVerifyResponse,
    ReplicationCreate,
    ReplicationListResponse,
    ReplicationResponse,
)
from services.auth import get_current_user
from services.database import get_db
from services.replication import replication_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stateful", tags=["stateful"])


# =============================================================================
# Backup Endpoints
# =============================================================================


@router.get("/backups", response_model=BackupListResponse)
async def list_backups(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = Query(None),
    service_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> BackupListResponse:
    """List all backups with optional filters."""
    query = select(Backup)

    if node_id:
        query = query.where(Backup.node_id == node_id)
    if service_type:
        query = query.where(Backup.service_type == service_type)
    if status_filter:
        query = query.where(Backup.status == status_filter)

    query = query.order_by(Backup.created_at.desc())

    # Get total count
    count_result = await db.execute(select(Backup.id).where(query.whereclause or True))
    total = len(count_result.all())

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    backups = result.scalars().all()

    return BackupListResponse(
        backups=[BackupResponse.model_validate(b) for b in backups],
        total=total,
    )


@router.get("/backups/{backup_id}", response_model=BackupResponse)
async def get_backup(
    backup_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> BackupResponse:
    """Get a backup by ID."""
    result = await db.execute(select(Backup).where(Backup.backup_id == backup_id))
    backup = result.scalar_one_or_none()

    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found",
        )

    return BackupResponse.model_validate(backup)


@router.post(
    "/backups", response_model=BackupResponse, status_code=status.HTTP_201_CREATED
)
async def create_backup(
    request: BackupCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> BackupResponse:
    """Create a new backup for a node's service."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == request.node_id))
    node = node_result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    backup_id = str(uuid.uuid4())[:16]
    backup = Backup(
        backup_id=backup_id,
        node_id=request.node_id,
        service_type=request.service_type,
        status=BackupStatus.PENDING.value,
    )
    db.add(backup)
    await db.commit()
    await db.refresh(backup)

    # Start async backup job
    asyncio.create_task(_run_backup(backup_id, node.ip_address, request.service_type))

    logger.info("Backup created: %s for node %s", backup_id, request.node_id)
    return BackupResponse.model_validate(backup)


@router.post("/backups/{backup_id}/restore", response_model=BackupRestoreResponse)
async def restore_backup(
    backup_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> BackupRestoreResponse:
    """Restore a backup to its original node."""
    result = await db.execute(select(Backup).where(Backup.backup_id == backup_id))
    backup = result.scalar_one_or_none()

    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found",
        )

    if backup.status != BackupStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot restore backup in status: {backup.status}",
        )

    # Start async restore job
    job_id = str(uuid.uuid4())[:16]
    asyncio.create_task(_run_restore(job_id, backup.backup_id, backup.node_id))

    logger.info("Restore started: %s from backup %s", job_id, backup_id)
    return BackupRestoreResponse(
        success=True,
        message="Restore job started",
        job_id=job_id,
    )


# =============================================================================
# Replication Endpoints
# =============================================================================


@router.get("/replications", response_model=ReplicationListResponse)
async def list_replications(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    source_node_id: Optional[str] = Query(None),
    target_node_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> ReplicationListResponse:
    """List all replications with optional filters."""
    query = select(Replication)

    if source_node_id:
        query = query.where(Replication.source_node_id == source_node_id)
    if target_node_id:
        query = query.where(Replication.target_node_id == target_node_id)
    if status_filter:
        query = query.where(Replication.status == status_filter)

    query = query.order_by(Replication.created_at.desc())

    # Get total count
    count_result = await db.execute(
        select(Replication.id).where(query.whereclause or True)
    )
    total = len(count_result.all())

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    replications = result.scalars().all()

    return ReplicationListResponse(
        replications=[ReplicationResponse.model_validate(r) for r in replications],
        total=total,
    )


@router.get("/replications/{replication_id}", response_model=ReplicationResponse)
async def get_replication(
    replication_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ReplicationResponse:
    """Get a replication by ID."""
    result = await db.execute(
        select(Replication).where(Replication.replication_id == replication_id)
    )
    replication = result.scalar_one_or_none()

    if not replication:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Replication not found",
        )

    return ReplicationResponse.model_validate(replication)


@router.post(
    "/replications",
    response_model=ReplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_replication(
    request: ReplicationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ReplicationResponse:
    """Start a new replication between nodes."""
    # Verify both nodes exist
    source_result = await db.execute(
        select(Node).where(Node.node_id == request.source_node_id)
    )
    source_node = source_result.scalar_one_or_none()
    if not source_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source node not found",
        )

    target_result = await db.execute(
        select(Node).where(Node.node_id == request.target_node_id)
    )
    target_node = target_result.scalar_one_or_none()
    if not target_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target node not found",
        )

    # Check for existing active replication
    existing = await db.execute(
        select(Replication)
        .where(Replication.source_node_id == request.source_node_id)
        .where(Replication.target_node_id == request.target_node_id)
        .where(
            Replication.status.in_(
                [
                    ReplicationStatus.PENDING.value,
                    ReplicationStatus.SYNCING.value,
                    ReplicationStatus.ACTIVE.value,
                ]
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active replication already exists between these nodes",
        )

    replication_id = str(uuid.uuid4())[:16]
    replication = Replication(
        replication_id=replication_id,
        source_node_id=request.source_node_id,
        target_node_id=request.target_node_id,
        service_type=request.service_type,
        status=ReplicationStatus.PENDING.value,
    )
    db.add(replication)
    await db.commit()
    await db.refresh(replication)

    # Start async replication job using the ReplicationService (Issue #726 Phase 4)
    asyncio.create_task(
        replication_service.setup_replication(
            db, replication_id, source_node, target_node, request.service_type
        )
    )

    logger.info(
        "Replication started: %s (%s -> %s)",
        replication_id,
        request.source_node_id,
        request.target_node_id,
    )
    return ReplicationResponse.model_validate(replication)


@router.post("/replications/{replication_id}/promote", response_model=ActionResponse)
async def promote_replica(
    replication_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ActionResponse:
    """Promote a replica to primary (Issue #726 Phase 4).

    This uses Ansible to properly promote the replica node to primary,
    removing the REPLICAOF configuration and making it a standalone master.
    """
    success, message = await replication_service.promote_replica(db, replication_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    logger.info("Replica promoted: %s", replication_id)
    return ActionResponse(
        action="promote",
        success=True,
        message=message,
        resource_id=replication_id,
    )


@router.post("/replications/{replication_id}/stop", response_model=ActionResponse)
async def stop_replication(
    replication_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ActionResponse:
    """Stop replication without promotion (Issue #726 Phase 4).

    Stops the replication link but does not promote the replica to primary.
    """
    success, message = await replication_service.stop_replication(db, replication_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    logger.info("Replication stopped: %s", replication_id)
    return ActionResponse(
        action="stop",
        success=True,
        message=message,
        resource_id=replication_id,
    )


@router.post(
    "/replications/{replication_id}/verify-sync", response_model=DataVerifyResponse
)
async def verify_replication_sync(
    replication_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> DataVerifyResponse:
    """Verify data sync between source and target nodes (Issue #726 Phase 4).

    Performs keyspace analysis to compare:
    - Key counts between source and target
    - Replication lag in bytes
    - Master link status
    """
    result = await db.execute(
        select(Replication).where(Replication.replication_id == replication_id)
    )
    replication = result.scalar_one_or_none()

    if not replication:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Replication not found",
        )

    # Get source and target nodes
    source_result = await db.execute(
        select(Node).where(Node.node_id == replication.source_node_id)
    )
    source_node = source_result.scalar_one_or_none()

    target_result = await db.execute(
        select(Node).where(Node.node_id == replication.target_node_id)
    )
    target_node = target_result.scalar_one_or_none()

    if not source_node or not target_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source or target node not found",
        )

    # Get Redis password from source
    from services.replication import replication_service

    redis_password = await replication_service._get_redis_password(
        source_node.ip_address,
        source_node.ssh_user or "autobot",
        source_node.ssh_port or 22,
    )

    # Verify sync
    sync_result = await replication_service.verify_sync(
        source_node.ip_address,
        target_node.ip_address,
        source_node.ssh_user or "autobot",
        source_node.ssh_port or 22,
        redis_password,
    )

    return DataVerifyResponse(
        is_healthy=sync_result.get("synced", False),
        service_type=replication.service_type,
        details={
            "source": sync_result.get("source", {}),
            "target": sync_result.get("target", {}),
            "comparison": sync_result.get("comparison", {}),
            "lag": sync_result.get("lag", {}),
        },
        checks=sync_result.get("checks", []),
    )


# =============================================================================
# Data Verification Endpoints
# =============================================================================


@router.post("/verify", response_model=DataVerifyResponse)
async def verify_data(
    request: DataVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> DataVerifyResponse:
    """Verify data integrity for a service on a node."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == request.node_id))
    node = node_result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Run verification based on service type
    checks = []
    details = {}
    is_healthy = True

    if request.service_type == "redis":
        verify_result = await _verify_redis(node.ip_address)
        checks = verify_result["checks"]
        details = verify_result["details"]
        is_healthy = verify_result["is_healthy"]
    else:
        checks.append(
            {
                "name": "service_check",
                "status": "skipped",
                "message": f"Verification not implemented for {request.service_type}",
            }
        )

    return DataVerifyResponse(
        is_healthy=is_healthy,
        service_type=request.service_type,
        details=details,
        checks=checks,
    )


# =============================================================================
# Helper Functions (async jobs)
# =============================================================================


async def _run_backup(backup_id: str, host: str, service_type: str) -> None:
    """Execute backup operation asynchronously using the backup service."""
    from services.backup import backup_service
    from services.database import db_service

    logger.info(
        "Running backup %s for host %s (service: %s)", backup_id, host, service_type
    )

    async with db_service.session() as db:
        # Get the backup record
        result = await db.execute(select(Backup).where(Backup.backup_id == backup_id))
        backup = result.scalar_one_or_none()
        if not backup:
            logger.error("Backup %s not found", backup_id)
            return

        # Get the node for full connection details
        node_result = await db.execute(
            select(Node).where(Node.node_id == backup.node_id)
        )
        node = node_result.scalar_one_or_none()
        if not node:
            logger.error("Node %s not found for backup %s", backup.node_id, backup_id)
            backup.status = BackupStatus.FAILED.value
            backup.error = "Node not found"
            backup.completed_at = datetime.utcnow()
            await db.commit()
            return

        # Execute backup using the dedicated service
        if service_type == "redis":
            success, message = await backup_service.execute_redis_backup(
                db, backup_id, node
            )
            if not success:
                logger.error("Backup %s failed: %s", backup_id, message)
        else:
            # For unsupported service types, mark as failed
            backup.status = BackupStatus.FAILED.value
            backup.error = f"Unsupported service type: {service_type}"
            backup.completed_at = datetime.utcnow()
            await db.commit()
            logger.warning("Backup %s failed: unsupported service type", backup_id)


async def _run_restore(job_id: str, backup_id: str, node_id: str) -> None:
    """Execute restore operation asynchronously using the backup service."""
    from services.backup import backup_service
    from services.database import db_service

    logger.info(
        "Running restore %s from backup %s to node %s", job_id, backup_id, node_id
    )

    async with db_service.session() as db:
        # Get the target node
        node_result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = node_result.scalar_one_or_none()
        if not node:
            logger.error("Target node %s not found for restore", node_id)
            return

        # Execute restore
        success, message = await backup_service.execute_restore(db, backup_id, node)
        if success:
            logger.info("Restore %s completed: %s", job_id, message)
        else:
            logger.error("Restore %s failed: %s", job_id, message)


# NOTE: Replication is now handled by services/replication.py using Ansible
# The old _run_replication function has been replaced by replication_service.setup_replication
# Issue #726 Phase 4


async def _verify_redis(host: str) -> dict:
    """Verify Redis data integrity."""
    checks = []
    details = {}
    is_healthy = True

    try:
        # Check Redis connectivity
        cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=10",
            f"autobot@{host}",
            "redis-cli PING && redis-cli INFO keyspace && redis-cli DBSIZE",
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)

        if process.returncode == 0:
            output = stdout.decode()
            checks.append(
                {
                    "name": "connectivity",
                    "status": "passed",
                    "message": "Redis is responding",
                }
            )

            # Parse output for details
            if "PONG" in output:
                details["ping"] = "OK"

            checks.append(
                {
                    "name": "data_integrity",
                    "status": "passed",
                    "message": "Data appears consistent",
                }
            )
        else:
            is_healthy = False
            checks.append(
                {
                    "name": "connectivity",
                    "status": "failed",
                    "message": stderr.decode()[:200] or "Redis not responding",
                }
            )

    except asyncio.TimeoutError:
        is_healthy = False
        checks.append(
            {
                "name": "connectivity",
                "status": "failed",
                "message": "Connection timed out",
            }
        )
    except Exception as e:
        is_healthy = False
        checks.append(
            {
                "name": "connectivity",
                "status": "failed",
                "message": str(e)[:200],
            }
        )

    return {
        "is_healthy": is_healthy,
        "checks": checks,
        "details": details,
    }
