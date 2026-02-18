"""
Unit tests for EnhancedSecurityLayer module
Tests integrated security features including role-based access and command execution
"""

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

# Import the modules to test
from enhanced_security_layer import EnhancedSecurityLayer
from secure_command_executor import CommandRisk


class TestEnhancedSecurityLayer:
    """Test EnhancedSecurityLayer functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        # Create temporary audit log file
        self.temp_audit_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_audit_file.close()

        # Mock config to use temporary file
        with patch("src.enhanced_security_layer.global_config_manager") as mock_config:
            mock_config.get.return_value = {
                "enable_auth": False,
                "enable_command_security": True,
                "audit_log_file": self.temp_audit_file.name,
                "command_approval_required": True,
                "use_docker_sandbox": False,
                "roles": {
                    "admin": {"permissions": ["allow_all"]},
                    "developer": {"permissions": ["allow_shell_execute"]},
                    "user": {"permissions": ["view_only"]},
                    "guest": {"permissions": []},
                },
            }
            self.security = EnhancedSecurityLayer()

    def teardown_method(self):
        """Clean up test fixtures"""
        try:
            os.unlink(self.temp_audit_file.name)
        except OSError:
            pass

    def test_initialization(self):
        """Test EnhancedSecurityLayer initializes correctly"""
        assert self.security.enable_auth is False
        assert self.security.enable_command_security is True
        assert self.security.command_approval_required is True
        assert self.security.use_docker_sandbox is False
        assert self.security.audit_log_file == self.temp_audit_file.name
        assert self.security.command_executor is not None
        assert isinstance(self.security.pending_approvals, dict)
        assert isinstance(self.security.approval_results, dict)

    def test_create_security_policy(self):
        """Test security policy creation from configuration"""
        # Test with custom policies in config
        with patch("src.enhanced_security_layer.global_config_manager") as mock_config:
            mock_config.get.return_value = {
                "enable_command_security": True,
                "command_policies": {
                    "safe_commands": ["custom_safe"],
                    "forbidden_commands": ["custom_forbidden"],
                    "allowed_paths": ["/custom/path"],
                },
            }

            security = EnhancedSecurityLayer()
            policy = security.command_executor.policy

            assert "custom_safe" in policy.safe_commands
            assert "custom_forbidden" in policy.forbidden_commands

    def test_check_permission_auth_disabled(self):
        """Test permission checking when authentication is disabled"""
        # All permissions should be allowed when auth is disabled
        assert self.security.check_permission("user", "allow_shell_execute") is True
        assert self.security.check_permission("guest", "allow_all") is True

    def test_check_permission_god_mode(self):
        """Test GOD MODE permissions"""
        self.security.enable_auth = True

        god_roles = ["god", "superuser", "root"]
        for role in god_roles:
            assert self.security.check_permission(role, "allow_shell_execute") is True
            assert self.security.check_permission(role, "dangerous_action") is True

    def test_check_permission_shell_execute(self):
        """Test shell execution permissions"""
        self.security.enable_auth = True

        # Test different roles for shell execution
        assert self.security.check_permission("admin", "allow_shell_execute") is True
        assert (
            self.security.check_permission("developer", "allow_shell_execute") is True
        )
        assert self.security.check_permission("user", "allow_shell_execute") is False
        assert self.security.check_permission("guest", "allow_shell_execute") is False

    def test_check_permission_safe_shell_execute(self):
        """Test safe shell execution permissions"""
        self.security.enable_auth = True

        # Developer should have safe shell execution permission
        assert (
            self.security.check_permission("developer", "allow_shell_execute") is True
        )

        # User should not have shell execution permission
        assert self.security.check_permission("user", "allow_shell_execute") is False

    def test_check_permission_custom_roles(self):
        """Test permission checking with custom role configuration"""
        self.security.enable_auth = True
        self.security.roles = {
            "custom_role": {"permissions": ["allow_shell_execute", "custom_permission"]}
        }

        assert (
            self.security.check_permission("custom_role", "allow_shell_execute") is True
        )
        assert (
            self.security.check_permission("custom_role", "custom_permission") is True
        )
        assert (
            self.security.check_permission("custom_role", "forbidden_action") is False
        )

    def test_check_permission_wildcard(self):
        """Test wildcard permission matching"""
        self.security.enable_auth = True
        self.security.roles = {"test_role": {"permissions": ["files.*", "api.read.*"]}}

        assert self.security.check_permission("test_role", "files.view") is True
        assert self.security.check_permission("test_role", "files.delete") is True
        assert self.security.check_permission("test_role", "api.read.users") is True
        assert self.security.check_permission("test_role", "api.write.users") is False

    def test_get_default_role_permissions(self):
        """Test default role permissions"""
        default_perms = self.security._get_default_role_permissions("developer")
        assert "allow_shell_execute_safe" in default_perms
        assert "allow_kb_write" in default_perms

        user_perms = self.security._get_default_role_permissions("user")
        assert "allow_shell_execute" not in user_perms
        assert "allow_kb_read" in user_perms

        guest_perms = self.security._get_default_role_permissions("guest")
        assert "files.view" in guest_perms
        assert len(guest_perms) == 1  # Very limited permissions

    @pytest.mark.asyncio
    async def test_command_approval_callback_auto_approve(self):
        """Test command approval callback with auto-approval"""
        self.security.security_config = {"auto_approve_moderate": True}

        approval_data = {
            "command": "mkdir test",
            "risk": CommandRisk.MODERATE.value,
            "reasons": ["Moderate risk"],
            "timestamp": asyncio.get_event_loop().time(),
        }

        result = await self.security._command_approval_callback(approval_data)
        assert result is True

    @pytest.mark.asyncio
    async def test_command_approval_callback_manual_approval(self):
        """Test command approval callback with manual approval"""
        approval_data = {
            "command": "rm file.txt",
            "risk": CommandRisk.HIGH.value,
            "reasons": ["High risk"],
            "timestamp": asyncio.get_event_loop().time(),
        }

        # Start approval in background
        approval_task = asyncio.create_task(
            self.security._command_approval_callback(approval_data)
        )

        # Wait a moment then approve
        await asyncio.sleep(0.1)

        # Find the command ID and approve it
        command_id = f"cmd_{int(approval_data['timestamp'])}"
        if command_id in self.security.pending_approvals:
            self.security.approve_command(command_id, True)

        result = await approval_task
        assert result is True

    @pytest.mark.asyncio
    async def test_command_approval_timeout(self):
        """Test command approval timeout"""
        approval_data = {
            "command": "rm file.txt",
            "risk": CommandRisk.HIGH.value,
            "reasons": ["High risk"],
            "timestamp": asyncio.get_event_loop().time(),
        }

        # Mock asyncio.wait_for to raise TimeoutError
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            result = await self.security._command_approval_callback(approval_data)
            assert result is False

    def test_approve_command(self):
        """Test command approval mechanism"""
        # Set up a pending approval
        command_id = "test_cmd_123"
        approval_event = asyncio.Event()
        self.security.pending_approvals[command_id] = approval_event

        # Approve the command
        self.security.approve_command(command_id, True)

        assert self.security.approval_results[command_id] is True
        assert approval_event.is_set()

        # Test denial
        command_id2 = "test_cmd_456"
        approval_event2 = asyncio.Event()
        self.security.pending_approvals[command_id2] = approval_event2

        self.security.approve_command(command_id2, False)

        assert self.security.approval_results[command_id2] is False
        assert approval_event2.is_set()

    @pytest.mark.asyncio
    async def test_execute_command_permission_denied(self):
        """Test command execution with permission denied"""
        self.security.enable_auth = True

        result = await self.security.execute_command("ls -la", "test_user", "guest")

        assert result["status"] == "error"
        assert "Permission denied" in result["stderr"]
        assert result["return_code"] == 1
        assert result["security"]["blocked"] is True
        assert result["security"]["reason"] == "no_permission"

    @pytest.mark.asyncio
    async def test_execute_command_with_permission(self):
        """Test command execution with proper permissions"""
        with patch.object(
            self.security.command_executor, "run_shell_command"
        ) as mock_run:
            mock_run.return_value = {
                "stdout": "file1 file2",
                "stderr": "",
                "return_code": 0,
                "status": "success",
                "security": {"risk": "safe"},
            }

            result = await self.security.execute_command(
                "ls -la", "admin_user", "admin"
            )

            assert result["status"] == "success"
            assert result["stdout"] == "file1 file2"
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_command_force_approval_for_restricted_role(self):
        """Test command execution with forced approval for restricted roles"""
        self.security.enable_auth = True

        with patch.object(
            self.security.command_executor, "assess_command_risk"
        ) as mock_assess:
            mock_assess.return_value = (CommandRisk.HIGH, ["High risk command"])

            with patch.object(
                self.security.command_executor, "run_shell_command"
            ) as mock_run:
                mock_run.return_value = {
                    "stdout": "",
                    "stderr": "Command execution denied by user",
                    "return_code": 1,
                    "status": "error",
                    "security": {"blocked": True},
                }

                # Developer can only execute safe commands without approval
                await self.security.execute_command(
                    "rm file.txt", "dev_user", "developer"
                )

                # Should force approval for non-safe command
                mock_run.assert_called_once_with("rm file.txt", force_approval=True)

    @pytest.mark.asyncio
    async def test_execute_command_security_disabled(self):
        """Test command execution with security disabled"""
        self.security.enable_command_security = False

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await self.security.execute_command(
                "echo hello", "test_user", "user"
            )

            assert result["status"] == "success"
            assert result["stdout"] == "output"
            assert result["security"]["enabled"] is False

    def test_audit_log(self):
        """Test audit logging functionality"""
        self.security.audit_log(
            action="test_action",
            user="test_user",
            outcome="success",
            details={"command": "test command"},
        )

        # Check that log entry was written
        with open(self.temp_audit_file.name, "r") as f:
            log_entry = json.loads(f.read().strip())

        assert log_entry["action"] == "test_action"
        assert log_entry["user"] == "test_user"
        assert log_entry["outcome"] == "success"
        assert log_entry["details"]["command"] == "test command"
        assert "timestamp" in log_entry

    def test_audit_log_file_error(self):
        """Test audit logging with file error"""
        # Point to invalid directory
        self.security.audit_log_file = "/invalid/path/audit.log"

        # Should not raise exception
        self.security.audit_log(
            action="test_action", user="test_user", outcome="success", details={}
        )

    def test_get_command_history_empty(self):
        """Test getting command history when empty"""
        history = self.security.get_command_history()
        assert history == []

    def test_get_command_history_with_data(self):
        """Test getting command history with data"""
        # Write some test log entries
        test_entries = [
            {
                "action": "command_execution_attempt",
                "user": "test_user",
                "timestamp": "2023-01-01T10:00:00",
                "details": {"command": "ls"},
            },
            {
                "action": "command_execution_complete",
                "user": "test_user",
                "timestamp": "2023-01-01T10:00:01",
                "details": {"command": "ls"},
            },
            {
                "action": "other_action",
                "user": "test_user",
                "timestamp": "2023-01-01T10:00:02",
                "details": {},
            },
        ]

        with open(self.temp_audit_file.name, "w") as f:
            for entry in test_entries:
                f.write(json.dumps(entry) + "\n")

        history = self.security.get_command_history()
        assert len(history) == 2  # Only command execution entries

        # Test with user filter
        history = self.security.get_command_history(user="test_user")
        assert len(history) == 2

        history = self.security.get_command_history(user="other_user")
        assert len(history) == 0

        # Test with limit
        history = self.security.get_command_history(limit=1)
        assert len(history) == 1

    def test_get_command_history_malformed_json(self):
        """Test getting command history with malformed JSON"""
        # Write malformed JSON
        with open(self.temp_audit_file.name, "w") as f:
            f.write('{"valid": "json"}\n')
            f.write("invalid json line\n")
            f.write('{"action": "command_execution_attempt", "user": "test"}\n')

        history = self.security.get_command_history()
        assert len(history) == 1  # Only valid entries

    def test_authenticate_user_auth_disabled(self):
        """Test user authentication when auth is disabled"""
        result = self.security.authenticate_user("any_user", "any_password")
        assert result == "admin"  # Default role when auth disabled

    def test_authenticate_user_auth_enabled(self):
        """Test user authentication when auth is enabled"""
        self.security.enable_auth = True
        self.security.allowed_users = {"test_user": "test_password"}
        self.security.security_config = {"user_roles": {"test_user": "developer"}}

        # Valid credentials
        result = self.security.authenticate_user("test_user", "test_password")
        assert result == "developer"

        # Invalid credentials
        result = self.security.authenticate_user("test_user", "wrong_password")
        assert result is None

        result = self.security.authenticate_user("invalid_user", "any_password")
        assert result is None

    def test_get_pending_approvals(self):
        """Test getting pending approvals list"""
        # Initially empty
        pending = self.security.get_pending_approvals()
        assert pending == []

        # Add some pending approvals
        self.security.pending_approvals["cmd_123"] = asyncio.Event()
        self.security.pending_approvals["cmd_456"] = asyncio.Event()

        pending = self.security.get_pending_approvals()
        assert len(pending) == 2

        command_ids = [item["command_id"] for item in pending]
        assert "cmd_123" in command_ids
        assert "cmd_456" in command_ids


# Integration tests
class TestEnhancedSecurityLayerIntegration:
    """Integration tests for EnhancedSecurityLayer with SecureCommandExecutor"""

    def setup_method(self):
        """Set up test fixtures"""
        with patch("src.enhanced_security_layer.global_config_manager") as mock_config:
            mock_config.get.return_value = {
                "enable_auth": False,
                "enable_command_security": True,
                "command_approval_required": False,  # Disable for integration tests
                "use_docker_sandbox": False,
            }
            self.security = EnhancedSecurityLayer()

    @pytest.mark.asyncio
    async def test_end_to_end_safe_command(self):
        """Test end-to-end execution of safe command"""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"hello world\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await self.security.execute_command(
                "echo 'hello world'", "test_user", "admin"
            )

            assert result["status"] == "success"
            assert result["stdout"] == "hello world"
            assert result["security"]["risk"] == "safe"

    @pytest.mark.asyncio
    async def test_end_to_end_forbidden_command(self):
        """Test end-to-end execution of forbidden command"""
        result = await self.security.execute_command("rm -rf /", "test_user", "admin")

        assert result["status"] == "error"
        assert "Command forbidden" in result["stderr"]
        assert result["security"]["risk"] == "forbidden"
        assert result["security"]["blocked"] is True


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
