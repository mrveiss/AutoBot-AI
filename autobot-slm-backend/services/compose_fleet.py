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
      that no real agent is heartbeating (#19292)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from autobot_shared.chromadb_endpoints import CHROMADB_HEARTBEAT_PATH
from autobot_shared.env_registry import env
from autobot_shared.env_utils import env_int_clamped
from config import settings
from services.database import db_service
from services.node_health_status import SELF_AGENT_VERSION, as_utc, mark_agent_lost
from services.reconciler import reconciler_service

logger = logging.getLogger(__name__)


# Nodes the SLM hosts itself and heartbeats locally WHEN no real agent does.
_SELF_MANAGED_NODE_IDS: set[str] = {settings.slm_node_id}

# #19292: how many of the AGENT's heartbeat intervals its last beat counts as
# "recent" -- the self-heartbeat stands down inside that window. 2 tolerates one
# missed agent beat before the local loop takes over again.
SELF_HEARTBEAT_STANDDOWN_BEATS = env_int_clamped("AUTOBOT_SELF_HEARTBEAT_STANDDOWN_BEATS", 2, min_v=1, max_v=1000)

# The key the agent reports its own heartbeat interval under (slm/agent/heartbeat_payload.py).
AGENT_INTERVAL_KEY = "heartbeat_interval_s"
# A larger report is ignored: an unbounded window would keep the self-heartbeat down after the agent dies.
AGENT_INTERVAL_MAX_S = env_int_clamped("AUTOBOT_SELF_HEARTBEAT_AGENT_INTERVAL_MAX_S", 3600, min_v=1, max_v=86400)


def _agent_heartbeat_window_s(node) -> int:
    """Seconds a real agent's last heartbeat keeps the self-heartbeat stood down.

    Measured in the agent's OWN interval when it reported one, else the
    fleet's configured ``heartbeat_interval``. A bool, non-positive or over-cap report is not one.
    """
    reported = (getattr(node, "extra_data", None) or {}).get(AGENT_INTERVAL_KEY)
    valid = type(reported) is int and 0 < reported <= AGENT_INTERVAL_MAX_S  # type(): True is an int
    interval = reported if valid else settings.heartbeat_interval
    return interval * SELF_HEARTBEAT_STANDDOWN_BEATS


def _last_written_by_real_agent(node) -> bool:
    """True when the row's latest heartbeat came from a real slm-agent, not this loop."""
    return node is not None and getattr(node, "agent_version", None) not in (None, SELF_AGENT_VERSION)


def real_agent_heartbeating(node, now: datetime) -> bool:
    """True when a real slm-agent (not this loop) heartbeated ``node`` recently."""
    if not _last_written_by_real_agent(node):
        return False
    beat = as_utc(getattr(node, "last_heartbeat", None))
    return beat is not None and now - beat < timedelta(seconds=_agent_heartbeat_window_s(node))


async def _load_node(db, node_id: str):
    """The node row by id, or None."""
    from sqlalchemy import select

    from models.database import Node

    return (await db.execute(select(Node).where(Node.node_id == node_id))).scalar_one_or_none()


async def _heartbeat_one_self_managed(db, node_id: str, metrics: tuple, now: datetime) -> None:
    """Self-heartbeat one node unless a real agent owns it (#19292).

    The first self-beat after a real agent goes silent records the loss
    (``mark_agent_lost``): the heartbeat path then holds the node DEGRADED for
    ``no_heartbeat`` -- a HEALTH_CHECK event -- until a real agent beats again.
    """
    node = await _load_node(db, node_id)
    if real_agent_heartbeating(node, now):
        return  # one heartbeat source per node: a live agent's samples are the truth
    if _last_written_by_real_agent(node):
        logger.warning("Real slm-agent on %s went silent; self-heartbeat resumes and records no_heartbeat", node_id)
        mark_agent_lost(node)
    await reconciler_service.update_node_heartbeat(db, node_id, *metrics, agent_version=SELF_AGENT_VERSION)


async def _heartbeat_self_managed_once(db, metrics: tuple) -> None:
    """One pass of the self-heartbeat over every self-managed node."""
    now = datetime.now(timezone.utc)
    for node_id in sorted(_SELF_MANAGED_NODE_IDS):
        # Unreachable container nodes are left to the reconciler's offline path.
        if await _node_reachable(node_id):
            await _heartbeat_one_self_managed(db, node_id, metrics, now)


class CpuSampler:
    """Host CPU busy-percent since this sampler's previous read, from ``cpu_times`` deltas.

    Owned by the self-heartbeat so it shares no baseline with
    ``psutil.cpu_percent(interval=None)`` callers elsewhere in this process,
    which would otherwise reset each other's window (#19292 review).
    """

    def __init__(self, psutil_module) -> None:
        self._psutil = psutil_module
        self._last = psutil_module.cpu_times()

    @staticmethod
    def _total(times) -> float:
        """All CPU time once: Linux already counts guest/guest_nice inside user/nice (as cpu_percent does)."""
        return sum(times) - getattr(times, "guest", 0.0) - getattr(times, "guest_nice", 0.0)

    def sample(self) -> float:
        now = self._psutil.cpu_times()
        idle = (now.idle + getattr(now, "iowait", 0.0)) - (self._last.idle + getattr(self._last, "iowait", 0.0))
        total = self._total(now) - self._total(self._last)
        self._last = now
        if total <= 0:
            return 0.0
        return round(100.0 * max(0.0, min(1.0, 1.0 - idle / total)), 1)


async def _heartbeat_self_managed_nodes() -> None:
    """Drive heartbeats for self-managed nodes that no real agent is heartbeating.

    VM nodes stay online because their slm-agent POSTs
    ``/api/nodes/{id}/heartbeat`` -> ``reconciler_service.update_node_heartbeat``.
    The SLM's own node and, in compose, the colocated service nodes in
    ``_SELF_MANAGED_NODE_IDS`` may have no agent; then ``last_heartbeat`` never
    updates and the reconciler flips them OFFLINE. This loop feeds the SAME
    path locally for them (#9761). A manager host can ALSO run a real
    slm-agent; two writers then alternated their own samples and each
    recomputed the status (#19292), so this loop stands down for any node a
    real agent heartbeated within ``_agent_heartbeat_window_s`` and resumes
    when that agent goes silent.
    """
    import psutil

    cpu = CpuSampler(psutil)
    while True:
        try:
            metrics = (cpu.sample(), psutil.virtual_memory().percent, psutil.disk_usage("/").percent)
            async with db_service.session() as db:
                await _heartbeat_self_managed_once(db, metrics)
        except Exception:
            logger.exception("Self-managed node heartbeat failed (non-fatal)")
        await asyncio.sleep(settings.heartbeat_interval)


# Compose fleet nodes (#9761): in a single-host docker compose stack each service
# container is surfaced as a fleet node, using the SAME Node model + heartbeat path
# as VM nodes. Gated by settings.compose_nodes_enabled (#19323): on in a compose stack,
# off on production (Ansible/VM) fleets. port=None => liveness can't be TCP-probed, so it's assumed up.
# Every mandatory AutoBot role (all canonical roles except optional vnc/docker) is
# assigned to exactly one node — roles are single-node, so the fleet wizard hides a
# role duplicated across nodes. "running" = the role has a live container here
# (detected_roles -> green); "assigned" = a mandatory role with no container in
# compose, parked on a node so it shows as assigned (yellow) and no node is empty.
# Placement of the container-less roles is by affinity (backend->ai-stack/none here,
# worker->browser, etc.); postgres/celery-beat map to canonical postgres/scheduler
# roles added in #9853.
# Addresses on autobot-mgmt are AUTOBOT_DOCKER_MGMT_PREFIX (first three octets, picked
# per host by docker/generate-secrets.sh, #16833) + "host", which MUST match that
# service's ipv4_address host number in docker-compose.yml (docker DNS only returns
# the app-tier IP, so the compose address is authoritative).
_SLM_MGMT_HOST = 16  # autobot-slm


def mgmt_ip(host: int) -> str:
    """The autobot-mgmt address of compose host number `host` (#16833)."""
    prefix = env("AUTOBOT_DOCKER_MGMT_PREFIX").strip()
    if not prefix:
        raise RuntimeError("AUTOBOT_DOCKER_MGMT_PREFIX is unset: run docker/generate-secrets.sh (#16833)")
    return f"{prefix}.{host}"


def slm_mgmt_ip() -> str:
    """The SLM manager's own autobot-mgmt address (#9761, #16833)."""
    return mgmt_ip(_SLM_MGMT_HOST)


_COMPOSE_NODE_SPECS: list[dict] = [
    {
        "id": "autobot-backend",
        "running": ["backend"],
        "assigned": ["ai-stack"],
        "host": 13,
        "port": 8001,
        "protocol": "http",
        "path": "/api/health",
    },
    {
        "id": "autobot-worker",
        "running": ["celery"],
        "assigned": ["browser-service"],
        "host": 14,
        "port": None,
        "protocol": "tcp",
        "path": None,
    },
    {
        "id": "autobot-celery-beat",
        "running": ["scheduler"],
        "assigned": ["autobot-llm-cpu", "autobot-llm-gpu"],
        "host": 15,
        "port": None,
        "protocol": "tcp",
        "path": None,
    },
    {
        "id": "autobot-frontend",
        "running": ["frontend"],
        "assigned": ["tts-worker"],
        "host": 17,
        "port": 80,
        "protocol": "http",
        "path": "/",
    },
    {
        "id": "autobot-postgres",
        "running": ["postgres"],
        "assigned": ["npu-worker"],
        "host": 11,
        "port": 5432,
        "protocol": "tcp",
        "path": None,
    },
    {
        "id": "autobot-redis",
        "running": ["redis"],
        "assigned": [],
        "host": 10,
        "port": 6379,
        "protocol": "redis",
        "path": None,
    },
    {
        "id": "autobot-chromadb",
        "running": ["chromadb"],
        "assigned": [],
        "host": 12,
        "port": 8000,
        "protocol": "http",
        "path": CHROMADB_HEARTBEAT_PATH,  # #19413
    },
]


def _compose_nodes_enabled() -> bool:
    """True when each compose container should be surfaced as a fleet node (default: config, #19323)."""
    return settings.compose_nodes_enabled


def is_manager_node(node_id: str) -> bool:
    """True when node_id is the SLM's own (manager/self) node (#11963).

    The manager node is heartbeated by its real slm-agent when one runs, and
    otherwise by ``_heartbeat_self_managed_nodes`` (#19292) — either way from
    real-time metrics of a live process — so the reconciler's ICMP-ping reachability fallback in
    ``_check_node_health`` (designed for externally-agent-heartbeating VM
    nodes) must never override it. Ping is an unreliable/redundant signal for
    a node that is, by definition, up while it is serving the health check.
    """
    return node_id == settings.slm_node_id


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

    from models.database import Node, NodeRole, NodeStatus, Service, ServiceCategory, SystemdState

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
                existing.ip_address = mgmt_ip(spec["host"])
                existing.roles = all_roles
                existing.detected_roles = running
            else:
                session.add(
                    Node(
                        node_id=node_id,
                        ansible_name=node_id,
                        hostname=node_id,
                        ip_address=mgmt_ip(spec["host"]),
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
                        status=SystemdState.UNKNOWN.value,
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
