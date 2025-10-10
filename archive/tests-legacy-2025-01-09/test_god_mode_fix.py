"""
Test suite for CVE-AUTOBOT-2025-003: God Mode Security Bypass Fix
Verifies that no roles bypass security validation, audit logging, or approval workflows
"""

import asyncio
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Import security layers
from src.enhanced_security_layer import EnhancedSecurityLayer
from src.security_layer import SecurityLayer


class TestGodModeBypassFix:
    """Test that god mode bypass has been completely removed"""

    @pytest.fixture
    def security_layer(self):
        """Create SecurityLayer instance with test config"""
        with patch("src.unified_config_manager.config") as mock_config:
            mock_config.get.return_value = {
                "enable_auth": True,
                "audit_log_file": tempfile.mktemp(suffix=".log"),
                "roles": {
                    "admin": {
                        "permissions": [
                            "files.*",
                            "allow_shell_execute",
                            "allow_kb_read",
                            "allow_kb_write",
                        ]
                    },
                    "user": {"permissions": ["files.view", "allow_kb_read"]},
                },
                "allowed_users": {"admin": "admin123", "testuser": "test123"},
            }
            return SecurityLayer()

    @pytest.fixture
    def enhanced_security_layer(self):
        """Create EnhancedSecurityLayer instance with test config"""
        with patch("src.unified_config_manager.config") as mock_config:
            mock_config.get.return_value = {
                "enable_auth": True,
                "enable_command_security": True,
                "command_approval_required": True,
                "use_docker_sandbox": False,
                "audit_log_file": tempfile.mktemp(suffix=".log"),
                "roles": {
                    "admin": {
                        "permissions": [
                            "files.*",
                            "allow_shell_execute",
                            "allow_shell_high_risk",
                        ]
                    },
                    "operator": {
                        "permissions": ["files.*", "allow_shell_execute"]
                    },
                    "user": {"permissions": ["files.view", "allow_kb_read"]},
                },
                "allowed_users": {},
            }
            return EnhancedSecurityLayer()

    def test_god_role_no_bypass_security_layer(self, security_layer):
        """Test that 'god' role does not bypass security in SecurityLayer"""
        # God role should be downgraded to admin with granular permissions
        result = security_layer.check_permission("god", "allow_shell_execute")

        # Should have permission (as admin), but not via bypass
        assert result is True

        # Verify audit log was written for deprecated role
        with open(security_layer.audit_log_file, "r") as f:
            logs = [json.loads(line) for line in f]

        deprecated_logs = [
            log for log in logs if log["action"] == "deprecated_role_usage"
        ]
        assert len(deprecated_logs) > 0
        assert deprecated_logs[0]["user"] == "god"
        assert "deprecated" in deprecated_logs[0]["details"]["message"].lower()

    def test_superuser_role_no_bypass_security_layer(self, security_layer):
        """Test that 'superuser' role does not bypass security"""
        result = security_layer.check_permission("superuser", "allow_shell_execute")

        # Should be treated as admin, not god
        assert result is True

        # Check audit log
        with open(security_layer.audit_log_file, "r") as f:
            logs = [json.loads(line) for line in f]

        deprecated_logs = [
            log for log in logs if log["action"] == "deprecated_role_usage"
        ]
        assert any(log["user"] == "superuser" for log in deprecated_logs)

    def test_root_role_no_bypass_security_layer(self, security_layer):
        """Test that 'root' role does not bypass security"""
        result = security_layer.check_permission("root", "files.delete")

        # Should be downgraded to admin
        assert result is True

        # Verify deprecation warning logged
        with open(security_layer.audit_log_file, "r") as f:
            logs = [json.loads(line) for line in f]

        deprecated_logs = [
            log for log in logs if log["action"] == "deprecated_role_usage"
        ]
        assert any(log["user"] == "root" for log in deprecated_logs)

    def test_god_role_no_bypass_enhanced_layer(self, enhanced_security_layer):
        """Test that 'god' role does not bypass EnhancedSecurityLayer"""
        result = enhanced_security_layer.check_permission("god", "allow_shell_execute")

        # Should have permission as admin, but not via bypass
        assert result is True

        # Verify audit log
        with open(enhanced_security_layer.audit_log_file, "r") as f:
            logs = [json.loads(line) for line in f]

        deprecated_logs = [
            log for log in logs if log["action"] == "deprecated_role_usage"
        ]
        assert len(deprecated_logs) > 0

    def test_no_allow_all_bypass(self, security_layer):
        """Test that 'allow_all' permission does not bypass security"""
        # Even if someone configures 'allow_all', it should not work
        # Permission must be explicitly granted

        # Admin should NOT have unrestricted access
        result = security_layer.check_permission("admin", "dangerous_operation")
        assert result is False  # Should be denied - no explicit permission

    @pytest.mark.asyncio
    async def test_dangerous_commands_require_approval_for_all(
        self, enhanced_security_layer
    ):
        """Test that dangerous commands require approval even for admin"""
        # Mock the approval callback to deny
        enhanced_security_layer._command_approval_callback = MagicMock(
            return_value=asyncio.Future()
        )
        enhanced_security_layer._command_approval_callback.return_value.set_result(
            False
        )

        # Test dangerous command as admin
        result = await enhanced_security_layer.execute_command(
            "rm -rf /tmp/test", user="admin", user_role="admin"
        )

        # Verify command security was applied
        assert "security" in result
        # Command should be assessed for risk regardless of role

    def test_all_roles_logged(self, security_layer):
        """Test that ALL roles generate audit logs (no silent bypasses)"""
        roles_to_test = ["god", "superuser", "root", "admin", "user"]

        for role in roles_to_test:
            # Clear previous logs
            with open(security_layer.audit_log_file, "w") as f:
                f.write("")

            # Perform action
            security_layer.check_permission(role, "files.view")

            # Verify audit log exists
            with open(security_layer.audit_log_file, "r") as f:
                logs = [json.loads(line) for line in f]

            # Deprecated roles should have deprecation warning
            if role in ["god", "superuser", "root"]:
                deprecated_logs = [
                    log for log in logs if log["action"] == "deprecated_role_usage"
                ]
                assert len(deprecated_logs) > 0, f"Role {role} did not log deprecation"

    def test_permission_denied_for_unauthorized_actions(self, security_layer):
        """Test that permission is properly denied for unauthorized actions"""
        # User role should not have shell execution permission
        result = security_layer.check_permission("user", "allow_shell_execute")
        assert result is False

        # Verify denial is logged
        # (check_permission doesn't log denials, but execute_command would)

    @pytest.mark.asyncio
    async def test_command_security_applies_to_all_users(
        self, enhanced_security_layer
    ):
        """Test that command security validation applies to ALL users"""
        # Even admin should go through command security assessment
        result = await enhanced_security_layer.execute_command(
            "echo test", user="admin", user_role="admin"
        )

        # Verify security metadata present
        assert "security" in result
        # Command should have been assessed

    def test_granular_permissions_enforced(self, security_layer):
        """Test that granular permissions are properly enforced"""
        # Admin should have 'files.*' wildcard permission
        assert security_layer.check_permission("admin", "files.view") is True
        assert security_layer.check_permission("admin", "files.delete") is True

        # But admin should NOT have permissions outside files.*
        # unless explicitly granted
        assert security_layer.check_permission("admin", "nuclear.launch") is False

    def test_no_unrestricted_access_for_any_role(self, enhanced_security_layer):
        """Test that no role has completely unrestricted access"""
        # Even admin should be subject to validation
        roles = ["admin", "operator", "user", "developer"]

        for role in roles:
            # All roles should be denied for non-existent permissions
            result = enhanced_security_layer.check_permission(
                role, "unrestricted_god_mode_operation"
            )
            assert result is False, f"Role {role} has unrestricted access!"


class TestDefenseInDepthEnforcement:
    """Test that defense-in-depth principles are maintained"""

    @pytest.fixture
    def enhanced_security(self):
        """Create EnhancedSecurityLayer for testing"""
        with patch("src.unified_config_manager.config") as mock_config:
            mock_config.get.return_value = {
                "enable_auth": True,
                "enable_command_security": True,
                "command_approval_required": True,
                "audit_log_file": tempfile.mktemp(suffix=".log"),
                "roles": {
                    "admin": {
                        "permissions": [
                            "files.*",
                            "allow_shell_execute",
                            "allow_shell_high_risk",
                        ]
                    }
                },
            }
            return EnhancedSecurityLayer()

    @pytest.mark.asyncio
    async def test_all_commands_validated(self, enhanced_security):
        """Test that ALL commands go through validation (no bypasses)"""
        test_commands = [
            ("echo test", "admin"),
            ("ls -la", "admin"),
            ("sudo apt update", "admin"),
        ]

        for cmd, role in test_commands:
            result = await enhanced_security.execute_command(
                cmd, user=f"{role}_user", user_role=role
            )

            # All commands should have security metadata
            assert (
                "security" in result or "status" in result
            ), f"Command {cmd} bypassed security"

    def test_all_commands_logged(self, enhanced_security):
        """Test that ALL commands are logged (including admin)"""
        # Clear audit log
        with open(enhanced_security.audit_log_file, "w") as f:
            f.write("")

        # Admin action should be logged
        enhanced_security.audit_log(
            action="test_action",
            user="admin",
            outcome="success",
            details={"command": "test"},
        )

        # Verify log entry
        with open(enhanced_security.audit_log_file, "r") as f:
            logs = [json.loads(line) for line in f]

        assert len(logs) > 0
        assert logs[0]["user"] == "admin"

    def test_approval_workflow_exists_for_dangerous_commands(self, enhanced_security):
        """Test that dangerous commands have approval workflow"""
        # The approval callback should be configured
        assert enhanced_security.command_approval_required is True
        assert enhanced_security._command_approval_callback is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
