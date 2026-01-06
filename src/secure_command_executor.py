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
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from src.constants.network_constants import NetworkConstants
from src.utils.command_utils import execute_shell_command

# Permission system imports (lazy to avoid circular imports)
if TYPE_CHECKING:
    from backend.services.permission_matcher import PermissionMatcher, MatchResult
    from backend.services.approval_memory import ApprovalMemoryManager

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
    Secure command executor with sandboxing and permission controls.

    Supports two permission models:
    1. Risk-based (default): Commands assessed by risk level (SAFE/MODERATE/HIGH/FORBIDDEN)
    2. Claude Code-style: Glob-pattern rules with ALLOW/ASK/DENY/DEFAULT actions

    When permission_v2 is enabled, the order is:
    1. Check permission rules (DENY > ASK > ALLOW)
    2. Check approval memory (per-project remembered approvals)
    3. Fall back to risk-based assessment (DEFAULT case)
    """

    def __init__(
        self,
        policy: Optional[SecurityPolicy] = None,
        require_approval_callback=None,
        use_docker_sandbox: bool = False,
        is_admin: bool = False,
        project_path: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """
        Initialize secure command executor

        Args:
            policy: Security policy to use (default: SecurityPolicy())
            require_approval_callback: Async callback function for user approval
            use_docker_sandbox: Whether to execute commands in Docker container
            is_admin: Whether current user has admin privileges (for permission v2)
            project_path: Current project path (for approval memory)
            user_id: Current user ID (for approval memory)
        """
        self.policy = policy or SecurityPolicy()
        self.require_approval_callback = require_approval_callback
        self.use_docker_sandbox = use_docker_sandbox
        self.docker_image = "autobot-sandbox:latest"

        # Permission v2 attributes
        self.is_admin = is_admin
        self.project_path = project_path
        self.user_id = user_id

        # Lazy-loaded permission matcher and approval memory
        self._permission_matcher: Optional["PermissionMatcher"] = None
        self._approval_memory: Optional["ApprovalMemoryManager"] = None

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

    def _get_permission_matcher(self) -> Optional["PermissionMatcher"]:
        """
        Get or create the permission matcher (lazy initialization).

        Returns:
            PermissionMatcher instance if permission v2 is enabled, None otherwise
        """
        from src.config.ssot_config import config

        if not config.permission.enabled:
            return None

        if self._permission_matcher is None:
            try:
                from backend.services.permission_matcher import PermissionMatcher
                self._permission_matcher = PermissionMatcher(is_admin=self.is_admin)
            except ImportError as e:
                logger.warning(f"Permission matcher not available: {e}")
                return None

        return self._permission_matcher

    def _get_approval_memory(self) -> Optional["ApprovalMemoryManager"]:
        """
        Get or create the approval memory manager (lazy initialization).

        Returns:
            ApprovalMemoryManager instance if enabled, None otherwise
        """
        from src.config.ssot_config import config

        if not config.permission.enabled or not config.permission.approval_memory_enabled:
            return None

        if self._approval_memory is None:
            try:
                from backend.services.approval_memory import ApprovalMemoryManager
                self._approval_memory = ApprovalMemoryManager()
            except ImportError as e:
                logger.warning(f"Approval memory not available: {e}")
                return None

        return self._approval_memory

    async def check_permission_rules(
        self, command: str, tool: str = "Bash"
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Check command against Claude Code-style permission rules.

        Called BEFORE risk assessment when permission v2 is enabled.

        Args:
            command: The command to check
            tool: The tool name (default: "Bash")

        Returns:
            Tuple of (action, rule_info) where:
            - action is "allow", "ask", "deny", or None (for default/risk-based)
            - rule_info contains matched rule details or None
        """
        matcher = self._get_permission_matcher()
        if not matcher:
            return None, None

        try:
            from backend.services.permission_matcher import MatchResult

            result, rule = matcher.match(tool, command)

            if result == MatchResult.DENY:
                rule_info = {
                    "action": "deny",
                    "pattern": rule.pattern if rule else None,
                    "description": rule.description if rule else "Denied by permission rule",
                }
                return "deny", rule_info

            if result == MatchResult.ASK:
                rule_info = {
                    "action": "ask",
                    "pattern": rule.pattern if rule else None,
                    "description": rule.description if rule else "Requires approval",
                }
                return "ask", rule_info

            if result == MatchResult.ALLOW:
                # Check approval memory for project-specific overrides
                if await self._check_approval_memory(command, tool):
                    rule_info = {
                        "action": "allow",
                        "pattern": rule.pattern if rule else None,
                        "description": rule.description if rule else "Allowed by rule",
                        "from_memory": True,
                    }
                    return "allow", rule_info

                rule_info = {
                    "action": "allow",
                    "pattern": rule.pattern if rule else None,
                    "description": rule.description if rule else "Allowed by rule",
                }
                return "allow", rule_info

            # DEFAULT - fall through to risk-based assessment
            # But still check approval memory
            if await self._check_approval_memory(command, tool):
                return "allow", {"action": "allow", "from_memory": True}

            return None, None

        except Exception as e:
            logger.error(f"Permission rule check failed: {e}")
            return None, None

    async def _check_approval_memory(self, command: str, tool: str = "Bash") -> bool:
        """
        Check if command is remembered in approval memory.

        Args:
            command: The command to check
            tool: The tool name

        Returns:
            True if command should be auto-approved from memory
        """
        if not self.project_path or not self.user_id:
            return False

        memory = self._get_approval_memory()
        if not memory:
            return False

        try:
            # Get risk level for memory check
            risk, _ = self.assess_command_risk(command)
            return await memory.check_remembered(
                project_path=self.project_path,
                command=command,
                user_id=self.user_id,
                risk_level=risk.value,
                tool=tool,
            )
        except Exception as e:
            logger.error(f"Approval memory check failed: {e}")
            return False

    async def store_approval_memory(
        self,
        command: str,
        risk_level: str,
        tool: str = "Bash",
        comment: Optional[str] = None,
    ) -> bool:
        """
        Store a command approval in memory for future auto-approval.

        Called when user approves a command with "Remember" checkbox.

        Args:
            command: The approved command
            risk_level: Risk level of the command
            tool: Tool name
            comment: Optional approval comment

        Returns:
            True if stored successfully
        """
        if not self.project_path or not self.user_id:
            logger.debug("Cannot store approval: no project_path or user_id")
            return False

        memory = self._get_approval_memory()
        if not memory:
            return False

        try:
            return await memory.remember_approval(
                project_path=self.project_path,
                command=command,
                user_id=self.user_id,
                risk_level=risk_level,
                tool=tool,
                comment=comment,
            )
        except Exception as e:
            logger.error(f"Failed to store approval memory: {e}")
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
        logger.warning("No approval callback set. Denying command: %s", command)
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

    def _build_permission_deny_result(
        self, command: str, rule_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Build result dict for permission rule denied commands.

        Args:
            command: The denied command
            rule_info: Permission rule info dict

        Returns:
            Result dict with error status and permission info
        """
        logger.warning(f"Command denied by permission rule: {command}")
        return {
            "stdout": "",
            "stderr": f"Command denied by permission rule: {rule_info.get('description', 'Denied')}",
            "return_code": 1,
            "status": "error",
            "security": {
                "risk": "forbidden",
                "reasons": [rule_info.get("description", "Denied by rule")],
                "blocked": True,
                "permission_rule": rule_info,
            },
        }

    def _build_auto_approved_log_entry(
        self,
        command: str,
        risk: CommandRisk,
        reasons: List[str],
        rule_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Build log entry for auto-approved commands.

        Args:
            command: The command being executed
            risk: Risk level of command
            reasons: Risk assessment reasons
            rule_info: Optional permission rule info

        Returns:
            Log entry dict for command history
        """
        auto_approved_by = "permission_rule"
        if rule_info and rule_info.get("from_memory"):
            auto_approved_by = "approval_memory"

        return {
            "command": command,
            "risk": risk.value,
            "reasons": reasons,
            "timestamp": asyncio.get_event_loop().time(),
            "approved": True,
            "executed": False,
            "auto_approved_by": auto_approved_by,
        }

    def _build_standard_log_entry(
        self, command: str, risk: CommandRisk, reasons: List[str]
    ) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Build standard log entry for risk-based assessment.

        Args:
            command: The command being executed
            risk: Risk level of command
            reasons: Risk assessment reasons

        Returns:
            Log entry dict for command history
        """
        return {
            "command": command,
            "risk": risk.value,
            "reasons": reasons,
            "timestamp": asyncio.get_event_loop().time(),
            "approved": False,
            "executed": False,
        }

    async def _handle_forbidden_command(
        self, command: str, risk: CommandRisk, reasons: List[str], log_entry: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Handle forbidden commands by logging and returning blocked result.

        Args:
            command: The forbidden command
            risk: Risk level (should be FORBIDDEN)
            reasons: List of risk reasons
            log_entry: Log entry dict to update

        Returns:
            Blocked result dict
        """
        logger.error("Forbidden command blocked: %s", command)
        log_entry["error"] = "Command forbidden by security policy"
        self.command_history.append(log_entry)
        return self._build_blocked_result(
            risk, reasons, f"Command forbidden: {'; '.join(reasons)}"
        )

    async def _handle_approval_flow(
        self,
        command: str,
        risk: CommandRisk,
        reasons: List[str],
        log_entry: Dict[str, Any],
        force_approval: bool,
        permission_action: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Handle approval flow for commands that need user approval.

        Args:
            command: The command to approve
            risk: Risk level of command
            reasons: Risk assessment reasons
            log_entry: Log entry dict to update
            force_approval: Whether to force approval
            permission_action: Permission action from rule check

        Returns:
            Blocked result dict if denied, None if approved
        """
        needs_approval = (
            force_approval
            or permission_action == "ask"
            or risk in {CommandRisk.HIGH, CommandRisk.MODERATE}
        )

        if needs_approval:
            approved = await self._request_approval(command, risk, reasons)
            log_entry["approved"] = approved

            if not approved:
                logger.warning("Command denied by user: %s", command)
                log_entry["error"] = "User denied execution"
                self.command_history.append(log_entry)
                return self._build_blocked_result(
                    risk, reasons, "Command execution denied by user"
                )

        return None

    async def _execute_command(
        self,
        command: str,
        risk: CommandRisk,
        reasons: List[str],
        log_entry: Dict[str, Any],
        rule_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a command after permission/risk checks.

        Internal helper used by run_shell_command for actual execution.

        Args:
            command: The shell command to execute
            risk: Assessed risk level
            reasons: Risk assessment reasons
            log_entry: Log entry dict to update
            rule_info: Optional permission rule info

        Returns:
            Execution result dictionary
        """
        # Prepare command for execution
        if self.use_docker_sandbox and risk != CommandRisk.SAFE:
            actual_command = self._build_docker_command(command)
            logger.info("Executing in Docker sandbox: %s", command)
        else:
            actual_command = command

        # Execute command
        try:
            result = await execute_shell_command(actual_command)

            log_entry["executed"] = True
            log_entry["return_code"] = result["return_code"]
            self.command_history.append(log_entry)

            security_info = {
                "risk": risk.value,
                "reasons": reasons,
                "sandboxed": self.use_docker_sandbox and risk != CommandRisk.SAFE,
                "approved": log_entry.get("approved", False),
            }

            # Add permission rule info if present
            if rule_info:
                security_info["permission_rule"] = rule_info
                if rule_info.get("from_memory"):
                    security_info["auto_approved_by"] = "approval_memory"
                else:
                    security_info["auto_approved_by"] = "permission_rule"

            result["security"] = security_info
            return result

        except asyncio.TimeoutError:
            logger.error("Command timed out: %s", command)
            log_entry["error"] = "Command timed out"
            self.command_history.append(log_entry)
            return self._build_error_result(
                risk, reasons, "timeout", "Command execution timed out after 5 minutes"
            )
        except Exception as e:
            logger.error("Command execution error: %s", e)
            log_entry["error"] = str(e)
            self.command_history.append(log_entry)
            return self._build_error_result(
                risk, reasons, "error", f"Error executing command: {e}"
            )

    async def run_shell_command(
        self, command: str, force_approval: bool = False, tool: str = "Bash"
    ) -> Dict[str, Any]:
        """
        Securely execute a shell command with risk assessment and sandboxing.

        Issue #665: Refactored to under 50 lines using extracted helper methods.
        Permission v2 order: DENY > ASK > ALLOW rules, then risk-based assessment.

        Args:
            command: The shell command to execute
            force_approval: Force user approval regardless of risk level
            tool: Tool name for permission matching (default: "Bash")

        Returns:
            Dictionary containing execution results and security info
        """
        permission_action, rule_info = await self.check_permission_rules(command, tool)

        if permission_action == "deny":
            return self._build_permission_deny_result(command, rule_info)

        if permission_action == "allow":
            logger.info(f"Command auto-approved by permission rule: {command[:50]}...")
            risk, reasons = self.assess_command_risk(command)
            log_entry = self._build_auto_approved_log_entry(command, risk, reasons, rule_info)
            return await self._execute_command(command, risk, reasons, log_entry, rule_info)

        # Risk-based assessment fallback
        risk, reasons = self.assess_command_risk(command)
        log_entry = self._build_standard_log_entry(command, risk, reasons)

        if risk == CommandRisk.FORBIDDEN:
            return await self._handle_forbidden_command(command, risk, reasons, log_entry)

        denial_result = await self._handle_approval_flow(
            command, risk, reasons, log_entry, force_approval, permission_action
        )
        if denial_result:
            return denial_result

        return await self._execute_command(command, risk, reasons, log_entry)

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
