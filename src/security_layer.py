# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import datetime
import json
import os
from typing import Any, Dict, List, Optional

import yaml

from src.constants.network_constants import NetworkConstants

# Import the centralized ConfigManager
from src.unified_config_manager import config as global_config_manager


class SecurityLayer:
    def __init__(self):
        # Use centralized config manager instead of direct file loading
        self.security_config = global_config_manager.get("security_config", {})

        # Check for single-user mode (development/personal use)
        self.single_user_mode = os.getenv("AUTOBOT_SINGLE_USER_MODE", "true").lower() in ["true", "1", "yes"]

        # If single-user mode is enabled, disable all authentication
        if self.single_user_mode:
            self.enable_auth = False
            print("🔓 Single-user mode enabled - authentication disabled")
        else:
            self.enable_auth = self.security_config.get("enable_auth", False)

        self.audit_log_file = self.security_config.get(
            "audit_log_file", os.getenv("AUTOBOT_AUDIT_LOG_FILE", "data/audit.log")
        )
        self.roles = self.security_config.get("roles", {})
        self.allowed_users = self.security_config.get(
            "allowed_users", {}
        )  # For simple demo auth

        os.makedirs(os.path.dirname(self.audit_log_file), exist_ok=True)
        print(
            "SecurityLayer initialized. Authentication enabled: " f"{self.enable_auth}"
        )
        print(f"Audit log file: {self.audit_log_file}")

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
        if user_role.lower() in ["god", "superuser", "root"]:
            # Log the deprecated role usage for security audit
            self.audit_log(
                action="deprecated_role_usage",
                user=user_role,
                outcome="warning",
                details={
                    "deprecated_role": user_role,
                    "action_attempted": action_type,
                    "resource": resource,
                    "message": "God/superuser/root roles deprecated for security. "
                    "Downgrading to admin with granular permissions.",
                },
            )
            user_role = "admin"  # Downgrade to admin with proper permissions

        role_permissions = self.roles.get(user_role, {}).get("permissions", [])

        # SECURITY FIX: Removed "allow_all" bypass - use granular permissions only
        # All roles must have explicit permissions for each action type

        if action_type in role_permissions:
            return True

        # Check for wildcard permissions
        # (e.g., 'files.*' matches 'files.view', 'files.delete', etc.)
        for permission in role_permissions:
            if permission.endswith(".*"):
                permission_prefix = permission[:-1]  # Remove the '*'
                if action_type.startswith(permission_prefix):
                    return True

        # Check default role permissions for common roles
        default_permissions = self._get_default_role_permissions(user_role)
        if action_type in default_permissions:
            return True

        # More granular checks could be added here based on resource
        # e.g., if action_type is 'files.view' and resource contains 'sensitive'
        # then check for 'files.view_sensitive' permission

        print(
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
                # NOTE: Dangerous operations still require approval even for admin
            ],
            "user": [
                "files.view",
                "files.download",
                "allow_goal_submission",
                "allow_kb_read",
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
            ],
            "guest": [
                "files.view",
                "files.download",
                "files.upload",
                "files.create",
                "files.delete",
                "allow_goal_submission",
                "allow_kb_read",
            ],  # Development mode - permissive guest access
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
            print(f"Audit log: {action} by {user} - {outcome}")
        except Exception as e:
            print(
                "ERROR: Failed to write to audit log file "
                f"{self.audit_log_file}: {e}"
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
    security_enabled.audit_log("login", "testuser", "success", {"ip": "127.0.0.1"})
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
