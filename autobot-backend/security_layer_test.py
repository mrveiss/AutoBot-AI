# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for SecurityLayer module
Tests integrated security features including role-based access and command execution
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Import the modules to test
import security_layer
from autobot_shared.paths import project_root
from autobot_shared.ssot_config import default_audit_log_file
from autobot_shared.status_enums import CommandRisk
from security_layer import SecurityLayer


class TestSecurityLayer:
    """Test SecurityLayer functionality"""

    def setup_method(self):
        """Set up test fixtures; audit records are captured at the canonical service (#17225 D6)."""
        self.emit_patcher = patch("security_layer.emit_security", return_value=True)
        self.emit_security = self.emit_patcher.start()
        with patch("security_layer.get_config_manager") as mock_get_cm:
            mock_config = mock_get_cm.return_value
            mock_config.get.return_value = {
                "enable_auth": False,
                "enable_command_security": True,
                "command_approval_required": True,
                "use_docker_sandbox": False,
                "roles": {
                    "admin": {"permissions": ["allow_all"]},
                    "developer": {"permissions": ["allow_shell_execute"]},
                    "user": {"permissions": ["view_only"]},
                    "guest": {"permissions": []},
                },
            }
            self.security = SecurityLayer()

    def teardown_method(self):
        """Stop capturing audit records."""
        self.emit_patcher.stop()

    def test_initialization(self):
        """Test SecurityLayer initializes correctly"""
        assert self.security.enable_auth is False
        assert self.security.enable_command_security is True
        assert self.security.command_approval_required is True
        assert self.security.use_docker_sandbox is False
        assert self.security.command_executor is not None
        assert isinstance(self.security.pending_approvals, dict)
        assert isinstance(self.security.approval_results, dict)

    def test_create_security_policy(self):
        """Test security policy creation from configuration"""
        # Test with custom policies in config
        with patch("security_layer.get_config_manager") as mock_get_cm:
            mock_config = mock_get_cm.return_value
            mock_config.get.return_value = {
                "enable_command_security": True,
                "command_policies": {
                    "safe_commands": ["custom_safe"],
                    "forbidden_commands": ["custom_forbidden"],
                    "allowed_paths": ["/custom/path"],
                },
            }

            security = SecurityLayer()
            policy = security.command_executor.policy

            assert "custom_safe" in policy.safe_commands
            assert "custom_forbidden" in policy.forbidden_commands

    def test_check_permission_auth_disabled(self):
        """Test permission checking when authentication is disabled"""
        # All permissions should be allowed when auth is disabled
        assert self.security.check_permission("user", "allow_shell_execute") is True
        assert self.security.check_permission("guest", "allow_all") is True

    def test_deprecated_privileged_roles_downgrade_to_admin(self):
        """#7161 / #744: god/superuser/root are deprecated and downgraded.

        Previously this test ('test_check_permission_god_mode') asserted
        unrestricted "god mode" access including auto-granted
        ``dangerous_action`` — a security anti-pattern. Issue #744
        explicitly removed the god-mode bypass: privileged role names get
        downgraded to 'admin' via ``_handle_deprecated_role`` and inherit
        admin's RBAC permissions (no wildcard for arbitrary actions).

        Pin the new contract: deprecated roles get admin-equivalent access
        for legitimate actions (``allow_shell_execute``), but NOT for
        arbitrary unmapped actions (no god-bypass wildcard).
        """
        self.security.enable_auth = True

        for role in ["god", "superuser", "root"]:
            # Deprecated roles inherit admin perms — admin has shell_execute.
            assert (
                self.security.check_permission(role, "allow_shell_execute") is True
            ), f"deprecated role {role!r} should inherit admin shell-execute"
            # No god-bypass: unmapped action_type is denied (not auto-True).
            assert (
                self.security.check_permission(role, "dangerous_action") is False
            ), f"deprecated role {role!r} must NOT auto-grant unmapped actions"

    def test_check_permission_shell_execute(self):
        """Test shell execution permissions"""
        self.security.enable_auth = True

        # Test different roles for shell execution
        assert self.security.check_permission("admin", "allow_shell_execute") is True
        assert self.security.check_permission("developer", "allow_shell_execute") is True
        assert self.security.check_permission("user", "allow_shell_execute") is False
        assert self.security.check_permission("guest", "allow_shell_execute") is False

    def test_check_permission_safe_shell_execute(self):
        """Test safe shell execution permissions"""
        self.security.enable_auth = True

        # Developer should have safe shell execution permission
        assert self.security.check_permission("developer", "allow_shell_execute") is True

        # User should not have shell execution permission
        assert self.security.check_permission("user", "allow_shell_execute") is False

    def test_check_permission_custom_roles(self):
        """Test permission checking with custom role configuration"""
        self.security.enable_auth = True
        self.security.roles = {"custom_role": {"permissions": ["allow_shell_execute", "custom_permission"]}}

        assert self.security.check_permission("custom_role", "allow_shell_execute") is True
        assert self.security.check_permission("custom_role", "custom_permission") is True
        assert self.security.check_permission("custom_role", "forbidden_action") is False

    def test_check_permission_wildcard(self):
        """Test wildcard permission matching"""
        self.security.enable_auth = True
        self.security.roles = {"test_role": {"permissions": ["files.*", "api.read.*"]}}

        assert self.security.check_permission("test_role", "files.view") is True
        assert self.security.check_permission("test_role", "files.delete") is True
        assert self.security.check_permission("test_role", "api.read.users") is True
        assert self.security.check_permission("test_role", "api.write.users") is False

    def test_get_default_role_permissions(self):
        """Test default role permissions.

        #7161 / #744: guest role was REMOVED as a security vulnerability —
        unauthenticated requests must be rejected, not assigned default
        permissions. Tests now pin the post-#744 contract.
        """
        default_perms = self.security._get_default_role_permissions("developer")
        assert "allow_shell_execute_safe" in default_perms
        assert "allow_kb_write" in default_perms

        user_perms = self.security._get_default_role_permissions("user")
        assert "allow_shell_execute" not in user_perms
        assert "allow_kb_read" in user_perms

        # #744: guest is REMOVED — empty permissions list returned.
        # Unauthenticated requests must be rejected upstream, not granted
        # any default access here.
        guest_perms = self.security._get_default_role_permissions("guest")
        assert guest_perms == [], (
            "guest role was removed by #744 as a security vulnerability; "
            "_get_default_role_permissions('guest') must return [] so "
            "unauthenticated requests are rejected upstream"
        )

    @pytest.mark.asyncio
    async def test_command_approval_callback_auto_approve(self):
        """Test command approval callback with auto-approval"""
        self.security.security_config = {"auto_approve_moderate": True}

        approval_data = {
            "command": "mkdir test",
            "risk": CommandRisk.MODERATE.value,
            "reasons": ["Moderate risk"],
            "timestamp": asyncio.get_running_loop().time(),
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
            "timestamp": asyncio.get_running_loop().time(),
        }

        # Start approval in background
        approval_task = asyncio.create_task(self.security._command_approval_callback(approval_data))

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
            "timestamp": asyncio.get_running_loop().time(),
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
        with patch.object(self.security.command_executor, "run_shell_command") as mock_run:
            mock_run.return_value = {
                "stdout": "file1 file2",
                "stderr": "",
                "return_code": 0,
                "status": "success",
                "security": {"risk": "safe"},
            }

            result = await self.security.execute_command("ls -la", "admin_user", "admin")

            assert result["status"] == "success"
            assert result["stdout"] == "file1 file2"
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_command_force_approval_for_restricted_role(self):
        """Test command execution with forced approval for restricted roles"""
        self.security.enable_auth = True

        with patch.object(self.security.command_executor, "assess_command_risk") as mock_assess:
            mock_assess.return_value = (CommandRisk.HIGH, ["High risk command"])

            with patch.object(self.security.command_executor, "run_shell_command") as mock_run:
                mock_run.return_value = {
                    "stdout": "",
                    "stderr": "Command execution denied by user",
                    "return_code": 1,
                    "status": "error",
                    "security": {"blocked": True},
                }

                # Developer can only execute safe commands without approval
                await self.security.execute_command("rm file.txt", "dev_user", "developer")

                # Should force approval for non-safe command
                mock_run.assert_called_once_with("rm file.txt", force_approval=True, policy=None)

    @pytest.mark.asyncio
    async def test_execute_command_security_disabled(self):
        """Test command execution with security disabled"""
        self.security.enable_command_security = False

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await self.security.execute_command("echo hello", "test_user", "user")

            assert result["status"] == "success"
            assert result["stdout"] == "output"
            assert result["security"]["enabled"] is False

    def test_audit_log(self):
        """An action is recorded as a SECURITY event at the canonical service, tagged as this layer's."""
        self.security.audit_log(
            action="test_action",
            user="test_user",
            outcome="success",
            details={"command": "test command"},
        )
        self.emit_security.assert_called_once_with(
            "test_action",
            "test_user",
            resource_type=security_layer.SECURITY_LAYER_SOURCE,
            metadata={"command": "test command"},
            outcome="success",
        )

    def test_a_record_that_cannot_be_scheduled_is_counted_not_raised(self):
        """#14843/#14750: never raises, and a lost record is distinguishable from a written one."""
        self.emit_security.return_value = False
        with patch("security_layer.record_audit_write_failure_safely") as counted:
            self.security.audit_log(action="test_action", user="test_user", outcome="success", details={})
        counted.assert_called_once_with("test_action", "NotScheduled")

    @pytest.mark.asyncio
    async def test_get_command_history_asks_for_command_actions(self):
        query = AsyncMock(return_value=[])
        with patch("security_layer.query_filtered", new=query):
            assert await self.security.get_command_history(user="u", limit=5) == []
        flt = query.call_args.args[0]
        assert flt.actions == security_layer.COMMAND_EXECUTION_ACTIONS
        assert (flt.actor_id, flt.resource_type) == ("u", security_layer.SECURITY_LAYER_SOURCE)
        assert query.call_args.kwargs == {"limit": 5}

    @pytest.mark.asyncio
    async def test_entries_come_back_in_the_layers_shape(self):
        stored = {
            "action": "command_execution_attempt",
            "actor_id": "test_user",
            "outcome": "success",
            "metadata": {"command": "ls"},
            "occurred_at": 0.0,
        }
        with patch("security_layer.query_filtered", new=AsyncMock(return_value=[stored])):
            entries = await self.security.get_audit_entries(limit=1)
        assert entries == [
            {
                "timestamp": "1970-01-01T00:00:00+00:00",
                "user": "test_user",
                "action": "command_execution_attempt",
                "outcome": "success",
                "details": {"command": "ls"},
            }
        ]

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
class TestSecurityLayerIntegration:
    """Integration tests for SecurityLayer with SecureCommandExecutor"""

    def setup_method(self):
        """Set up test fixtures"""
        self.emit_patcher = patch("security_layer.emit_security", return_value=True)
        self.emit_patcher.start()
        with patch("security_layer.get_config_manager") as mock_get_cm:
            mock_config = mock_get_cm.return_value
            mock_config.get.return_value = {
                "enable_auth": False,
                "enable_command_security": True,
                "command_approval_required": False,  # Disable for integration tests
                "use_docker_sandbox": False,
            }
            self.security = SecurityLayer()

    def teardown_method(self):
        """Stop capturing audit records."""
        self.emit_patcher.stop()

    @pytest.mark.asyncio
    async def test_end_to_end_safe_command(self):
        """Test end-to-end execution of safe command"""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"hello world\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await self.security.execute_command("echo 'hello world'", "test_user", "admin")

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


class TestAuditLogFileDefault:
    """The audit-log default resolves from the canonical project root (#13149, #14070).

    Asserted through the value the module actually uses (``_AUDIT_LOG_FILE``)
    and the single canonical formula (``ssot_config.default_audit_log_file``).
    The module-level copy ``_AUDIT_LOG_FILE_DEFAULT`` these tests used to name
    is gone: it was a second hand-written spelling of the same formula (#14070).
    """

    def test_default_is_not_the_live_install(self):
        """The property that matters: a dev run must not resolve under /opt/autobot."""
        assert not default_audit_log_file().startswith("/opt/autobot")

    def test_default_is_wired_to_the_canonical_resolver(self):
        assert default_audit_log_file() == str(project_root() / "logs" / "audit.log")

    def test_default_tracks_project_root_env_override(self, monkeypatch, tmp_path):
        fake_root = tmp_path / "fake-checkout"
        fake_root.mkdir()
        monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", str(fake_root))

        assert default_audit_log_file() == str(fake_root / "logs" / "audit.log")

    def test_deployed_install_still_resolves_to_the_original_default(self, monkeypatch):
        """Compositional check for the deployed case — see the equivalent test
        in ``source_paths_test.py`` for why AUTOBOT_PROJECT_ROOT stands in for
        the real ``.env``-walk here, and why full host verification is out of
        scope for a hermetic test.
        """
        monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", "/opt/autobot")

        assert default_audit_log_file() == str(Path("/opt/autobot/logs/audit.log"))


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
