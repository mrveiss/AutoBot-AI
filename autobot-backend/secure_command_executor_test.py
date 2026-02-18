"""
Unit tests for SecureCommandExecutor module
Tests command risk assessment, approval workflows, and secure execution
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Import the modules to test
from secure_command_executor import CommandRisk, SecureCommandExecutor, SecurityPolicy


class TestSecurityPolicy:
    """Test SecurityPolicy configuration and methods"""

    def test_security_policy_initialization(self):
        """Test SecurityPolicy initializes with default values"""
        policy = SecurityPolicy()

        # Check that safe commands are populated
        assert "echo" in policy.safe_commands
        assert "ls" in policy.safe_commands
        assert "pwd" in policy.safe_commands

        # Check that forbidden commands are populated
        assert "shutdown" in policy.forbidden_commands
        assert "reboot" in policy.forbidden_commands

        # Check that dangerous patterns are populated
        assert len(policy.dangerous_patterns) > 0

        # Check that allowed paths include common directories
        assert Path.home() in policy.allowed_paths
        assert Path("/tmp") in policy.allowed_paths


class TestSecureCommandExecutor:
    """Test SecureCommandExecutor functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.executor = SecureCommandExecutor()
        self.mock_approval_callback = AsyncMock()
        self.executor_with_callback = SecureCommandExecutor(
            require_approval_callback=self.mock_approval_callback
        )

    def test_executor_initialization(self):
        """Test SecureCommandExecutor initializes correctly"""
        assert self.executor.policy is not None
        assert isinstance(self.executor.policy, SecurityPolicy)
        assert self.executor.require_approval_callback is None
        assert self.executor.use_docker_sandbox is False
        assert self.executor.command_history == []

    def test_executor_initialization_with_params(self):
        """Test SecureCommandExecutor initializes with custom parameters"""
        policy = SecurityPolicy()
        callback = AsyncMock()

        executor = SecureCommandExecutor(
            policy=policy, require_approval_callback=callback, use_docker_sandbox=True
        )

        assert executor.policy is policy
        assert executor.require_approval_callback is callback
        assert executor.use_docker_sandbox is True

    def test_extract_command_name(self):
        """Test command name extraction from various command formats"""
        # Simple command
        assert self.executor._extract_command_name("ls") == "ls"

        # Command with arguments
        assert self.executor._extract_command_name("ls -la /tmp") == "ls"

        # Command with path
        assert self.executor._extract_command_name("/usr/bin/ls -la") == "ls"

        # Complex command with quotes
        assert self.executor._extract_command_name("echo 'hello world'") == "echo"

        # Empty command
        assert self.executor._extract_command_name("") == ""

        # Malformed command - returns partial result due to fallback
        assert self.executor._extract_command_name("'unclosed quote") == "'unclosed"

    def test_check_dangerous_patterns(self):
        """Test dangerous pattern detection"""
        # Safe command should have no dangerous patterns
        assert self.executor._check_dangerous_patterns("echo hello") == []

        # Dangerous rm command
        patterns = self.executor._check_dangerous_patterns("rm -rf /")
        assert len(patterns) > 0
        assert any("rm\\s+-rf\\s+/" in pattern for pattern in patterns)

        # Command with /etc/passwd access
        patterns = self.executor._check_dangerous_patterns("cat /etc/passwd")
        assert len(patterns) > 0
        assert any("/etc/passwd" in pattern for pattern in patterns)

        # Fork bomb
        patterns = self.executor._check_dangerous_patterns(":(){ :|:& };:")
        assert len(patterns) > 0

        # Command substitution
        patterns = self.executor._check_dangerous_patterns("echo $(rm -rf /)")
        assert len(patterns) > 0

    def test_assess_command_risk_safe(self):
        """Test risk assessment for safe commands"""
        safe_commands = ["echo hello", "ls -la", "pwd", "whoami", "date"]

        for cmd in safe_commands:
            risk, reasons = self.executor.assess_command_risk(cmd)
            assert risk == CommandRisk.SAFE
            assert "Safe command" in reasons

    def test_assess_command_risk_moderate(self):
        """Test risk assessment for moderate risk commands"""
        moderate_commands = ["cp file1 file2", "mkdir newdir", "chmod 755 file"]

        for cmd in moderate_commands:
            risk, reasons = self.executor.assess_command_risk(cmd)
            assert risk == CommandRisk.MODERATE
            assert any("Moderate-risk command" in reason for reason in reasons)

    def test_assess_command_risk_high(self):
        """Test risk assessment for high risk commands"""
        high_commands = ["sudo apt update", "rm file.txt", "systemctl restart service"]

        for cmd in high_commands:
            risk, reasons = self.executor.assess_command_risk(cmd)
            assert risk in [
                CommandRisk.HIGH,
                CommandRisk.FORBIDDEN,
            ]  # rm might be forbidden

    def test_assess_command_risk_forbidden(self):
        """Test risk assessment for forbidden commands"""
        forbidden_commands = [
            "rm -rf /",
            "shutdown now",
            "kill -9 1",
            ":(){ :|:& };:",
            "cat /etc/passwd",
        ]

        for cmd in forbidden_commands:
            risk, reasons = self.executor.assess_command_risk(cmd)
            assert risk == CommandRisk.FORBIDDEN
            assert len(reasons) > 0

    def test_assess_command_risk_empty_command(self):
        """Test risk assessment for empty/malformed commands"""
        risk, reasons = self.executor.assess_command_risk("")
        assert risk == CommandRisk.FORBIDDEN
        assert "Empty or malformed command" in reasons

    def test_assess_command_risk_unknown_command(self):
        """Test risk assessment for unknown commands"""
        risk, reasons = self.executor.assess_command_risk("unknown_command_xyz")
        assert risk == CommandRisk.MODERATE
        assert any("Unknown command" in reason for reason in reasons)

    def test_assess_command_risk_system_paths(self):
        """Test risk assessment for commands operating on system paths"""
        # Moderate command with system path should become HIGH
        risk, reasons = self.executor.assess_command_risk("cp /etc/file /tmp/")
        assert risk == CommandRisk.HIGH
        assert any("Operates on system paths" in reason for reason in reasons)

    def test_assess_command_risk_sudo_elevation(self):
        """Test risk assessment for commands with sudo"""
        # Safe command with sudo becomes HIGH due to sudo being high-risk command
        risk, reasons = self.executor.assess_command_risk("sudo ls")
        assert risk == CommandRisk.HIGH
        assert any("High-risk command" in reason for reason in reasons)

    def test_assess_command_risk_sensitive_redirection(self):
        """Test risk assessment for output redirection to sensitive locations"""
        # Safe command with dangerous redirection - detected as forbidden
        # due to /etc/passwd pattern
        risk, reasons = self.executor.assess_command_risk("echo evil > /etc/passwd")
        assert risk == CommandRisk.FORBIDDEN
        assert any("Dangerous pattern" in reason for reason in reasons)

    @pytest.mark.asyncio
    async def test_request_approval_with_callback(self):
        """Test approval request with callback"""
        self.mock_approval_callback.return_value = True

        result = await self.executor_with_callback._request_approval(
            "rm file.txt", CommandRisk.HIGH, ["High-risk command: rm"]
        )

        assert result is True
        self.mock_approval_callback.assert_called_once()

        # Check approval data structure
        call_args = self.mock_approval_callback.call_args[0][0]
        assert call_args["command"] == "rm file.txt"
        assert call_args["risk"] == "high"
        assert call_args["reasons"] == ["High-risk command: rm"]
        assert "timestamp" in call_args

    @pytest.mark.asyncio
    async def test_request_approval_denied(self):
        """Test approval request denial"""
        self.mock_approval_callback.return_value = False

        result = await self.executor_with_callback._request_approval(
            "rm file.txt", CommandRisk.HIGH, ["High-risk command: rm"]
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_request_approval_no_callback(self):
        """Test approval request without callback"""
        result = await self.executor._request_approval(
            "rm file.txt", CommandRisk.HIGH, ["High-risk command: rm"]
        )

        # Should deny by default when no callback is set
        assert result is False

    def test_build_docker_command(self):
        """Test Docker command construction"""
        executor = SecureCommandExecutor(use_docker_sandbox=True)

        docker_cmd = executor._build_docker_command("echo hello")

        assert "docker run" in docker_cmd
        assert "--rm" in docker_cmd
        assert "--read-only" in docker_cmd
        assert "--network none" in docker_cmd
        assert "--memory 512m" in docker_cmd
        assert "--cpus 1.0" in docker_cmd
        assert "--user 1000:1000" in docker_cmd
        assert "autobot-sandbox:latest" in docker_cmd
        assert "echo hello" in docker_cmd

    @pytest.mark.asyncio
    async def test_run_shell_command_safe(self):
        """Test execution of safe command"""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            # Mock successful command execution
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"hello\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await self.executor.run_shell_command("echo hello")

            assert result["status"] == "success"
            assert result["stdout"] == "hello"
            assert result["stderr"] == ""
            assert result["return_code"] == 0
            assert result["security"]["risk"] == "safe"
            assert result["security"]["sandboxed"] is False

    @pytest.mark.asyncio
    async def test_run_shell_command_forbidden(self):
        """Test execution of forbidden command"""
        result = await self.executor.run_shell_command("rm -rf /")

        assert result["status"] == "error"
        assert "Command forbidden" in result["stderr"]
        assert result["return_code"] == 1
        assert result["security"]["risk"] == "forbidden"
        assert result["security"]["blocked"] is True

    @pytest.mark.asyncio
    async def test_run_shell_command_needs_approval_denied(self):
        """Test execution of command that needs approval but is denied"""
        self.mock_approval_callback.return_value = False

        result = await self.executor_with_callback.run_shell_command("rm file.txt")

        assert result["status"] == "error"
        assert "Command execution denied by user" in result["stderr"]
        assert result["return_code"] == 1
        assert result["security"]["blocked"] is True

    @pytest.mark.asyncio
    async def test_run_shell_command_needs_approval_approved(self):
        """Test execution of command that needs approval and is approved"""
        self.mock_approval_callback.return_value = True

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"file removed\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await self.executor_with_callback.run_shell_command("rm file.txt")

            assert result["status"] == "success"
            assert result["stdout"] == "file removed"
            assert result["security"]["approved"] is True

    @pytest.mark.asyncio
    async def test_run_shell_command_force_approval(self):
        """Test execution with forced approval"""
        self.mock_approval_callback.return_value = True

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"hello\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            # Force approval for safe command
            result = await self.executor_with_callback.run_shell_command(
                "echo hello", force_approval=True
            )

            assert result["status"] == "success"
            assert result["security"]["approved"] is True
            self.mock_approval_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_shell_command_timeout(self):
        """Test command execution timeout"""
        with patch("src.secure_command_executor.execute_shell_command") as mock_execute:
            mock_execute.side_effect = asyncio.TimeoutError()

            # Use safe command that doesn't need approval
            result = await self.executor.run_shell_command("echo hello")

            assert result["status"] == "error"
            assert "Command execution timed out" in result["stderr"]
            assert result["return_code"] == 124
            assert result["security"]["timeout"] is True

    @pytest.mark.asyncio
    async def test_run_shell_command_execution_error(self):
        """Test command execution error handling"""
        with patch("src.secure_command_executor.execute_shell_command") as mock_execute:
            mock_execute.side_effect = Exception("Execution failed")

            # Use safe command that doesn't need approval
            result = await self.executor.run_shell_command("echo hello")

            assert result["status"] == "error"
            assert "Error executing command" in result["stderr"]
            assert result["return_code"] == 1
            assert "error" in result["security"]

    @pytest.mark.asyncio
    async def test_run_shell_command_docker_sandbox(self):
        """Test command execution with Docker sandbox"""
        executor = SecureCommandExecutor(use_docker_sandbox=True)

        # Set up approval callback to allow the command
        approve_callback = AsyncMock(return_value=True)
        executor.require_approval_callback = approve_callback

        with patch("src.secure_command_executor.execute_shell_command") as mock_execute:
            mock_execute.return_value = {
                "stdout": "sandboxed output",
                "stderr": "",
                "return_code": 0,
                "status": "success",
            }

            # High risk command should use sandbox
            result = await executor.run_shell_command("sudo apt list")

            # Check that Docker command was passed to execute_shell_command
            assert mock_execute.called
            call_args = mock_execute.call_args[0][0]
            assert "docker run" in call_args
            assert result["security"]["sandboxed"] is True

    def test_command_history(self):
        """Test command history tracking"""
        # Initially empty
        assert len(self.executor.get_command_history()) == 0

        # History should be populated after command execution
        # This is tested indirectly through other execution tests

        # Test history limits
        history = self.executor.get_command_history(limit=5)
        assert len(history) <= 5

    def test_clear_history(self):
        """Test command history clearing"""
        # Add some mock history
        self.executor.command_history = [{"test": "data"}]

        self.executor.clear_history()

        assert len(self.executor.command_history) == 0


class TestCommandRiskEnum:
    """Test CommandRisk enumeration"""

    def test_command_risk_values(self):
        """Test CommandRisk enum values"""
        assert CommandRisk.SAFE.value == "safe"
        assert CommandRisk.MODERATE.value == "moderate"
        assert CommandRisk.HIGH.value == "high"
        assert CommandRisk.CRITICAL.value == "critical"
        assert CommandRisk.FORBIDDEN.value == "forbidden"


# Async test helper
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
