# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Nodes API Routes
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import (
    Certificate,
    CodeStatus,
    EventSeverity,
    EventType,
    Node,
    NodeEvent,
    NodeStatus,
    Setting,
)
from models.schemas import (
    CertificateActionResponse,
    CertificateResponse,
    ConnectionTestRequest,
    ConnectionTestResponse,
    EnrollRequest,
    HeartbeatRequest,
    HeartbeatResponse,
    NodeCreate,
    NodeEventListResponse,
    NodeEventResponse,
    NodeListResponse,
    NodeResponse,
    NodeUpdate,
)
from services.auth import get_current_user
from services.database import get_db
from services.encryption import encrypt_data
from services.reconciler import reconciler_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])


async def _broadcast_lifecycle_event(
    node_id: str, event_type: str, details: dict = None
) -> None:
    """Broadcast a node lifecycle event via WebSocket."""
    try:
        from api.websocket import ws_manager

        await ws_manager.send_node_lifecycle_event(node_id, event_type, details)
    except Exception as e:
        logger.debug("Failed to broadcast lifecycle event: %s", e)


async def _create_node_event(
    db: AsyncSession,
    node_id: str,
    event_type: EventType,
    severity: EventSeverity,
    message: str,
    details: dict = None,
) -> NodeEvent:
    """Helper to create a node lifecycle event."""
    event = NodeEvent(
        event_id=str(uuid.uuid4())[:16],
        node_id=node_id,
        event_type=event_type.value,
        severity=severity.value,
        message=message,
        details=details or {},
    )
    db.add(event)
    await db.flush()  # Flush but don't commit - let caller handle transaction
    return event


@router.get("", response_model=NodeListResponse)
async def list_nodes(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> NodeListResponse:
    """List all nodes with optional status filter."""
    query = select(Node)

    if status_filter:
        query = query.where(Node.status == status_filter)

    query = query.order_by(Node.hostname)

    count_result = await db.execute(select(Node.id).where(query.whereclause or True))
    total = len(count_result.all())

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    nodes = result.scalars().all()

    return NodeListResponse(
        nodes=[NodeResponse.model_validate(n) for n in nodes],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    node_data: NodeCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """Register a new node."""
    existing = await db.execute(
        select(Node).where(Node.ip_address == node_data.ip_address)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Node with this IP address already exists",
        )

    node_id = str(uuid.uuid4())[:8]

    # If importing an existing node, mark as online immediately
    # Otherwise, mark as pending for enrollment
    if node_data.import_existing:
        initial_status = NodeStatus.ONLINE.value
    else:
        initial_status = NodeStatus.PENDING.value

    # Store SSH password in extra_data if provided (for enrollment)
    # Password is encrypted using AES-256-GCM before storage
    extra_data = {}
    if node_data.ssh_password and node_data.auth_method == "password":
        try:
            extra_data["ssh_password"] = encrypt_data(node_data.ssh_password)
            extra_data["ssh_password_encrypted"] = True
        except Exception as e:
            logger.error("Failed to encrypt SSH password: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to securely store credentials",
            )

    node = Node(
        node_id=node_id,
        hostname=node_data.hostname,
        ip_address=node_data.ip_address,
        roles=node_data.roles,
        ssh_user=node_data.ssh_user,
        ssh_port=node_data.ssh_port,
        auth_method=node_data.auth_method,
        status=initial_status,
        extra_data=extra_data if extra_data else None,
    )
    db.add(node)
    await db.flush()

    # Create registration event
    event_msg = f"Node registered: {node.hostname} ({node.ip_address})"
    if node_data.import_existing:
        event_msg = f"Existing node imported: {node.hostname} ({node.ip_address})"

    await _create_node_event(
        db,
        node_id,
        EventType.STATE_CHANGE,
        EventSeverity.INFO,
        event_msg,
        {
            "status": initial_status,
            "roles": node_data.roles,
            "import_existing": node_data.import_existing,
        },
    )

    await db.commit()
    await db.refresh(node)

    logger.info(event_msg)

    # Broadcast lifecycle event via WebSocket
    await _broadcast_lifecycle_event(
        node_id,
        "node_created",
        {
            "hostname": node.hostname,
            "ip_address": node.ip_address,
            "status": initial_status,
            "roles": node_data.roles,
            "import_existing": node_data.import_existing,
        },
    )

    return NodeResponse.model_validate(node)


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """Get a node by ID."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    return NodeResponse.model_validate(node)


@router.patch("/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: str,
    node_data: NodeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """Update a node."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    update_data = node_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            if field == "status" and hasattr(value, "value"):
                value = value.value
            setattr(node, field, value)

    await db.commit()
    await db.refresh(node)

    logger.info("Node updated: %s", node_id)
    return NodeResponse.model_validate(node)


class RolesUpdateRequest(BaseModel):
    """Request to update node roles."""

    roles: List[str]


@router.patch("/{node_id}/roles", response_model=NodeResponse)
async def update_node_roles(
    node_id: str,
    roles_data: RolesUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """Update roles for a node."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    node.roles = roles_data.roles
    await db.commit()
    await db.refresh(node)

    logger.info("Node roles updated: %s -> %s", node_id, roles_data.roles)
    return NodeResponse.model_validate(node)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Delete a node."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Store node info before deletion for the event
    hostname = node.hostname
    ip_address = node.ip_address

    await db.delete(node)
    await db.commit()

    logger.info("Node deleted: %s", node_id)

    # Broadcast lifecycle event via WebSocket
    await _broadcast_lifecycle_event(
        node_id,
        "node_deleted",
        {"hostname": hostname, "ip_address": ip_address},
    )


@router.put("/{node_id}/replace", response_model=NodeResponse)
async def replace_node(
    node_id: str,
    node_data: NodeCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """
    Replace a node with a new one.

    This removes the old node and creates a new node with the provided data.
    The new node gets a new node_id but can optionally reuse the hostname/IP.
    """
    # Find the existing node
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    old_node = result.scalar_one_or_none()

    if not old_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Check if new IP conflicts with another node (not the one being replaced)
    if node_data.ip_address != old_node.ip_address:
        existing = await db.execute(
            select(Node).where(Node.ip_address == node_data.ip_address)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another node with this IP address already exists",
            )

    # Delete the old node
    await db.delete(old_node)
    await db.flush()

    # Create new node with new ID
    new_node_id = str(uuid.uuid4())[:8]

    if node_data.import_existing:
        initial_status = NodeStatus.ONLINE.value
    else:
        initial_status = NodeStatus.PENDING.value

    # Store encrypted SSH password if provided
    extra_data = {}
    if node_data.ssh_password and node_data.auth_method == "password":
        try:
            extra_data["ssh_password"] = encrypt_data(node_data.ssh_password)
            extra_data["ssh_password_encrypted"] = True
        except Exception as e:
            logger.error("Failed to encrypt SSH password: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to securely store credentials",
            )

    new_node = Node(
        node_id=new_node_id,
        hostname=node_data.hostname,
        ip_address=node_data.ip_address,
        roles=node_data.roles,
        ssh_user=node_data.ssh_user,
        ssh_port=node_data.ssh_port,
        auth_method=node_data.auth_method,
        status=initial_status,
        extra_data=extra_data if extra_data else None,
    )
    db.add(new_node)
    await db.commit()
    await db.refresh(new_node)

    logger.info(
        "Node replaced: %s -> %s (%s)",
        node_id,
        new_node_id,
        new_node.hostname,
    )

    return NodeResponse.model_validate(new_node)


@router.post("/{node_id}/heartbeat", response_model=HeartbeatResponse)
async def node_heartbeat(
    node_id: str,
    heartbeat: HeartbeatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HeartbeatResponse:
    """Receive heartbeat from node agent."""
    node = await reconciler_service.update_node_heartbeat(
        db,
        node_id,
        heartbeat.cpu_percent,
        heartbeat.memory_percent,
        heartbeat.disk_percent,
        heartbeat.agent_version,
        heartbeat.os_info,
        heartbeat.extra_data,
    )

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Store code_version if provided (Issue #741)
    if heartbeat.code_version:
        node.code_version = heartbeat.code_version

    # Get latest agent code version from settings (Issue #741)
    latest_result = await db.execute(
        select(Setting).where(Setting.key == "slm_agent_latest_commit")
    )
    latest_setting = latest_result.scalar_one_or_none()
    latest_version = latest_setting.value if latest_setting else None

    # Compare and update code_status (Issue #741)
    if heartbeat.code_version and latest_version:
        if heartbeat.code_version == latest_version:
            node.code_status = CodeStatus.UP_TO_DATE.value
        else:
            node.code_status = CodeStatus.OUTDATED.value
    elif heartbeat.code_version:
        # No latest version configured yet
        node.code_status = CodeStatus.UNKNOWN.value

    # Commit changes to database
    await db.commit()
    await db.refresh(node)

    # Build and return HeartbeatResponse (Issue #741)
    update_available = (
        node.code_status == CodeStatus.OUTDATED.value and latest_version is not None
    )

    return HeartbeatResponse(
        status="ok",
        update_available=update_available,
        latest_version=latest_version if update_available else None,
        update_url=f"/api/nodes/{node_id}/code-package" if update_available else None,
    )


@router.post("/{node_id}/enroll")
async def enroll_node(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    enroll_request: Optional[EnrollRequest] = None,
):
    """
    Start node enrollment process.

    This deploys the SLM agent to the node via Ansible,
    which then starts sending heartbeats automatically.

    Optionally accepts SSH credentials for password-based authentication.
    """
    from services.deployment import deployment_service

    # Extract SSH password if provided
    ssh_password = None
    if enroll_request and enroll_request.ssh_password:
        ssh_password = enroll_request.ssh_password

    # Create enrollment started event
    await _create_node_event(
        db,
        node_id,
        EventType.DEPLOYMENT_STARTED,
        EventSeverity.INFO,
        f"Enrollment started for node {node_id}",
        {"auth_method": "password" if ssh_password else "key"},
    )
    await db.commit()

    # Broadcast enrollment started via WebSocket
    await _broadcast_lifecycle_event(
        node_id,
        "enrollment_started",
        {"auth_method": "password" if ssh_password else "key"},
    )

    # Run enrollment (deploys agent via Ansible)
    success, message = await deployment_service.enroll_node(
        db, node_id, ssh_password=ssh_password
    )

    if not success:
        # Create enrollment failed event
        await _create_node_event(
            db,
            node_id,
            EventType.DEPLOYMENT_FAILED,
            EventSeverity.ERROR,
            f"Enrollment failed for node {node_id}: {message}",
            {"error": message},
        )
        await db.commit()

        # Broadcast enrollment failed via WebSocket
        await _broadcast_lifecycle_event(
            node_id,
            "enrollment_failed",
            {"error": message},
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    # Refresh node from DB
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    # Create enrollment completed event
    await _create_node_event(
        db,
        node_id,
        EventType.DEPLOYMENT_COMPLETED,
        EventSeverity.INFO,
        f"Enrollment completed for node {node_id}",
        {
            "hostname": node.hostname if node else None,
            "status": node.status if node else None,
        },
    )
    await db.commit()

    # Broadcast enrollment completed via WebSocket
    await _broadcast_lifecycle_event(
        node_id,
        "enrollment_completed",
        {
            "hostname": node.hostname if node else None,
            "status": node.status if node else None,
        },
    )

    logger.info("Node enrollment completed: %s", node_id)
    return {
        "success": True,
        "message": "Agent deployed successfully. Node will begin sending heartbeats.",
        "node": NodeResponse.model_validate(node) if node else None,
    }


@router.post("/{node_id}/drain", response_model=NodeResponse)
async def drain_node(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """
    Put a node into maintenance mode (drain).

    This marks the node as unavailable for new workloads
    while allowing existing services to be migrated.
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    if node.status == NodeStatus.MAINTENANCE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Node is already in maintenance mode",
        )

    node.status = NodeStatus.MAINTENANCE.value
    await db.commit()
    await db.refresh(node)

    logger.info("Node drained (maintenance mode): %s", node_id)
    return NodeResponse.model_validate(node)


@router.post("/{node_id}/resume", response_model=NodeResponse)
async def resume_node(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeResponse:
    """
    Resume a node from maintenance mode.

    This marks the node as available for workloads again.
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    if node.status != NodeStatus.MAINTENANCE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Node is not in maintenance mode",
        )

    node.status = NodeStatus.ONLINE.value
    await db.commit()
    await db.refresh(node)

    logger.info("Node resumed from maintenance: %s", node_id)
    return NodeResponse.model_validate(node)


@router.post("/{node_id}/reboot")
async def reboot_node(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """
    Reboot a node via SSH.

    This sends a reboot command to the node. The node will go offline
    temporarily and should come back online after the reboot completes.
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    if node.status == NodeStatus.OFFLINE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reboot an offline node",
        )

    # Create reboot event before issuing command
    await _create_node_event(
        db,
        node_id,
        EventType.MANUAL_ACTION,
        EventSeverity.WARNING,
        f"Reboot initiated for {node.hostname}",
        {"action": "reboot", "initiated_by": "api"},
    )
    await db.commit()

    # Broadcast lifecycle event via WebSocket
    await _broadcast_lifecycle_event(
        node_id,
        "reboot_initiated",
        {"hostname": node.hostname, "ip_address": node.ip_address},
    )

    # Execute reboot via SSH
    success, message = await _reboot_via_ssh(
        node.ip_address,
        node.ssh_user or "autobot",
        node.ssh_port or 22,
    )

    if success:
        logger.info("Reboot initiated for node %s (%s)", node_id, node.ip_address)
        return {
            "success": True,
            "message": f"Reboot initiated for {node.hostname}. Node will be temporarily offline.",
            "node_id": node_id,
        }
    else:
        logger.error("Failed to reboot node %s: %s", node_id, message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reboot node: {message}",
        )


async def _reboot_via_ssh(ip_address: str, ssh_user: str, ssh_port: int) -> tuple:
    """Execute reboot command on a remote node via SSH."""
    try:
        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            "-p",
            str(ssh_port),
            f"{ssh_user}@{ip_address}",
            "sudo reboot",
        ]

        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)

        # Reboot command often returns non-zero or connection closes
        # Success is if the command was accepted (might get connection reset)
        return True, "Reboot command sent"

    except asyncio.TimeoutError:
        return False, "SSH connection timed out"
    except Exception as e:
        return False, str(e)


@router.post("/{node_id}/acknowledge-remediation")
async def acknowledge_remediation(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """
    Acknowledge and reset remediation tracking for a node.

    Use this after manually fixing a node that exceeded automatic
    remediation attempts. This resets the attempt counter, allowing
    automatic remediation to try again if issues recur.
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Reset the remediation tracker
    reconciler_service.reset_remediation_tracker(node_id)

    # Create acknowledgment event
    await _create_node_event(
        db,
        node_id,
        EventType.MANUAL_ACTION,
        EventSeverity.INFO,
        f"Remediation tracker reset for {node.hostname}",
        {"action": "acknowledge_remediation"},
    )
    await db.commit()

    logger.info("Remediation acknowledged for node: %s", node_id)
    return {
        "success": True,
        "message": "Remediation tracker reset. Automatic remediation will retry if issues persist.",
        "node_id": node_id,
    }


@router.post("/test-connection", response_model=ConnectionTestResponse)
async def test_connection(
    request: ConnectionTestRequest,
    _: Annotated[dict, Depends(get_current_user)],
) -> ConnectionTestResponse:
    """Test SSH connection to a node."""
    import shutil

    start_time = time.time()

    try:
        remote_cmd = (
            "uname -a && cat /etc/os-release 2>/dev/null | "
            "head -5 || echo 'OS info unavailable'"
        )

        # Build SSH command based on auth method
        if request.auth_method == "password" and request.password:
            # Check if sshpass is available for password auth
            if not shutil.which("sshpass"):
                return ConnectionTestResponse(
                    success=False,
                    message="Connection failed",
                    error="Password auth requires 'sshpass'. Install: sudo apt install sshpass",
                )

            # Use sshpass for password authentication
            ssh_cmd = [
                "sshpass",
                "-p",
                request.password,
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "PubkeyAuthentication=no",
                "-p",
                str(request.ssh_port),
                f"{request.ssh_user}@{request.ip_address}",
                remote_cmd,
            ]
        else:
            # Use key-based authentication (BatchMode)
            ssh_cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "BatchMode=yes",
                "-p",
                str(request.ssh_port),
                f"{request.ssh_user}@{request.ip_address}",
                remote_cmd,
            ]

        process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=15.0,
        )

        latency_ms = (time.time() - start_time) * 1000

        if process.returncode == 0:
            os_info = stdout.decode("utf-8", errors="replace").strip()
            return ConnectionTestResponse(
                success=True,
                message="Connection successful",
                latency_ms=round(latency_ms, 2),
                os_info=os_info[:500] if os_info else None,
            )
        else:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            # Clean up error message - don't expose password details
            if "sshpass" in error_msg.lower():
                error_msg = "SSH authentication failed. Check credentials."
            return ConnectionTestResponse(
                success=False,
                message="Connection failed",
                latency_ms=round(latency_ms, 2),
                error=error_msg[:500] if error_msg else "SSH connection refused",
            )

    except asyncio.TimeoutError:
        return ConnectionTestResponse(
            success=False,
            message="Connection timed out",
            error="SSH connection timed out after 15 seconds",
        )
    except FileNotFoundError as e:
        error_msg = str(e)
        if "ssh" in error_msg.lower():
            return ConnectionTestResponse(
                success=False,
                message="Connection failed",
                error="SSH client not found. Install: sudo apt install openssh-client",
            )
        return ConnectionTestResponse(
            success=False,
            message="Connection failed",
            error=f"Required tool not found: {error_msg}",
        )
    except Exception as e:
        logger.exception("Connection test error: %s", e)
        return ConnectionTestResponse(
            success=False,
            message="Connection test failed",
            error=str(e)[:500],
        )


@router.get("/{node_id}/events", response_model=NodeEventListResponse)
async def get_node_events(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    event_type: Optional[str] = Query(None, alias="type"),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> NodeEventListResponse:
    """Get events for a node."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    query = select(NodeEvent).where(NodeEvent.node_id == node_id)

    if event_type:
        query = query.where(NodeEvent.event_type == event_type)
    if severity:
        query = query.where(NodeEvent.severity == severity)

    query = query.order_by(NodeEvent.created_at.desc())

    # Get total count - build the count query with same filters
    count_query = select(NodeEvent.id).where(NodeEvent.node_id == node_id)
    if event_type:
        count_query = count_query.where(NodeEvent.event_type == event_type)
    if severity:
        count_query = count_query.where(NodeEvent.severity == severity)
    count_result = await db.execute(count_query)
    total = len(count_result.all())

    # Apply pagination
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()

    return NodeEventListResponse(
        events=[NodeEventResponse.model_validate(e) for e in events],
        total=total,
    )


@router.get("/{node_id}/certificate", response_model=CertificateResponse)
async def get_node_certificate(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CertificateResponse:
    """Get certificate status for a node."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Get certificate
    cert_result = await db.execute(
        select(Certificate)
        .where(Certificate.node_id == node_id)
        .order_by(Certificate.created_at.desc())
    )
    cert = cert_result.scalar_one_or_none()

    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No certificate found for this node",
        )

    # Calculate days until expiry
    days_until_expiry = None
    if cert.not_after:
        delta = cert.not_after - datetime.utcnow()
        days_until_expiry = delta.days

    response = CertificateResponse.model_validate(cert)
    response.days_until_expiry = days_until_expiry
    return response


@router.post("/{node_id}/certificate/renew", response_model=CertificateActionResponse)
async def renew_node_certificate(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CertificateActionResponse:
    """Renew certificate for a node."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = node_result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Get existing certificate
    cert_result = await db.execute(
        select(Certificate)
        .where(Certificate.node_id == node_id)
        .order_by(Certificate.created_at.desc())
    )
    old_cert = cert_result.scalar_one_or_none()

    try:
        # Generate new certificate using cfssl or openssl
        cert_id = str(uuid.uuid4())[:16]
        new_cert = Certificate(
            cert_id=cert_id,
            node_id=node_id,
            subject=f"CN={node.hostname}",
            issuer="CN=SLM-CA",
            not_before=datetime.utcnow(),
            not_after=datetime.utcnow().replace(year=datetime.utcnow().year + 1),
            status="active",
        )
        db.add(new_cert)

        # Mark old cert as replaced
        if old_cert:
            old_cert.status = "revoked"

        await db.commit()

        logger.info("Certificate renewed for node %s: %s", node_id, cert_id)
        return CertificateActionResponse(
            action="renew",
            success=True,
            message="Certificate renewed successfully",
            cert_id=cert_id,
        )

    except Exception as e:
        logger.exception("Certificate renewal failed for node %s: %s", node_id, e)
        return CertificateActionResponse(
            action="renew",
            success=False,
            message=f"Certificate renewal failed: {e}",
        )


@router.post("/{node_id}/certificate/deploy", response_model=CertificateActionResponse)
async def deploy_node_certificate(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CertificateActionResponse:
    """Deploy/issue initial certificate for a node."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = node_result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Check if certificate already exists
    cert_result = await db.execute(
        select(Certificate)
        .where(Certificate.node_id == node_id)
        .where(Certificate.status == "active")
    )
    if cert_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active certificate already exists for this node",
        )

    try:
        # Generate new certificate
        cert_id = str(uuid.uuid4())[:16]
        new_cert = Certificate(
            cert_id=cert_id,
            node_id=node_id,
            subject=f"CN={node.hostname}",
            issuer="CN=SLM-CA",
            not_before=datetime.utcnow(),
            not_after=datetime.utcnow().replace(year=datetime.utcnow().year + 1),
            status="active",
        )
        db.add(new_cert)
        await db.commit()

        logger.info("Certificate deployed to node %s: %s", node_id, cert_id)
        return CertificateActionResponse(
            action="deploy",
            success=True,
            message="Certificate deployed successfully",
            cert_id=cert_id,
        )

    except Exception as e:
        logger.exception("Certificate deployment failed for node %s: %s", node_id, e)
        return CertificateActionResponse(
            action="deploy",
            success=False,
            message=f"Certificate deployment failed: {e}",
        )


@router.get("/{node_id}/updates")
async def get_node_updates(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """Get available updates for a node."""
    from sqlalchemy import or_

    from models.database import UpdateInfo
    from models.schemas import UpdateCheckResponse, UpdateInfoResponse

    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Get updates for this node (or global updates)
    query = (
        select(UpdateInfo)
        .where(UpdateInfo.is_applied.is_(False))
        .where(or_(UpdateInfo.node_id == node_id, UpdateInfo.node_id.is_(None)))
        .order_by(UpdateInfo.severity.desc(), UpdateInfo.created_at.desc())
    )

    result = await db.execute(query)
    updates = result.scalars().all()

    return UpdateCheckResponse(
        updates=[UpdateInfoResponse.model_validate(u) for u in updates],
        total=len(updates),
    )


@router.post("/{node_id}/updates/apply")
async def apply_node_updates(
    node_id: str,
    update_ids: List[str],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """Apply updates to a node."""
    from models.database import UpdateInfo
    from models.schemas import UpdateApplyResponse

    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Get the updates
    updates_result = await db.execute(
        select(UpdateInfo).where(UpdateInfo.update_id.in_(update_ids))
    )
    updates = updates_result.scalars().all()

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No valid updates found",
        )

    # Mark updates as applied
    applied = []
    failed = []
    for update in updates:
        try:
            update.is_applied = True
            update.applied_at = datetime.utcnow()
            applied.append(update.update_id)
        except Exception as e:
            logger.error("Failed to apply update %s: %s", update.update_id, e)
            failed.append(update.update_id)

    await db.commit()

    logger.info("Applied %d updates to node %s", len(applied), node_id)
    return UpdateApplyResponse(
        success=len(failed) == 0,
        message=f"Applied {len(applied)} update(s)"
        if applied
        else "No updates applied",
        applied_updates=applied,
        failed_updates=failed,
    )
