# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Execution Backends (Issue #4343)

Tests cover local, Docker, SSH, and Modal execution backends.
Validates task routing, health checks, and result capture.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.execution.base_backend import (
    BackendType,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTask,
    ResourceLimits,
)
from services.execution.docker_backend import DockerBackend
from services.execution.execution_manager import ExecutionManager, get_execution_manager
from services.execution.local_backend import LocalBackend
from services.execution.modal_backend import ModalBackend
from services.execution.ssh_backend import SSHBackend


class TestExecutionTask:
    """Test ExecutionTask creation and validation."""

    def test_create_task_basic(self):
        """Test basic task creation."""
        task = ExecutionTask(
            task_id="test-1",
            code="print('hello')",
            language="python",
        )
        assert task.task_id == "test-1"
        assert task.code == "print('hello')"
        assert task.language == "python"
        assert task.timeout_seconds == 300  # Default

    def test_create_task_with_env_vars(self):
        """Test task with environment variables."""
        task = ExecutionTask(
            task_id="test-2",
            code="echo $MY_VAR",
            language="bash",
            env_vars={"MY_VAR": "hello"},
        )
        assert task.env_vars["MY_VAR"] == "hello"

    def test_create_task_with_custom_timeout(self):
        """Test task with custom timeout."""
        task = ExecutionTask(
            task_id="test-3",
            code="sleep 10",
            language="bash",
            timeout_seconds=60,
        )
        assert task.timeout_seconds == 60

    def test_task_validation_requires_id(self):
        """Test that task_id is required."""
        with pytest.raises(ValueError, match="task_id"):
            ExecutionTask(task_id="", code="print('hi')")

    def test_task_validation_requires_code(self):
        """Test that code is required."""
        with pytest.raises(ValueError, match="code"):
            ExecutionTask(task_id="test-4", code="")


class TestResourceLimits:
    """Test resource limit configuration."""

    def test_default_limits(self):
        """Test default resource limits."""
        limits = ResourceLimits()
        assert limits.cpu_cores == 1.0
        assert limits.memory_mb == 512
        assert limits.timeout_seconds == 300

    def test_custom_limits(self):
        """Test custom resource limits."""
        limits = ResourceLimits(
            cpu_cores=4.0,
            memory_mb=2048,
            timeout_seconds=600,
        )
        assert limits.cpu_cores == 4.0
        assert limits.memory_mb == 2048
        assert limits.timeout_seconds == 600

    def test_limits_to_dict(self):
        """Test limits serialization."""
        limits = ResourceLimits(cpu_cores=2.0, memory_mb=1024)
        data = limits.to_dict()
        assert data["cpu_cores"] == 2.0
        assert data["memory_mb"] == 1024


@pytest.mark.asyncio
class TestLocalBackend:
    """Test local execution backend."""

    async def test_execute_python_code(self):
        """Test executing Python code locally."""
        backend = LocalBackend()

        task = ExecutionTask(
            task_id="local-1",
            code="print('Hello from Local')",
            language="python",
            timeout_seconds=10,
        )

        result = await backend.execute(task)

        assert result.task_id == "local-1"
        assert result.status == ExecutionStatus.SUCCESS
        assert "Hello from Local" in result.stdout
        assert result.return_code == 0
        assert result.backend_type == "local"

    async def test_execute_bash_code(self):
        """Test executing bash code locally."""
        backend = LocalBackend()

        task = ExecutionTask(
            task_id="local-2",
            code="echo 'Hello from Bash'",
            language="bash",
            timeout_seconds=10,
        )

        result = await backend.execute(task)

        assert result.status == ExecutionStatus.SUCCESS
        assert "Hello from Bash" in result.stdout
        assert result.return_code == 0

    async def test_execute_with_failure(self):
        """Test execution failure capture."""
        backend = LocalBackend()

        task = ExecutionTask(
            task_id="local-3",
            code="exit 1",
            language="bash",
            timeout_seconds=10,
        )

        result = await backend.execute(task)

        assert result.status == ExecutionStatus.FAILED
        assert result.return_code == 1

    async def test_execute_with_timeout(self):
        """Test timeout handling."""
        backend = LocalBackend()

        task = ExecutionTask(
            task_id="local-4",
            code="sleep 10",
            language="bash",
            timeout_seconds=1,
        )

        result = await backend.execute(task)

        assert result.status == ExecutionStatus.TIMEOUT
        assert result.return_code == -1
        assert "timeout" in result.stderr.lower()

    async def test_execute_with_env_vars(self):
        """Test environment variable injection."""
        backend = LocalBackend()

        task = ExecutionTask(
            task_id="local-5",
            code="echo $TEST_VAR",
            language="bash",
            env_vars={"TEST_VAR": "test-value"},
            timeout_seconds=10,
        )

        result = await backend.execute(task)

        assert result.status == ExecutionStatus.SUCCESS
        assert "test-value" in result.stdout

    async def test_health_check(self):
        """Test backend health check."""
        backend = LocalBackend()
        is_healthy = await backend.health_check()
        assert is_healthy is True

    async def test_verify_compatibility_python(self):
        """Test Python compatibility check."""
        backend = LocalBackend()
        task = ExecutionTask(
            task_id="local-6",
            code="print('hi')",
            language="python",
        )
        is_compatible, reason = await backend.verify_task_compatibility(task)
        assert is_compatible is True

    async def test_verify_incompatible_language(self):
        """Test incompatible language detection."""
        backend = LocalBackend()
        task = ExecutionTask(
            task_id="local-7",
            code="console.log('hi')",
            language="ruby",
        )
        is_compatible, reason = await backend.verify_task_compatibility(task)
        assert is_compatible is False
        assert "ruby" in reason.lower()


@pytest.mark.asyncio
class TestDockerBackend:
    """Test Docker execution backend."""

    @pytest.fixture
    def mock_docker_client(self):
        """Fixture for mocked Docker client."""
        with patch("services.execution.docker_backend.docker") as mock_docker:
            client = MagicMock()
            mock_docker.from_env.return_value = client
            client.ping.return_value = None
            yield client

    async def test_initialization_with_docker(self, mock_docker_client):
        """Test Docker backend initialization."""
        backend = DockerBackend()
        assert backend.client is not None
        assert backend.backend_type == BackendType.DOCKER

    async def test_initialization_without_docker(self):
        """Test error when Docker is not available."""
        with patch(
            "services.execution.docker_backend.docker", None
        ):
            with pytest.raises(RuntimeError, match="docker"):
                DockerBackend()

    async def test_health_check_docker(self, mock_docker_client):
        """Test Docker health check."""
        backend = DockerBackend()
        is_healthy = await backend.health_check()
        assert is_healthy is True

    async def test_verify_compatibility(self, mock_docker_client):
        """Test Docker task compatibility."""
        backend = DockerBackend()
        task = ExecutionTask(
            task_id="docker-1",
            code="print('hi')",
            language="python",
        )
        is_compatible, reason = await backend.verify_task_compatibility(task)
        assert is_compatible is True


class TestSSHBackend:
    """Test SSH execution backend."""

    def test_initialization_without_paramiko(self):
        """Test error when paramiko is not available."""
        with patch("services.execution.ssh_backend.paramiko", None):
            with pytest.raises(RuntimeError, match="paramiko"):
                SSHBackend(
                    hostname="localhost",
                    username="user",
                )

    async def test_verify_compatibility(self):
        """Test SSH task compatibility."""
        try:
            backend = SSHBackend(
                hostname="localhost",
                username="user",
                password="pass",
            )
            task = ExecutionTask(
                task_id="ssh-1",
                code="echo 'hi'",
                language="bash",
            )
            is_compatible, reason = await backend.verify_task_compatibility(task)
            assert is_compatible is True
        except RuntimeError:
            # Skip if paramiko not installed
            pytest.skip("paramiko not installed")


class TestModalBackend:
    """Test Modal execution backend."""

    def test_initialization_without_modal(self):
        """Test error when Modal is not available."""
        with patch("services.execution.modal_backend.modal", None):
            with pytest.raises(RuntimeError, match="modal"):
                ModalBackend()

    async def test_verify_compatibility(self):
        """Test Modal task compatibility."""
        try:
            backend = ModalBackend()
            task = ExecutionTask(
                task_id="modal-1",
                code="print('hi')",
                language="python",
            )
            is_compatible, reason = await backend.verify_task_compatibility(task)
            assert is_compatible is True
        except RuntimeError:
            # Skip if modal not installed
            pytest.skip("modal not installed")

    async def test_verify_incompatible_language(self):
        """Test Modal language restrictions."""
        try:
            backend = ModalBackend()
            task = ExecutionTask(
                task_id="modal-2",
                code="echo 'hi'",
                language="bash",
            )
            is_compatible, reason = await backend.verify_task_compatibility(task)
            assert is_compatible is False
            assert "python" in reason.lower()
        except RuntimeError:
            pytest.skip("modal not installed")


class TestExecutionManager:
    """Test execution manager and routing."""

    def test_register_backend(self):
        """Test backend registration."""
        manager = ExecutionManager()
        backend = LocalBackend()

        manager.register_backend(BackendType.LOCAL, backend)

        assert BackendType.LOCAL in manager.backends
        assert manager.backends[BackendType.LOCAL] is backend

    def test_enable_disable_backend(self):
        """Test enabling/disabling backends."""
        manager = ExecutionManager()
        backend = LocalBackend()
        manager.register_backend(BackendType.LOCAL, backend)

        assert BackendType.LOCAL in manager._enabled_backends

        manager.disable_backend(BackendType.LOCAL)
        assert BackendType.LOCAL not in manager._enabled_backends

        manager.enable_backend(BackendType.LOCAL)
        assert BackendType.LOCAL in manager._enabled_backends

    @pytest.mark.asyncio
    async def test_execute_task_local(self):
        """Test task execution on local backend."""
        manager = ExecutionManager()
        manager.register_backend(BackendType.LOCAL, LocalBackend())

        task = ExecutionTask(
            task_id="mgr-1",
            code="print('Managed')",
            language="python",
            timeout_seconds=10,
        )

        result = await manager.execute(task)

        assert result.status == ExecutionStatus.SUCCESS
        assert "Managed" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_with_preferred_backend(self):
        """Test preferred backend selection."""
        manager = ExecutionManager()
        manager.register_backend(BackendType.LOCAL, LocalBackend())

        task = ExecutionTask(
            task_id="mgr-2",
            code="echo 'test'",
            language="bash",
            timeout_seconds=10,
        )

        result = await manager.execute(task, preferred_backend=BackendType.LOCAL)

        assert result.status == ExecutionStatus.SUCCESS
        assert result.backend_type == "local"

    @pytest.mark.asyncio
    async def test_health_check_all(self):
        """Test health check for all backends."""
        manager = ExecutionManager()
        manager.register_backend(BackendType.LOCAL, LocalBackend())

        health = await manager.health_check_all()

        assert "local" in health
        assert health["local"] is True

    @pytest.mark.asyncio
    async def test_cleanup_all(self):
        """Test cleanup of all backends."""
        manager = ExecutionManager()
        backend = LocalBackend()
        manager.register_backend(BackendType.LOCAL, backend)

        # Should not raise
        await manager.cleanup_all()

    def test_get_backend_info(self):
        """Test getting backend information."""
        manager = ExecutionManager()
        manager.register_backend(BackendType.LOCAL, LocalBackend())

        info = manager.get_backend_info()

        assert "local" in info
        assert "healthy" in info["local"]
        assert "enabled" in info["local"]

    def test_set_routing_policy(self):
        """Test routing policy configuration."""
        manager = ExecutionManager()

        manager.set_routing_policy("smart")
        assert manager._routing_policy == "smart"

        manager.set_routing_policy("first_available")
        assert manager._routing_policy == "first_available"

        with pytest.raises(ValueError):
            manager.set_routing_policy("invalid")

    @pytest.mark.asyncio
    async def test_no_backends_available(self):
        """Test error when no backends are available."""
        manager = ExecutionManager()

        task = ExecutionTask(
            task_id="mgr-3",
            code="echo 'test'",
            language="bash",
        )

        with pytest.raises(RuntimeError, match="No suitable backends"):
            await manager.execute(task)

    def test_get_execution_manager_singleton(self):
        """Test singleton pattern for execution manager."""
        manager1 = get_execution_manager()
        manager2 = get_execution_manager()

        assert manager1 is manager2


class TestExecutionResult:
    """Test execution result handling."""

    def test_result_serialization(self):
        """Test result can be serialized to dict."""
        import datetime

        result = ExecutionResult(
            task_id="test-1",
            status=ExecutionStatus.SUCCESS,
            stdout="output",
            stderr="",
            return_code=0,
            started_at=datetime.datetime.utcnow(),
            completed_at=datetime.datetime.utcnow(),
        )

        data = result.to_dict()

        assert data["task_id"] == "test-1"
        assert data["status"] == "success"
        assert isinstance(data["started_at"], str)
        assert isinstance(data["completed_at"], str)

    def test_result_with_metadata(self):
        """Test result metadata handling."""
        result = ExecutionResult(
            task_id="test-2",
            status=ExecutionStatus.SUCCESS,
            metadata={"run_id": "abc123", "cost": 0.01},
        )

        assert result.metadata["run_id"] == "abc123"
        assert result.metadata["cost"] == 0.01
