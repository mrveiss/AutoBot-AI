# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Security Layer with Command Execution Controls
Integrates secure command execution with role-based permissions
"""

import asyncio
import datetime
import json
import os
from typing import Any, Dict, List, Optional

import logging

from src.secure_command_executor import (
    CommandRisk,
    SecureCommandExecutor,
    SecurityPolicy,
)

# Import the centralized ConfigManager
from src.config import config as global_config_manager

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for security checks (Issue #326)
DEPRECATED_PRIVILEGED_ROLES = {"god", "superuser", "root"}
HIGH_RISK_COMMAND_RISKS = {CommandRisk.HIGH, CommandRisk.MODERATE}
COMMAND_EXECUTION_ACTIONS = {"command_execution_attempt", "command_execution_complete"}


def _parse_audit_log_entry(line: str, user: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Parse a single audit log line and filter by user (Issue #315: extracted).

    Args:
        line: JSON line from audit log
        user: Optional user filter

    Returns:
        Parsed entry dict if valid command execution, None otherwise
    """
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None

    if "action" not in entry:
        return None
    if entry["action"] not in COMMAND_EXECUTION_ACTIONS:
        return None
    if user is not None and entry.get("user") != user:
        return None

    return entry


class EnhancedSecurityLayer:
    """
    Enhanced security layer that integrates command execution security
    with role-based access control and audit logging
    """

    def __init__(self):
        """Initialize security layer with RBAC, auditing, and command executor."""
        # Use centralized config manager
        self.security_config = global_config_manager.get("security_config", {})
        self.enable_auth = self.security_config.get("enable_auth", False)
        self.enable_command_security = self.security_config.get(
            "enable_command_security", True
        )
        self.audit_log_file = self.security_config.get(
            "audit_log_file", os.getenv("AUTOBOT_AUDIT_LOG_FILE", "data/audit.log")
        )
        self.roles = self.security_config.get("roles", {})
        self.allowed_users = self.security_config.get("allowed_users", {})

        # Command security settings
        self.command_approval_required = self.security_config.get(
            "command_approval_required", True
        )
        self.use_docker_sandbox = self.security_config.get("use_docker_sandbox", False)

        # Initialize secure command executor
        self.command_executor = SecureCommandExecutor(
            policy=self._create_security_policy(),
            require_approval_callback=self._command_approval_callback,
            use_docker_sandbox=self.use_docker_sandbox,
        )

        # Initialize enhanced sandbox executor if Docker is available
        self.sandbox_executor = None
        if self.use_docker_sandbox:
            try:
                from src.secure_sandbox_executor import secure_sandbox

                self.sandbox_executor = secure_sandbox
                logger.info("Enhanced Docker sandbox executor initialized")
            except Exception as e:
                logger.warning("Failed to initialize enhanced sandbox executor: %s", e)

        # Approval queue for async command approvals
        self.pending_approvals: Dict[str, asyncio.Event] = {}
        self.approval_results: Dict[str, bool] = {}

        os.makedirs(os.path.dirname(self.audit_log_file), exist_ok=True)
        logger.info("EnhancedSecurityLayer initialized")
        logger.debug("Authentication enabled: %s", self.enable_auth)
        logger.debug("Command security enabled: %s", self.enable_command_security)
        logger.debug("Docker sandbox: %s", self.use_docker_sandbox)
        logger.debug("Audit log file: %s", self.audit_log_file)

    def _create_security_policy(self) -> SecurityPolicy:
        """Create security policy from configuration"""
        policy = SecurityPolicy()

        # Load custom policies from config if available
        custom_policies = self.security_config.get("command_policies", {})

        if "safe_commands" in custom_policies:
            policy.safe_commands.update(custom_policies["safe_commands"])

        if "forbidden_commands" in custom_policies:
            policy.forbidden_commands.update(custom_policies["forbidden_commands"])

        if "allowed_paths" in custom_policies:
            from pathlib import Path

            policy.allowed_paths = [Path(p) for p in custom_policies["allowed_paths"]]

        return policy

    async def _command_approval_callback(self, approval_data: Dict[str, Any]) -> bool:
        """
        Callback for command approval requests
        This can be extended to integrate with UI or notification systems
        """
        command_id = f"cmd_{int(approval_data['timestamp'])}"

        # Log the approval request
        self.audit_log(
            action="command_approval_request",
            user="system",
            outcome="pending",
            details={
                "command": approval_data["command"],
                "risk": approval_data["risk"],
                "reasons": approval_data["reasons"],
                "command_id": command_id,
            },
        )

        # In a real implementation, this would:
        # 1. Send notification to UI/admin
        # 2. Wait for user response
        # 3. Return approval decision

        # For now, implement automatic approval based on risk level
        if approval_data["risk"] == CommandRisk.MODERATE.value:
            # Auto-approve moderate risk commands if configured
            if self.security_config.get("auto_approve_moderate", False):
                self.audit_log(
                    action="command_auto_approved",
                    user="system",
                    outcome="approved",
                    details={"command_id": command_id, "risk": "moderate"},
                )
                return True

        # Create approval event
        approval_event = asyncio.Event()
        self.pending_approvals[command_id] = approval_event

        # Wait for approval (with timeout)
        try:
            await asyncio.wait_for(
                approval_event.wait(), timeout=300
            )  # 5 minute timeout
            approved = self.approval_results.get(command_id, False)

            self.audit_log(
                action="command_approval_response",
                user="system",
                outcome="approved" if approved else "denied",
                details={"command_id": command_id},
            )

            return approved

        except asyncio.TimeoutError:
            self.audit_log(
                action="command_approval_timeout",
                user="system",
                outcome="denied",
                details={"command_id": command_id},
            )
            return False

        finally:
            # Cleanup
            self.pending_approvals.pop(command_id, None)
            self.approval_results.pop(command_id, None)

    def approve_command(self, command_id: str, approved: bool = True):
        """
        Approve or deny a pending command
        This would be called from UI or API endpoint
        """
        if command_id in self.pending_approvals:
            self.approval_results[command_id] = approved
            self.pending_approvals[command_id].set()

    def check_permission(
        self, user_role: str, action_type: str, resource: Optional[str] = None
    ) -> bool:
        """
        Enhanced permission checking that includes command execution permissions
        SECURITY FIX: Removed god mode bypass - all roles use granular RBAC
        """
        if not self.enable_auth:
            return True

        # SECURITY FIX: Deprecated god/superuser/root roles - use admin with proper permissions
        # ALL roles must go through RBAC, audit logging, and validation (O(1) lookup - Issue #326)
        if user_role.lower() in DEPRECATED_PRIVILEGED_ROLES:
            self.audit_log(
                action="deprecated_role_usage",
                user=user_role,
                outcome="warning",
                details={
                    "deprecated_role": user_role,
                    "action_attempted": action_type,
                    "resource": resource,
                    "message": (
                        "God/superuser/root roles deprecated. Update to admin role."
                    ),
                },
            )
            # Downgrade to admin role with proper permissions and audit logging
            user_role = "admin"

        # Special handling for command execution
        if action_type == "allow_shell_execute":
            # Check if role has shell execution permission
            role_permissions = self.roles.get(user_role, {}).get("permissions", [])

            # SECURITY FIX: Removed "allow_all" bypass - granular permissions only
            # All command execution must go through proper risk assessment

            if "allow_shell_execute" in role_permissions:
                # Even with permission, command security still applies
                return True

            # Check for restricted shell execution
            if "allow_shell_execute_safe" in role_permissions:
                # User can only execute safe commands
                return True

            return False

        # Regular permission checking
        role_permissions = self.roles.get(user_role, {}).get("permissions", [])

        # SECURITY FIX: Removed "allow_all" bypass - use granular permissions only
        # This ensures all actions go through proper permission validation

        if action_type in role_permissions:
            return True

        # Check for wildcard permissions
        for permission in role_permissions:
            if permission.endswith(".*"):
                permission_prefix = permission[:-1]
                if action_type.startswith(permission_prefix):
                    return True

        # Check default role permissions
        default_permissions = self._get_default_role_permissions(user_role)
        if action_type in default_permissions:
            return True

        logger.warning(
            f"Permission DENIED for role '{user_role}' to perform "
            f"action '{action_type}'"
        )
        return False

    def _create_permission_denied_result(
        self, command: str, user: str, user_role: str
    ) -> Dict[str, Any]:
        """
        Create a permission denied result for command execution.

        Issue #281: Extracted from execute_command to reduce function length
        and improve reusability.

        Args:
            command: The command that was attempted
            user: Username who attempted execution
            user_role: Role of the user

        Returns:
            Dict with error status and permission denied details
        """
        self.audit_log(
            action="command_execution_denied",
            user=user,
            outcome="denied",
            details={
                "command": command,
                "reason": "no_permission",
                "role": user_role,
            },
        )
        return {
            "stdout": "",
            "stderr": (
                "Permission denied: You do not have shell execution privileges"
            ),
            "return_code": 1,
            "status": "error",
            "security": {"blocked": True, "reason": "no_permission"},
        }

    def _should_force_approval(
        self, command: str, user_role: str
    ) -> bool:
        """
        Determine if command requires forced approval based on role and risk.

        Issue #281: Extracted from execute_command to reduce function length
        and improve readability of approval logic.

        Args:
            command: Command to check
            user_role: Role of user executing

        Returns:
            True if approval should be forced, False otherwise
        """
        role_permissions = self.roles.get(user_role, {}).get("permissions", [])
        if not role_permissions:
            # Fall back to default permissions if no configured role
            role_permissions = self._get_default_role_permissions(user_role)

        if "allow_all" in role_permissions:
            return False

        # Check if user has limited shell execution permissions
        risk, _ = self.command_executor.assess_command_risk(command)
        if (
            "allow_shell_execute_safe" in role_permissions
            and risk != CommandRisk.SAFE
        ):
            # User can only execute safe commands without approval
            return True
        elif "allow_shell_execute" in role_permissions and risk in HIGH_RISK_COMMAND_RISKS:
            # User has shell execute permission but high-risk commands need approval
            return True

        return False

    def _get_default_role_permissions(self, user_role: str) -> List[str]:
        """
        Get default permissions for common user roles
        SECURITY FIX: Removed god/superuser/root roles and granular admin permissions
        """
        default_role_permissions = {
            # SECURITY FIX: Admin has elevated permissions but NOT unrestricted access
            # Dangerous commands still require approval and validation for ALL users
            "admin": [
                "files.*",
                "allow_goal_submission",
                "allow_kb_read",
                "allow_kb_write",
                "allow_shell_execute",  # Can execute commands with proper validation
                "allow_shell_high_risk",  # Can execute high-risk with approval
                # NOTE: Dangerous commands ALWAYS require approval, even for admin
            ],
            "operator": [
                "files.*",
                "allow_goal_submission",
                "allow_kb_read",
                "allow_kb_write",
                "allow_shell_execute",  # Standard shell execution
                "allow_shell_moderate",  # Moderate risk commands with approval
            ],
            "developer": [
                "files.*",
                "allow_goal_submission",
                "allow_kb_read",
                "allow_kb_write",
                "allow_shell_execute_safe",  # Only safe commands
            ],
            "user": [
                "files.view",
                "files.download",
                "allow_goal_submission",
                "allow_kb_read",
            ],
            "readonly": ["files.view", "files.download", "allow_kb_read"],
            "guest": ["files.view"],
        }

        return default_role_permissions.get(user_role, [])

    async def execute_command(
        self, command: str, user: str, user_role: str
    ) -> Dict[str, Any]:
        """
        Execute a command with security checks and audit logging

        Args:
            command: Command to execute
            user: Username executing the command
            user_role: Role of the user

        Returns:
            Execution result with security information
        """
        # Issue #281: Use extracted helper for permission check
        if not self.check_permission(user_role, "allow_shell_execute"):
            return self._create_permission_denied_result(command, user, user_role)

        # Issue #281: Use extracted helper for approval logic
        force_approval = self._should_force_approval(command, user_role)

        # Log command attempt
        self.audit_log(
            action="command_execution_attempt",
            user=user,
            outcome="pending",
            details={
                "command": command,
                "role": user_role,
                "force_approval": force_approval,
            },
        )

        # Execute command with security controls
        if self.enable_command_security:
            result = await self.command_executor.run_shell_command(
                command, force_approval=force_approval
            )
        else:
            # Fallback to basic execution if security is disabled
            import asyncio

            process = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            result = {
                "stdout": stdout.decode().strip(),
                "stderr": stderr.decode().strip(),
                "return_code": process.returncode,
                "status": "success" if process.returncode == 0 else "error",
                "security": {"enabled": False},
            }

        # Log execution result
        self.audit_log(
            action="command_execution_complete",
            user=user,
            outcome=result["status"],
            details={
                "command": command,
                "return_code": result["return_code"],
                "security": result.get("security", {}),
            },
        )

        return result

    def audit_log(self, action: str, user: str, outcome: str, details: Dict[str, Any]):
        """Enhanced audit logging with command execution tracking"""
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "user": user,
            "action": action,
            "outcome": outcome,
            "details": details,
        }

        try:
            with open(self.audit_log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
            logger.debug("Audit log: %s by %s - %s", action, user, outcome)
        except Exception as e:
            logger.error("Failed to write to audit log: %s", e)

    def get_command_history(
        self, user: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get command execution history from audit log

        Args:
            user: Filter by specific user (optional)
            limit: Maximum number of entries to return

        Returns:
            List of command execution entries
        """
        command_history = []

        try:
            with open(self.audit_log_file, "r") as f:
                for line in f:
                    # Use helper for parsing and filtering (Issue #315: depth reduction)
                    entry = _parse_audit_log_entry(line, user)
                    if entry:
                        command_history.append(entry)
        except FileNotFoundError:
            return []

        # Return most recent entries
        return command_history[-limit:]

    def authenticate_user(self, username: str, password: str) -> Optional[str]:
        """Authenticate user and return their role"""
        if not self.enable_auth:
            return "admin"

        if username in self.allowed_users and self.allowed_users[username] == password:
            # Map users to roles (simplified for demo)
            user_roles = self.security_config.get("user_roles", {})
            return user_roles.get(username, "user")

        return None

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get list of commands pending approval"""
        pending = []
        for cmd_id in self.pending_approvals:
            pending.append(
                {
                    "command_id": cmd_id,
                    "timestamp": cmd_id.split("_")[1] if "_" in cmd_id else "unknown",
                }
            )
        return pending


# Test the enhanced security layer
if __name__ == "__main__":

    async def test_security():
        """Test security layer with various commands and user roles."""
        print("Testing Enhanced Security Layer")
        print("=" * 60)

        # Create enhanced security layer
        security = EnhancedSecurityLayer()

        # Test command risk assessment
        test_commands = [
            ("echo 'Hello World'", "admin"),
            ("rm -rf /tmp/test", "admin"),
            ("sudo apt update", "user"),
            ("ls -la", "developer"),
            ("cat /etc/passwd", "admin"),
        ]

        for cmd, role in test_commands:
            print(f"\nTesting: {cmd} (as {role})")
            result = await security.execute_command(cmd, f"{role}_user", role)
            print(f"Result: {result['status']}")
            if result.get("security"):
                print(f"Security: {result['security']}")
            if result["stderr"]:
                print(f"Error: {result['stderr']}")
            if result["stdout"]:
                print(f"Output: {result['stdout'][:100]}...")

        # Show command history
        print("\n" + "=" * 60)
        print("Command History:")
        history = security.get_command_history(limit=10)
        for entry in history:
            print(
                f"- {entry['timestamp']}: {entry['user']} - "
                f"{entry['action']} - {entry['outcome']}"
            )
            if "command" in entry.get("details", {}):
                print(f"  Command: {entry['details']['command']}")

    asyncio.run(test_security())
