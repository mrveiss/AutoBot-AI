# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Infrastructure API Routes

Issue #786: Provides endpoints for running infrastructure setup playbooks
such as database deployment, monitoring setup, and other infrastructure tasks.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from services.auth import get_current_user
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/infrastructure", tags=["infrastructure"])

# Directory where infrastructure playbooks are stored
PLAYBOOKS_DIR = os.getenv(
    "SLM_INFRASTRUCTURE_PLAYBOOKS_DIR", "/opt/autobot/autobot-slm-backend/ansible"
)


class PlaybookCategory(str, Enum):
    """Categories of infrastructure playbooks."""

    DATABASE = "database"
    MONITORING = "monitoring"
    SECURITY = "security"
    NETWORKING = "networking"
    STORAGE = "storage"
    OPERATIONS = "operations"


class PlaybookStatus(str, Enum):
    """Status of a playbook execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlaybookInfo(BaseModel):
    """Information about an available infrastructure playbook."""

    id: str
    name: str
    description: str
    category: PlaybookCategory
    playbook_file: str
    target_hosts: list[str]
    variables: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    estimated_duration: str = "5-10 minutes"
    requires_confirmation: bool = True


class PlaybookExecution(BaseModel):
    """Model for tracking playbook execution."""

    execution_id: str
    playbook_id: str
    status: PlaybookStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    triggered_by: str


class ExecutePlaybookRequest(BaseModel):
    """Request model for executing a playbook."""

    playbook_id: str
    variables: dict = Field(default_factory=dict)
    limit_hosts: Optional[list[str]] = None


class PlaybookListResponse(BaseModel):
    """Response model for listing playbooks."""

    playbooks: list[PlaybookInfo]


class ExecutionResponse(BaseModel):
    """Response model for playbook execution."""

    execution: PlaybookExecution


# Available infrastructure playbooks
AVAILABLE_PLAYBOOKS: list[PlaybookInfo] = [
    PlaybookInfo(
        id="user-management-db",
        name="User Management Database Setup",
        description="Deploy PostgreSQL databases for user management on SLM Server "
        "and Redis VM. Sets up slm, slm_users, and autobot_users databases "
        "with secure authentication and cross-VM connectivity.",
        category=PlaybookCategory.DATABASE,
        playbook_file="deploy-user-management-db.yml",
        target_hosts=["slm", "redis"],
        variables={
            "postgresql_version": "16",
            "db_pool_size": 20,
        },
        estimated_duration="10-15 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="redis-stack",
        name="Redis Stack Deployment",
        description="Deploy Redis Stack server with RediSearch, RedisJSON, "
        "RedisGraph, and RedisTimeSeries modules for high-performance "
        "data operations.",
        category=PlaybookCategory.DATABASE,
        playbook_file="deploy-redis-stack.yml",
        target_hosts=["redis"],
        variables={
            "redis_port": 6379,
            "redis_maxmemory": "4gb",
        },
        estimated_duration="5-10 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="monitoring-stack",
        name="Monitoring Stack Setup",
        description="Deploy Prometheus, Grafana, and Alertmanager for "
        "comprehensive fleet monitoring and alerting.",
        category=PlaybookCategory.MONITORING,
        playbook_file="deploy-slm-manager.yml",
        target_hosts=["00-SLM-Manager"],
        variables={
            "prometheus_port": 9090,
            "grafana_port": 3000,
        },
        tags=["monitoring"],
        estimated_duration="10-15 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="postgresql-db",
        name="PostgreSQL Database Setup",
        description="Deploy PostgreSQL 16 database server for SLM "
        "backend data persistence.",
        category=PlaybookCategory.DATABASE,
        playbook_file="deploy-slm-manager.yml",
        target_hosts=["00-SLM-Manager"],
        variables={
            "postgresql_version": "16",
            "postgresql_port": 5432,
        },
        tags=["postgresql"],
        estimated_duration="5-10 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="tls-certificates",
        name="TLS Certificate Setup",
        description="Generate and deploy TLS certificates for secure "
        "communication between fleet nodes using internal CA.",
        category=PlaybookCategory.SECURITY,
        playbook_file="deploy-tls.yml",
        target_hosts=["all"],
        variables={
            "cert_validity_days": 365,
            "key_size": 4096,
        },
        estimated_duration="5-10 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="provision-fleet",
        name="Auto-Provision Fleet Nodes",
        description="Provision all fleet nodes with their assigned roles. "
        "Deploys common baseline, SLM agent, and role-specific "
        "configuration (redis, backend, frontend, AI, NPU, browser) "
        "in dependency order.",
        category=PlaybookCategory.NETWORKING,
        playbook_file="provision-fleet-roles.yml",
        target_hosts=["slm_nodes"],
        variables={},
        estimated_duration="20-30 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="seed-fleet",
        name="Seed Fleet Nodes",
        description="Register all inventory nodes in the SLM database "
        "via the REST API. Assigns roles for heartbeat acceptance "
        "and fleet dashboard visibility.",
        category=PlaybookCategory.NETWORKING,
        playbook_file="seed-fleet-nodes.yml",
        target_hosts=["localhost"],
        variables={},
        estimated_duration="1-2 minutes",
        requires_confirmation=False,
    ),
    PlaybookInfo(
        id="full-slm-deploy",
        name="Full SLM Deployment",
        description="Complete SLM setup pipeline: PostgreSQL, backend, "
        "frontend, nginx, TLS, monitoring, seed nodes, and "
        "auto-provision all fleet roles.",
        category=PlaybookCategory.NETWORKING,
        playbook_file="deploy-slm-manager.yml",
        target_hosts=["00-SLM-Manager", "slm_nodes"],
        variables={},
        estimated_duration="30-45 minutes",
        requires_confirmation=True,
    ),
    # =========================================================================
    # NODE SETUP PLAYBOOKS (Fresh provisioning from blank Ubuntu 22.04)
    # =========================================================================
    PlaybookInfo(
        id="setup-npu-worker",
        name="Setup NPU Worker Node",
        description="Provision NPU worker from scratch with OpenVINO, "
        "hardware acceleration drivers, and systemd service. "
        "Auto-migrates from old directory structure.",
        category=PlaybookCategory.NETWORKING,
        playbook_file="setup-npu-worker.yml",
        target_hosts=["npu_worker"],
        variables={"npu_worker_port": 8081},
        estimated_duration="6 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="setup-user-backend",
        name="Setup User Backend Node",
        description="Provision main AutoBot backend with FastAPI, "
        "VNC server, database migrations, and TLS certificates.",
        category=PlaybookCategory.NETWORKING,
        playbook_file="setup-user-backend.yml",
        target_hosts=["main"],
        variables={"backend_port": 8001},
        estimated_duration="8 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="setup-user-frontend",
        name="Setup User Frontend Node",
        description="Provision user frontend with nginx HTTPS, Vue "
        "production build, API proxy, and WebSocket support.",
        category=PlaybookCategory.NETWORKING,
        playbook_file="setup-user-frontend.yml",
        target_hosts=["frontend"],
        variables={"frontend_port": 443},
        estimated_duration="5 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="setup-browser-worker",
        name="Setup Browser Worker Node",
        description="Provision browser automation worker with Playwright, "
        "Chromium, and systemd service for GUI automation tasks.",
        category=PlaybookCategory.NETWORKING,
        playbook_file="setup-browser-worker.yml",
        target_hosts=["browser_worker"],
        variables={"browser_port": 3000},
        estimated_duration="7 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="setup-redis-stack",
        name="Setup Redis Stack Node",
        description="Provision Redis Stack with modules (Search, JSON, "
        "Graph, TimeSeries), persistence, TLS, and memory optimization.",
        category=PlaybookCategory.DATABASE,
        playbook_file="setup-redis-stack.yml",
        target_hosts=["redis"],
        variables={"redis_maxmemory": "4gb"},
        estimated_duration="3 minutes",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="setup-ai-stack",
        name="Setup AI Stack Node",
        description="Provision ChromaDB vector database with optional "
        "Ollama integration for LLM model storage and inference.",
        category=PlaybookCategory.DATABASE,
        playbook_file="setup-ai-stack.yml",
        target_hosts=["ai_stack"],
        variables={"chromadb_port": 8080},
        estimated_duration="4 minutes",
        requires_confirmation=True,
    ),
    # =========================================================================
    # FLEET UPDATE PLAYBOOKS (Fast code-only updates)
    # =========================================================================
    PlaybookInfo(
        id="update-all-nodes",
        name="Update All Nodes (Code Only)",
        description="Fast code synchronization across entire fleet. "
        "Syncs latest code, restarts services gracefully (3 nodes at a time). "
        "NO system package updates or configuration changes. ~30s per node.",
        category=PlaybookCategory.NETWORKING,
        playbook_file="update-all-nodes.yml",
        target_hosts=["infrastructure"],
        variables={},
        estimated_duration="2 minutes (fleet-wide)",
        requires_confirmation=False,
    ),
    # =========================================================================
    # MIGRATION PLAYBOOKS (Node migration workflow)
    # =========================================================================
    PlaybookInfo(
        id="pre-migration-check",
        name="Pre-Migration Validation",
        description="Validates disk space, network connectivity, and "
        "dependencies before migration. Ensures destination has enough "
        "space (data + 20% buffer) and minimum 10GB free remains. "
        "FAILS migration if insufficient resources.",
        category=PlaybookCategory.STORAGE,
        playbook_file="pre-migration-check.yml",
        target_hosts=["all"],
        variables={
            "source_host": "",
            "required_space_gb": 100,
            "buffer_percent": 20,
            "min_free_gb": 10,
        },
        estimated_duration="1-2 minutes",
        requires_confirmation=False,
    ),
    PlaybookInfo(
        id="backup-node-data",
        name="Comprehensive Node Backup",
        description="Creates timestamped backup of ALL critical data: "
        "PostgreSQL (pg_dumpall), Prometheus (56GB TSDB), Grafana, "
        "Redis (RDB+AOF), ChromaDB, SQLite databases, LLM models, "
        "configs, and TLS certs. Generates SHA256 checksums for verification.",
        category=PlaybookCategory.STORAGE,
        playbook_file="backup-node-data.yml",
        target_hosts=["all"],
        variables={
            "backup_dir": "/opt/autobot/backups",
            "include_models": True,
        },
        estimated_duration="10-30 minutes (depends on data size)",
        requires_confirmation=True,
    ),
    # =========================================================================
    # SYSTEM UPDATE PLAYBOOKS (Package updates)
    # =========================================================================
    PlaybookInfo(
        id="check-system-updates",
        name="Check System Updates",
        description="Check for available system package updates across fleet. "
        "Reports total updates, security updates, kernel status, and "
        "whether reboot is required. Generates JSON report per node.",
        category=PlaybookCategory.MONITORING,
        playbook_file="check-system-updates.yml",
        target_hosts=["all"],
        variables={
            "check_security_only": False,
            "output_format": "json",
        },
        estimated_duration="1-2 minutes",
        requires_confirmation=False,
    ),
    PlaybookInfo(
        id="apply-system-updates",
        name="Apply System Updates",
        description="Safely apply system package updates with rollback capability. "
        "Supports update types: all, security, specific packages. "
        "Optional auto-reboot, rolling updates (3 nodes at a time), "
        "pre-update backups, and service verification.",
        category=PlaybookCategory.SECURITY,
        playbook_file="apply-system-updates.yml",
        target_hosts=["all"],
        variables={
            "update_type": "security",
            "auto_reboot": False,
            "backup_before_update": True,
            "dry_run": False,
            "update_batch_size": 3,
        },
        estimated_duration="10-30 minutes (depends on update count)",
        requires_confirmation=True,
    ),
    PlaybookInfo(
        id="reboot-node",
        name="Reboot Node",
        description="Safely reboot a fleet node and wait for it to come back online. "
        "Uses Ansible's reboot module with configurable timeout and delays. "
        "Verifies node is responsive after reboot completes.",
        category=PlaybookCategory.OPERATIONS,
        playbook_file="reboot-node.yml",
        target_hosts=["all"],
        variables={
            "reboot_timeout": 300,
            "pre_reboot_delay": 5,
            "post_reboot_delay": 30,
        },
        estimated_duration="5-10 minutes",
        requires_confirmation=True,
    ),
]

# In-memory storage for executions (in production, use database)
_executions: dict[str, PlaybookExecution] = {}


@router.get("/playbooks", response_model=PlaybookListResponse)
async def list_playbooks(
    _: Annotated[dict, Depends(get_current_user)],
    category: Optional[PlaybookCategory] = None,
) -> PlaybookListResponse:
    """List available infrastructure playbooks."""
    playbooks = AVAILABLE_PLAYBOOKS
    if category:
        playbooks = [p for p in playbooks if p.category == category]
    return PlaybookListResponse(playbooks=playbooks)


@router.get("/playbooks/{playbook_id}", response_model=PlaybookInfo)
async def get_playbook(
    playbook_id: str,
    _: Annotated[dict, Depends(get_current_user)],
) -> PlaybookInfo:
    """Get details of a specific playbook."""
    for playbook in AVAILABLE_PLAYBOOKS:
        if playbook.id == playbook_id:
            return playbook
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Playbook '{playbook_id}' not found",
    )


@router.post("/execute", response_model=ExecutionResponse)
async def execute_playbook(
    request: ExecutePlaybookRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ExecutionResponse:
    """Execute an infrastructure playbook."""
    # Find the playbook
    playbook = None
    for p in AVAILABLE_PLAYBOOKS:
        if p.id == request.playbook_id:
            playbook = p
            break

    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playbook '{request.playbook_id}' not found",
        )

    # Create execution record
    execution_id = str(uuid.uuid4())
    execution = PlaybookExecution(
        execution_id=execution_id,
        playbook_id=request.playbook_id,
        status=PlaybookStatus.PENDING,
        triggered_by=current_user.get("sub", "unknown"),
    )
    _executions[execution_id] = execution

    # Start execution in background
    asyncio.create_task(
        _run_playbook(execution_id, playbook, request.variables, request.limit_hosts)
    )

    logger.info(
        "Infrastructure playbook execution started: %s (%s) by %s",
        playbook.name,
        execution_id,
        execution.triggered_by,
    )

    return ExecutionResponse(execution=execution)


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: str,
    _: Annotated[dict, Depends(get_current_user)],
) -> ExecutionResponse:
    """Get the status and output of a playbook execution."""
    execution = _executions.get(execution_id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )
    return ExecutionResponse(execution=execution)


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    _: Annotated[dict, Depends(get_current_user)],
) -> ExecutionResponse:
    """Cancel a running playbook execution."""
    execution = _executions.get(execution_id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )

    if execution.status not in [PlaybookStatus.PENDING, PlaybookStatus.RUNNING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel execution in status: {execution.status}",
        )

    execution.status = PlaybookStatus.CANCELLED
    execution.completed_at = datetime.now(timezone.utc)
    execution.output.append("[CANCELLED] Execution cancelled by user")

    logger.info("Infrastructure playbook execution cancelled: %s", execution_id)
    return ExecutionResponse(execution=execution)


def _build_playbook_command(
    playbook_path: str,
    inventory_path: str,
    playbook: PlaybookInfo,
    limit_hosts,
    variables,
):
    """Build ansible-playbook command with arguments.

    Helper for _run_playbook (Issue #665).
    """
    cmd = ["ansible-playbook", "-i", inventory_path, playbook_path]

    if limit_hosts:
        cmd.extend(["--limit", ",".join(limit_hosts)])

    if playbook.tags:
        cmd.extend(["--tags", ",".join(playbook.tags)])

    merged_vars = {**playbook.variables, **variables}
    for key, value in merged_vars.items():
        cmd.extend(["-e", f"{key}={value}"])

    return cmd


def _get_ansible_environment():
    """Get environment variables for Ansible subprocess.

    Helper for _run_playbook (Issue #665).
    """
    env = os.environ.copy()
    env.update(
        {
            "ANSIBLE_CONFIG": "/opt/autobot/.ansible.cfg",
            "ANSIBLE_HOME": "/opt/autobot/.ansible",
            "ANSIBLE_LOCAL_TEMP": "/opt/autobot/.ansible/tmp",
        }
    )
    return env


async def _stream_process_output(process, execution):
    """Stream subprocess output to execution log.

    Helper for _run_playbook (Issue #665).
    """
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        decoded = line.decode().rstrip()
        execution.output.append(decoded)


async def _run_playbook(
    execution_id: str,
    playbook: PlaybookInfo,
    variables: dict,
    limit_hosts: Optional[list[str]],
) -> None:
    """Execute an Ansible playbook asynchronously."""
    execution = _executions.get(execution_id)
    if not execution:
        return

    execution.status = PlaybookStatus.RUNNING
    execution.started_at = datetime.now(timezone.utc)

    try:
        # Build ansible-playbook command
        playbook_path = os.path.join(PLAYBOOKS_DIR, playbook.playbook_file)

        # Check if playbook exists
        if not os.path.exists(playbook_path):
            execution.status = PlaybookStatus.FAILED
            execution.completed_at = datetime.now(timezone.utc)
            execution.output.append(
                f"[ERROR] Playbook not found: {playbook_path}. "
                "Deploy playbooks via Ansible first."
            )
            logger.error("Playbook file missing: %s", playbook_path)
            return

        inventory_dir = os.path.join(os.path.dirname(PLAYBOOKS_DIR), "inventory")
        inventory_path = os.path.join(inventory_dir, "slm-nodes.yml")
        cmd = _build_playbook_command(
            playbook_path, inventory_path, playbook, limit_hosts, variables
        )

        execution.output.append(f"[INFO] Running: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=_get_ansible_environment(),
        )

        await _stream_process_output(process, execution)

        await process.wait()

        if process.returncode == 0:
            execution.status = PlaybookStatus.COMPLETED
            execution.output.append("[SUCCESS] Playbook completed successfully")
        else:
            execution.status = PlaybookStatus.FAILED
            execution.error = f"Playbook failed with exit code {process.returncode}"
            execution.output.append(f"[FAILED] Exit code: {process.returncode}")

    except Exception as e:
        execution.status = PlaybookStatus.FAILED
        execution.error = str(e)
        execution.output.append(f"[ERROR] {str(e)}")
        logger.exception("Playbook execution failed: %s", execution_id)

    finally:
        execution.completed_at = datetime.now(timezone.utc)
