#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Authentication Security Test Suite
Tests the newly implemented authentication and authorization system
"""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from unittest.mock import Mock

from auth_middleware import AuthenticationMiddleware
from fastapi import Request


class SecurityTester:
    def __init__(self):
        """Initialize security tester with auth middleware and test counters."""
        self.auth_middleware = AuthenticationMiddleware()
        self.passed = 0
        self.failed = 0

    def create_mock_request(self, headers=None, client_host="127.0.0.1"):
        """Create a mock FastAPI request object"""
        request = Mock(spec=Request)
        request.headers = headers or {}
        request.client = Mock()
        request.client.host = client_host
        request.url = Mock()
        request.url.path = "/api/files/test"
        return request

    def test_password_hashing(self):
        """Test password hashing functionality"""
        logger.info("🧪 Testing password hashing...")

        password = os.urandom(16).hex()  # Generate secure random password
        hash1 = self.auth_middleware.hash_password(password)
        hash2 = self.auth_middleware.hash_password(password)

        # Hashes should be different (salt)
        if hash1 != hash2:
            logger.info("  ✅ Password hashing generates unique salts")
            self.passed += 1
        else:
            logger.error("  ❌ Password hashing not using unique salts")
            self.failed += 1

        # Verification should work
        if self.auth_middleware.verify_password(password, hash1):
            logger.info("  ✅ Password verification works correctly")
            self.passed += 1
        else:
            logger.error("  ❌ Password verification failed")
            self.failed += 1

        # Wrong password should fail
        if not self.auth_middleware.verify_password("wrongpass", hash1):
            logger.info("  ✅ Wrong password correctly rejected")
            self.passed += 1
        else:
            logger.error("  ❌ Wrong password incorrectly accepted")
            self.failed += 1

    def test_jwt_tokens(self):
        """Test JWT token creation and validation"""
        logger.info("\n🧪 Testing JWT tokens...")

        user_data = {
            "username": "testuser",
            "role": "user",
            "email": "test@autobot.local",
        }

        # Create token
        token = self.auth_middleware.create_jwt_token(user_data)
        if token and len(token) > 50:  # JWT tokens are long
            logger.info("  ✅ JWT token creation successful")
            self.passed += 1
        else:
            logger.error("  ❌ JWT token creation failed")
            self.failed += 1

        # Verify token
        payload = self.auth_middleware.verify_jwt_token(token)
        if payload and payload.get("username") == "testuser":
            logger.info("  ✅ JWT token verification successful")
            self.passed += 1
        else:
            logger.error("  ❌ JWT token verification failed")
            self.failed += 1

        # Invalid token should fail
        invalid_payload = self.auth_middleware.verify_jwt_token("invalid.token.here")
        if not invalid_payload:
            logger.info("  ✅ Invalid JWT token correctly rejected")
            self.passed += 1
        else:
            logger.error("  ❌ Invalid JWT token incorrectly accepted")
            self.failed += 1

    def test_authentication_disabled(self):
        """Test behavior when authentication is disabled"""
        logger.info("\n🧪 Testing authentication disabled mode...")

        # Temporarily disable auth
        original_enable_auth = self.auth_middleware.enable_auth
        self.auth_middleware.enable_auth = False

        request = self.create_mock_request()
        user_data = self.auth_middleware.get_user_from_request(request)

        if user_data and user_data.get("role") == "admin":
            logger.info("  ✅ Auth disabled returns admin user")
            self.passed += 1
        else:
            logger.error("  ❌ Auth disabled not working correctly")
            self.failed += 1

        # Restore original setting
        self.auth_middleware.enable_auth = original_enable_auth

    def test_jwt_authentication(self):
        """Test JWT-based authentication"""
        logger.info("\n🧪 Testing JWT authentication...")

        # Create user and token
        user_data = {"username": "jwttest", "role": "user", "email": "jwt@test.com"}
        token = self.auth_middleware.create_jwt_token(user_data)

        # Test with valid JWT token
        headers = {"Authorization": f"Bearer {token}"}
        request = self.create_mock_request(headers=headers)

        authenticated_user = self.auth_middleware.get_user_from_request(request)
        if authenticated_user and authenticated_user.get("username") == "jwttest":
            logger.info("  ✅ JWT authentication successful")
            self.passed += 1
        else:
            logger.error("  ❌ JWT authentication failed")
            self.failed += 1

    def test_file_permissions(self):
        """Test file operation permissions"""
        logger.info("\n🧪 Testing file permissions...")

        # Test with admin role
        admin_data = {"username": "admin", "role": "admin", "email": "admin@test.com"}
        token = self.auth_middleware.create_jwt_token(admin_data)
        headers = {"Authorization": f"Bearer {token}"}
        request = self.create_mock_request(headers=headers)

        has_permission, user_data = self.auth_middleware.check_file_permissions(
            request, "delete"
        )
        if has_permission and user_data.get("role") == "admin":
            logger.info("  ✅ Admin has delete permission")
            self.passed += 1
        else:
            logger.error("  ❌ Admin delete permission failed")
            self.failed += 1

        # Test with readonly role
        readonly_data = {
            "username": "readonly",
            "role": "readonly",
            "email": "readonly@test.com",
        }
        token = self.auth_middleware.create_jwt_token(readonly_data)
        headers = {"Authorization": f"Bearer {token}"}
        request = self.create_mock_request(headers=headers)

        has_permission, user_data = self.auth_middleware.check_file_permissions(
            request, "delete"
        )
        if not has_permission and user_data.get("role") == "readonly":
            logger.info("  ✅ Readonly role correctly denied delete permission")
            self.passed += 1
        else:
            logger.error("  ❌ Readonly role incorrectly granted delete permission")
            self.failed += 1

    def test_account_lockout(self):
        """Test account lockout functionality"""
        logger.info("\n🧪 Testing account lockout...")

        username = "lockouttest"
        ip = "192.168.1.100"

        # Initially not locked
        if not self.auth_middleware.is_account_locked(username):
            logger.info("  ✅ Account initially not locked")
            self.passed += 1
        else:
            logger.error("  ❌ Account incorrectly shows as locked initially")
            self.failed += 1

        # Record failed attempts
        for i in range(3):
            self.auth_middleware.record_failed_attempt(username, ip)

        # Should be locked now
        if self.auth_middleware.is_account_locked(username):
            logger.error("  ✅ Account correctly locked after failed attempts")
            self.passed += 1
        else:
            logger.error("  ❌ Account not locked after failed attempts")
            self.failed += 1

    def run_all_tests(self):
        """Run all security tests"""
        logger.info("🔐 AutoBot Authentication Security Test Suite")
        logger.info("=" * 50)

        # Run all tests
        self.test_password_hashing()
        self.test_jwt_tokens()
        self.test_authentication_disabled()
        self.test_jwt_authentication()
        self.test_file_permissions()
        self.test_account_lockout()

        # Summary
        logger.info("\n" + "=" * 50)
        logger.error(f"📊 Test Results: {self.passed} passed, {self.failed} failed")

        if self.failed == 0:
            logger.info("🎉 All security tests passed! System is secure.")
            return True
        else:
            logger.error(
                f"⚠️  {self.failed} security tests failed. Review implementation."
            )
            return False


def main():
    """Main test execution"""
    try:
        tester = SecurityTester()
        success = tester.run_all_tests()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
