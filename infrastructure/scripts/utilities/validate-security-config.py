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

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_security_config():
    """Test that security configuration is properly loaded."""
    try:
        print("🔐 AUTOBOT SECURITY CONFIGURATION VALIDATION")
        print("=" * 50)

        # Test 1: Import SecurityLayer
        print("\n1. Testing SecurityLayer import...")
        from src.security_layer import SecurityLayer

        print("✅ SecurityLayer imported successfully")

        # Test 2: Initialize SecurityLayer
        print("\n2. Testing SecurityLayer initialization...")
        security = SecurityLayer()
        print("✅ SecurityLayer initialized successfully")

        # Test 3: Check authentication enabled
        print("\n3. Testing authentication status...")
        print(f"   enable_auth: {security.enable_auth}")
        if security.enable_auth:
            print("✅ Authentication is ENABLED")
        else:
            print("❌ Authentication is DISABLED - SECURITY VULNERABILITY!")
            return False

        # Test 4: Check audit log configuration
        print("\n4. Testing audit log configuration...")
        print(f"   audit_log_file: {security.audit_log_file}")
        audit_dir = os.path.dirname(security.audit_log_file)
        if os.path.exists(audit_dir):
            print("✅ Audit log directory exists")
        else:
            print(f"❌ Audit log directory missing: {audit_dir}")
            return False

        # Test 5: Check allowed users configuration
        print("\n5. Testing allowed users configuration...")
        print(f"   Number of allowed users: {len(security.allowed_users)}")
        expected_users = ["admin", "developer", "readonly"]
        for user in expected_users:
            if user in security.allowed_users:
                print(f"   ✅ User '{user}' configured")
                user_config = security.allowed_users[user]
                if "password_hash" in user_config:
                    print(f"      ✅ Password hash configured for '{user}'")
                else:
                    print(f"      ❌ Missing password hash for '{user}'")
                    return False
            else:
                print(f"   ❌ Missing user '{user}'")
                return False

        # Test 6: Check roles configuration
        print("\n6. Testing roles configuration...")
        print(f"   Number of roles: {len(security.roles)}")
        expected_roles = ["admin", "developer", "editor", "user", "readonly", "guest"]
        for role in expected_roles:
            if role in security.roles:
                print(f"   ✅ Role '{role}' configured")
                role_config = security.roles[role]
                if "permissions" in role_config:
                    perms = role_config["permissions"]
                    print(f"      ✅ {len(perms)} permissions defined for '{role}'")
                else:
                    print(f"      ❌ Missing permissions for role '{role}'")
                    return False
            else:
                print(f"   ❌ Missing role '{role}'")
                return False

        # Test 7: Test permission checking
        print("\n7. Testing permission checking...")

        # Admin should have all permissions
        has_all = security.check_permission("admin", "allow_shell_execute")
        if has_all:
            print("   ✅ Admin role has full permissions")
        else:
            print("   ❌ Admin role missing permissions")
            return False

        # Readonly should not have write permissions
        has_write = security.check_permission("readonly", "files.upload")
        if not has_write:
            print("   ✅ Readonly role properly restricted")
        else:
            print("   ❌ Readonly role has too many permissions")
            return False

        # Test 8: Test audit logging
        print("\n8. Testing audit logging...")
        try:
            security.audit_log(
                action="security_validation_test",
                user="test_user",
                outcome="success",
                details={"test": "security_config_validation"},
            )
            print("   ✅ Audit logging working")
        except Exception as e:
            print(f"   ❌ Audit logging failed: {e}")
            return False

        print("\n🎉 ALL SECURITY CONFIGURATION TESTS PASSED!")
        print("\n📋 SECURITY STATUS SUMMARY:")
        print("   • Authentication: ENABLED")
        print(f"   • Users configured: {len(security.allowed_users)}")
        print(f"   • Roles configured: {len(security.roles)}")
        print("   • Audit logging: WORKING")
        print("   • Permission system: FUNCTIONAL")

        return True

    except Exception as e:
        print("\n❌ SECURITY CONFIGURATION TEST FAILED!")
        print(f"Error: {e}")
        print("\nTraceback:")
        traceback.print_exc()
        return False


def test_auth_middleware():
    """Test that AuthMiddleware can load the security configuration."""
    try:
        print("\n" + "=" * 50)
        print("🔐 AUTHENTICATION MIDDLEWARE VALIDATION")
        print("=" * 50)

        # Test AuthMiddleware import and initialization
        print("\n1. Testing AuthMiddleware import...")
        from src.auth_middleware import auth_middleware

        print("✅ AuthMiddleware imported successfully")

        print("\n2. Testing AuthMiddleware configuration...")
        print(f"   enable_auth: {auth_middleware.enable_auth}")
        if auth_middleware.enable_auth:
            print("✅ AuthMiddleware authentication ENABLED")
        else:
            print("❌ AuthMiddleware authentication DISABLED")
            return False

        print("\n🎉 AUTHENTICATION MIDDLEWARE TESTS PASSED!")
        return True

    except Exception as e:
        print("\n❌ AUTHENTICATION MIDDLEWARE TEST FAILED!")
        print(f"Error: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Starting AutoBot Security Configuration Validation...")

    success = True

    # Test SecurityLayer
    if not test_security_config():
        success = False

    # Test AuthMiddleware
    if not test_auth_middleware():
        success = False

    if success:
        print("\n✅ ALL SECURITY TESTS PASSED - AUTHENTICATION BYPASS FIXED!")
        sys.exit(0)
    else:
        print("\n❌ SECURITY TESTS FAILED - AUTHENTICATION STILL VULNERABLE!")
        sys.exit(1)
