"""
Integration tests for security system end-to-end workflows
Tests how security components work together with the rest of the AutoBot system
"""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import system components
from backend.app_factory import create_app
from fastapi.testclient import TestClient
from src.enhanced_security_layer import EnhancedSecurityLayer
from src.secure_command_executor import CommandRisk, SecureCommandExecutor


@pytest.fixture
def temp_audit_file():
    """Create temporary audit log file"""
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.close()
    yield temp_file.name
    try:
        os.unlink(temp_file.name)
    except OSError:
        pass


@pytest.fixture
def security_layer(temp_audit_file):
    """Create enhanced security layer for testing"""
    with patch("src.enhanced_security_layer.global_config_manager") as mock_config:
        mock_config.get.return_value = {
            "enable_auth": False,
            "enable_command_security": True,
            "audit_log_file": temp_audit_file,
            "command_approval_required": False,  # Simplify for integration tests
            "use_docker_sandbox": False,
            "roles": {
                "admin": {"permissions": ["allow_all", "allow_shell_execute"]},
                "guest": {"permissions": ["read_only"]},
            },
        }
        return EnhancedSecurityLayer()


class TestSecuritySystemIntegration:
    """Integration tests for security system components"""

    def test_security_layer_command_executor_integration(self, security_layer):
        """Test integration between security layer and command executor"""
        # Test that security layer has a properly configured command executor
        assert security_layer.command_executor is not None
        assert isinstance(security_layer.command_executor, SecureCommandExecutor)

        # Test policy configuration
        policy = security_layer.command_executor.policy
        assert "echo" in policy.safe_commands
        assert "sudo" in policy.high_risk_commands
        assert len(policy.dangerous_patterns) > 0

    @pytest.mark.asyncio
    async def test_end_to_end_safe_command_execution(self, security_layer):
        """Test complete safe command execution workflow"""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"test output\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await security_layer.execute_command(
                "echo 'integration test'", "test_user", "admin"
            )

            # Verify successful execution
            assert result["status"] == "success"
            assert result["stdout"] == "test output"
            assert result["security"]["risk"] == "safe"

            # Verify audit logging
            history = security_layer.get_command_history(limit=10)
            assert len(history) >= 2  # Should have attempt + complete entries

            # Check that command was logged
            command_logged = any(
                "echo 'integration test'" in entry.get("details", {}).get("command", "")
                for entry in history
            )
            assert command_logged

    @pytest.mark.asyncio
    async def test_end_to_end_forbidden_command_blocking(self, security_layer):
        """Test complete forbidden command blocking workflow"""
        result = await security_layer.execute_command("rm -rf /", "test_user", "admin")

        # Verify command was blocked
        assert result["status"] == "error"
        assert "Command forbidden" in result["stderr"]
        assert result["security"]["blocked"] is True
        assert result["security"]["risk"] == "forbidden"

        # Verify audit logging
        history = security_layer.get_command_history(limit=10)
        blocked_logged = any(
            entry.get("action") == "command_execution_attempt"
            and "rm -rf /" in entry.get("details", {}).get("command", "")
            for entry in history
        )
        assert blocked_logged

    @pytest.mark.asyncio
    async def test_role_based_access_control_workflow(self, security_layer):
        """Test role-based access control in command execution"""
        security_layer.enable_auth = True

        # Admin should be able to execute commands
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"admin output\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await security_layer.execute_command(
                "ls -la", "admin_user", "admin"
            )
            assert result["status"] == "success"

        # Guest should be denied shell execution
        result = await security_layer.execute_command("ls -la", "guest_user", "guest")
        assert result["status"] == "error"
        assert "Permission denied" in result["stderr"]
        assert result["security"]["reason"] == "no_permission"

    @pytest.mark.asyncio
    async def test_command_risk_assessment_integration(self, security_layer):
        """Test command risk assessment integration with execution"""
        # Test various risk levels
        test_cases = [
            ("echo hello", CommandRisk.SAFE),
            ("mkdir test_dir", CommandRisk.MODERATE),
            ("sudo apt update", CommandRisk.HIGH),
            ("rm -rf /tmp/dangerous", CommandRisk.FORBIDDEN),
        ]

        for command, expected_risk in test_cases:
            risk, reasons = security_layer.command_executor.assess_command_risk(command)
            assert risk == expected_risk or risk.value == expected_risk.value
            assert len(reasons) > 0

    def test_audit_log_integration(self, security_layer):
        """Test audit log integration across components"""
        # Test audit logging
        security_layer.audit_log(
            action="integration_test",
            user="test_user",
            outcome="success",
            details={"test": "data"},
        )

        # Verify log entry was written
        with open(security_layer.audit_log_file, "r") as f:
            content = f.read()
            assert "integration_test" in content
            assert "test_user" in content

        # Test command history retrieval
        history = security_layer.get_command_history(limit=1)
        if history:
            assert isinstance(history[0], dict)
            assert "timestamp" in history[0]
            assert "user" in history[0]


class TestSecurityAPIIntegration:
    """Integration tests for security API endpoints with backend system"""

    def test_security_api_integration_with_app_factory(self):
        """Test security API integration with FastAPI app factory"""
        app = create_app()
        client = TestClient(app)

        # Test that security endpoints are available
        response = client.get("/api/security/status")

        # Should either work (200) or initialize on-demand (200)
        # If app lifecycle hasn't run, it should auto-initialize
        assert response.status_code == 200

        data = response.json()
        assert "security_enabled" in data
        assert "command_security_enabled" in data
        assert "docker_sandbox_enabled" in data
        assert "pending_approvals" in data

    def test_security_endpoints_workflow(self):
        """Test complete security management workflow via API"""
        app = create_app()
        client = TestClient(app)

        # 1. Check security status
        status_response = client.get("/api/security/status")
        assert status_response.status_code == 200

        # 2. Check pending approvals
        pending_response = client.get("/api/security/pending-approvals")
        assert pending_response.status_code == 200
        pending_data = pending_response.json()
        assert "count" in pending_data

        # 3. Check command history
        history_response = client.get("/api/security/command-history")
        assert history_response.status_code == 200
        history_data = history_response.json()
        assert "count" in history_data

        # 4. Check audit log
        audit_response = client.get("/api/security/audit-log")
        assert audit_response.status_code == 200
        audit_data = audit_response.json()
        assert "count" in audit_data

    def test_command_approval_workflow_api(self):
        """Test command approval workflow through API"""
        app = create_app()
        client = TestClient(app)

        # Test command approval endpoint
        approval_request = {"command_id": "test_cmd_123", "approved": True}

        response = client.post("/api/security/approve-command", json=approval_request)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "approved" in data["message"]


class TestTerminalSecurityIntegration:
    """Integration tests for secure terminal functionality"""

    @pytest.mark.asyncio
    async def test_secure_terminal_session_integration(self):
        """Test secure terminal session with security layer integration"""
        from backend.api.secure_terminal_websocket import SecureTerminalSession

        # Create mock security layer
        mock_security = MagicMock()

        # Create terminal session
        session = SecureTerminalSession(
            session_id="integration_test",
            security_layer=mock_security,
            user_role="developer",
        )

        # Test command auditing integration
        await session.audit_command("ls -la")

        # Verify security layer was called for auditing
        mock_security.audit_log.assert_called()
        call_args = mock_security.audit_log.call_args
        assert call_args[1]["action"] == "terminal_command"
        assert call_args[1]["details"]["command"] == "ls -la"

    @pytest.mark.asyncio
    async def test_terminal_risk_assessment_integration(self):
        """Test terminal risk assessment integration"""
        from backend.api.secure_terminal_websocket import SecureTerminalSession

        # Mock security layer with command executor
        mock_security = MagicMock()
        mock_executor = MagicMock()
        mock_executor.assess_command_risk.return_value = ("high", ["High risk command"])
        mock_security.command_executor = mock_executor

        # Create terminal session
        session = SecureTerminalSession(
            session_id="risk_test", security_layer=mock_security, user_role="user"
        )

        # Mock WebSocket for warning messages
        session.websocket = AsyncMock()
        session.active = True

        # Test high-risk command that matches risky patterns
        await session.audit_command("rm -rf /tmp/test")

        # Should log both command execution and risky command detection
        assert mock_security.audit_log.call_count == 2

        # Verify the audit calls
        audit_calls = mock_security.audit_log.call_args_list
        assert audit_calls[0][1]["action"] == "terminal_command"
        assert audit_calls[1][1]["action"] == "risky_command_detected"
        assert audit_calls[1][1]["outcome"] == "warning"
        assert audit_calls[1][1]["details"]["risk_level"] == "high"


class TestDockerSandboxIntegration:
    """Integration tests for Docker sandbox functionality"""

    def test_docker_sandbox_configuration(self):
        """Test Docker sandbox configuration in security system"""
        with patch("src.enhanced_security_layer.global_config_manager") as mock_config:
            mock_config.get.return_value = {
                "enable_command_security": True,
                "use_docker_sandbox": True,
            }

            security = EnhancedSecurityLayer()
            assert security.use_docker_sandbox is True
            assert security.command_executor.use_docker_sandbox is True

    def test_docker_command_construction(self):
        """Test Docker command construction for sandboxing"""
        executor = SecureCommandExecutor(use_docker_sandbox=True)

        docker_cmd = executor._build_docker_command("echo 'sandbox test'")

        # Verify Docker command structure
        assert "docker run" in docker_cmd
        assert "--rm" in docker_cmd
        assert "--read-only" in docker_cmd
        assert "--network none" in docker_cmd
        assert "autobot-sandbox:latest" in docker_cmd
        assert "echo 'sandbox test'" in docker_cmd

    @pytest.mark.asyncio
    async def test_docker_sandbox_execution_integration(self):
        """Test Docker sandbox execution integration (mocked)"""
        executor = SecureCommandExecutor(use_docker_sandbox=True)

        # Set up approval callback to auto-approve for testing
        async def auto_approve_callback(approval_data):
            return True

        executor.require_approval_callback = auto_approve_callback

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"sandboxed output\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            # Execute moderate risk command (should use sandbox)
            result = await executor.run_shell_command("rm test.txt")

            # Verify Docker was used
            executed_command = mock_subprocess.call_args[0][0]
            assert "docker run" in executed_command

            # Verify result indicates sandboxing
            assert result["security"]["sandboxed"] is True


class TestSecuritySystemResilience:
    """Test security system resilience and error handling"""

    @pytest.mark.asyncio
    async def test_security_layer_error_resilience(self, security_layer):
        """Test security layer handles errors gracefully"""
        # Test with broken audit log file
        security_layer.audit_log_file = "/invalid/path/audit.log"

        # Should not raise exception
        security_layer.audit_log(
            action="test_action", user="test_user", outcome="test", details={}
        )

        # Command execution should still work
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await security_layer.execute_command("echo test", "user", "admin")
            assert result["status"] == "success"

    def test_command_executor_error_handling(self):
        """Test command executor error handling"""
        executor = SecureCommandExecutor()

        # Test with malformed command
        risk, reasons = executor.assess_command_risk("")
        assert risk == CommandRisk.FORBIDDEN
        assert "Empty or malformed command" in reasons

        # Test with extremely long command
        long_command = "echo " + "a" * 10000
        risk, reasons = executor.assess_command_risk(long_command)
        # Should handle gracefully without crashing
        assert risk in [CommandRisk.SAFE, CommandRisk.MODERATE, CommandRisk.HIGH]

    @pytest.mark.asyncio
    async def test_approval_timeout_handling(self, security_layer):
        """Test approval timeout handling"""
        # Enable approval requirement
        security_layer.command_approval_required = True

        # Mock approval callback that times out
        async def timeout_callback(approval_data):
            await asyncio.sleep(0.1)  # Simulate delay
            raise asyncio.TimeoutError()

        security_layer.command_executor.require_approval_callback = timeout_callback

        # Test command that needs approval
        try:
            result = await security_layer.execute_command(
                "rm test.txt", "user", "admin"
            )

            # Should handle timeout gracefully
            assert result["status"] == "error"
            assert (
                "timeout" in result.get("stderr", "").lower()
                or "denied" in result.get("stderr", "").lower()
            )

        except asyncio.TimeoutError:
            # If timeout is not caught, that's also acceptable behavior
            pass


class TestSecurityPerformance:
    """Test security system performance characteristics"""

    def test_risk_assessment_performance(self):
        """Test risk assessment performance"""
        executor = SecureCommandExecutor()

        import time

        # Test batch risk assessment
        commands = [
            "echo hello",
            "ls -la",
            "cat file.txt",
            "mkdir test",
            "rm file.txt",
            "sudo apt update",
        ] * 10  # 60 commands total

        start_time = time.time()

        for cmd in commands:
            risk, reasons = executor.assess_command_risk(cmd)
            assert risk is not None

        end_time = time.time()
        duration = end_time - start_time

        # Should be fast (< 1 second for 60 assessments)
        assert (
            duration < 1.0
        ), f"Risk assessment took {duration:.2f}s for {len(commands)} commands"

        # Average should be under 16ms per assessment
        avg_time = duration / len(commands) * 1000
        assert avg_time < 16, f"Average assessment time: {avg_time:.2f}ms"

    @pytest.mark.asyncio
    async def test_audit_logging_performance(self, security_layer):
        """Test audit logging performance"""
        import time

        start_time = time.time()

        # Log 100 audit entries
        for i in range(100):
            security_layer.audit_log(
                action=f"performance_test_{i}",
                user="perf_user",
                outcome="success",
                details={"iteration": i, "test": "performance"},
            )

        end_time = time.time()
        duration = end_time - start_time

        # Should be fast (< 0.5 seconds for 100 entries)
        assert duration < 0.5, f"Audit logging took {duration:.2f}s for 100 entries"


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "--tb=short"])
