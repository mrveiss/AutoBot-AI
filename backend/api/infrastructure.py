# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Infrastructure Management API

Complete REST API for Infrastructure as Code (IaC) platform including:
- Host inventory management
- Deployment orchestration via Celery
- SSH credential provisioning
- Infrastructure statistics and monitoring
"""

import logging
import os
import socket
from datetime import datetime
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from backend.schemas.infrastructure import (
    DeploymentCreate,
    DeploymentDetailResponse,
    DeploymentResponse,
    HostDetailResponse,
    HostResponse,
    HostStatusResponse,
    HostUpdate,
    ProvisionKeyRequest,
    ProvisionKeyResponse,
    RoleResponse,
    StatisticsResponse,
)
from backend.services.infrastructure_db import InfrastructureDB
from backend.services.ssh_provisioner import SSHKeyProvisioner
from backend.tasks.deployment_tasks import deploy_host
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Infrastructure as Code"])

# Initialize services
db = InfrastructureDB()
ssh_provisioner = SSHKeyProvisioner()


# ==================== Host Management Endpoints ====================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_hosts",
    error_code_prefix="INFRASTRUCTURE",
)
@router.get("/hosts")
async def list_hosts(
    role: Optional[str] = Query(None, description="Filter by role name"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """
    List all infrastructure hosts with optional filtering and database-level pagination

    PERFORMANCE FEATURES:
    - Database-level pagination (OFFSET/LIMIT) - only requested page loaded from database
    - Eager loading of relationships (role, credentials, deployments) - prevents N+1 queries
    - Single optimized query instead of 101+ queries for 100 hosts

    Query Parameters:
    - role: Filter hosts by role name (e.g., 'frontend', 'redis')
    - status: Filter hosts by status (e.g., 'deployed', 'healthy')
    - page: Page number (starts at 1)
    - page_size: Number of hosts per page (max 100)

    Returns:
    - hosts: List of hosts matching filters (current page only)
    - pagination: Metadata including total count, current page, total pages
    """
    try:
        filters = {}
        if role:
            filters["role"] = role
        if status:
            filters["status"] = status

        # Database-level pagination with eager loading (prevents N+1 queries)
        result = db.get_hosts(filters=filters, page=page, page_size=page_size)

        logger.info(
            f"Listed {len(result['hosts'])} hosts "
            f"(page {result['page']}/{result['total_pages']}, "
            f"total: {result['total']}, filters: {filters})"
        )

        return {
            "hosts": result["hosts"],
            "pagination": {
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
                "total_pages": result["total_pages"],
            },
        }

    except Exception as e:
        logger.error(f"Error listing hosts: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing hosts: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_host",
    error_code_prefix="INFRASTRUCTURE",
)
@router.post("/hosts", response_model=HostResponse, status_code=201)
async def create_host(
    hostname: str = Form(..., description="Hostname of the infrastructure host"),
    ip_address: str = Form(..., description="IP address (IPv4 or IPv6)"),
    role: str = Form(..., description="Infrastructure role name"),
    ssh_port: int = Form(22, description="SSH port number"),
    ssh_user: str = Form("autobot", description="SSH username"),
    auth_method: str = Form(
        "key", description="Authentication method: 'password' or 'key'"
    ),
    password: Optional[str] = Form(
        None, description="Password for initial auth (if auth_method=password)"
    ),
    key_file: Optional[UploadFile] = File(
        None, description="SSH private key file (if auth_method=key)"
    ),
):
    """
    Create new infrastructure host

    Authentication Methods:
    - password: Provide password in 'password' field. Use /hosts/{id}/provision-key to generate SSH key.
    - key: Upload existing SSH private key via 'key_file' field.

    Returns:
    - Created host details

    Raises:
    - 400: Invalid input data
    - 404: Role not found
    - 409: Host with IP already exists
    - 500: Internal server error
    """
    try:
        # Validate role exists
        role_obj = db.get_role_by_name(role)
        if not role_obj:
            raise HTTPException(
                status_code=404,
                detail=f"Role '{role}' not found. Use /api/iac/roles to list available roles.",
            )

        # Check if host with IP already exists
        existing_host = db.get_host_by_ip(ip_address)
        if existing_host:
            raise HTTPException(
                status_code=409,
                detail=f"Host with IP address {ip_address} already exists (ID: {existing_host.id})",
            )

        # Validate auth method
        if auth_method == "password" and not password:
            raise HTTPException(
                status_code=400, detail="Password required when auth_method='password'"
            )

        if auth_method == "key" and not key_file:
            raise HTTPException(
                status_code=400, detail="SSH key file required when auth_method='key'"
            )

        # Create host data
        host_data = {
            "hostname": hostname,
            "ip_address": ip_address,
            "role_id": role_obj.id,
            "ssh_port": ssh_port,
            "ssh_user": ssh_user,
            "status": "new",
        }

        # Handle SSH key file upload
        if auth_method == "key" and key_file:
            # Save uploaded key to secure location
            key_dir = "/home/autobot/.ssh/infrastructure_keys"
            os.makedirs(key_dir, exist_ok=True)

            key_filename = f"{hostname}_{ip_address.replace('.', '_')}.pem"
            key_path = os.path.join(key_dir, key_filename)

            # Save key file asynchronously
            try:
                content = await key_file.read()
                async with aiofiles.open(key_path, "wb") as f:
                    await f.write(content)

                # Set secure permissions
                os.chmod(key_path, 0o600)

                host_data["ssh_key_path"] = key_path
                key_content = content.decode("utf-8")
            except OSError as e:
                logger.error(f"Failed to save SSH key file {key_path}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to save SSH key file: {str(e)}")

        # Create host FIRST (CRITICAL: Must exist before credential storage)
        host = db.create_host(host_data)

        # Store SSH key credential if uploaded (AFTER host creation)
        if auth_method == "key" and key_file:
            db.store_ssh_credential(
                host_id=host.id, credential_type="ssh_key", value=key_content
            )

        # Store password credential if provided
        if auth_method == "password" and password:
            db.store_ssh_credential(
                host_id=host.id, credential_type="password", value=password
            )

        logger.info(f"Created host: {hostname} ({ip_address}) with role {role}")

        return host

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating host: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating host: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_host",
    error_code_prefix="INFRASTRUCTURE",
)
@router.get("/hosts/{host_id}", response_model=HostDetailResponse)
async def get_host(host_id: int):
    """
    Get detailed information about a specific host

    Path Parameters:
    - host_id: Host ID

    Returns:
    - Detailed host information including role, deployment status

    Raises:
    - 404: Host not found
    - 500: Internal server error
    """
    try:
        host = db.get_host(host_id)

        if not host:
            raise HTTPException(status_code=404, detail=f"Host {host_id} not found")

        # Get role information
        role = db.get_role_by_name(host.role.name) if host.role else None
        role_name = role.name if role else "unknown"

        # Check for active credentials
        has_credential = db.get_active_credential(host_id, "ssh_key") is not None

        # Get deployment information
        deployments = db.get_deployments(host_id=host_id)
        deployment_count = len(deployments)
        last_deployment = deployments[0] if deployments else None
        last_deployment_status = last_deployment.status if last_deployment else None

        # Build detailed response
        host_detail = {
            **host.__dict__,
            "role_name": role_name,
            "has_active_credential": has_credential,
            "deployment_count": deployment_count,
            "last_deployment_status": last_deployment_status,
        }

        return host_detail

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting host {host_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting host: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_host",
    error_code_prefix="INFRASTRUCTURE",
)
@router.put("/hosts/{host_id}", response_model=HostResponse)
async def update_host(host_id: int, host_update: HostUpdate):
    """
    Update infrastructure host configuration

    Path Parameters:
    - host_id: Host ID

    Request Body:
    - HostUpdate schema (all fields optional)

    Returns:
    - Updated host details

    Raises:
    - 404: Host not found
    - 400: Invalid update data
    - 500: Internal server error
    """
    try:
        host = db.get_host(host_id)

        if not host:
            raise HTTPException(status_code=404, detail=f"Host {host_id} not found")

        # Build update data from non-None fields
        update_data = {
            k: v for k, v in host_update.model_dump().items() if v is not None
        }

        if not update_data:
            raise HTTPException(status_code=400, detail="No update data provided")

        # Apply updates
        for key, value in update_data.items():
            setattr(host, key, value)

        # Save changes (would use db.update_host() in production)
        # For now, update_host_status handles status updates
        if "status" in update_data:
            db.update_host_status(host_id, update_data["status"])

        # Get updated host
        updated_host = db.get_host(host_id)

        logger.info(f"Updated host {host_id}: {update_data}")

        return updated_host

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating host {host_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating host: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_host",
    error_code_prefix="INFRASTRUCTURE",
)
@router.delete("/hosts/{host_id}", status_code=204)
async def delete_host(host_id: int):
    """
    Delete infrastructure host (cascades to credentials and deployments)

    Path Parameters:
    - host_id: Host ID

    Returns:
    - 204 No Content on success

    Raises:
    - 404: Host not found
    - 500: Internal server error
    """
    try:
        host = db.get_host(host_id)

        if not host:
            raise HTTPException(status_code=404, detail=f"Host {host_id} not found")

        # Delete SSH key file if exists
        if host.ssh_key_path and os.path.exists(host.ssh_key_path):
            try:
                os.unlink(host.ssh_key_path)
                logger.info(f"Deleted SSH key file: {host.ssh_key_path}")
            except Exception as e:
                logger.warning(f"Failed to delete SSH key file: {e}")

        # Delete host (cascades to credentials and deployments)
        db.delete_host(host_id)

        logger.info(f"Deleted host {host_id}")

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting host {host_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting host: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_host_status",
    error_code_prefix="INFRASTRUCTURE",
)
@router.get("/hosts/{host_id}/status", response_model=HostStatusResponse)
async def get_host_status(host_id: int):
    """
    Get real-time host status (connectivity check)

    Path Parameters:
    - host_id: Host ID

    Returns:
    - Real-time host status including reachability and response time

    Raises:
    - 404: Host not found
    - 500: Internal server error
    """
    try:
        host = db.get_host(host_id)

        if not host:
            raise HTTPException(status_code=404, detail=f"Host {host_id} not found")

        # Test connectivity
        is_reachable = False
        response_time_ms = None
        error_message = None

        try:
            start_time = datetime.now()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host.ip_address, host.ssh_port))
            sock.close()

            end_time = datetime.now()
            response_time_ms = (end_time - start_time).total_seconds() * 1000

            is_reachable = result == 0

            if is_reachable:
                # Update last_seen_at
                db.update_host_status(host_id, host.status)

        except Exception as e:
            error_message = str(e)
            logger.warning(f"Connectivity check failed for host {host_id}: {e}")

        # Get active deployments count
        deployments = db.get_deployments(host_id=host_id, status="running")
        active_deployments = len(deployments)

        return HostStatusResponse(
            host_id=host.id,
            hostname=host.hostname,
            ip_address=host.ip_address,
            status=host.status,
            is_reachable=is_reachable,
            response_time_ms=response_time_ms,
            last_seen_at=host.last_seen_at,
            active_deployments=active_deployments,
            error_message=error_message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting host status {host_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error getting host status: {str(e)}"
        )


# ==================== Deployment Management Endpoints ====================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_deployment",
    error_code_prefix="INFRASTRUCTURE",
)
@router.post("/deployments", response_model=List[DeploymentResponse], status_code=202)
async def create_deployment(deployment: DeploymentCreate):
    """
    Trigger deployment for one or more hosts (asynchronous via Celery)

    Request Body:
    - host_ids: List of host IDs to deploy
    - force_redeploy: Force redeployment even if already deployed

    Returns:
    - 202 Accepted with list of created deployment records

    Raises:
    - 400: Invalid input data
    - 404: Host not found
    - 500: Internal server error

    Note: Deployment runs asynchronously. Use GET /deployments/{id} to check status.
    """
    try:
        created_deployments = []

        for host_id in deployment.host_ids:
            host = db.get_host(host_id)

            if not host:
                raise HTTPException(status_code=404, detail=f"Host {host_id} not found")

            # Check if SSH key is provisioned
            ssh_key = db.get_active_credential(host_id, "ssh_key")
            if not ssh_key and not host.ssh_key_path:
                raise HTTPException(
                    status_code=400,
                    detail=f"Host {host_id} ({host.hostname}) has no SSH key provisioned. "
                    f"Use POST /api/iac/hosts/{host_id}/provision-key first.",
                )

            # Get role name
            role_name = host.role.name if host.role else "unknown"

            # Create deployment record
            deploy_record = db.create_deployment(
                host_id=host_id, role=role_name, status="queued"
            )

            # Trigger Celery task
            host_config = {
                "ip_address": host.ip_address,
                "role": role_name,
                "ssh_user": host.ssh_user,
                "ssh_key_path": host.ssh_key_path,
                "ssh_port": host.ssh_port,
            }

            # Queue deployment task
            task = deploy_host.delay(host_config, deployment.force_redeploy)

            # Update deployment with Celery task ID
            deploy_record.ansible_run_id = task.id

            created_deployments.append(deploy_record)

            logger.info(
                f"Queued deployment {deploy_record.id} for host {host_id} "
                f"(Celery task: {task.id})"
            )

        return created_deployments

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating deployment: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error creating deployment: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_deployment",
    error_code_prefix="INFRASTRUCTURE",
)
@router.get("/deployments/{deployment_id}", response_model=DeploymentDetailResponse)
async def get_deployment(deployment_id: int):
    """
    Get deployment details including status and logs

    Path Parameters:
    - deployment_id: Deployment ID

    Returns:
    - Detailed deployment information

    Raises:
    - 404: Deployment not found
    - 500: Internal server error
    """
    try:
        deployments = db.get_deployments()
        deployment = next((d for d in deployments if d.id == deployment_id), None)

        if not deployment:
            raise HTTPException(
                status_code=404, detail=f"Deployment {deployment_id} not found"
            )

        # Get host information
        host = db.get_host(deployment.host_id)
        if not host:
            raise HTTPException(
                status_code=404,
                detail=f"Host {deployment.host_id} for deployment not found",
            )

        # Calculate duration if completed
        duration_seconds = None
        if deployment.started_at and deployment.completed_at:
            duration = deployment.completed_at - deployment.started_at
            duration_seconds = duration.total_seconds()

        deployment_detail = {
            **deployment.__dict__,
            "hostname": host.hostname,
            "ip_address": host.ip_address,
            "duration_seconds": duration_seconds,
        }

        return deployment_detail

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting deployment {deployment_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error getting deployment: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_deployments",
    error_code_prefix="INFRASTRUCTURE",
)
@router.get("/deployments", response_model=List[DeploymentResponse])
async def list_deployments(
    host_id: Optional[int] = Query(None, description="Filter by host ID"),
    status: Optional[str] = Query(None, description="Filter by deployment status"),
):
    """
    List deployments with optional filtering

    Query Parameters:
    - host_id: Filter deployments for specific host
    - status: Filter by deployment status (queued, running, success, failed, rolled_back)

    Returns:
    - List of deployments matching filters

    Raises:
    - 500: Internal server error
    """
    try:
        deployments = db.get_deployments(host_id=host_id, status=status)

        logger.info(
            f"Listed {len(deployments)} deployments "
            f"(host_id={host_id}, status={status})"
        )

        return deployments

    except Exception as e:
        logger.error(f"Error listing deployments: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error listing deployments: {str(e)}"
        )


# ==================== Credential Management Endpoints ====================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="provision_ssh_key",
    error_code_prefix="INFRASTRUCTURE",
)
@router.post("/hosts/{host_id}/provision-key", response_model=ProvisionKeyResponse)
async def provision_ssh_key(host_id: int, provision_request: ProvisionKeyRequest):
    """
    Provision SSH key on host using password authentication

    This endpoint:
    1. Connects to host using password
    2. Generates 4096-bit RSA key pair
    3. Adds public key to authorized_keys
    4. Stores private key (encrypted) in database
    5. Verifies key authentication works

    Path Parameters:
    - host_id: Host ID

    Request Body:
    - password: Password for initial authentication

    Returns:
    - Provisioning result with public key fingerprint

    Raises:
    - 404: Host not found
    - 400: SSH provisioning failed
    - 500: Internal server error
    """
    try:
        host = db.get_host(host_id)

        if not host:
            raise HTTPException(status_code=404, detail=f"Host {host_id} not found")

        logger.info(
            f"Starting SSH key provisioning for host {host_id} ({host.hostname})"
        )

        # Update host status
        db.update_host_status(host_id, "provisioning")

        try:
            # Provision SSH key (returns content, not file path)
            private_key_content, public_key_content = ssh_provisioner.provision_key(
                host_ip=host.ip_address,
                port=host.ssh_port,
                username=host.ssh_user,
                password=provision_request.password,
            )

            # Deactivate old credentials
            db.deactivate_credentials(host_id, "ssh_key")

            # Store new SSH key in encrypted database
            db.store_ssh_credential(
                host_id=host_id, credential_type="ssh_key", value=private_key_content
            )

            # Update host status (no key_path needed - key stored in database)
            host.status = "deployed"
            db.update_host_status(host_id, "deployed")

            # Calculate fingerprint for response
            fingerprint = (
                public_key_content.split()[-1] if "@" in public_key_content else None
            )

            logger.info(f"SSH key provisioning successful for host {host_id}")

            return ProvisionKeyResponse(
                success=True,
                message=f"SSH key provisioned successfully for {host.hostname}",
                host_id=host_id,
                public_key_fingerprint=fingerprint,
            )

        except Exception as e:
            # Update host status to failed
            db.update_host_status(host_id, "failed")

            logger.error(f"SSH key provisioning failed for host {host_id}: {e}")

            raise HTTPException(
                status_code=400, detail=f"SSH key provisioning failed: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error provisioning SSH key for host {host_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error provisioning SSH key: {str(e)}"
        )


# ==================== Supporting Endpoints ====================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_roles",
    error_code_prefix="INFRASTRUCTURE",
)
@router.get("/roles", response_model=List[RoleResponse])
async def list_roles():
    """
    List all available infrastructure roles

    Returns:
    - List of infrastructure roles with details

    Raises:
    - 500: Internal server error
    """
    try:
        roles = db.get_roles()

        logger.info(f"Listed {len(roles)} infrastructure roles")

        return roles

    except Exception as e:
        logger.error(f"Error listing roles: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing roles: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_statistics",
    error_code_prefix="INFRASTRUCTURE",
)
@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics():
    """
    Get infrastructure statistics and metrics

    Returns:
    - Comprehensive infrastructure statistics

    Raises:
    - 500: Internal server error
    """
    try:
        stats = db.get_statistics()

        logger.info("Retrieved infrastructure statistics")

        return stats

    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error getting statistics: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="health_check",
    error_code_prefix="INFRASTRUCTURE",
)
@router.get("/health")
async def health_check():
    """
    Infrastructure API health check

    Returns:
    - Health status of infrastructure API components
    """
    try:
        # Test database connectivity
        stats = db.get_statistics()

        return {
            "status": "healthy",
            "service": "infrastructure_api",
            "timestamp": datetime.utcnow().isoformat(),
            "database": "connected",
            "total_hosts": stats.get("total_hosts", 0),
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "infrastructure_api",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
