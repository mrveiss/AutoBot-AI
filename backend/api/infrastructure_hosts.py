# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Infrastructure Hosts API

REST API endpoints for managing user-defined SSH/VNC infrastructure hosts.
Hosts are stored as encrypted secrets and become queryable infrastructure knowledge.

Related Issue: #715 - Dynamic SSH/VNC host management via secrets

Endpoints:
- GET    /api/infrastructure/hosts          - List all hosts
- POST   /api/infrastructure/hosts          - Create a new host
- GET    /api/infrastructure/hosts/{id}     - Get host details
- PUT    /api/infrastructure/hosts/{id}     - Update host
- DELETE /api/infrastructure/hosts/{id}     - Delete host
- POST   /api/infrastructure/hosts/{id}/test - Test host connectivity
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.infrastructure_host_service import (
    AuthType,
    HostCapability,
    InfrastructureHostService,
    get_infrastructure_host_service,
)
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/infrastructure", tags=["infrastructure"])


# Request/Response Models


class CreateHostRequest(BaseModel):
    """Request model for creating an infrastructure host."""

    name: str = Field(..., description="Unique name for the host")
    host: str = Field(..., description="IP address or hostname")
    username: str = Field(default="root", description="SSH username")
    auth_type: str = Field(default="ssh_key", description="Authentication type: ssh_key or password")

    # Credentials (sensitive - will be encrypted)
    ssh_key: Optional[str] = Field(default=None, description="SSH private key content")
    ssh_key_passphrase: Optional[str] = Field(default=None, description="SSH key passphrase")
    ssh_password: Optional[str] = Field(default=None, description="SSH password")
    vnc_password: Optional[str] = Field(default=None, description="VNC password")

    # Connection settings
    ssh_port: int = Field(default=22, description="SSH port")
    vnc_port: Optional[int] = Field(default=None, description="VNC port")
    capabilities: List[str] = Field(default=["ssh"], description="Host capabilities: ssh, vnc")

    # Metadata for knowledge base
    description: Optional[str] = Field(default=None, description="Human-readable description")
    tags: List[str] = Field(default=[], description="Tags for categorization")
    os: Optional[str] = Field(default=None, description="Operating system")
    purpose: Optional[str] = Field(default=None, description="Purpose/role of the host")

    # Scope
    scope: str = Field(default="general", description="Scope: general or chat")
    chat_id: Optional[str] = Field(default=None, description="Chat ID if scope is chat")


class UpdateHostRequest(BaseModel):
    """Request model for updating an infrastructure host."""

    name: Optional[str] = None
    description: Optional[str] = None
    host: Optional[str] = None
    ssh_port: Optional[int] = None
    vnc_port: Optional[int] = None
    capabilities: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    os: Optional[str] = None
    purpose: Optional[str] = None

    # Credentials (optional update)
    ssh_key: Optional[str] = None
    ssh_password: Optional[str] = None
    vnc_password: Optional[str] = None


class HostResponse(BaseModel):
    """Response model for infrastructure host."""

    id: str
    name: str
    description: Optional[str]
    host: str
    ssh_port: int
    vnc_port: Optional[int]
    capabilities: List[str]
    tags: List[str]
    os: Optional[str]
    purpose: Optional[str]
    username: str
    auth_type: str
    commands_extracted: bool
    last_connected: Optional[str]
    connection_count: int
    created_at: str
    updated_at: str
    scope: str
    chat_id: Optional[str]


class HostListResponse(BaseModel):
    """Response model for host list."""

    hosts: List[HostResponse]
    total: int


class ConnectionTestResponse(BaseModel):
    """Response model for connection test."""

    success: bool
    host: str
    ssh_available: bool
    vnc_available: bool
    ssh_error: Optional[str]
    vnc_error: Optional[str]
    latency_ms: Optional[float]


# API Endpoints


@router.get("/hosts", response_model=HostListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_infrastructure_hosts",
    error_code_prefix="INFRA",
)
async def list_hosts(
    capability: Optional[str] = Query(default=None, description="Filter by capability: ssh or vnc"),
    scope: Optional[str] = Query(default=None, description="Filter by scope: general or chat"),
    chat_id: Optional[str] = Query(default=None, description="Filter by chat ID"),
    tags: Optional[str] = Query(default=None, description="Filter by tags (comma-separated)"),
):
    """
    List infrastructure hosts with optional filtering.

    Query Parameters:
    - capability: Filter by capability (ssh, vnc)
    - scope: Filter by scope (general, chat)
    - chat_id: Filter by chat ID
    - tags: Filter by tags (comma-separated)

    Returns:
    - List of hosts matching the filters
    """
    service = get_infrastructure_host_service()

    # Parse capability filter
    cap_filter = None
    if capability:
        try:
            cap_filter = HostCapability(capability)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid capability: {capability}")

    # Parse tags filter
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    hosts = service.list_hosts(
        capability=cap_filter,
        scope=scope,
        chat_id=chat_id,
        tags=tag_list,
    )

    return HostListResponse(
        hosts=[HostResponse(**h.to_dict()) for h in hosts],
        total=len(hosts),
    )


@router.post("/hosts", response_model=HostResponse, status_code=201)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_infrastructure_host",
    error_code_prefix="INFRA",
)
async def create_host(request: CreateHostRequest):
    """
    Create a new infrastructure host.

    The host will be stored as an encrypted secret and its metadata
    will be indexed in the knowledge base for AI queries.

    Request Body:
    - name: Unique name for the host
    - host: IP address or hostname
    - username: SSH username
    - auth_type: ssh_key or password
    - ssh_key/ssh_password: Credentials based on auth_type
    - capabilities: List of capabilities (ssh, vnc)
    - description, tags, os, purpose: Metadata for knowledge base

    Returns:
    - Created host details
    """
    service = get_infrastructure_host_service()

    # Parse capabilities
    capabilities = []
    for cap in request.capabilities:
        try:
            capabilities.append(HostCapability(cap))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid capability: {cap}")

    # Parse auth type
    try:
        auth_type = AuthType(request.auth_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid auth_type: {request.auth_type}")

    # Validate credentials based on auth type
    if auth_type == AuthType.SSH_KEY and not request.ssh_key:
        raise HTTPException(status_code=400, detail="SSH key is required when auth_type is ssh_key")
    if auth_type == AuthType.PASSWORD and not request.ssh_password:
        raise HTTPException(status_code=400, detail="SSH password is required when auth_type is password")

    # Validate VNC
    if HostCapability.VNC in capabilities and not request.vnc_port:
        raise HTTPException(status_code=400, detail="VNC port is required when VNC capability is enabled")

    try:
        result = service.create_host(
            name=request.name,
            host=request.host,
            username=request.username,
            auth_type=auth_type,
            ssh_key=request.ssh_key,
            ssh_key_passphrase=request.ssh_key_passphrase,
            ssh_password=request.ssh_password,
            vnc_password=request.vnc_password,
            ssh_port=request.ssh_port,
            vnc_port=request.vnc_port,
            capabilities=capabilities,
            description=request.description,
            tags=request.tags,
            os=request.os,
            purpose=request.purpose,
            scope=request.scope,
            chat_id=request.chat_id,
        )

        # Fetch the created host to return full details
        host = service.get_host(result["id"])
        if not host:
            raise HTTPException(status_code=500, detail="Failed to retrieve created host")

        return HostResponse(**host.to_dict())

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/hosts/{host_id}", response_model=HostResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_infrastructure_host",
    error_code_prefix="INFRA",
)
async def get_host(host_id: str):
    """
    Get details of a specific infrastructure host.

    Path Parameters:
    - host_id: The host ID

    Returns:
    - Host details (credentials are not included)
    """
    service = get_infrastructure_host_service()

    host = service.get_host(host_id)
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    return HostResponse(**host.to_dict())


@router.put("/hosts/{host_id}", response_model=HostResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_infrastructure_host",
    error_code_prefix="INFRA",
)
async def update_host(host_id: str, request: UpdateHostRequest):
    """
    Update an infrastructure host.

    Path Parameters:
    - host_id: The host ID

    Request Body:
    - Any fields to update (all optional)

    Returns:
    - Updated host details
    """
    service = get_infrastructure_host_service()

    # Verify host exists
    existing = service.get_host(host_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Host not found")

    # Parse capabilities if provided
    capabilities = None
    if request.capabilities is not None:
        capabilities = []
        for cap in request.capabilities:
            try:
                capabilities.append(HostCapability(cap))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid capability: {cap}")

    success = service.update_host(
        host_id=host_id,
        name=request.name,
        description=request.description,
        host=request.host,
        ssh_port=request.ssh_port,
        vnc_port=request.vnc_port,
        capabilities=capabilities,
        tags=request.tags,
        os=request.os,
        purpose=request.purpose,
        ssh_key=request.ssh_key,
        ssh_password=request.ssh_password,
        vnc_password=request.vnc_password,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update host")

    # Return updated host
    host = service.get_host(host_id)
    return HostResponse(**host.to_dict())


@router.delete("/hosts/{host_id}", status_code=204)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_infrastructure_host",
    error_code_prefix="INFRA",
)
async def delete_host(
    host_id: str,
    hard_delete: bool = Query(default=False, description="Permanently delete the host"),
):
    """
    Delete an infrastructure host.

    Path Parameters:
    - host_id: The host ID

    Query Parameters:
    - hard_delete: If true, permanently delete. Otherwise soft delete.

    Returns:
    - 204 No Content on success
    """
    service = get_infrastructure_host_service()

    success = service.delete_host(host_id, hard_delete=hard_delete)
    if not success:
        raise HTTPException(status_code=404, detail="Host not found")

    return None


@router.post("/hosts/{host_id}/test", response_model=ConnectionTestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_infrastructure_host",
    error_code_prefix="INFRA",
)
async def test_host_connection(
    host_id: str,
    timeout: float = Query(default=10.0, description="Connection timeout in seconds"),
):
    """
    Test connectivity to an infrastructure host.

    Tests SSH and VNC port availability based on host capabilities.

    Path Parameters:
    - host_id: The host ID

    Query Parameters:
    - timeout: Connection timeout in seconds (default 10)

    Returns:
    - Connection test results for SSH and VNC
    """
    service = get_infrastructure_host_service()

    host = service.get_host(host_id)
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    result = await service.test_connection(host_id, timeout=timeout)

    return ConnectionTestResponse(**result)
