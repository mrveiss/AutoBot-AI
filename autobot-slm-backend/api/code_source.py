# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Source API Routes (Issue #779).

Manages the code-source node assignment and git notifications.
"""

import asyncio
import logging
import os
import tarfile
import tempfile
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from models.database import (
    CodeSource,
    CodeStatus,
    Node,
    NodeCodeVersion,
    NodeRole,
    RoleStatus,
    Setting,
)
from pydantic import BaseModel
from services.auth import get_current_user
from services.database import get_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/code-source", tags=["code-source"])


class CodeSourceResponse(BaseModel):
    """Code source configuration response."""

    node_id: str
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    repo_path: str
    branch: str
    last_known_commit: Optional[str] = None
    last_notified_at: Optional[datetime] = None
    is_active: bool

    class Config:
        from_attributes = True


class CodeSourceAssign(BaseModel):
    """Assign code-source to a node."""

    node_id: str
    repo_path: str = "/opt/autobot"
    branch: str = "main"


class CodeNotification(BaseModel):
    """Git commit notification from code-source."""

    node_id: str
    commit: str
    branch: str = "main"
    message: Optional[str] = None
    is_code_source: bool = True
    # Phase 5 (#926): list of role dirs that changed (empty = all roles)
    changed_roles: List[str] = []


class CodeNotificationResponse(BaseModel):
    """Response to code notification."""

    success: bool
    message: str
    commit: str
    outdated_nodes: int = 0


@router.get("", response_model=Optional[CodeSourceResponse])
async def get_active_code_source(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> Optional[CodeSourceResponse]:
    """Get the active code source configuration."""
    result = await db.execute(select(CodeSource).where(CodeSource.is_active.is_(True)))
    source = result.scalar_one_or_none()

    if not source:
        return None

    # Get node info
    node_result = await db.execute(select(Node).where(Node.node_id == source.node_id))
    node = node_result.scalar_one_or_none()

    return CodeSourceResponse(
        node_id=source.node_id,
        hostname=node.hostname if node else None,
        ip_address=node.ip_address if node else None,
        repo_path=source.repo_path,
        branch=source.branch,
        last_known_commit=source.last_known_commit,
        last_notified_at=source.last_notified_at,
        is_active=source.is_active,
    )


async def _upsert_code_source(db: AsyncSession, data: CodeSourceAssign) -> CodeSource:
    """Deactivate existing sources and create/update the target source.

    Helper for assign_code_source (#829).
    """
    # Deactivate any existing code-source
    existing_result = await db.execute(
        select(CodeSource).where(CodeSource.is_active.is_(True))
    )
    for existing in existing_result.scalars().all():
        existing.is_active = False

    # Check if this node already has a code-source record
    source_result = await db.execute(
        select(CodeSource).where(CodeSource.node_id == data.node_id)
    )
    source = source_result.scalar_one_or_none()

    if source:
        source.is_active = True
        source.repo_path = data.repo_path
        source.branch = data.branch
    else:
        source = CodeSource(
            node_id=data.node_id,
            repo_path=data.repo_path,
            branch=data.branch,
            is_active=True,
        )
        db.add(source)

    return source


async def _ensure_code_source_role(db: AsyncSession, node_id: str) -> None:
    """Ensure the node has the code-source role assigned.

    Helper for assign_code_source (#829).
    """
    role_result = await db.execute(
        select(NodeRole).where(
            NodeRole.node_id == node_id,
            NodeRole.role_name == "code-source",
        )
    )
    if not role_result.scalar_one_or_none():
        db.add(
            NodeRole(
                node_id=node_id,
                role_name="code-source",
                assignment_type="manual",
                status=RoleStatus.ACTIVE.value,
            )
        )


async def _find_similar_paths(node: Node, target_path: str) -> Optional[str]:
    """Find paths similar to target (case-insensitive match).

    Helper for _validate_repo_path (#865).
    Returns the actual path if found, None otherwise.
    """
    parent_dir = target_path.rsplit("/", 1)[0] if "/" in target_path else "/"
    basename = target_path.rsplit("/", 1)[-1] if "/" in target_path else target_path

    # Check if parent directory exists and list contents
    ssh_cmd = [
        "ssh",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=no",
        f"{node.ssh_user}@{node.ip_address}",
        f"test -d {parent_dir} && ls -1 {parent_dir} 2>/dev/null || true",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)

        if proc.returncode == 0 and stdout:
            # Check for case-insensitive match
            entries = stdout.decode().strip().split("\n")
            for entry in entries:
                if entry.lower() == basename.lower() and entry != basename:
                    return f"{parent_dir}/{entry}"
    except Exception as e:
        logger.debug("Failed to search for similar paths: %s", e)

    return None


async def _validate_repo_path(node: Node, repo_path: str) -> None:
    """Validate that repo path exists on the source node.

    Helper for assign_code_source (#865).

    Args:
        node: The source node to SSH into
        repo_path: The repository path to validate

    Raises:
        HTTPException: If path doesn't exist or SSH fails
    """
    ssh_cmd = [
        "ssh",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=no",
        f"{node.ssh_user}@{node.ip_address}",
        f"test -d {repo_path} && echo exists",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)

        if proc.returncode != 0 or stdout.decode().strip() != "exists":
            # Check for similar paths (case mismatch)
            similar_path = await _find_similar_paths(node, repo_path)

            error_detail = f"Repository path does not exist on source node: {repo_path}"
            if similar_path:
                error_detail += f". Did you mean: {similar_path}?"

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=error_detail
            )

    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Timeout connecting to node {node.hostname} ({node.ip_address})",
        )
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error("SSH validation failed for %s: %s", node.hostname, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate path on {node.hostname}: {str(e)}",
        )


@router.post("/assign", response_model=CodeSourceResponse)
async def assign_code_source(
    data: CodeSourceAssign,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CodeSourceResponse:
    """Assign a node as code-source."""
    node_result = await db.execute(select(Node).where(Node.node_id == data.node_id))
    node = node_result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node not found: {data.node_id}",
        )

    # Validate repo path exists on the node (#865)
    await _validate_repo_path(node, data.repo_path)

    source = await _upsert_code_source(db, data)
    await _ensure_code_source_role(db, data.node_id)

    await db.commit()
    await db.refresh(source)

    logger.info("Assigned code-source to node: %s", data.node_id)

    return CodeSourceResponse(
        node_id=source.node_id,
        hostname=node.hostname,
        ip_address=node.ip_address,
        repo_path=source.repo_path,
        branch=source.branch,
        last_known_commit=source.last_known_commit,
        last_notified_at=source.last_notified_at,
        is_active=source.is_active,
    )


@router.delete("/assign")
async def remove_code_source(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Remove the active code-source assignment."""
    result = await db.execute(select(CodeSource).where(CodeSource.is_active.is_(True)))
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active code-source",
        )

    source.is_active = False
    await db.commit()

    logger.info("Removed code-source from node: %s", source.node_id)
    return {"success": True, "message": "Code-source removed"}


async def _update_code_sync_state(
    db: AsyncSession,
    node_id: str,
    commit: str,
    changed_roles: List[str],
) -> int:
    """Update latest version setting and mark affected nodes outdated.

    Phase 5 (#926): If changed_roles is provided, only mark nodes that have
    those roles assigned as OUTDATED. Otherwise mark all other nodes.

    Returns:
        Number of nodes marked as outdated.
    """
    setting_result = await db.execute(
        select(Setting).where(Setting.key == "slm_agent_latest_commit")
    )
    setting = setting_result.scalar_one_or_none()
    if setting:
        setting.value = commit
    else:
        db.add(Setting(key="slm_agent_latest_commit", value=commit))

    if changed_roles:
        outdated_count = await _mark_roles_outdated(db, node_id, commit, changed_roles)
    else:
        outdated_count = await _mark_all_nodes_outdated(db, node_id, commit)

    return outdated_count


async def _mark_all_nodes_outdated(
    db: AsyncSession, source_node_id: str, commit: str
) -> int:
    """Mark all nodes except source as outdated.

    Helper for _update_code_sync_state (#926 Phase 5).
    """
    outdated_result = await db.execute(
        select(Node).where(
            Node.node_id != source_node_id,
            Node.code_version != commit,
        )
    )
    nodes = outdated_result.scalars().all()
    for node in nodes:
        node.code_status = CodeStatus.OUTDATED.value
    return len(nodes)


async def _mark_roles_outdated(
    db: AsyncSession,
    source_node_id: str,
    commit: str,
    changed_roles: List[str],
) -> int:
    """Mark only nodes that have changed roles assigned as outdated.

    Also upserts NodeCodeVersion rows for each (node, role) pair.

    Helper for _update_code_sync_state (#926 Phase 5).
    """
    affected_node_ids: set = set()

    for role_name in changed_roles:
        # Find nodes that have this role assigned
        role_result = await db.execute(
            select(NodeRole).where(
                NodeRole.role_name == role_name,
                NodeRole.node_id != source_node_id,
            )
        )
        for node_role in role_result.scalars().all():
            affected_node_ids.add(node_role.node_id)
            await _upsert_node_code_version(
                db, node_role.node_id, role_name, commit, CodeStatus.OUTDATED
            )

    # Mark affected nodes OUTDATED at the node level too
    for affected_id in affected_node_ids:
        node_result = await db.execute(select(Node).where(Node.node_id == affected_id))
        node = node_result.scalar_one_or_none()
        if node:
            node.code_status = CodeStatus.OUTDATED.value

    return len(affected_node_ids)


async def _upsert_node_code_version(
    db: AsyncSession,
    node_id: str,
    role_name: str,
    commit: str,
    status: CodeStatus,
    cache_path: Optional[str] = None,
) -> None:
    """Insert or update a NodeCodeVersion row.

    Helper for Phase 5 code sync (#926).
    """
    result = await db.execute(
        select(NodeCodeVersion).where(
            NodeCodeVersion.node_id == node_id,
            NodeCodeVersion.role_name == role_name,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.commit_hash = commit
        row.status = status.value
        if cache_path:
            row.cache_path = cache_path
        if status == CodeStatus.UP_TO_DATE:
            row.deployed_at = datetime.utcnow()
    else:
        db.add(
            NodeCodeVersion(
                node_id=node_id,
                role_name=role_name,
                commit_hash=commit,
                status=status.value,
                cache_path=cache_path,
                deployed_at=(
                    datetime.utcnow() if status == CodeStatus.UP_TO_DATE else None
                ),
            )
        )


async def _broadcast_commit_notification(
    notification: CodeNotification, outdated_count: int
) -> None:
    """Broadcast new commit via WebSocket.

    Helper for notify_new_commit (#829).
    """
    try:
        from api.websocket import ws_manager

        await ws_manager.broadcast(
            {
                "type": "code_source.new_commit",
                "data": {
                    "commit": notification.commit,
                    "branch": notification.branch,
                    "message": notification.message,
                    "node_id": notification.node_id,
                    "outdated_nodes": outdated_count,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }
        )
    except Exception as e:
        logger.debug("Failed to broadcast commit notification: %s", e)


@router.post("/notify", response_model=CodeNotificationResponse)
async def notify_new_commit(
    notification: CodeNotification,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CodeNotificationResponse:
    """
    Receive notification of new commit from code-source.

    Called by git post-commit hook. No authentication - uses node_id.
    """
    # Verify this is from an active code-source
    source_result = await db.execute(
        select(CodeSource).where(
            CodeSource.node_id == notification.node_id,
            CodeSource.is_active.is_(True),
        )
    )
    source = source_result.scalar_one_or_none()

    if not source:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Node is not an active code-source",
        )

    # Update source with new commit
    source.last_known_commit = notification.commit
    source.last_notified_at = datetime.utcnow()

    # Update source node's code_version and mark as up-to-date
    node_result = await db.execute(
        select(Node).where(Node.node_id == notification.node_id)
    )
    node = node_result.scalar_one_or_none()
    if node:
        node.code_version = notification.commit
        # Mark as OUTDATED: the deployed service at /opt/autobot/ still needs
        # to be synced from the git repo. Only mark UP_TO_DATE after a sync (#913).
        node.code_status = CodeStatus.OUTDATED.value

    # Update code-sync status and mark fleet nodes outdated (#829/#926)
    outdated_count = await _update_code_sync_state(
        db, notification.node_id, notification.commit, notification.changed_roles
    )

    await db.commit()

    logger.info(
        "Code notification received: commit=%s from node=%s, "
        "%d nodes marked outdated",
        notification.commit[:12],
        notification.node_id,
        outdated_count,
    )

    await _broadcast_commit_notification(notification, outdated_count)

    return CodeNotificationResponse(
        success=True,
        message=f"Commit {notification.commit[:12]} recorded",
        commit=notification.commit,
        outdated_nodes=outdated_count,
    )


# =============================================================================
# Phase 5 (#926): per-role version tracking + air-gapped upload
# =============================================================================

_CACHE_BASE = os.environ.get("AUTOBOT_CODE_CACHE_DIR", "/opt/autobot/cache")


class NodeCodeVersionResponse(BaseModel):
    """Per-role version entry for a node."""

    node_id: str
    role_name: str
    commit_hash: Optional[str] = None
    status: str
    deployed_at: Optional[datetime] = None
    cache_path: Optional[str] = None


class PackageUploadResponse(BaseModel):
    """Response after uploading a role package."""

    success: bool
    role_name: str
    commit_hash: str
    cache_path: str
    outdated_nodes: int


@router.get("/node-code-versions", response_model=List[NodeCodeVersionResponse])
async def list_node_code_versions(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = None,
    role_name: Optional[str] = None,
) -> List[NodeCodeVersionResponse]:
    """List per-role code version status across the fleet."""
    query = select(NodeCodeVersion)
    if node_id:
        query = query.where(NodeCodeVersion.node_id == node_id)
    if role_name:
        query = query.where(NodeCodeVersion.role_name == role_name)

    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        NodeCodeVersionResponse(
            node_id=r.node_id,
            role_name=r.role_name,
            commit_hash=r.commit_hash,
            status=r.status,
            deployed_at=r.deployed_at,
            cache_path=r.cache_path,
        )
        for r in rows
    ]


def _extract_tarball_to_cache(data: bytes, role_name: str, commit_hash: str) -> str:
    """Extract uploaded tarball to the role cache directory.

    Helper for upload_package (#926 Phase 5).
    Returns the cache path.
    """
    cache_path = os.path.join(_CACHE_BASE, role_name)
    os.makedirs(cache_path, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tar_path = os.path.join(tmpdir, "upload.tar.gz")
        with open(tar_path, "wb") as fh:
            fh.write(data)

        if not tarfile.is_tarfile(tar_path):
            raise ValueError("Uploaded file is not a valid tar archive")

        with tarfile.open(tar_path, "r:gz") as tar:
            # Security: reject absolute paths and path traversal
            for member in tar.getmembers():
                if member.name.startswith("/") or ".." in member.name:
                    raise ValueError(f"Unsafe path in archive: {member.name}")
            tar.extractall(cache_path)  # noqa: S202  # nosec B202

    return cache_path


async def _extract_package_to_cache(
    data: bytes, role_name: str, commit_hash: str
) -> str:
    """Helper for upload_package. Run tarball extraction in executor. Ref: #1088."""
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, _extract_tarball_to_cache, data, role_name, commit_hash
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except OSError as exc:
        logger.error("Failed to extract package for %s: %s", role_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract package: {exc}",
        ) from exc


async def _mark_role_nodes_outdated(
    db: AsyncSession, role_name: str, commit_hash: str, cache_path: str
) -> int:
    """Helper for upload_package. Mark all nodes with the role as OUTDATED. Ref: #1088."""
    role_result = await db.execute(
        select(NodeRole).where(NodeRole.role_name == role_name)
    )
    outdated_count = 0
    for node_role in role_result.scalars().all():
        await _upsert_node_code_version(
            db,
            node_role.node_id,
            role_name,
            commit_hash,
            CodeStatus.OUTDATED,
            cache_path=cache_path,
        )
        node_result = await db.execute(
            select(Node).where(Node.node_id == node_role.node_id)
        )
        node = node_result.scalar_one_or_none()
        if node:
            node.code_status = CodeStatus.OUTDATED.value
            outdated_count += 1
    return outdated_count


@router.post("/upload-package", response_model=PackageUploadResponse)
async def upload_package(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    role_name: str = Form(...),
    commit_hash: str = Form(...),
    package: UploadFile = File(...),
) -> PackageUploadResponse:
    """Upload a role code package for air-gapped deployments.

    Accepts a .tar.gz of the role directory. Extracts to
    /opt/autobot/cache/<role_name>/ and marks all nodes that have
    this role assigned as OUTDATED.

    Issue #1088: Refactored with _extract_package_to_cache and
    _mark_role_nodes_outdated helpers.
    """
    if not package.filename or not package.filename.endswith((".tar.gz", ".tgz")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Package must be a .tar.gz or .tgz file",
        )

    data = await package.read()
    cache_path = await _extract_package_to_cache(data, role_name, commit_hash)
    outdated_count = await _mark_role_nodes_outdated(
        db, role_name, commit_hash, cache_path
    )
    await db.commit()

    logger.info(
        "Package uploaded: role=%s commit=%s cache=%s outdated=%d",
        role_name,
        commit_hash[:12],
        cache_path,
        outdated_count,
    )
    return PackageUploadResponse(
        success=True,
        role_name=role_name,
        commit_hash=commit_hash,
        cache_path=cache_path,
        outdated_nodes=outdated_count,
    )
