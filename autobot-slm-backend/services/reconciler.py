# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Reconciler Service

Monitors node health and manages role state reconciliation.
Implements conservative remediation: auto-restart services, but require
human approval for re-enrollment.
"""

import asyncio
import logging
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.http_client import get_http_client
from autobot_shared.service_discovery import SERVICE_DISCOVERY_TTL_S
from autobot_shared.time_utils import parse_utc_iso, utc_timestamp
from config import settings
from models.database import (
    Deployment,
    DeploymentStatus,
    EventSeverity,
    EventType,
    Node,
    NodeEvent,
    NodeStatus,
    Service,
    ServiceCategory,
    ServiceStatus,
    Setting,
)
from services.service_categorizer import categorize_service
from services.service_extra_data import engine_degraded_fields, is_managed_autobot_service

logger = logging.getLogger(__name__)

# Role to systemd service mapping
ROLE_SERVICE_MAP: Dict[str, list] = {
    "slm-agent": ["slm-agent"],
    "redis": ["redis-server", "redis"],
    "backend": ["autobot-backend", "autobot"],
    "frontend": ["autobot-frontend"],
    "npu-worker": ["autobot-npu-worker"],
    "browser-automation": ["playwright-server", "browser-automation"],
    "monitoring": ["prometheus", "grafana-server", "node_exporter"],
}

# Maximum remediation attempts before requiring human intervention
MAX_REMEDIATION_ATTEMPTS = 3
# How often to poll manifest health endpoints (seconds)
MANIFEST_HEALTH_INTERVAL = 60
# How often to check TLS cert expiry (seconds — daily)
CERT_EXPIRY_CHECK_INTERVAL = 86_400
# Cooldown between remediation attempts (seconds)
REMEDIATION_COOLDOWN = 300  # 5 minutes

# #14344: how long to wait for a heartbeat after restarting the agent before
# calling the remediation a failure. Remediation exists to restore the
# heartbeat, so the heartbeat is what "success" has to mean — the restart
# exiting 0 only says the command ran. Env-backed rather than hardcoded: the
# right window depends on the agent's own heartbeat interval on that fleet.
# min_v=1, not 0: a 0 window makes the poll body unreachable, so every
# remediation would report failure and march healthy nodes to `exhausted`.
REMEDIATION_HEARTBEAT_WAIT_S = env_int_clamped("AUTOBOT_REMEDIATION_HEARTBEAT_WAIT_S", 90, min_v=1)
# Clamped, not bare: env_int accepts 0 and negatives, and a 0 here turns the
# verification poll into a tight open/close-session loop for the whole window.
REMEDIATION_HEARTBEAT_POLL_S = env_int_clamped("AUTOBOT_REMEDIATION_HEARTBEAT_POLL_S", 5, min_v=1)
# #14465 review: this does NOT read any heartbeat/streak signal, which closes
# the specific way the prior two designs were fakeable by a flap -- but it is
# not, on its own, a general fix for escalation reachability. The dominant
# gate for a node whose agent keeps heartbeating is `_heartbeat_returned`'s
# own success semantics a few lines below in `_remediate_node`: ANY beat that
# lands within `REMEDIATION_HEARTBEAT_WAIT_S` of a restart resets `count` to 0
# through that path, every attempt, regardless of this mechanism. This is
# genuinely inert for that shape -- it only matters once `_heartbeat_returned`
# has ALREADY failed repeatedly (an ansible restart that cannot run, or one
# that runs but never gets a heartbeat accepted), where it stops those
# failures from being silently forgiven by nothing at all. Whether/how to
# widen "recovered" beyond that is a posted, unresolved decision on #14465 --
# out of scope here.
#
# How long a non-exhausted tracker may sit with no NEW attempt before its
# count is forgiven, in the cases above where it does apply. `last_attempt`
# only advances when `_remediate_node` actually runs an attempt, which
# happens every `REMEDIATION_COOLDOWN` for as long as the node keeps being
# selected DEGRADED -- so it can only go this stale if the reconciler
# genuinely stopped re-selecting the node for the whole window.
#
# This value alone is NOT what `_forgive_if_expired` enforces -- see
# `_effective_tracker_expiry_s()`. It must be strictly greater than
# REMEDIATION_COOLDOWN plus a reconcile-tick margin, not merely >=: at exactly
# REMEDIATION_COOLDOWN, the cooldown check and the forgive check flip at the
# identical elapsed time, and forgive runs first -- so a tracker is forgiven
# back to 0 in the same instant an attempt becomes due, every time, and count
# can never exceed 1. That reconcile-tick margin depends on `settings.
# reconcile_interval`, a per-process pydantic setting -- deliberately NOT read
# here at import time. A review-caught regression: one test module stubs
# `config.settings` as a bare `SimpleNamespace` lacking `reconcile_interval`,
# and reading it here raised `AttributeError` at module-exec time, which
# aborted collection for that entire file, not just this constant. `min_v=1`
# is a cheap sanity floor only; the real, reconcile-interval-aware floor is
# computed fresh on every call, from the LIVE `settings` object, exactly where
# it is used.
REMEDIATION_TRACKER_EXPIRY_S = env_int_clamped("AUTOBOT_REMEDIATION_TRACKER_EXPIRY_S", 1800, min_v=1)

# #14465 review: how often `_handle_max_attempts_refusal` re-broadcasts "still
# exhausted" for a node parked at MAX_REMEDIATION_ATTEMPTS. Once exhausted,
# `last_attempt` freezes, so this branch runs on every reconcile pass for as
# long as the node stays selected DEGRADED -- unthrottled, that is once per
# `reconcile_interval` forever (~1400/day at the 60s default). An hour is
# frequent enough that a human watching the UI sees the node is still stuck
# without needing to have caught the one original event, and infrequent
# enough not to be noise.
MAX_ATTEMPTS_REFUSAL_BROADCAST_INTERVAL_S = env_int_clamped(
    "AUTOBOT_MAX_ATTEMPTS_REFUSAL_BROADCAST_INTERVAL_S", 3600, min_v=1
)

# #14465 review, round 7: one-shot latches for _effective_tracker_expiry_s's
# two "log once, not every call" warnings -- that function runs on every
# _forgive_if_expired, up to once per reconcile pass per degraded node.
_expiry_floor_override_logged = False
_reconcile_interval_type_warning_logged = False


def _effective_tracker_expiry_s() -> int:
    """The expiry window actually enforced by `_forgive_if_expired` (#14465 review).

    Reads `settings.reconcile_interval` fresh on every call rather than once
    at import time -- see `REMEDIATION_TRACKER_EXPIRY_S` for why. `getattr`
    with a default cannot raise for a genuinely missing attribute, unlike a
    `try/except` around a narrower guess at which exception a stub might
    raise; the `isinstance` check below additionally covers a stub where the
    attribute IS present but is not a real int (e.g. an auto-vivified
    `MagicMock` child under the root conftest's `config.settings = MagicMock()`
    stub) -- `int + MagicMock` does not raise either, it silently produces
    another `MagicMock`, which `max()` against would raise `TypeError` one
    call later instead of never.

    The margin is NOT `reconcile_interval` alone (review, round 6):
    `_attempt_remediation` processes every currently-degraded node SERIALLY
    within one pass, and `_heartbeat_returned` blocks that pass for up to
    `REMEDIATION_HEARTBEAT_WAIT_S` for EACH node that gets an actual attempt.
    With more than one such node in the same pass, the real gap between two
    `_remediate_node` calls for a GIVEN node can run well beyond `reconcile_
    interval` -- a margin of `reconcile_interval` alone was measured
    defeated for realistic real-world pass durations. `REMEDIATION_
    HEARTBEAT_WAIT_S` upper-bounds the dominant source of that variance for
    ONE node; this does NOT bound the case of many nodes degraded
    simultaneously, which needs either a known fleet-size ceiling or
    restructuring `_attempt_remediation` to process nodes concurrently (each
    with its own DB session -- sharing one `AsyncSession` across concurrent
    coroutines is unsafe, so that is a real change, not a one-line fix).
    Tracked as #14515. Nor does it bound `execute_playbook`'s own runtime,
    which has no wall-clock timeout at all -- tracked separately as #14524,
    since that is a single-node gap, not a many-nodes one.

    Two conditions are logged once (not on every call -- this runs on every
    `_forgive_if_expired`, up to once per reconcile pass per degraded node)
    rather than silently: an operator's `AUTOBOT_REMEDIATION_TRACKER_
    EXPIRY_S` being below the enforced floor (round 7 -- setting 60 expecting
    a short window silently gets 391+ instead, which is ALSO shorter than
    the 1800s default, so the operator ends up less protected than doing
    nothing while believing they configured something specific), and
    `settings.reconcile_interval` being present but not a real int (an
    auto-vivified `MagicMock` child, dormant today but would otherwise
    silently collapse a legitimately large configured interval down to the
    60s fallback with no warning).
    """
    global _expiry_floor_override_logged, _reconcile_interval_type_warning_logged

    reconcile_interval = getattr(settings, "reconcile_interval", 60)
    if not isinstance(reconcile_interval, int):
        if not _reconcile_interval_type_warning_logged:
            logger.warning(
                "settings.reconcile_interval is %r, not an int -- falling back to 60s for the "
                "remediation-tracker expiry floor margin",
                reconcile_interval,
            )
            _reconcile_interval_type_warning_logged = True
        reconcile_interval = 60

    margin = max(reconcile_interval, REMEDIATION_HEARTBEAT_WAIT_S)
    floor = REMEDIATION_COOLDOWN + margin + 1
    effective = max(REMEDIATION_TRACKER_EXPIRY_S, floor)

    if effective != REMEDIATION_TRACKER_EXPIRY_S and not _expiry_floor_override_logged:
        logger.warning(
            "AUTOBOT_REMEDIATION_TRACKER_EXPIRY_S=%ds is below the enforced floor -- using %ds instead "
            "(REMEDIATION_COOLDOWN=%ds + margin=%ds + 1)",
            REMEDIATION_TRACKER_EXPIRY_S,
            effective,
            REMEDIATION_COOLDOWN,
            margin,
        )
        _expiry_floor_override_logged = True

    return effective


# Default rollback window (seconds) - deployments older than this won't be auto-rolled back
DEFAULT_ROLLBACK_WINDOW = 600  # 10 minutes
# Service remediation cooldown (shorter than node remediation)
SERVICE_REMEDIATION_COOLDOWN = 120  # 2 minutes
# Maximum service restart attempts before requiring human intervention
MAX_SERVICE_RESTART_ATTEMPTS = 3

# #14465 review: how long a service is reported as CHURNING after its last
# observed `n_restarts` increase. Must be comfortably larger than health_
# collector's own `discover_all_services()` cache TTL
# (`autobot_shared.service_discovery.SERVICE_DISCOVERY_TTL_S`) -- against a
# 30s heartbeat, 9 of every 10 beats otherwise carry a byte-identical cached
# snapshot, so a bare "did it change since the immediately preceding
# heartbeat" pulse only fires on the ~1 beat in 10 where the cache actually
# refreshed (measured: 1 of 20 degraded across continuous churn, vs 20 of 20
# on the absolute threshold this replaced -- the node flapped ONLINE/DEGRADED
# every 5 minutes instead of staying DEGRADED). A level -- degrade while
# `now - last_increase < window` -- reports whether the node is CURRENTLY
# churning, which is what a status field means, instead of whether THIS
# SPECIFIC sample happened to land on a cache refresh.
#
# min_v is DERIVED from SERVICE_DISCOVERY_TTL_S, not a second hardcoded
# literal: an earlier version of this fix hardcoded `min_v=1`, and measured
# with the TTL at its own default, every window from 1 to 271 seconds
# restored the pulse-flapping regression this replaces -- a bare literal
# gives no warning when the agent-side TTL changes out from under it (raising
# the TTL to 900 would make the unrelated 600s DEFAULT flap too). Twice the
# TTL guarantees the window spans at least one full cache-refresh cycle, so a
# service that is genuinely still churning re-arms the window (a fresh
# increase observed within it) before the earlier arming closes, keeping
# DEGRADED continuous throughout sustained churn. The trade-off this makes
# explicit: a single benign restart (one OOM kill, one dependency flap) now
# degrades the node for the whole window and stands a real chance of
# triggering one ansible restart via remediation, where the absolute
# threshold it replaced made that same trade unboundedly (forever, once
# n_restarts crossed 3) rather than for one bounded window.
RESTART_CHURN_WINDOW_S = env_int_clamped("AUTOBOT_RESTART_CHURN_WINDOW_S", 600, min_v=SERVICE_DISCOVERY_TTL_S * 2 + 1)


def _restart_count_increased(svc_data: dict, previous_extra: dict) -> bool:
    """Did a managed service's `n_restarts` rise since the last heartbeat?

    Helper for `_restart_churn_active`. Compares against the immediately
    preceding heartbeat's stored value, never an absolute threshold --
    `NRestarts` is lifetime-cumulative for as long as a unit keeps failing
    (systemd resets it on the next clean manual start once a unit settles,
    not merely with the passage of time), so a static gate on it can never
    self-heal on its own (see `_calculate_node_status`'s docstring). A
    decrease (e.g. that reset, or a reboot) is deliberately not itself a
    signal here -- only a rise arms the churn window; `_update_existing_
    service` still rewrites the stored baseline to the new, lower value
    either way, so a later rise compares against the post-reset count.
    """
    if not is_managed_autobot_service(svc_data):
        return False
    current = svc_data.get("n_restarts")
    previous = previous_extra.get("n_restarts")
    if current is None or previous is None:
        return False
    return current > previous


def _restart_churn_active(svc_data: dict, previous_extra: dict, now: datetime) -> tuple[bool, str | None]:
    """Is a managed service CURRENTLY churning, and what timestamp to persist for it?

    Helper for `ReconcilerService._update_existing_service` (#14465 review: a
    pulse -- "did it change since the immediately preceding heartbeat" -- is
    the wrong shape for a status field; see `RESTART_CHURN_WINDOW_S`). Tracks
    the timestamp of the last OBSERVED increase and reports "churning" for
    `RESTART_CHURN_WINDOW_S` afterward -- a level.

    First-ever observation (no previous `n_restarts` to compare against, the
    `_create_new_service` path) is honestly `(False, None)`: there is no rate
    information yet on a service just discovered, or a row `_remove_stale_
    services` deleted and the agent re-reported. The next observed increase
    arms the window. Acceptable rather than a regression here specifically
    because the signal is a level: a service that is GENUINELY still
    churning will produce that next increase within one heartbeat interval,
    not eventually -- unlike the absolute threshold this replaced, which had
    no such excuse for missing an already-churning service on first sight.

    Returns `(is_churning_now, last_increase_iso_to_persist)`.
    """
    if not is_managed_autobot_service(svc_data):
        return False, previous_extra.get("n_restarts_increased_at")

    last_increase_iso = previous_extra.get("n_restarts_increased_at")
    if _restart_count_increased(svc_data, previous_extra):
        last_increase_iso = now.isoformat()

    if last_increase_iso is None:
        return False, None

    try:
        last_increase_at = parse_utc_iso(last_increase_iso)
    except (TypeError, ValueError):
        return False, None

    is_churning = (now - last_increase_at).total_seconds() < RESTART_CHURN_WINDOW_S
    return is_churning, last_increase_iso


def _service_health_degraded(extra_data: dict | None, restart_churn_active: bool) -> bool:
    """The two current-state service signals `_calculate_node_status` acts on.

    Module-level and pure: `restart_churn_active` is computed elsewhere
    (against the OLD `Service` row this function does not have); this only
    combines it with the current-heartbeat status scan.
    """
    if restart_churn_active:
        return True
    if not extra_data:
        return False
    for svc in extra_data.get("discovered_services", []):
        if not is_managed_autobot_service(svc):
            continue
        if svc.get("status") in ("crash-loop", "failed"):
            return True
    return False


class ReconcilerService:
    """Background service for health monitoring and reconciliation.

    Implements conservative remediation:
    - Auto-restart: Automatically restart failed services via SSH
    - Human required: Re-enrollment requires manual approval
    """

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        # Default: 3 missed heartbeats = unhealthy
        self._heartbeat_timeout = settings.heartbeat_interval * settings.unhealthy_threshold
        # Track remediation attempts per node: {node_id: {"count": int, "last_attempt": datetime}}
        self._remediation_tracker: Dict[str, Dict] = {}
        # Track service restart attempts: {(node_id, svc_name): {"count": int, "last_attempt": dt}}
        self._service_remediation_tracker: Dict[tuple, Dict] = {}
        # Timestamps for rate-limited background tasks (#926 Phase 3)
        self._last_manifest_health_check: float = 0.0
        self._last_cert_expiry_check: float = 0.0

    async def start(self) -> None:
        """Start the reconciler background task."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Reconciler service started")

    async def stop(self) -> None:
        """Stop the reconciler background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Reconciler service stopped")

    async def _run_loop(self) -> None:
        """Main reconciliation loop."""
        import time

        while self._running:
            try:
                await self._check_node_health()
                await self._attempt_remediation()
                await self._remediate_failed_services()
                await self._check_auto_rollback()
                await self._reconcile_roles()

                # Rate-limited manifest tasks (Issue #926 Phase 3)
                now = time.monotonic()
                if now - self._last_manifest_health_check >= MANIFEST_HEALTH_INTERVAL:
                    await self._poll_manifest_health()
                    self._last_manifest_health_check = now
                if now - self._last_cert_expiry_check >= CERT_EXPIRY_CHECK_INTERVAL:
                    await self._check_cert_expiry()
                    self._last_cert_expiry_check = now
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Reconciler error: %s", e)

            await asyncio.sleep(settings.reconcile_interval)

    async def _handle_degraded_node(self, db: AsyncSession, node: Node, old_status: str) -> None:
        """Mark node as degraded, create event, and broadcast status.

        Helper for _check_node_health (Issue #665).
        """
        node.status = NodeStatus.DEGRADED.value
        event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=node.node_id,
            event_type=EventType.HEALTH_CHECK.value,
            severity=EventSeverity.WARNING.value,
            message=f"Node {node.hostname} reachable but agent not responding",
            details={"old_status": old_status, "reason": "no_heartbeat"},
        )
        db.add(event)
        logger.info(
            "Node %s (%s) reachable but no heartbeat - marking degraded",
            node.node_id,
            node.ip_address,
        )
        await self._broadcast_node_status(node.node_id, NodeStatus.DEGRADED.value, node.hostname)

    async def _handle_offline_node(self, db: AsyncSession, node: Node, old_status: str) -> None:
        """Mark node as offline, create event, and broadcast status.

        Helper for _check_node_health (Issue #665).
        """
        node.status = NodeStatus.OFFLINE.value
        event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=node.node_id,
            event_type=EventType.HEALTH_CHECK.value,
            severity=EventSeverity.ERROR.value,
            message=f"Node {node.hostname} is unreachable",
            details={"old_status": old_status, "reason": "unreachable"},
        )
        db.add(event)
        logger.info(
            "Node %s (%s) unreachable - marking offline",
            node.node_id,
            node.ip_address,
        )
        await self._broadcast_node_status(node.node_id, NodeStatus.OFFLINE.value, node.hostname)

    async def _check_node_health(self) -> None:
        """Check node health based on heartbeats and network reachability.

        Issue #11963: the manager/self node is excluded from the ping-based
        demotion below — it is heartbeated locally (compose_fleet.py) from
        real-time metrics of this very process, so ICMP reachability (which
        can be blocked/unreliable and races the self-heartbeat loop) must
        never mark it degraded/offline.
        """
        from sqlalchemy import or_

        from services.compose_fleet import is_manager_node
        from services.database import db_service

        async with db_service.session() as db:
            timeout_setting = await db.execute(select(Setting).where(Setting.key == "heartbeat_timeout"))
            setting = timeout_setting.scalar_one_or_none()
            if setting and setting.value:
                self._heartbeat_timeout = int(setting.value)

            cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._heartbeat_timeout)

            # Get nodes with stale or missing heartbeats
            result = await db.execute(
                select(Node)
                .where(
                    Node.status.in_(
                        [
                            NodeStatus.ONLINE.value,
                            NodeStatus.DEGRADED.value,
                            NodeStatus.OFFLINE.value,
                        ]
                    )
                )
                .where(or_(Node.last_heartbeat < cutoff, Node.last_heartbeat.is_(None)))
            )
            stale_nodes = result.scalars().all()

            for node in stale_nodes:
                if is_manager_node(node.node_id):
                    continue

                is_reachable = await self._ping_host(node.ip_address)
                old_status = node.status

                if is_reachable:
                    if node.status != NodeStatus.DEGRADED.value:
                        await self._handle_degraded_node(db, node, old_status)
                else:
                    if node.status != NodeStatus.OFFLINE.value:
                        await self._handle_offline_node(db, node, old_status)

            await db.commit()

    async def _ping_host(self, ip_address: str, timeout: int = 2) -> bool:
        """Check if a host responds to ping."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping",
                "-c",
                "1",
                "-W",
                str(timeout),
                ip_address,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception as e:
            logger.debug("Ping failed for %s: %s", ip_address, e)
            return False

    async def _broadcast_node_status(self, node_id: str, status: str, hostname: str = None) -> None:
        """Broadcast node status change via WebSocket."""
        try:
            from api.websocket import ws_manager

            await ws_manager.send_node_status(node_id, status, hostname)
        except Exception as e:
            logger.debug("Failed to broadcast node status: %s", e)

    async def _broadcast_remediation_event(
        self, node_id: str, event_type: str, success: bool = None, message: str = None
    ) -> None:
        """Broadcast remediation event via WebSocket."""
        try:
            from api.websocket import ws_manager

            await ws_manager.send_remediation_event(node_id, event_type, success, message)
        except Exception as e:
            logger.debug("Failed to broadcast remediation event: %s", e)

    async def _attempt_remediation(self) -> None:
        """Attempt to remediate degraded nodes by restarting services.

        Conservative approach:
        - Auto-restart: Restart failed services via SSH
        - Human required: Re-enrollment requires manual approval
        - Rate limited: Max 3 attempts per node, 5 min cooldown
        - Respects maintenance windows: Skip nodes in maintenance
        """
        from services.database import db_service

        async with db_service.session() as db:
            # Check if auto-remediation is enabled
            auto_remediate = await db.execute(select(Setting).where(Setting.key == "auto_remediate"))
            setting = auto_remediate.scalar_one_or_none()

            if not setting or setting.value != "true":
                return

            # Get degraded nodes (reachable but agent not responding)
            result = await db.execute(select(Node).where(Node.status == NodeStatus.DEGRADED.value))
            degraded_nodes = result.scalars().all()

            for node in degraded_nodes:
                # Check if node is in maintenance window with remediation suppression
                if await self._is_remediation_suppressed(db, node.node_id):
                    logger.debug(
                        "Skipping remediation for node %s - in maintenance window",
                        node.node_id,
                    )
                    continue

                await self._remediate_node(db, node)

    def _forgive_if_expired(self, node_id: str, tracker: dict, now: datetime) -> dict:
        """Reset a stale, non-exhausted tracker's count to zero, once genuinely idle (#14465).

        Helper for _check_remediation_limits; see REMEDIATION_TRACKER_EXPIRY_S
        and `_effective_tracker_expiry_s` for what this does and does not fix
        -- it is scoped to time since the last ATTEMPT, not any heartbeat-side
        signal, but it is not the gate that decides whether count accumulates
        in the first place for a node whose agent keeps heartbeating;
        `_heartbeat_returned`, below, is.

        `exhausted` trackers are deliberately excluded: that flag means human
        intervention was already required, and forgiving it on a timer alone
        would be a silent, unbounded auto-retry -- a scope change this issue
        does not ask for, not a bug fix.
        """
        if tracker.get("exhausted") or not tracker.get("count"):
            return tracker
        last_attempt = tracker.get("last_attempt")
        effective_expiry_s = _effective_tracker_expiry_s()
        if last_attempt is None or (now - last_attempt).total_seconds() < effective_expiry_s:
            return tracker

        forgiven = {"count": 0, "last_attempt": last_attempt}
        self._remediation_tracker[node_id] = forgiven
        logger.info(
            "Node %s remediation history expired after %ds with no further attempts - forgiving",
            node_id,
            effective_expiry_s,
        )
        return forgiven

    def _check_remediation_limits(self, node_id: str, now: datetime) -> tuple[bool, str | None, dict]:
        """Check if remediation can proceed based on cooldown and attempt limits.

        Helper for _remediate_node (Issue #665).

        Returns:
            (can_proceed, skip_reason, tracker) tuple where:
            - can_proceed: True if remediation should proceed
            - skip_reason: "cooldown" or "max_attempts" if skipped, None otherwise
            - tracker: The remediation tracker dict for this node
        """
        tracker = self._remediation_tracker.get(node_id, {"count": 0, "last_attempt": None})
        tracker = self._forgive_if_expired(node_id, tracker, now)

        # Check cooldown
        if tracker["last_attempt"]:
            elapsed = (now - tracker["last_attempt"]).total_seconds()
            if elapsed < REMEDIATION_COOLDOWN:
                logger.debug(
                    "Node %s in remediation cooldown (%d seconds remaining)",
                    node_id,
                    REMEDIATION_COOLDOWN - elapsed,
                )
                return False, "cooldown", tracker

        # Check attempt limit
        if tracker["count"] >= MAX_REMEDIATION_ATTEMPTS:
            logger.warning(
                "Node %s exceeded max remediation attempts (%d). Human intervention required.",
                node_id,
                MAX_REMEDIATION_ATTEMPTS,
            )
            return False, "max_attempts", tracker

        return True, None, tracker

    async def _create_max_attempts_event(self, db: AsyncSession, node: Node, tracker: dict) -> None:
        """Create event when max remediation attempts exceeded.

        Helper for _remediate_node (Issue #665).
        """
        event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=node.node_id,
            event_type=EventType.REMEDIATION_COMPLETED.value,
            severity=EventSeverity.WARNING.value,
            message=(
                f"Node {node.hostname} requires human intervention after "
                f"{MAX_REMEDIATION_ATTEMPTS} failed remediation attempts"
            ),
            details={
                "attempts": tracker["count"],
                "action_required": "manual_review",
            },
        )
        db.add(event)
        await db.commit()

    async def _handle_max_attempts_refusal(self, db: AsyncSession, node: Node, tracker: dict) -> None:
        """React to a DEGRADED node being refused a remediation attempt at the limit.

        Helper for _remediate_node (#14465 review). Base's recovery reset
        dropped `exhausted` whenever it fired, so a recovered node became
        remediable again -- rarely reachable, per this issue's own root-cause
        finding, but a real path. `_forgive_if_expired` deliberately excludes
        `exhausted` trackers (see its docstring), so with no other path back
        this refusal now repeats silently: `_create_max_attempts_event` fired
        once and every later pass was only a `logger.warning` inside
        `_check_remediation_limits` -- no event, no broadcast, no UI signal
        that the node is still stuck. An automatic un-exhaust path is a
        design decision, tracked on #14465, not built here.

        `exhausted` is set and stored BEFORE `_create_max_attempts_event`'s
        `db.commit()` is even attempted, not after: `last_attempt` is now
        frozen (nothing advances it once exhausted), so this branch runs on
        EVERY future reconcile pass for as long as the node stays selected
        DEGRADED. If the flag were only set after a successful commit, a
        commit failure would leave it unset and every subsequent pass would
        retry the same DB write -- unbounded for a sustained outage. Setting
        it first means at worst one informational event is lost to a
        transient failure, never a retry loop.

        The follow-up visibility fix is throttled
        (`MAX_ATTEMPTS_REFUSAL_BROADCAST_INTERVAL_S`) and does two things,
        not one (#14465 review round 7 -- a live-only broadcast reaches
        nobody who is not watching at that exact moment, and was found
        emitted onto a wire nothing renders):

        - Persists a throttled `NodeEvent` (`_create_still_exhausted_event`)
          so the DB-backed timeline shows the node is STILL stuck, not just
          the one original exhaustion event -- reusing the same generic,
          already-rendered `EventType.REMEDIATION_COMPLETED` shape rather
          than inventing a new one, so this needs no new frontend work.
        - Broadcasts over the websocket for anyone watching live, with
          `event_type="still_exhausted"` -- deliberately NOT `"completed"`:
          `FleetOverview.vue`'s `onRemediationEvent` handler calls
          `fleetStore.refreshNode(nodeId)`, a real API request, for exactly
          that `event_type`. Broadcasting `"completed"` on every refusal
          would have turned "make the lockout visible" into a refresh storm
          once per reconcile tick, forever, for every exhausted node.
        """
        if not tracker.get("exhausted"):
            tracker["exhausted"] = True
            self._remediation_tracker[node.node_id] = tracker
            await self._create_max_attempts_event(db, node, tracker)
            return

        now = datetime.now(timezone.utc)
        last_broadcast = tracker.get("last_refusal_broadcast")
        if last_broadcast is not None and (now - last_broadcast).total_seconds() < (
            MAX_ATTEMPTS_REFUSAL_BROADCAST_INTERVAL_S
        ):
            return

        tracker["last_refusal_broadcast"] = now
        self._remediation_tracker[node.node_id] = tracker
        await self._create_still_exhausted_event(db, node, tracker)
        await self._broadcast_remediation_event(
            node.node_id,
            "still_exhausted",
            success=False,
            message=f"Node {node.hostname} remains at max remediation attempts - human intervention required",
        )

    async def _create_still_exhausted_event(self, db: AsyncSession, node: Node, tracker: dict) -> None:
        """Persist a throttled record of an ONGOING refusal, distinct from the first (#14465).

        Helper for _handle_max_attempts_refusal. Reusing `_create_max_attempts_
        event`'s exact message would misrepresent every later refusal as a
        fresh exhaustion; this is the same `event_type`/`severity` (so the
        existing generic events timeline, which renders by message and
        severity rather than a fixed per-event_type template, shows it with
        no new frontend work) with wording that says "still", and the
        attempt count is unchanged from the first event by design -- it is
        frozen along with `last_attempt` once exhausted.
        """
        event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=node.node_id,
            event_type=EventType.REMEDIATION_COMPLETED.value,
            severity=EventSeverity.WARNING.value,
            message=(
                f"Node {node.hostname} still requires human intervention "
                f"({tracker['count']} failed remediation attempts)"
            ),
            details={
                "attempts": tracker["count"],
                "action_required": "manual_review",
                "still_exhausted": True,
            },
        )
        db.add(event)
        await db.commit()

    async def _record_remediation_result(
        self, db: AsyncSession, node: Node, success: bool, tracker: dict, restarted: bool = True
    ) -> None:
        """Create completion event and broadcast for remediation result.

        Helper for _remediate_node (Issue #665).

        #14344: failure now has two distinct causes and they call for different
        responses. ``restarted=False`` is an unreachable or broken node. A
        successful restart with no heartbeat is an agent that runs but is
        rejected -- the #14350 signature -- and telling an operator the restart
        "failed" would send them to look at the wrong layer entirely.
        """
        node_id = node.node_id

        if success:
            event = NodeEvent(
                event_id=str(uuid.uuid4())[:16],
                node_id=node_id,
                event_type=EventType.REMEDIATION_COMPLETED.value,
                severity=EventSeverity.INFO.value,
                message=f"SLM agent on {node.hostname} restarted and resumed heartbeating",
                details={"action": "restart_agent", "success": True, "verified_by": "heartbeat"},
            )
            logger.info("Remediation verified for node %s - heartbeat resumed", node_id)
            await self._broadcast_remediation_event(
                node_id,
                "completed",
                success=True,
                message=f"SLM agent on {node.hostname} restarted and resumed heartbeating",
            )
        else:
            # One message for the event, the log and the UI. Built once so the
            # three cannot drift: the broadcast previously kept saying "failed
            # to restart" after the event learned to distinguish the stages.
            stage = "restart" if not restarted else "heartbeat"
            failure_message = (
                f"Failed to restart SLM agent on {node.hostname}"
                if not restarted
                else f"SLM agent on {node.hostname} restarted but did not resume heartbeating"
            )
            event = NodeEvent(
                event_id=str(uuid.uuid4())[:16],
                node_id=node_id,
                event_type=EventType.REMEDIATION_COMPLETED.value,
                severity=EventSeverity.WARNING.value,
                message=failure_message,
                details={
                    "action": "restart_agent",
                    "success": False,
                    "failed_at": stage,
                    "attempts_remaining": MAX_REMEDIATION_ATTEMPTS - tracker["count"] - 1,
                },
            )
            logger.warning("Remediation failed for node %s at the %s stage", node_id, stage)
            await self._broadcast_remediation_event(
                node_id,
                "completed",
                success=False,
                message=failure_message,
            )

        db.add(event)
        await db.commit()

    async def _remediate_node(self, db: AsyncSession, node: Node) -> bool:
        """Attempt to remediate a single degraded node.

        Returns True if remediation was attempted, False if skipped.
        """
        node_id = node.node_id
        now = datetime.now(timezone.utc)

        # #14344 review: verification makes `exhausted` reachable for the first
        # time -- before this change a restart's exit code always reset the
        # counter, so a node effectively never ran out of attempts. That turns a
        # dormant gap into a live trap: nothing clears the tracker when a node
        # recovers outside remediation (an operator fixes the auth problem and
        # the agent starts heartbeating again), so an exhausted node would be
        # refused remediation for the life of the process on every future
        # degradation, until someone called the manual reset endpoint.
        #
        # #14465: the recovery reset formerly lived here (a heartbeat newer
        # than the last attempt), then inside update_node_heartbeat's ONLINE
        # transition, then behind a dwell window there. All three cleared on a
        # POSITIVE observation of health that a later flap does not retract,
        # which made each one fakeable by a flap in a different way. Replaced
        # with `_forgive_if_expired`, inside `_check_remediation_limits` --
        # gated on elapsed time since the last ATTEMPT rather than any
        # heartbeat/streak signal, but NOT a complete fix on its own: see
        # `_effective_tracker_expiry_s` for what its margin does and does not
        # bound (it does not bound `execute_playbook`'s own runtime, which has
        # no wall-clock timeout at all -- #14524; the margin's own N=5
        # coverage gap at this floor is #14515). It is also not the reason
        # `count` stays low for a node whose agent keeps heartbeating;
        # `success = restarted and await self._heartbeat_returned(...)`, a
        # few lines below, is.

        # Check remediation limits (cooldown and max attempts)
        can_proceed, skip_reason, tracker = self._check_remediation_limits(node_id, now)

        if not can_proceed:
            if skip_reason == "max_attempts":
                await self._handle_max_attempts_refusal(db, node, tracker)
            return False

        # Log remediation attempt
        logger.info(
            "Attempting remediation for node %s (attempt %d/%d)",
            node_id,
            tracker["count"] + 1,
            MAX_REMEDIATION_ATTEMPTS,
        )

        # Create remediation started event
        event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=node_id,
            event_type=EventType.REMEDIATION_STARTED.value,
            severity=EventSeverity.INFO.value,
            message=f"Starting auto-remediation for {node.hostname}",
            details={"attempt": tracker["count"] + 1, "action": "restart_agent"},
        )
        db.add(event)
        await db.commit()

        # Broadcast remediation started via WebSocket
        await self._broadcast_remediation_event(
            node_id,
            "started",
            message=f"Attempting to restart SLM agent on {node.hostname}",
        )

        # Try to restart the SLM agent via Ansible (#1814: prefer ansible_name)
        ansible_target = node.ansible_target
        restarted = await self._restart_service_via_ansible(
            ansible_target,
            "slm-agent",
        )

        # #14344: the restart exiting 0 is not remediation. A node whose agent
        # starts cleanly but cannot authenticate (#14350) restarts forever,
        # reports success every time, and — because success RESETS the attempt
        # counter below — never reaches MAX_REMEDIATION_ATTEMPTS and never
        # escalates. Observed live: ten consecutive "Remediation successful"
        # over fifty minutes, with the node never heartbeating once.
        success = restarted and await self._heartbeat_returned(node, now)

        # Update tracker (reset on success, increment on failure)
        self._remediation_tracker[node_id] = {
            "count": tracker["count"] + 1 if not success else 0,
            "last_attempt": now,
        }

        # Record result and broadcast
        await self._record_remediation_result(db, node, success, tracker, restarted=restarted)
        return True

    async def _heartbeat_returned(self, node: Node, restarted_at: datetime) -> bool:
        """Did a heartbeat arrive after the restart, within the wait window?

        This is what remediation is for, so this is what its success means
        (#14344). Polls the node row rather than trusting the restart's exit
        code, because an agent can start perfectly and still be rejected.

        Returns False on timeout, which lets the attempt counter advance toward
        escalation instead of resetting.
        """
        from services.database import db_service

        loop = asyncio.get_running_loop()
        deadline = loop.time() + REMEDIATION_HEARTBEAT_WAIT_S
        while True:
            # Check first, sleep second: an agent that comes back immediately
            # should not cost a full poll interval of reconciler time.
            async with db_service.session() as check_db:
                result = await check_db.execute(select(Node).where(Node.node_id == node.node_id))
                fresh = result.scalar_one_or_none()
            beat = getattr(fresh, "last_heartbeat", None)
            if beat is not None and beat > restarted_at:
                return True
            if loop.time() >= deadline:
                break
            await asyncio.sleep(REMEDIATION_HEARTBEAT_POLL_S)
        logger.warning(
            "Remediation: agent on %s restarted but sent no heartbeat within %ss — "
            "not counting this as success (#14344)",
            node.node_id,
            REMEDIATION_HEARTBEAT_WAIT_S,
        )
        return False

    async def _restart_service_via_ansible(
        self,
        hostname: str,
        service_name: str,
    ) -> bool:
        """Restart a systemd service on a remote node via Ansible playbook.

        Returns True if successful, False otherwise.
        """
        try:
            from services.playbook_executor import get_playbook_executor

            executor = get_playbook_executor()
            result = await executor.execute_playbook(
                playbook_name="manage-service.yml",
                limit=[hostname],
                extra_vars={
                    "service_name": service_name,
                    "service_action": "restarted",
                },
            )

            if result.get("success"):
                logger.info("Successfully restarted %s on %s", service_name, hostname)
                return True
            else:
                error_msg = result.get("error", "Unknown error")
                logger.warning(
                    "Failed to restart %s on %s: %s",
                    service_name,
                    hostname,
                    error_msg,
                )
                return False

        except Exception as e:
            logger.warning("Error restarting %s on %s: %s", service_name, hostname, e)
            return False

    def reset_remediation_tracker(self, node_id: str) -> None:
        """Reset remediation tracker for a node (e.g., after manual intervention)."""
        if node_id in self._remediation_tracker:
            del self._remediation_tracker[node_id]
            logger.info("Reset remediation tracker for node %s", node_id)

    def reset_service_remediation_tracker(self, node_id: str, service_name: str = None) -> None:
        """Reset service remediation tracker for a node/service."""
        if service_name:
            key = (node_id, service_name)
            if key in self._service_remediation_tracker:
                del self._service_remediation_tracker[key]
                logger.info(
                    "Reset service remediation tracker for %s on %s",
                    service_name,
                    node_id,
                )
        else:
            keys_to_remove = [k for k in self._service_remediation_tracker if k[0] == node_id]
            for key in keys_to_remove:
                del self._service_remediation_tracker[key]
            if keys_to_remove:
                logger.info("Reset all service remediation trackers for node %s", node_id)

    async def _remediate_failed_services(self) -> None:
        """Auto-restart failed services that are enabled.

        Conservative approach:
        - Only restart services with status="failed" that are enabled (should be running)
        - Only restart AutoBot-related services (category=autobot)
        - Rate limited: Max 3 attempts per service, 2 min cooldown
        - Respects maintenance windows
        """
        from services.database import db_service

        async with db_service.session() as db:
            # Check if auto-restart services is enabled
            auto_restart = await db.execute(select(Setting).where(Setting.key == "auto_restart_services"))
            setting = auto_restart.scalar_one_or_none()

            if not setting or setting.value != "true":
                return

            # Get failed services that are enabled (should be running)
            result = await db.execute(
                select(Service).where(
                    Service.status == ServiceStatus.FAILED.value,
                    Service.enabled.is_(True),
                    Service.category == ServiceCategory.AUTOBOT.value,
                )
            )
            failed_services = result.scalars().all()

            for service in failed_services:
                # Check if node is in maintenance window
                if await self._is_remediation_suppressed(db, service.node_id):
                    logger.debug(
                        "Skipping service remediation for %s on %s - maintenance window",
                        service.service_name,
                        service.node_id,
                    )
                    continue

                # Get node for SSH details
                node_result = await db.execute(select(Node).where(Node.node_id == service.node_id))
                node = node_result.scalar_one_or_none()
                if not node:
                    continue

                # Skip if node is offline (can't SSH to it)
                if node.status == NodeStatus.OFFLINE.value:
                    continue

                await self._remediate_failed_service(db, node, service)

    def _check_service_cooldown(self, node_id: str, service_name: str, tracker: dict, now: datetime) -> bool:
        """Check if service is in remediation cooldown.

        Helper for _remediate_failed_service (Issue #665).

        Returns True if in cooldown (should skip), False otherwise.
        """
        if tracker["last_attempt"]:
            elapsed = (now - tracker["last_attempt"]).total_seconds()
            if elapsed < SERVICE_REMEDIATION_COOLDOWN:
                logger.debug(
                    "Service %s on %s in remediation cooldown (%d seconds remaining)",
                    service_name,
                    node_id,
                    SERVICE_REMEDIATION_COOLDOWN - elapsed,
                )
                return True
        return False

    async def _create_max_attempts_service_event(
        self, db: AsyncSession, node: Node, service: Service, tracker: dict
    ) -> None:
        """Create event when max service restart attempts exceeded.

        Helper for _remediate_failed_service (Issue #665).
        """
        logger.warning(
            "Service %s on %s exceeded max restart attempts (%d). " "Human intervention required.",
            service.service_name,
            node.node_id,
            MAX_SERVICE_RESTART_ATTEMPTS,
        )
        event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=node.node_id,
            event_type=EventType.REMEDIATION_COMPLETED.value,
            severity=EventSeverity.WARNING.value,
            message=(
                f"Service {service.service_name} on {node.hostname} requires "
                f"human intervention after {MAX_SERVICE_RESTART_ATTEMPTS} failed restart attempts"
            ),
            details={
                "service_name": service.service_name,
                "attempts": tracker["count"],
                "action_required": "manual_review",
            },
        )
        db.add(event)
        await db.commit()

    async def _handle_service_restart_result(
        self,
        db: AsyncSession,
        node: Node,
        service: Service,
        success: bool,
        tracker: dict,
    ) -> None:
        """Handle success/failure after service restart attempt.

        Helper for _remediate_failed_service (Issue #665).
        """
        if success:
            service.status = ServiceStatus.RUNNING.value
            logger.info(
                "Successfully restarted service %s on %s",
                service.service_name,
                node.node_id,
            )
            await self._broadcast_service_remediation(
                node.node_id,
                service.service_name,
                "completed",
                success=True,
                message=f"Successfully restarted {service.service_name}",
            )
        else:
            logger.warning(
                "Failed to restart service %s on %s (attempt %d/%d)",
                service.service_name,
                node.node_id,
                tracker["count"] + 1,
                MAX_SERVICE_RESTART_ATTEMPTS,
            )
            await self._broadcast_service_remediation(
                node.node_id,
                service.service_name,
                "completed",
                success=False,
                message=(
                    f"Failed to restart {service.service_name} "
                    f"(attempt {tracker['count'] + 1}/{MAX_SERVICE_RESTART_ATTEMPTS})"
                ),
            )
        await db.commit()

    async def _remediate_failed_service(self, db: AsyncSession, node: Node, service: Service) -> bool:
        """Attempt to restart a single failed service.

        Returns True if remediation was attempted, False if skipped.
        """
        key = (node.node_id, service.service_name)
        now = datetime.now(timezone.utc)

        tracker = self._service_remediation_tracker.get(key, {"count": 0, "last_attempt": None})

        # Check cooldown
        if self._check_service_cooldown(node.node_id, service.service_name, tracker, now):
            return False

        # Check attempt limit
        if tracker["count"] >= MAX_SERVICE_RESTART_ATTEMPTS:
            if not tracker.get("exhausted"):
                await self._create_max_attempts_service_event(db, node, service, tracker)
                tracker["exhausted"] = True
                self._service_remediation_tracker[key] = tracker
            return False

        # Attempt restart
        logger.info(
            "Attempting to restart service %s on %s (attempt %d/%d)",
            service.service_name,
            node.node_id,
            tracker["count"] + 1,
            MAX_SERVICE_RESTART_ATTEMPTS,
        )

        # Broadcast restart starting
        await self._broadcast_service_remediation(
            node.node_id,
            service.service_name,
            "started",
            message=f"Attempting to restart {service.service_name} on {node.hostname}",
        )

        # Try to restart via Ansible (#1814: prefer ansible_name)
        ansible_target = node.ansible_target
        success = await self._restart_service_via_ansible(
            ansible_target,
            service.service_name,
        )

        # Update tracker
        self._service_remediation_tracker[key] = {
            "count": tracker["count"] + 1 if not success else 0,
            "last_attempt": now,
        }

        # Handle result and broadcast
        await self._handle_service_restart_result(db, node, service, success, tracker)
        return True

    async def _broadcast_service_remediation(
        self,
        node_id: str,
        service_name: str,
        event_type: str,
        success: bool = None,
        message: str = None,
    ) -> None:
        """Broadcast service remediation event via WebSocket."""
        try:
            from api.websocket import ws_manager

            await ws_manager.send_service_status(
                node_id,
                service_name,
                status=("restarting" if event_type == "started" else ("running" if success else "failed")),
                action="auto_restart",
                success=success if event_type == "completed" else None,
                message=message,
            )
        except Exception as e:
            logger.debug("Failed to broadcast service remediation event: %s", e)

    async def _check_auto_rollback(self) -> None:
        """Check for health failures after recent deployments and trigger auto-rollback.

        Conservative approach:
        - Only rolls back if node becomes degraded/error within rollback window
        - Only affects the most recent completed deployment
        - Requires auto_rollback setting to be enabled
        """
        from services.database import db_service

        async with db_service.session() as db:
            # Check if auto-rollback is enabled
            auto_rollback = await db.execute(select(Setting).where(Setting.key == "auto_rollback"))
            setting = auto_rollback.scalar_one_or_none()

            if not setting or setting.value != "true":
                return

            # Get rollback window setting
            rollback_window_setting = await db.execute(select(Setting).where(Setting.key == "rollback_window_seconds"))
            window_setting = rollback_window_setting.scalar_one_or_none()
            rollback_window = int(window_setting.value) if window_setting else DEFAULT_ROLLBACK_WINDOW

            cutoff = datetime.now(timezone.utc) - timedelta(seconds=rollback_window)

            # Find nodes that are degraded/error with recent completed deployments
            degraded_nodes = await db.execute(
                select(Node).where(Node.status.in_([NodeStatus.DEGRADED.value, NodeStatus.ERROR.value]))
            )
            degraded_nodes = degraded_nodes.scalars().all()

            for node in degraded_nodes:
                await self._check_node_for_rollback(db, node, cutoff)

    async def _find_recent_deployment_for_rollback(
        self, db: AsyncSession, node: Node, cutoff: datetime
    ) -> Deployment | None:
        """Find recent deployment eligible for rollback.

        Helper for _check_node_for_rollback (Issue #665).
        """
        result = await db.execute(
            select(Deployment)
            .where(Deployment.node_id == node.node_id)
            .where(Deployment.status == DeploymentStatus.COMPLETED.value)
            .where(Deployment.completed_at >= cutoff)
            .order_by(Deployment.completed_at.desc())
            .limit(1)
        )
        recent_deployment = result.scalar_one_or_none()

        if not recent_deployment:
            return None

        # Check if already rolled back
        if recent_deployment.extra_data and recent_deployment.extra_data.get("auto_rollback_attempted"):
            return None

        return recent_deployment

    async def _create_rollback_started_event(self, db: AsyncSession, node: Node, deployment: Deployment) -> None:
        """Create and broadcast rollback started event.

        Helper for _check_node_for_rollback (Issue #665).
        """
        logger.info(
            "Node %s degraded after recent deployment %s - triggering auto-rollback",
            node.node_id,
            deployment.deployment_id,
        )

        event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=node.node_id,
            event_type=EventType.ROLLBACK_STARTED.value,
            severity=EventSeverity.WARNING.value,
            message=f"Auto-rollback triggered for deployment {deployment.deployment_id}",
            details={
                "deployment_id": deployment.deployment_id,
                "roles": deployment.roles,
                "reason": f"Node status became {node.status} after deployment",
            },
        )
        db.add(event)
        await db.commit()

        await self._broadcast_rollback_event(
            node.node_id,
            deployment.deployment_id,
            "started",
            message=f"Auto-rollback triggered due to {node.status} status after deployment",
        )

    async def _handle_rollback_result(
        self, db: AsyncSession, node: Node, deployment: Deployment, success: bool
    ) -> None:
        """Create and broadcast completion event based on rollback result.

        Helper for _check_node_for_rollback (Issue #665).
        """
        if success:
            event = NodeEvent(
                event_id=str(uuid.uuid4())[:16],
                node_id=node.node_id,
                event_type=EventType.ROLLBACK_COMPLETED.value,
                severity=EventSeverity.INFO.value,
                message=f"Auto-rollback completed for deployment {deployment.deployment_id}",
                details={
                    "deployment_id": deployment.deployment_id,
                    "roles_removed": deployment.roles,
                    "success": True,
                },
            )
            await self._broadcast_rollback_event(
                node.node_id,
                deployment.deployment_id,
                "completed",
                success=True,
                message="Deployment rolled back successfully",
            )
        else:
            event = NodeEvent(
                event_id=str(uuid.uuid4())[:16],
                node_id=node.node_id,
                event_type=EventType.ROLLBACK_COMPLETED.value,
                severity=EventSeverity.ERROR.value,
                message=f"Auto-rollback failed for deployment {deployment.deployment_id}",
                details={
                    "deployment_id": deployment.deployment_id,
                    "success": False,
                    "action_required": "manual_review",
                },
            )
            await self._broadcast_rollback_event(
                node.node_id,
                deployment.deployment_id,
                "completed",
                success=False,
                message="Rollback failed - manual intervention required",
            )

        db.add(event)
        await db.commit()

    async def _check_node_for_rollback(self, db: AsyncSession, node: Node, cutoff: datetime) -> None:
        """Check if a degraded/error node should have its recent deployment rolled back."""
        recent_deployment = await self._find_recent_deployment_for_rollback(db, node, cutoff)

        if not recent_deployment:
            return

        await self._create_rollback_started_event(db, node, recent_deployment)

        success = await self._perform_auto_rollback(db, recent_deployment, node)

        await self._handle_rollback_result(db, node, recent_deployment, success)

    async def _perform_auto_rollback(self, db: AsyncSession, deployment: Deployment, node: Node) -> bool:
        """Perform the actual rollback of a deployment.

        Returns True if successful, False otherwise.
        """
        try:
            # Mark deployment as rolled back
            deployment.status = DeploymentStatus.ROLLED_BACK.value
            deployment.extra_data = {
                **(deployment.extra_data or {}),
                "auto_rollback_attempted": True,
                "auto_rollback_reason": f"Node status: {node.status}",
                "auto_rollback_time": utc_timestamp(),
            }

            # Remove deployed roles from node
            current_roles = set(node.roles or [])
            deployed_roles = set(deployment.roles or [])
            node.roles = list(current_roles - deployed_roles)

            await db.commit()

            logger.info(
                "Auto-rollback completed for deployment %s on node %s - removed roles: %s",
                deployment.deployment_id,
                node.node_id,
                deployment.roles,
            )
            return True

        except Exception as e:
            logger.error(
                "Auto-rollback failed for deployment %s: %s",
                deployment.deployment_id,
                e,
            )
            # Mark that rollback was attempted even if it failed
            deployment.extra_data = {
                **(deployment.extra_data or {}),
                "auto_rollback_attempted": True,
                "auto_rollback_error": str(e),
            }
            await db.commit()
            return False

    async def _broadcast_rollback_event(
        self,
        node_id: str,
        deployment_id: str,
        event_type: str,
        success: bool = None,
        message: str = None,
    ) -> None:
        """Broadcast rollback event via WebSocket."""
        try:
            from api.websocket import ws_manager

            await ws_manager.broadcast(
                "events:global",
                {
                    "type": "rollback_event",
                    "node_id": node_id,
                    "data": {
                        "deployment_id": deployment_id,
                        "event_type": event_type,
                        "success": success,
                        "message": message,
                    },
                    "timestamp": asyncio.get_running_loop().time(),
                },
            )
        except Exception as e:
            logger.debug("Failed to broadcast rollback event: %s", e)

    async def _is_remediation_suppressed(self, db: AsyncSession, node_id: str) -> bool:
        """Check if remediation is suppressed for a node due to maintenance window."""
        try:
            from api.maintenance import should_suppress_remediation

            return await should_suppress_remediation(db, node_id)
        except ImportError:
            return False

    async def _reconcile_roles(self) -> None:
        """Reconcile roles on nodes if auto-reconcile is enabled."""
        from services.database import db_service

        async with db_service.session() as db:
            auto_reconcile = await db.execute(select(Setting).where(Setting.key == "auto_reconcile"))
            setting = auto_reconcile.scalar_one_or_none()

            if not setting or setting.value != "true":
                return

            result = await db.execute(
                select(Node).where(Node.status.in_([NodeStatus.DEGRADED.value, NodeStatus.ERROR.value]))
            )
            degraded_nodes = result.scalars().all()

            for node in degraded_nodes:
                logger.info(
                    "Auto-reconciling node %s (status: %s)",
                    node.node_id,
                    node.status,
                )

    async def _find_node_by_id_or_hostname(self, db: AsyncSession, node_id: str) -> Node | None:
        """Find node by node_id or fallback to hostname.

        Helper for update_node_heartbeat (Issue #665).
        """
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = result.scalar_one_or_none()

        if not node:
            result = await db.execute(select(Node).where(Node.hostname == node_id))
            node = result.scalar_one_or_none()

        return node

    async def _update_node_metrics(
        self,
        db: AsyncSession,
        node: Node,
        cpu_percent: float,
        memory_percent: float,
        disk_percent: float,
        agent_version: str | None = None,
        os_info: str | None = None,
        extra_data: dict | None = None,
    ) -> bool:
        """Update basic metrics and optional fields.

        Helper for update_node_heartbeat (Issue #665).

        Returns whether a managed service is CURRENTLY churning (#14465), for
        `_calculate_node_status` to act on.
        """
        node.cpu_percent = cpu_percent
        node.memory_percent = memory_percent
        node.disk_percent = disk_percent
        node.last_heartbeat = datetime.now(timezone.utc)

        if agent_version:
            node.agent_version = agent_version
        if os_info:
            node.os_info = os_info
        if not extra_data:
            return False

        node.extra_data = {**(node.extra_data or {}), **extra_data}
        services_data = extra_data.get("discovered_services") or extra_data.get("services")
        if not services_data:
            return False
        return await self._sync_discovered_services(db, node.node_id, services_data)

    async def _handle_node_status_change(
        self,
        db: AsyncSession,
        node: Node,
        old_status: str,
        new_status: str,
        cpu_percent: float,
        memory_percent: float,
        disk_percent: float,
    ) -> None:
        """Create event and broadcast if status changed.

        Helper for update_node_heartbeat (Issue #665).
        """
        if old_status == new_status:
            return

        severity = EventSeverity.INFO
        if new_status in [NodeStatus.ERROR.value, NodeStatus.OFFLINE.value]:
            severity = EventSeverity.ERROR
        elif new_status == NodeStatus.DEGRADED.value:
            severity = EventSeverity.WARNING

        event = NodeEvent(
            event_id=str(uuid.uuid4())[:16],
            node_id=node.node_id,
            event_type=EventType.HEALTH_CHECK.value,
            severity=severity.value,
            message=f"Node status changed from {old_status} to {new_status}",
            details={
                "old_status": old_status,
                "new_status": new_status,
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "disk_percent": disk_percent,
            },
        )
        db.add(event)
        logger.info("Node %s status changed: %s -> %s", node.node_id, old_status, new_status)
        await self._broadcast_node_status(node.node_id, new_status, node.hostname)

    async def _broadcast_heartbeat_update(
        self,
        node: Node,
        cpu_percent: float,
        memory_percent: float,
        disk_percent: float,
        new_status: str,
    ) -> None:
        """Broadcast health update via WebSocket.

        Helper for update_node_heartbeat (Issue #665).
        """
        try:
            from api.websocket import ws_manager

            await ws_manager.send_health_update(
                node.node_id,
                cpu_percent,
                memory_percent,
                disk_percent,
                new_status,
                last_heartbeat=(node.last_heartbeat.isoformat() if node.last_heartbeat else None),
            )
        except Exception as e:
            logger.debug("Failed to broadcast health update: %s", e)

    async def update_node_heartbeat(
        self,
        db: AsyncSession,
        node_id: str,
        cpu_percent: float,
        memory_percent: float,
        disk_percent: float,
        agent_version: str | None = None,
        os_info: str | None = None,
        extra_data: dict | None = None,
    ) -> Node | None:
        """Update a node's heartbeat and health metrics."""
        node = await self._find_node_by_id_or_hostname(db, node_id)
        if not node:
            return None

        restart_churn_active = await self._update_node_metrics(
            db,
            node,
            cpu_percent,
            memory_percent,
            disk_percent,
            agent_version,
            os_info,
            extra_data,
        )

        old_status = node.status
        new_status = self._calculate_node_status(
            cpu_percent, memory_percent, disk_percent, extra_data, restart_churn_active
        )

        await self._handle_node_status_change(
            db, node, old_status, new_status, cpu_percent, memory_percent, disk_percent
        )

        node.status = new_status

        await db.commit()
        await db.refresh(node)

        await self._broadcast_heartbeat_update(node, cpu_percent, memory_percent, disk_percent, new_status)

        return node

    def _update_existing_service(
        self,
        service: Service,
        svc_data: dict,
        status: str,
        error_msg: str,
        now: datetime,
    ) -> bool:
        """Apply heartbeat data to an existing Service row.

        Helper for _upsert_service. Ref: #1088.

        Returns whether this managed service is CURRENTLY churning -- its
        restart count rose within the last `RESTART_CHURN_WINDOW_S` (#14465),
        a level rather than a pulse. Computed here, not in
        `_calculate_node_status`, because only this call site holds the OLD
        `Service` row before it gets overwritten.
        """
        is_churning, last_increase_iso = _restart_churn_active(svc_data, service.extra_data or {}, now)

        service.status = status
        service.active_state = svc_data.get("active_state")
        service.sub_state = svc_data.get("sub_state")
        service.main_pid = svc_data.get("main_pid")
        service.memory_bytes = svc_data.get("memory_bytes")
        service.enabled = svc_data.get("enabled", False)
        service.description = svc_data.get("description")
        service.last_checked = now
        # #14465 review: a genuine COPY, not `service.extra_data or {}` handed
        # straight back. SQLAlchemy's Column(JSON) does not reliably flag a
        # reassignment dirty when it is the SAME object mutated in place and
        # written back to itself -- silently dropping every field this method
        # sets, `n_restarts`/`n_restarts_increased_at` included. Load-bearing
        # for the delta: do not "simplify" this back to the old form.
        existing_extra = dict(service.extra_data or {})
        if error_msg:
            existing_extra["error_message"] = error_msg
        else:
            existing_extra.pop("error_message", None)
        existing_extra.update(engine_degraded_fields(svc_data))
        if "n_restarts" in svc_data:
            existing_extra["n_restarts"] = svc_data["n_restarts"]
        existing_extra["n_restarts_increased_at"] = last_increase_iso
        service.extra_data = existing_extra
        return is_churning

    def _create_new_service(
        self,
        node_id: str,
        service_name: str,
        svc_data: dict,
        status: str,
        svc_extra: dict,
        now: datetime,
    ) -> Service:
        """Construct a new Service ORM object from heartbeat data.

        Helper for _upsert_service. Ref: #1088.

        Stores `n_restarts` so the NEXT heartbeat has something to compare
        against (#14465) -- a first observation genuinely has no rate
        information yet, so `n_restarts_increased_at` is deliberately left
        unset here rather than backfilled; the next observed increase arms
        the churn window (see `_restart_churn_active`).
        """
        category = categorize_service(service_name)
        if "n_restarts" in svc_data:
            svc_extra = {**svc_extra, "n_restarts": svc_data["n_restarts"]}
        return Service(
            node_id=node_id,
            service_name=service_name,
            status=status,
            category=category,
            active_state=svc_data.get("active_state"),
            sub_state=svc_data.get("sub_state"),
            main_pid=svc_data.get("main_pid"),
            memory_bytes=svc_data.get("memory_bytes"),
            enabled=svc_data.get("enabled", False),
            description=svc_data.get("description"),
            last_checked=now,
            extra_data=svc_extra,
        )

    async def _upsert_service(
        self,
        db: AsyncSession,
        node_id: str,
        svc_data: dict,
        now: datetime,
    ) -> bool:
        """Upsert a single discovered service record into the database.

        Helper for _sync_discovered_services. Ref: #1088.

        Returns whether this service is managed and CURRENTLY churning --
        see `_restart_churn_active` (#14465).

        #14465 review: the broad `except Exception` below (pre-existing --
        Ref #1088 -- kept broad so one service's sync failure never aborts
        the whole heartbeat) also swallows a transient failure of the row
        SELECT itself, not just the upsert logic after it. On that beat this
        returns `False` ("not churning") regardless of the service's real
        state -- the churn signal is a function of DB availability for that
        one heartbeat, not just of the service. Self-healing (the next
        heartbeat tries again, and the level design means one missed beat
        does not by itself end an already-armed window), but not something
        this fix eliminates.
        """
        service_name = svc_data.get("name")
        if not service_name:
            return False

        try:
            result = await db.execute(
                select(Service).where(
                    Service.node_id == node_id,
                    Service.service_name == service_name,
                )
            )
            service = result.scalar_one_or_none()

            status = svc_data.get("status", "unknown")
            if status not in [s.value for s in ServiceStatus]:
                status = ServiceStatus.UNKNOWN.value

            # Issue #1019: Capture error context for failed services
            error_msg = svc_data.get("error_message", "")
            svc_extra = {"error_message": error_msg} if error_msg else {}
            svc_extra.update(engine_degraded_fields(svc_data))

            if service:
                return self._update_existing_service(service, svc_data, status, error_msg, now)
            service = self._create_new_service(node_id, service_name, svc_data, status, svc_extra, now)
            db.add(service)
            return False
        except Exception as exc:
            logger.warning(
                "service sync failed node=%s service=%s error=%s",
                node_id,
                service_name,
                exc,
            )
            return False

    async def _remove_stale_services(
        self,
        db: AsyncSession,
        node_id: str,
        discovered_services: list,
    ) -> None:
        """Delete services no longer reported by the agent for a node.

        Helper for _sync_discovered_services. Ref: #1088.
        """
        discovered_names = {s.get("name") for s in discovered_services if s.get("name")}
        if not discovered_names:
            return

        stale_result = await db.execute(
            select(Service).where(
                Service.node_id == node_id,
                Service.service_name.notin_(discovered_names),
            )
        )
        for stale_svc in stale_result.scalars().all():
            await db.delete(stale_svc)

    async def _sync_discovered_services(
        self,
        db: AsyncSession,
        node_id: str,
        discovered_services: list,
    ) -> bool:
        """
        Sync discovered services from agent heartbeat to database.

        Related to Issue #728.

        Returns whether ANY managed service is CURRENTLY churning (#14465).
        """
        if not discovered_services:
            return False

        now = datetime.now(timezone.utc)

        any_churning = False
        for svc_data in discovered_services:
            if await self._upsert_service(db, node_id, svc_data, now):
                any_churning = True

        # Remove stale services no longer reported by the agent (#1018)
        await self._remove_stale_services(db, node_id, discovered_services)

        # Note: commit happens in the calling method (update_node_heartbeat)
        return any_churning

    def _calculate_node_status(
        self,
        cpu_percent: float,
        memory_percent: float,
        disk_percent: float,
        extra_data: dict | None = None,
        restart_churn_active: bool = False,
    ) -> str:
        """Calculate node status based on health metrics and services.

        Issue #1604: Also degrade if any autobot service is crash-looping.

        #14465: this used to degrade on `n_restarts > 3` -- systemd's
        `NRestarts` read as a static absolute threshold. `NRestarts` climbs
        for as long as a unit keeps failing (systemd resets it on the next
        clean manual start once a unit settles, not merely with the passage
        of time), so a static gate on it can climb past 3 and never come back
        down on its own: once any managed service anywhere in the node's
        uptime crossed 3 restarts -- one redeploy, one operator restart, one
        long-resolved crash-loop -- every future heartbeat was forced
        DEGRADED regardless of current state, with no path back to ONLINE.

        Replaced with two signals over the SAME field, each answering a
        different question a static threshold cannot:

        - `restart_churn_active` (computed in `_update_existing_service` via
          `_restart_churn_active`) catches a service CHURNING -- restarting
          faster than it settles. This is a LEVEL, not a pulse: it reports
          "an increase was observed within the last `RESTART_CHURN_WINDOW_S`",
          not "did it increase since the immediately-preceding heartbeat".
          The latter was tried first and found to regress: health_collector's
          own service-discovery sweep is cached for 300s
          (`_SERVICE_DISCOVERY_TTL`) against a 30s heartbeat, so 9 of every 10
          beats carry a byte-identical cached snapshot and a bare pulse only
          fires on the ~1 in 10 that lands on a cache refresh -- measured, 1
          of 20 beats degraded across continuous churn, and the node flapped
          ONLINE/DEGRADED every 5 minutes instead of staying DEGRADED. See
          `RESTART_CHURN_WINDOW_S` for the window and its own trade-offs.
        - `status == "failed"` (below) catches a service that has SETTLED --
          every unit template sets `StartLimitBurst`/`StartLimitIntervalSec`
          (#4090), so a real, ongoing crash loop eventually reaches systemd's
          designed end state and stops restarting altogether. Neither a pulse
          nor the level above catches this alone: both go quiet once
          `NRestarts` stops climbing, exactly when a settled service needs
          catching most.

        Both are scoped by `is_managed_autobot_service` (autobot*-prefixed
        service names, or `slm-agent` itself, NOT explicitly disabled in
        systemd on THIS node) rather than `extra_data["services"]`
        (`slm_services_to_monitor`) -- that operator-declared set is `[]` by
        role default, is `[]` on at least one real inventory node, and never
        contains `slm-agent`, the one unit remediation actually restarts, so
        scoping to it left this whole class of signal dark for most of the
        fleet on the one service that matters most.
        """
        if cpu_percent > 95 or memory_percent > 95 or disk_percent > 95:
            return NodeStatus.ERROR.value

        if _service_health_degraded(extra_data, restart_churn_active):
            return NodeStatus.DEGRADED.value

        if cpu_percent > 80 or memory_percent > 80 or disk_percent > 80:
            return NodeStatus.DEGRADED.value

        return NodeStatus.ONLINE.value

    # ------------------------------------------------------------------
    # Manifest-driven background tasks (Issue #926 Phase 3)
    # ------------------------------------------------------------------

    async def _poll_manifest_health(self) -> None:
        """
        Poll manifest-defined health endpoints for every assigned NodeRole.

        Updates NodeRole.status based on HTTP response.
        Runs every MANIFEST_HEALTH_INTERVAL seconds (default 60s).
        """
        from models.database import NodeRole
        from services.database import db_service
        from services.manifest_loader import get_manifest_loader

        loader = get_manifest_loader()

        async with db_service.session() as db:
            result = await db.execute(select(NodeRole))
            node_roles = result.scalars().all()

            node_ip_map = await self._build_node_ip_map(db)

            for node_role in node_roles:
                endpoint = loader.get_health_endpoint(node_role.role_name)
                if not endpoint:
                    continue

                node_ip = node_ip_map.get(node_role.node_id)
                if not node_ip:
                    continue

                # Replace localhost/127.0.0.1 with the node's actual IP
                url = endpoint.replace("localhost", node_ip).replace("127.0.0.1", node_ip)

                new_status = await self._http_health_check(url)
                if new_status != node_role.status:
                    logger.info(
                        "NodeRole %s/%s health: %s → %s",
                        node_role.node_id,
                        node_role.role_name,
                        node_role.status,
                        new_status,
                    )
                    node_role.status = new_status

            await db.commit()

    async def _build_node_ip_map(self, db: AsyncSession) -> dict:
        """Return {node_id: ip_address} for all known nodes.

        Helper for _poll_manifest_health (Issue #926 Phase 3).
        """
        result = await db.execute(select(Node))
        return {n.node_id: n.ip_address for n in result.scalars().all()}

    async def _http_health_check(self, url: str) -> str:
        """
        Perform a single HTTP(S) GET health check.

        Helper for _poll_manifest_health (Issue #926 Phase 3).
        Returns: "healthy" | "unhealthy" | "unknown"
        """
        try:
            import aiohttp

            ssl_ctx = ssl.create_default_context()
            if not settings.verify_ssl:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
            timeout = aiohttp.ClientTimeout(total=10)
            # #13134: pooled client instead of a per-call ClientSession.
            async with get_http_client().tracked_request("GET", url, ssl=ssl_ctx, timeout=timeout) as resp:
                return "healthy" if resp.status < 400 else "unhealthy"
        except Exception as exc:
            logger.debug("Health check failed for %s: %s", url, exc)
            return "unhealthy"

    async def _check_cert_expiry(self) -> None:
        """
        Check TLS cert expiry for roles with tls.auto_rotate=true.

        Logs a warning when a cert expires within rotate_days_before days.
        Runs once per CERT_EXPIRY_CHECK_INTERVAL (daily).
        """
        from services.manifest_loader import get_manifest_loader

        loader = get_manifest_loader()
        all_manifests = loader.load_all()

        for role_name, manifest in all_manifests.items():
            if not manifest.tls or not manifest.tls.auto_rotate:
                continue
            cert_path = manifest.tls.cert
            if not cert_path:
                continue
            days_left = self._cert_days_remaining(cert_path)
            if days_left is None:
                continue
            threshold = loader.get_tls_rotate_days_before(role_name)
            if days_left <= threshold:
                logger.warning(
                    "TLS cert for %s expires in %d day(s) (threshold: %d). " "Run rotate-certs.yml to renew.",
                    role_name,
                    days_left,
                    threshold,
                )

    def _cert_days_remaining(self, cert_path: str) -> int | None:
        """
        Return days until a PEM cert expires, or None if unreadable.

        Helper for _check_cert_expiry (Issue #926 Phase 3).
        """
        from pathlib import Path

        try:
            import cryptography.x509
            from cryptography.hazmat.backends import default_backend

            pem = Path(cert_path).read_bytes()
            cert = cryptography.x509.load_pem_x509_certificate(pem, default_backend())
            delta = cert.not_valid_after_utc.replace(tzinfo=None) - datetime.now(timezone.utc)
            return max(0, delta.days)
        except Exception as exc:
            logger.debug("Could not read cert %s: %s", cert_path, exc)
            return None

    def get_role_health_summary(self, role_statuses: List[dict]) -> str:
        """
        Summarise per-role health into a node-level status string.

        Helper for callers that aggregate manifest health results (#926 Phase 3).
        """
        if not role_statuses:
            return NodeStatus.UNKNOWN.value
        if all(r.get("status") == "healthy" for r in role_statuses):
            return NodeStatus.ONLINE.value
        if any(r.get("status") == "unhealthy" for r in role_statuses):
            return NodeStatus.DEGRADED.value
        return NodeStatus.UNKNOWN.value


reconciler_service = ReconcilerService()
