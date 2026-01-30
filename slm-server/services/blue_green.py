# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Blue-Green Deployment Service

Manages zero-downtime deployments with role borrowing.
Implements the blue-green deployment pattern where:
- Blue = current production node
- Green = standby node temporarily borrowing roles
- Automatic rollback on health failure
- Full purge on role release (clean slate)
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import (
    BlueGreenDeployment,
    BlueGreenStatus,
    Node,
    NodeEvent,
    NodeStatus,
    EventType,
    EventSeverity,
)
from models.schemas import (
    BlueGreenCreate,
    BlueGreenResponse,
    EligibleNodeResponse,
)

logger = logging.getLogger(__name__)

# Minimum resource headroom required for role borrowing (percent)
MIN_CPU_HEADROOM = 30
MIN_MEMORY_HEADROOM = 30

# Health check defaults
DEFAULT_HEALTH_CHECK_INTERVAL = 10
DEFAULT_HEALTH_CHECK_TIMEOUT = 300


class BlueGreenService:
    """Orchestrates blue-green deployments with role borrowing."""

    def __init__(self):
        self.ansible_dir = Path(settings.ansible_dir)
        self._running_deployments: Dict[str, asyncio.Task] = {}
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}  # Post-deployment monitoring

    async def create_deployment(
        self,
        db: AsyncSession,
        data: BlueGreenCreate,
        triggered_by: str,
    ) -> BlueGreenResponse:
        """Create a new blue-green deployment."""
        # Validate blue node exists and is online
        blue_node = await self._get_node(db, data.blue_node_id)
        if not blue_node:
            raise ValueError(f"Blue node not found: {data.blue_node_id}")
        if blue_node.status not in [NodeStatus.ONLINE.value, NodeStatus.DEGRADED.value]:
            raise ValueError(f"Blue node not available: {blue_node.status}")

        # Validate green node exists and is online
        green_node = await self._get_node(db, data.green_node_id)
        if not green_node:
            raise ValueError(f"Green node not found: {data.green_node_id}")
        if green_node.status not in [NodeStatus.ONLINE.value]:
            raise ValueError(f"Green node not available: {green_node.status}")

        # Check green node has capacity for borrowed roles
        if not await self._check_node_capacity(green_node):
            raise ValueError(
                f"Green node {data.green_node_id} lacks capacity for role borrowing"
            )

        # Create deployment record
        bg_deployment_id = str(uuid.uuid4())[:8]
        deployment = BlueGreenDeployment(
            bg_deployment_id=bg_deployment_id,
            blue_node_id=data.blue_node_id,
            blue_roles=data.roles,
            green_node_id=data.green_node_id,
            green_original_roles=green_node.roles or [],
            borrowed_roles=[],
            purge_on_complete=data.purge_on_complete,
            deployment_type=data.deployment_type,
            health_check_url=data.health_check_url,
            health_check_interval=data.health_check_interval,
            health_check_timeout=data.health_check_timeout,
            auto_rollback=data.auto_rollback,
            # Post-deployment monitoring (Issue #726 Phase 3)
            post_deploy_monitor_duration=data.post_deploy_monitor_duration,
            health_failure_threshold=data.health_failure_threshold,
            status=BlueGreenStatus.PENDING.value,
            triggered_by=triggered_by,
        )
        db.add(deployment)
        await db.commit()
        await db.refresh(deployment)

        # Start deployment in background
        task = asyncio.create_task(
            self._execute_deployment(bg_deployment_id)
        )
        self._running_deployments[bg_deployment_id] = task

        logger.info(
            "Blue-green deployment created: %s (blue=%s, green=%s, roles=%s)",
            bg_deployment_id,
            data.blue_node_id,
            data.green_node_id,
            data.roles,
        )

        return BlueGreenResponse.model_validate(deployment)

    async def get_deployment(
        self, db: AsyncSession, bg_deployment_id: str
    ) -> Optional[BlueGreenResponse]:
        """Get a blue-green deployment by ID."""
        result = await db.execute(
            select(BlueGreenDeployment).where(
                BlueGreenDeployment.bg_deployment_id == bg_deployment_id
            )
        )
        deployment = result.scalar_one_or_none()
        if deployment:
            return BlueGreenResponse.model_validate(deployment)
        return None

    async def list_deployments(
        self,
        db: AsyncSession,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[BlueGreenResponse], int]:
        """List blue-green deployments with optional status filter."""
        query = select(BlueGreenDeployment)

        if status:
            query = query.where(BlueGreenDeployment.status == status)

        query = query.order_by(BlueGreenDeployment.created_at.desc())

        # Count total
        count_result = await db.execute(
            select(BlueGreenDeployment.id).where(query.whereclause or True)
        )
        total = len(count_result.all())

        # Paginate
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await db.execute(query)
        deployments = result.scalars().all()

        return (
            [BlueGreenResponse.model_validate(d) for d in deployments],
            total,
        )

    async def switch_traffic(
        self, db: AsyncSession, bg_deployment_id: str
    ) -> Tuple[bool, str]:
        """Manually trigger traffic switch from blue to green."""
        deployment = await self._get_deployment(db, bg_deployment_id)
        if not deployment:
            return False, "Deployment not found"

        if deployment.status != BlueGreenStatus.VERIFYING.value:
            return False, f"Cannot switch in status: {deployment.status}"

        deployment.status = BlueGreenStatus.SWITCHING.value
        deployment.current_step = "Manually triggered traffic switch"
        await db.commit()

        return True, "Traffic switch initiated"

    async def rollback(
        self, db: AsyncSession, bg_deployment_id: str
    ) -> Tuple[bool, str]:
        """Rollback a blue-green deployment."""
        deployment = await self._get_deployment(db, bg_deployment_id)
        if not deployment:
            return False, "Deployment not found"

        rollbackable_statuses = [
            BlueGreenStatus.BORROWING.value,
            BlueGreenStatus.DEPLOYING.value,
            BlueGreenStatus.VERIFYING.value,
            BlueGreenStatus.SWITCHING.value,
            BlueGreenStatus.ACTIVE.value,
            BlueGreenStatus.MONITORING.value,  # Can rollback during monitoring (Issue #726 Phase 3)
        ]

        if deployment.status not in rollbackable_statuses:
            return False, f"Cannot rollback in status: {deployment.status}"

        deployment.status = BlueGreenStatus.ROLLING_BACK.value
        deployment.current_step = "Manual rollback initiated"
        await db.commit()

        # Cancel running deployment task if exists
        if bg_deployment_id in self._running_deployments:
            self._running_deployments[bg_deployment_id].cancel()

        # Cancel running monitoring task if exists (Issue #726 Phase 3)
        if bg_deployment_id in self._monitoring_tasks:
            self._monitoring_tasks[bg_deployment_id].cancel()
            try:
                await self._monitoring_tasks[bg_deployment_id]
            except asyncio.CancelledError:
                pass

        # Start rollback task
        asyncio.create_task(self._execute_rollback(bg_deployment_id))

        return True, "Rollback initiated"

    async def cancel(
        self, db: AsyncSession, bg_deployment_id: str
    ) -> Tuple[bool, str]:
        """Cancel a pending blue-green deployment."""
        deployment = await self._get_deployment(db, bg_deployment_id)
        if not deployment:
            return False, "Deployment not found"

        if deployment.status != BlueGreenStatus.PENDING.value:
            return False, f"Cannot cancel in status: {deployment.status}"

        deployment.status = BlueGreenStatus.FAILED.value
        deployment.error = "Cancelled by user"
        deployment.completed_at = datetime.utcnow()
        await db.commit()

        return True, "Deployment cancelled"

    async def find_eligible_nodes(
        self, db: AsyncSession, roles: List[str]
    ) -> List[EligibleNodeResponse]:
        """Find nodes eligible to borrow the specified roles."""
        result = await db.execute(
            select(Node).where(Node.status == NodeStatus.ONLINE.value)
        )
        nodes = result.scalars().all()

        eligible = []
        for node in nodes:
            # Skip nodes already running these roles
            current_roles = set(node.roles or [])
            if current_roles & set(roles):
                continue

            # Check capacity
            capacity = await self._calculate_capacity(node)
            if capacity >= MIN_CPU_HEADROOM:
                eligible.append(
                    EligibleNodeResponse(
                        node_id=node.node_id,
                        hostname=node.hostname,
                        ip_address=node.ip_address,
                        current_roles=node.roles or [],
                        available_capacity=capacity,
                        status=node.status,
                    )
                )

        # Sort by available capacity (highest first)
        eligible.sort(key=lambda x: x.available_capacity, reverse=True)
        return eligible

    async def purge_roles(
        self, db: AsyncSession, node_id: str, roles: List[str], force: bool = False
    ) -> Tuple[bool, str, List[str]]:
        """Purge specified roles from a node (clean slate)."""
        node = await self._get_node(db, node_id)
        if not node:
            return False, "Node not found", []

        logger.info("Purging roles %s from node %s", roles, node_id)

        # Stop services first
        stopped_services = []
        for role in roles:
            services = self._get_role_services(role)
            for service in services:
                success = await self._stop_service_via_ssh(
                    node.ip_address,
                    node.ssh_user or "autobot",
                    node.ssh_port or 22,
                    service,
                )
                if success:
                    stopped_services.append(service)

        # Execute purge playbook
        success = await self._execute_purge_playbook(
            node.ip_address,
            node.ssh_user or "autobot",
            node.ssh_port or 22,
            roles,
        )

        if success:
            # Update node roles
            current_roles = set(node.roles or [])
            node.roles = list(current_roles - set(roles))
            await db.commit()

            return True, f"Purged roles: {roles}", stopped_services
        else:
            return False, "Purge playbook failed", stopped_services

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _get_node(self, db: AsyncSession, node_id: str) -> Optional[Node]:
        """Get a node by ID."""
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        return result.scalar_one_or_none()

    async def _get_deployment(
        self, db: AsyncSession, bg_deployment_id: str
    ) -> Optional[BlueGreenDeployment]:
        """Get a deployment by ID."""
        result = await db.execute(
            select(BlueGreenDeployment).where(
                BlueGreenDeployment.bg_deployment_id == bg_deployment_id
            )
        )
        return result.scalar_one_or_none()

    async def _check_node_capacity(self, node: Node) -> bool:
        """Check if a node has capacity for role borrowing."""
        cpu_headroom = 100 - (node.cpu_percent or 0)
        memory_headroom = 100 - (node.memory_percent or 0)
        return cpu_headroom >= MIN_CPU_HEADROOM and memory_headroom >= MIN_MEMORY_HEADROOM

    async def _calculate_capacity(self, node: Node) -> float:
        """Calculate available capacity (average of CPU and memory headroom)."""
        cpu_headroom = 100 - (node.cpu_percent or 0)
        memory_headroom = 100 - (node.memory_percent or 0)
        return (cpu_headroom + memory_headroom) / 2

    def _get_role_services(self, role: str) -> List[str]:
        """Get systemd services associated with a role."""
        role_service_map = {
            "slm-agent": ["slm-agent", "autobot-agent"],
            "redis": ["redis-server", "redis"],
            "backend": ["autobot-backend", "autobot"],
            "frontend": ["autobot-frontend"],
            "npu-worker": ["autobot-npu-worker"],
            "browser-automation": ["playwright-server", "browser-automation"],
            "monitoring": ["prometheus", "grafana-server", "node_exporter"],
            "ai-stack": ["autobot-ai-stack"],
            "llm": ["ollama"],
        }
        return role_service_map.get(role, [role])

    async def _execute_deployment(self, bg_deployment_id: str) -> None:
        """Execute the blue-green deployment workflow."""
        from services.database import db_service

        logger.info("Starting blue-green deployment: %s", bg_deployment_id)

        async with db_service.session() as db:
            deployment = await self._get_deployment(db, bg_deployment_id)
            if not deployment:
                logger.error("Deployment not found: %s", bg_deployment_id)
                return

            try:
                # Phase 1: Start deployment
                deployment.status = BlueGreenStatus.BORROWING.value
                deployment.started_at = datetime.utcnow()
                deployment.progress_percent = 10
                deployment.current_step = "Borrowing roles to green node"
                await db.commit()

                await self._broadcast_deployment_event(
                    bg_deployment_id, "started",
                    f"Blue-green deployment started for roles: {deployment.blue_roles}"
                )

                # Phase 2: Deploy roles to green node
                deployment.status = BlueGreenStatus.DEPLOYING.value
                deployment.progress_percent = 30
                deployment.current_step = "Deploying roles to green node"
                await db.commit()

                green_node = await self._get_node(db, deployment.green_node_id)
                success = await self._deploy_roles_to_node(
                    green_node, deployment.blue_roles
                )

                if not success:
                    raise RuntimeError("Failed to deploy roles to green node")

                deployment.borrowed_roles = deployment.blue_roles
                deployment.progress_percent = 50
                await db.commit()

                # Phase 3: Health verification
                deployment.status = BlueGreenStatus.VERIFYING.value
                deployment.progress_percent = 60
                deployment.current_step = "Verifying green node health"
                await db.commit()

                healthy = await self._verify_health(
                    deployment.green_node_id,
                    deployment.health_check_url,
                    deployment.health_check_interval,
                    deployment.health_check_timeout,
                )

                if not healthy:
                    if deployment.auto_rollback:
                        raise RuntimeError("Health verification failed - auto-rollback")
                    else:
                        deployment.status = BlueGreenStatus.FAILED.value
                        deployment.error = "Health verification failed"
                        deployment.completed_at = datetime.utcnow()
                        await db.commit()
                        return

                deployment.progress_percent = 70
                await db.commit()

                # Phase 4: Switch traffic
                deployment.status = BlueGreenStatus.SWITCHING.value
                deployment.progress_percent = 80
                deployment.current_step = "Switching traffic to green node"
                await db.commit()

                # Stop services on blue node
                blue_node = await self._get_node(db, deployment.blue_node_id)
                await self._stop_role_services(blue_node, deployment.blue_roles)

                # Update node roles
                blue_node.roles = list(
                    set(blue_node.roles or []) - set(deployment.blue_roles)
                )
                green_node.roles = list(
                    set(green_node.roles or []) | set(deployment.blue_roles)
                )
                deployment.switched_at = datetime.utcnow()
                await db.commit()

                # Phase 5: Active - Green is now live
                deployment.status = BlueGreenStatus.ACTIVE.value
                deployment.progress_percent = 90
                deployment.current_step = "Green node is now live"
                await db.commit()

                await self._broadcast_deployment_event(
                    bg_deployment_id, "active",
                    "Traffic switched to green node - now live"
                )

                # Phase 6: Post-deployment health monitoring (Issue #726 Phase 3)
                if deployment.post_deploy_monitor_duration > 0 and deployment.auto_rollback:
                    deployment.status = BlueGreenStatus.MONITORING.value
                    deployment.monitoring_started_at = datetime.utcnow()
                    deployment.current_step = (
                        f"Post-deployment monitoring ({deployment.post_deploy_monitor_duration}s, "
                        f"threshold: {deployment.health_failure_threshold} failures)"
                    )
                    await db.commit()

                    await self._broadcast_deployment_event(
                        bg_deployment_id, "monitoring_started",
                        f"Post-deployment health monitoring started for {deployment.post_deploy_monitor_duration}s"
                    )

                    # Start monitoring task (non-blocking)
                    monitoring_task = asyncio.create_task(
                        self._monitor_deployment_health(bg_deployment_id)
                    )
                    self._monitoring_tasks[bg_deployment_id] = monitoring_task

                    logger.info(
                        "Started post-deployment monitoring: %s (duration=%ds, threshold=%d)",
                        bg_deployment_id,
                        deployment.post_deploy_monitor_duration,
                        deployment.health_failure_threshold,
                    )
                    return  # Exit - monitoring task will handle completion

                # No monitoring configured - proceed to completion
                # Optional: Purge roles from blue node
                if deployment.purge_on_complete:
                    deployment.current_step = "Purging roles from blue node"
                    await self.purge_roles(
                        db, deployment.blue_node_id, deployment.blue_roles
                    )

                deployment.status = BlueGreenStatus.COMPLETED.value
                deployment.progress_percent = 100
                deployment.current_step = "Deployment completed successfully"
                deployment.completed_at = datetime.utcnow()
                await db.commit()

                await self._broadcast_deployment_event(
                    bg_deployment_id, "completed",
                    "Blue-green deployment completed successfully"
                )

                logger.info("Blue-green deployment completed: %s", bg_deployment_id)

            except asyncio.CancelledError:
                deployment.status = BlueGreenStatus.ROLLING_BACK.value
                deployment.error = "Deployment cancelled"
                await db.commit()
                await self._execute_rollback(bg_deployment_id)

            except Exception as e:
                logger.error(
                    "Blue-green deployment failed: %s - %s", bg_deployment_id, e
                )
                deployment.error = str(e)
                await db.commit()

                if deployment.auto_rollback:
                    await self._execute_rollback(bg_deployment_id)
                else:
                    deployment.status = BlueGreenStatus.FAILED.value
                    deployment.completed_at = datetime.utcnow()
                    await db.commit()

    async def _execute_rollback(self, bg_deployment_id: str) -> None:
        """Execute rollback for a blue-green deployment."""
        from services.database import db_service

        logger.info("Executing rollback for deployment: %s", bg_deployment_id)

        async with db_service.session() as db:
            deployment = await self._get_deployment(db, bg_deployment_id)
            if not deployment:
                return

            try:
                deployment.status = BlueGreenStatus.ROLLING_BACK.value
                deployment.current_step = "Rolling back to blue node"
                await db.commit()

                # Stop services on green node
                green_node = await self._get_node(db, deployment.green_node_id)
                await self._stop_role_services(green_node, deployment.borrowed_roles)

                # Restore services on blue node
                blue_node = await self._get_node(db, deployment.blue_node_id)
                await self._deploy_roles_to_node(blue_node, deployment.blue_roles)

                # Restore node roles
                blue_node.roles = list(
                    set(blue_node.roles or []) | set(deployment.blue_roles)
                )
                green_node.roles = deployment.green_original_roles
                await db.commit()

                # Purge borrowed roles from green
                if deployment.borrowed_roles:
                    await self.purge_roles(
                        db, deployment.green_node_id, deployment.borrowed_roles
                    )

                deployment.status = BlueGreenStatus.ROLLED_BACK.value
                deployment.rollback_at = datetime.utcnow()
                deployment.completed_at = datetime.utcnow()
                deployment.current_step = "Rollback completed"
                await db.commit()

                await self._broadcast_deployment_event(
                    bg_deployment_id, "rolled_back",
                    "Blue-green deployment rolled back successfully"
                )

                logger.info("Rollback completed for deployment: %s", bg_deployment_id)

            except Exception as e:
                logger.error("Rollback failed for %s: %s", bg_deployment_id, e)
                deployment.status = BlueGreenStatus.FAILED.value
                deployment.error = f"Rollback failed: {e}"
                deployment.completed_at = datetime.utcnow()
                await db.commit()

    async def _monitor_deployment_health(self, bg_deployment_id: str) -> None:
        """Post-deployment health monitoring with automatic rollback (Issue #726 Phase 3).

        Monitors green node health after deployment for the configured duration.
        Triggers automatic rollback if health failures exceed threshold.
        """
        from services.database import db_service

        logger.info("Starting health monitoring for deployment: %s", bg_deployment_id)

        try:
            async with db_service.session() as db:
                deployment = await self._get_deployment(db, bg_deployment_id)
                if not deployment:
                    logger.error("Deployment not found for monitoring: %s", bg_deployment_id)
                    return

                # Calculate monitoring deadline
                monitoring_start = deployment.monitoring_started_at or datetime.utcnow()
                monitoring_deadline = monitoring_start + timedelta(
                    seconds=deployment.post_deploy_monitor_duration
                )
                check_interval = deployment.health_check_interval
                failure_threshold = deployment.health_failure_threshold

                consecutive_failures = 0
                total_checks = 0
                successful_checks = 0

                while datetime.utcnow() < monitoring_deadline:
                    # Check if deployment was cancelled or rolled back externally
                    async with db_service.session() as check_db:
                        current_deployment = await self._get_deployment(check_db, bg_deployment_id)
                        if not current_deployment:
                            return
                        if current_deployment.status not in [
                            BlueGreenStatus.MONITORING.value,
                            BlueGreenStatus.ACTIVE.value,
                        ]:
                            logger.info(
                                "Monitoring stopped - deployment status changed: %s -> %s",
                                bg_deployment_id,
                                current_deployment.status,
                            )
                            return

                    # Perform health check
                    healthy = await self._verify_health(
                        deployment.green_node_id,
                        deployment.health_check_url,
                        check_interval,
                        check_interval * 2,  # Short timeout for monitoring checks
                    )

                    total_checks += 1

                    if healthy:
                        consecutive_failures = 0
                        successful_checks += 1
                        logger.debug(
                            "Health check passed for %s (check #%d)",
                            bg_deployment_id,
                            total_checks,
                        )
                    else:
                        consecutive_failures += 1
                        logger.warning(
                            "Health check failed for %s (failures: %d/%d)",
                            bg_deployment_id,
                            consecutive_failures,
                            failure_threshold,
                        )

                        # Update failure count in database
                        async with db_service.session() as update_db:
                            dep = await self._get_deployment(update_db, bg_deployment_id)
                            if dep:
                                dep.health_failures = consecutive_failures
                                dep.current_step = (
                                    f"Health monitoring: {consecutive_failures}/{failure_threshold} "
                                    f"failures, {successful_checks}/{total_checks} checks passed"
                                )
                                await update_db.commit()

                        # Broadcast health failure event
                        await self._broadcast_deployment_event(
                            bg_deployment_id,
                            "health_check_failed",
                            f"Health check failed ({consecutive_failures}/{failure_threshold} failures)",
                        )

                        # Check if threshold exceeded
                        if consecutive_failures >= failure_threshold:
                            logger.error(
                                "Health failure threshold exceeded for %s - triggering rollback",
                                bg_deployment_id,
                            )

                            async with db_service.session() as rollback_db:
                                dep = await self._get_deployment(rollback_db, bg_deployment_id)
                                if dep:
                                    dep.error = (
                                        f"Automatic rollback triggered: {consecutive_failures} "
                                        f"consecutive health failures exceeded threshold of {failure_threshold}"
                                    )
                                    dep.status = BlueGreenStatus.ROLLING_BACK.value
                                    await rollback_db.commit()

                            await self._broadcast_deployment_event(
                                bg_deployment_id,
                                "auto_rollback_triggered",
                                f"Automatic rollback triggered after {consecutive_failures} consecutive failures",
                            )

                            # Execute rollback
                            await self._execute_rollback(bg_deployment_id)
                            return

                    # Wait before next check
                    await asyncio.sleep(check_interval)

                # Monitoring period completed successfully
                logger.info(
                    "Health monitoring completed for %s (%d/%d checks passed)",
                    bg_deployment_id,
                    successful_checks,
                    total_checks,
                )

                async with db_service.session() as complete_db:
                    deployment = await self._get_deployment(complete_db, bg_deployment_id)
                    if not deployment:
                        return

                    # Check status - only complete if still monitoring
                    if deployment.status != BlueGreenStatus.MONITORING.value:
                        return

                    # Optional: Purge roles from blue node
                    if deployment.purge_on_complete:
                        deployment.current_step = "Purging roles from blue node"
                        await complete_db.commit()
                        await self.purge_roles(
                            complete_db, deployment.blue_node_id, deployment.blue_roles
                        )

                    deployment.status = BlueGreenStatus.COMPLETED.value
                    deployment.progress_percent = 100
                    deployment.current_step = (
                        f"Deployment completed - monitoring passed "
                        f"({successful_checks}/{total_checks} health checks)"
                    )
                    deployment.completed_at = datetime.utcnow()
                    await complete_db.commit()

                await self._broadcast_deployment_event(
                    bg_deployment_id,
                    "completed",
                    f"Blue-green deployment completed after successful monitoring ({successful_checks}/{total_checks} checks)",
                )

        except asyncio.CancelledError:
            logger.info("Health monitoring cancelled for %s", bg_deployment_id)
            raise

        except Exception as e:
            logger.error(
                "Health monitoring error for %s: %s", bg_deployment_id, e
            )

            # Mark as failed
            async with db_service.session() as error_db:
                deployment = await self._get_deployment(error_db, bg_deployment_id)
                if deployment and deployment.status == BlueGreenStatus.MONITORING.value:
                    deployment.status = BlueGreenStatus.FAILED.value
                    deployment.error = f"Health monitoring error: {e}"
                    deployment.completed_at = datetime.utcnow()
                    await error_db.commit()

        finally:
            # Cleanup monitoring task reference
            if bg_deployment_id in self._monitoring_tasks:
                del self._monitoring_tasks[bg_deployment_id]

    async def stop_monitoring(self, bg_deployment_id: str) -> bool:
        """Stop post-deployment health monitoring for a deployment."""
        if bg_deployment_id in self._monitoring_tasks:
            self._monitoring_tasks[bg_deployment_id].cancel()
            try:
                await self._monitoring_tasks[bg_deployment_id]
            except asyncio.CancelledError:
                pass
            return True
        return False

    async def _deploy_roles_to_node(
        self, node: Node, roles: List[str]
    ) -> bool:
        """Deploy roles to a node using Ansible."""
        try:
            playbook_path = self.ansible_dir / "deploy.yml"
            if not playbook_path.exists():
                logger.error("Deploy playbook not found: %s", playbook_path)
                return False

            roles_str = ",".join(roles)
            cmd = [
                "ansible-playbook",
                str(playbook_path),
                "-i", f"{node.ip_address},",
                "-e", f"target_roles={roles_str}",
                "-e", f"target_host={node.ip_address}",
                "-e", f"ansible_user={node.ssh_user or 'autobot'}",
                "-e", f"ansible_port={node.ssh_port or 22}",
                "-e", "ansible_ssh_common_args='-o StrictHostKeyChecking=no'",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.ansible_dir),
            )

            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=600.0
            )

            if process.returncode != 0:
                logger.error(
                    "Ansible deployment failed: %s",
                    stdout.decode("utf-8", errors="replace"),
                )
                return False

            logger.info("Deployed roles %s to node %s", roles, node.node_id)
            return True

        except Exception as e:
            logger.error("Deployment error: %s", e)
            return False

    async def _stop_role_services(self, node: Node, roles: List[str]) -> None:
        """Stop all services associated with roles on a node."""
        for role in roles:
            services = self._get_role_services(role)
            for service in services:
                await self._stop_service_via_ssh(
                    node.ip_address,
                    node.ssh_user or "autobot",
                    node.ssh_port or 22,
                    service,
                )

    async def _stop_service_via_ssh(
        self, ip_address: str, ssh_user: str, ssh_port: int, service: str
    ) -> bool:
        """Stop a systemd service via SSH."""
        try:
            cmd = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=10",
                "-o", "BatchMode=yes",
                "-p", str(ssh_port),
                f"{ssh_user}@{ip_address}",
                f"sudo systemctl stop {service}",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await asyncio.wait_for(process.communicate(), timeout=30.0)
            return process.returncode == 0

        except Exception as e:
            logger.warning("Failed to stop service %s: %s", service, e)
            return False

    async def _verify_health(
        self,
        node_id: str,
        health_url: Optional[str],
        interval: int,
        timeout: int,
    ) -> bool:
        """Verify node health after deployment."""
        from services.database import db_service

        start_time = datetime.utcnow()
        deadline = start_time + timedelta(seconds=timeout)

        while datetime.utcnow() < deadline:
            # Check node status from database
            async with db_service.session() as db:
                node = await self._get_node(db, node_id)
                if not node:
                    return False

                if node.status == NodeStatus.ONLINE.value:
                    # If custom health URL provided, check it
                    if health_url:
                        if await self._check_health_url(health_url):
                            return True
                    else:
                        return True

            await asyncio.sleep(interval)

        return False

    async def _check_health_url(self, url: str) -> bool:
        """Check a health endpoint URL."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception:
            return False

    async def _execute_purge_playbook(
        self,
        ip_address: str,
        ssh_user: str,
        ssh_port: int,
        roles: List[str],
    ) -> bool:
        """Execute Ansible playbook to purge roles."""
        try:
            playbook_path = self.ansible_dir / "purge.yml"

            # Create purge playbook if it doesn't exist
            if not playbook_path.exists():
                await self._create_purge_playbook(playbook_path)

            roles_str = ",".join(roles)
            cmd = [
                "ansible-playbook",
                str(playbook_path),
                "-i", f"{ip_address},",
                "-e", f"purge_roles={roles_str}",
                "-e", f"ansible_user={ssh_user}",
                "-e", f"ansible_port={ssh_port}",
                "-e", "ansible_ssh_common_args='-o StrictHostKeyChecking=no'",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.ansible_dir),
            )

            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=300.0
            )

            if process.returncode != 0:
                logger.error(
                    "Purge playbook failed: %s",
                    stdout.decode("utf-8", errors="replace"),
                )
                return False

            return True

        except Exception as e:
            logger.error("Purge error: %s", e)
            return False

    async def _create_purge_playbook(self, path: Path) -> None:
        """Create the role purge playbook."""
        playbook_content = """# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Role Purge Playbook - Clean slate for role release
---
- name: Purge Roles from Node
  hosts: all
  become: true
  gather_facts: false

  vars:
    purge_roles: ""
    role_service_map:
      slm-agent:
        - slm-agent
        - autobot-agent
      redis:
        - redis-server
        - redis
      backend:
        - autobot-backend
        - autobot
      frontend:
        - autobot-frontend
      npu-worker:
        - autobot-npu-worker
      browser-automation:
        - playwright-server
        - browser-automation
      monitoring:
        - prometheus
        - grafana-server
        - node_exporter
      ai-stack:
        - autobot-ai-stack
      llm:
        - ollama

    role_data_dirs:
      redis:
        - /var/lib/redis
        - /etc/redis
      backend:
        - /opt/autobot/backend
        - /var/log/autobot
      frontend:
        - /opt/autobot/frontend
      monitoring:
        - /var/lib/prometheus
        - /var/lib/grafana
        - /etc/prometheus
        - /etc/grafana

  tasks:
    - name: Parse purge roles
      ansible.builtin.set_fact:
        role_list: "{{ purge_roles.split(',') | map('trim') | list }}"

    - name: Stop and disable services for each role
      ansible.builtin.systemd:
        name: "{{ item.1 }}"
        state: stopped
        enabled: false
      loop: "{{ role_list | product(role_service_map[item] | default([])) | list }}"
      when: item.0 in role_service_map
      ignore_errors: true
      loop_control:
        label: "{{ item.1 | default(item) }}"

    - name: Remove service files
      ansible.builtin.file:
        path: "/etc/systemd/system/{{ item.1 }}.service"
        state: absent
      loop: "{{ role_list | product(role_service_map[item] | default([])) | list }}"
      when: item.0 in role_service_map
      ignore_errors: true
      loop_control:
        label: "{{ item.1 | default(item) }}"

    - name: Remove role data directories
      ansible.builtin.file:
        path: "{{ item.1 }}"
        state: absent
      loop: "{{ role_list | product(role_data_dirs[item] | default([])) | list }}"
      when: item.0 in role_data_dirs
      ignore_errors: true
      loop_control:
        label: "{{ item.1 | default(item) }}"

    - name: Reload systemd daemon
      ansible.builtin.systemd:
        daemon_reload: true

    - name: Display purge summary
      ansible.builtin.debug:
        msg: "Purged roles: {{ role_list | join(', ') }}"
"""
        path.write_text(playbook_content, encoding="utf-8")
        logger.info("Created purge playbook: %s", path)

    async def _broadcast_deployment_event(
        self, bg_deployment_id: str, event_type: str, message: str
    ) -> None:
        """Broadcast deployment event via WebSocket."""
        try:
            from api.websocket import ws_manager
            await ws_manager.broadcast(
                "events:global",
                {
                    "type": "blue_green_event",
                    "bg_deployment_id": bg_deployment_id,
                    "event_type": event_type,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            logger.debug("Failed to broadcast deployment event: %s", e)


blue_green_service = BlueGreenService()
