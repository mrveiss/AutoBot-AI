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
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import (
    EventSeverity,
    EventType,
    Node,
    NodeEvent,
    NodeStatus,
    Service,
    ServiceStatus,
    Setting,
)

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
# Cooldown between remediation attempts (seconds)
REMEDIATION_COOLDOWN = 300  # 5 minutes


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
        self._heartbeat_timeout = settings.heartbeat_interval * settings.unhealthy_threshold
        # Track remediation attempts per node: {node_id: {"count": int, "last_attempt": datetime}}
        self._remediation_tracker: Dict[str, Dict] = {}

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
        while self._running:
            try:
                await self._check_node_health()
                await self._attempt_remediation()
                await self._reconcile_roles()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Reconciler error: %s", e)

            await asyncio.sleep(settings.reconcile_interval)

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
                    Node.status.in_([
                        NodeStatus.ONLINE.value,
                        NodeStatus.DEGRADED.value,
                        NodeStatus.OFFLINE.value,
                    ])
                )
                .where(
                    or_(
                        Node.last_heartbeat < cutoff,
                        Node.last_heartbeat.is_(None)
                    )
                )
            )
            stale_nodes = result.scalars().all()

            for node in stale_nodes:
                # Ping to check if host is reachable
                is_reachable = await self._ping_host(node.ip_address)
                old_status = node.status

                if is_reachable:
                    # Host responds to ping but no heartbeat = degraded (agent not running)
                    if node.status != NodeStatus.DEGRADED.value:
                        node.status = NodeStatus.DEGRADED.value
                        # Create degraded event
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
                else:
                    # Host doesn't respond to ping = offline
                    if node.status != NodeStatus.OFFLINE.value:
                        node.status = NodeStatus.OFFLINE.value
                        # Create offline event
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

            await db.commit()

    async def _ping_host(self, ip_address: str, timeout: int = 2) -> bool:
        """Check if a host responds to ping."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", str(timeout), ip_address,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception as e:
            logger.debug("Ping failed for %s: %s", ip_address, e)
            return False

    async def _attempt_remediation(self) -> None:
        """Attempt to remediate degraded nodes by restarting services.

        Conservative approach:
        - Auto-restart: Restart failed services via SSH
        - Human required: Re-enrollment requires manual approval
        - Rate limited: Max 3 attempts per node, 5 min cooldown
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
                await self._remediate_node(db, node)

    async def _remediate_node(self, db: AsyncSession, node: Node) -> bool:
        """Attempt to remediate a single degraded node.

        Returns True if remediation was attempted, False if skipped.
        """
        node_id = node.node_id
        now = datetime.utcnow()

        # Check remediation tracker
        tracker = self._remediation_tracker.get(node_id, {"count": 0, "last_attempt": None})

        # Check cooldown
        if tracker["last_attempt"]:
            elapsed = (now - tracker["last_attempt"]).total_seconds()
            if elapsed < REMEDIATION_COOLDOWN:
                logger.debug(
                    "Node %s in remediation cooldown (%d seconds remaining)",
                    node_id, REMEDIATION_COOLDOWN - elapsed
                )
                return False

        # Check attempt limit
        if tracker["count"] >= MAX_REMEDIATION_ATTEMPTS:
            logger.warning(
                "Node %s exceeded max remediation attempts (%d). Human intervention required.",
                node_id, MAX_REMEDIATION_ATTEMPTS
            )
            # Create event for human attention
            event = NodeEvent(
                event_id=str(uuid.uuid4())[:16],
                node_id=node_id,
                event_type=EventType.REMEDIATION_COMPLETED.value,
                severity=EventSeverity.WARNING.value,
                message=f"Node {node.hostname} requires human intervention after {MAX_REMEDIATION_ATTEMPTS} failed remediation attempts",
                details={"attempts": tracker["count"], "action_required": "manual_review"},
            )
            db.add(event)
            await db.commit()
            return False

        # Attempt remediation - restart the SLM agent service
        logger.info("Attempting remediation for node %s (attempt %d/%d)",
                   node_id, tracker["count"] + 1, MAX_REMEDIATION_ATTEMPTS)

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

        # Try to restart the SLM agent via SSH
        success = await self._restart_service_via_ssh(
            node.ip_address,
            node.ssh_user or "autobot",
            node.ssh_port or 22,
            "slm-agent"
        )

        # Update tracker
        self._remediation_tracker[node_id] = {
            "count": tracker["count"] + 1 if not success else 0,  # Reset on success
            "last_attempt": now,
        }

        # Create completion event
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
        else:
            event = NodeEvent(
                event_id=str(uuid.uuid4())[:16],
                node_id=node_id,
                event_type=EventType.REMEDIATION_COMPLETED.value,
                severity=EventSeverity.WARNING.value,
                message=f"Failed to restart SLM agent on {node.hostname}",
                details={"action": "restart_agent", "success": False,
                        "attempts_remaining": MAX_REMEDIATION_ATTEMPTS - tracker["count"] - 1},
            )
            logger.warning("Remediation failed for node %s", node_id)

        db.add(event)
        await db.commit()
        return True

    async def _restart_service_via_ssh(
        self,
        ip_address: str,
        ssh_user: str,
        ssh_port: int,
        service_name: str,
    ) -> bool:
        """Restart a systemd service on a remote node via SSH.

        Returns True if successful, False otherwise.
        """
        try:
            # Use SSH with BatchMode to avoid password prompts
            ssh_cmd = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=10",
                "-o", "BatchMode=yes",
                "-p", str(ssh_port),
                f"{ssh_user}@{ip_address}",
                f"sudo systemctl restart {service_name}",
            ]

            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=30.0,
            )

            if proc.returncode == 0:
                logger.info(
                    "Successfully restarted %s on %s",
                    service_name, ip_address
                )
                return True
            else:
                logger.warning(
                    "Failed to restart %s on %s: %s",
                    service_name, ip_address,
                    stderr.decode("utf-8", errors="replace").strip()
                )
                return False

        except asyncio.TimeoutError:
            logger.warning("SSH timeout restarting %s on %s", service_name, ip_address)
            return False
        except Exception as e:
            logger.warning("Error restarting %s on %s: %s", service_name, ip_address, e)
            return False

    def reset_remediation_tracker(self, node_id: str) -> None:
        """Reset remediation tracker for a node (e.g., after manual intervention)."""
        if node_id in self._remediation_tracker:
            del self._remediation_tracker[node_id]
            logger.info("Reset remediation tracker for node %s", node_id)

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
                    Node.status.in_(
                        [NodeStatus.DEGRADED.value, NodeStatus.ERROR.value]
                    )
                )
            )
            degraded_nodes = result.scalars().all()

            for node in degraded_nodes:
                logger.info(
                    "Auto-reconciling node %s (status: %s)",
                    node.node_id,
                    node.status,
                )

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
        # Try to find by node_id first, then by hostname
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = result.scalar_one_or_none()

        if not node:
            # Fallback: try matching by hostname
            result = await db.execute(select(Node).where(Node.hostname == node_id))
            node = result.scalar_one_or_none()

        if not node:
            return None

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

            # Sync discovered services to database (Issue #728)
            if "discovered_services" in extra_data:
                await self._sync_discovered_services(
                    db, node.node_id, extra_data["discovered_services"]
                )

        old_status = node.status
        new_status = self._calculate_node_status(cpu_percent, memory_percent, disk_percent)

        # Create event if status changed
        if old_status != new_status:
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
                "Node %s status changed: %s -> %s",
                node.node_id, old_status, new_status
            )

        node.status = new_status

        await db.commit()
        await db.refresh(node)

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
                # Create new
                service = Service(
                    node_id=node_id,
                    service_name=service_name,
                    status=status,
                    active_state=svc_data.get("active_state"),
                    sub_state=svc_data.get("sub_state"),
                    main_pid=svc_data.get("main_pid"),
                    memory_bytes=svc_data.get("memory_bytes"),
                    enabled=svc_data.get("enabled", False),
                    description=svc_data.get("description"),
                    last_checked=now,
                )
                db.add(service)

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


reconciler_service = ReconcilerService()
