# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for SLM Deployment Orchestrator.
"""

import asyncio
import os
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.infrastructure import (
    DeploymentStrategy as DeploymentStrategyType,
    NodeState,
)
from backend.services.slm.db_service import SLMDatabaseService
from backend.services.slm.deployment_orchestrator import (
    BaseDeploymentStrategy,
    BlueGreenStrategy,
    DeploymentContext,
    DeploymentOrchestrator,
    DeploymentStatus,
    DeploymentStep,
    DeploymentStepType,
    MaintenanceWindowStrategy,
    SequentialDeploymentStrategy,
    get_orchestrator,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def db_service(temp_db):
    """Create a database service with temporary database."""
    return SLMDatabaseService(db_path=temp_db)


@pytest.fixture
def mock_ssh():
    """Create mock SSH executor."""
    ssh = AsyncMock()
    ssh.execute = AsyncMock(return_value=(0, "success", ""))
    return ssh


@pytest.fixture
def orchestrator(db_service, mock_ssh):
    """Create deployment orchestrator with test dependencies."""
    return DeploymentOrchestrator(
        db_service=db_service,
        ssh_executor=mock_ssh,
    )


@pytest.fixture
def sample_node(db_service):
    """Create a sample node for testing."""
    node = db_service.create_node(
        name="test-node-1",
        ip_address="192.168.1.100",
        ssh_user="autobot",
        ssh_port=22,
        current_role="worker",
    )
    # Set node to online state
    db_service.update_node_state(
        node_id=node.id,
        new_state=NodeState.ONLINE,
        trigger="test",
        validate_transition=False,
    )
    return db_service.get_node(node.id)


class TestDeploymentStatus:
    """Test deployment status enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert DeploymentStatus.QUEUED.value == "queued"
        assert DeploymentStatus.RUNNING.value == "running"
        assert DeploymentStatus.PAUSED.value == "paused"
        assert DeploymentStatus.SUCCESS.value == "success"
        assert DeploymentStatus.FAILED.value == "failed"
        assert DeploymentStatus.ROLLED_BACK.value == "rolled_back"
        assert DeploymentStatus.CANCELLED.value == "cancelled"


class TestDeploymentStepType:
    """Test deployment step type enum."""

    def test_step_types(self):
        """Test all step types exist."""
        assert DeploymentStepType.DRAIN.value == "drain"
        assert DeploymentStepType.HEALTH_CHECK.value == "health_check"
        assert DeploymentStepType.EXECUTE_PLAYBOOK.value == "execute_playbook"
        assert DeploymentStepType.VERIFY.value == "verify"
        assert DeploymentStepType.RECOVER.value == "recover"
        assert DeploymentStepType.ROLLBACK.value == "rollback"


class TestDeploymentContext:
    """Test deployment context dataclass."""

    def test_context_defaults(self):
        """Test context default values."""
        context = DeploymentContext(
            deployment_id="test-123",
            strategy=DeploymentStrategyType.SEQUENTIAL,
            role_name="worker",
            target_nodes=["node-1", "node-2"],
        )

        assert context.deployment_id == "test-123"
        assert context.strategy == DeploymentStrategyType.SEQUENTIAL
        assert context.role_name == "worker"
        assert len(context.target_nodes) == 2
        assert context.playbook_path is None
        assert context.params == {}
        assert context.steps == []
        assert context.current_step_index == 0
        assert context.status == DeploymentStatus.QUEUED
        assert context.started_at is None
        assert context.completed_at is None
        assert context.error is None
        assert context.rollback_triggered is False

    def test_context_with_playbook(self):
        """Test context with playbook path."""
        context = DeploymentContext(
            deployment_id="test-456",
            strategy=DeploymentStrategyType.SEQUENTIAL,
            role_name="worker",
            target_nodes=["node-1"],
            playbook_path="/path/to/playbook.yml",
            params={"version": "1.2.3"},
        )

        assert context.playbook_path == "/path/to/playbook.yml"
        assert context.params["version"] == "1.2.3"


class TestDeploymentStep:
    """Test deployment step dataclass."""

    def test_step_defaults(self):
        """Test step default values."""
        step = DeploymentStep(
            step_type=DeploymentStepType.DRAIN,
            node_id="node-1",
            node_name="test-node",
            description="Draining test-node",
        )

        assert step.step_type == DeploymentStepType.DRAIN
        assert step.node_id == "node-1"
        assert step.node_name == "test-node"
        assert step.started_at is None
        assert step.completed_at is None
        assert step.success is False
        assert step.error is None


class TestDeploymentOrchestrator:
    """Test deployment orchestrator."""

    @pytest.mark.asyncio
    async def test_init_orchestrator(self, db_service, mock_ssh):
        """Test orchestrator initialization."""
        orch = DeploymentOrchestrator(
            db_service=db_service,
            ssh_executor=mock_ssh,
        )

        assert orch.db == db_service
        assert orch.ssh == mock_ssh
        assert len(orch.active_deployments) == 0

    @pytest.mark.asyncio
    async def test_create_deployment(self, orchestrator):
        """Test creating a deployment."""
        context = await orchestrator.create_deployment(
            role_name="worker",
            target_nodes=["node-1", "node-2"],
            strategy=DeploymentStrategyType.SEQUENTIAL,
        )

        assert context.deployment_id is not None
        assert context.role_name == "worker"
        assert context.target_nodes == ["node-1", "node-2"]
        assert context.status == DeploymentStatus.QUEUED
        assert len(orchestrator.active_deployments) == 1

    @pytest.mark.asyncio
    async def test_create_deployment_with_playbook(self, orchestrator):
        """Test creating deployment with playbook."""
        context = await orchestrator.create_deployment(
            role_name="worker",
            target_nodes=["node-1"],
            strategy=DeploymentStrategyType.SEQUENTIAL,
            playbook_path="/path/to/deploy.yml",
            params={"env": "prod"},
        )

        assert context.playbook_path == "/path/to/deploy.yml"
        assert context.params["env"] == "prod"

    @pytest.mark.asyncio
    async def test_get_deployment(self, orchestrator):
        """Test getting deployment by ID."""
        context = await orchestrator.create_deployment(
            role_name="worker",
            target_nodes=["node-1"],
            strategy=DeploymentStrategyType.SEQUENTIAL,
        )

        retrieved = orchestrator.get_deployment(context.deployment_id)
        assert retrieved == context

    @pytest.mark.asyncio
    async def test_get_nonexistent_deployment(self, orchestrator):
        """Test getting nonexistent deployment returns None."""
        result = orchestrator.get_deployment("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_queued_deployment(self, orchestrator):
        """Test cancelling a queued deployment."""
        context = await orchestrator.create_deployment(
            role_name="worker",
            target_nodes=["node-1"],
            strategy=DeploymentStrategyType.SEQUENTIAL,
        )

        result = await orchestrator.cancel_deployment(context.deployment_id)

        assert result is True
        assert context.status == DeploymentStatus.CANCELLED
        assert context.completed_at is not None

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_deployment(self, orchestrator):
        """Test cancelling nonexistent deployment returns False."""
        result = await orchestrator.cancel_deployment("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_nonexistent_deployment(self, orchestrator):
        """Test executing nonexistent deployment returns False."""
        result = await orchestrator.execute_deployment("nonexistent")
        assert result is False


class TestSequentialDeploymentStrategy:
    """Test sequential deployment strategy."""

    @pytest.fixture
    def strategy(self, db_service, mock_ssh):
        """Create sequential deployment strategy."""
        return SequentialDeploymentStrategy(
            db=db_service,
            ssh=mock_ssh,
        )

    @pytest.mark.asyncio
    async def test_strategy_init(self, db_service, mock_ssh):
        """Test strategy initialization."""
        strategy = SequentialDeploymentStrategy(
            db=db_service,
            ssh=mock_ssh,
        )

        assert strategy.db == db_service
        assert strategy.ssh == mock_ssh

    @pytest.mark.asyncio
    async def test_drain_node(self, strategy, sample_node):
        """Test draining a node."""
        result = await strategy._drain_node(sample_node)

        assert result is True

        # Verify node state changed
        updated = strategy.db.get_node(sample_node.id)
        assert updated.state == NodeState.MAINTENANCE_DRAINING.value

    @pytest.mark.asyncio
    async def test_wait_for_health_success(self, strategy, sample_node):
        """Test waiting for healthy node."""
        # Node is already online
        result = await strategy._wait_for_health(sample_node, timeout=5)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_health_timeout(self, strategy, sample_node, db_service):
        """Test health check timeout."""
        # Set node to degraded state
        db_service.update_node_state(
            node_id=sample_node.id,
            new_state=NodeState.DEGRADED,
            trigger="test",
            validate_transition=False,
        )

        result = await strategy._wait_for_health(sample_node, timeout=1)
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_single_node_success(self, strategy, sample_node):
        """Test successful deployment to single node."""
        context = DeploymentContext(
            deployment_id="test-deploy",
            strategy=DeploymentStrategyType.SEQUENTIAL,
            role_name="worker",
            target_nodes=[sample_node.id],
        )

        # Mock _wait_for_health to return True
        with patch.object(strategy, '_wait_for_health', return_value=True):
            result = await strategy.execute(context)

        assert result is True
        assert context.status == DeploymentStatus.SUCCESS
        assert context.started_at is not None
        assert context.completed_at is not None
        assert len(context.steps) >= 2  # drain + recover at minimum

    @pytest.mark.asyncio
    async def test_execute_node_not_found(self, strategy):
        """Test deployment with nonexistent node."""
        context = DeploymentContext(
            deployment_id="test-deploy",
            strategy=DeploymentStrategyType.SEQUENTIAL,
            role_name="worker",
            target_nodes=["nonexistent-node"],
        )

        result = await strategy.execute(context)

        # Should succeed (skips nonexistent nodes)
        assert result is True
        assert context.status == DeploymentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_execute_with_playbook(self, strategy, sample_node):
        """Test deployment with playbook execution."""
        context = DeploymentContext(
            deployment_id="test-deploy",
            strategy=DeploymentStrategyType.SEQUENTIAL,
            role_name="worker",
            target_nodes=[sample_node.id],
            playbook_path="/path/to/playbook.yml",
        )

        # Mock playbook execution and health check
        with patch.object(strategy, '_run_playbook', return_value=True), \
             patch.object(strategy, '_wait_for_health', return_value=True):
            result = await strategy.execute(context)

        assert result is True
        # Should have playbook step
        playbook_steps = [
            s for s in context.steps
            if s.step_type == DeploymentStepType.EXECUTE_PLAYBOOK
        ]
        assert len(playbook_steps) == 1

    @pytest.mark.asyncio
    async def test_execute_playbook_failure_triggers_recovery(
        self, strategy, sample_node
    ):
        """Test playbook failure triggers node recovery."""
        context = DeploymentContext(
            deployment_id="test-deploy",
            strategy=DeploymentStrategyType.SEQUENTIAL,
            role_name="worker",
            target_nodes=[sample_node.id],
            playbook_path="/path/to/playbook.yml",
        )

        # Mock playbook to fail
        with patch.object(strategy, '_run_playbook', return_value=False), \
             patch.object(strategy, '_recover_node', return_value=True) as mock_recover:
            result = await strategy.execute(context)

        assert result is False
        assert context.status == DeploymentStatus.FAILED
        # Recovery should have been called
        mock_recover.assert_called()

    @pytest.mark.asyncio
    async def test_rollback_on_failure(self, strategy, db_service, mock_ssh):
        """Test automatic rollback on failure."""
        # Create two nodes
        node1 = db_service.create_node(
            name="node-1", ip_address="192.168.1.1", ssh_user="autobot"
        )
        db_service.update_node_state(
            node_id=node1.id,
            new_state=NodeState.ONLINE,
            trigger="test",
            validate_transition=False,
        )

        node2 = db_service.create_node(
            name="node-2", ip_address="192.168.1.2", ssh_user="autobot"
        )
        db_service.update_node_state(
            node_id=node2.id,
            new_state=NodeState.ONLINE,
            trigger="test",
            validate_transition=False,
        )

        context = DeploymentContext(
            deployment_id="test-deploy",
            strategy=DeploymentStrategyType.SEQUENTIAL,
            role_name="worker",
            target_nodes=[node1.id, node2.id],
        )

        # First node succeeds, second fails
        call_count = [0]

        async def mock_deploy(ctx, node):
            call_count[0] += 1
            if call_count[0] == 1:
                return True  # node1 succeeds
            return False  # node2 fails

        with patch.object(strategy, '_deploy_to_node', side_effect=mock_deploy), \
             patch.object(strategy, '_rollback_nodes', new_callable=AsyncMock) as mock_rb:
            result = await strategy.execute(context)

        assert result is False
        assert context.rollback_triggered is True
        assert context.status == DeploymentStatus.ROLLED_BACK
        # Rollback should have been called with first node
        mock_rb.assert_called_once()

    @pytest.mark.asyncio
    async def test_progress_callback(self, db_service, mock_ssh, sample_node):
        """Test progress callback is called."""
        progress_calls = []

        def on_progress(ctx):
            progress_calls.append(ctx.status)

        strategy = SequentialDeploymentStrategy(
            db=db_service,
            ssh=mock_ssh,
            on_progress=on_progress,
        )

        context = DeploymentContext(
            deployment_id="test-deploy",
            strategy=DeploymentStrategyType.SEQUENTIAL,
            role_name="worker",
            target_nodes=[sample_node.id],
        )

        with patch.object(strategy, '_wait_for_health', return_value=True):
            await strategy.execute(context)

        # Progress should have been called multiple times
        assert len(progress_calls) > 0
        assert DeploymentStatus.RUNNING in progress_calls

    @pytest.mark.asyncio
    async def test_manual_rollback(self, strategy, sample_node):
        """Test manual rollback trigger."""
        context = DeploymentContext(
            deployment_id="test-deploy",
            strategy=DeploymentStrategyType.SEQUENTIAL,
            role_name="worker",
            target_nodes=[sample_node.id],
        )

        # Add a successful recover step
        context.steps.append(DeploymentStep(
            step_type=DeploymentStepType.RECOVER,
            node_id=sample_node.id,
            node_name=sample_node.name,
            description="Test",
            success=True,
        ))

        with patch.object(strategy, '_rollback_nodes', new_callable=AsyncMock):
            result = await strategy.rollback(context)

        assert result is True
        assert context.status == DeploymentStatus.ROLLED_BACK
        assert context.rollback_triggered is True

    @pytest.mark.asyncio
    async def test_rollback_empty_context(self, strategy):
        """Test rollback with no completed steps."""
        context = DeploymentContext(
            deployment_id="test-deploy",
            strategy=DeploymentStrategyType.SEQUENTIAL,
            role_name="worker",
            target_nodes=["node-1"],
        )

        result = await strategy.rollback(context)
        assert result is False


class TestRunPlaybook:
    """Test playbook execution."""

    @pytest.fixture
    def strategy(self, db_service, mock_ssh):
        """Create strategy for testing."""
        return SequentialDeploymentStrategy(db=db_service, ssh=mock_ssh)

    @pytest.mark.asyncio
    async def test_run_playbook_success(self, strategy, sample_node):
        """Test successful playbook execution."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))

        with patch('asyncio.create_subprocess_shell', return_value=mock_proc), \
             patch('asyncio.wait_for', return_value=(b"ok", b"")):
            result = await strategy._run_playbook(
                sample_node, "/path/to/playbook.yml"
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_run_playbook_failure(self, strategy, sample_node):
        """Test failed playbook execution."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))

        with patch('asyncio.create_subprocess_shell', return_value=mock_proc), \
             patch('asyncio.wait_for', return_value=(b"", b"error")):
            result = await strategy._run_playbook(
                sample_node, "/path/to/playbook.yml"
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_run_playbook_timeout(self, strategy, sample_node):
        """Test playbook timeout."""
        with patch(
            'asyncio.create_subprocess_shell',
            side_effect=asyncio.TimeoutError()
        ):
            result = await strategy._run_playbook(
                sample_node, "/path/to/playbook.yml"
            )

        assert result is False


class TestGetOrchestrator:
    """Test singleton orchestrator getter."""

    def test_get_orchestrator_singleton(self):
        """Test orchestrator is singleton."""
        # Clear any existing instance
        import backend.services.slm.deployment_orchestrator as module
        module._orchestrator = None

        orch1 = get_orchestrator()
        orch2 = get_orchestrator()

        assert orch1 is orch2

        # Clean up
        module._orchestrator = None


class TestRecoverNode:
    """Test node recovery."""

    @pytest.fixture
    def strategy(self, db_service, mock_ssh):
        """Create strategy for testing."""
        return SequentialDeploymentStrategy(db=db_service, ssh=mock_ssh)

    @pytest.fixture
    def draining_node(self, db_service):
        """Create a node in draining state for recovery tests."""
        node = db_service.create_node(
            name="drain-node",
            ip_address="192.168.1.101",
            ssh_user="autobot",
        )
        # Set node to draining state (valid for recovery)
        db_service.update_node_state(
            node_id=node.id,
            new_state=NodeState.MAINTENANCE_DRAINING,
            trigger="test",
            validate_transition=False,
        )
        return db_service.get_node(node.id)

    @pytest.mark.asyncio
    async def test_recover_node_success(self, strategy, draining_node):
        """Test successful node recovery."""
        with patch.object(strategy, '_wait_for_health', return_value=True):
            result = await strategy._recover_node(draining_node)

        assert result is True

        # Verify node is back online
        updated = strategy.db.get_node(draining_node.id)
        assert updated.state == NodeState.ONLINE.value

    @pytest.mark.asyncio
    async def test_recover_node_health_failure(self, strategy, draining_node):
        """Test recovery when health check fails."""
        with patch.object(strategy, '_wait_for_health', return_value=False):
            result = await strategy._recover_node(draining_node)

        assert result is False

        # Verify node is in error state
        updated = strategy.db.get_node(draining_node.id)
        assert updated.state == NodeState.ERROR.value


class TestMaintenanceWindowStrategy:
    """Test maintenance window deployment strategy."""

    @pytest.fixture
    def strategy(self, db_service, mock_ssh):
        """Create maintenance window strategy."""
        return MaintenanceWindowStrategy(
            db=db_service,
            ssh=mock_ssh,
        )

    @pytest.fixture
    def multiple_nodes(self, db_service):
        """Create multiple nodes for testing."""
        nodes = []
        for i in range(3):
            node = db_service.create_node(
                name=f"maint-node-{i}",
                ip_address=f"192.168.1.{100 + i}",
                ssh_user="autobot",
            )
            db_service.update_node_state(
                node_id=node.id,
                new_state=NodeState.ONLINE,
                trigger="test",
                validate_transition=False,
            )
            nodes.append(db_service.get_node(node.id))
        return nodes

    @pytest.mark.asyncio
    async def test_strategy_init(self, db_service, mock_ssh):
        """Test strategy initialization."""
        strategy = MaintenanceWindowStrategy(
            db=db_service,
            ssh=mock_ssh,
        )

        assert strategy.db == db_service
        assert strategy.ssh == mock_ssh
        assert strategy.parallel_execution is False

    @pytest.mark.asyncio
    async def test_strategy_init_parallel(self, db_service, mock_ssh):
        """Test strategy initialization with parallel execution."""
        strategy = MaintenanceWindowStrategy(
            db=db_service,
            ssh=mock_ssh,
            parallel_execution=True,
        )

        assert strategy.parallel_execution is True

    @pytest.mark.asyncio
    async def test_execute_drains_all_nodes(self, strategy, multiple_nodes):
        """Test all nodes are drained simultaneously."""
        context = DeploymentContext(
            deployment_id="maint-deploy",
            strategy=DeploymentStrategyType.MAINTENANCE_WINDOW,
            role_name="worker",
            target_nodes=[n.id for n in multiple_nodes],
        )

        with patch.object(strategy, '_wait_for_health', return_value=True):
            result = await strategy.execute(context)

        assert result is True
        assert context.status == DeploymentStatus.SUCCESS

        # All nodes should have drain steps
        drain_steps = [
            s for s in context.steps
            if s.step_type == DeploymentStepType.DRAIN
        ]
        assert len(drain_steps) == 3

    @pytest.mark.asyncio
    async def test_execute_with_scheduled_start(self, strategy, multiple_nodes):
        """Test waiting for scheduled start time."""
        from datetime import datetime, timedelta

        # Schedule for 0.1 seconds from now
        start_time = datetime.utcnow() + timedelta(seconds=0.1)

        context = DeploymentContext(
            deployment_id="maint-deploy",
            strategy=DeploymentStrategyType.MAINTENANCE_WINDOW,
            role_name="worker",
            target_nodes=[multiple_nodes[0].id],
            params={"scheduled_start": start_time.isoformat()},
        )

        with patch.object(strategy, '_wait_for_health', return_value=True):
            result = await strategy.execute(context)

        assert result is True

    @pytest.mark.asyncio
    async def test_execute_with_playbook(self, strategy, multiple_nodes):
        """Test execution with playbook."""
        context = DeploymentContext(
            deployment_id="maint-deploy",
            strategy=DeploymentStrategyType.MAINTENANCE_WINDOW,
            role_name="worker",
            target_nodes=[n.id for n in multiple_nodes],
            playbook_path="/path/to/playbook.yml",
        )

        with patch.object(strategy, '_wait_for_health', return_value=True), \
             patch.object(
                 SequentialDeploymentStrategy, '_run_playbook', return_value=True
             ):
            result = await strategy.execute(context)

        assert result is True

        # Should have playbook steps for all nodes
        playbook_steps = [
            s for s in context.steps
            if s.step_type == DeploymentStepType.EXECUTE_PLAYBOOK
        ]
        assert len(playbook_steps) == 3

    @pytest.mark.asyncio
    async def test_execute_parallel_playbook(self, db_service, mock_ssh, multiple_nodes):
        """Test parallel playbook execution."""
        strategy = MaintenanceWindowStrategy(
            db=db_service,
            ssh=mock_ssh,
            parallel_execution=True,
        )

        context = DeploymentContext(
            deployment_id="maint-deploy",
            strategy=DeploymentStrategyType.MAINTENANCE_WINDOW,
            role_name="worker",
            target_nodes=[n.id for n in multiple_nodes],
            playbook_path="/path/to/playbook.yml",
        )

        with patch.object(strategy, '_wait_for_health', return_value=True), \
             patch.object(
                 SequentialDeploymentStrategy, '_run_playbook', return_value=True
             ):
            result = await strategy.execute(context)

        assert result is True

    @pytest.mark.asyncio
    async def test_playbook_failure_triggers_recovery(self, strategy, multiple_nodes):
        """Test playbook failure triggers node recovery."""
        context = DeploymentContext(
            deployment_id="maint-deploy",
            strategy=DeploymentStrategyType.MAINTENANCE_WINDOW,
            role_name="worker",
            target_nodes=[multiple_nodes[0].id],
            playbook_path="/path/to/playbook.yml",
        )

        with patch.object(strategy, '_wait_for_health', return_value=True), \
             patch.object(
                 SequentialDeploymentStrategy, '_run_playbook', return_value=False
             ):
            result = await strategy.execute(context)

        assert result is False
        assert context.status == DeploymentStatus.FAILED
        assert "Playbook execution failed" in context.error

    @pytest.mark.asyncio
    async def test_rollback_recovers_all_nodes(self, strategy, multiple_nodes):
        """Test rollback recovers all target nodes."""
        context = DeploymentContext(
            deployment_id="maint-deploy",
            strategy=DeploymentStrategyType.MAINTENANCE_WINDOW,
            role_name="worker",
            target_nodes=[n.id for n in multiple_nodes],
        )

        with patch.object(strategy, '_wait_for_health', return_value=True):
            result = await strategy.rollback(context)

        assert result is True
        assert context.status == DeploymentStatus.ROLLED_BACK
        assert context.rollback_triggered is True

    @pytest.mark.asyncio
    async def test_drain_failure_stops_deployment(self, strategy, multiple_nodes):
        """Test drain failure stops deployment."""
        context = DeploymentContext(
            deployment_id="maint-deploy",
            strategy=DeploymentStrategyType.MAINTENANCE_WINDOW,
            role_name="worker",
            target_nodes=[n.id for n in multiple_nodes],
        )

        with patch.object(strategy, '_drain_node', return_value=False):
            result = await strategy.execute(context)

        assert result is False
        assert context.status == DeploymentStatus.FAILED
        assert "Failed to drain" in context.error

    @pytest.mark.asyncio
    async def test_nonexistent_nodes_skipped(self, strategy):
        """Test nonexistent nodes are skipped."""
        context = DeploymentContext(
            deployment_id="maint-deploy",
            strategy=DeploymentStrategyType.MAINTENANCE_WINDOW,
            role_name="worker",
            target_nodes=["nonexistent-1", "nonexistent-2"],
        )

        result = await strategy.execute(context)

        # Should succeed with no nodes (nothing to do)
        assert result is True


class TestBlueGreenStrategy:
    """Test blue-green deployment strategy."""

    @pytest.fixture
    def strategy(self, db_service, mock_ssh):
        """Create blue-green strategy."""
        return BlueGreenStrategy(
            db=db_service,
            ssh=mock_ssh,
        )

    @pytest.fixture
    def blue_nodes(self, db_service):
        """Create blue nodes (current targets)."""
        nodes = []
        for i in range(2):
            node = db_service.create_node(
                name=f"blue-node-{i}",
                ip_address=f"192.168.1.{100 + i}",
                ssh_user="autobot",
                current_role="worker",
            )
            db_service.update_node_state(
                node_id=node.id,
                new_state=NodeState.ONLINE,
                trigger="test",
                validate_transition=False,
            )
            nodes.append(db_service.get_node(node.id))
        return nodes

    @pytest.fixture
    def spare_nodes(self, db_service):
        """Create spare nodes (no role)."""
        nodes = []
        for i in range(2):
            node = db_service.create_node(
                name=f"spare-node-{i}",
                ip_address=f"192.168.1.{200 + i}",
                ssh_user="autobot",
            )
            db_service.update_node_state(
                node_id=node.id,
                new_state=NodeState.ONLINE,
                trigger="test",
                validate_transition=False,
            )
            nodes.append(db_service.get_node(node.id))
        return nodes

    @pytest.mark.asyncio
    async def test_strategy_init(self, db_service, mock_ssh):
        """Test strategy initialization."""
        strategy = BlueGreenStrategy(
            db=db_service,
            ssh=mock_ssh,
        )

        assert strategy.db == db_service
        assert strategy.ssh == mock_ssh

    @pytest.mark.asyncio
    async def test_execute_with_spare_nodes(
        self, strategy, blue_nodes, spare_nodes
    ):
        """Test execution using spare nodes."""
        context = DeploymentContext(
            deployment_id="bg-deploy",
            strategy=DeploymentStrategyType.BLUE_GREEN,
            role_name="worker",
            target_nodes=[n.id for n in blue_nodes],
        )

        result = await strategy.execute(context)

        assert result is True
        assert context.status == DeploymentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_no_blue_nodes_fails(self, strategy):
        """Test fails when no blue nodes found."""
        context = DeploymentContext(
            deployment_id="bg-deploy",
            strategy=DeploymentStrategyType.BLUE_GREEN,
            role_name="worker",
            target_nodes=["nonexistent-1", "nonexistent-2"],
        )

        result = await strategy.execute(context)

        assert result is False
        assert context.status == DeploymentStatus.FAILED
        assert "No blue nodes" in context.error

    @pytest.mark.asyncio
    async def test_no_green_nodes_fails(self, strategy, blue_nodes):
        """Test fails when no green nodes available."""
        # Only blue nodes exist, no spares
        context = DeploymentContext(
            deployment_id="bg-deploy",
            strategy=DeploymentStrategyType.BLUE_GREEN,
            role_name="worker",
            target_nodes=[n.id for n in blue_nodes],
        )

        result = await strategy.execute(context)

        assert result is False
        assert context.status == DeploymentStatus.FAILED
        assert "Unable to acquire green nodes" in context.error

    @pytest.mark.asyncio
    async def test_borrow_from_role(self, strategy, db_service, blue_nodes):
        """Test borrowing nodes from another role."""
        # Create nodes with 'backup' role
        backup_nodes = []
        for i in range(2):
            node = db_service.create_node(
                name=f"backup-node-{i}",
                ip_address=f"192.168.1.{150 + i}",
                ssh_user="autobot",
                current_role="backup",
            )
            db_service.update_node_state(
                node_id=node.id,
                new_state=NodeState.ONLINE,
                trigger="test",
                validate_transition=False,
            )
            backup_nodes.append(db_service.get_node(node.id))

        context = DeploymentContext(
            deployment_id="bg-deploy",
            strategy=DeploymentStrategyType.BLUE_GREEN,
            role_name="worker",
            target_nodes=[n.id for n in blue_nodes],
            params={"borrow_from_role": "backup"},
        )

        result = await strategy.execute(context)

        assert result is True
        assert context.status == DeploymentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_playbook_execution(self, strategy, blue_nodes, spare_nodes):
        """Test playbook execution on green nodes."""
        context = DeploymentContext(
            deployment_id="bg-deploy",
            strategy=DeploymentStrategyType.BLUE_GREEN,
            role_name="worker",
            target_nodes=[n.id for n in blue_nodes],
            playbook_path="/path/to/playbook.yml",
        )

        with patch.object(
            SequentialDeploymentStrategy, '_run_playbook', return_value=True
        ):
            result = await strategy.execute(context)

        assert result is True

        # Should have playbook steps
        playbook_steps = [
            s for s in context.steps
            if s.step_type == DeploymentStepType.EXECUTE_PLAYBOOK
        ]
        assert len(playbook_steps) > 0

    @pytest.mark.asyncio
    async def test_playbook_failure_releases_nodes(
        self, strategy, blue_nodes, spare_nodes
    ):
        """Test playbook failure releases borrowed nodes."""
        context = DeploymentContext(
            deployment_id="bg-deploy",
            strategy=DeploymentStrategyType.BLUE_GREEN,
            role_name="worker",
            target_nodes=[n.id for n in blue_nodes],
            playbook_path="/path/to/playbook.yml",
        )

        with patch.object(
            SequentialDeploymentStrategy, '_run_playbook', return_value=False
        ):
            result = await strategy.execute(context)

        assert result is False
        assert context.status == DeploymentStatus.FAILED
        assert "Green deployment failed" in context.error

    @pytest.mark.asyncio
    async def test_traffic_switch(self, strategy, db_service, blue_nodes, spare_nodes):
        """Test traffic switch assigns role to green nodes."""
        context = DeploymentContext(
            deployment_id="bg-deploy",
            strategy=DeploymentStrategyType.BLUE_GREEN,
            role_name="new_worker",
            target_nodes=[n.id for n in blue_nodes],
        )

        result = await strategy.execute(context)

        assert result is True

        # Check green nodes have the role
        for spare in spare_nodes:
            updated = db_service.get_node(spare.id)
            assert updated.current_role == "new_worker"

    @pytest.mark.asyncio
    async def test_decommissions_blue_nodes(
        self, strategy, db_service, blue_nodes, spare_nodes
    ):
        """Test blue nodes are decommissioned."""
        context = DeploymentContext(
            deployment_id="bg-deploy",
            strategy=DeploymentStrategyType.BLUE_GREEN,
            role_name="worker",
            target_nodes=[n.id for n in blue_nodes],
        )

        result = await strategy.execute(context)

        assert result is True

        # Check blue nodes have no role
        for blue in blue_nodes:
            updated = db_service.get_node(blue.id)
            assert updated.current_role is None

    @pytest.mark.asyncio
    async def test_rollback(self, strategy, blue_nodes, spare_nodes):
        """Test rollback releases green nodes."""
        context = DeploymentContext(
            deployment_id="bg-deploy",
            strategy=DeploymentStrategyType.BLUE_GREEN,
            role_name="worker",
            target_nodes=[n.id for n in blue_nodes],
        )

        # Add a successful verify step to simulate completed switch
        context.steps.append(DeploymentStep(
            step_type=DeploymentStepType.VERIFY,
            node_id=spare_nodes[0].id,
            node_name=spare_nodes[0].name,
            description="Test",
            success=True,
        ))

        result = await strategy.rollback(context)

        assert result is True
        assert context.status == DeploymentStatus.ROLLED_BACK
        assert context.rollback_triggered is True

    @pytest.mark.asyncio
    async def test_rollback_no_green_nodes(self, strategy, blue_nodes):
        """Test rollback with no green nodes does nothing."""
        context = DeploymentContext(
            deployment_id="bg-deploy",
            strategy=DeploymentStrategyType.BLUE_GREEN,
            role_name="worker",
            target_nodes=[n.id for n in blue_nodes],
        )

        result = await strategy.rollback(context)

        assert result is False
