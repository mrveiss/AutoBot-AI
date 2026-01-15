# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Reconciliation Loop

Background service that monitors node health and triggers remediation.

Runs every 30 seconds:
1. Collect state from database
2. Check heartbeat ages
3. Detect drift (ONLINE but stale heartbeat → DEGRADED)
4. Execute conservative remediation
5. Log state transitions and notify via WebSocket
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from backend.models.infrastructure import NodeState, SLMNode
from backend.services.slm.db_service import SLMDatabaseService
from backend.services.slm.state_machine import InvalidStateTransition
from backend.services.slm.remediator import (
    SLMRemediator,
    RemediationResult,
    get_remediator,
)

logger = logging.getLogger(__name__)


# Thresholds (seconds)
HEARTBEAT_STALE_THRESHOLD = 60  # Mark degraded if no heartbeat in 60s
HEARTBEAT_CRITICAL_THRESHOLD = 300  # Mark error if no heartbeat in 5min
REMEDIATION_RETRY_LIMIT = 3  # Max remediation attempts before ERROR


class SLMReconciler:
    """
    Reconciliation loop for SLM node health monitoring.

    Responsibilities:
    - Monitor heartbeat freshness
    - Detect state drift
    - Trigger conservative remediation (service restarts)
    - Log state transitions
    - Notify via WebSocket callbacks
    """

    def __init__(
        self,
        db_service: Optional[SLMDatabaseService] = None,
        remediator: Optional[SLMRemediator] = None,
        interval: int = 30,
        on_state_change: Optional[Callable[[str, str, str], None]] = None,
        on_alert: Optional[Callable[[str, str, Dict], None]] = None,
    ):
        """
        Initialize reconciler.

        Args:
            db_service: Database service instance
            remediator: Remediator service instance
            interval: Reconciliation interval in seconds (default 30)
            on_state_change: Callback for state changes (node_id, old, new)
            on_alert: Callback for alerts (node_id, level, details)
        """
        self.db = db_service or SLMDatabaseService()
        self.remediator = remediator or get_remediator()
        self.interval = interval
        self.on_state_change = on_state_change
        self.on_alert = on_alert

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_run: Optional[datetime] = None
        self._run_count = 0

        logger.info(
            "SLM Reconciler initialized (interval=%ds, stale=%ds, critical=%ds)",
            interval, HEARTBEAT_STALE_THRESHOLD, HEARTBEAT_CRITICAL_THRESHOLD,
        )

    @property
    def is_running(self) -> bool:
        """Check if reconciler is running."""
        return self._running

    @property
    def stats(self) -> Dict:
        """Get reconciler statistics."""
        return {
            "running": self._running,
            "interval": self.interval,
            "run_count": self._run_count,
            "last_run": self._last_run.isoformat() if self._last_run else None,
        }

    async def start(self):
        """Start the reconciliation loop."""
        if self._running:
            logger.warning("Reconciler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("SLM Reconciler started")

    async def stop(self):
        """Stop the reconciliation loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SLM Reconciler stopped")

    async def _loop(self):
        """Main reconciliation loop."""
        while self._running:
            try:
                await self._reconcile()
                self._run_count += 1
                self._last_run = datetime.utcnow()
            except Exception as e:
                logger.exception("Reconciliation error: %s", e)

            await asyncio.sleep(self.interval)

    async def _reconcile(self):
        """Execute one reconciliation cycle."""
        nodes = self.db.get_all_nodes()
        now = datetime.utcnow()

        for node in nodes:
            await self._check_node(node, now)

    async def _check_node(self, node: SLMNode, now: datetime):
        """Check a single node's health state."""
        # Skip nodes in maintenance or terminal states
        if self._is_maintenance_state(node.state):
            return

        # Skip nodes that haven't enrolled yet
        if node.state in (NodeState.UNKNOWN.value, NodeState.PENDING.value,
                          NodeState.ENROLLING.value):
            return

        # Check heartbeat freshness
        heartbeat_age = self._get_heartbeat_age(node, now)

        if heartbeat_age is None:
            # Never received heartbeat - if ONLINE, that's concerning
            if node.state == NodeState.ONLINE.value:
                await self._mark_degraded(
                    node, "No heartbeat ever received"
                )
            return

        # Evaluate based on thresholds
        if heartbeat_age > HEARTBEAT_CRITICAL_THRESHOLD:
            await self._handle_critical_heartbeat(node, heartbeat_age)
        elif heartbeat_age > HEARTBEAT_STALE_THRESHOLD:
            await self._handle_stale_heartbeat(node, heartbeat_age)
        else:
            # Heartbeat is fresh - recover if degraded
            await self._handle_healthy_heartbeat(node)

    def _is_maintenance_state(self, state: str) -> bool:
        """Check if state is a maintenance state."""
        maintenance_states = {
            NodeState.MAINTENANCE_DRAINING.value,
            NodeState.MAINTENANCE_PLANNED.value,
            NodeState.MAINTENANCE_IMMEDIATE.value,
            NodeState.MAINTENANCE_OFFLINE.value,
            NodeState.MAINTENANCE_RECOVERING.value,
        }
        return state in maintenance_states

    def _get_heartbeat_age(self, node: SLMNode, now: datetime) -> Optional[float]:
        """Get heartbeat age in seconds, or None if never received."""
        if not node.last_heartbeat:
            return None
        return (now - node.last_heartbeat).total_seconds()

    async def _handle_stale_heartbeat(self, node: SLMNode, age: float):
        """Handle stale heartbeat (60-300s)."""
        if node.state == NodeState.ONLINE.value:
            await self._mark_degraded(
                node, f"Heartbeat stale ({age:.0f}s old)"
            )
        elif node.state == NodeState.DEGRADED.value:
            # Already degraded, check if we should attempt remediation
            if node.consecutive_failures < REMEDIATION_RETRY_LIMIT:
                await self._attempt_remediation(node)

    async def _handle_critical_heartbeat(self, node: SLMNode, age: float):
        """Handle critical heartbeat (>300s)."""
        if node.state == NodeState.DEGRADED.value:
            # Degraded for too long, mark as error
            if node.consecutive_failures >= REMEDIATION_RETRY_LIMIT:
                await self._mark_error(
                    node, f"Remediation failed {REMEDIATION_RETRY_LIMIT}x, heartbeat {age:.0f}s old"
                )
        elif node.state == NodeState.ONLINE.value:
            # Directly to degraded, then check on next cycle
            await self._mark_degraded(
                node, f"Heartbeat critical ({age:.0f}s old)"
            )

    async def _handle_healthy_heartbeat(self, node: SLMNode):
        """Handle fresh heartbeat - recover if degraded."""
        if node.state == NodeState.DEGRADED.value:
            await self._mark_online(node, "Heartbeat recovered")
        elif node.state == NodeState.ERROR.value:
            # Don't auto-recover from ERROR - needs human intervention
            pass

    async def _mark_degraded(self, node: SLMNode, reason: str):
        """Transition node to DEGRADED state."""
        try:
            old_state = node.state
            self.db.update_node_state(
                node_id=node.id,
                new_state=NodeState.DEGRADED,
                trigger="reconciler",
                details={"reason": reason},
            )

            logger.warning("Node %s DEGRADED: %s", node.name, reason)
            await self._notify_state_change(node.id, old_state, NodeState.DEGRADED.value)
            await self._send_alert(node.id, "warning", {
                "message": f"Node degraded: {reason}",
                "node_name": node.name,
            })

        except InvalidStateTransition as e:
            logger.debug("Cannot transition %s to DEGRADED: %s", node.name, e)

    async def _mark_online(self, node: SLMNode, reason: str):
        """Transition node to ONLINE state."""
        try:
            old_state = node.state
            self.db.update_node_state(
                node_id=node.id,
                new_state=NodeState.ONLINE,
                trigger="reconciler",
                details={"reason": reason},
            )

            logger.info("Node %s ONLINE: %s", node.name, reason)
            await self._notify_state_change(node.id, old_state, NodeState.ONLINE.value)

        except InvalidStateTransition as e:
            logger.debug("Cannot transition %s to ONLINE: %s", node.name, e)

    async def _mark_error(self, node: SLMNode, reason: str):
        """Transition node to ERROR state."""
        try:
            old_state = node.state
            self.db.update_node_state(
                node_id=node.id,
                new_state=NodeState.ERROR,
                trigger="reconciler",
                details={"reason": reason},
            )

            logger.error("Node %s ERROR: %s", node.name, reason)
            await self._notify_state_change(node.id, old_state, NodeState.ERROR.value)
            await self._send_alert(node.id, "critical", {
                "message": f"Node error: {reason}",
                "node_name": node.name,
                "requires_human": True,
            })

        except InvalidStateTransition as e:
            logger.debug("Cannot transition %s to ERROR: %s", node.name, e)

    async def _attempt_remediation(self, node: SLMNode):
        """
        Attempt conservative remediation (service restart).

        Uses the SLMRemediator to execute SSH service restarts.
        """
        self.db.increment_failure_count(node.id)
        attempt_num = node.consecutive_failures + 1

        logger.info(
            "Attempting remediation for %s (attempt %d/%d)",
            node.name, attempt_num, REMEDIATION_RETRY_LIMIT,
        )

        # Get services for this node's role
        services = await self._get_node_services(node)

        if not services:
            logger.warning(
                "No services defined for node %s role=%s, skipping remediation",
                node.name, node.current_role,
            )
            await self._send_alert(node.id, "warning", {
                "message": f"Remediation skipped - no services defined",
                "node_name": node.name,
                "role": node.current_role,
            })
            return

        # Attempt to restart services
        attempts = await self.remediator.restart_all_services(
            node_id=node.id,
            node_name=node.name,
            host=node.ip_address,
            services=services,
            ssh_user=node.ssh_user,
            ssh_port=node.ssh_port,
        )

        # Check results
        all_success = all(a.result == RemediationResult.SUCCESS for a in attempts)
        any_unreachable = any(a.result == RemediationResult.UNREACHABLE for a in attempts)

        if all_success:
            await self._send_alert(node.id, "info", {
                "message": f"Remediation attempt {attempt_num} successful",
                "node_name": node.name,
                "services_restarted": services,
            })
        elif any_unreachable:
            await self._send_alert(node.id, "warning", {
                "message": f"Node unreachable during remediation attempt {attempt_num}",
                "node_name": node.name,
                "action": "node_unreachable",
            })
        else:
            failed = [a for a in attempts if a.result != RemediationResult.SUCCESS]
            await self._send_alert(node.id, "warning", {
                "message": f"Remediation attempt {attempt_num} failed",
                "node_name": node.name,
                "failed_services": [a.details.get("service") for a in failed if a.details],
            })

    async def _get_node_services(self, node: SLMNode) -> List[str]:
        """Get the list of services for a node's current role."""
        if not node.current_role:
            return []

        role = self.db.get_role_by_name(node.current_role)
        if not role:
            return []

        return role.services or []

    async def _notify_state_change(self, node_id: str, old_state: str, new_state: str):
        """Notify state change via callback."""
        if self.on_state_change:
            try:
                self.on_state_change(node_id, old_state, new_state)
            except Exception as e:
                logger.warning("State change callback error: %s", e)

    async def _send_alert(self, node_id: str, level: str, details: Dict):
        """Send alert via callback."""
        if self.on_alert:
            try:
                self.on_alert(node_id, level, details)
            except Exception as e:
                logger.warning("Alert callback error: %s", e)


# Singleton instance for app lifecycle
_reconciler: Optional[SLMReconciler] = None


def get_reconciler() -> SLMReconciler:
    """Get or create the singleton reconciler instance."""
    global _reconciler
    if _reconciler is None:
        _reconciler = SLMReconciler()
    return _reconciler


async def start_reconciler():
    """Start the global reconciler."""
    reconciler = get_reconciler()
    await reconciler.start()


async def stop_reconciler():
    """Stop the global reconciler."""
    global _reconciler
    if _reconciler:
        await _reconciler.stop()
        _reconciler = None
