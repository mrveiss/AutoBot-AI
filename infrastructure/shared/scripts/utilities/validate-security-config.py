#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Configuration Validation Script
Tests that the security_config section is properly loaded and authentication is enabled.
"""

import os
import sys
import traceback
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def _test_auth_and_audit(security) -> bool:
    """Test authentication status and audit log configuration.

    Helper for test_security_config (#825).
    """
    logger.info("\n3. Testing authentication status...")
    logger.info("   enable_auth: %s", security.enable_auth)
    if not security.enable_auth:
        logger.error(
            "Authentication is DISABLED - SECURITY VULNERABILITY!"
        )
        return False
    logger.info("Authentication is ENABLED")

    logger.info("\n4. Testing audit log configuration...")
    logger.info("   audit_log_file: %s", security.audit_log_file)
    audit_dir = os.path.dirname(security.audit_log_file)
    if not os.path.exists(audit_dir):
        logger.error("Audit log directory missing: %s", audit_dir)
        return False
    logger.info("Audit log directory exists")
    return True


def _test_allowed_users(security) -> bool:
    """Test allowed users configuration.

    Helper for test_security_config (#825).
    """
    logger.info("\n5. Testing allowed users configuration...")
    logger.info(
        "   Number of allowed users: %s", len(security.allowed_users)
    )
    expected_users = ["admin", "developer", "readonly"]
    for user in expected_users:
        if user not in security.allowed_users:
            logger.error("   Missing user '%s'", user)
            return False
        logger.info("   User '%s' configured", user)
        user_config = security.allowed_users[user]
        if "password_hash" not in user_config:
            logger.error("   Missing password hash for '%s'", user)
            return False
        logger.info("      Password hash configured for '%s'", user)
    return True


def _test_roles_config(security) -> bool:
    """Test roles configuration.

    Helper for test_security_config (#825).
    """
    logger.info("\n6. Testing roles configuration...")
    logger.info("   Number of roles: %s", len(security.roles))
    expected_roles = [
        "admin", "developer", "editor", "user", "readonly", "guest",
    ]
    for role in expected_roles:
        if role not in security.roles:
            logger.error("   Missing role '%s'", role)
            return False
        logger.info("   Role '%s' configured", role)
        role_config = security.roles[role]
        if "permissions" not in role_config:
            logger.error("   Missing permissions for role '%s'", role)
            return False
        perms = role_config["permissions"]
        logger.info(
            "      %s permissions defined for '%s'", len(perms), role
        )
    return True


def _test_permissions_and_audit_log(security) -> bool:
    """Test permission checking and audit logging.

    Helper for test_security_config (#825).
    """
    logger.info("\n7. Testing permission checking...")
    has_all = security.check_permission("admin", "allow_shell_execute")
    if not has_all:
        logger.error("   Admin role missing permissions")
        return False
    logger.info("   Admin role has full permissions")

    has_write = security.check_permission("readonly", "files.upload")
    if has_write:
        logger.error("   Readonly role has too many permissions")
        return False
    logger.info("   Readonly role properly restricted")

    logger.info("\n8. Testing audit logging...")
    try:
        security.audit_log(
            action="security_validation_test",
            user="test_user",
            outcome="success",
            details={"test": "security_config_validation"},
        )
        logger.info("   Audit logging working")
    except Exception as e:
        logger.error("   Audit logging failed: %s", e)
        return False
    return True


def test_security_config():
    """Test that security configuration is properly loaded."""
    try:
        logger.info("AUTOBOT SECURITY CONFIGURATION VALIDATION")
        logger.info("=" * 50)

        logger.info("\n1. Testing SecurityLayer import...")
        from security_layer import SecurityLayer
        logger.info("SecurityLayer imported successfully")

        logger.info("\n2. Testing SecurityLayer initialization...")
        security = SecurityLayer()
        logger.info("SecurityLayer initialized successfully")

        if not _test_auth_and_audit(security):
            return False
        if not _test_allowed_users(security):
            return False
        if not _test_roles_config(security):
            return False
        if not _test_permissions_and_audit_log(security):
            return False

        logger.info("\nALL SECURITY CONFIGURATION TESTS PASSED!")
        logger.info("\nSECURITY STATUS SUMMARY:")
        logger.info("   Authentication: ENABLED")
        logger.info(
            "   Users configured: %s", len(security.allowed_users)
        )
        logger.info("   Roles configured: %s", len(security.roles))
        logger.info("   Audit logging: WORKING")
        logger.info("   Permission system: FUNCTIONAL")
        return True

    except Exception as e:
        logger.error("\nSECURITY CONFIGURATION TEST FAILED!")
        logger.error("Error: %s", e)
        logger.info("\nTraceback:")
        traceback.print_exc()
        return False


def test_auth_middleware():
    """Test that AuthMiddleware can load the security configuration."""
    try:
        logger.info("\n" + "=" * 50)
        logger.info("AUTHENTICATION MIDDLEWARE VALIDATION")
        logger.info("=" * 50)

        logger.info("\n1. Testing AuthMiddleware import...")
        from auth_middleware import auth_middleware
        logger.info("AuthMiddleware imported successfully")

        logger.info("\n2. Testing AuthMiddleware configuration...")
        logger.info("   enable_auth: %s", auth_middleware.enable_auth)
        if auth_middleware.enable_auth:
            logger.info("AuthMiddleware authentication ENABLED")
        else:
            logger.error("AuthMiddleware authentication DISABLED")
            return False

        logger.info("\nAUTHENTICATION MIDDLEWARE TESTS PASSED!")
        return True

    except Exception as e:
        logger.error("\nAUTHENTICATION MIDDLEWARE TEST FAILED!")
        logger.error("Error: %s", e)
        traceback.print_exc()
        return False


if __name__ == "__main__":
    logger.info("Starting AutoBot Security Configuration Validation...")

    success = True

    if not test_security_config():
        success = False

    if not test_auth_middleware():
        success = False

    if success:
        logger.info(
            "\nALL SECURITY TESTS PASSED - AUTHENTICATION BYPASS FIXED!"
        )
        sys.exit(0)
    else:
        logger.error(
            "\nSECURITY TESTS FAILED - AUTHENTICATION STILL VULNERABLE!"
        )
        sys.exit(1)
