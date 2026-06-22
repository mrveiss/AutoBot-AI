# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

_PROVISION_LOG = Path("/var/log/autobot/provision-wizard.log")

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.websocket import ws_manager
from config import settings
from services.ansible_secrets import fetch_deploy_secrets
from services.ansible_utils import _extract_failure_summary
from services.auth import get_current_user
from services.database import db_service
from services.playbook_executor import get_playbook_executor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["setup-wizard"])

# -- Wizard Steps ────────────────────────────────────────────────────────────

WIZARD_STEPS = [
    "welcome",
    "add_nodes",
    "test_connections",
    "enroll_agents",
    "assign_roles",
    "configure_secrets",
    "provision_fleet",
    "verify_health",
    "complete",
]


# -- Schemas ─────────────────────────────────────────────────────────────────


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

    node_ids: list[str] | None = None


# -- Settings Helpers ─────────────────────────────────────────────────────────


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
# Ports are INTERNAL service ports (uvicorn/service listen ports), not the
# external nginx TLS port (8443).  Co-located nodes use 127.0.0.1 so uvicorn
# binds to loopback; nginx already holds 8443 on the same host (#3426).
_ROLE_INFRA_VARS: dict[str, tuple[str, int]] = {
    "backend": ("backend_host", 8001),  # uvicorn internal port (#3426: was 8443)
    "redis": ("redis_host", 6379),
    "frontend": ("frontend_host", 5173),
    "ai-stack": ("ai_stack_host", 8080),
    "npu-worker": ("npu_worker_host", 8081),
    "browser-service": ("browser_host", 3000),
    "tts-worker": (
        "tts_host",
        8083,
    ),  # Issue #3431: 8082 is WSL2/Hyper-V reserved (Windows NPU)
}

# ChromaDB runs on the AI stack VM but is NOT a separately-routed role, so it
# has no entry in _ROLE_INFRA_VARS.  This constant must match chromadb_port in
# ansible/roles/ai-stack/defaults/main.yml and backend_chromadb_port in
# ansible/roles/backend/defaults/main.yml (#3526).
_CHROMADB_PORT = 8100


def _build_infra_vars(
    node_roles: list,
    node_id_to_ip: dict[str, str],
    local_ips: set | None = None,
) -> dict:
    """Derive infrastructure discovery vars from active role assignments (#1431).

    For co-located services (node IP in local_ips), uses 127.0.0.1 so that
    uvicorn and other daemons bind to loopback rather than an external
    interface that nginx may already hold (#3426).
    """
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
            # Co-located: use loopback so services bind correctly on the SLM host.
            resolved = "127.0.0.1" if (local_ips and ip in local_ips) else ip
            infra_vars[host_var] = resolved
            infra_vars[host_var.replace("_host", "_port")] = port
    return infra_vars


def _sanitize_ansible_name(name: str) -> str:
    """Sanitize a name to be Ansible group/host compliant (#9283).

    Ansible group names (and host names, which create implicit groups)
    must not start with numbers and should avoid hyphens to prevent
    warnings. Converts names like '01-Backend' to 'node_01_Backend'.

    Returns a name that:
    - Contains only letters, numbers, and underscores
    - Does not start with a number
    - Does not contain hyphens
    """
    import re

    # Replace hyphens with underscores
    sanitized = name.replace("-", "_")
    # Replace any other non-alphanumeric/underscore chars with underscores
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", sanitized)
    # Prepend 'node_' if starts with a number
    if sanitized and sanitized[0].isdigit():
        sanitized = f"node_{sanitized}"
    return sanitized


def _build_host_entries(
    db_nodes: list,
    local_ips: set,
) -> tuple[dict[str, dict], dict[str, str], dict[str, str]]:
    """Build per-host inventory entries from DB node records (#2823, #9283).

    Returns (hosts, node_id_to_hostname, node_id_to_ip).
    Sets ansible_connection=local for nodes whose IP is on this machine (#2722).

    Issue #9283: Sanitizes inventory names to avoid Ansible warnings about
    invalid group characters (host names create implicit groups).
    """
    hosts: dict[str, dict] = {}
    node_id_to_hostname: dict[str, str] = {}
    node_id_to_ip: dict[str, str] = {}
    for node in db_nodes:
        host_vars: dict = {
            "ansible_host": node.ip_address,
            "ansible_user": node.ssh_user or "autobot",
            "slm_node_id": node.node_id,
        }
        if node.ip_address in local_ips:
            host_vars["ansible_connection"] = "local"
        if node.ssh_port and node.ssh_port != 22:
            host_vars["ansible_port"] = node.ssh_port
        # Issue #9283: Sanitize inventory name to avoid Ansible warnings
        raw_name = node.ansible_target  # #1814
        inventory_name = _sanitize_ansible_name(raw_name)
        hosts[inventory_name] = host_vars
        node_id_to_hostname[node.node_id] = inventory_name
        node_id_to_ip[node.node_id] = node.ip_address
    return hosts, node_id_to_hostname, node_id_to_ip


def _apply_role_host_vars(
    hosts: dict[str, dict],
    db_nodes: list,
    all_node_roles: list,
) -> None:
    """Stamp node_roles, node_dependencies, and pending_dep_removals onto hosts (#2823).

    Sets node_roles so provision-fleet-roles.yml conditions work, resolves
    shared-dependency names for Phase 0 (#2747), and propagates any pending
    dependency removals recorded in node.extra_data.
    """
    from services.role_registry import ROLE_DEPENDENCIES

    node_id_to_roles: dict[str, list[str]] = {}
    for nr in all_node_roles:
        node_id_to_roles.setdefault(nr.node_id, []).append(nr.role_name)
    for node in db_nodes:
        # #9965: hosts is keyed by the SANITIZED ansible name (_fetch_inventory_data
        # uses _sanitize_ansible_name), so the raw node.ansible_target never matched
        # the host key (e.g. '00-SLM-Manager' vs 'node_00_SLM_Manager') and these
        # per-host vars (node_roles, colocation, etc.) were silently never applied.
        inv_name = _sanitize_ansible_name(node.ansible_target)
        if inv_name not in hosts:
            continue
        if node.node_id in node_id_to_roles:
            hosts[inv_name]["node_roles"] = node_id_to_roles[node.node_id]
        roles = hosts[inv_name].get("node_roles", [])
        deps: set[str] = set()
        for role in roles:
            deps.update(ROLE_DEPENDENCIES.get(role, []))
        hosts[inv_name]["node_dependencies"] = sorted(deps)
        pending = (node.extra_data or {}).get("pending_dep_removals", [])
        if pending:
            hosts[inv_name]["pending_dep_removals"] = pending


def _apply_colocation_vars(
    hosts: dict[str, dict],
    db_nodes: list,
    local_ips: set,
) -> None:
    """Set co-location Ansible vars when frontend/backend share the SLM host (#2823).

    When a node on the SLM host also carries the 'frontend' role, sets
    slm_colocated_frontend=True so the SLM nginx config serves the user
    frontend at / and SLM at /slm/ (#2829).  When backend is co-located too,
    sets frontend_backend_port=8001 and frontend_backend_protocol=http so
    templates proxy directly to uvicorn, eliminating the double-proxy.

    Also propagates slm_colocated_frontend=True to the SLM manager host
    entry so Phase 4c in provision-fleet-roles.yml can rebuild the SLM
    frontend with VITE_API_URL=/slm (#3426).
    """
    _frontend_roles = {"frontend", "autobot-frontend"}
    _backend_roles = {"backend", "autobot-backend"}
    colocated_frontend_detected = False
    for node in db_nodes:
        # #9965: hosts is keyed by the SANITIZED ansible name (_fetch_inventory_data
        # uses _sanitize_ansible_name), so the raw node.ansible_target never matched
        # the host key (e.g. '00-SLM-Manager' vs 'node_00_SLM_Manager') and these
        # per-host vars (node_roles, colocation, etc.) were silently never applied.
        inv_name = _sanitize_ansible_name(node.ansible_target)
        if inv_name not in hosts:
            continue
        roles = set(hosts[inv_name].get("node_roles", []))
        # Match by IP or by the fixed SLM manager node_id (#3227): the registered
        # IP may be stale (e.g. SLM_EXTERNAL_URL not updated after reinstall).
        is_local = node.ip_address in local_ips or node.node_id == settings.slm_node_id
        if is_local and roles & _frontend_roles:
            hosts[inv_name]["slm_colocated_frontend"] = True
            colocated_frontend_detected = True
            if roles & _backend_roles:
                hosts[inv_name]["frontend_backend_host"] = "127.0.0.1"
                hosts[inv_name]["frontend_backend_port"] = 8001
                hosts[inv_name]["frontend_backend_protocol"] = "http"

    # Propagate to the SLM manager so Phase 4c can rebuild the SLM frontend
    # with VITE_API_URL=/slm after the user frontend has been deployed (#3426).
    if colocated_frontend_detected:
        for node in db_nodes:
            if node.node_id == settings.slm_node_id and node.ansible_target in hosts:
                hosts[node.ansible_target]["slm_colocated_frontend"] = True
                break


def _inject_co_located_ai_stack(
    hosts: dict[str, dict],
    db_nodes: list,
    fleet_has_ai_stack: bool,
) -> list[str]:
    """Auto-inject ai-stack onto backend nodes when no fleet node has it (#3461).

    On single-host co-located deployments, users often assign backend/frontend/
    redis but forget ai-stack (which deploys ChromaDB).  Without ChromaDB, the
    knowledge base is permanently unhealthy.  When the full fleet has no ai-stack
    assignment, silently add it to each backend node so Phase 5a runs the role.

    In distributed setups where a dedicated AI stack VM already carries ai-stack,
    fleet_has_ai_stack is True and this function is a no-op.

    Returns the list of inventory names onto which ai-stack was injected so the
    caller can patch infra_vars without a second DB query (#3515).
    """
    if fleet_has_ai_stack:
        return []

    _ai_stack_roles = {"ai-stack", "autobot-ai-stack"}
    _backend_roles = {"backend", "autobot-backend"}
    injected: list[str] = []

    for node in db_nodes:
        # #9965: hosts is keyed by the SANITIZED ansible name (_fetch_inventory_data
        # uses _sanitize_ansible_name), so the raw node.ansible_target never matched
        # the host key (e.g. '00-SLM-Manager' vs 'node_00_SLM_Manager') and these
        # per-host vars (node_roles, colocation, etc.) were silently never applied.
        inv_name = _sanitize_ansible_name(node.ansible_target)
        if inv_name not in hosts:
            continue
        roles = hosts[inv_name].get("node_roles", [])
        if not (_backend_roles & set(roles)):
            continue
        if _ai_stack_roles & set(roles):
            continue
        hosts[inv_name]["node_roles"] = list(roles) + ["ai-stack"]
        # Note: ai-stack role now defaults to autobot:autobot (not autobot-ai)
        # per unified service account model (#4091). No override needed.
        injected.append(inv_name)
        logger.info(
            "Auto-injecting ai-stack onto %s (no dedicated AI stack node in fleet; #3461)",
            inv_name,
        )
    return injected


def _build_inventory_dict(
    hosts: dict[str, dict],
    children: dict[str, dict],
    infra_vars: dict,
) -> dict:
    """Assemble the top-level Ansible inventory structure (#2823).

    Derives slm_host from external_url so the slm_agent role builds the
    correct admin URL on single-host installs (#2747).  Merges infra service
    discovery vars alongside fixed SSH key and interpreter paths (#2828).
    """
    from urllib.parse import urlparse

    from config import settings as _slm_settings

    slm_host = urlparse(_slm_settings.external_url).hostname or "127.0.0.1"
    return {
        "all": {
            "vars": {
                # Issue #2828: Use shared key path for any-operator access
                "ansible_ssh_private_key_file": "/etc/autobot/ssh/autobot_key",
                "ansible_python_interpreter": "/usr/bin/python3",
                "slm_host": slm_host,
                **infra_vars,
            },
            "hosts": hosts,
            "children": children,
        },
    }


async def _fetch_inventory_data(
    node_ids: list[str] | None,
) -> (
    tuple[
        list,
        dict[str, dict],
        dict[str, str],
        dict[str, str],
        list,
        list,
        dict[str, str],
        set,
        list[str],
    ]
    | None
):
    """Load all DB data needed to build the Ansible inventory (#2823).

    Returns (db_nodes, hosts, node_id_to_hostname, node_id_to_ip,
             all_node_roles, all_active, all_ip_map, local_ips,
             injected_ai_stack) or None when no nodes match.
    """
    from sqlalchemy import select

    from autobot_shared.network_utils import get_local_ips
    from models.database import Node, NodeRole

    injected_ai_stack: list[str] = []
    async with db_service.session() as session:
        query = select(Node)
        if node_ids:
            query = query.where(Node.node_id.in_(node_ids))
        db_nodes = (await session.execute(query)).scalars().all()
        if not db_nodes:
            return None

        local_ips = get_local_ips()
        hosts, node_id_to_hostname, node_id_to_ip = _build_host_entries(db_nodes, local_ips)

        # Include active + inactive + not_installed roles for provisioning (#2747)
        nr_query = select(NodeRole).where(NodeRole.status.in_(["active", "inactive", "not_installed"]))
        if node_ids:
            nr_query = nr_query.where(NodeRole.node_id.in_(node_ids))
        all_node_roles = (await session.execute(nr_query)).scalars().all()

        _apply_role_host_vars(hosts, db_nodes, all_node_roles)
        _apply_colocation_vars(hosts, db_nodes, local_ips)

        # (#3461) Check full fleet for ai-stack assignment (independent of node_ids filter)
        # so single-host setups get ChromaDB even if user forgot to assign ai-stack.
        fleet_ai_q = select(NodeRole).where(
            NodeRole.status.in_(["active", "inactive", "not_installed"]),
            NodeRole.role_name.in_(["ai-stack", "autobot-ai-stack"]),
        )
        fleet_ai_stack = (await session.execute(fleet_ai_q)).scalars().all()
        injected_ai_stack = _inject_co_located_ai_stack(hosts, db_nodes, fleet_has_ai_stack=len(fleet_ai_stack) > 0)

        # Fetch ALL active roles for infra var derivation (#1431)
        if node_ids:
            all_nodes = (await session.execute(select(Node))).scalars().all()
            all_ip_map = {n.node_id: n.ip_address for n in all_nodes}
            all_active_q = select(NodeRole).where(NodeRole.status == "active")
            all_active = (await session.execute(all_active_q)).scalars().all()
        else:
            all_ip_map = node_id_to_ip
            all_active = all_node_roles

    return (
        db_nodes,
        hosts,
        node_id_to_hostname,
        node_id_to_ip,
        all_node_roles,
        all_active,
        all_ip_map,
        local_ips,
        injected_ai_stack,
    )


async def _generate_dynamic_inventory(
    node_ids: list[str] | None = None,
) -> Path | None:
    """Build Ansible inventory with role-based groups (#1346, #2823).

    Orchestrates focused helpers: _fetch_inventory_data, _build_inventory_children,
    _build_infra_vars, and _build_inventory_dict, then writes the result to a
    temporary YAML file for Ansible consumption.
    """
    result = await _fetch_inventory_data(node_ids)
    if result is None:
        return None

    (
        _db_nodes,
        hosts,
        node_id_to_hostname,
        _node_id_to_ip,
        all_node_roles,
        all_active,
        all_ip_map,
        local_ips,
        injected_ai_stack,
    ) = result
    # #9965: stamp node_roles (+ deps) onto each host so role_active_facts.yml
    # activates roles via node_roles. Without this the wizard inventory only
    # carries group membership, and roles whose mapped group isn't the one
    # role_*_active checks (tts-worker, browser-service) silently never deploy —
    # the provision reports failed=0 while optional roles stay inactive.
    _apply_role_host_vars(hosts, _db_nodes, all_node_roles)
    children, ansible_groups = _build_inventory_children(hosts, all_node_roles, node_id_to_hostname)
    infra_vars = _build_infra_vars(all_active, all_ip_map, local_ips)
    # For co-located ai-stack (injected, no dedicated AI stack VM), _build_infra_vars
    # never sees the injected role because it reads from DB node_roles, not the
    # in-memory hosts dict.  Explicitly populate ai_stack_host/port so templates
    # that reference {{ ai_stack_host }} resolve correctly (#3515).
    if injected_ai_stack and "ai_stack_host" not in infra_vars:
        infra_vars["ai_stack_host"] = "127.0.0.1"
        infra_vars["ai_stack_port"] = _ROLE_INFRA_VARS["ai-stack"][1]
    # Auto-derive backend_chromadb_host from ai_stack_host for fleet deployments (#3523).
    # In co-located setups ai_stack_host is 127.0.0.1 (correct); in fleet setups it
    # is the AI stack node IP (also correct).  backend_chromadb_host in role defaults
    # is always 127.0.0.1 and has no knowledge of fleet topology.
    if "ai_stack_host" in infra_vars and "backend_chromadb_host" not in infra_vars:
        infra_vars["backend_chromadb_host"] = infra_vars["ai_stack_host"]
        infra_vars["backend_chromadb_port"] = _CHROMADB_PORT
    inventory = _build_inventory_dict(hosts, children, infra_vars)

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


async def _ssh_check_host(hostname: str, ip: str, user: str, key: str) -> tuple[str, bool]:
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
        key = str(Path(host_vars.get("ansible_ssh_private_key_file", default_key)).expanduser())
        tasks.append(_ssh_check_host(hostname, ip, user, key))

    results: dict[str, bool] = {h: True for h in local_hosts}
    if tasks:
        for hostname, reachable in await asyncio.gather(*tasks):
            results[hostname] = reachable

    for hostname, reachable in results.items():
        if not reachable:
            host_vars = hosts.get(hostname, {})
            ip = host_vars.get("ansible_host", hostname) if isinstance(host_vars, dict) else hostname
            logger.warning(
                "Node %s (%s) is unreachable -- skipping (not enrolled?)",
                hostname,
                ip,
            )
    return results


# -- Provisioning State (#1384) ───────────────────────────────────────────────


async def _activate_provisioned_roles(
    node_ids: list[str] | None,
) -> None:
    """Mark all roles on provisioned nodes as 'active' (#2836, #2900).

    After provisioning deploys code/services to a node, the role status
    should reflect that.  Without this, roles stay 'inactive'/'not_installed'
    and infra-var derivation (backend_host, redis_host) breaks.
    """
    from sqlalchemy import select

    from models.database import NodeRole

    try:
        async with db_service.session() as session:
            query = select(NodeRole).where(NodeRole.status.in_(["inactive", "not_installed"]))
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
        summary = _extract_failure_summary(raw_output)
        _provision_state["error"] = summary or f"Ansible exited with code {rc}"
        _write_provision_log(f"FAILED: {_provision_state['error']}")
        logger.error("Fleet provisioning failed (rc=%s): %s", rc, _provision_state["error"])


async def _create_wizard_deployments(
    node_ids: list[str] | None,
) -> dict[str, str]:
    """Create one Deployment record per provisioned node before playbook runs (#3032).

    Returns a mapping of node_id -> deployment_id so the caller can update
    records after provisioning completes.  Roles are derived from the
    NodeRole assignments already stored for each node.
    """
    from sqlalchemy import select

    from models.database import Deployment, DeploymentStatus, Node, NodeRole

    node_to_deployment: dict[str, str] = {}
    try:
        async with db_service.session() as session:
            q = select(Node)
            if node_ids:
                q = q.where(Node.node_id.in_(node_ids))
            db_nodes = (await session.execute(q)).scalars().all()

            nr_q = select(NodeRole).where(NodeRole.status.in_(["active", "inactive", "not_installed"]))
            if node_ids:
                nr_q = nr_q.where(NodeRole.node_id.in_(node_ids))
            node_roles = (await session.execute(nr_q)).scalars().all()

            roles_by_node: dict[str, list[str]] = {}
            for nr in node_roles:
                roles_by_node.setdefault(nr.node_id, []).append(nr.role_name)

            for node in db_nodes:
                dep_id = str(uuid.uuid4())[:8]
                roles = roles_by_node.get(node.node_id, [])
                session.add(
                    Deployment(
                        deployment_id=dep_id,
                        node_id=node.node_id,
                        roles=roles,
                        status=DeploymentStatus.IN_PROGRESS.value,
                        started_at=datetime.now(timezone.utc),
                        triggered_by="setup-wizard",
                        extra_data={"source": "setup_wizard"},
                    )
                )
                node_to_deployment[node.node_id] = dep_id

            await session.commit()
            logger.info(
                "Created %d wizard deployment records: %s",
                len(node_to_deployment),
                list(node_to_deployment.values()),
            )
    except Exception as exc:
        logger.warning("Failed to create wizard deployment records: %s", exc)
    return node_to_deployment


async def _complete_wizard_deployments(
    node_to_deployment: dict[str, str],
    success: bool,
    output: str,
    error: str | None,
    reachable_nodes: list[str] | None,
) -> None:
    """Update Deployment records after wizard provisioning finishes (#3032).

    Nodes that were not reachable keep IN_PROGRESS and are marked failed.
    """
    from sqlalchemy import select

    from models.database import Deployment, DeploymentStatus

    if not node_to_deployment:
        return
    try:
        async with db_service.session() as session:
            for node_id, dep_id in node_to_deployment.items():
                result = await session.execute(select(Deployment).where(Deployment.deployment_id == dep_id))
                dep = result.scalar_one_or_none()
                if not dep:
                    continue
                node_succeeded = success and (reachable_nodes is None or node_id in reachable_nodes)
                dep.status = DeploymentStatus.COMPLETED.value if node_succeeded else DeploymentStatus.FAILED.value
                dep.completed_at = datetime.now(timezone.utc)
                dep.playbook_output = output
                if not node_succeeded:
                    dep.error = error or "Provisioning failed or node unreachable"
            await session.commit()
            logger.info(
                "Updated %d wizard deployment records (success=%s)",
                len(node_to_deployment),
                success,
            )
    except Exception as exc:
        logger.warning("Failed to update wizard deployment records: %s", exc)


async def _run_provisioning_task(
    node_ids: list[str] | None,
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
    node_to_deployment: dict[str, str] = {}
    try:
        temp_inventory_path = await _generate_dynamic_inventory(node_ids)
        if not temp_inventory_path:
            _provision_state["status"] = "failed"
            _provision_state["error"] = "No nodes found for provisioning"
            _provision_state["finished_at"] = time.time()
            _write_provision_log("ERROR: No nodes found for provisioning")
            await ws_manager.send_provision_status("failed", "", 0, error="No nodes found for provisioning")
            await ws_manager.send_provision_log("error", "No nodes found for provisioning")
            return

        _write_provision_log(f"Inventory: {temp_inventory_path}\n" f"{temp_inventory_path.read_text(encoding='utf-8')}")

        # Create Deployment records before running the playbook (#3032)
        node_to_deployment = await _create_wizard_deployments(node_ids)

        # Pre-check SSH reachability before running Ansible (#2897)
        reachability = await _check_node_reachability(temp_inventory_path)
        unreachable = [h for h, ok in reachability.items() if not ok]
        reachable = [h for h, ok in reachability.items() if ok]

        if unreachable:
            raw_inv = yaml.safe_load(temp_inventory_path.read_text(encoding="utf-8"))
            inv_hosts = raw_inv.get("all", {}).get("hosts", {})
            for hostname in unreachable:
                host_vars = inv_hosts.get(hostname, {})
                ip = host_vars.get("ansible_host", hostname) if isinstance(host_vars, dict) else hostname
                msg = f"Node {hostname} ({ip}) is unreachable" " -- skipping (not enrolled?)"
                _write_provision_log(f"WARNING: {msg}")
                await ws_manager.send_provision_log("warning", msg)

        if not reachable:
            _provision_state["status"] = "failed"
            _provision_state["error"] = "All nodes are unreachable" " -- ensure nodes are enrolled before provisioning"
            _provision_state["finished_at"] = time.time()
            _write_provision_log("ERROR: All nodes are unreachable")
            await ws_manager.send_provision_status(
                "failed",
                "",
                0,
                error=("All nodes are unreachable" " -- ensure nodes are enrolled before provisioning"),
            )
            await ws_manager.send_provision_log(
                "error",
                ("All nodes are unreachable" " -- ensure nodes are enrolled before provisioning"),
            )
            await _complete_wizard_deployments(
                node_to_deployment,
                success=False,
                output="",
                error="All nodes are unreachable -- ensure nodes are enrolled before provisioning",
                reachable_nodes=None,
            )
            return

        # Build --limit to include only reachable nodes (#2897)
        reachability_limit: list[str] | None = None
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
                if stage == "heartbeat":
                    log_type = "heartbeat"
                elif stage == "phase":
                    log_type = "phase"
                elif stage.endswith("_complete") or stage == "complete":
                    log_type = "success"
                elif "error" in msg.lower() or "failed" in msg.lower():
                    log_type = "error"
                await ws_manager.send_provision_log(log_type, msg)
                elapsed = time.time() - (_provision_state.get("started_at") or time.time())
                await ws_manager.send_provision_status("running", stage, elapsed)

        # Issue #3079: Pass stored secrets as Ansible extra_vars (#3778)
        extra_vars = await fetch_deploy_secrets()

        result = await executor.execute_playbook(
            playbook_name="playbooks/provision-fleet-roles.yml",
            extra_vars=extra_vars,
            limit=reachability_limit,
            inventory_path=temp_inventory_path,
            progress_callback=log_callback,
        )
        _handle_provision_result(result)

        # Update Deployment records with playbook outcome (#3032)
        await _complete_wizard_deployments(
            node_to_deployment,
            success=bool(result.get("success")),
            output=result.get("output", ""),
            error=(None if result.get("success") else _provision_state.get("error")),
            reachable_nodes=None,
        )

        # Activate roles on provisioned nodes (#2836, #2900)
        # Even with partial failures, roles on reachable nodes were deployed.
        await _activate_provisioned_roles(reachable or node_ids)

        elapsed = time.time() - (_provision_state.get("started_at") or time.time())
        if result.get("success"):
            await ws_manager.send_provision_status("completed", "complete", elapsed)
            await ws_manager.send_provision_log("success", "Fleet provisioning completed successfully")
        else:
            human_error = _provision_state.get("error", "Provisioning failed")
            await ws_manager.send_provision_status("failed", "", elapsed, error=human_error)
            await ws_manager.send_provision_log("error", f"Provisioning failed — {human_error}")
    except Exception as exc:
        _provision_state["status"] = "failed"
        _provision_state["error"] = str(exc)
        _write_provision_log(f"EXCEPTION: {exc}")
        logger.exception("Fleet provisioning error: %s", exc)
        elapsed = time.time() - (_provision_state.get("started_at") or time.time())
        # Sanitize -- Ansible exceptions may contain credentials (#2754)
        await ws_manager.send_provision_status("failed", "", elapsed, error="internal error")
        await ws_manager.send_provision_log("error", "Provisioning error: internal error (see server logs)")
        await _complete_wizard_deployments(
            node_to_deployment,
            success=False,
            output="",
            error="internal error",
            reachable_nodes=None,
        )
    finally:
        _provision_state["finished_at"] = time.time()
        if temp_inventory_path and temp_inventory_path.exists():
            temp_inventory_path.unlink(missing_ok=True)


# -- Endpoints ────────────────────────────────────────────────────────────────


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
    completed_steps = set(completed_steps_raw.split(",")) if completed_steps_raw else set()

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
        elapsed = (_provision_state.get("finished_at") or time.time()) - _provision_state["started_at"]
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

        online_result = await session.execute(select(func.count(Node.id)).where(Node.status == "online"))
        online_nodes = online_result.scalar() or 0

        # Only check roles that are actually assigned to nodes (#2747)
        # Roles not yet assigned via wizard are not "missing"
        assigned_roles = (await session.execute(select(NodeRole.role_name).distinct())).scalars().all()

        # Look up which of the assigned roles are required (#9965).
        # Optional roles (required=False) that are assigned but not yet active
        # should not degrade the fleet health score — report them separately.
        from models.database import Role as RoleModel

        role_required_map: dict[str, bool] = {}
        for role_name in assigned_roles:
            role_row = await session.execute(select(RoleModel).where(RoleModel.name == role_name))
            role_obj = role_row.scalar_one_or_none()
            # Default required=True when the DB row is missing (fail-safe)
            role_required_map[role_name] = role_obj.required if role_obj is not None else True

        missing_required_roles: list[str] = []
        inactive_optional_roles: list[str] = []
        for role_name in assigned_roles:
            active = await session.execute(
                select(func.count(NodeRole.id)).where(
                    NodeRole.role_name == role_name,
                    NodeRole.status == "active",
                )
            )
            if (active.scalar() or 0) == 0:
                if role_required_map.get(role_name, True):
                    missing_required_roles.append(role_name)
                else:
                    inactive_optional_roles.append(role_name)

    health = "healthy"
    if missing_required_roles:
        health = "degraded"
    elif online_nodes < total_nodes:
        health = "degraded"

    return {
        "health": health,
        "total_nodes": total_nodes,
        "online_nodes": online_nodes,
        "missing_required_roles": missing_required_roles,
        # Informational: optional roles assigned but not yet active — not health-degrading
        "inactive_optional_roles": inactive_optional_roles,
        "ready": total_nodes > 0,
    }
