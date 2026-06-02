# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Execution Snapshot API endpoints (GH#4458, MVA-2227).

Provides REST API for Docker container snapshot management:
- POST /execution/snapshots - Create snapshot from running container
- GET /execution/snapshots - List snapshots by session_id
- POST /execution/snapshots/{id}/restore - Restore container from snapshot
- DELETE /execution/snapshots/{id} - Delete snapshot and image
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.schemas_system import (
    CreateSnapshotRequest,
    CreateSnapshotResponse,
    DeleteSnapshotResponse,
    RestoreSnapshotResponse,
    SnapshotListResponse,
    SnapshotMetadata,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from services.execution.docker_backend import DockerBackend
from services.execution.snapshot_index import SnapshotRecord

logger = get_logger(__name__)

router = APIRouter()


def get_docker_backend() -> DockerBackend:
    """Dependency injection for DockerBackend singleton.

    Returns:
        DockerBackend instance configured from environment.
    """
    return lazy_singleton(DockerBackend)


def _snapshot_record_to_metadata(record: SnapshotRecord) -> SnapshotMetadata:
    """Convert SnapshotRecord dataclass to SnapshotMetadata Pydantic model."""
    return SnapshotMetadata(
        snapshot_id=record.snapshot_id,
        session_id=record.session_id,
        container_id=record.container_id,
        image_name=record.image_name,
        created_at=record.created_at,
        size_bytes=record.size_bytes,
        labels=record.labels,
        user_id=record.user_id,
    )


@router.post("/execution/snapshots", response_model=CreateSnapshotResponse)
@with_error_handling(category="execution_snapshot")
async def create_snapshot(
    request_body: CreateSnapshotRequest,
    request: Request,
    backend: DockerBackend = Depends(get_docker_backend),
    current_user: dict = Depends(get_current_user),
) -> CreateSnapshotResponse:
    """Create a snapshot of a running Docker container.

    Args:
        request_body: Container ID and optional session ID
        request: FastAPI request (for user_id extraction)
        backend: DockerBackend instance
        current_user: Authenticated user from JWT/session

    Returns:
        CreateSnapshotResponse with snapshot metadata

    Raises:
        HTTPException: If snapshot creation fails
    """
    # Strict user_id extraction - fail-open is a security risk
    user_id = current_user.get("username") or current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Verify container ownership before allowing snapshot
        # DockerBackend should validate container ownership, but we add defense-in-depth here
        container_id = request_body.container_id

        # Attempt to inspect container to verify it exists and is accessible
        try:
            container = backend.client.containers.get(container_id)
            # Check if container has autobot-owner label matching user
            container_labels = container.labels or {}
            container_owner = container_labels.get("autobot-owner", "")

            if container_owner and container_owner != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: container belongs to another user"
                )
        except Exception as container_err:
            logger.warning("Container verification failed for %s: %s", container_id, container_err)
            # Container not found or not accessible - let backend.snapshot handle it
            pass

        snapshot_record = await backend.snapshot(
            container_id=container_id,
            session_id=request_body.session_id,
            user_id=user_id,
        )

        snapshot_meta = _snapshot_record_to_metadata(snapshot_record)

        logger.info(
            "Created snapshot %s for container %s (user=%s)",
            snapshot_record.snapshot_id,
            container_id,
            user_id,
        )

        return CreateSnapshotResponse(
            success=True,
            snapshot=snapshot_meta,
            message=f"Snapshot {snapshot_record.snapshot_id} created successfully",
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to create snapshot: %s", exc)
        # Generic error message - don't leak internal details
        raise HTTPException(status_code=500, detail="Snapshot creation failed")


@router.get("/execution/snapshots", response_model=SnapshotListResponse)
@with_error_handling(category="execution_snapshot")
async def list_snapshots(
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    backend: DockerBackend = Depends(get_docker_backend),
    current_user: dict = Depends(get_current_user),
) -> SnapshotListResponse:
    """List snapshots, optionally filtered by session_id.

    Args:
        session_id: Optional session ID filter
        backend: DockerBackend instance
        current_user: Authenticated user from JWT/session

    Returns:
        SnapshotListResponse with list of snapshots
    """
    # Strict user_id extraction
    user_id = current_user.get("username") or current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        if session_id:
            # Get snapshots for session, then filter by user ownership
            snapshot_records = await backend.get_snapshots_for_session(session_id)
            # Filter to only user's snapshots
            snapshot_records = [rec for rec in snapshot_records if rec.user_id == user_id]
        else:
            # List only snapshots owned by this user
            snapshot_records = backend._snapshot_index.list_by_user(user_id)

        snapshots = [_snapshot_record_to_metadata(rec) for rec in snapshot_records]

        logger.debug(
            "Listed %d snapshots (session_id=%s, user=%s)",
            len(snapshots),
            session_id or "all",
            user_id,
        )

        return SnapshotListResponse(
            success=True,
            snapshots=snapshots,
            count=len(snapshots),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list snapshots: %s", exc)
        # Generic error message
        raise HTTPException(status_code=500, detail="Snapshot list failed")


@router.post("/execution/snapshots/{snapshot_id}/restore", response_model=RestoreSnapshotResponse)
@with_error_handling(category="execution_snapshot")
async def restore_snapshot(
    snapshot_id: str,
    backend: DockerBackend = Depends(get_docker_backend),
    current_user: dict = Depends(get_current_user),
) -> RestoreSnapshotResponse:
    """Restore a container from a snapshot.

    Args:
        snapshot_id: ID of snapshot to restore
        backend: DockerBackend instance
        current_user: Authenticated user from JWT/session

    Returns:
        RestoreSnapshotResponse with new container ID

    Raises:
        HTTPException: 404 if snapshot not found, 403 if permission denied, 500 on failure
    """
    # Strict user_id extraction
    user_id = current_user.get("username") or current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        container_id = await backend.restore(snapshot_id, caller_user_id=user_id)

        logger.info(
            "Restored snapshot %s to container %s (user=%s)",
            snapshot_id,
            container_id,
            user_id,
        )

        return RestoreSnapshotResponse(
            success=True,
            container_id=container_id,
            snapshot_id=snapshot_id,
            message=f"Snapshot restored to container {container_id}",
        )

    except KeyError:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to restore snapshot %s: %s", snapshot_id, exc)
        # Generic error message
        raise HTTPException(status_code=500, detail="Snapshot restore failed")


@router.delete("/execution/snapshots/{snapshot_id}", response_model=DeleteSnapshotResponse)
@with_error_handling(category="execution_snapshot")
async def delete_snapshot(
    snapshot_id: str,
    backend: DockerBackend = Depends(get_docker_backend),
    current_user: dict = Depends(get_current_user),
) -> DeleteSnapshotResponse:
    """Delete a snapshot and its associated Docker image.

    Args:
        snapshot_id: ID of snapshot to delete
        backend: DockerBackend instance
        current_user: Authenticated user from JWT/session

    Returns:
        DeleteSnapshotResponse confirming deletion

    Raises:
        HTTPException: 404 if snapshot not found, 403 if permission denied
    """
    # Strict user_id extraction
    user_id = current_user.get("username") or current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        deleted = await backend.delete_snapshot(snapshot_id, caller_user_id=user_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Snapshot not found")

        logger.info("Deleted snapshot %s (user=%s)", snapshot_id, user_id)

        return DeleteSnapshotResponse(
            success=True,
            message=f"Snapshot {snapshot_id} deleted successfully",
        )

    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete snapshot %s: %s", snapshot_id, exc)
        # Generic error message
        raise HTTPException(status_code=500, detail="Snapshot deletion failed")
