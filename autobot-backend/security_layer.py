# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

from backend.constants.network_constants import NetworkConstants

# Import the centralized ConfigManager
from config import config as global_config_manager

# Performance optimization: O(1) lookup for boolean string values (Issue #326)
BOOLEAN_TRUE_VALUES = {"true", "1", "yes"}

# Performance optimization: O(1) lookup for deprecated privileged roles (Issue #326)
DEPRECATED_PRIVILEGED_ROLES = {"god", "superuser", "root"}


class SecurityLayer:
    def __init__(self):
        """Initialize security layer with config, role permissions, and audit logging."""
        # Use centralized config manager instead of direct file loading
        self.security_config = global_config_manager.get("security_config", {})

        # Check for single-user mode (development/personal use)
        self.single_user_mode = (
            os.getenv("AUTOBOT_SINGLE_USER_MODE", "true").lower() in BOOLEAN_TRUE_VALUES
        )

        # If single-user mode is enabled, disable all authentication
        # Issue #745: Added security warning for production awareness
        if self.single_user_mode:
            self.enable_auth = False
            logger.warning(
                "SECURITY: Single-user mode enabled - authentication disabled. "
                "Set AUTOBOT_SINGLE_USER_MODE=false for production deployments."
            )
        else:
            # Issue #745: Default to True for production security
            # Authentication should be enabled unless explicitly disabled
            self.enable_auth = self.security_config.get("enable_auth", True)
            logger.info("Multi-user mode - authentication enabled by default")

        self.audit_log_file = self.security_config.get(
            "audit_log_file", os.getenv("AUTOBOT_AUDIT_LOG_FILE", "data/audit.log")
        )
        self.roles = self.security_config.get("roles", {})
        self.allowed_users = self.security_config.get(
            "allowed_users", {}
        )  # For simple demo auth

        os.makedirs(os.path.dirname(self.audit_log_file), exist_ok=True)
        logger.info(
            f"SecurityLayer initialized. Authentication enabled: {self.enable_auth}"
        )
        logger.debug("Audit log file: %s", self.audit_log_file)

    def _handle_deprecated_role(
        self, user_role: str, action_type: str, resource: Optional[str]
    ) -> str:
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

    def _check_wildcard_permissions(
        self, action_type: str, permissions: List[str]
    ) -> bool:
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

    def check_permission(
        self, user_role: str, action_type: str, resource: Optional[str] = None
    ) -> bool:
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
            f"Permission DENIED for role '{user_role}' to perform action "
            f"'{action_type}' on resource '{resource}'."
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
            "timestamp": datetime.datetime.now().isoformat(),
            "user": user,
            "action": action,
            "outcome": outcome,
            "details": details,
        }

        # For tamper-resistance, one could hash the previous log entry
        # and include it here. Or sign the log entries.
        # For this demo, simple append-only.

        try:
            with open(self.audit_log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
            logger.debug("Audit log: %s by %s - %s", action, user, outcome)
        except Exception as e:
            logger.error(
                f"Failed to write to audit log file {self.audit_log_file}: {e}"
            )

    # Basic user authentication (for demo purposes)
    def authenticate_user(self, username, password) -> Optional[str]:
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
        print("config/config.yaml not found. Copying from template for testing.")
        os.makedirs("config", exist_ok=True)
        with open("config/config.yaml.template", "r") as f_template:
            with open("config/config.yaml", "w") as f_config:
                f_config.write(f_template.read())

    # Test with authentication disabled (default)
    print("\n--- Testing with Authentication DISABLED ---")
    security = SecurityLayer()
    print(
        "Can 'user' execute shell command? "
        f"{security.check_permission('user', 'allow_shell_execute')}"
    )
    security.audit_log(
        "test_action", "test_user", "success", {"info": "demo disabled auth"}
    )

    # Temporarily enable auth in config for testing
    with open("config/config.yaml", "r") as f:
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
    with open("config/config.yaml", "w") as f:
        yaml.safe_dump(cfg, f, indent=2)

    print("\n--- Testing with Authentication ENABLED ---")
    security_enabled = SecurityLayer()

    # Test authentication
    print(
        "Authenticate 'testuser': "
        f"{security_enabled.authenticate_user('testuser', 'password123')}"
    )
    print(
        "Authenticate 'baduser': "
        f"{security_enabled.authenticate_user('baduser', 'wrongpass')}"
    )

    # Test permissions
    print(
        "Can 'admin' execute shell command? "
        f"{security_enabled.check_permission('admin', 'allow_shell_execute')}"
    )
    print(
        "Can 'testuser_role' execute shell command? "
        f"{security_enabled.check_permission('testuser_role', 'allow_shell_execute')}"
    )
    print(
        "Can 'testuser_role' submit goal? "
        f"{security_enabled.check_permission('testuser_role', 'allow_goal_submission')}"
    )

    # Test audit logging
    security_enabled.audit_log(
        "login", "testuser", "success", {"ip": NetworkConstants.LOCALHOST_IP}
    )
    security_enabled.audit_log(
        "execute_command", "testuser", "denied", {"command": "rm -rf /"}
    )
    security_enabled.audit_log(
        "execute_command", "admin", "success", {"command": "ls -l"}
    )

    # Clean up config for next run
    with open("config/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    cfg["security_config"]["enable_auth"] = False
    with open("config/config.yaml", "w") as f:
        yaml.safe_dump(cfg, f, indent=2)
