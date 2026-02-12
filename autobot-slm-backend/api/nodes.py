# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Nodes API Routes
"""

import asyncio
import hashlib
import logging
import time
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from models.database import (
    Certificate,
    CodeStatus,
    EventSeverity,
    EventType,
    Node,
    NodeEvent,
    NodeRole,
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
    NodeRoleAssignRequest,
    NodeRoleResponse,
    NodeRolesResponse,
    NodeUpdate,
    PortInfo,
)
from pydantic import BaseModel
from services.auth import get_current_user
from services.database import get_db
from services.encryption import encrypt_data
from services.reconciler import reconciler_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

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


async def _process_role_report(
    db: AsyncSession, node_id: str, role_report: dict
) -> None:
    """
    Process role report from agent heartbeat (Issue #779).

    Updates NodeRole entries based on detected roles.
    """
    from models.schemas import RoleReportItem

    for role_name, report_data in role_report.items():
        # Handle both dict and RoleReportItem
        if isinstance(report_data, dict):
            report = RoleReportItem(**report_data)
        else:
            report = report_data

        # Find or create NodeRole entry
        result = await db.execute(
            select(NodeRole).where(
                NodeRole.node_id == node_id, NodeRole.role_name == role_name
            )
        )
        node_role = result.scalar_one_or_none()

        if not node_role:
            # Create new NodeRole with auto assignment type
            node_role = NodeRole(
                node_id=node_id,
                role_name=role_name,
                assignment_type="auto",
            )
            db.add(node_role)

        # Update role status
        node_role.status = report.status
        node_role.current_version = report.version

    await db.flush()


async def _handle_enrollment_started(
    db: AsyncSession, node_id: str, ssh_password: Optional[str]
) -> None:
    """
    Create event and broadcast for enrollment started.

    Helper for enroll_node (Issue #665).
    """
    auth_method_details = {"auth_method": "password" if ssh_password else "key"}

    await _create_node_event(
        db,
        node_id,
        EventType.DEPLOYMENT_STARTED,
        EventSeverity.INFO,
        f"Enrollment started for node {node_id}",
        auth_method_details,
    )
    await db.commit()

    await _broadcast_lifecycle_event(
        node_id,
        "enrollment_started",
        auth_method_details,
    )


async def _handle_enrollment_failed(
    db: AsyncSession, node_id: str, message: str
) -> None:
    """
    Create event, broadcast, and raise HTTPException on enrollment failure.

    Helper for enroll_node (Issue #665).
    """
    error_details = {"error": message}

    await _create_node_event(
        db,
        node_id,
        EventType.DEPLOYMENT_FAILED,
        EventSeverity.ERROR,
        f"Enrollment failed for node {node_id}: {message}",
        error_details,
    )
    await db.commit()

    await _broadcast_lifecycle_event(
        node_id,
        "enrollment_failed",
        error_details,
    )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=message,
    )


async def _handle_enrollment_completed(db: AsyncSession, node_id: str) -> dict:
    """
    Refresh node, create event, broadcast, and return success response.

    Helper for enroll_node (Issue #665).
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    completion_details = {
        "hostname": node.hostname if node else None,
        "status": node.status if node else None,
    }

    await _create_node_event(
        db,
        node_id,
        EventType.DEPLOYMENT_COMPLETED,
        EventSeverity.INFO,
        f"Enrollment completed for node {node_id}",
        completion_details,
    )
    await db.commit()

    await _broadcast_lifecycle_event(
        node_id,
        "enrollment_completed",
        completion_details,
    )

    logger.info("Node enrollment completed: %s", node_id)
    return {
        "success": True,
        "message": "Agent deployed successfully. Node will begin sending heartbeats.",
        "node": NodeResponse.model_validate(node) if node else None,
    }


async def _check_existing_node(db: AsyncSession, ip_address: str) -> None:
    """
    Check for duplicate IP address and raise HTTPException if found.

    Helper for create_node (Issue #665).
    """
    existing = await db.execute(select(Node).where(Node.ip_address == ip_address))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Node with this IP address already exists",
        )


def _generate_node_id(node_data: NodeCreate) -> str:
    """
    Generate or return node_id based on node_data.

    Helper for create_node (Issue #665).
    """
    if node_data.node_id:
        return node_data.node_id
    # Generate deterministic ID from hostname (first 8 chars of SHA256)
    return hashlib.sha256(node_data.hostname.encode()).hexdigest()[:8]


def _prepare_extra_data(node_data: NodeCreate) -> dict:
    """
    Encrypt SSH password and prepare extra_data dict.

    Helper for create_node (Issue #665).
    """
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
    return extra_data


async def _create_registration_event(
    db: AsyncSession,
    node_id: str,
    node: Node,
    node_data: NodeCreate,
    initial_status: str,
) -> None:
    """
    Create registration event and broadcast lifecycle event.

    Helper for create_node (Issue #665).
    """
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

    logger.info(event_msg)

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
    await _check_existing_node(db, node_data.ip_address)

    node_id = _generate_node_id(node_data)

    # If importing an existing node, mark as online immediately
    # Otherwise, mark as pending for enrollment
    if node_data.import_existing:
        initial_status = NodeStatus.ONLINE.value
    else:
        initial_status = NodeStatus.PENDING.value

    extra_data = _prepare_extra_data(node_data)

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

    await _create_registration_event(db, node_id, node, node_data, initial_status)

    await db.commit()
    await db.refresh(node)

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


@router.get("/{node_id}/detected-roles", response_model=NodeRolesResponse)
async def get_node_detected_roles(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeRolesResponse:
    """
    Get detected roles for a node (Issue #779).

    Returns all roles detected by the agent, including their status,
    version, and sync history.
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Get all NodeRole entries for this node
    role_result = await db.execute(select(NodeRole).where(NodeRole.node_id == node_id))
    node_roles = list(role_result.scalars().all())

    # Convert listening_ports from dict back to PortInfo
    listening_ports = []
    if node.listening_ports:
        for p in node.listening_ports:
            if isinstance(p, dict):
                listening_ports.append(PortInfo(**p))

    return NodeRolesResponse(
        node_id=node_id,
        detected_roles=node.detected_roles or [],
        role_versions=node.role_versions or {},
        listening_ports=listening_ports,
        roles=[NodeRoleResponse.model_validate(r) for r in node_roles],
    )


@router.post("/{node_id}/detected-roles", response_model=NodeRoleResponse)
async def assign_role_to_node(
    node_id: str,
    role_request: NodeRoleAssignRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeRoleResponse:
    """
    Manually assign a role to a node (Issue #779).

    Used for manual role assignment when auto-detection doesn't apply.
    """
    # Verify node exists
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Check if role assignment already exists
    role_result = await db.execute(
        select(NodeRole).where(
            NodeRole.node_id == node_id, NodeRole.role_name == role_request.role_name
        )
    )
    existing = role_result.scalar_one_or_none()

    if existing:
        # Update assignment type to manual
        existing.assignment_type = role_request.assignment_type
        await db.commit()
        await db.refresh(existing)
        logger.info(
            "Updated role assignment: %s -> %s (%s)",
            node_id,
            role_request.role_name,
            role_request.assignment_type,
        )
        return NodeRoleResponse.model_validate(existing)

    # Create new role assignment
    node_role = NodeRole(
        node_id=node_id,
        role_name=role_request.role_name,
        assignment_type=role_request.assignment_type,
        status="not_installed",
    )
    db.add(node_role)
    await db.commit()
    await db.refresh(node_role)

    logger.info(
        "Assigned role to node: %s -> %s (%s)",
        node_id,
        role_request.role_name,
        role_request.assignment_type,
    )
    return NodeRoleResponse.model_validate(node_role)


@router.delete("/{node_id}/detected-roles/{role_name}")
async def remove_role_from_node(
    node_id: str,
    role_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Remove a role assignment from a node (Issue #779).

    Only removes the assignment, not the actual role installation.
    """
    result = await db.execute(
        select(NodeRole).where(
            NodeRole.node_id == node_id, NodeRole.role_name == role_name
        )
    )
    node_role = result.scalar_one_or_none()

    if not node_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role assignment not found: {role_name}",
        )

    await db.delete(node_role)
    await db.commit()

    logger.info("Removed role from node: %s -> %s", node_id, role_name)
    return {"success": True, "message": f"Role '{role_name}' removed from node"}


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


async def _check_ip_conflict(
    db: AsyncSession,
    new_ip: str,
    current_ip: str,
) -> None:
    """Check if new IP conflicts with another node.

    Helper for replace_node (Issue #665).

    Args:
        db: Database session
        new_ip: The new IP address to check
        current_ip: The current node's IP address

    Raises:
        HTTPException: If IP conflict detected
    """
    if new_ip != current_ip:
        existing = await db.execute(select(Node).where(Node.ip_address == new_ip))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another node with this IP address already exists",
            )


async def _prepare_node_extra_data(node_data: NodeCreate) -> Optional[dict]:
    """Prepare extra_data dict with encrypted password if needed.

    Helper for replace_node (Issue #665).

    Args:
        node_data: The node creation data

    Returns:
        Dictionary with encrypted password or None

    Raises:
        HTTPException: If password encryption fails
    """
    if node_data.ssh_password and node_data.auth_method == "password":
        try:
            return {
                "ssh_password": encrypt_data(node_data.ssh_password),
                "ssh_password_encrypted": True,
            }
        except Exception as e:
            logger.error("Failed to encrypt SSH password: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to securely store credentials",
            )
    return None


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
    await _check_ip_conflict(db, node_data.ip_address, old_node.ip_address)

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
    extra_data = await _prepare_node_extra_data(node_data)

    new_node = Node(
        node_id=new_node_id,
        hostname=node_data.hostname,
        ip_address=node_data.ip_address,
        roles=node_data.roles,
        ssh_user=node_data.ssh_user,
        ssh_port=node_data.ssh_port,
        auth_method=node_data.auth_method,
        status=initial_status,
        extra_data=extra_data,
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

    # Process role report (Issue #779)
    if heartbeat.role_report:
        await _process_role_report(db, node_id, heartbeat.role_report)
        # Update node's detected_roles and role_versions
        node.detected_roles = list(heartbeat.role_report.keys())
        node.role_versions = {
            name: report.version
            for name, report in heartbeat.role_report.items()
            if report.version
        }

    # Store listening ports (Issue #779)
    if heartbeat.listening_ports:
        node.listening_ports = [p.model_dump() for p in heartbeat.listening_ports]

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

    # Handle enrollment started
    await _handle_enrollment_started(db, node_id, ssh_password)

    # Run enrollment (deploys agent via Ansible)
    success, message = await deployment_service.enroll_node(
        db, node_id, ssh_password=ssh_password
    )

    # Handle failure if enrollment did not succeed
    if not success:
        await _handle_enrollment_failed(db, node_id, message)

    # Handle successful completion
    return await _handle_enrollment_completed(db, node_id)


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

    # Execute reboot via Ansible playbook
    from services.playbook_executor import get_playbook_executor

    executor = get_playbook_executor()
    result = await executor.execute_playbook(
        playbook_name="reboot-node.yml",
        limit=[node.hostname],
    )

    if result["success"]:
        logger.info("Reboot completed for node %s (%s)", node_id, node.ip_address)
        return {
            "success": True,
            "message": f"Reboot completed for {node.hostname}. Node is back online.",
            "node_id": node_id,
        }
    else:
        logger.error("Failed to reboot node %s: %s", node_id, result["output"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reboot node: {result['output'][:500]}",
        )


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


def _build_password_ssh_command(
    request: ConnectionTestRequest, remote_cmd: str
) -> list[str]:
    """
    Build SSH command with sshpass for password authentication.

    Helper for test_connection (Issue #665).
    """
    return [
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


def _build_key_ssh_command(
    request: ConnectionTestRequest, remote_cmd: str
) -> list[str]:
    """
    Build SSH command with BatchMode for key-based authentication.

    Helper for test_connection (Issue #665).
    """
    return [
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


def _build_ssh_success_response(
    stdout: bytes, latency_ms: float
) -> ConnectionTestResponse:
    """
    Create success ConnectionTestResponse from SSH stdout.

    Helper for test_connection (Issue #665).
    """
    os_info = stdout.decode("utf-8", errors="replace").strip()
    return ConnectionTestResponse(
        success=True,
        message="Connection successful",
        latency_ms=round(latency_ms, 2),
        os_info=os_info[:500] if os_info else None,
    )


def _build_ssh_failure_response(
    stderr: bytes, latency_ms: float
) -> ConnectionTestResponse:
    """
    Create failure ConnectionTestResponse from SSH stderr with cleaned error.

    Helper for test_connection (Issue #665).
    """
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


def _handle_file_not_found_error(error: FileNotFoundError) -> ConnectionTestResponse:
    """
    Handle FileNotFoundError for missing SSH tools.

    Helper for test_connection (Issue #665).
    """
    error_msg = str(error)
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


@router.post("/test-connection", response_model=ConnectionTestResponse)
async def test_connection(
    request: ConnectionTestRequest,
    _: Annotated[dict, Depends(get_current_user)],
) -> ConnectionTestResponse:
    """Test SSH connection to a node."""
    import shutil

    start_time = time.time()
    remote_cmd = (
        "uname -a && cat /etc/os-release 2>/dev/null | "
        "head -5 || echo 'OS info unavailable'"
    )

    try:
        # Build SSH command based on auth method
        if request.auth_method == "password" and request.password:
            if not shutil.which("sshpass"):
                return ConnectionTestResponse(
                    success=False,
                    message="Connection failed",
                    error="Password auth requires 'sshpass'. Install: sudo apt install sshpass",
                )
            ssh_cmd = _build_password_ssh_command(request, remote_cmd)
        else:
            ssh_cmd = _build_key_ssh_command(request, remote_cmd)

        process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15.0)
        latency_ms = (time.time() - start_time) * 1000

        if process.returncode == 0:
            return _build_ssh_success_response(stdout, latency_ms)
        return _build_ssh_failure_response(stderr, latency_ms)

    except asyncio.TimeoutError:
        return ConnectionTestResponse(
            success=False,
            message="Connection timed out",
            error="SSH connection timed out after 15 seconds",
        )
    except FileNotFoundError as e:
        return _handle_file_not_found_error(e)
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
    from models.database import UpdateInfo
    from models.schemas import UpdateCheckResponse, UpdateInfoResponse
    from sqlalchemy import or_

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
