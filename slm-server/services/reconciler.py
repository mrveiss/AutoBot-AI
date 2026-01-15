# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Reconciler Service

Monitors node health and manages role state reconciliation.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import Node, NodeStatus, Setting

logger = logging.getLogger(__name__)


class ReconcilerService:
    """Background service for health monitoring and reconciliation."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._heartbeat_timeout = settings.heartbeat_timeout_seconds

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
                await self._reconcile_roles()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Reconciler error: %s", e)

            await asyncio.sleep(settings.reconcile_interval_seconds)

    async def _check_node_health(self) -> None:
        """Check node health based on heartbeats."""
        from services.database import db_service

        async with db_service.session() as db:
            timeout_setting = await db.execute(
                select(Setting).where(Setting.key == "heartbeat_timeout")
            )
            setting = timeout_setting.scalar_one_or_none()
            if setting and setting.value:
                self._heartbeat_timeout = int(setting.value)

            cutoff = datetime.utcnow() - timedelta(seconds=self._heartbeat_timeout)

            await db.execute(
                update(Node)
                .where(
                    Node.status.in_([NodeStatus.ONLINE.value, NodeStatus.DEGRADED.value])
                )
                .where(Node.last_heartbeat < cutoff)
                .values(status=NodeStatus.OFFLINE.value)
            )

            await db.commit()

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
        result = await db.execute(select(Node).where(Node.node_id == node_id))
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

        new_status = self._calculate_node_status(cpu_percent, memory_percent, disk_percent)
        node.status = new_status

        await db.commit()
        await db.refresh(node)

        return node

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
