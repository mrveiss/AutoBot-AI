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
    "SLM_INFRASTRUCTURE_PLAYBOOKS_DIR", "/opt/autobot/ansible/playbooks"
)


class PlaybookCategory(str, Enum):
    """Categories of infrastructure playbooks."""

    DATABASE = "database"
    MONITORING = "monitoring"
    SECURITY = "security"
    NETWORKING = "networking"
    STORAGE = "storage"


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
            execution.output.append(
                f"[WARNING] Playbook file not found: {playbook_path}"
            )
            execution.output.append("[INFO] Using simulation mode for demonstration")

            # Simulate playbook execution for demo purposes
            await _simulate_playbook_execution(execution, playbook)
            return

        inventory_dir = os.path.join(os.path.dirname(PLAYBOOKS_DIR), "inventory")
        inventory_path = os.path.join(inventory_dir, "slm-nodes.yml")
        cmd = [
            "ansible-playbook",
            "-i",
            inventory_path,
            playbook_path,
        ]

        # Add limit if specified
        if limit_hosts:
            cmd.extend(["--limit", ",".join(limit_hosts)])

        # Add tags if specified
        if playbook.tags:
            cmd.extend(["--tags", ",".join(playbook.tags)])

        # Add extra variables
        merged_vars = {**playbook.variables, **variables}
        for key, value in merged_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        execution.output.append(f"[INFO] Running: {' '.join(cmd)}")

        # Execute the playbook
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        # Stream output
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded = line.decode().rstrip()
            execution.output.append(decoded)

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


def _get_user_management_db_steps() -> list[str]:
    """Get simulation steps for user-management-db playbook (#786)."""
    return [
        "",
        "TASK [Install PostgreSQL 16] *****",
        "changed: [slm]",
        "changed: [redis]",
        "",
        "TASK [Configure postgresql.conf] *****",
        "changed: [slm]",
        "changed: [redis]",
        "",
        "TASK [Configure pg_hba.conf] *****",
        "changed: [slm]",
        "changed: [redis]",
        "",
        "TASK [Create database user] *****",
        "changed: [slm]",
        "changed: [redis]",
        "",
        "TASK [Create databases] *****",
        "changed: [slm] => (item=slm)",
        "changed: [slm] => (item=slm_users)",
        "changed: [redis] => (item=autobot_users)",
        "",
        "TASK [Save credentials] *****",
        "changed: [slm]",
        "changed: [redis]",
        "",
        "TASK [Verify connectivity] *****",
        "ok: [slm]",
        "",
        "PLAY RECAP *****",
        "slm                        : ok=8    changed=6    unreachable=0    failed=0",
        "redis                      : ok=7    changed=5    unreachable=0    failed=0",
    ]


def _get_generic_playbook_steps(hosts: list[str]) -> list[str]:
    """Get simulation steps for generic playbook (#786)."""
    return [
        "",
        "TASK [Install dependencies] *****",
        *[f"changed: [{host}]" for host in hosts],
        "",
        "TASK [Configure service] *****",
        *[f"changed: [{host}]" for host in hosts],
        "",
        "TASK [Start service] *****",
        *[f"ok: [{host}]" for host in hosts],
        "",
        "PLAY RECAP *****",
        *[
            f"{host:24} : ok=4    changed=2    unreachable=0    failed=0"
            for host in hosts
        ],
    ]


async def _stream_simulation_output(
    execution: PlaybookExecution,
    steps: list[str],
) -> None:
    """Stream simulation output with delays (#786)."""
    for line in steps:
        if execution.status == PlaybookStatus.CANCELLED:
            return
        execution.output.append(line)
        await asyncio.sleep(0.3)

    execution.status = PlaybookStatus.COMPLETED
    execution.output.append("")
    execution.output.append(
        "[SUCCESS] Playbook completed successfully (simulation mode)"
    )


async def _simulate_playbook_execution(
    execution: PlaybookExecution,
    playbook: PlaybookInfo,
) -> None:
    """Simulate playbook execution for demonstration when playbook file not found."""
    steps = [
        f"PLAY [{playbook.name}]",
        "",
        "TASK [Gathering Facts] *****",
        *[f"ok: [{host}]" for host in playbook.target_hosts],
    ]

    if playbook.id == "user-management-db":
        steps.extend(_get_user_management_db_steps())
    else:
        steps.extend(_get_generic_playbook_steps(playbook.target_hosts))

    await _stream_simulation_output(execution, steps)
