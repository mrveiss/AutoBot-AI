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

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Certificate, Node, NodeEvent, NodeStatus
from models.schemas import (
    CertificateActionResponse,
    CertificateResponse,
    ConnectionTestRequest,
    ConnectionTestResponse,
    HeartbeatRequest,
    NodeCreate,
    NodeEventListResponse,
    NodeEventResponse,
    NodeListResponse,
    NodeResponse,
    NodeUpdate,
)
from services.auth import get_current_user
from services.database import get_db
from services.reconciler import reconciler_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])


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

    node = Node(
        node_id=node_id,
        hostname=node_data.hostname,
        ip_address=node_data.ip_address,
        roles=node_data.roles,
        ssh_user=node_data.ssh_user,
        ssh_port=node_data.ssh_port,
        auth_method=node_data.auth_method,
        status=initial_status,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)

    if node_data.import_existing:
        logger.info("Existing node imported: %s (%s)", node.hostname, node.ip_address)
    else:
        logger.info("Node registered: %s (%s)", node.hostname, node.ip_address)

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

    await db.delete(node)
    await db.commit()

    logger.info("Node deleted: %s", node_id)


@router.post("/{node_id}/heartbeat", response_model=NodeResponse)
async def node_heartbeat(
    node_id: str,
    heartbeat: HeartbeatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NodeResponse:
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

    return NodeResponse.model_validate(node)


@router.post("/{node_id}/enroll")
async def enroll_node(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """
    Start node enrollment process.

    This deploys the SLM agent to the node via Ansible,
    which then starts sending heartbeats automatically.
    """
    from services.deployment import deployment_service

    # Run enrollment (deploys agent via Ansible)
    success, message = await deployment_service.enroll_node(db, node_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    # Refresh node from DB
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    logger.info("Node enrollment completed: %s", node_id)
    return {
        "success": True,
        "message": "Agent deployed successfully. Node will begin sending heartbeats.",
        "node": NodeResponse.model_validate(node) if node else None,
    }


@router.post("/test-connection", response_model=ConnectionTestResponse)
async def test_connection(
    request: ConnectionTestRequest,
    _: Annotated[dict, Depends(get_current_user)],
) -> ConnectionTestResponse:
    """Test SSH connection to a node."""
    start_time = time.time()

    try:
        # Build SSH command for connection test
        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes",
            "-p", str(request.ssh_port),
            f"{request.ssh_user}@{request.ip_address}",
            "uname -a && cat /etc/os-release 2>/dev/null | head -5 || echo 'OS info unavailable'",
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

    # Get total count
    count_result = await db.execute(
        select(NodeEvent.id).where(query.whereclause or True)
    )
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
        .where(UpdateInfo.is_applied == False)
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
        message=f"Applied {len(applied)} update(s)" if applied else "No updates applied",
        applied_updates=applied,
        failed_updates=failed,
    )
