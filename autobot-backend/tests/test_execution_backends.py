# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Execution Backends (Issue #4343)

Tests cover local, Docker, SSH, and Modal execution backends.
Validates task routing, health checks, and result capture.
"""

from unittest.mock import MagicMock, patch

import pytest

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
        """Allowlisted AUTOBOT_* task env vars reach the subprocess."""
        backend = LocalBackend()

        task = ExecutionTask(
            task_id="local-5",
            code="echo $AUTOBOT_TEST_VAR",
            language="bash",
            env_vars={"AUTOBOT_TEST_VAR": "test-value"},
            timeout_seconds=10,
        )

        result = await backend.execute(task)

        assert result.status == ExecutionStatus.SUCCESS
        assert "test-value" in result.stdout

    async def test_execute_drops_non_allowlisted_env_var(self):
        """A non-AUTOBOT_ task env var is dropped and never reaches the subprocess."""
        backend = LocalBackend()

        task = ExecutionTask(
            task_id="local-5b",
            code="echo [$TEST_VAR]",
            language="bash",
            env_vars={"TEST_VAR": "leak"},
            timeout_seconds=10,
        )

        result = await backend.execute(task)

        assert result.status == ExecutionStatus.SUCCESS
        assert "leak" not in result.stdout

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
        with patch("services.execution.docker_backend.docker", None):
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


def _make_modal_mock() -> MagicMock:
    """Build a minimal modal module mock that satisfies ModalBackend init checks."""
    mock_modal = MagicMock()

    # App lookup
    mock_app = MagicMock()
    mock_modal.App.lookup.return_value = mock_app

    # Image
    mock_image = MagicMock()
    mock_modal.Image.debian_slim.return_value = mock_image

    # Secret
    mock_modal.Secret.from_dict.return_value = MagicMock()

    # Sandbox + proc
    mock_proc = MagicMock()
    mock_proc.stdout.read.return_value = "hello from sandbox\n"
    mock_proc.stderr.read.return_value = ""
    mock_proc.wait.return_value = None
    mock_proc.returncode = 0

    mock_sandbox = MagicMock()
    mock_sandbox.exec.return_value = mock_proc
    mock_sandbox.object_id = "sandbox-abc123"
    mock_modal.Sandbox.create.return_value = mock_sandbox

    return mock_modal


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


# ---------------------------------------------------------------------------
# Modal Sandbox dispatch tests (Issue #11003)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestModalSandboxDispatch:
    """Unit tests for real Modal Sandbox dispatch (Issue #11003).

    All tests monkeypatch ``services.execution.modal_backend.modal`` with a
    MagicMock so no real Modal SDK or network is required.
    """

    def _make_backend(self, monkeypatch) -> "ModalBackend":
        mock_modal = _make_modal_mock()
        monkeypatch.setattr("services.execution.modal_backend.modal", mock_modal)
        # Supply a fake token so health_check passes
        return ModalBackend(api_token="test-token"), mock_modal

    # (a) Successful run returns stdout / return_code 0 / status SUCCESS
    async def test_successful_run(self, monkeypatch):
        """Sandbox exec with rc=0 produces SUCCESS result with correct stdout."""
        backend, mock_modal = self._make_backend(monkeypatch)
        task = ExecutionTask(task_id="sb-1", code="print('hi')", language="python", timeout_seconds=30)

        result = await backend.execute(task)

        assert result.status == ExecutionStatus.SUCCESS
        assert result.return_code == 0
        assert "hello from sandbox" in result.stdout
        assert result.metadata["modal_run_id"] == "sandbox-abc123"

    # (b) Non-zero returncode → FAILED
    async def test_nonzero_returncode_gives_failed(self, monkeypatch):
        """Sandbox proc returning rc=1 maps to ExecutionStatus.FAILED."""
        backend, mock_modal = self._make_backend(monkeypatch)
        mock_modal.Sandbox.create.return_value.exec.return_value.returncode = 1
        mock_modal.Sandbox.create.return_value.exec.return_value.stderr.read.return_value = "oops"

        task = ExecutionTask(task_id="sb-2", code="raise SystemExit(1)", language="python")

        result = await backend.execute(task)

        assert result.status == ExecutionStatus.FAILED
        assert result.return_code == 1

    # (c) modal is None → RuntimeError / health_check False / no code execution
    async def test_modal_none_raises_runtime_error(self, monkeypatch):
        """When modal is None, _call_modal_function raises RuntimeError immediately."""
        monkeypatch.setattr("services.execution.modal_backend.modal", None)

        # health_check must return False
        # We cannot instantiate ModalBackend with modal=None — verify that too
        with pytest.raises(RuntimeError, match="modal"):
            ModalBackend()

    async def test_health_check_false_when_modal_none(self, monkeypatch):
        """health_check returns False when modal module is absent."""
        backend, mock_modal = self._make_backend(monkeypatch)
        # Patch modal away after construction
        monkeypatch.setattr("services.execution.modal_backend.modal", None)
        result = await backend.health_check()
        assert result is False

    async def test_health_check_false_when_no_credentials(self, monkeypatch):
        """health_check returns False when no api_token and no env vars."""
        mock_modal = _make_modal_mock()
        monkeypatch.setattr("services.execution.modal_backend.modal", mock_modal)
        monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
        monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)

        backend = ModalBackend(api_token=None)
        assert await backend.health_check() is False

    async def test_health_check_true_with_api_token(self, monkeypatch):
        """health_check returns True when api_token is set at construction."""
        backend, _ = self._make_backend(monkeypatch)
        assert await backend.health_check() is True

    async def test_health_check_true_with_env_token_id(self, monkeypatch):
        """health_check returns True when MODAL_TOKEN_ID env var is present."""
        mock_modal = _make_modal_mock()
        monkeypatch.setattr("services.execution.modal_backend.modal", mock_modal)
        monkeypatch.setenv("MODAL_TOKEN_ID", "tid-123")
        monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)

        backend = ModalBackend(api_token=None)
        assert await backend.health_check() is True

    # (d) Env vars passed via modal.Secret.from_dict; AUTOBOT_*/hijack names stripped
    async def test_env_vars_passed_via_secret(self, monkeypatch):
        """Allowed AUTOBOT_* env vars reach modal.Secret.from_dict."""
        backend, mock_modal = self._make_backend(monkeypatch)
        task = ExecutionTask(
            task_id="sb-3",
            code="print('env')",
            language="python",
            env_vars={"AUTOBOT_MY_VAR": "value123", "SECRET_SAUCE": "should-be-dropped"},
        )

        await backend.execute(task)

        mock_modal.Secret.from_dict.assert_called_once()
        passed_dict = mock_modal.Secret.from_dict.call_args[0][0]
        assert "AUTOBOT_MY_VAR" in passed_dict
        assert passed_dict["AUTOBOT_MY_VAR"] == "value123"
        assert "SECRET_SAUCE" not in passed_dict

    async def test_hijack_env_vars_stripped(self, monkeypatch):
        """PYTHONPATH, LD_PRELOAD and other hijack names are stripped."""
        backend, mock_modal = self._make_backend(monkeypatch)
        task = ExecutionTask(
            task_id="sb-4",
            code="print('safe')",
            language="python",
            env_vars={
                "PYTHONPATH": "/evil",
                "LD_PRELOAD": "/evil.so",
                "NODE_OPTIONS": "--require /evil",
                "AUTOBOT_SAFE": "ok",
            },
        )

        await backend.execute(task)

        mock_modal.Secret.from_dict.assert_called_once()
        passed_dict = mock_modal.Secret.from_dict.call_args[0][0]
        for bad_key in ("PYTHONPATH", "LD_PRELOAD", "NODE_OPTIONS"):
            assert bad_key not in passed_dict
        assert "AUTOBOT_SAFE" in passed_dict

    async def test_no_secret_when_env_vars_empty(self, monkeypatch):
        """modal.Secret.from_dict is NOT called when env_vars is empty."""
        backend, mock_modal = self._make_backend(monkeypatch)
        task = ExecutionTask(task_id="sb-5", code="print('no env')", language="python", env_vars={})

        await backend.execute(task)

        mock_modal.Secret.from_dict.assert_not_called()
        # Sandbox.create should have been called with secrets=[]
        call_kwargs = mock_modal.Sandbox.create.call_args[1]
        assert call_kwargs.get("secrets") == []

    # (e) sandbox.terminate() is always called (finally)
    async def test_sandbox_terminate_always_called(self, monkeypatch):
        """sandbox.terminate() is called even when sandbox.exec raises."""
        backend, mock_modal = self._make_backend(monkeypatch)
        mock_sandbox = mock_modal.Sandbox.create.return_value
        mock_sandbox.exec.side_effect = RuntimeError("sandbox exploded")

        task = ExecutionTask(task_id="sb-6", code="bad code", language="python")

        result = await backend.execute(task)

        mock_sandbox.terminate.assert_called_once()
        assert result.status == ExecutionStatus.FAILED

    async def test_sandbox_terminate_called_on_success(self, monkeypatch):
        """sandbox.terminate() is called on the happy path too."""
        backend, mock_modal = self._make_backend(monkeypatch)
        mock_sandbox = mock_modal.Sandbox.create.return_value

        task = ExecutionTask(task_id="sb-7", code="print('done')", language="python")
        await backend.execute(task)

        mock_sandbox.terminate.assert_called_once()

    # Assert exec() is NEVER used to run task code in-process
    async def test_builtin_exec_never_called(self, monkeypatch):
        """The built-in exec() must not be used to run task code."""
        backend, _ = self._make_backend(monkeypatch)
        task = ExecutionTask(task_id="sb-8", code="x = 1 + 1", language="python")

        # Patch builtins.exec to fail hard if called
        import builtins

        original_exec = builtins.exec

        def _no_exec(code, *args, **kwargs):
            raise AssertionError("exec() was called with task code — this is the RCE bug!")

        monkeypatch.setattr(builtins, "exec", _no_exec)
        try:
            result = await backend.execute(task)
        finally:
            monkeypatch.setattr(builtins, "exec", original_exec)

        # If we reach here, exec() was not called in-process
        assert result.status == ExecutionStatus.SUCCESS

    # App caching
    async def test_app_lookup_called_only_once(self, monkeypatch):
        """modal.App.lookup is called once and the result is cached."""
        backend, mock_modal = self._make_backend(monkeypatch)
        task = ExecutionTask(task_id="sb-9", code="pass", language="python")

        await backend.execute(task)
        await backend.execute(task)

        mock_modal.App.lookup.assert_called_once_with(ModalBackend._APP_NAME, create_if_missing=True)


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
            started_at=datetime.datetime.now(datetime.timezone.utc),
            completed_at=datetime.datetime.now(datetime.timezone.utc),
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


# ---------------------------------------------------------------------------
# Snapshot / restore tests (GH#4458)
# ---------------------------------------------------------------------------


class TestSnapshotIndex:
    """Unit tests for SnapshotIndex file-based storage."""

    def test_add_and_get(self, tmp_path):
        pass

        from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord

        idx = SnapshotIndex(storage_path=tmp_path)
        rec = SnapshotRecord(
            snapshot_id="abc123",
            session_id="sess-1",
            container_id="cont-xyz",
            image_name="autobot-snapshot-abc123:latest",
            created_at="2025-01-01T00:00:00",
            size_bytes=1024,
        )
        idx.add(rec)
        fetched = idx.get("abc123")
        assert fetched is not None
        assert fetched.snapshot_id == "abc123"
        assert fetched.session_id == "sess-1"
        assert fetched.size_bytes == 1024

    def test_get_missing_returns_none(self, tmp_path):
        from services.execution.snapshot_index import SnapshotIndex

        idx = SnapshotIndex(storage_path=tmp_path)
        assert idx.get("does-not-exist") is None

    def test_list_by_session(self, tmp_path):
        from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord

        idx = SnapshotIndex(storage_path=tmp_path)
        for i in range(3):
            idx.add(
                SnapshotRecord(
                    snapshot_id=f"snap{i}",
                    session_id="sess-A" if i < 2 else "sess-B",
                    container_id=f"c{i}",
                    image_name=f"autobot-snapshot-snap{i}:latest",
                    created_at="2025-01-01T00:00:00",
                )
            )
        sess_a = idx.list_by_session("sess-A")
        assert len(sess_a) == 2
        assert all(r.session_id == "sess-A" for r in sess_a)

    def test_remove(self, tmp_path):
        from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord

        idx = SnapshotIndex(storage_path=tmp_path)
        rec = SnapshotRecord(
            snapshot_id="del-me",
            session_id="s",
            container_id="c",
            image_name="autobot-snapshot-del-me:latest",
            created_at="2025-01-01T00:00:00",
        )
        idx.add(rec)
        assert idx.remove("del-me") is True
        assert idx.get("del-me") is None
        assert idx.remove("del-me") is False  # idempotent

    def test_index_survives_empty_file(self, tmp_path):
        from services.execution.snapshot_index import SnapshotIndex

        idx_file = tmp_path / "snapshot_index.json"
        idx_file.write_text("", encoding="utf-8")
        idx = SnapshotIndex(storage_path=tmp_path)
        assert idx.list_all() == []


class TestDockerBackendSnapshot:
    """Tests for DockerBackend snapshot/restore (GH#4458)."""

    def _make_backend(self, tmp_path):
        from services.execution.snapshot_index import SnapshotIndex

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("services.execution.docker_backend.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.DockerException = Exception
            idx = SnapshotIndex(storage_path=tmp_path)
            backend = DockerBackend(snapshot_index=idx)
            backend.client = mock_client
            return backend, mock_client, idx

    @pytest.mark.asyncio
    async def test_snapshot_creates_record(self, tmp_path):
        backend, mock_client, idx = self._make_backend(tmp_path)

        mock_container = MagicMock()
        mock_image = MagicMock()
        mock_image.attrs = {"Size": 4096}
        mock_container.commit.return_value = mock_image
        mock_client.containers.get.return_value = mock_container

        record = await backend.snapshot("cont-abc", session_id="sess-xyz")

        assert record.session_id == "sess-xyz"
        assert record.container_id == "cont-abc"
        assert record.size_bytes == 4096
        assert record.image_name.startswith("autobot-snapshot-")
        stored = idx.get(record.snapshot_id)
        assert stored is not None
        assert stored.snapshot_id == record.snapshot_id

    @pytest.mark.asyncio
    async def test_snapshot_raises_on_missing_container(self, tmp_path):
        backend, mock_client, _ = self._make_backend(tmp_path)
        mock_client.containers.get.side_effect = Exception("Not found")

        with pytest.raises(RuntimeError, match="Failed to snapshot"):
            await backend.snapshot("no-such-container")

    @pytest.mark.asyncio
    async def test_restore_starts_container(self, tmp_path):
        from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord

        idx = SnapshotIndex(storage_path=tmp_path)
        idx.add(
            SnapshotRecord(
                snapshot_id="snap-001",
                session_id="sess-1",
                container_id="orig-cont",
                image_name="autobot-snapshot-snap-001:latest",
                created_at="2025-01-01T00:00:00",
            )
        )

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("services.execution.docker_backend.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.DockerException = Exception
            backend = DockerBackend(snapshot_index=idx)
            backend.client = mock_client

        mock_new_container = MagicMock()
        mock_new_container.id = "new-cont-id-123"
        mock_client.containers.run.return_value = mock_new_container

        new_id = await backend.restore("snap-001", caller_user_id="__system__")

        assert new_id == "new-cont-id-123"
        mock_client.containers.run.assert_called_once_with(
            "autobot-snapshot-snap-001:latest",
            "sleep infinity",
            detach=True,
            remove=False,
        )

    @pytest.mark.asyncio
    async def test_restore_raises_for_unknown_snapshot(self, tmp_path):
        from services.execution.snapshot_index import SnapshotIndex

        idx = SnapshotIndex(storage_path=tmp_path)
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("services.execution.docker_backend.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.DockerException = Exception
            backend = DockerBackend(snapshot_index=idx)
            backend.client = mock_client

        with pytest.raises(KeyError, match="not found"):
            await backend.restore("nonexistent-snap", caller_user_id="__system__")

    @pytest.mark.asyncio
    async def test_delete_snapshot_removes_record(self, tmp_path):
        backend, mock_client, idx = self._make_backend(tmp_path)

        mock_container = MagicMock()
        mock_image = MagicMock()
        mock_image.attrs = {"Size": 512}
        mock_container.commit.return_value = mock_image
        mock_client.containers.get.return_value = mock_container

        record = await backend.snapshot("cont-del", session_id="s")
        assert idx.get(record.snapshot_id) is not None

        deleted = await backend.delete_snapshot(record.snapshot_id, caller_user_id="__system__")
        assert deleted is True
        assert idx.get(record.snapshot_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_snapshot_returns_false(self, tmp_path):
        backend, _, _ = self._make_backend(tmp_path)
        result = await backend.delete_snapshot("ghost-snap", caller_user_id="__system__")
        assert result is False

    # ------------------------------------------------------------------
    # Ownership checks (GH#8968)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_restore_owner_can_restore(self, tmp_path):
        """Snapshot owner is allowed to restore."""
        from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord

        idx = SnapshotIndex(storage_path=tmp_path)
        idx.add(
            SnapshotRecord(
                snapshot_id="own-snap",
                session_id="s",
                container_id="c",
                image_name="autobot-snapshot-own-snap:latest",
                created_at="2025-01-01T00:00:00",
                user_id="user-alice",
            )
        )
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("services.execution.docker_backend.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.DockerException = Exception
            backend = DockerBackend(snapshot_index=idx)
            backend.client = mock_client

        mock_new_container = MagicMock()
        mock_new_container.id = "restored-id"
        mock_client.containers.run.return_value = mock_new_container

        new_id = await backend.restore("own-snap", caller_user_id="user-alice")
        assert new_id == "restored-id"

    @pytest.mark.asyncio
    async def test_restore_wrong_user_raises_permission_error(self, tmp_path):
        """A user who does not own the snapshot cannot restore it."""
        from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord

        idx = SnapshotIndex(storage_path=tmp_path)
        idx.add(
            SnapshotRecord(
                snapshot_id="priv-snap",
                session_id="s",
                container_id="c",
                image_name="autobot-snapshot-priv-snap:latest",
                created_at="2025-01-01T00:00:00",
                user_id="user-alice",
            )
        )
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("services.execution.docker_backend.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.DockerException = Exception
            backend = DockerBackend(snapshot_index=idx)
            backend.client = mock_client

        with pytest.raises(PermissionError, match="not authorised"):
            await backend.restore("priv-snap", caller_user_id="user-bob")

    @pytest.mark.asyncio
    async def test_restore_no_user_id_on_snapshot_allows_any_caller(self, tmp_path):
        """Legacy snapshots (no user_id) are accessible to any caller."""
        from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord

        idx = SnapshotIndex(storage_path=tmp_path)
        idx.add(
            SnapshotRecord(
                snapshot_id="legacy-snap",
                session_id="s",
                container_id="c",
                image_name="autobot-snapshot-legacy-snap:latest",
                created_at="2025-01-01T00:00:00",
            )
        )
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("services.execution.docker_backend.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.DockerException = Exception
            backend = DockerBackend(snapshot_index=idx)
            backend.client = mock_client

        mock_new_container = MagicMock()
        mock_new_container.id = "legacy-new"
        mock_client.containers.run.return_value = mock_new_container

        new_id = await backend.restore("legacy-snap", caller_user_id="user-anyone")
        assert new_id == "legacy-new"

    @pytest.mark.asyncio
    async def test_delete_wrong_user_raises_permission_error(self, tmp_path):
        """A user who does not own the snapshot cannot delete it."""
        from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord

        idx = SnapshotIndex(storage_path=tmp_path)
        idx.add(
            SnapshotRecord(
                snapshot_id="del-priv",
                session_id="s",
                container_id="c",
                image_name="autobot-snapshot-del-priv:latest",
                created_at="2025-01-01T00:00:00",
                user_id="user-alice",
            )
        )
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("services.execution.docker_backend.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.DockerException = Exception
            backend = DockerBackend(snapshot_index=idx)
            backend.client = mock_client

        with pytest.raises(PermissionError, match="not authorised"):
            await backend.delete_snapshot("del-priv", caller_user_id="user-bob")

    @pytest.mark.asyncio
    async def test_delete_owner_can_delete(self, tmp_path):
        """Snapshot owner is allowed to delete their snapshot."""
        backend, mock_client, idx = self._make_backend(tmp_path)

        mock_container = MagicMock()
        mock_image = MagicMock()
        mock_image.attrs = {"Size": 512}
        mock_container.commit.return_value = mock_image
        mock_client.containers.get.return_value = mock_container

        record = await backend.snapshot("cont-owned", session_id="s", user_id="user-alice")
        assert idx.get(record.snapshot_id) is not None

        deleted = await backend.delete_snapshot(record.snapshot_id, caller_user_id="user-alice")
        assert deleted is True
        assert idx.get(record.snapshot_id) is None

    @pytest.mark.asyncio
    async def test_system_caller_bypasses_ownership_on_restore(self, tmp_path):
        """_SYSTEM_CALLER can restore any snapshot regardless of user_id."""
        from services.execution.docker_backend import _SYSTEM_CALLER
        from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord

        idx = SnapshotIndex(storage_path=tmp_path)
        idx.add(
            SnapshotRecord(
                snapshot_id="sys-snap",
                session_id="s",
                container_id="c",
                image_name="autobot-snapshot-sys-snap:latest",
                created_at="2025-01-01T00:00:00",
                user_id="user-alice",
            )
        )
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("services.execution.docker_backend.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.DockerException = Exception
            backend = DockerBackend(snapshot_index=idx)
            backend.client = mock_client

        mock_new_container = MagicMock()
        mock_new_container.id = "sys-restored-id"
        mock_client.containers.run.return_value = mock_new_container

        new_id = await backend.restore("sys-snap", caller_user_id=_SYSTEM_CALLER)
        assert new_id == "sys-restored-id"

    @pytest.mark.asyncio
    async def test_get_snapshots_for_session(self, tmp_path):
        from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord

        idx = SnapshotIndex(storage_path=tmp_path)
        for i in range(2):
            idx.add(
                SnapshotRecord(
                    snapshot_id=f"s{i}",
                    session_id="sess-Q",
                    container_id=f"c{i}",
                    image_name=f"autobot-snapshot-s{i}:latest",
                    created_at="2025-01-01T00:00:00",
                )
            )

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("services.execution.docker_backend.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.DockerException = Exception
            backend = DockerBackend(snapshot_index=idx)
            backend.client = mock_client

        records = await backend.get_snapshots_for_session("sess-Q")
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_snapshot_env_var_storage_path(self, tmp_path, monkeypatch):
        """AUTOBOT_SNAPSHOT_STORAGE_PATH controls where the index is stored."""
        monkeypatch.setenv("AUTOBOT_SNAPSHOT_STORAGE_PATH", str(tmp_path))

        from services.execution.snapshot_index import SnapshotIndex

        idx = SnapshotIndex()
        assert idx._storage_path == tmp_path

    @pytest.mark.asyncio
    async def test_existing_ephemeral_execution_unchanged(self, tmp_path):
        """Snapshot feature must not affect normal cold-start execution."""
        from services.execution.snapshot_index import SnapshotIndex

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        mock_container = MagicMock()
        mock_container.id = "ephemeral-id"
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = b"hello"
        mock_client.containers.run.return_value = mock_container

        snapshot_idx = SnapshotIndex(storage_path=tmp_path)
        with patch("services.execution.docker_backend.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.DockerException = Exception
            backend = DockerBackend(snapshot_index=snapshot_idx)
            backend.client = mock_client

        task = ExecutionTask(task_id="t1", code="print('hi')", language="python")
        result = await backend._execute_cold(task, "python:3.10-slim")

        assert result.status == ExecutionStatus.SUCCESS
        assert result.stdout == "hello"
        assert snapshot_idx.list_all() == []  # no snapshots created by normal execution
