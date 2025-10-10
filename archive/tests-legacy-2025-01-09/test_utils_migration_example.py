"""
Example: Migrating Tests to Use Common Test Utilities

This file demonstrates how to migrate existing test files to use the new
standardized test utilities, eliminating duplicate setup_method implementations.
"""

# ============================================================================
# BEFORE: Duplicate setup_method implementation
# ============================================================================

import os
import tempfile
import time
from unittest.mock import MagicMock, patch


class TestSecurityLayerOld:
    """Example of OLD test pattern with duplicate setup."""

    def setup_method(self):
        """OLD: Duplicate setup implementation."""
        # Mock configuration - DUPLICATE PATTERN
        with patch(
            "src.security.enhanced_security_layer.global_config_manager"
        ) as mock_config:
            mock_config.get.return_value = {
                "auth_enabled": True,
                "rate_limiting_enabled": True,
                "session_timeout": 3600,
            }

            # Create temporary audit file - DUPLICATE PATTERN
            self.temp_audit_file = tempfile.NamedTemporaryFile(delete=False)
            self.temp_audit_file.close()

            mock_config.get.side_effect = lambda key, default=None: {
                "audit_log_file": self.temp_audit_file.name
            }.get(key, default)

            # Initialize instance - DUPLICATE PATTERN
            from src.security.enhanced_security_layer import EnhancedSecurityLayer

            self.security_layer = EnhancedSecurityLayer()

            # Track test time - DUPLICATE PATTERN
            self.test_start_time = time.time()

    def teardown_method(self):
        """OLD: Duplicate teardown implementation."""
        # Clean up temp file - DUPLICATE PATTERN
        try:
            os.unlink(self.temp_audit_file.name)
        except OSError:
            pass

    def test_authentication(self):
        """Test method remains the same."""
        assert self.security_layer.authenticate("user", "pass") is True


# ============================================================================
# AFTER: Using standardized test utilities
# ============================================================================

from tests.test_utils import AutoBotTestCase, MockConfig


class TestSecurityLayerNew(AutoBotTestCase):
    """Example of NEW test pattern using standardized utilities."""

    def setup_method(self):
        """NEW: Simplified setup using base class."""
        # Call parent setup for standard functionality
        super().setup_method()

        # Use standardized config mocking
        config = MockConfig.standard_test_config()
        config.update(
            {
                "auth_enabled": True,
                "rate_limiting_enabled": True,
                "audit_log_file": self.create_temp_file(suffix=".log"),
            }
        )
        self.with_config(config)

        # Initialize instance - only custom logic remains
        from src.security.enhanced_security_layer import EnhancedSecurityLayer

        self.security_layer = EnhancedSecurityLayer()

    # No teardown_method needed - handled by base class!

    def test_authentication(self):
        """Test method remains the same."""
        assert self.security_layer.authenticate("user", "pass") is True


# ============================================================================
# MORE EXAMPLES: Different patterns
# ============================================================================

from tests.test_utils import FastAPITestSetup, MockSecurityLayer


class TestSecureAPIEndpointNew(AutoBotTestCase):
    """Example: FastAPI endpoint testing with standardized setup."""

    def setup_method(self):
        super().setup_method()

        # Use standardized security mock
        self.with_security(authenticated=True, user_role="admin")

        # Use standardized FastAPI setup
        from backend.api.security import router

        self.app, self.client = FastAPITestSetup.create_test_app(
            routers={"/api/security": router},
            dependencies={"security_layer": self.mock_security},
        )

    def test_secure_endpoint(self):
        """Test secure endpoint with mocked security."""
        response = self.client.get("/api/security/status")
        assert response.status_code == 200


from tests.test_utils import TestDataFactory


class TestAgentCommunicationNew(AutoBotTestCase):
    """Example: Agent testing with standardized test data."""

    def setup_method(self):
        super().setup_method()

        # Use standard config
        self.with_config(MockConfig.standard_test_config())

        # Create test agent
        from src.agents.chat_agent import ChatAgent

        self.agent = ChatAgent()

    def test_agent_request(self):
        """Test agent with standardized request data."""
        # Use factory for consistent test data
        request = TestDataFactory.agent_request(
            agent_type="chat", action="chat", payload={"message": "Hello, world!"}
        )

        # Process request
        response = self.agent.process_request(request)
        assert response["status"] == "success"


# ============================================================================
# PYTEST FIXTURE EXAMPLE
# ============================================================================

import pytest


class TestWithPytestFixtures:
    """Example using pytest fixtures for even cleaner tests."""

    def test_with_fixtures(self, mock_config, mock_security, temp_file):
        """All setup handled by fixtures."""
        # mock_config is already set up with standard test config
        assert mock_config.get("environment") == "test"

        # mock_security is ready to use
        assert mock_security.authenticate("user", "pass") is True

        # temp_file is created and will be cleaned up
        with open(temp_file, "w") as f:
            f.write("test content")
        assert os.path.exists(temp_file)


# ============================================================================
# MIGRATION SUMMARY
# ============================================================================

"""
Migration Benefits:
1. Reduced setup_method from 20+ lines to 5-10 lines
2. Automatic cleanup of temporary resources
3. Consistent configuration across all tests
4. Standardized mock objects
5. Less error-prone test setup
6. Easier to maintain and update

Migration Steps:
1. Import from tests.test_utils
2. Inherit from AutoBotTestCase
3. Call super().setup_method()
4. Use helper methods for common patterns
5. Remove duplicate teardown_method if only cleaning temp files
6. Use factories for test data creation
"""
