# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Compose fleet node seeding + self-managed heartbeat (#9761, extracted in #9854).

In a single-host docker compose stack each service container is surfaced as a
fleet node, using the SAME Node model + heartbeat path as VM nodes.  This module
owns that logic so main.py stays a lean app entrypoint.

Public API (wired from main.py's lifespan):
    - ``seed_compose_nodes()``     — idempotent node registration at startup
    - ``start_compose_heartbeat()`` — background heartbeat task for self-managed nodes
"""

import asyncio
import logging
import os

from config import settings
from services.database import db_service
from services.reconciler import reconciler_service

logger = logging.getLogger(__name__)


# Nodes the SLM hosts itself and must heartbeat locally (no external agent).
_SELF_MANAGED_NODE_IDS: set[str] = {settings.slm_node_id}


async def _heartbeat_self_managed_nodes() -> None:
    """Drive heartbeats for nodes the SLM hosts itself (no external agent).

    VM nodes stay online because their autobot-slm-agent POSTs
    ``/api/nodes/{id}/heartbeat`` -> ``reconciler_service.update_node_heartbeat``.
    The SLM's own node (and, in compose, the colocated service nodes registered
    in ``_SELF_MANAGED_NODE_IDS``) have no external agent, so ``last_heartbeat``
    never updates and the reconciler flips them OFFLINE after
    ``heartbeat_interval * unhealthy_threshold``. This loop feeds the SAME
    heartbeat path locally so they stay online — uniform with VM nodes, only the
    heartbeat source differs (#9761).
    """
    import psutil

    from services.database import db_service

    while True:
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent
            async with db_service.session() as db:
                for node_id in sorted(_SELF_MANAGED_NODE_IDS):
                    # Only heartbeat reachable nodes; unreachable container nodes
                    # are left to the reconciler's offline path (same as VM nodes).
                    if not await _node_reachable(node_id):
                        continue
                    await reconciler_service.update_node_heartbeat(
                        db, node_id, cpu, mem, disk, agent_version="slm-local"
                    )
        except Exception:
            logger.exception("Self-managed node heartbeat failed (non-fatal)")
        await asyncio.sleep(settings.heartbeat_interval)


# Compose fleet nodes (#9761): in a single-host docker compose stack each service
# container is surfaced as a fleet node, using the SAME Node model + heartbeat path
# as VM nodes. Gated by SLM_COMPOSE_NODES so production (Ansible/VM) fleets are
# unaffected. port=None => liveness can't be TCP-probed, so it's assumed up.
# Every mandatory AutoBot role (all canonical roles except optional vnc/docker) is
# assigned to exactly one node — roles are single-node, so the fleet wizard hides a
# role duplicated across nodes. "running" = the role has a live container here
# (detected_roles -> green); "assigned" = a mandatory role with no container in
# compose, parked on a node so it shows as assigned (yellow) and no node is empty.
# Placement of the container-less roles is by affinity (backend->ai-stack/none here,
# worker->browser, etc.); postgres/celery-beat map to canonical postgres/scheduler
# roles added in #9853.
# ip MUST match the ipv4_address in docker-compose.yml (docker DNS only returns the
# app-tier IP, so the static value is authoritative).
_SLM_MGMT_IP = "172.30.0.16"  # autobot-slm on autobot-mgmt (matches docker-compose.yml)
_COMPOSE_NODE_SPECS: list[dict] = [
    {
        "id": "autobot-backend",
        "running": ["backend"],
        "assigned": ["ai-stack"],
        "ip": "172.30.0.13",
        "port": 8001,
        "protocol": "http",
        "path": "/api/health",
    },
    {
        "id": "autobot-worker",
        "running": ["celery"],
        "assigned": ["browser-service"],
        "ip": "172.30.0.14",
        "port": None,
        "protocol": "tcp",
        "path": None,
    },
    {
        "id": "autobot-celery-beat",
        "running": ["scheduler"],
        "assigned": ["autobot-llm-cpu", "autobot-llm-gpu"],
        "ip": "172.30.0.15",
        "port": None,
        "protocol": "tcp",
        "path": None,
    },
    {
        "id": "autobot-frontend",
        "running": ["frontend"],
        "assigned": ["tts-worker"],
        "ip": "172.30.0.17",
        "port": 80,
        "protocol": "http",
        "path": "/",
    },
    {
        "id": "autobot-postgres",
        "running": ["postgres"],
        "assigned": ["npu-worker"],
        "ip": "172.30.0.11",
        "port": 5432,
        "protocol": "tcp",
        "path": None,
    },
    {
        "id": "autobot-redis",
        "running": ["redis"],
        "assigned": [],
        "ip": "172.30.0.10",
        "port": 6379,
        "protocol": "redis",
        "path": None,
    },
    {
        "id": "autobot-chromadb",
        "running": ["chromadb"],
        "assigned": [],
        "ip": "172.30.0.12",
        "port": 8000,
        "protocol": "http",
        "path": "/api/v2/heartbeat",
    },
]


def _compose_nodes_enabled() -> bool:
    """True when each compose container should be surfaced as a fleet node."""
    return os.getenv("SLM_COMPOSE_NODES", "false").strip().lower() in ("1", "true", "yes")


async def _probe_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def _node_reachable(node_id: str) -> bool:
    """Liveness check for a self-managed node before heartbeating it.

    The SLM manager node is the SLM itself (always up). Compose container nodes
    with a known port are TCP-probed; port-less ones (celery worker/beat) can't be
    probed and are assumed up while the stack runs.
    """
    if node_id == settings.slm_node_id:
        return True
    spec = next((s for s in _COMPOSE_NODE_SPECS if s["id"] == node_id), None)
    if not spec or not spec["port"]:
        return True
    return await _probe_tcp(node_id, spec["port"])


async def _ensure_compose_nodes() -> None:
    """Register each compose service container as a fleet node (#9761).

    Idempotent and gated by SLM_COMPOSE_NODES. Mirrors _ensure_local_node but for
    the sibling containers, so the fleet view lists every service in the stack and
    the self-heartbeat loop keeps them online via the same path VM nodes use.
    """
    if not _compose_nodes_enabled():
        return

    from sqlalchemy import delete, select

    from models.database import Node, NodeRole, NodeStatus, Service, ServiceCategory, ServiceStatus

    node_ids = [spec["id"] for spec in _COMPOSE_NODE_SPECS]
    async with db_service.session() as session:
        # These nodes are fully seeder-managed: drop all their existing role rows
        # up front (any assignment_type) and flush, so the re-add below can't hit
        # the uq_node_role unique constraint or premature-autoflush ordering.
        await session.execute(delete(NodeRole).where(NodeRole.node_id.in_(node_ids)))
        await session.flush()
        for spec in _COMPOSE_NODE_SPECS:
            node_id = spec["id"]
            _SELF_MANAGED_NODE_IDS.add(node_id)
            running = spec["running"]  # has a live container -> detected_roles (green)
            all_roles = running + spec["assigned"]  # + mandatory roles parked here (yellow)
            existing = (await session.execute(select(Node).where(Node.node_id == node_id))).scalar_one_or_none()
            if existing:
                existing.ip_address = spec["ip"]
                existing.roles = all_roles
                existing.detected_roles = running
            else:
                session.add(
                    Node(
                        node_id=node_id,
                        ansible_name=node_id,
                        hostname=node_id,
                        ip_address=spec["ip"],
                        auth_method="none",
                        status=NodeStatus.PENDING.value,
                        roles=all_roles,
                        detected_roles=running,
                    )
                )
                session.add(
                    Service(
                        node_id=node_id,
                        service_name=(running[0] if running else node_id),
                        status=ServiceStatus.UNKNOWN.value,
                        category=ServiceCategory.AUTOBOT.value,
                        port=spec["port"],
                        protocol=spec["protocol"],
                        endpoint_path=spec["path"],
                        is_discoverable=True,
                    )
                )
            for role_name in all_roles:
                session.add(NodeRole(node_id=node_id, role_name=role_name, status="active", assignment_type="auto"))
        await session.commit()
    logger.info("Registered/updated %d compose fleet nodes", len(_COMPOSE_NODE_SPECS))


async def seed_compose_nodes() -> None:
    """Register compose service containers as fleet nodes (lifespan entrypoint)."""
    await _ensure_compose_nodes()


def start_compose_heartbeat() -> "asyncio.Task[None]":
    """Start the self-managed node heartbeat loop as a background task."""
    return asyncio.create_task(_heartbeat_self_managed_nodes())
