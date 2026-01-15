# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for SLM Remediator service.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.slm.remediator import (
    RemediationAction,
    RemediationResult,
    SLMRemediator,
    SSHExecutor,
)


class TestSSHExecutor:
    """Test SSH executor functionality."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful SSH command execution."""
        executor = SSHExecutor()

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock successful command
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"ok\n", b""))
            mock_exec.return_value = mock_proc

            returncode, stdout, stderr = await executor.execute(
                "192.168.1.1", "echo ok"
            )

            assert returncode == 0
            assert stdout == "ok\n"
            assert stderr == ""

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        """Test failed SSH command execution."""
        executor = SSHExecutor()

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(return_value=(b"", b"error\n"))
            mock_exec.return_value = mock_proc

            returncode, stdout, stderr = await executor.execute(
                "192.168.1.1", "false"
            )

            assert returncode == 1
            assert stderr == "error\n"

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test SSH command timeout."""
        executor = SSHExecutor(ssh_timeout=1)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_exec.return_value = mock_proc

            returncode, stdout, stderr = await executor.execute(
                "192.168.1.1", "sleep 60"
            )

            assert returncode == -1
            assert "timed out" in stderr

    @pytest.mark.asyncio
    async def test_check_connectivity_success(self):
        """Test connectivity check success."""
        executor = SSHExecutor()

        with patch.object(executor, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = (0, "ok", "")

            result = await executor.check_connectivity("192.168.1.1")

            assert result is True
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_connectivity_failure(self):
        """Test connectivity check failure."""
        executor = SSHExecutor()

        with patch.object(executor, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = (-1, "", "Connection refused")

            result = await executor.check_connectivity("192.168.1.1")

            assert result is False


class TestSLMRemediator:
    """Test SLM Remediator functionality."""

    @pytest.fixture
    def mock_ssh(self):
        """Create mock SSH executor."""
        executor = MagicMock(spec=SSHExecutor)
        executor.execute = AsyncMock(return_value=(0, "", ""))
        executor.check_connectivity = AsyncMock(return_value=True)
        return executor

    @pytest.fixture
    def remediator(self, mock_ssh):
        """Create remediator with mock SSH."""
        return SLMRemediator(ssh_executor=mock_ssh)

    @pytest.mark.asyncio
    async def test_restart_service_success(self, remediator, mock_ssh):
        """Test successful service restart."""
        mock_ssh.execute.return_value = (0, "", "")

        attempt = await remediator.restart_service(
            node_id="node-1",
            node_name="test-node",
            host="192.168.1.1",
            service_name="nginx",
        )

        assert attempt.result == RemediationResult.SUCCESS
        assert attempt.action == RemediationAction.RESTART_SERVICE
        assert attempt.node_id == "node-1"
        assert attempt.details["service"] == "nginx"

    @pytest.mark.asyncio
    async def test_restart_service_failure(self, remediator, mock_ssh):
        """Test failed service restart."""
        mock_ssh.execute.return_value = (1, "", "Failed to restart")

        attempt = await remediator.restart_service(
            node_id="node-1",
            node_name="test-node",
            host="192.168.1.1",
            service_name="nginx",
        )

        assert attempt.result == RemediationResult.FAILURE
        assert attempt.error == "Failed to restart"

    @pytest.mark.asyncio
    async def test_restart_service_timeout(self, remediator, mock_ssh):
        """Test service restart timeout."""
        mock_ssh.execute.return_value = (-1, "", "SSH command timed out")

        attempt = await remediator.restart_service(
            node_id="node-1",
            node_name="test-node",
            host="192.168.1.1",
            service_name="nginx",
        )

        assert attempt.result == RemediationResult.TIMEOUT

    @pytest.mark.asyncio
    async def test_restart_all_services_success(self, remediator, mock_ssh):
        """Test restarting all services successfully."""
        mock_ssh.execute.return_value = (0, "", "")

        attempts = await remediator.restart_all_services(
            node_id="node-1",
            node_name="test-node",
            host="192.168.1.1",
            services=["nginx", "redis-stack-server"],
        )

        assert len(attempts) == 2
        assert all(a.result == RemediationResult.SUCCESS for a in attempts)

    @pytest.mark.asyncio
    async def test_restart_all_services_stops_on_failure(self, remediator, mock_ssh):
        """Test that restart stops on first failure."""
        # First call succeeds, second fails
        mock_ssh.execute.side_effect = [
            (0, "", ""),
            (1, "", "Failed"),
        ]

        attempts = await remediator.restart_all_services(
            node_id="node-1",
            node_name="test-node",
            host="192.168.1.1",
            services=["nginx", "redis-stack-server", "another-service"],
        )

        # Should stop after second service fails
        assert len(attempts) == 2
        assert attempts[0].result == RemediationResult.SUCCESS
        assert attempts[1].result == RemediationResult.FAILURE

    @pytest.mark.asyncio
    async def test_check_node_reachable(self, remediator, mock_ssh):
        """Test node reachability check."""
        mock_ssh.check_connectivity.return_value = True

        attempt = await remediator.check_node_reachable(
            node_id="node-1",
            node_name="test-node",
            host="192.168.1.1",
        )

        assert attempt.result == RemediationResult.SUCCESS
        assert attempt.action == RemediationAction.HEALTH_CHECK
        assert attempt.details["reachable"] is True

    @pytest.mark.asyncio
    async def test_check_node_unreachable(self, remediator, mock_ssh):
        """Test node unreachability detection."""
        mock_ssh.check_connectivity.return_value = False

        attempt = await remediator.check_node_reachable(
            node_id="node-1",
            node_name="test-node",
            host="192.168.1.1",
        )

        assert attempt.result == RemediationResult.UNREACHABLE
        assert attempt.details["reachable"] is False

    def test_history_tracking(self, remediator):
        """Test that remediation attempts are tracked in history."""
        assert len(remediator.history) == 0

    @pytest.mark.asyncio
    async def test_history_populated_after_attempts(self, remediator, mock_ssh):
        """Test history is populated after remediation attempts."""
        mock_ssh.execute.return_value = (0, "", "")

        await remediator.restart_service(
            node_id="node-1",
            node_name="test-node",
            host="192.168.1.1",
            service_name="nginx",
        )

        assert len(remediator.history) == 1
        assert remediator.history[0].node_id == "node-1"

    @pytest.mark.asyncio
    async def test_get_history_for_node(self, remediator, mock_ssh):
        """Test filtering history by node."""
        mock_ssh.execute.return_value = (0, "", "")

        await remediator.restart_service(
            node_id="node-1", node_name="node1", host="192.168.1.1", service_name="nginx"
        )
        await remediator.restart_service(
            node_id="node-2", node_name="node2", host="192.168.1.2", service_name="nginx"
        )
        await remediator.restart_service(
            node_id="node-1", node_name="node1", host="192.168.1.1", service_name="redis"
        )

        node1_history = remediator.get_history_for_node("node-1")
        assert len(node1_history) == 2

        node2_history = remediator.get_history_for_node("node-2")
        assert len(node2_history) == 1
