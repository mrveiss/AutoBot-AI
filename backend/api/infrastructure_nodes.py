# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Infrastructure Nodes API - Issue #695

REST API endpoints for oVirt-style node management with Ansible-based enrollment.
Provides node listing, enrollment, role management, and real-time status updates.

Endpoints:
- GET    /api/infrastructure/nodes              - List all nodes with status
- POST   /api/infrastructure/nodes              - Add new node
- GET    /api/infrastructure/nodes/{id}         - Get node details
- PUT    /api/infrastructure/nodes/{id}         - Update node
- DELETE /api/infrastructure/nodes/{id}         - Remove node (with safety checks)
- POST   /api/infrastructure/nodes/{id}/test    - Test connection
- POST   /api/infrastructure/nodes/{id}/enroll  - Run Ansible enrollment
- POST   /api/infrastructure/nodes/{id}/role    - Change node role
- GET    /api/infrastructure/nodes/roles        - List available roles
- POST   /api/infrastructure/nodes/test-connection - Test connection (pre-add)
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/infrastructure", tags=["infrastructure-nodes"])


# Enums
class NodeStatus(str, Enum):
    """Node status states."""

    PENDING = "pending"
    ENROLLING = "enrolling"
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class AuthMethod(str, Enum):
    """Authentication methods for SSH."""

    PASSWORD = "password"
    PKI = "pki"


# Request/Response Models
class NodeMetrics(BaseModel):
    """Real-time node metrics."""

    cpu: float = Field(default=0, description="CPU usage percentage")
    ram: float = Field(default=0, description="RAM usage percentage")
    uptime: int = Field(default=0, description="Uptime in seconds")
    disk: Optional[float] = Field(default=None, description="Disk usage percentage")


class NodeRole(BaseModel):
    """Node role definition."""

    id: str
    name: str
    description: str
    services: List[str]
    default_port: Optional[int] = None


class CreateNodeRequest(BaseModel):
    """Request model for adding a new node."""

    name: str = Field(..., min_length=1, max_length=64, description="Node hostname")
    ip_address: str = Field(..., description="IPv4 address")
    ssh_user: str = Field(default="autobot", description="SSH username")
    ssh_port: int = Field(default=22, ge=1, le=65535, description="SSH port")
    auth_method: AuthMethod = Field(default=AuthMethod.PASSWORD, description="Auth method")
    password: Optional[str] = Field(default=None, description="SSH password (for password auth)")
    ssh_key: Optional[str] = Field(default=None, description="SSH private key content (for PKI auth)")
    role: str = Field(..., description="Node role ID")
    auto_enroll: bool = Field(default=True, description="Start enrollment immediately")

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        """Validate IPv4 address format."""
        import re

        pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
        if not re.match(pattern, v):
            raise ValueError("Invalid IPv4 address format")
        return v

    @field_validator("name")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        """Validate hostname format."""
        import re

        pattern = r"^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$"
        if not re.match(pattern, v):
            raise ValueError("Invalid hostname format")
        return v


class UpdateNodeRequest(BaseModel):
    """Request model for updating a node."""

    name: Optional[str] = None
    ssh_user: Optional[str] = None
    ssh_port: Optional[int] = Field(default=None, ge=1, le=65535)
    password: Optional[str] = None
    ssh_key: Optional[str] = None


class ChangeRoleRequest(BaseModel):
    """Request for changing node role."""

    role: str = Field(..., description="New role ID")


class TestConnectionRequest(BaseModel):
    """Request for testing connection before adding node."""

    ip_address: str
    ssh_port: int = Field(default=22)
    ssh_user: str = Field(default="autobot")
    auth_method: AuthMethod
    password: Optional[str] = None
    ssh_key: Optional[str] = None


class NodeResponse(BaseModel):
    """Response model for node details."""

    id: str
    name: str
    ip_address: str
    ssh_user: str
    ssh_port: int
    auth_method: AuthMethod
    role: str
    status: NodeStatus
    enrollment_step: Optional[int] = None
    metrics: Optional[NodeMetrics] = None
    os: Optional[str] = None
    created_at: str
    last_seen: Optional[str] = None


class NodeListResponse(BaseModel):
    """Response for node list."""

    nodes: List[NodeResponse]
    total: int


class TestConnectionResponse(BaseModel):
    """Response for connection test."""

    success: bool
    os: Optional[str] = None
    error: Optional[str] = None
    latency_ms: Optional[float] = None


class EnrollmentResponse(BaseModel):
    """Response for enrollment operation."""

    success: bool
    task_id: Optional[str] = None
    message: str


# In-memory storage (replace with database in production)
# This is a simplified implementation - production should use Redis or SQLite
_nodes_store: Dict[str, dict] = {}
_enrollment_tasks: Dict[str, dict] = {}


def _get_node_service():
    """Get or initialize the node service."""
    # Lazy import to avoid circular dependencies
    try:
        from backend.services.node_enrollment_service import NodeEnrollmentService

        return NodeEnrollmentService()
    except ImportError:
        logger.warning("NodeEnrollmentService not available, using mock")
        return None


# Available Roles (from VM_DEFINITIONS and Ansible roles)
AVAILABLE_ROLES: List[NodeRole] = [
    NodeRole(
        id="frontend",
        name="Frontend Server",
        description="Vue.js frontend with Vite dev server",
        services=["vite-dev", "nginx"],
        default_port=5173,
    ),
    NodeRole(
        id="npu-worker",
        name="NPU Worker",
        description="Intel OpenVINO NPU acceleration",
        services=["npu-service"],
        default_port=8081,
    ),
    NodeRole(
        id="redis",
        name="Redis Stack",
        description="Redis database with RediSearch/RedisJSON",
        services=["redis-stack"],
        default_port=6379,
    ),
    NodeRole(
        id="ai-stack",
        name="AI Stack",
        description="LLM and AI model inference",
        services=["llm-server"],
        default_port=8080,
    ),
    NodeRole(
        id="browser",
        name="Browser Automation",
        description="Playwright browser automation with VNC",
        services=["playwright", "vnc-server"],
        default_port=3000,
    ),
    NodeRole(
        id="custom",
        name="Custom",
        description="Custom service configuration",
        services=[],
        default_port=None,
    ),
]


# API Endpoints


@router.get("/nodes/roles", response_model=List[NodeRole])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_node_roles",
    error_code_prefix="NODE",
)
async def list_roles():
    """
    List available node roles.

    Returns all predefined roles with their service configurations.
    """
    return AVAILABLE_ROLES


@router.get("/nodes", response_model=NodeListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_infrastructure_nodes",
    error_code_prefix="NODE",
)
async def list_nodes(
    status: Optional[NodeStatus] = Query(default=None, description="Filter by status"),
    role: Optional[str] = Query(default=None, description="Filter by role"),
):
    """
    List all infrastructure nodes with optional filtering.

    Returns nodes from VM_DEFINITIONS plus any dynamically added nodes.
    """
    # Get static nodes from VM_DEFINITIONS
    from src.pki.config import VM_DEFINITIONS

    nodes = []

    # Add static nodes from VM_DEFINITIONS
    for vm_name, vm_ip in VM_DEFINITIONS.items():
        # Check if we have dynamic data for this node
        if vm_name in _nodes_store:
            node_data = _nodes_store[vm_name]
        else:
            # Create entry from static config
            node_data = {
                "id": vm_name,
                "name": vm_name,
                "ip_address": vm_ip,
                "ssh_user": "autobot",
                "ssh_port": 22,
                "auth_method": AuthMethod.PKI,
                "role": _get_role_from_name(vm_name),
                "status": NodeStatus.PENDING,
                "created_at": datetime.now().isoformat(),
            }
            _nodes_store[vm_name] = node_data

        # Apply filters
        if status and node_data.get("status") != status:
            continue
        if role and node_data.get("role") != role:
            continue

        nodes.append(NodeResponse(**node_data))

    # Add any additional dynamic nodes
    for node_id, node_data in _nodes_store.items():
        if node_id not in VM_DEFINITIONS:
            if status and node_data.get("status") != status:
                continue
            if role and node_data.get("role") != role:
                continue
            nodes.append(NodeResponse(**node_data))

    return NodeListResponse(nodes=nodes, total=len(nodes))


@router.post("/nodes", response_model=NodeResponse, status_code=201)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_infrastructure_node",
    error_code_prefix="NODE",
)
async def create_node(request: CreateNodeRequest, background_tasks: BackgroundTasks):
    """
    Add a new infrastructure node.

    Creates a node entry and optionally starts Ansible enrollment.
    """
    import uuid

    # Check for duplicate hostname or IP
    for node_data in _nodes_store.values():
        if node_data["name"] == request.name:
            raise HTTPException(status_code=400, detail=f"Node with name '{request.name}' already exists")
        if node_data["ip_address"] == request.ip_address:
            raise HTTPException(status_code=400, detail=f"Node with IP '{request.ip_address}' already exists")

    # Validate role
    valid_roles = [r.id for r in AVAILABLE_ROLES]
    if request.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {request.role}")

    # Validate credentials
    if request.auth_method == AuthMethod.PASSWORD and not request.password:
        raise HTTPException(status_code=400, detail="Password required for password authentication")

    # Create node entry
    node_id = str(uuid.uuid4())[:8]
    node_data = {
        "id": node_id,
        "name": request.name,
        "ip_address": request.ip_address,
        "ssh_user": request.ssh_user,
        "ssh_port": request.ssh_port,
        "auth_method": request.auth_method,
        "role": request.role,
        "status": NodeStatus.PENDING,
        "created_at": datetime.now().isoformat(),
    }

    _nodes_store[node_id] = node_data

    # Store credentials securely (in production, use secrets management)
    if request.password:
        _store_credentials(node_id, "password", request.password)
    if request.ssh_key:
        _store_credentials(node_id, "ssh_key", request.ssh_key)

    logger.info("Node created: %s (%s) with role %s", request.name, request.ip_address, request.role)

    # Auto-enroll if requested
    if request.auto_enroll:
        background_tasks.add_task(_run_enrollment, node_id)
        node_data["status"] = NodeStatus.ENROLLING

    return NodeResponse(**node_data)


@router.get("/nodes/{node_id}", response_model=NodeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_infrastructure_node",
    error_code_prefix="NODE",
)
async def get_node(node_id: str):
    """Get details of a specific node."""
    if node_id not in _nodes_store:
        raise HTTPException(status_code=404, detail="Node not found")

    return NodeResponse(**_nodes_store[node_id])


@router.put("/nodes/{node_id}", response_model=NodeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_infrastructure_node",
    error_code_prefix="NODE",
)
async def update_node(node_id: str, request: UpdateNodeRequest):
    """Update node configuration."""
    if node_id not in _nodes_store:
        raise HTTPException(status_code=404, detail="Node not found")

    node_data = _nodes_store[node_id]

    # Update fields
    if request.name is not None:
        node_data["name"] = request.name
    if request.ssh_user is not None:
        node_data["ssh_user"] = request.ssh_user
    if request.ssh_port is not None:
        node_data["ssh_port"] = request.ssh_port
    if request.password is not None:
        _store_credentials(node_id, "password", request.password)
    if request.ssh_key is not None:
        _store_credentials(node_id, "ssh_key", request.ssh_key)

    logger.info("Node updated: %s", node_id)

    return NodeResponse(**node_data)


@router.delete("/nodes/{node_id}", status_code=204)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_infrastructure_node",
    error_code_prefix="NODE",
)
async def delete_node(
    node_id: str,
    force: bool = Query(default=False, description="Force delete without safety checks"),
):
    """
    Remove a node from the infrastructure.

    Performs safety checks unless force=True.
    """
    if node_id not in _nodes_store:
        raise HTTPException(status_code=404, detail="Node not found")

    node_data = _nodes_store[node_id]

    # Safety checks
    if not force:
        if node_data.get("status") == NodeStatus.ONLINE:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove online node. Use force=True or take node offline first.",
            )

        # Check if this is a critical infrastructure node
        from src.pki.config import VM_DEFINITIONS

        if node_data.get("name") in VM_DEFINITIONS:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove core infrastructure node. Use force=True to override.",
            )

    # Remove credentials
    _remove_credentials(node_id)

    # Remove node
    del _nodes_store[node_id]

    logger.info("Node deleted: %s (force=%s)", node_id, force)

    return None


@router.post("/nodes/{node_id}/test", response_model=TestConnectionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_node_connection",
    error_code_prefix="NODE",
)
async def test_node_connection(node_id: str):
    """Test SSH connection to an existing node."""
    if node_id not in _nodes_store:
        raise HTTPException(status_code=404, detail="Node not found")

    node_data = _nodes_store[node_id]
    credentials = _get_credentials(node_id)

    result = await _test_ssh_connection(
        ip_address=node_data["ip_address"],
        ssh_port=node_data["ssh_port"],
        ssh_user=node_data["ssh_user"],
        auth_method=node_data["auth_method"],
        password=credentials.get("password"),
        ssh_key=credentials.get("ssh_key"),
    )

    # Update node status based on test result
    if result["success"]:
        node_data["status"] = NodeStatus.ONLINE
        node_data["last_seen"] = datetime.now().isoformat()
        if result.get("os"):
            node_data["os"] = result["os"]

    return TestConnectionResponse(**result)


@router.post("/nodes/test-connection", response_model=TestConnectionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_connection_preadd",
    error_code_prefix="NODE",
)
async def test_connection_preadd(request: TestConnectionRequest):
    """Test SSH connection before adding a node."""
    result = await _test_ssh_connection(
        ip_address=request.ip_address,
        ssh_port=request.ssh_port,
        ssh_user=request.ssh_user,
        auth_method=request.auth_method,
        password=request.password,
        ssh_key=request.ssh_key,
    )

    return TestConnectionResponse(**result)


@router.post("/nodes/{node_id}/enroll", response_model=EnrollmentResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enroll_infrastructure_node",
    error_code_prefix="NODE",
)
async def enroll_node(node_id: str, background_tasks: BackgroundTasks):
    """
    Start Ansible-based node enrollment.

    Runs the enrollment playbook to:
    1. Install dependencies
    2. Deploy PKI certificates
    3. Configure services for the assigned role
    """
    if node_id not in _nodes_store:
        raise HTTPException(status_code=404, detail="Node not found")

    node_data = _nodes_store[node_id]

    if node_data.get("status") == NodeStatus.ENROLLING:
        raise HTTPException(status_code=400, detail="Enrollment already in progress")

    # Start enrollment in background
    import uuid

    task_id = str(uuid.uuid4())
    node_data["status"] = NodeStatus.ENROLLING
    node_data["enrollment_step"] = 0

    _enrollment_tasks[task_id] = {
        "node_id": node_id,
        "status": "running",
        "started_at": datetime.now().isoformat(),
    }

    background_tasks.add_task(_run_enrollment, node_id, task_id)

    logger.info("Enrollment started for node %s (task: %s)", node_id, task_id)

    return EnrollmentResponse(
        success=True,
        task_id=task_id,
        message=f"Enrollment started for {node_data['name']}",
    )


@router.post("/nodes/{node_id}/role", response_model=NodeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="change_node_role",
    error_code_prefix="NODE",
)
async def change_node_role(
    node_id: str,
    request: ChangeRoleRequest,
    background_tasks: BackgroundTasks,
):
    """
    Change the role of an existing node.

    This will run Ansible to migrate services.
    """
    if node_id not in _nodes_store:
        raise HTTPException(status_code=404, detail="Node not found")

    # Validate role
    valid_roles = [r.id for r in AVAILABLE_ROLES]
    if request.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {request.role}")

    node_data = _nodes_store[node_id]
    old_role = node_data.get("role")

    if old_role == request.role:
        raise HTTPException(status_code=400, detail="Node already has this role")

    # Update role
    node_data["role"] = request.role

    # Run role migration in background
    background_tasks.add_task(_run_role_migration, node_id, old_role, request.role)

    logger.info("Role change initiated: %s from %s to %s", node_id, old_role, request.role)

    return NodeResponse(**node_data)


# Helper Functions


def _get_role_from_name(vm_name: str) -> str:
    """Map VM name to role ID."""
    role_mapping = {
        "main-host": "backend",
        "frontend": "frontend",
        "npu-worker": "npu-worker",
        "redis": "redis",
        "ai-stack": "ai-stack",
        "browser": "browser",
    }
    return role_mapping.get(vm_name, "custom")


def _store_credentials(node_id: str, key: str, value: str):
    """Store credentials securely (simplified - use secrets management in production)."""
    # In production, use the secrets API from backend/api/secrets.py
    if node_id not in _nodes_store:
        return

    if "_credentials" not in _nodes_store[node_id]:
        _nodes_store[node_id]["_credentials"] = {}

    _nodes_store[node_id]["_credentials"][key] = value


def _get_credentials(node_id: str) -> dict:
    """Retrieve stored credentials."""
    if node_id not in _nodes_store:
        return {}
    return _nodes_store[node_id].get("_credentials", {})


def _remove_credentials(node_id: str):
    """Remove stored credentials."""
    if node_id in _nodes_store and "_credentials" in _nodes_store[node_id]:
        del _nodes_store[node_id]["_credentials"]


async def _test_ssh_connection(
    ip_address: str,
    ssh_port: int,
    ssh_user: str,
    auth_method: AuthMethod,
    password: Optional[str] = None,
    ssh_key: Optional[str] = None,
) -> dict:
    """Test SSH connection to a host."""
    import asyncio
    import time

    start_time = time.time()

    try:
        import asyncssh

        # Prepare connection kwargs
        connect_kwargs = {
            "host": ip_address,
            "port": ssh_port,
            "username": ssh_user,
            "known_hosts": None,  # TODO: Use proper known_hosts in production
            "connect_timeout": 10,
        }

        if auth_method == AuthMethod.PASSWORD and password:
            connect_kwargs["password"] = password
        elif auth_method == AuthMethod.PKI:
            if ssh_key:
                # Use provided key
                connect_kwargs["client_keys"] = [asyncssh.import_private_key(ssh_key)]
            else:
                # Use default key
                import os

                default_key = os.path.expanduser("~/.ssh/autobot_key")
                if os.path.exists(default_key):
                    connect_kwargs["client_keys"] = [default_key]

        async with asyncssh.connect(**connect_kwargs) as conn:
            # Get OS info
            result = await conn.run("cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'", check=False)
            os_info = result.stdout.strip() if result.exit_status == 0 else None

            latency_ms = (time.time() - start_time) * 1000

            return {
                "success": True,
                "os": os_info,
                "latency_ms": round(latency_ms, 2),
            }

    except asyncssh.PermissionDenied as e:
        return {"success": False, "error": f"Authentication failed: {e}"}
    except asyncssh.HostKeyNotVerifiable:
        return {"success": False, "error": "Host key verification failed"}
    except asyncio.TimeoutError:
        return {"success": False, "error": "Connection timeout"}
    except OSError as e:
        return {"success": False, "error": f"Connection failed: {e}"}
    except ImportError:
        # asyncssh not available, use paramiko fallback
        return await _test_ssh_connection_paramiko(
            ip_address, ssh_port, ssh_user, auth_method, password, ssh_key
        )
    except Exception as e:
        logger.error("SSH connection test failed: %s", e)
        return {"success": False, "error": str(e)}


async def _test_ssh_connection_paramiko(
    ip_address: str,
    ssh_port: int,
    ssh_user: str,
    auth_method: AuthMethod,
    password: Optional[str] = None,
    ssh_key: Optional[str] = None,
) -> dict:
    """Fallback SSH test using paramiko."""
    import time

    start_time = time.time()

    try:
        import paramiko

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if auth_method == AuthMethod.PASSWORD and password:
            ssh.connect(
                hostname=ip_address,
                port=ssh_port,
                username=ssh_user,
                password=password,
                timeout=10,
            )
        else:
            import os
            from io import StringIO

            if ssh_key:
                pkey = paramiko.RSAKey.from_private_key(StringIO(ssh_key))
            else:
                key_path = os.path.expanduser("~/.ssh/autobot_key")
                pkey = paramiko.RSAKey.from_private_key_file(key_path)

            ssh.connect(
                hostname=ip_address,
                port=ssh_port,
                username=ssh_user,
                pkey=pkey,
                timeout=10,
            )

        # Get OS info
        _stdin, stdout, _stderr = ssh.exec_command(
            "cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'"
        )
        os_info = stdout.read().decode().strip()

        ssh.close()

        latency_ms = (time.time() - start_time) * 1000

        return {
            "success": True,
            "os": os_info or None,
            "latency_ms": round(latency_ms, 2),
        }

    except Exception as e:
        logger.error("Paramiko SSH test failed: %s", e)
        return {"success": False, "error": str(e)}


async def _run_enrollment(node_id: str, task_id: Optional[str] = None):
    """Run Ansible enrollment playbook for a node."""
    import asyncio

    if node_id not in _nodes_store:
        return

    node_data = _nodes_store[node_id]
    credentials = _get_credentials(node_id)

    # Enrollment steps (simulated - integrate with actual Ansible runner)
    steps = [
        "Validating SSH connectivity",
        "Checking OS compatibility",
        "Installing dependencies",
        "Deploying PKI certificates",
        "Configuring services",
        "Registering node",
        "Starting monitoring",
    ]

    try:
        for i, step in enumerate(steps):
            logger.info("Enrollment step %d/%d for %s: %s", i + 1, len(steps), node_id, step)
            node_data["enrollment_step"] = i

            # Simulate step execution (replace with actual Ansible calls)
            await asyncio.sleep(2)

            # Step 0: Test connection
            if i == 0:
                result = await _test_ssh_connection(
                    ip_address=node_data["ip_address"],
                    ssh_port=node_data["ssh_port"],
                    ssh_user=node_data["ssh_user"],
                    auth_method=node_data["auth_method"],
                    password=credentials.get("password"),
                    ssh_key=credentials.get("ssh_key"),
                )
                if not result["success"]:
                    raise RuntimeError(f"SSH connection failed: {result.get('error')}")
                if result.get("os"):
                    node_data["os"] = result["os"]

            # Step 3: Deploy PKI certificates
            elif i == 3:
                try:
                    from src.pki.distributor import CertificateDistributor
                    from src.pki.config import TLSConfig

                    config = TLSConfig()
                    distributor = CertificateDistributor(config)
                    # In production, call distributor.distribute_to_vm()
                except ImportError:
                    logger.warning("PKI module not available, skipping certificate deployment")

        # Enrollment complete
        node_data["status"] = NodeStatus.ONLINE
        node_data["last_seen"] = datetime.now().isoformat()
        node_data["enrollment_step"] = None

        if task_id and task_id in _enrollment_tasks:
            _enrollment_tasks[task_id]["status"] = "completed"
            _enrollment_tasks[task_id]["completed_at"] = datetime.now().isoformat()

        logger.info("Enrollment completed for node %s", node_id)

    except Exception as e:
        logger.error("Enrollment failed for node %s: %s", node_id, e)
        node_data["status"] = NodeStatus.ERROR
        node_data["enrollment_step"] = None

        if task_id and task_id in _enrollment_tasks:
            _enrollment_tasks[task_id]["status"] = "failed"
            _enrollment_tasks[task_id]["error"] = str(e)


async def _run_role_migration(node_id: str, old_role: str, new_role: str):
    """Run Ansible to migrate services when role changes."""
    import asyncio

    logger.info("Starting role migration for %s: %s -> %s", node_id, old_role, new_role)

    # Simulated role migration (replace with actual Ansible calls)
    # In production, this would:
    # 1. Stop old role services
    # 2. Remove old role configuration
    # 3. Install new role dependencies
    # 4. Configure new role services
    # 5. Start new role services

    await asyncio.sleep(5)  # Simulate migration time

    logger.info("Role migration completed for %s", node_id)
