# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Setup Wizard API (Issue #1294)

Guided first-run setup wizard for configuring fleet nodes after SLM install.
Tracks wizard progress via the Settings key-value store and orchestrates
node addition, enrollment, role assignment, and fleet provisioning.
"""

import asyncio
import logging
import tempfile
import time
from pathlib import Path
from typing import Annotated, Optional

_PROVISION_LOG = Path("/var/log/autobot/provision-wizard.log")

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from services.auth import get_current_user
from services.database import db_service
from services.playbook_executor import get_playbook_executor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["setup-wizard"])

# ── Wizard Steps ────────────────────────────────────────────────────────────

WIZARD_STEPS = [
    "welcome",
    "add_nodes",
    "test_connections",
    "enroll_agents",
    "assign_roles",
    "provision_fleet",
    "verify_health",
    "complete",
]


# ── Schemas ─────────────────────────────────────────────────────────────────


class WizardStatus(BaseModel):
    """Current state of the setup wizard."""

    completed: bool
    current_step: str
    current_step_index: int
    total_steps: int
    steps: list[dict]


class StepCompleteRequest(BaseModel):
    """Request to mark a wizard step as completed."""

    step: str


class ProvisionRequest(BaseModel):
    """Request to provision fleet nodes."""

    node_ids: Optional[list[str]] = None


# ── Settings Helpers ────────────────────────────────────────────────────────


async def _get_setting(key: str, default: str = "") -> str:
    """Read a setting value from the database."""
    from models.database import Setting
    from sqlalchemy import select

    async with db_service.session() as session:
        result = await session.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        return setting.value if setting else default


async def _set_setting(key: str, value: str) -> None:
    """Write a setting value to the database."""
    from models.database import Setting
    from sqlalchemy import select

    async with db_service.session() as session:
        result = await session.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            session.add(Setting(key=key, value=value, value_type="string"))
        await session.commit()


def _build_inventory_children(
    hosts: dict[str, dict],
    node_roles: list,
    node_id_to_hostname: dict[str, str],
) -> tuple[dict[str, dict], dict[str, set[str]]]:
    """Build Ansible inventory ``children`` with role-based groups (#1346).

    Returns (children dict, ansible_groups) where ansible_groups maps
    group name to set of hostnames for logging.
    """
    from services.role_registry import ROLE_ANSIBLE_GROUPS

    ansible_groups: dict[str, set[str]] = {}
    for nr in node_roles:
        hostname = node_id_to_hostname.get(nr.node_id)
        if not hostname:
            continue
        group = ROLE_ANSIBLE_GROUPS.get(nr.role_name)
        if group:
            ansible_groups.setdefault(group, set()).add(hostname)

    children: dict[str, dict] = {
        "slm_nodes": {"hosts": {h: None for h in hosts}},
    }
    for group_name, group_hosts in sorted(ansible_groups.items()):
        children[group_name] = {"hosts": {h: None for h in sorted(group_hosts)}}
    return children, ansible_groups


# Role name -> (variable_name, port) for infrastructure service discovery.
# Maps active roles to the Ansible vars that templates expect (#1431).
_ROLE_INFRA_VARS: dict[str, tuple[str, int]] = {
    "backend": ("backend_host", 8443),
    "redis": ("redis_host", 6379),
    "frontend": ("frontend_host", 5173),
    "ai-stack": ("ai_stack_host", 8080),
    "npu-worker": ("npu_worker_host", 8081),
    "browser-service": ("browser_host", 3000),
}


def _build_infra_vars(
    node_roles: list,
    node_id_to_ip: dict[str, str],
) -> dict:
    """Derive infrastructure discovery vars from active role assignments (#1431)."""
    infra_vars: dict = {}
    for nr in node_roles:
        mapping = _ROLE_INFRA_VARS.get(nr.role_name)
        if not mapping:
            continue
        ip = node_id_to_ip.get(nr.node_id)
        if not ip:
            continue
        host_var, port = mapping
        if host_var not in infra_vars:
            infra_vars[host_var] = ip
            infra_vars[host_var.replace("_host", "_port")] = port
    return infra_vars


async def _generate_dynamic_inventory(
    node_ids: Optional[list[str]] = None,
) -> Optional[Path]:
    """Build Ansible inventory with role-based groups (#1346)."""
    from models.database import Node, NodeRole
    from sqlalchemy import select

    async with db_service.session() as session:
        query = select(Node)
        if node_ids:
            query = query.where(Node.node_id.in_(node_ids))
        db_nodes = (await session.execute(query)).scalars().all()
        if not db_nodes:
            return None

        hosts: dict[str, dict] = {}
        node_id_to_hostname: dict[str, str] = {}
        node_id_to_ip: dict[str, str] = {}
        for node in db_nodes:
            host_vars = {
                "ansible_host": node.ip_address,
                "ansible_user": node.ssh_user or "autobot",
                "slm_node_id": node.node_id,
            }
            if node.ssh_port and node.ssh_port != 22:
                host_vars["ansible_port"] = node.ssh_port
            hosts[node.hostname] = host_vars
            node_id_to_hostname[node.node_id] = node.hostname
            node_id_to_ip[node.node_id] = node.ip_address

        # Only include active roles in Ansible groups (#1431)
        nr_query = select(NodeRole).where(NodeRole.status == "active")
        if node_ids:
            nr_query = nr_query.where(NodeRole.node_id.in_(node_ids))
        all_node_roles = (await session.execute(nr_query)).scalars().all()

        # Fetch ALL active roles for infra var derivation (#1431)
        if node_ids:
            all_nodes = (await session.execute(select(Node))).scalars().all()
            all_ip_map = {n.node_id: n.ip_address for n in all_nodes}
            all_active_q = select(NodeRole).where(NodeRole.status == "active")
            all_active = (await session.execute(all_active_q)).scalars().all()
        else:
            all_ip_map = node_id_to_ip
            all_active = all_node_roles

    children, ansible_groups = _build_inventory_children(
        hosts, all_node_roles, node_id_to_hostname
    )
    infra_vars = _build_infra_vars(all_active, all_ip_map)
    inventory = {
        "all": {
            "vars": {
                "ansible_ssh_private_key_file": "~/.ssh/autobot_key",
                "ansible_python_interpreter": "/usr/bin/python3",
                **infra_vars,
            },
            "hosts": hosts,
            "children": children,
        },
    }

    fd, path = tempfile.mkstemp(suffix=".yml", prefix="wizard-inventory-")
    with open(fd, "w", encoding="utf-8") as f:
        yaml.dump(inventory, f, default_flow_style=False)

    grp = ", ".join(f"{g}({len(h)})" for g, h in sorted(ansible_groups.items()))
    logger.info(
        "Generated inventory at %s: %d nodes, groups: %s",
        path,
        len(hosts),
        grp or "(none)",
    )
    return Path(path)


# ── Provisioning State (#1384) ──────────────────────────────────────────────

_provision_state: dict = {
    "status": "idle",  # idle | running | completed | failed
    "started_at": None,
    "finished_at": None,
    "output_lines": [],
    "error": None,
}
_provision_lock = asyncio.Lock()


def _write_provision_log(line: str) -> None:
    """Append a line to the persistent provision log (#1455)."""
    try:
        _PROVISION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_PROVISION_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _handle_provision_result(result: dict) -> None:
    """Record provisioning result to state and log (#1455)."""
    raw_output = result.get("output", "")
    if raw_output:
        for line in raw_output.splitlines():
            _provision_state["output_lines"].append(line)
            _write_provision_log(line)

    if result.get("success"):
        _provision_state["status"] = "completed"
        _write_provision_log("SUCCESS: Fleet provisioning completed")
        logger.info("Fleet provisioning completed successfully")
    else:
        rc = result.get("returncode", -1)
        _provision_state["status"] = "failed"
        _provision_state["error"] = f"Ansible exited with code {rc}"
        _write_provision_log(f"FAILED: Ansible exited with code {rc}")
        logger.error("Fleet provisioning failed (rc=%s)", rc)


async def _run_provisioning_task(
    node_ids: Optional[list[str]],
) -> None:
    """Run Ansible provisioning in background (#1384)."""
    global _provision_state

    _write_provision_log(
        f"\n{'=' * 60}\n"
        f"Provisioning started at {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Node IDs: {node_ids or 'all'}\n"
        f"{'=' * 60}"
    )

    temp_inventory_path = None
    try:
        temp_inventory_path = await _generate_dynamic_inventory(node_ids)
        if not temp_inventory_path:
            _provision_state["status"] = "failed"
            _provision_state["error"] = "No nodes found for provisioning"
            _provision_state["finished_at"] = time.time()
            _write_provision_log("ERROR: No nodes found for provisioning")
            return

        _write_provision_log(
            f"Inventory: {temp_inventory_path}\n"
            f"{temp_inventory_path.read_text(encoding='utf-8')}"
        )

        executor = get_playbook_executor()

        async def log_callback(progress: dict) -> None:
            msg = progress.get("message", "")
            if msg:
                _provision_state["output_lines"].append(msg)
                _write_provision_log(msg)

        result = await executor.execute_playbook(
            playbook_name="playbooks/provision-fleet-roles.yml",
            extra_vars={},
            inventory_path=temp_inventory_path,
            progress_callback=log_callback,
        )
        _handle_provision_result(result)
    except Exception as exc:
        _provision_state["status"] = "failed"
        _provision_state["error"] = str(exc)
        _write_provision_log(f"EXCEPTION: {exc}")
        logger.exception("Fleet provisioning error: %s", exc)
    finally:
        _provision_state["finished_at"] = time.time()
        if temp_inventory_path and temp_inventory_path.exists():
            temp_inventory_path.unlink(missing_ok=True)


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/status", response_model=WizardStatus)
async def get_wizard_status(
    _: Annotated[dict, Depends(get_current_user)],
):
    """Get the current setup wizard status."""
    is_completed = (await _get_setting("setup_wizard_completed")) == "true"
    current_step = await _get_setting("setup_wizard_current_step", "welcome")

    if current_step not in WIZARD_STEPS:
        current_step = "welcome"

    current_index = WIZARD_STEPS.index(current_step)
    completed_steps_raw = await _get_setting("setup_wizard_completed_steps", "")
    completed_steps = (
        set(completed_steps_raw.split(",")) if completed_steps_raw else set()
    )

    steps = []
    for i, step_name in enumerate(WIZARD_STEPS):
        steps.append(
            {
                "name": step_name,
                "index": i,
                "completed": step_name in completed_steps,
                "current": step_name == current_step,
            }
        )

    return WizardStatus(
        completed=is_completed,
        current_step=current_step,
        current_step_index=current_index,
        total_steps=len(WIZARD_STEPS),
        steps=steps,
    )


@router.post("/complete-step")
async def complete_step(
    request: StepCompleteRequest,
    _: Annotated[dict, Depends(get_current_user)],
):
    """Mark a wizard step as completed and advance to the next."""
    step = request.step
    if step not in WIZARD_STEPS:
        raise HTTPException(status_code=400, detail=f"Unknown step: {step}")

    completed_raw = await _get_setting("setup_wizard_completed_steps", "")
    completed = set(completed_raw.split(",")) if completed_raw else set()
    completed.discard("")
    completed.add(step)
    await _set_setting(
        "setup_wizard_completed_steps",
        ",".join(sorted(completed)),
    )

    current_index = WIZARD_STEPS.index(step)
    if current_index + 1 < len(WIZARD_STEPS):
        next_step = WIZARD_STEPS[current_index + 1]
        await _set_setting("setup_wizard_current_step", next_step)
    else:
        await _set_setting("setup_wizard_completed", "true")
        await _set_setting("setup_wizard_current_step", "complete")

    logger.info("Setup wizard step completed: %s", step)
    return {"status": "ok", "completed_step": step}


@router.post("/skip")
async def skip_wizard(
    _: Annotated[dict, Depends(get_current_user)],
):
    """Skip the setup wizard entirely (mark as completed)."""
    await _set_setting("setup_wizard_completed", "true")
    await _set_setting("setup_wizard_current_step", "complete")
    logger.info("Setup wizard skipped")
    return {"status": "ok", "message": "Setup wizard skipped"}


@router.post("/reset")
async def reset_wizard(
    _: Annotated[dict, Depends(get_current_user)],
):
    """Reset the setup wizard to run again."""
    await _set_setting("setup_wizard_completed", "false")
    await _set_setting("setup_wizard_current_step", "welcome")
    await _set_setting("setup_wizard_completed_steps", "")
    logger.info("Setup wizard reset")
    return {"status": "ok", "message": "Setup wizard reset"}


@router.post("/provision-fleet")
async def provision_fleet(
    request: ProvisionRequest,
    _: Annotated[dict, Depends(get_current_user)],
):
    """Start fleet provisioning as a background task (#1384).

    Returns immediately. Poll GET /provision-status for logs.
    """
    global _provision_state

    async with _provision_lock:
        if _provision_state["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="Provisioning is already running",
            )

        _provision_state = {
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "output_lines": [],
            "error": None,
        }

    logger.info(
        "Starting fleet provisioning (nodes: %s)",
        request.node_ids or "all",
    )

    asyncio.create_task(_run_provisioning_task(request.node_ids))

    return {
        "status": "started",
        "message": "Provisioning started in background",
    }


@router.get("/provision-status")
async def get_provision_status(
    _: Annotated[dict, Depends(get_current_user)],
    since_line: int = 0,
):
    """Poll provisioning progress and log output (#1384).

    Args:
        since_line: Return lines from this index (incremental).
    """
    lines = _provision_state["output_lines"]
    new_lines = lines[since_line:] if since_line < len(lines) else []

    result = {
        "status": _provision_state["status"],
        "lines": new_lines,
        "total_lines": len(lines),
        "error": _provision_state.get("error"),
    }

    if _provision_state["started_at"]:
        elapsed = (
            _provision_state.get("finished_at") or time.time()
        ) - _provision_state["started_at"]
        result["elapsed_seconds"] = round(elapsed, 1)

    return result


@router.get("/validate")
async def validate_fleet(
    _: Annotated[dict, Depends(get_current_user)],
):
    """Validate that all fleet nodes are healthy."""
    from models.database import Node, NodeRole
    from services.role_registry import DEFAULT_ROLES
    from sqlalchemy import func, select

    async with db_service.session() as session:
        node_count_result = await session.execute(select(func.count(Node.id)))
        total_nodes = node_count_result.scalar() or 0

        online_result = await session.execute(
            select(func.count(Node.id)).where(Node.status == "online")
        )
        online_nodes = online_result.scalar() or 0

        required_roles = [r["name"] for r in DEFAULT_ROLES if r.get("required")]
        missing_roles = []
        for role_name in required_roles:
            active = await session.execute(
                select(func.count(NodeRole.id)).where(
                    NodeRole.role_name == role_name,
                    NodeRole.status == "active",
                )
            )
            if (active.scalar() or 0) == 0:
                missing_roles.append(role_name)

    health = "healthy"
    if missing_roles:
        health = "critical"
    elif online_nodes < total_nodes:
        health = "degraded"

    return {
        "health": health,
        "total_nodes": total_nodes,
        "online_nodes": online_nodes,
        "missing_required_roles": missing_roles,
        "ready": health in ("healthy", "degraded") and total_nodes > 0,
    }
