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

from api.websocket import ws_manager
from services.auth import get_current_user
from services.database import db_service
from services.playbook_executor import get_playbook_executor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["setup-wizard"])

# -- Wizard Steps ------------------------------------------------------------

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


# -- Schemas -----------------------------------------------------------------


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


# -- Settings Helpers --------------------------------------------------------


async def _get_setting(key: str, default: str = "") -> str:
    """Read a setting value from the database."""
    from sqlalchemy import select

    from models.database import Setting

    async with db_service.session() as session:
        result = await session.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        return setting.value if setting else default


async def _set_setting(key: str, value: str) -> None:
    """Write a setting value to the database."""
    from sqlalchemy import select

    from models.database import Setting

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
    node_id_to_inv_name: dict[str, str],
) -> tuple[dict[str, dict], dict[str, set[str]]]:
    """Build Ansible inventory ``children`` with role-based groups (#1346).

    Returns (children dict, ansible_groups) where ansible_groups maps
    group name to set of inventory names for logging.
    """
    from services.role_registry import ROLE_ANSIBLE_GROUPS

    ansible_groups: dict[str, set[str]] = {}
    for nr in node_roles:
        inv_name = node_id_to_inv_name.get(nr.node_id)
        if not inv_name:
            continue
        group = ROLE_ANSIBLE_GROUPS.get(nr.role_name)
        if group:
            ansible_groups.setdefault(group, set()).add(inv_name)

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
    from sqlalchemy import select

    from models.database import Node, NodeRole

    async with db_service.session() as session:
        query = select(Node)
        if node_ids:
            query = query.where(Node.node_id.in_(node_ids))
        db_nodes = (await session.execute(query)).scalars().all()
        if not db_nodes:
            return None

        from autobot_shared.network_utils import get_local_ips

        hosts: dict[str, dict] = {}
        node_id_to_hostname: dict[str, str] = {}
        node_id_to_ip: dict[str, str] = {}
        # Detect local IPs for ansible_connection: local (#2722)
        local_ips = get_local_ips()

        for node in db_nodes:
            host_vars = {
                "ansible_host": node.ip_address,
                "ansible_user": node.ssh_user or "autobot",
                "slm_node_id": node.node_id,
            }
            if node.ip_address in local_ips:
                host_vars["ansible_connection"] = "local"
            if node.ssh_port and node.ssh_port != 22:
                host_vars["ansible_port"] = node.ssh_port
            inventory_name = node.ansible_target  # #1814
            hosts[inventory_name] = host_vars
            node_id_to_hostname[node.node_id] = inventory_name
            node_id_to_ip[node.node_id] = node.ip_address

        # Include all assigned roles for provisioning (active + inactive + not_installed)
        # The wizard provisions roles that aren't yet active (#2747)
        nr_query = select(NodeRole).where(
            NodeRole.status.in_(["active", "inactive", "not_installed"])
        )
        if node_ids:
            nr_query = nr_query.where(NodeRole.node_id.in_(node_ids))
        all_node_roles = (await session.execute(nr_query)).scalars().all()

        # Set node_roles per host so provision-fleet-roles.yml conditions work
        node_id_to_roles: dict[str, list[str]] = {}
        for nr in all_node_roles:
            node_id_to_roles.setdefault(nr.node_id, []).append(nr.role_name)
        for node in db_nodes:
            inv_name = node.ansible_target
            if inv_name in hosts and node.node_id in node_id_to_roles:
                hosts[inv_name]["node_roles"] = node_id_to_roles[node.node_id]

        # Resolve dependencies for Phase 0 (#2747)
        from services.role_registry import ROLE_DEPENDENCIES

        for node in db_nodes:
            inv_name = node.ansible_target
            if inv_name not in hosts:
                continue
            roles = hosts[inv_name].get("node_roles", [])
            deps: set[str] = set()
            for role in roles:
                deps.update(ROLE_DEPENDENCIES.get(role, []))
            hosts[inv_name]["node_dependencies"] = sorted(deps)

            # Pending removals from extra_data
            extra = node.extra_data or {}
            pending = extra.get("pending_dep_removals", [])
            if pending:
                hosts[inv_name]["pending_dep_removals"] = pending

        # Detect co-located frontend for SLM nginx routing (#2829)
        # When a node on the SLM host also has the 'frontend' role,
        # set slm_colocated_frontend so the SLM nginx config serves
        # user frontend at / and SLM at /slm/ instead of redirecting.
        # Also configure the backend upstream to proxy directly to
        # uvicorn (HTTP on port 8001) instead of through the backend
        # nginx (HTTPS on port 8443), eliminating the double-proxy.
        _frontend_roles = {"frontend", "autobot-frontend"}
        _backend_roles = {"backend", "autobot-backend"}
        for node in db_nodes:
            inv_name = node.ansible_target
            if inv_name not in hosts:
                continue
            roles = set(hosts[inv_name].get("node_roles", []))
            if node.ip_address in local_ips and roles & _frontend_roles:
                hosts[inv_name]["slm_colocated_frontend"] = True
                # When backend is also co-located, proxy directly to
                # uvicorn (HTTP) -- the backend nginx vhost is skipped.
                if roles & _backend_roles:
                    hosts[inv_name]["frontend_backend_port"] = 8001
                    hosts[inv_name]["frontend_backend_protocol"] = "http"

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

    # Derive slm_host from external_url so the slm_agent role resolves the
    # correct admin URL on single-host installs (#2747).  On single-host the
    # SLM Manager runs on the same machine as the backend; external_url holds
    # the routable IP that remote nodes should use.  The slm_agent role's
    # default builds slm_admin_url from this value, and the template's
    # auto-detect logic then rewrites it to 127.0.0.1 when the agent is
    # co-located -- but only after slm_host contains the real local IP rather
    # than the hardcoded multi-node default (172.16.168.19).
    from urllib.parse import urlparse

    from config import settings as _slm_settings

    _slm_host = urlparse(_slm_settings.external_url).hostname or "127.0.0.1"

    inventory = {
        "all": {
            "vars": {
                # Issue #2828: Use shared key path for any-operator access
                "ansible_ssh_private_key_file": "/etc/autobot/ssh/autobot_key",
                "ansible_python_interpreter": "/usr/bin/python3",
                "slm_host": _slm_host,
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


async def _ssh_check_host(
    hostname: str, ip: str, user: str, key: str
) -> tuple[str, bool]:
    """Run a single SSH connectivity probe and return (hostname, reachable).

    Uses BatchMode=yes so the process never prompts for a password (#2897).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "BatchMode=yes",
            "-i",
            key,
            f"{user}@{ip}",
            "echo",
            "ok",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10)
        reachable = proc.returncode == 0
    except (asyncio.TimeoutError, OSError):
        reachable = False
    return hostname, reachable


async def _check_node_reachability(inventory_path: Path) -> dict[str, bool]:
    """Parse the generated inventory and SSH-probe each non-local host (#2897).

    Local hosts (ansible_connection: local) are always considered reachable.
    Probes run in parallel; each probe has a 5-second ConnectTimeout plus a
    10-second asyncio timeout as a safety net.

    Returns a dict mapping inventory hostname -> reachable (bool).
    """
    raw = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    all_vars = raw.get("all", {}).get("vars", {})
    default_key = str(
        Path(
            all_vars.get(
                "ansible_ssh_private_key_file",
                "/etc/autobot/ssh/autobot_key",  # Issue #2828
            )
        ).expanduser()
    )
    default_user = all_vars.get("ansible_user", "autobot")

    hosts: dict[str, dict] = raw.get("all", {}).get("hosts", {})
    tasks = []
    local_hosts: set[str] = set()

    for hostname, host_vars in hosts.items():
        if not isinstance(host_vars, dict):
            host_vars = {}
        if host_vars.get("ansible_connection") == "local":
            local_hosts.add(hostname)
            continue
        ip = host_vars.get("ansible_host", hostname)
        user = host_vars.get("ansible_user", default_user)
        key = str(
            Path(
                host_vars.get("ansible_ssh_private_key_file", default_key)
            ).expanduser()
        )
        tasks.append(_ssh_check_host(hostname, ip, user, key))

    results: dict[str, bool] = {h: True for h in local_hosts}
    if tasks:
        for hostname, reachable in await asyncio.gather(*tasks):
            results[hostname] = reachable

    for hostname, reachable in results.items():
        if not reachable:
            host_vars = hosts.get(hostname, {})
            ip = (
                host_vars.get("ansible_host", hostname)
                if isinstance(host_vars, dict)
                else hostname
            )
            logger.warning(
                "Node %s (%s) is unreachable -- skipping (not enrolled?)",
                hostname,
                ip,
            )
    return results


# -- Provisioning State (#1384) ----------------------------------------------


async def _activate_provisioned_roles(
    node_ids: Optional[list[str]],
) -> None:
    """Mark all roles on provisioned nodes as 'active' (#2836, #2900).

    After provisioning deploys code/services to a node, the role status
    should reflect that.  Without this, roles stay 'inactive'/'not_installed'
    and infra-var derivation (backend_host, redis_host) breaks.
    """
    from models.database import NodeRole

    try:
        async with db_service.session() as session:
            query = select(NodeRole).where(
                NodeRole.status.in_(["inactive", "not_installed"])
            )
            if node_ids:
                query = query.where(NodeRole.node_id.in_(node_ids))
            roles = (await session.execute(query)).scalars().all()
            activated = []
            for role in roles:
                role.status = "active"
                activated.append(f"{role.node_id}/{role.role_name}")
            await session.commit()
            if activated:
                logger.info(
                    "Activated %d roles after provisioning: %s",
                    len(activated),
                    activated,
                )
    except Exception as exc:
        logger.warning("Failed to activate provisioned roles: %s", exc)


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
    _write_provision_log(
        f"\n{'=' * 60}\n"
        f"Provisioning started at {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Node IDs: {node_ids or 'all'}\n"
        f"{'=' * 60}"
    )
    await ws_manager.send_provision_status("running", "starting", 0)
    await ws_manager.send_provision_log("info", "Provisioning started")

    temp_inventory_path = None
    try:
        temp_inventory_path = await _generate_dynamic_inventory(node_ids)
        if not temp_inventory_path:
            _provision_state["status"] = "failed"
            _provision_state["error"] = "No nodes found for provisioning"
            _provision_state["finished_at"] = time.time()
            _write_provision_log("ERROR: No nodes found for provisioning")
            await ws_manager.send_provision_status(
                "failed", "", 0, error="No nodes found for provisioning"
            )
            await ws_manager.send_provision_log(
                "error", "No nodes found for provisioning"
            )
            return

        _write_provision_log(
            f"Inventory: {temp_inventory_path}\n"
            f"{temp_inventory_path.read_text(encoding='utf-8')}"
        )

        # Pre-check SSH reachability before running Ansible (#2897)
        reachability = await _check_node_reachability(temp_inventory_path)
        unreachable = [h for h, ok in reachability.items() if not ok]
        reachable = [h for h, ok in reachability.items() if ok]

        if unreachable:
            raw_inv = yaml.safe_load(temp_inventory_path.read_text(encoding="utf-8"))
            inv_hosts = raw_inv.get("all", {}).get("hosts", {})
            for hostname in unreachable:
                host_vars = inv_hosts.get(hostname, {})
                ip = (
                    host_vars.get("ansible_host", hostname)
                    if isinstance(host_vars, dict)
                    else hostname
                )
                msg = (
                    f"Node {hostname} ({ip}) is unreachable"
                    " -- skipping (not enrolled?)"
                )
                _write_provision_log(f"WARNING: {msg}")
                await ws_manager.send_provision_log("warning", msg)

        if not reachable:
            _provision_state["status"] = "failed"
            _provision_state["error"] = (
                "All nodes are unreachable"
                " -- ensure nodes are enrolled before provisioning"
            )
            _provision_state["finished_at"] = time.time()
            _write_provision_log("ERROR: All nodes are unreachable")
            await ws_manager.send_provision_status(
                "failed",
                "",
                0,
                error=(
                    "All nodes are unreachable"
                    " -- ensure nodes are enrolled before provisioning"
                ),
            )
            await ws_manager.send_provision_log(
                "error",
                (
                    "All nodes are unreachable"
                    " -- ensure nodes are enrolled before provisioning"
                ),
            )
            return

        # Build --limit to include only reachable nodes (#2897)
        reachability_limit: Optional[list[str]] = None
        if unreachable:
            reachability_limit = reachable
            logger.info(
                "Excluding %d unreachable node(s) from provisioning: %s",
                len(unreachable),
                unreachable,
            )

        executor = get_playbook_executor()

        async def log_callback(progress: dict) -> None:
            msg = progress.get("message", "")
            stage = progress.get("stage", "")
            if msg:
                _provision_state["output_lines"].append(msg)
                _write_provision_log(msg)
                # Broadcast via WebSocket (#2754)
                log_type = "task"
                if stage.endswith("_complete") or stage == "complete":
                    log_type = "success"
                elif "error" in msg.lower() or "failed" in msg.lower():
                    log_type = "error"
                await ws_manager.send_provision_log(log_type, msg)
                elapsed = time.time() - (
                    _provision_state.get("started_at") or time.time()
                )
                await ws_manager.send_provision_status("running", stage, elapsed)

        result = await executor.execute_playbook(
            playbook_name="playbooks/provision-fleet-roles.yml",
            extra_vars={},
            limit=reachability_limit,
            inventory_path=temp_inventory_path,
            progress_callback=log_callback,
        )
        _handle_provision_result(result)

        # Activate roles on provisioned nodes (#2836, #2900)
        # Even with partial failures, roles on reachable nodes were deployed.
        await _activate_provisioned_roles(reachable or node_ids)

        elapsed = time.time() - (_provision_state.get("started_at") or time.time())
        if result.get("success"):
            await ws_manager.send_provision_status("completed", "complete", elapsed)
            await ws_manager.send_provision_log(
                "success", "Fleet provisioning completed successfully"
            )
        else:
            rc = result.get("returncode", -1)
            await ws_manager.send_provision_status(
                "failed", "", elapsed, error=f"Ansible exited with code {rc}"
            )
            await ws_manager.send_provision_log(
                "error", f"Provisioning failed (exit code {rc})"
            )
    except Exception as exc:
        _provision_state["status"] = "failed"
        _provision_state["error"] = str(exc)
        _write_provision_log(f"EXCEPTION: {exc}")
        logger.exception("Fleet provisioning error: %s", exc)
        elapsed = time.time() - (_provision_state.get("started_at") or time.time())
        # Sanitize -- Ansible exceptions may contain credentials (#2754)
        await ws_manager.send_provision_status(
            "failed", "", elapsed, error="internal error"
        )
        await ws_manager.send_provision_log(
            "error", "Provisioning error: internal error (see server logs)"
        )
    finally:
        _provision_state["finished_at"] = time.time()
        if temp_inventory_path and temp_inventory_path.exists():
            temp_inventory_path.unlink(missing_ok=True)


# -- Endpoints ---------------------------------------------------------------


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
    from sqlalchemy import func, select

    from models.database import Node, NodeRole

    async with db_service.session() as session:
        node_count_result = await session.execute(select(func.count(Node.id)))
        total_nodes = node_count_result.scalar() or 0

        online_result = await session.execute(
            select(func.count(Node.id)).where(Node.status == "online")
        )
        online_nodes = online_result.scalar() or 0

        # Only check roles that are actually assigned to nodes (#2747)
        # Roles not yet assigned via wizard are not "missing"
        assigned_roles = (
            (await session.execute(select(NodeRole.role_name).distinct()))
            .scalars()
            .all()
        )
        missing_roles = []
        for role_name in assigned_roles:
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
        health = "degraded"
    elif online_nodes < total_nodes:
        health = "degraded"

    return {
        "health": health,
        "total_nodes": total_nodes,
        "online_nodes": online_nodes,
        "missing_required_roles": missing_roles,
        "ready": total_nodes > 0,
    }
