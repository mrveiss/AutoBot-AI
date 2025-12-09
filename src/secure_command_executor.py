# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Secure Command Executor with Sandboxing and Permission Controls
Implements security measures to prevent arbitrary command execution
"""

import asyncio
import logging
import os
import re
import shlex
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.constants.network_constants import NetworkConstants
from src.utils.command_utils import execute_shell_command

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozensets for path checking
_SYSTEM_PATHS = frozenset({"/etc", "/usr", "/bin", "/sbin", "/lib"})
_SENSITIVE_REDIRECT_PATHS = frozenset({"/etc/", "/boot/", "/sys/"})


class CommandRisk(Enum):
    """Risk levels for commands"""

    SAFE = "safe"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    FORBIDDEN = "forbidden"


class SecurityPolicy:
    """Security policy for command execution"""

    def __init__(self):
        """
        Initialize security policy with command classifications and path restrictions.

        Issue #281: Refactored from 148 lines to use extracted helper methods.
        """
        self.safe_commands = self._get_safe_commands()
        self.moderate_commands = self._get_moderate_commands()
        self.high_risk_commands = self._get_high_risk_commands()
        self.forbidden_commands = self._get_forbidden_commands()
        self.dangerous_patterns = self._get_dangerous_patterns()
        self.allowed_paths = self._get_allowed_paths()
        self.allowed_extensions = self._get_allowed_extensions()

    def _get_safe_commands(self) -> set:
        """Safe commands that can run without approval. Issue #281: Extracted helper."""
        return {
            "echo", "date", "pwd", "whoami", "hostname", "uname",
            "cat", "head", "tail", "wc", "sort", "uniq", "grep", "find",
            "ls", "tree", "which", "env", "printenv",
            "ps", "top", "htop", "d", "du", "free", "uptime",
            "ping", "curl", "wget", "git", "npm", "python", "pip",
        }

    def _get_moderate_commands(self) -> set:
        """Commands that need approval for certain arguments. Issue #281: Extracted helper."""
        return {
            "cp", "mv", "mkdir", "touch", "chmod", "chown",
            "tar", "zip", "unzip", "gzip", "gunzip",
            "sed", "awk", "cut", "paste", "join",
        }

    def _get_high_risk_commands(self) -> set:
        """High-risk commands that always need approval. Issue #281: Extracted helper."""
        return {
            "rm", "rmdir", "dd", "mkfs", "fdisk", "parted",
            "mount", "umount", "chroot", "sudo", "su",
            "systemctl", "service", "apt", "apt-get", "dpkg",
            "yum", "dn", "zypper", "pacman",
        }

    def _get_forbidden_commands(self) -> set:
        """Forbidden commands that should never run. Issue #281: Extracted helper."""
        return {
            "shutdown", "reboot", "halt", "powerof",
            "init", "telinit", "kill", "killall", "pkill",
        }

    def _get_dangerous_patterns(self) -> list:
        """Dangerous patterns in arguments. Issue #281: Extracted helper."""
        return [
            r"rm\s+-rf\s+/",  # rm -rf /
            r">\s*/dev/sd[a-z]",  # Overwrite disk
            r"dd\s+.*of=/dev/",  # dd to device
            r"/etc/passwd",  # Password file
            r"/etc/shadow",  # Shadow file
            r":(){ :|:& };:",  # Fork bomb
            r"\$\(.*\)",  # Command substitution
            r"`.*`",  # Backtick substitution
            r";\s*rm\s+-r",  # Command chaining with rm
            r"&&\s*rm\s+-r",  # Conditional rm
            r"\|\s*rm\s+-r",  # Piped to rm
        ]

    def _get_allowed_paths(self) -> list:
        """Allowed directories for file operations. Issue #281: Extracted helper."""
        return [
            Path.home(),  # User home directory
            Path("/tmp"),  # Temporary directory
            Path("/var/tmp"),  # Var temporary
            Path.cwd(),  # Current working directory
        ]

    def _get_allowed_extensions(self) -> set:
        """File extensions that can be modified. Issue #281: Extracted helper."""
        return {
            ".txt", ".log", ".json", ".yaml", ".yml", ".md",
            ".py", ".js", ".ts", ".jsx", ".tsx", ".vue",
            ".html", ".css", ".scss", ".sass",
            ".sh", ".bash", ".zsh", ".con", ".cfg", ".ini", ".env",
            ".csv", ".tsv", ".xml",
        }


class SecureCommandExecutor:
    """
    Secure command executor with sandboxing and permission controls
    """

    def __init__(
        self,
        policy: Optional[SecurityPolicy] = None,
        require_approval_callback=None,
        use_docker_sandbox: bool = False,
    ):
        """
        Initialize secure command executor

        Args:
            policy: Security policy to use (default: SecurityPolicy())
            require_approval_callback: Async callback function for user approval
            use_docker_sandbox: Whether to execute commands in Docker container
        """
        self.policy = policy or SecurityPolicy()
        self.require_approval_callback = require_approval_callback
        self.use_docker_sandbox = use_docker_sandbox
        self.docker_image = "autobot-sandbox:latest"

        # Command history for audit
        self.command_history: List[Dict[str, Any]] = []

    def _extract_command_name(self, command: str) -> str:
        """Extract the base command name from a command string"""
        try:
            parts = shlex.split(command)
            if parts:
                # Handle cases like /usr/bin/ls
                return os.path.basename(parts[0])
        except ValueError:
            # Fallback for malformed commands
            parts = command.split()
            if parts:
                return os.path.basename(parts[0])
        return ""

    def _check_dangerous_patterns(self, command: str) -> List[str]:
        """Check command for dangerous patterns"""
        found_patterns = []
        for pattern in self.policy.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                found_patterns.append(pattern)
        return found_patterns

    def _check_path_access(self, command: str) -> bool:
        """Check if file operations are within allowed paths"""
        # This is a simplified check - in production, parse command properly
        # to extract all file paths
        for allowed_path in self.policy.allowed_paths:
            if str(allowed_path) in command:
                return True
        return False

    def assess_command_risk(self, command: str) -> tuple[CommandRisk, List[str]]:
        """
        Assess the risk level of a command

        Returns:
            (risk_level, list_of_reasons)
        """
        reasons = []
        base_command = self._extract_command_name(command)

        # Check for empty or malformed commands
        if not base_command:
            return CommandRisk.FORBIDDEN, ["Empty or malformed command"]

        # Check dangerous patterns first
        dangerous_patterns = self._check_dangerous_patterns(command)
        if dangerous_patterns:
            reasons.extend([f"Dangerous pattern: {p}" for p in dangerous_patterns])
            return CommandRisk.FORBIDDEN, reasons

        # Check command categories
        if base_command in self.policy.forbidden_commands:
            reasons.append(f"Forbidden command: {base_command}")
            return CommandRisk.FORBIDDEN, reasons

        if base_command in self.policy.high_risk_commands:
            reasons.append(f"High-risk command: {base_command}")
            return CommandRisk.HIGH, reasons

        if base_command in self.policy.moderate_commands:
            reasons.append(f"Moderate-risk command: {base_command}")
            # Check if it involves system paths - Issue #380: Use module-level frozenset
            if any(path in command for path in _SYSTEM_PATHS):
                reasons.append("Operates on system paths")
                return CommandRisk.HIGH, reasons
            return CommandRisk.MODERATE, reasons

        if base_command in self.policy.safe_commands:
            # Even safe commands can be risky with certain arguments
            if "sudo" in command or command.startswith("sudo"):
                reasons.append("Uses sudo elevation")
                return CommandRisk.HIGH, reasons

            # Check for output redirection to sensitive files - Issue #380
            if ">" in command or ">>" in command:
                if any(sensitive in command for sensitive in _SENSITIVE_REDIRECT_PATHS):
                    reasons.append("Redirects to sensitive location")
                    return CommandRisk.HIGH, reasons

            return CommandRisk.SAFE, ["Safe command"]

        # Unknown command - treat as moderate risk
        reasons.append(f"Unknown command: {base_command}")
        return CommandRisk.MODERATE, reasons

    async def _request_approval(
        self, command: str, risk: CommandRisk, reasons: List[str]
    ) -> bool:
        """Request user approval for command execution"""
        if self.require_approval_callback:
            approval_data = {
                "command": command,
                "risk": risk.value,
                "reasons": reasons,
                "timestamp": asyncio.get_event_loop().time(),
            }
            return await self.require_approval_callback(approval_data)

        # If no callback, log and deny by default for safety
        logger.warning(f"No approval callback set. Denying command: {command}")
        return False

    def _build_docker_command(self, command: str) -> str:
        """Build Docker command for sandboxed execution"""
        # Create a minimal sandbox container
        docker_cmd = [
            "docker",
            "run",
            "--rm",  # Remove container after execution
            "--read-only",  # Read-only root filesystem
            "--network",
            "none",  # No network access
            "--memory",
            "512m",  # Memory limit
            "--cpus",
            "1.0",  # CPU limit
            "--user",
            NetworkConstants.DEFAULT_USER_GROUP,  # Non-root user
            "-v",
            f"{os.getcwd()}:/workspace:ro",  # Mount current dir read-only
            "-w",
            "/workspace",
            self.docker_image,
            "sh",
            "-c",
            command,
        ]
        return " ".join(docker_cmd)

    def _build_blocked_result(
        self,
        risk: CommandRisk,
        reasons: List[str],
        message: str,
    ) -> Dict[str, Any]:
        """
        Build result dict for blocked/denied commands.

        Issue #281: Extracted helper for blocked result building.

        Args:
            risk: Risk level of command
            reasons: List of risk reasons
            message: Error message for stderr

        Returns:
            Result dict with error status and security info
        """
        return {
            "stdout": "",
            "stderr": message,
            "return_code": 1,
            "status": "error",
            "security": {"risk": risk.value, "reasons": reasons, "blocked": True},
        }

    def _build_error_result(
        self,
        risk: CommandRisk,
        reasons: List[str],
        error_type: str,
        error_msg: str,
    ) -> Dict[str, Any]:
        """
        Build result dict for execution errors.

        Issue #281: Extracted helper for error result building.

        Args:
            risk: Risk level of command
            reasons: List of risk reasons
            error_type: Type of error (timeout, error)
            error_msg: Error message

        Returns:
            Result dict with error status
        """
        return_code = 124 if error_type == "timeout" else 1
        security_info = {"risk": risk.value, "reasons": reasons, error_type: True}
        if error_type == "error":
            security_info["error"] = error_msg

        return {
            "stdout": "",
            "stderr": error_msg,
            "return_code": return_code,
            "status": "error",
            "security": security_info,
        }

    async def run_shell_command(
        self, command: str, force_approval: bool = False
    ) -> Dict[str, Any]:
        """
        Securely execute a shell command with risk assessment and sandboxing.

        Issue #281: Refactored from 111 lines to use extracted helper methods.

        Args:
            command: The shell command to execute
            force_approval: Force user approval regardless of risk level

        Returns:
            Dictionary containing execution results and security info
        """
        risk, reasons = self.assess_command_risk(command)

        log_entry = {
            "command": command,
            "risk": risk.value,
            "reasons": reasons,
            "timestamp": asyncio.get_event_loop().time(),
            "approved": False,
            "executed": False,
        }

        # Handle forbidden commands (Issue #281: uses helper)
        if risk == CommandRisk.FORBIDDEN:
            logger.error(f"Forbidden command blocked: {command}")
            log_entry["error"] = "Command forbidden by security policy"
            self.command_history.append(log_entry)
            return self._build_blocked_result(
                risk, reasons, f"Command forbidden: {'; '.join(reasons)}"
            )

        # Handle approval flow
        needs_approval = force_approval or risk in {CommandRisk.HIGH, CommandRisk.MODERATE}

        if needs_approval:
            approved = await self._request_approval(command, risk, reasons)
            log_entry["approved"] = approved

            if not approved:
                logger.warning(f"Command denied by user: {command}")
                log_entry["error"] = "User denied execution"
                self.command_history.append(log_entry)
                return self._build_blocked_result(
                    risk, reasons, "Command execution denied by user"
                )

        # Prepare command for execution
        if self.use_docker_sandbox and risk != CommandRisk.SAFE:
            actual_command = self._build_docker_command(command)
            logger.info(f"Executing in Docker sandbox: {command}")
        else:
            actual_command = command

        # Execute command
        try:
            result = await execute_shell_command(actual_command)

            log_entry["executed"] = True
            log_entry["return_code"] = result["return_code"]
            self.command_history.append(log_entry)

            result["security"] = {
                "risk": risk.value,
                "reasons": reasons,
                "sandboxed": self.use_docker_sandbox and risk != CommandRisk.SAFE,
                "approved": needs_approval,
            }
            return result

        except asyncio.TimeoutError:
            logger.error(f"Command timed out: {command}")
            log_entry["error"] = "Command timed out"
            self.command_history.append(log_entry)
            return self._build_error_result(
                risk, reasons, "timeout", "Command execution timed out after 5 minutes"
            )
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            log_entry["error"] = str(e)
            self.command_history.append(log_entry)
            return self._build_error_result(
                risk, reasons, "error", f"Error executing command: {e}"
            )

    def get_command_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent command history for audit purposes"""
        return self.command_history[-limit:]

    def clear_history(self):
        """Clear command history"""
        self.command_history.clear()


# Example usage and testing
if __name__ == "__main__":

    async def example_approval_callback(approval_data: Dict[str, Any]) -> bool:
        """Example approval callback that auto-approves safe commands"""
        print("\n🔒 Approval Request:")
        print(f"Command: {approval_data['command']}")
        print(f"Risk: {approval_data['risk']}")
        print(f"Reasons: {', '.join(approval_data['reasons'])}")

        # In real implementation, this would ask the user
        # For demo, auto-approve moderate risk, deny high risk
        if approval_data["risk"] == "moderate":
            print("✅ Auto-approved (moderate risk)")
            return True
        else:
            print("❌ Auto-denied (high risk)")
            return False

    async def test_commands():
        """Test secure command executor with various risk-level commands."""
        # Create executor with approval callback
        executor = SecureCommandExecutor(
            require_approval_callback=example_approval_callback,
            use_docker_sandbox=False,  # Set to True to test Docker sandboxing
        )

        # Test various commands
        test_cases = [
            "echo 'Hello, secure world!'",  # Safe
            "ls -la /tmp",  # Safe
            "rm test.txt",  # High risk
            "sudo apt update",  # High risk
            "mkdir /tmp/test",  # Moderate risk
            "rm -rf /",  # Forbidden
            "cat /etc/passwd",  # Dangerous pattern
            "echo test > /tmp/safe.txt",  # Safe with redirection
            "curl https://example.com",  # Safe
        ]

        for cmd in test_cases:
            print(f"\n{'='*60}")
            print(f"Testing: {cmd}")
            result = await executor.run_shell_command(cmd)
            print(f"Status: {result['status']}")
            print(f"Security: {result.get('security', {})}")
            if result["stdout"]:
                print(f"Output: {result['stdout'][:100]}...")

        # Show command history
        print(f"\n{'='*60}")
        print("Command History:")
        for entry in executor.get_command_history():
            print(
                f"- {entry['command']}: {entry['risk']} "
                f"(approved: {entry.get('approved', 'N/A')}, "
                f"executed: {entry['executed']})"
            )

    asyncio.run(test_commands())
