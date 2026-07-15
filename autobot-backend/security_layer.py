# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Security validation and configuration enforcement layer.

Validates YAML-based security rules, manages authentication tokens, and
enforces platform-level access policies for all AutoBot services.

Also integrates command execution security with role-based permissions
and audit logging (command executor, approval workflow — folded in per #10666 B6).
"""

import asyncio
import datetime
import json
import os
from datetime import timezone
from typing import Any, Dict, List

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from config import get_config_manager
from secure_command_executor import CommandRisk, SecureCommandExecutor, SecurityPolicy

logger = get_logger(__name__)

# Audit log file path resolved from AUTOBOT_AUDIT_LOG_FILE env var at import time.
# Set AUTOBOT_AUDIT_LOG_FILE to override the default path.
_AUDIT_LOG_FILE_DEFAULT = "/opt/autobot/logs/audit.log"


def _resolve_audit_log_file() -> str:
    """Return audit log file path from AUTOBOT_AUDIT_LOG_FILE env var with logged fallback."""
    value = config.audit_log_file
    if not value:
        logger.warning(
            "AUTOBOT_AUDIT_LOG_FILE is not set or empty; falling back to %s",
            _AUDIT_LOG_FILE_DEFAULT,
        )
        return _AUDIT_LOG_FILE_DEFAULT
    return value


_AUDIT_LOG_FILE = _resolve_audit_log_file()

# Performance optimization: O(1) lookup for deprecated privileged roles (Issue #326)
DEPRECATED_PRIVILEGED_ROLES = {"god", "superuser", "root"}

# Performance optimization: O(1) lookup for security checks (Issue #326)
HIGH_RISK_COMMAND_RISKS = {CommandRisk.HIGH, CommandRisk.MODERATE}
COMMAND_EXECUTION_ACTIONS = {"command_execution_attempt", "command_execution_complete"}


def _parse_audit_log_entry(line: str, user: str | None = None) -> Dict[str, Any] | None:
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


class SecurityLayer:
    """Security layer with RBAC, audit logging, and command execution controls.

    Combines role-based access control, authentication, and secure command execution
    in a single cohesive class. Authentication is always derived from security_config;
    there is no single-user bypass (#10713, #10636).
    """

    def __init__(self):
        """Initialize security layer with RBAC, auditing, and command executor."""
        # Use centralized config manager
        self.security_config = get_config_manager().get("security_config", {})

        # Issue #745: Default to True for production security.
        # Authentication is always enabled unless explicitly disabled in security_config.
        # single_user auth-disable branch removed per #10713 (originally retired by #10636,
        # accidentally revived by #10666, now permanently retired).
        self.enable_auth = self.security_config.get("enable_auth", True)
        logger.info("Authentication enabled: %s", self.enable_auth)

        self.audit_log_file = self.security_config.get("audit_log_file") or _AUDIT_LOG_FILE
        self.roles = self.security_config.get("roles", {})
        self.allowed_users = self.security_config.get("allowed_users", {})

        # Command security settings (folded from enhanced layer per #10666 B6)
        self.enable_command_security = self.security_config.get("enable_command_security", True)
        self.command_approval_required = self.security_config.get("command_approval_required", True)
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
                from secure_sandbox_executor import secure_sandbox

                self.sandbox_executor = secure_sandbox
                logger.info("Docker sandbox executor initialized")
            except Exception as e:
                logger.warning("Failed to initialize sandbox executor: %s", e)

        # Approval queue for async command approvals
        self.pending_approvals: Dict[str, asyncio.Event] = {}
        self.approval_results: Dict[str, bool] = {}

        if self.audit_log_file:
            log_dir = os.path.dirname(self.audit_log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
        logger.info("SecurityLayer initialized. Authentication enabled: %s", self.enable_auth)
        logger.debug("Command security enabled: %s", self.enable_command_security)
        logger.debug("Docker sandbox: %s", self.use_docker_sandbox)
        logger.debug("Audit log file: %s", self.audit_log_file)

    # =========================================================================
    # Security Policy
    # =========================================================================

    def _create_security_policy(self) -> SecurityPolicy:
        """Create security policy from configuration."""
        policy = SecurityPolicy()

        # Load custom policies from config if available
        custom_policies = self.security_config.get("command_policies", {})

        # #7161: SAFE_COMMANDS / FORBIDDEN_COMMANDS are frozensets after the
        # #765 centralized-command-patterns refactor. Rebuild as mutable sets
        # merging defaults + customs to avoid AttributeError on .update() calls.
        if "safe_commands" in custom_policies:
            policy.safe_commands = set(policy.safe_commands) | set(custom_policies["safe_commands"])

        if "forbidden_commands" in custom_policies:
            policy.forbidden_commands = set(policy.forbidden_commands) | set(custom_policies["forbidden_commands"])

        if "allowed_paths" in custom_policies:
            from pathlib import Path

            policy.allowed_paths = [Path(p) for p in custom_policies["allowed_paths"]]

        return policy

    # =========================================================================
    # Approval Workflow
    # =========================================================================

    def _log_approval_request(self, command_id: str, approval_data: Dict[str, Any]) -> None:
        """Log command approval request to audit log. Issue #620."""
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

    def _check_auto_approve_moderate(self, command_id: str, approval_data: Dict[str, Any]) -> bool | None:
        """Check if moderate risk command should be auto-approved. Issue #620.

        Returns:
            True if auto-approved, None if approval still required.
        """
        if approval_data["risk"] != CommandRisk.MODERATE.value:
            return None
        if not self.security_config.get("auto_approve_moderate", False):
            return None
        self.audit_log(
            action="command_auto_approved",
            user="system",
            outcome="approved",
            details={"command_id": command_id, "risk": "moderate"},
        )
        return True

    async def _wait_for_approval_response(self, command_id: str) -> bool:
        """Wait for approval response with timeout and log result. Issue #620.

        Returns:
            True if approved, False if denied or timeout.
        """
        approval_event = asyncio.Event()
        self.pending_approvals[command_id] = approval_event

        try:
            await asyncio.wait_for(approval_event.wait(), timeout=300)
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
            self.pending_approvals.pop(command_id, None)
            self.approval_results.pop(command_id, None)

    async def _command_approval_callback(self, approval_data: Dict[str, Any]) -> bool:
        """Callback for command approval requests.

        Can be extended to integrate with UI or notification systems.
        """
        command_id = f"cmd_{int(approval_data['timestamp'])}"
        self._log_approval_request(command_id, approval_data)

        # Check for auto-approval of moderate risk commands
        auto_result = self._check_auto_approve_moderate(command_id, approval_data)
        if auto_result is not None:
            return auto_result

        # Wait for manual approval
        return await self._wait_for_approval_response(command_id)

    def approve_command(self, command_id: str, approved: bool = True) -> None:
        """Approve or deny a pending command.

        Called from UI or API endpoint.
        """
        if command_id in self.pending_approvals:
            self.approval_results[command_id] = approved
            self.pending_approvals[command_id].set()

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get list of commands pending approval."""
        pending = []
        for cmd_id in self.pending_approvals:
            pending.append(
                {
                    "command_id": cmd_id,
                    "timestamp": cmd_id.split("_")[1] if "_" in cmd_id else "unknown",
                }
            )
        return pending

    # =========================================================================
    # Role / Permission Checks
    # =========================================================================

    def _handle_deprecated_role(self, user_role: str, action_type: str, resource: str | None) -> str:
        """Handle deprecated privileged roles by logging and downgrading to admin.

        Deprecated roles (god, superuser, root) are security vulnerabilities and
        are downgraded to admin with proper RBAC permissions. Issue #620.

        Args:
            user_role: The role to check for deprecation.
            action_type: The action being attempted.
            resource: The resource being accessed.

        Returns:
            The effective role to use (admin if deprecated, original otherwise).
        """
        if user_role.lower() not in DEPRECATED_PRIVILEGED_ROLES:
            return user_role

        self.audit_log(
            action="deprecated_role_usage",
            user=user_role,
            outcome="warning",
            details={
                "deprecated_role": user_role,
                "action_attempted": action_type,
                "resource": resource,
                "message": (
                    "God/superuser/root roles deprecated for security. "
                    "Downgrading to admin with granular permissions."
                ),
            },
        )
        return "admin"

    def _check_shell_execute_permission(self, role_permissions: List[str]) -> bool:
        """Check if role has shell execution permission. Issue #620.

        Args:
            role_permissions: List of permissions for the role

        Returns:
            True if shell execution is allowed
        """
        if "allow_shell_execute" in role_permissions:
            return True
        if "allow_shell_execute_safe" in role_permissions:
            return True
        return False

    def _check_wildcard_permissions(self, action_type: str, permissions: List[str]) -> bool:
        """Check if action matches any wildcard permissions in the list.

        Wildcard permissions end with '.*' and match any action with the
        same prefix. Issue #620.

        Args:
            action_type: The action to check.
            permissions: List of permissions to check against.

        Returns:
            True if action matches a wildcard permission, False otherwise.
        """
        for permission in permissions:
            if permission.endswith(".*"):
                permission_prefix = permission[:-1]  # Remove the '*'
                if action_type.startswith(permission_prefix):
                    return True
        return False

    def _check_permission_match(self, action_type: str, permissions: List[str]) -> bool:
        """Check if action matches permissions list (direct or wildcard).

        First checks for exact match, then checks wildcard patterns. Issue #620.

        Args:
            action_type: The action to check.
            permissions: List of permissions to check against.

        Returns:
            True if action matches any permission, False otherwise.
        """
        if action_type in permissions:
            return True
        return self._check_wildcard_permissions(action_type, permissions)

    def check_permission(self, user_role: str, action_type: str, resource: str | None = None) -> bool:
        """Check if a given role has permission for a specific action.

        SECURITY FIX: Removed god mode bypass — all roles use granular RBAC.

        Args:
            user_role: The role of the user performing the action.
            action_type: The type of action being performed.
            resource: The specific resource being accessed (optional).

        Returns:
            True if permission is granted, False otherwise.
        """
        if not self.enable_auth:
            return True

        # SECURITY: Removed god mode — all access must go through proper RBAC
        user_role = self._handle_deprecated_role(user_role, action_type, resource)

        role_permissions = self.roles.get(user_role, {}).get("permissions", [])

        # #7161: combine configured + default permissions so shell_execute special-case
        # respects defaults too (roles like 'admin' that only have allow_shell_execute
        # in defaults were previously denied shell access).
        default_permissions = self._get_default_role_permissions(user_role)
        all_permissions = list(role_permissions) + list(default_permissions)

        # Special handling for command execution
        if action_type == "allow_shell_execute":
            return self._check_shell_execute_permission(all_permissions)

        # Direct and wildcard permission check (configured permissions first)
        if self._check_permission_match(action_type, role_permissions):
            return True

        # Check default role permissions
        if self._check_permission_match(action_type, default_permissions):
            return True

        logger.warning(
            "Permission DENIED for role '%s' to perform action '%s' on resource '%s'.",
            user_role,
            action_type,
            resource,
        )
        return False

    def _get_default_role_permissions(self, user_role: str) -> List[str]:
        """Get default permissions for common user roles.

        SECURITY FIX: Removed god/superuser/root roles and granular admin permissions.

        Args:
            user_role: The user role to get default permissions for

        Returns:
            List of default permissions for the role
        """
        default_role_permissions = {
            # SECURITY: Admin has elevated permissions but NOT unrestricted access
            # Dangerous commands ALWAYS require approval, even for admin
            "admin": [
                "files.*",
                "allow_goal_submission",
                "allow_kb_read",
                "allow_kb_write",
                "allow_shell_execute",
                "allow_shell_high_risk",
                "allow_voice_speak",
                "allow_voice_listen",
            ],
            "operator": [
                "files.*",
                "allow_goal_submission",
                "allow_kb_read",
                "allow_kb_write",
                "allow_shell_execute",
                "allow_shell_moderate",
            ],
            "developer": [
                "files.*",
                "allow_goal_submission",
                "allow_kb_read",
                "allow_kb_write",
                "allow_shell_execute_safe",
            ],
            "user": [
                "files.view",
                "files.download",
                "allow_goal_submission",
                "allow_kb_read",
                "allow_voice_speak",
                "allow_voice_listen",
            ],
            "readonly": ["files.view", "files.download"],
            "editor": [
                "files.view",
                "files.download",
                "files.upload",
                "files.create",
                "allow_goal_submission",
                "allow_kb_read",
                "allow_kb_write",
                "allow_voice_speak",
                "allow_voice_listen",
            ],
            # Issue #744: Guest role REMOVED — security vulnerability.
            # Unauthenticated requests must be rejected, not assigned permissions.
        }

        return default_role_permissions.get(user_role, [])

    # =========================================================================
    # Command Execution
    # =========================================================================

    def _create_permission_denied_result(self, command: str, user: str, user_role: str) -> Dict[str, Any]:
        """Build a permission denied result for command execution.

        Issue #281: Extracted from execute_command.
        """
        self.audit_log(
            action="command_execution_denied",
            user=user,
            outcome="denied",
            details={"command": command, "reason": "no_permission", "role": user_role},
        )
        return {
            "stdout": "",
            "stderr": "Permission denied: You do not have shell execution privileges",
            "return_code": 1,
            "status": "error",
            "security": {"blocked": True, "reason": "no_permission"},
        }

    def _should_force_approval(self, command: str, user_role: str) -> bool:
        """Determine if command requires forced approval based on role and risk.

        Issue #281: Extracted from execute_command.
        """
        role_permissions = self.roles.get(user_role, {}).get("permissions", [])
        if not role_permissions:
            role_permissions = self._get_default_role_permissions(user_role)

        if "allow_all" in role_permissions:
            return False

        risk, _ = self.command_executor.assess_command_risk(command)
        if "allow_shell_execute_safe" in role_permissions and risk != CommandRisk.SAFE:
            return True
        if "allow_shell_execute" in role_permissions and risk in HIGH_RISK_COMMAND_RISKS:
            return True

        return False

    def _log_command_attempt(self, command: str, user: str, user_role: str, force_approval: bool) -> None:
        """Log command execution attempt to audit log. Issue #620."""
        self.audit_log(
            action="command_execution_attempt",
            user=user,
            outcome="pending",
            details={"command": command, "role": user_role, "force_approval": force_approval},
        )

    async def _execute_basic_command(self, command: str) -> Dict[str, Any]:
        """Execute command without security controls (fallback mode). Issue #620."""
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return {
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
            "return_code": process.returncode,
            "status": "success" if process.returncode == 0 else "error",
            "security": {"enabled": False},
        }

    def _log_command_complete(self, command: str, user: str, result: Dict[str, Any]) -> None:
        """Log command execution completion to audit log. Issue #620."""
        self.audit_log(
            action="command_execution_complete",
            user=user,
            outcome=result["status"],
            details={"command": command, "return_code": result["return_code"], "security": result.get("security", {})},
        )

    async def execute_command(self, command: str, user: str, user_role: str) -> Dict[str, Any]:
        """Execute a command with security checks and audit logging.

        Args:
            command: Command to execute
            user: Username executing the command
            user_role: Role of the user

        Returns:
            Execution result with security information
        """
        if not self.check_permission(user_role, "allow_shell_execute"):
            return self._create_permission_denied_result(command, user, user_role)

        force_approval = self._should_force_approval(command, user_role)
        self._log_command_attempt(command, user, user_role, force_approval)

        if self.enable_command_security:
            result = await self.command_executor.run_shell_command(command, force_approval=force_approval)
        else:
            result = await self._execute_basic_command(command)

        self._log_command_complete(command, user, result)
        return result

    # =========================================================================
    # Audit Log
    # =========================================================================

    def audit_log(self, action: str, user: str, outcome: str, details: Dict[str, Any]) -> None:
        """Log an action to a tamper-resistant audit log file (append-only)."""
        log_entry = {
            "timestamp": datetime.datetime.now(tz=timezone.utc).isoformat(),
            "user": user,
            "action": action,
            "outcome": outcome,
            "details": details,
        }

        try:
            with open(self.audit_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
            logger.debug("Audit log: %s by %s - %s", action, user, outcome)
        except Exception as e:
            logger.error("Failed to write to audit log file %s: %s", self.audit_log_file, e)

    def get_command_history(self, user: str | None = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get command execution history from audit log.

        Args:
            user: Filter by specific user (optional)
            limit: Maximum number of entries to return

        Returns:
            List of command execution entries
        """
        command_history = []

        try:
            with open(self.audit_log_file, "r", encoding="utf-8") as f:
                for line in f:
                    entry = _parse_audit_log_entry(line, user)
                    if entry:
                        command_history.append(entry)
        except FileNotFoundError:
            return []

        # Return most recent entries
        return command_history[-limit:]

    # =========================================================================
    # Authentication
    # =========================================================================

    def authenticate_user(self, username: str, password: str) -> str | None:
        """Authenticate user and return their role.

        For demo purposes, uses a simple dictionary lookup.
        In production, use proper password hashing (e.g., bcrypt).
        """
        if not self.enable_auth:
            return "admin"

        if username in self.allowed_users and self.allowed_users[username] == password:
            user_roles = self.security_config.get("user_roles", {})
            role = user_roles.get(username)
            if role:
                return role
            return "admin" if username == "admin" else "user"

        return None


# Test entry point
if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async def test_security():
        """Test security layer with various commands and user roles."""
        logger.info("Testing SecurityLayer")
        logger.info("%s", "=" * 60)

        security = SecurityLayer()

        test_commands = [
            ("echo 'Hello World'", "admin"),
            ("rm -rf /tmp/test", "admin"),
            ("ls -la", "developer"),
        ]

        for cmd, role in test_commands:
            logger.info("\nTesting: %s (as %s)", cmd, role)
            result = await security.execute_command(cmd, f"{role}_user", role)
            logger.info("Result: %s", result["status"])

    run_or_schedule(test_security())
