# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Roles API Routes (Issue #779, #1129, #1243).

CRUD endpoints for role definitions, fleet health status, role migration,
and post-sync action badges (build, restart, schema).
"""

import asyncio
import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from models.database import Node, NodeRole, Role, RoleStatus, SyncType
from pydantic import BaseModel, Field
from services.auth import get_current_user
from services.database import get_db
from services.role_registry import get_role_definitions, list_roles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/roles", tags=["roles"])


class RoleResponse(BaseModel):
    """Role response schema."""

    name: str
    display_name: Optional[str] = None
    sync_type: Optional[str] = None
    source_paths: list
    target_path: str
    systemd_service: Optional[str] = None
    auto_restart: bool
    health_check_port: Optional[int] = None
    health_check_path: Optional[str] = None
    pre_sync_cmd: Optional[str] = None
    post_sync_cmd: Optional[str] = None
    required: bool = False
    degraded_without: list = Field(default_factory=list)
    ansible_playbook: Optional[str] = None

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    """Role creation schema."""

    name: str = Field(..., min_length=1, max_length=50)
    display_name: Optional[str] = None
    sync_type: str = SyncType.COMPONENT.value
    source_paths: list = Field(default_factory=list)
    target_path: str = Field(..., min_length=1)
    systemd_service: Optional[str] = None
    auto_restart: bool = False
    health_check_port: Optional[int] = None
    health_check_path: Optional[str] = None
    pre_sync_cmd: Optional[str] = None
    post_sync_cmd: Optional[str] = None
    required: bool = False
    degraded_without: list = Field(default_factory=list)
    ansible_playbook: Optional[str] = None


class RoleUpdate(BaseModel):
    """Role update schema."""

    display_name: Optional[str] = None
    sync_type: Optional[str] = None
    source_paths: Optional[list] = None
    target_path: Optional[str] = None
    systemd_service: Optional[str] = None
    auto_restart: Optional[bool] = None
    health_check_port: Optional[int] = None
    health_check_path: Optional[str] = None
    pre_sync_cmd: Optional[str] = None
    post_sync_cmd: Optional[str] = None
    required: Optional[bool] = None
    degraded_without: Optional[list] = None
    ansible_playbook: Optional[str] = None


class MigrateRequest(BaseModel):
    """Role migration request schema."""

    target_node_id: str = Field(..., min_length=1)


class FleetHealthResponse(BaseModel):
    """Fleet health status response."""

    health: str  # healthy | degraded | critical
    required_down: List[str]
    optional_down: List[str]
    detail: str


# ---- Post-sync action models (Issue #1243) ----


class PostSyncAction(BaseModel):
    """Single post-sync action for a node role."""

    role_name: str
    display_name: str
    category: str  # build | restart | schema | install
    label: str
    command: Optional[str] = None
    systemd_service: Optional[str] = None


class NodeActionsResponse(BaseModel):
    """All post-sync actions available for a node."""

    node_id: str
    actions: List[PostSyncAction]


class ExecuteActionRequest(BaseModel):
    """Request to execute a post-sync action."""

    role_name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)


@router.get("", response_model=List[RoleResponse])
async def get_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> List[RoleResponse]:
    """List all role definitions."""
    roles = await list_roles(db)
    return [RoleResponse.model_validate(r) for r in roles]


@router.get("/definitions")
async def get_definitions_for_agents() -> List[dict]:
    """
    Get lightweight role definitions for agents.

    No authentication required - agents use this to know what to detect.
    """
    return await get_role_definitions()


@router.get("/fleet-health", response_model=FleetHealthResponse)
async def get_fleet_health(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetHealthResponse:
    """
    Compute fleet health status based on required vs optional role availability.

    Returns Critical if any required role has no active node,
    Degraded if all required roles are up but optional roles are down,
    Healthy if all required roles are active.
    Issue #1129.
    """
    roles_result = await db.execute(select(Role))
    all_roles = list(roles_result.scalars().all())

    active_roles = await _get_active_role_names(db)
    return _classify_fleet_health(all_roles, active_roles)


async def _get_active_role_names(db: AsyncSession) -> set:
    """Return set of role names with at least one active NodeRole record."""
    result = await db.execute(
        select(NodeRole.role_name)
        .where(NodeRole.status == RoleStatus.ACTIVE.value)
        .distinct()
    )
    return set(result.scalars().all())


def _classify_fleet_health(
    all_roles: list, active_role_names: set
) -> FleetHealthResponse:
    """Classify fleet health from role list and set of active role names."""
    required_down = []
    optional_down = []
    for role in all_roles:
        if role.name not in active_role_names:
            if role.required:
                required_down.append(role.name)
            else:
                optional_down.append(role.name)

    if required_down:
        detail = f"Critical: required roles offline: {', '.join(required_down)}"
        return FleetHealthResponse(
            health="critical",
            required_down=required_down,
            optional_down=optional_down,
            detail=detail,
        )
    if optional_down:
        detail = f"Degraded: optional roles offline: {', '.join(optional_down)}"
        return FleetHealthResponse(
            health="degraded",
            required_down=[],
            optional_down=optional_down,
            detail=detail,
        )
    return FleetHealthResponse(
        health="healthy", required_down=[], optional_down=[], detail="All roles active"
    )


@router.get("/{role_name}", response_model=RoleResponse)
async def get_role_by_name(
    role_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RoleResponse:
    """Get a specific role by name."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )

    return RoleResponse.model_validate(role)


@router.post("", response_model=RoleResponse)
async def create_role(
    role_data: RoleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RoleResponse:
    """Create a new role definition."""
    result = await db.execute(select(Role).where(Role.name == role_data.name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role already exists: {role_data.name}",
        )

    role = Role(**role_data.model_dump())
    db.add(role)
    await db.commit()
    await db.refresh(role)

    logger.info("Created role: %s", role.name)
    return RoleResponse.model_validate(role)


@router.put("/{role_name}", response_model=RoleResponse)
async def update_role(
    role_name: str,
    role_data: RoleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RoleResponse:
    """Update a role definition."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )

    for field, value in role_data.model_dump(exclude_unset=True).items():
        setattr(role, field, value)

    await db.commit()
    await db.refresh(role)

    logger.info("Updated role: %s", role.name)
    return RoleResponse.model_validate(role)


@router.delete("/{role_name}")
async def delete_role(
    role_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Delete a role definition."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )

    await db.delete(role)
    await db.commit()

    logger.info("Deleted role: %s", role_name)
    return {"success": True, "message": f"Role '{role_name}' deleted"}


@router.post("/{role_name}/migrate")
async def migrate_role(
    role_name: str,
    migrate_req: MigrateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Migrate a role to a target node by running its Ansible playbook.

    Looks up the role's ansible_playbook, then executes it limited to
    the target node. Returns execution output.
    Issue #1129 Phase 4.
    """
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )
    if not role.ansible_playbook:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Role '{role_name}' has no ansible_playbook configured",
        )
    return await _run_role_migration(role, migrate_req.target_node_id)


async def _run_role_migration(role: Role, target_node_id: str) -> dict:
    """Execute playbook migration for a role on a target node."""
    from services.playbook_executor import PlaybookExecutor

    executor = PlaybookExecutor()
    logger.info(
        "Migrating role %s to node %s via %s",
        role.name,
        target_node_id,
        role.ansible_playbook,
    )
    try:
        result = await executor.execute_playbook(
            playbook_name=role.ansible_playbook,
            limit=[target_node_id],
            extra_vars={"deploy_role": role.name},
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    logger.info(
        "Migration of role %s to %s: success=%s",
        role.name,
        target_node_id,
        result["success"],
    )
    return {
        "success": result["success"],
        "role": role.name,
        "target_node_id": target_node_id,
        "playbook": role.ansible_playbook,
        "output": result["output"],
        "returncode": result["returncode"],
    }


# =========================================================================
# Post-Sync Action Badges  (Issue #1243)
# =========================================================================

# Patterns to classify post_sync_cmd segments
_BUILD_PATTERNS = re.compile(r"npm run build|webpack|vite build", re.IGNORECASE)
_SCHEMA_PATTERNS = re.compile(r"alembic upgrade|migrate|db upgrade", re.IGNORECASE)
_INSTALL_PATTERNS = re.compile(r"pip install|npm install|yarn install", re.IGNORECASE)


def _classify_post_sync(role: Role) -> List[PostSyncAction]:
    """Parse a role's post_sync_cmd into categorised actions."""
    actions: List[PostSyncAction] = []
    cmd = role.post_sync_cmd or ""
    display = role.display_name or role.name

    if _SCHEMA_PATTERNS.search(cmd):
        actions.append(
            PostSyncAction(
                role_name=role.name,
                display_name=display,
                category="schema",
                label=f"Run migrations ({display})",
                command=cmd,
            )
        )

    if _BUILD_PATTERNS.search(cmd):
        actions.append(
            PostSyncAction(
                role_name=role.name,
                display_name=display,
                category="build",
                label=f"Build ({display})",
                command=cmd,
            )
        )

    if _INSTALL_PATTERNS.search(cmd) and not actions:
        actions.append(
            PostSyncAction(
                role_name=role.name,
                display_name=display,
                category="install",
                label=f"Install deps ({display})",
                command=cmd,
            )
        )

    if role.systemd_service and role.auto_restart:
        actions.append(
            PostSyncAction(
                role_name=role.name,
                display_name=display,
                category="restart",
                label=f"Restart {role.systemd_service}",
                systemd_service=role.systemd_service,
            )
        )

    return actions


@router.get(
    "/node-actions/{node_id}",
    response_model=NodeActionsResponse,
)
async def get_node_actions(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeActionsResponse:
    """Return post-sync actions for a node based on its roles.

    Issue #1243 — surfaces build, schema, install, and restart
    actions in the per-node orchestration view.
    """
    nr_result = await db.execute(
        select(NodeRole.role_name).where(
            NodeRole.node_id == node_id,
            NodeRole.status == RoleStatus.ACTIVE.value,
        )
    )
    role_names = set(nr_result.scalars().all())

    if not role_names:
        return NodeActionsResponse(node_id=node_id, actions=[])

    roles_result = await db.execute(select(Role).where(Role.name.in_(role_names)))
    node_roles = list(roles_result.scalars().all())

    actions: List[PostSyncAction] = []
    for role in node_roles:
        actions.extend(_classify_post_sync(role))

    return NodeActionsResponse(node_id=node_id, actions=actions)


async def _resolve_node_and_role(
    db: AsyncSession,
    node_id: str,
    role_name: str,
) -> tuple:
    """Look up Node and Role or raise 404. Issue #1243 helper."""
    node_res = await db.execute(select(Node).where(Node.node_id == node_id))
    node = node_res.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node not found: {node_id}",
        )
    role_res = await db.execute(select(Role).where(Role.name == role_name))
    role = role_res.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )
    return node, role


@router.post("/node-actions/{node_id}/execute")
async def execute_node_action(
    node_id: str,
    req: ExecuteActionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Execute a post-sync action on a node via SSH.

    Issue #1243 — one-click execution of build / schema / restart
    actions from the per-node orchestration view.
    """
    node, role = await _resolve_node_and_role(db, node_id, req.role_name)

    if req.category == "restart":
        if not role.systemd_service:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Role has no systemd_service",
            )
        success, output = await _run_ssh_cmd(
            node,
            f"sudo -n systemctl restart {role.systemd_service}",
        )
    else:
        cmd = role.post_sync_cmd
        if not cmd:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Role has no post_sync_cmd",
            )
        success, output = await _run_ssh_cmd(node, cmd)

    logger.info(
        "Executed %s action for role %s on %s: success=%s",
        req.category,
        req.role_name,
        node_id,
        success,
    )
    return {
        "success": success,
        "node_id": node_id,
        "role_name": req.role_name,
        "category": req.category,
        "output": output,
    }


async def _run_ssh_cmd(node: Node, remote_cmd: str) -> tuple:
    """Run a command on a node via SSH. Returns (success, output)."""
    ssh_user = node.ssh_user or "autobot"
    ssh_port = node.ssh_port or 22
    ssh_key = "/home/autobot/.ssh/id_rsa"
    ssh_cmd = [
        "/usr/bin/ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "BatchMode=yes",
        "-i",
        ssh_key,
        "-p",
        str(ssh_port),
        f"{ssh_user}@{node.ip_address}",
        remote_cmd,
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=120.0,
        )
        combined = stdout.decode("utf-8", errors="replace") + stderr.decode(
            "utf-8", errors="replace"
        )
        return process.returncode == 0, combined[:2000]
    except asyncio.TimeoutError:
        return False, "Timeout after 120 seconds"
    except Exception as e:
        logger.exception("SSH command error: %s", e)
        return False, f"Error: {str(e)[:500]}"
