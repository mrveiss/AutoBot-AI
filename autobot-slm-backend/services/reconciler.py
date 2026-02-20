# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
from datetime import datetime, timedelta
from typing import Dict, List, Optional

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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

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
# Default rollback window (seconds) - deployments older than this won't be auto-rolled back
DEFAULT_ROLLBACK_WINDOW = 600  # 10 minutes
# Service remediation cooldown (shorter than node remediation)
SERVICE_REMEDIATION_COOLDOWN = 120  # 2 minutes
# Maximum service restart attempts before requiring human intervention
MAX_SERVICE_RESTART_ATTEMPTS = 3


class ReconcilerService:
    """Background service for health monitoring and reconciliation.

    Implements conservative remediation:
    - Auto-restart: Automatically restart failed services via SSH
    - Human required: Re-enrollment requires manual approval
    """

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # Default: 3 missed heartbeats = unhealthy
        self._heartbeat_timeout = (
            settings.heartbeat_interval * settings.unhealthy_threshold
        )
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

    async def _handle_degraded_node(
        self, db: AsyncSession, node: Node, old_status: str
    ) -> None:
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
        await self._broadcast_node_status(
            node.node_id, NodeStatus.DEGRADED.value, node.hostname
        )

    async def _handle_offline_node(
        self, db: AsyncSession, node: Node, old_status: str
    ) -> None:
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
        await self._broadcast_node_status(
            node.node_id, NodeStatus.OFFLINE.value, node.hostname
        )

    async def _check_node_health(self) -> None:
        """Check node health based on heartbeats and network reachability."""
        from services.database import db_service
        from sqlalchemy import or_

        async with db_service.session() as db:
            timeout_setting = await db.execute(
                select(Setting).where(Setting.key == "heartbeat_timeout")
            )
            setting = timeout_setting.scalar_one_or_none()
            if setting and setting.value:
                self._heartbeat_timeout = int(setting.value)

            cutoff = datetime.utcnow() - timedelta(seconds=self._heartbeat_timeout)

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

    async def _broadcast_node_status(
        self, node_id: str, status: str, hostname: str = None
    ) -> None:
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

            await ws_manager.send_remediation_event(
                node_id, event_type, success, message
            )
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
            auto_remediate = await db.execute(
                select(Setting).where(Setting.key == "auto_remediate")
            )
            setting = auto_remediate.scalar_one_or_none()

            if not setting or setting.value != "true":
                return

            # Get degraded nodes (reachable but agent not responding)
            result = await db.execute(
                select(Node).where(Node.status == NodeStatus.DEGRADED.value)
            )
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

    def _check_remediation_limits(
        self, node_id: str, now: datetime
    ) -> tuple[bool, Optional[str], dict]:
        """Check if remediation can proceed based on cooldown and attempt limits.

        Helper for _remediate_node (Issue #665).

        Returns:
            (can_proceed, skip_reason, tracker) tuple where:
            - can_proceed: True if remediation should proceed
            - skip_reason: "cooldown" or "max_attempts" if skipped, None otherwise
            - tracker: The remediation tracker dict for this node
        """
        tracker = self._remediation_tracker.get(
            node_id, {"count": 0, "last_attempt": None}
        )

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

    async def _create_max_attempts_event(
        self, db: AsyncSession, node: Node, tracker: dict
    ) -> None:
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

    async def _record_remediation_result(
        self, db: AsyncSession, node: Node, success: bool, tracker: dict
    ) -> None:
        """Create completion event and broadcast for remediation result.

        Helper for _remediate_node (Issue #665).
        """
        node_id = node.node_id

        if success:
            event = NodeEvent(
                event_id=str(uuid.uuid4())[:16],
                node_id=node_id,
                event_type=EventType.REMEDIATION_COMPLETED.value,
                severity=EventSeverity.INFO.value,
                message=f"Successfully restarted SLM agent on {node.hostname}",
                details={"action": "restart_agent", "success": True},
            )
            logger.info("Remediation successful for node %s", node_id)
            await self._broadcast_remediation_event(
                node_id,
                "completed",
                success=True,
                message=f"Successfully restarted SLM agent on {node.hostname}",
            )
        else:
            event = NodeEvent(
                event_id=str(uuid.uuid4())[:16],
                node_id=node_id,
                event_type=EventType.REMEDIATION_COMPLETED.value,
                severity=EventSeverity.WARNING.value,
                message=f"Failed to restart SLM agent on {node.hostname}",
                details={
                    "action": "restart_agent",
                    "success": False,
                    "attempts_remaining": MAX_REMEDIATION_ATTEMPTS
                    - tracker["count"]
                    - 1,
                },
            )
            logger.warning("Remediation failed for node %s", node_id)
            await self._broadcast_remediation_event(
                node_id,
                "completed",
                success=False,
                message=f"Failed to restart SLM agent on {node.hostname}",
            )

        db.add(event)
        await db.commit()

    async def _remediate_node(self, db: AsyncSession, node: Node) -> bool:
        """Attempt to remediate a single degraded node.

        Returns True if remediation was attempted, False if skipped.
        """
        node_id = node.node_id
        now = datetime.utcnow()

        # Check remediation limits (cooldown and max attempts)
        can_proceed, skip_reason, tracker = self._check_remediation_limits(node_id, now)

        if not can_proceed:
            if skip_reason == "max_attempts" and not tracker.get("exhausted"):
                await self._create_max_attempts_event(db, node, tracker)
                tracker["exhausted"] = True
                self._remediation_tracker[node_id] = tracker
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

        # Try to restart the SLM agent via Ansible
        success = await self._restart_service_via_ansible(
            node.hostname,
            "slm-agent",
        )

        # Update tracker (reset on success, increment on failure)
        self._remediation_tracker[node_id] = {
            "count": tracker["count"] + 1 if not success else 0,
            "last_attempt": now,
        }

        # Record result and broadcast
        await self._record_remediation_result(db, node, success, tracker)
        return True

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

    def reset_service_remediation_tracker(
        self, node_id: str, service_name: str = None
    ) -> None:
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
            keys_to_remove = [
                k for k in self._service_remediation_tracker if k[0] == node_id
            ]
            for key in keys_to_remove:
                del self._service_remediation_tracker[key]
            if keys_to_remove:
                logger.info(
                    "Reset all service remediation trackers for node %s", node_id
                )

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
            auto_restart = await db.execute(
                select(Setting).where(Setting.key == "auto_restart_services")
            )
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
                node_result = await db.execute(
                    select(Node).where(Node.node_id == service.node_id)
                )
                node = node_result.scalar_one_or_none()
                if not node:
                    continue

                # Skip if node is offline (can't SSH to it)
                if node.status == NodeStatus.OFFLINE.value:
                    continue

                await self._remediate_failed_service(db, node, service)

    def _check_service_cooldown(
        self, node_id: str, service_name: str, tracker: dict, now: datetime
    ) -> bool:
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
            "Service %s on %s exceeded max restart attempts (%d). "
            "Human intervention required.",
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

    async def _remediate_failed_service(
        self, db: AsyncSession, node: Node, service: Service
    ) -> bool:
        """Attempt to restart a single failed service.

        Returns True if remediation was attempted, False if skipped.
        """
        key = (node.node_id, service.service_name)
        now = datetime.utcnow()

        tracker = self._service_remediation_tracker.get(
            key, {"count": 0, "last_attempt": None}
        )

        # Check cooldown
        if self._check_service_cooldown(
            node.node_id, service.service_name, tracker, now
        ):
            return False

        # Check attempt limit
        if tracker["count"] >= MAX_SERVICE_RESTART_ATTEMPTS:
            if not tracker.get("exhausted"):
                await self._create_max_attempts_service_event(
                    db, node, service, tracker
                )
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

        # Try to restart via Ansible
        success = await self._restart_service_via_ansible(
            node.hostname,
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
                status="restarting"
                if event_type == "started"
                else ("running" if success else "failed"),
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
            auto_rollback = await db.execute(
                select(Setting).where(Setting.key == "auto_rollback")
            )
            setting = auto_rollback.scalar_one_or_none()

            if not setting or setting.value != "true":
                return

            # Get rollback window setting
            rollback_window_setting = await db.execute(
                select(Setting).where(Setting.key == "rollback_window_seconds")
            )
            window_setting = rollback_window_setting.scalar_one_or_none()
            rollback_window = (
                int(window_setting.value) if window_setting else DEFAULT_ROLLBACK_WINDOW
            )

            cutoff = datetime.utcnow() - timedelta(seconds=rollback_window)

            # Find nodes that are degraded/error with recent completed deployments
            degraded_nodes = await db.execute(
                select(Node).where(
                    Node.status.in_([NodeStatus.DEGRADED.value, NodeStatus.ERROR.value])
                )
            )
            degraded_nodes = degraded_nodes.scalars().all()

            for node in degraded_nodes:
                await self._check_node_for_rollback(db, node, cutoff)

    async def _find_recent_deployment_for_rollback(
        self, db: AsyncSession, node: Node, cutoff: datetime
    ) -> Optional[Deployment]:
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
        if recent_deployment.extra_data and recent_deployment.extra_data.get(
            "auto_rollback_attempted"
        ):
            return None

        return recent_deployment

    async def _create_rollback_started_event(
        self, db: AsyncSession, node: Node, deployment: Deployment
    ) -> None:
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

    async def _check_node_for_rollback(
        self, db: AsyncSession, node: Node, cutoff: datetime
    ) -> None:
        """Check if a degraded/error node should have its recent deployment rolled back."""
        recent_deployment = await self._find_recent_deployment_for_rollback(
            db, node, cutoff
        )

        if not recent_deployment:
            return

        await self._create_rollback_started_event(db, node, recent_deployment)

        success = await self._perform_auto_rollback(db, recent_deployment, node)

        await self._handle_rollback_result(db, node, recent_deployment, success)

    async def _perform_auto_rollback(
        self, db: AsyncSession, deployment: Deployment, node: Node
    ) -> bool:
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
                "auto_rollback_time": datetime.utcnow().isoformat(),
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
                    "timestamp": asyncio.get_event_loop().time(),
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
            auto_reconcile = await db.execute(
                select(Setting).where(Setting.key == "auto_reconcile")
            )
            setting = auto_reconcile.scalar_one_or_none()

            if not setting or setting.value != "true":
                return

            result = await db.execute(
                select(Node).where(
                    Node.status.in_([NodeStatus.DEGRADED.value, NodeStatus.ERROR.value])
                )
            )
            degraded_nodes = result.scalars().all()

            for node in degraded_nodes:
                logger.info(
                    "Auto-reconciling node %s (status: %s)",
                    node.node_id,
                    node.status,
                )

    async def _find_node_by_id_or_hostname(
        self, db: AsyncSession, node_id: str
    ) -> Optional[Node]:
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
        agent_version: Optional[str] = None,
        os_info: Optional[str] = None,
        extra_data: Optional[dict] = None,
    ) -> None:
        """Update basic metrics and optional fields.

        Helper for update_node_heartbeat (Issue #665).
        """
        node.cpu_percent = cpu_percent
        node.memory_percent = memory_percent
        node.disk_percent = disk_percent
        node.last_heartbeat = datetime.utcnow()

        if agent_version:
            node.agent_version = agent_version
        if os_info:
            node.os_info = os_info
        if extra_data:
            node.extra_data = {**(node.extra_data or {}), **extra_data}

            services_data = extra_data.get("discovered_services") or extra_data.get(
                "services"
            )
            if services_data:
                await self._sync_discovered_services(db, node.node_id, services_data)

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
        logger.info(
            "Node %s status changed: %s -> %s", node.node_id, old_status, new_status
        )
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
                last_heartbeat=node.last_heartbeat.isoformat()
                if node.last_heartbeat
                else None,
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
        agent_version: Optional[str] = None,
        os_info: Optional[str] = None,
        extra_data: Optional[dict] = None,
    ) -> Optional[Node]:
        """Update a node's heartbeat and health metrics."""
        node = await self._find_node_by_id_or_hostname(db, node_id)
        if not node:
            return None

        await self._update_node_metrics(
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
            cpu_percent, memory_percent, disk_percent
        )

        await self._handle_node_status_change(
            db, node, old_status, new_status, cpu_percent, memory_percent, disk_percent
        )

        node.status = new_status

        await db.commit()
        await db.refresh(node)

        await self._broadcast_heartbeat_update(
            node, cpu_percent, memory_percent, disk_percent, new_status
        )

        return node

    async def _sync_discovered_services(
        self,
        db: AsyncSession,
        node_id: str,
        discovered_services: list,
    ) -> None:
        """
        Sync discovered services from agent heartbeat to database.

        Related to Issue #728.
        """
        if not discovered_services:
            return

        now = datetime.utcnow()

        for svc_data in discovered_services:
            service_name = svc_data.get("name")
            if not service_name:
                continue

            # Check if service exists
            result = await db.execute(
                select(Service).where(
                    Service.node_id == node_id,
                    Service.service_name == service_name,
                )
            )
            service = result.scalar_one_or_none()

            # Map status from agent
            status = svc_data.get("status", "unknown")
            if status not in [s.value for s in ServiceStatus]:
                status = ServiceStatus.UNKNOWN.value

            if service:
                # Update existing
                service.status = status
                service.active_state = svc_data.get("active_state")
                service.sub_state = svc_data.get("sub_state")
                service.main_pid = svc_data.get("main_pid")
                service.memory_bytes = svc_data.get("memory_bytes")
                service.enabled = svc_data.get("enabled", False)
                service.description = svc_data.get("description")
                service.last_checked = now
            else:
                # Create new - auto-categorize based on service name
                category = categorize_service(service_name)
                service = Service(
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
                )
                db.add(service)

        # Remove stale services no longer reported by the agent (#1018)
        discovered_names = {s.get("name") for s in discovered_services if s.get("name")}
        if discovered_names:
            stale_result = await db.execute(
                select(Service).where(
                    Service.node_id == node_id,
                    Service.service_name.notin_(discovered_names),
                )
            )
            for stale_svc in stale_result.scalars().all():
                await db.delete(stale_svc)

        # Note: commit happens in the calling method (update_node_heartbeat)

    def _calculate_node_status(
        self, cpu_percent: float, memory_percent: float, disk_percent: float
    ) -> str:
        """Calculate node status based on health metrics."""
        if cpu_percent > 95 or memory_percent > 95 or disk_percent > 95:
            return NodeStatus.ERROR.value
        elif cpu_percent > 80 or memory_percent > 80 or disk_percent > 80:
            return NodeStatus.DEGRADED.value
        else:
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
                url = endpoint.replace("localhost", node_ip).replace(
                    "127.0.0.1", node_ip
                )

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
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, ssl=ssl_ctx) as resp:
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
                    "TLS cert for %s expires in %d day(s) (threshold: %d). "
                    "Run rotate-certs.yml to renew.",
                    role_name,
                    days_left,
                    threshold,
                )

    def _cert_days_remaining(self, cert_path: str) -> Optional[int]:
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
            delta = cert.not_valid_after_utc.replace(tzinfo=None) - datetime.utcnow()
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
