# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Deployment Orchestrator

Orchestrates deployments across the node fleet with multiple strategies:
- Sequential: One node at a time with health checks
- Blue-green: Zero-downtime with role borrowing
- Maintenance window: Scheduled downtime operations

Design principles:
- Health-first: Always verify health before proceeding
- Automatic rollback: Revert on consecutive failures
- Observable: WebSocket events for real-time progress
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional
from uuid import uuid4

from backend.models.infrastructure import (
    DeploymentStrategy as DeploymentStrategyType,
    NodeState,
    SLMDeployment,
    SLMNode,
)
from backend.services.slm.db_service import SLMDatabaseService
from backend.services.slm.remediator import SSHExecutor

logger = logging.getLogger(__name__)


class DeploymentStatus(str, Enum):
    """Deployment status values."""
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class DeploymentStepType(str, Enum):
    """Types of deployment steps."""
    DRAIN = "drain"
    HEALTH_CHECK = "health_check"
    EXECUTE_PLAYBOOK = "execute_playbook"
    VERIFY = "verify"
    RECOVER = "recover"
    ROLLBACK = "rollback"


@dataclass
class DeploymentStep:
    """A single step in a deployment."""
    step_type: DeploymentStepType
    node_id: str
    node_name: str
    description: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    success: bool = False
    error: Optional[str] = None


@dataclass
class DeploymentContext:
    """Context for a deployment operation."""
    deployment_id: str
    strategy: DeploymentStrategyType
    role_name: str
    target_nodes: List[str]
    playbook_path: Optional[str] = None
    params: Dict = field(default_factory=dict)
    steps: List[DeploymentStep] = field(default_factory=list)
    current_step_index: int = 0
    status: DeploymentStatus = DeploymentStatus.QUEUED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    rollback_triggered: bool = False


# Health check configuration
HEALTH_CHECK_TIMEOUT = 60  # seconds
HEALTH_CHECK_INTERVAL = 5  # seconds
HEALTH_CHECK_RETRIES = 3
ROLLBACK_THRESHOLD = 2  # consecutive failures before rollback


class BaseDeploymentStrategy(ABC):
    """Base class for deployment strategies."""

    def __init__(
        self,
        db: SLMDatabaseService,
        ssh: SSHExecutor,
        on_progress: Optional[Callable[[DeploymentContext], None]] = None,
    ):
        """
        Initialize deployment strategy.

        Args:
            db: Database service
            ssh: SSH executor for remote commands
            on_progress: Callback for progress updates
        """
        self.db = db
        self.ssh = ssh
        self.on_progress = on_progress

    @abstractmethod
    async def execute(self, context: DeploymentContext) -> bool:
        """
        Execute the deployment strategy.

        Args:
            context: Deployment context

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def rollback(self, context: DeploymentContext) -> bool:
        """
        Rollback the deployment.

        Args:
            context: Deployment context

        Returns:
            True if rollback successful
        """
        pass

    async def _notify_progress(self, context: DeploymentContext):
        """Notify progress callback."""
        if self.on_progress:
            try:
                self.on_progress(context)
            except Exception as e:
                logger.warning("Progress callback error: %s", e)

    async def _wait_for_health(
        self,
        node: SLMNode,
        timeout: int = HEALTH_CHECK_TIMEOUT,
    ) -> bool:
        """
        Wait for node to become healthy.

        Args:
            node: Node to check
            timeout: Maximum wait time in seconds

        Returns:
            True if healthy within timeout
        """
        start = datetime.utcnow()
        retries = 0

        while (datetime.utcnow() - start).total_seconds() < timeout:
            # Refresh node state
            current = self.db.get_node(node.id)
            if current and current.state == NodeState.ONLINE.value:
                logger.info("Node %s is healthy", node.name)
                return True

            retries += 1
            if retries >= HEALTH_CHECK_RETRIES:
                logger.warning(
                    "Node %s not healthy after %d checks",
                    node.name, retries,
                )
                return False

            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

        logger.warning("Health check timeout for node %s", node.name)
        return False

    async def _drain_node(self, node: SLMNode) -> bool:
        """
        Put node into draining state.

        Args:
            node: Node to drain

        Returns:
            True if successful
        """
        try:
            self.db.update_node_state(
                node_id=node.id,
                new_state=NodeState.MAINTENANCE_DRAINING,
                trigger="deployment",
                details={"action": "drain"},
            )
            logger.info("Node %s entering drain state", node.name)
            return True
        except Exception as e:
            logger.error("Failed to drain node %s: %s", node.name, e)
            return False

    async def _recover_node(self, node: SLMNode) -> bool:
        """
        Recover node from maintenance state.

        Args:
            node: Node to recover

        Returns:
            True if successful
        """
        try:
            # First move to recovering (skip validation for deployment ops)
            self.db.update_node_state(
                node_id=node.id,
                new_state=NodeState.MAINTENANCE_RECOVERING,
                trigger="deployment",
                details={"action": "recover"},
                validate_transition=False,
            )

            # Then to online if healthy
            healthy = await self._wait_for_health(node)
            if healthy:
                self.db.update_node_state(
                    node_id=node.id,
                    new_state=NodeState.ONLINE,
                    trigger="deployment",
                    details={"action": "recovered"},
                    validate_transition=False,
                )
                return True

            # Mark as error if not healthy
            self.db.update_node_state(
                node_id=node.id,
                new_state=NodeState.ERROR,
                trigger="deployment",
                details={"action": "recovery_failed"},
                validate_transition=False,
            )
            return False

        except Exception as e:
            logger.error("Failed to recover node %s: %s", node.name, e)
            return False


class SequentialDeploymentStrategy(BaseDeploymentStrategy):
    """
    Sequential deployment: one node at a time.

    Process for each node:
    1. Drain (stop accepting work)
    2. Execute playbook/update
    3. Verify health
    4. Recover (resume work)

    On failure: rollback completed nodes, abort remaining.
    """

    async def execute(self, context: DeploymentContext) -> bool:
        """Execute sequential deployment."""
        context.status = DeploymentStatus.RUNNING
        context.started_at = datetime.utcnow()
        await self._notify_progress(context)

        completed_nodes: List[str] = []
        failed = False

        for node_id in context.target_nodes:
            node = self.db.get_node(node_id)
            if not node:
                logger.error("Node %s not found, skipping", node_id)
                continue

            logger.info(
                "Deploying to node %s (%d/%d)",
                node.name,
                len(completed_nodes) + 1,
                len(context.target_nodes),
            )

            # Execute deployment steps for this node
            success = await self._deploy_to_node(context, node)

            if success:
                completed_nodes.append(node_id)
            else:
                failed = True
                context.error = f"Deployment failed on node {node.name}"
                break

        if failed and completed_nodes:
            # Rollback completed nodes
            logger.warning(
                "Deployment failed, rolling back %d nodes",
                len(completed_nodes),
            )
            context.rollback_triggered = True
            await self._rollback_nodes(context, completed_nodes)
            context.status = DeploymentStatus.ROLLED_BACK
        elif failed:
            context.status = DeploymentStatus.FAILED
        else:
            context.status = DeploymentStatus.SUCCESS

        context.completed_at = datetime.utcnow()
        await self._notify_progress(context)

        return not failed

    async def _deploy_to_node(
        self,
        context: DeploymentContext,
        node: SLMNode,
    ) -> bool:
        """Deploy to a single node."""
        # Step 1: Drain
        step = DeploymentStep(
            step_type=DeploymentStepType.DRAIN,
            node_id=node.id,
            node_name=node.name,
            description=f"Draining node {node.name}",
        )
        context.steps.append(step)
        step.started_at = datetime.utcnow()
        await self._notify_progress(context)

        if not await self._drain_node(node):
            step.error = "Failed to drain node"
            step.completed_at = datetime.utcnow()
            return False

        step.success = True
        step.completed_at = datetime.utcnow()

        # Step 2: Execute playbook (if provided)
        if context.playbook_path:
            step = DeploymentStep(
                step_type=DeploymentStepType.EXECUTE_PLAYBOOK,
                node_id=node.id,
                node_name=node.name,
                description=f"Executing playbook on {node.name}",
            )
            context.steps.append(step)
            step.started_at = datetime.utcnow()
            await self._notify_progress(context)

            success = await self._run_playbook(node, context.playbook_path)
            step.success = success
            step.completed_at = datetime.utcnow()

            if not success:
                step.error = "Playbook execution failed"
                await self._recover_node(node)
                return False

        # Step 3: Verify health
        step = DeploymentStep(
            step_type=DeploymentStepType.VERIFY,
            node_id=node.id,
            node_name=node.name,
            description=f"Verifying health of {node.name}",
        )
        context.steps.append(step)
        step.started_at = datetime.utcnow()
        await self._notify_progress(context)

        # Move to offline then recovering
        self.db.update_node_state(
            node_id=node.id,
            new_state=NodeState.MAINTENANCE_OFFLINE,
            trigger="deployment",
            validate_transition=False,
        )

        # Step 4: Recover
        step = DeploymentStep(
            step_type=DeploymentStepType.RECOVER,
            node_id=node.id,
            node_name=node.name,
            description=f"Recovering {node.name}",
        )
        context.steps.append(step)
        step.started_at = datetime.utcnow()
        await self._notify_progress(context)

        if not await self._recover_node(node):
            step.error = "Recovery failed"
            step.completed_at = datetime.utcnow()
            return False

        step.success = True
        step.completed_at = datetime.utcnow()

        logger.info("Successfully deployed to node %s", node.name)
        return True

    async def _run_playbook(self, node: SLMNode, playbook_path: str) -> bool:
        """
        Run Ansible playbook on node.

        Args:
            node: Target node
            playbook_path: Path to playbook

        Returns:
            True if successful
        """
        # Build ansible-playbook command
        cmd = (
            f"ansible-playbook {playbook_path} "
            f"-i {node.ip_address}, "
            f"-u {node.ssh_user} "
            f"--ssh-extra-args='-o StrictHostKeyChecking=no'"
        )

        logger.info("Running playbook on %s: %s", node.name, playbook_path)

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=300,  # 5 minute timeout
            )

            if proc.returncode == 0:
                logger.info("Playbook succeeded on %s", node.name)
                return True
            else:
                logger.error(
                    "Playbook failed on %s (rc=%d): %s",
                    node.name, proc.returncode,
                    stderr.decode("utf-8", errors="replace"),
                )
                return False

        except asyncio.TimeoutError:
            logger.error("Playbook timed out on %s", node.name)
            return False
        except Exception as e:
            logger.error("Playbook error on %s: %s", node.name, e)
            return False

    async def _rollback_nodes(
        self,
        context: DeploymentContext,
        node_ids: List[str],
    ):
        """Rollback completed nodes."""
        for node_id in reversed(node_ids):
            node = self.db.get_node(node_id)
            if not node:
                continue

            step = DeploymentStep(
                step_type=DeploymentStepType.ROLLBACK,
                node_id=node.id,
                node_name=node.name,
                description=f"Rolling back {node.name}",
            )
            context.steps.append(step)
            step.started_at = datetime.utcnow()

            # For now, just recover the node
            # Full rollback would re-run previous playbook version
            success = await self._recover_node(node)
            step.success = success
            step.completed_at = datetime.utcnow()

            if not success:
                logger.error("Rollback failed for node %s", node.name)

    async def rollback(self, context: DeploymentContext) -> bool:
        """Manual rollback trigger."""
        completed = [
            step.node_id
            for step in context.steps
            if step.step_type == DeploymentStepType.RECOVER and step.success
        ]

        if completed:
            await self._rollback_nodes(context, completed)
            context.status = DeploymentStatus.ROLLED_BACK
            context.rollback_triggered = True
            return True

        return False


class MaintenanceWindowStrategy(BaseDeploymentStrategy):
    """
    Maintenance window deployment: scheduled downtime operations.

    Process:
    1. Wait for maintenance window start time
    2. Put ALL target nodes into maintenance state simultaneously
    3. Execute playbook on each node (parallel or sequential)
    4. Verify all nodes healthy
    5. Recover all nodes

    Best for: Major updates requiring coordinated downtime.
    """

    def __init__(
        self,
        db: SLMDatabaseService,
        ssh: SSHExecutor,
        on_progress: Optional[Callable[[DeploymentContext], None]] = None,
        parallel_execution: bool = False,
    ):
        """
        Initialize maintenance window strategy.

        Args:
            db: Database service
            ssh: SSH executor
            on_progress: Progress callback
            parallel_execution: Execute playbooks in parallel (default: sequential)
        """
        super().__init__(db, ssh, on_progress)
        self.parallel_execution = parallel_execution

    async def execute(self, context: DeploymentContext) -> bool:
        """Execute maintenance window deployment."""
        context.status = DeploymentStatus.RUNNING
        context.started_at = datetime.utcnow()
        await self._notify_progress(context)

        # Check for scheduled start time
        scheduled_start = context.params.get("scheduled_start")
        if scheduled_start:
            await self._wait_for_window(scheduled_start)

        # Phase 1: Drain all nodes
        nodes = []
        for node_id in context.target_nodes:
            node = self.db.get_node(node_id)
            if not node:
                logger.warning("Node %s not found, skipping", node_id)
                continue
            nodes.append(node)

        logger.info("Starting maintenance window for %d nodes", len(nodes))

        # Drain all nodes simultaneously
        drain_success = await self._drain_all_nodes(context, nodes)
        if not drain_success:
            context.status = DeploymentStatus.FAILED
            context.error = "Failed to drain one or more nodes"
            context.completed_at = datetime.utcnow()
            return False

        # Phase 2: Execute playbooks
        if context.playbook_path:
            exec_success = await self._execute_all_playbooks(context, nodes)
            if not exec_success:
                # Try to recover nodes
                await self._recover_all_nodes(context, nodes)
                context.status = DeploymentStatus.FAILED
                context.error = "Playbook execution failed"
                context.completed_at = datetime.utcnow()
                return False

        # Phase 3: Recover all nodes
        recover_success = await self._recover_all_nodes(context, nodes)
        if not recover_success:
            context.status = DeploymentStatus.FAILED
            context.error = "Recovery failed for one or more nodes"
            context.completed_at = datetime.utcnow()
            return False

        context.status = DeploymentStatus.SUCCESS
        context.completed_at = datetime.utcnow()
        await self._notify_progress(context)

        logger.info("Maintenance window completed successfully")
        return True

    async def _wait_for_window(self, scheduled_start: str):
        """Wait for the maintenance window to start."""
        try:
            start_time = datetime.fromisoformat(scheduled_start)
            now = datetime.utcnow()

            if start_time > now:
                wait_seconds = (start_time - now).total_seconds()
                logger.info(
                    "Waiting %.1f seconds for maintenance window",
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
        except ValueError as e:
            logger.warning("Invalid scheduled_start format: %s", e)

    async def _drain_all_nodes(
        self, context: DeploymentContext, nodes: List[SLMNode]
    ) -> bool:
        """Drain all nodes simultaneously."""
        tasks = []

        for node in nodes:
            step = DeploymentStep(
                step_type=DeploymentStepType.DRAIN,
                node_id=node.id,
                node_name=node.name,
                description=f"Draining {node.name}",
            )
            context.steps.append(step)
            step.started_at = datetime.utcnow()
            tasks.append(self._drain_node(node))

        await self._notify_progress(context)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_success = True
        for i, result in enumerate(results):
            step = context.steps[-(len(nodes) - i)]
            step.completed_at = datetime.utcnow()

            if isinstance(result, Exception):
                step.error = str(result)
                step.success = False
                all_success = False
            else:
                step.success = result
                if not result:
                    all_success = False

        return all_success

    async def _execute_all_playbooks(
        self, context: DeploymentContext, nodes: List[SLMNode]
    ) -> bool:
        """Execute playbooks on all nodes."""
        if self.parallel_execution:
            return await self._execute_playbooks_parallel(context, nodes)
        return await self._execute_playbooks_sequential(context, nodes)

    async def _execute_playbooks_sequential(
        self, context: DeploymentContext, nodes: List[SLMNode]
    ) -> bool:
        """Execute playbooks sequentially."""
        # Reuse parent sequential logic
        sequential = SequentialDeploymentStrategy(
            db=self.db, ssh=self.ssh, on_progress=self.on_progress
        )

        for node in nodes:
            step = DeploymentStep(
                step_type=DeploymentStepType.EXECUTE_PLAYBOOK,
                node_id=node.id,
                node_name=node.name,
                description=f"Executing playbook on {node.name}",
            )
            context.steps.append(step)
            step.started_at = datetime.utcnow()
            await self._notify_progress(context)

            success = await sequential._run_playbook(node, context.playbook_path)
            step.success = success
            step.completed_at = datetime.utcnow()

            if not success:
                step.error = "Playbook execution failed"
                return False

        return True

    async def _execute_playbooks_parallel(
        self, context: DeploymentContext, nodes: List[SLMNode]
    ) -> bool:
        """Execute playbooks in parallel."""
        sequential = SequentialDeploymentStrategy(
            db=self.db, ssh=self.ssh, on_progress=self.on_progress
        )

        tasks = []
        for node in nodes:
            step = DeploymentStep(
                step_type=DeploymentStepType.EXECUTE_PLAYBOOK,
                node_id=node.id,
                node_name=node.name,
                description=f"Executing playbook on {node.name}",
            )
            context.steps.append(step)
            step.started_at = datetime.utcnow()
            tasks.append(sequential._run_playbook(node, context.playbook_path))

        await self._notify_progress(context)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_success = True
        playbook_steps = [
            s for s in context.steps
            if s.step_type == DeploymentStepType.EXECUTE_PLAYBOOK
        ][-len(nodes):]

        for i, result in enumerate(results):
            step = playbook_steps[i]
            step.completed_at = datetime.utcnow()

            if isinstance(result, Exception):
                step.error = str(result)
                step.success = False
                all_success = False
            else:
                step.success = result
                if not result:
                    step.error = "Playbook execution failed"
                    all_success = False

        return all_success

    async def _recover_all_nodes(
        self, context: DeploymentContext, nodes: List[SLMNode]
    ) -> bool:
        """Recover all nodes."""
        all_success = True

        for node in nodes:
            step = DeploymentStep(
                step_type=DeploymentStepType.RECOVER,
                node_id=node.id,
                node_name=node.name,
                description=f"Recovering {node.name}",
            )
            context.steps.append(step)
            step.started_at = datetime.utcnow()
            await self._notify_progress(context)

            # First set to offline
            self.db.update_node_state(
                node_id=node.id,
                new_state=NodeState.MAINTENANCE_OFFLINE,
                trigger="deployment",
                validate_transition=False,
            )

            success = await self._recover_node(node)
            step.success = success
            step.completed_at = datetime.utcnow()

            if not success:
                step.error = "Recovery failed"
                all_success = False

        return all_success

    async def rollback(self, context: DeploymentContext) -> bool:
        """Rollback all nodes in maintenance."""
        nodes = []
        for node_id in context.target_nodes:
            node = self.db.get_node(node_id)
            if node:
                nodes.append(node)

        if nodes:
            await self._recover_all_nodes(context, nodes)
            context.status = DeploymentStatus.ROLLED_BACK
            context.rollback_triggered = True
            return True

        return False


class BlueGreenStrategy(BaseDeploymentStrategy):
    """
    Blue-green deployment with role borrowing.

    Process:
    1. Identify "blue" (current) and "green" (target) groups
    2. Borrow spare nodes from other roles if needed
    3. Set up green environment on borrowed/spare nodes
    4. Switch traffic from blue to green
    5. Verify green healthy
    6. Decommission blue, return borrowed nodes

    Best for: Zero-downtime updates requiring instant rollback capability.
    """

    async def execute(self, context: DeploymentContext) -> bool:
        """Execute blue-green deployment."""
        context.status = DeploymentStatus.RUNNING
        context.started_at = datetime.utcnow()
        await self._notify_progress(context)

        # Get blue nodes (current targets)
        blue_nodes = []
        for node_id in context.target_nodes:
            node = self.db.get_node(node_id)
            if node:
                blue_nodes.append(node)

        if not blue_nodes:
            context.status = DeploymentStatus.FAILED
            context.error = "No blue nodes found"
            context.completed_at = datetime.utcnow()
            return False

        logger.info("Blue-green deployment: %d blue nodes", len(blue_nodes))

        # Phase 1: Find/borrow green nodes
        green_nodes = await self._acquire_green_nodes(context, len(blue_nodes))

        if not green_nodes:
            context.status = DeploymentStatus.FAILED
            context.error = "Unable to acquire green nodes"
            context.completed_at = datetime.utcnow()
            return False

        logger.info("Acquired %d green nodes", len(green_nodes))

        # Phase 2: Deploy to green nodes
        deploy_success = await self._deploy_to_green(context, green_nodes)

        if not deploy_success:
            # Release borrowed nodes
            await self._release_nodes(context, green_nodes)
            context.status = DeploymentStatus.FAILED
            context.error = "Green deployment failed"
            context.completed_at = datetime.utcnow()
            return False

        # Phase 3: Switch traffic (assign role to green nodes)
        switch_success = await self._switch_to_green(context, blue_nodes, green_nodes)

        if not switch_success:
            await self._release_nodes(context, green_nodes)
            context.status = DeploymentStatus.FAILED
            context.error = "Traffic switch failed"
            context.completed_at = datetime.utcnow()
            return False

        # Phase 4: Decommission blue nodes
        await self._decommission_blue(context, blue_nodes)

        context.status = DeploymentStatus.SUCCESS
        context.completed_at = datetime.utcnow()
        await self._notify_progress(context)

        logger.info("Blue-green deployment completed successfully")
        return True

    async def _acquire_green_nodes(
        self, context: DeploymentContext, count: int
    ) -> List[SLMNode]:
        """
        Acquire nodes for green environment.

        Strategy:
        1. Look for nodes with spare capacity (no role assigned)
        2. If not enough, borrow from roles with excess capacity
        """
        green_nodes = []
        borrowed_role = context.params.get("borrow_from_role")

        # Step 1: Look for spare nodes
        all_nodes = self.db.get_all_nodes()
        spare_nodes = [
            n for n in all_nodes
            if n.current_role is None
            and n.state == NodeState.ONLINE.value
            and n.id not in context.target_nodes
        ]

        for node in spare_nodes[:count]:
            step = DeploymentStep(
                step_type=DeploymentStepType.DRAIN,  # Reuse for acquiring
                node_id=node.id,
                node_name=node.name,
                description=f"Acquiring spare node {node.name}",
            )
            context.steps.append(step)
            step.started_at = datetime.utcnow()
            step.success = True
            step.completed_at = datetime.utcnow()
            green_nodes.append(node)

        await self._notify_progress(context)

        if len(green_nodes) >= count:
            return green_nodes[:count]

        # Step 2: Borrow from specified role
        if borrowed_role:
            role_nodes = [
                n for n in all_nodes
                if n.current_role == borrowed_role
                and n.state == NodeState.ONLINE.value
                and n.id not in context.target_nodes
            ]

            needed = count - len(green_nodes)
            for node in role_nodes[:needed]:
                step = DeploymentStep(
                    step_type=DeploymentStepType.DRAIN,
                    node_id=node.id,
                    node_name=node.name,
                    description=f"Borrowing {node.name} from {borrowed_role}",
                )
                context.steps.append(step)
                step.started_at = datetime.utcnow()

                # Mark as borrowed
                node.current_role = f"borrowed:{borrowed_role}"
                self.db.update_node_state(
                    node_id=node.id,
                    new_state=NodeState.MAINTENANCE_DRAINING,
                    trigger="deployment",
                    details={"borrowed_from": borrowed_role},
                    validate_transition=False,
                )

                step.success = True
                step.completed_at = datetime.utcnow()
                green_nodes.append(node)

            await self._notify_progress(context)

        return green_nodes

    async def _deploy_to_green(
        self, context: DeploymentContext, green_nodes: List[SLMNode]
    ) -> bool:
        """Deploy playbook to green nodes."""
        if not context.playbook_path:
            # No playbook, just mark as ready
            return True

        sequential = SequentialDeploymentStrategy(
            db=self.db, ssh=self.ssh, on_progress=self.on_progress
        )

        for node in green_nodes:
            step = DeploymentStep(
                step_type=DeploymentStepType.EXECUTE_PLAYBOOK,
                node_id=node.id,
                node_name=node.name,
                description=f"Deploying to green node {node.name}",
            )
            context.steps.append(step)
            step.started_at = datetime.utcnow()
            await self._notify_progress(context)

            success = await sequential._run_playbook(node, context.playbook_path)
            step.success = success
            step.completed_at = datetime.utcnow()

            if not success:
                step.error = "Playbook failed"
                return False

        return True

    async def _switch_to_green(
        self,
        context: DeploymentContext,
        blue_nodes: List[SLMNode],
        green_nodes: List[SLMNode],
    ) -> bool:
        """Switch traffic from blue to green."""
        target_role = context.role_name

        # Assign role to green nodes
        for node in green_nodes:
            step = DeploymentStep(
                step_type=DeploymentStepType.VERIFY,  # Reuse for switch
                node_id=node.id,
                node_name=node.name,
                description=f"Switching {node.name} to {target_role}",
            )
            context.steps.append(step)
            step.started_at = datetime.utcnow()

            try:
                self.db.assign_role_to_node(node.id, target_role)
                self.db.update_node_state(
                    node_id=node.id,
                    new_state=NodeState.ONLINE,
                    trigger="deployment",
                    details={"role": target_role},
                    validate_transition=False,
                )
                step.success = True
            except Exception as e:
                step.error = str(e)
                step.success = False
                return False
            finally:
                step.completed_at = datetime.utcnow()

        await self._notify_progress(context)
        return True

    async def _decommission_blue(
        self, context: DeploymentContext, blue_nodes: List[SLMNode]
    ):
        """Decommission old blue nodes."""
        for node in blue_nodes:
            step = DeploymentStep(
                step_type=DeploymentStepType.DRAIN,
                node_id=node.id,
                node_name=node.name,
                description=f"Decommissioning blue node {node.name}",
            )
            context.steps.append(step)
            step.started_at = datetime.utcnow()

            try:
                # Remove role assignment, keep node available
                self.db.assign_role_to_node(node.id, None)
                step.success = True
            except Exception as e:
                step.error = str(e)
                step.success = False
            finally:
                step.completed_at = datetime.utcnow()

        await self._notify_progress(context)

    async def _release_nodes(
        self, context: DeploymentContext, nodes: List[SLMNode]
    ):
        """Release borrowed nodes back to original roles."""
        for node in nodes:
            # Check if borrowed
            if node.current_role and node.current_role.startswith("borrowed:"):
                original_role = node.current_role.replace("borrowed:", "")
                try:
                    self.db.assign_role_to_node(node.id, original_role)
                    self.db.update_node_state(
                        node_id=node.id,
                        new_state=NodeState.ONLINE,
                        trigger="deployment",
                        details={"returned_to": original_role},
                        validate_transition=False,
                    )
                except Exception as e:
                    logger.error("Failed to release node %s: %s", node.name, e)

    async def rollback(self, context: DeploymentContext) -> bool:
        """Rollback blue-green deployment."""
        # Get green nodes that were deployed to
        green_node_ids = set()
        for step in context.steps:
            if step.step_type == DeploymentStepType.VERIFY and step.success:
                green_node_ids.add(step.node_id)

        if not green_node_ids:
            return False

        green_nodes = []
        for node_id in green_node_ids:
            node = self.db.get_node(node_id)
            if node:
                green_nodes.append(node)

        # Release green nodes
        await self._release_nodes(context, green_nodes)

        context.status = DeploymentStatus.ROLLED_BACK
        context.rollback_triggered = True
        return True


class DeploymentOrchestrator:
    """
    Main orchestrator for deployment operations.

    Manages deployment lifecycle:
    - Create and queue deployments
    - Execute with appropriate strategy
    - Track progress and results
    - Handle cancellation and rollback
    """

    def __init__(
        self,
        db_service: Optional[SLMDatabaseService] = None,
        ssh_executor: Optional[SSHExecutor] = None,
        on_progress: Optional[Callable[[DeploymentContext], None]] = None,
    ):
        """
        Initialize deployment orchestrator.

        Args:
            db_service: Database service
            ssh_executor: SSH executor
            on_progress: Progress callback
        """
        self.db = db_service or SLMDatabaseService()
        self.ssh = ssh_executor or SSHExecutor()
        self.on_progress = on_progress

        self._active_deployments: Dict[str, DeploymentContext] = {}
        self._lock = asyncio.Lock()

        logger.info("Deployment orchestrator initialized")

    @property
    def active_deployments(self) -> List[DeploymentContext]:
        """Get list of active deployments."""
        return list(self._active_deployments.values())

    def get_deployment(self, deployment_id: str) -> Optional[DeploymentContext]:
        """Get deployment by ID."""
        return self._active_deployments.get(deployment_id)

    async def create_deployment(
        self,
        role_name: str,
        target_nodes: List[str],
        strategy: DeploymentStrategyType = DeploymentStrategyType.SEQUENTIAL,
        playbook_path: Optional[str] = None,
        params: Optional[Dict] = None,
    ) -> DeploymentContext:
        """
        Create a new deployment.

        Args:
            role_name: Role being deployed
            target_nodes: List of node IDs
            strategy: Deployment strategy
            playbook_path: Path to Ansible playbook
            params: Additional parameters

        Returns:
            Deployment context
        """
        deployment_id = str(uuid4())

        context = DeploymentContext(
            deployment_id=deployment_id,
            strategy=strategy,
            role_name=role_name,
            target_nodes=target_nodes,
            playbook_path=playbook_path,
            params=params or {},
        )

        async with self._lock:
            self._active_deployments[deployment_id] = context

        logger.info(
            "Created deployment %s: role=%s, nodes=%d, strategy=%s",
            deployment_id, role_name, len(target_nodes), strategy.value,
        )

        return context

    async def execute_deployment(
        self,
        deployment_id: str,
    ) -> bool:
        """
        Execute a queued deployment.

        Args:
            deployment_id: Deployment ID

        Returns:
            True if successful
        """
        context = self._active_deployments.get(deployment_id)
        if not context:
            logger.error("Deployment %s not found", deployment_id)
            return False

        if context.status != DeploymentStatus.QUEUED:
            logger.error(
                "Cannot execute deployment %s in status %s",
                deployment_id, context.status.value,
            )
            return False

        # Select strategy implementation
        strategy = self._get_strategy(context.strategy)

        try:
            success = await strategy.execute(context)
            return success

        except Exception as e:
            logger.exception("Deployment %s failed: %s", deployment_id, e)
            context.status = DeploymentStatus.FAILED
            context.error = str(e)
            context.completed_at = datetime.utcnow()
            return False

    async def cancel_deployment(self, deployment_id: str) -> bool:
        """
        Cancel a deployment.

        Args:
            deployment_id: Deployment ID

        Returns:
            True if cancelled
        """
        context = self._active_deployments.get(deployment_id)
        if not context:
            return False

        if context.status in (DeploymentStatus.QUEUED, DeploymentStatus.PAUSED):
            context.status = DeploymentStatus.CANCELLED
            context.completed_at = datetime.utcnow()
            logger.info("Deployment %s cancelled", deployment_id)
            return True

        logger.warning(
            "Cannot cancel deployment %s in status %s",
            deployment_id, context.status.value,
        )
        return False

    async def trigger_rollback(self, deployment_id: str) -> bool:
        """
        Manually trigger rollback for a deployment.

        Args:
            deployment_id: Deployment ID

        Returns:
            True if rollback initiated
        """
        context = self._active_deployments.get(deployment_id)
        if not context:
            return False

        strategy = self._get_strategy(context.strategy)
        return await strategy.rollback(context)

    def _get_strategy(
        self, strategy_type: DeploymentStrategyType
    ) -> BaseDeploymentStrategy:
        """Get strategy implementation."""
        if strategy_type == DeploymentStrategyType.SEQUENTIAL:
            return SequentialDeploymentStrategy(
                db=self.db,
                ssh=self.ssh,
                on_progress=self.on_progress,
            )
        elif strategy_type == DeploymentStrategyType.MAINTENANCE_WINDOW:
            return MaintenanceWindowStrategy(
                db=self.db,
                ssh=self.ssh,
                on_progress=self.on_progress,
            )
        elif strategy_type == DeploymentStrategyType.BLUE_GREEN:
            return BlueGreenStrategy(
                db=self.db,
                ssh=self.ssh,
                on_progress=self.on_progress,
            )
        else:
            # Default to sequential for unimplemented strategies
            logger.warning(
                "Strategy %s not fully implemented, using sequential",
                strategy_type.value,
            )
            return SequentialDeploymentStrategy(
                db=self.db,
                ssh=self.ssh,
                on_progress=self.on_progress,
            )


# Singleton instance
_orchestrator: Optional[DeploymentOrchestrator] = None


def get_orchestrator() -> DeploymentOrchestrator:
    """Get or create the singleton orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = DeploymentOrchestrator()
    return _orchestrator
