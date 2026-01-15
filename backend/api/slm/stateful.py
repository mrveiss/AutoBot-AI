# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Stateful Services API

REST endpoints for stateful service operations:
- Replication management
- Backup/restore operations
- Data verification
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from backend.services.slm.stateful_manager import (
    BackupContext,
    BackupState,
    ReplicationContext,
    ReplicationState,
    get_stateful_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm/stateful", tags=["SLM Stateful Services"])


# ==================== Pydantic Models ====================


class ReplicationCreate(BaseModel):
    """Request model for starting replication."""

    primary_node_id: str = Field(..., min_length=1)
    replica_node_id: str = Field(..., min_length=1)
    service_type: str = Field(default="redis", description="Service type (redis)")


class ReplicationResponse(BaseModel):
    """Response model for replication data."""

    replication_id: str
    primary_node_id: str
    replica_node_id: str
    service_type: str
    state: str
    sync_progress: float
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]
    details: Dict

    class Config:
        from_attributes = True


class ReplicationListResponse(BaseModel):
    """Response model for replication list."""

    replications: List[ReplicationResponse]
    total: int


class BackupCreate(BaseModel):
    """Request model for creating a backup."""

    node_id: str = Field(..., min_length=1)
    service_type: str = Field(default="redis", description="Service type (redis)")
    backup_name: Optional[str] = Field(
        default=None,
        description="Optional backup name (auto-generated if not provided)",
    )


class BackupResponse(BaseModel):
    """Response model for backup data."""

    backup_id: str
    node_id: str
    service_type: str
    backup_path: str
    state: str
    size_bytes: int
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]
    checksum: Optional[str]

    class Config:
        from_attributes = True


class BackupListResponse(BaseModel):
    """Response model for backup list."""

    backups: List[BackupResponse]
    total: int


class VerifyDataRequest(BaseModel):
    """Request model for data verification."""

    node_id: str = Field(..., min_length=1)
    service_type: str = Field(default="redis", description="Service type (redis)")


class VerifyDataResponse(BaseModel):
    """Response model for data verification."""

    node_id: str
    service_type: str
    is_healthy: bool
    details: Dict


class ActionResponse(BaseModel):
    """Response for stateful service actions."""

    action: str
    success: bool
    message: str
    resource_id: Optional[str] = None


# ==================== Helper Functions ====================


def _replication_to_response(ctx: ReplicationContext) -> ReplicationResponse:
    """Convert ReplicationContext to response model."""
    return ReplicationResponse(
        replication_id=ctx.replication_id,
        primary_node_id=ctx.primary_node_id,
        replica_node_id=ctx.replica_node_id,
        service_type=ctx.service_type,
        state=ctx.state.value,
        sync_progress=ctx.sync_progress,
        started_at=ctx.started_at.isoformat() if ctx.started_at else None,
        completed_at=ctx.completed_at.isoformat() if ctx.completed_at else None,
        error=ctx.error,
        details=ctx.details,
    )


def _backup_to_response(ctx: BackupContext) -> BackupResponse:
    """Convert BackupContext to response model."""
    return BackupResponse(
        backup_id=ctx.backup_id,
        node_id=ctx.node_id,
        service_type=ctx.service_type,
        backup_path=ctx.backup_path,
        state=ctx.state.value,
        size_bytes=ctx.size_bytes,
        started_at=ctx.started_at.isoformat() if ctx.started_at else None,
        completed_at=ctx.completed_at.isoformat() if ctx.completed_at else None,
        error=ctx.error,
        checksum=ctx.checksum,
    )


# ==================== Replication Endpoints ====================


@router.get("/replications", response_model=ReplicationListResponse)
async def list_replications():
    """List all active replication operations."""
    manager = get_stateful_manager()
    replications = manager.active_replications

    return ReplicationListResponse(
        replications=[_replication_to_response(r) for r in replications],
        total=len(replications),
    )


@router.post(
    "/replications",
    response_model=ReplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_replication(request: ReplicationCreate):
    """
    Start replication from primary to replica node.

    This sets up the replica to sync data from the primary.
    Use GET /replications/{id} to monitor sync progress.
    """
    manager = get_stateful_manager()

    context = await manager.start_replication(
        primary_node_id=request.primary_node_id,
        replica_node_id=request.replica_node_id,
        service_type=request.service_type,
    )

    if context.state == ReplicationState.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=context.error or "Failed to start replication",
        )

    logger.info(
        "Started replication %s: %s -> %s",
        context.replication_id,
        request.primary_node_id,
        request.replica_node_id,
    )

    return _replication_to_response(context)


@router.get("/replications/{replication_id}", response_model=ReplicationResponse)
async def get_replication(replication_id: str):
    """Get replication status by ID."""
    manager = get_stateful_manager()
    context = manager.get_replication(replication_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replication {replication_id} not found",
        )

    # Update sync status
    if context.state == ReplicationState.SYNCING:
        await manager.check_replication_sync(replication_id)

    return _replication_to_response(context)


@router.post("/replications/{replication_id}/promote", response_model=ActionResponse)
async def promote_replica(replication_id: str):
    """
    Promote replica to primary.

    The replica will stop replicating and become an independent primary.
    """
    manager = get_stateful_manager()
    context = manager.get_replication(replication_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replication {replication_id} not found",
        )

    if context.state not in [ReplicationState.SYNCING, ReplicationState.SYNCED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot promote replica in state: {context.state.value}",
        )

    success = await manager.promote_replica(replication_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=context.error or "Promotion failed",
        )

    logger.info("Promoted replica %s", replication_id)

    return ActionResponse(
        action="promote",
        success=True,
        message="Replica promoted to primary",
        resource_id=replication_id,
    )


# ==================== Backup Endpoints ====================


@router.get("/backups", response_model=BackupListResponse)
async def list_backups():
    """List all backup operations."""
    manager = get_stateful_manager()
    backups = manager.active_backups

    return BackupListResponse(
        backups=[_backup_to_response(b) for b in backups],
        total=len(backups),
    )


@router.post(
    "/backups",
    response_model=BackupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_backup(
    request: BackupCreate,
    background_tasks: BackgroundTasks,
):
    """
    Create a backup of service data.

    The backup will be created asynchronously. Monitor progress
    via GET /backups/{id}.
    """
    manager = get_stateful_manager()

    context = await manager.create_backup(
        node_id=request.node_id,
        service_type=request.service_type,
        backup_name=request.backup_name,
    )

    if context.state == BackupState.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=context.error or "Failed to create backup",
        )

    logger.info(
        "Created backup %s: node=%s, path=%s",
        context.backup_id,
        request.node_id,
        context.backup_path,
    )

    return _backup_to_response(context)


@router.get("/backups/{backup_id}", response_model=BackupResponse)
async def get_backup(backup_id: str):
    """Get backup status by ID."""
    manager = get_stateful_manager()
    context = manager.get_backup(backup_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup {backup_id} not found",
        )

    return _backup_to_response(context)


@router.post("/backups/{backup_id}/restore", response_model=ActionResponse)
async def restore_backup(backup_id: str):
    """
    Restore a backup to its original node.

    This will stop the service, restore data, and restart.
    """
    manager = get_stateful_manager()
    context = manager.get_backup(backup_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup {backup_id} not found",
        )

    if context.state != BackupState.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot restore backup in state: {context.state.value}",
        )

    success = await manager.restore_backup(backup_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=context.error or "Restore failed",
        )

    logger.info("Restored backup %s", backup_id)

    return ActionResponse(
        action="restore",
        success=True,
        message="Backup restored successfully",
        resource_id=backup_id,
    )


# ==================== Verification Endpoints ====================


@router.post("/verify", response_model=VerifyDataResponse)
async def verify_data(request: VerifyDataRequest):
    """
    Verify data integrity on a node.

    Checks service-specific data integrity (key count, persistence, etc.).
    """
    manager = get_stateful_manager()

    is_healthy, details = await manager.verify_data(
        node_id=request.node_id,
        service_type=request.service_type,
    )

    return VerifyDataResponse(
        node_id=request.node_id,
        service_type=request.service_type,
        is_healthy=is_healthy,
        details=details,
    )
