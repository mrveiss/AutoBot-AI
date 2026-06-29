# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Security validation and configuration enforcement layer.

Validates YAML-based security rules, manages authentication tokens, and
enforces platform-level access policies for all AutoBot services.
"""

import datetime
import json
import os
from datetime import timezone
from typing import Any, Dict, List

import yaml

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from config import get_config_manager
from constants.network_constants import NetworkConstants

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


class SecurityLayer:
    def __init__(self):
        """Initialize security layer with config, role permissions, and audit logging."""
        # Use centralized config manager instead of direct file loading
        self.security_config = get_config_manager().get("security_config", {})

        # Issue #745: Default to True for production security.
        # Authentication is enabled unless explicitly disabled in security_config.
        self.enable_auth = self.security_config.get("enable_auth", True)
        logger.info("Authentication enabled by default")

        self.audit_log_file = self.security_config.get("audit_log_file") or _AUDIT_LOG_FILE
        self.roles = self.security_config.get("roles", {})
        self.allowed_users = self.security_config.get("allowed_users", {})  # For simple demo auth

        if self.audit_log_file:
            log_dir = os.path.dirname(self.audit_log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
        logger.info(f"SecurityLayer initialized. Authentication enabled: {self.enable_auth}")
        logger.debug("Audit log file: %s", self.audit_log_file)

    def _handle_deprecated_role(self, user_role: str, action_type: str, resource: str | None) -> str:
        """
        Handle deprecated privileged roles by logging and downgrading to admin.

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

    def _check_wildcard_permissions(self, action_type: str, permissions: List[str]) -> bool:
        """
        Check if action matches any wildcard permissions in the list.

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
        """
        Check if action matches permissions list (direct or wildcard).

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
        """
        Checks if a given role has permission for a specific action.

        Args:
            user_role (str): The role of the user performing the action.
            action_type (str): The type of action being performed
                (e.g., 'files.view', 'files.delete', 'allow_shell_execute').
            resource (str, optional): The specific resource being accessed
                (e.g., 'file_operation:delete').

        Returns:
            bool: True if permission is granted, False otherwise.
        """
        if not self.enable_auth:
            return True  # If authentication is disabled, all actions are allowed

        # SECURITY: Removed god mode - all access must go through proper RBAC
        # Former god/superuser roles now use admin permissions with audit logging
        user_role = self._handle_deprecated_role(user_role, action_type, resource)

        role_permissions = self.roles.get(user_role, {}).get("permissions", [])

        # SECURITY FIX: Removed "allow_all" bypass - use granular permissions only
        # All roles must have explicit permissions for each action type
        if self._check_permission_match(action_type, role_permissions):
            return True

        # Check default role permissions for common roles
        # Issue #745: Apply wildcard matching to default permissions too
        default_permissions = self._get_default_role_permissions(user_role)
        if self._check_permission_match(action_type, default_permissions):
            return True

        logger.warning(
            f"Permission DENIED for role '{user_role}' to perform action " f"'{action_type}' on resource '{resource}'."
        )
        return False

    def _get_default_role_permissions(self, user_role: str) -> List[str]:
        """
        Get default permissions for common user roles when not explicitly configured.

        Args:
            user_role: The user role to get default permissions for

        Returns:
            List of default permissions for the role
        """
        default_role_permissions = {
            # SECURITY: Admin has elevated permissions but NOT unrestricted access
            # Removed "allow_all" - admin must go through validation like everyone else
            "admin": [
                "files.*",
                "allow_goal_submission",
                "allow_kb_read",
                "allow_kb_write",
                "allow_shell_execute",
                "allow_voice_speak",
                "allow_voice_listen",
                # NOTE: Dangerous operations still require approval even for admin
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
            # Issue #744: Guest role REMOVED - security vulnerability
            # Unauthenticated requests must be rejected, not assigned permissions
        }

        return default_role_permissions.get(user_role, [])

    def audit_log(self, action: str, user: str, outcome: str, details: Dict[str, Any]):
        """
        Logs an action to a tamper-resistant audit log file.
        Currently append-only. For true tamper-resistance,
        hashing/encryption would be added.
        """
        log_entry = {
            "timestamp": datetime.datetime.now(tz=timezone.utc).isoformat(),
            "user": user,
            "action": action,
            "outcome": outcome,
            "details": details,
        }

        # For tamper-resistance, one could hash the previous log entry
        # and include it here. Or sign the log entries.
        # For this demo, simple append-only.

        try:
            with open(self.audit_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
            logger.debug("Audit log: %s by %s - %s", action, user, outcome)
        except Exception as e:
            logger.error(f"Failed to write to audit log file {self.audit_log_file}: {e}")

    # Basic user authentication (for demo purposes)
    def authenticate_user(self, username, password) -> str | None:
        """
        Authenticates a user and returns their role if successful.
        For demo purposes, uses a simple dictionary lookup.
        In production, use proper password hashing (e.g., bcrypt).
        """
        if not self.enable_auth:
            return "admin"  # Default to admin role if auth is disabled

        if username in self.allowed_users and self.allowed_users[username] == password:
            # In a real system, roles would be associated with users
            # in a more robust way. For this demo, we'll assume 'admin' user
            # gets 'admin' role, others 'user'
            if username == "admin":
                return "admin"
            else:
                return "user"  # Or fetch from a user database
        return None  # Authentication failed


# Example Usage (for testing)
if __name__ == "__main__":
    # Ensure config.yaml exists for testing
    if not os.path.exists("config/config.yaml"):
        logger.info("config/config.yaml not found. Copying from template for testing.")
        os.makedirs("config", exist_ok=True)
        with open("config/config.yaml.template", "r", encoding="utf-8") as f_template:
            with open("config/config.yaml", "w", encoding="utf-8") as f_config:
                f_config.write(f_template.read())

    # Test with authentication disabled (default)
    logger.info("\n--- Testing with Authentication DISABLED ---")
    security = SecurityLayer()
    logger.info(
        "Can 'user' execute shell command? %s",
        security.check_permission("user", "allow_shell_execute"),
    )
    security.audit_log("test_action", "test_user", "success", {"info": "demo disabled auth"})

    # Temporarily enable auth in config for testing
    with open("config/config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["security_config"]["enable_auth"] = True
    cfg["security_config"]["allowed_users"] = {
        "testuser": "password123",
        "admin": "adminpass",
    }
    cfg["security_config"]["roles"] = {
        "admin": {"permissions": ["allow_all"]},
        "testuser_role": {"permissions": ["allow_goal_submission", "allow_kb_read"]},
    }
    with open("config/config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, indent=2)

    logger.info("\n--- Testing with Authentication ENABLED ---")
    security_enabled = SecurityLayer()

    # Test authentication
    logger.info("Authenticate 'testuser': %s", security_enabled.authenticate_user("testuser", "password123"))
    logger.info("Authenticate 'baduser': %s", security_enabled.authenticate_user("baduser", "wrongpass"))

    # Test permissions
    logger.info(
        "Can 'admin' execute shell command? %s",
        security_enabled.check_permission("admin", "allow_shell_execute"),
    )
    logger.info(
        "Can 'testuser_role' execute shell command? %s",
        security_enabled.check_permission("testuser_role", "allow_shell_execute"),
    )
    logger.info(
        "Can 'testuser_role' submit goal? %s",
        security_enabled.check_permission("testuser_role", "allow_goal_submission"),
    )

    # Test audit logging
    security_enabled.audit_log("login", "testuser", "success", {"ip": NetworkConstants.LOCALHOST_IP})
    security_enabled.audit_log("execute_command", "testuser", "denied", {"command": "rm -rf /"})
    security_enabled.audit_log("execute_command", "admin", "success", {"command": "ls -l"})

    # Clean up config for next run
    with open("config/config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["security_config"]["enable_auth"] = False
    with open("config/config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, indent=2)
