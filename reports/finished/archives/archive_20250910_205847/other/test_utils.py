"""
Common Test Utilities for AutoBot

This module provides standardized test utilities to eliminate duplicate setup_method
implementations across test files. It addresses the 20 duplicate patterns identified
in our codebase analysis.

Usage:
    from tests.test_utils import AutoBotTestCase, MockConfig, TempFileContext

    class TestMyFeature(AutoBotTestCase):
        def setup_method(self):
            super().setup_method()
            self.instance = MyClass()
"""

import os
import tempfile
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class MockConfig:
    """Standardized configuration mocking for tests."""

    @staticmethod
    @contextmanager
    def mock_global_config(config_values: Dict[str, Any]):
        """
        Context manager for mocking global_config_manager.

        Args:
            config_values: Dictionary of configuration values to mock

        Yields:
            Mock config manager instance

        Example:
            with MockConfig.mock_global_config({"redis_url": "redis://test"}):
                instance = MyClass()
                # Test with mocked config
        """
        with patch("src.config.config") as mock_config:
            # Handle both get() method and direct attribute access
            mock_config.get.side_effect = lambda key, default=None: config_values.get(
                key, default
            )

            # Set attributes for direct access
            for key, value in config_values.items():
                setattr(mock_config, key, value)

            yield mock_config

    @staticmethod
    def standard_test_config() -> Dict[str, Any]:
        """
        Returns standard test configuration values.

        Returns:
            Dictionary with common test configuration
        """
        return {
            "redis_url": "redis://localhost:6379/15",  # Test DB
            "redis_enabled": True,
            "log_level": "WARNING",
            "environment": "test",
            "auth_enabled": False,
            "rate_limiting_enabled": False,
            "session_timeout": 3600,
            "max_file_size": 1048576,  # 1MB
            "allowed_file_types": [".txt", ".py", ".js"],
            "api_timeout": 30,
            "workers": 1,
            "debug": False,
        }


class TempFileContext:
    """Context manager for temporary file handling in tests."""

    def __init__(
        self, suffix: str = "", prefix: str = "autobot_test_", delete: bool = True
    ):
        self.suffix = suffix
        self.prefix = prefix
        self.delete = delete
        self.temp_file = None
        self.temp_path = None

    def __enter__(self):
        """Create temporary file and return its path."""
        self.temp_file = tempfile.NamedTemporaryFile(
            suffix=self.suffix, prefix=self.prefix, delete=False
        )
        self.temp_path = self.temp_file.name
        self.temp_file.close()
        return self.temp_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up temporary file."""
        if self.delete and self.temp_path:
            try:
                os.unlink(self.temp_path)
            except OSError:
                pass  # File already deleted or doesn't exist


class MockSecurityLayer:
    """Standardized mock for security layer testing."""

    @staticmethod
    def create(
        authenticated: bool = True,
        user_role: str = "developer",
        session_id: str = "test_session_123",
        user_id: str = "test_user_456",
    ) -> MagicMock:
        """
        Create a mock security layer with standard behavior.

        Args:
            authenticated: Whether the user is authenticated
            user_role: User role for authorization
            session_id: Session identifier
            user_id: User identifier

        Returns:
            Configured mock security layer
        """
        mock_security = MagicMock()

        # Authentication
        mock_security.authenticate.return_value = authenticated
        mock_security.is_authenticated.return_value = authenticated

        # Authorization
        mock_security.authorize.return_value = authenticated
        mock_security.check_permission.return_value = authenticated

        # Session management
        mock_security.get_session_id.return_value = session_id
        mock_security.get_user_id.return_value = user_id
        mock_security.get_user_role.return_value = user_role

        # Token validation
        mock_security.validate_token.return_value = {
            "user_id": user_id,
            "role": user_role,
            "session_id": session_id,
            "authenticated": authenticated,
        }

        # Command validation
        mock_security.validate_command.return_value = True
        mock_security.filter_command.side_effect = lambda cmd: cmd  # Pass through

        return mock_security


class FastAPITestSetup:
    """Standardized FastAPI test application setup."""

    @staticmethod
    def create_test_app(
        routers: Optional[Dict[str, Any]] = None,
        dependencies: Optional[Dict[str, Any]] = None,
    ) -> tuple[FastAPI, TestClient]:
        """
        Create a test FastAPI application with standard configuration.

        Args:
            routers: Dictionary of {prefix: router} to include
            dependencies: Dictionary of dependencies to add to app.state

        Returns:
            Tuple of (FastAPI app, TestClient)
        """
        app = FastAPI(
            title="AutoBot Test API", version="test", docs_url=None, redoc_url=None
        )

        # Add routers
        if routers:
            for prefix, router in routers.items():
                app.include_router(router, prefix=prefix)

        # Add dependencies to app state
        if dependencies:
            for key, value in dependencies.items():
                setattr(app.state, key, value)

        # Create test client
        client = TestClient(app)

        return app, client


class AutoBotTestCase:
    """
    Base test class providing common setup functionality.

    Inherit from this class to get standardized setup/teardown behavior.
    """

    def setup_method(self):
        """Standard setup for all AutoBot tests."""
        # Track test execution time
        self.test_start_time = time.time()

        # Initialize common mocks
        self.mock_config = None
        self.mock_security = None
        self.temp_files = []

        # Set up test environment
        os.environ["AUTOBOT_ENV"] = "test"

    def teardown_method(self):
        """Standard teardown for all AutoBot tests."""
        # Clean up temporary files
        for temp_file in self.temp_files:
            try:
                os.unlink(temp_file)
            except OSError:
                pass

        # Reset environment
        os.environ.pop("AUTOBOT_ENV", None)

        # Log test execution time if needed
        execution_time = time.time() - self.test_start_time
        if execution_time > 1.0:  # Log slow tests
            print(f"Slow test detected: {execution_time:.2f}s")

    def with_config(self, config_values: Dict[str, Any]):
        """
        Set up configuration mocking for the test.

        Args:
            config_values: Configuration values to mock
        """
        self.mock_config = MockConfig.mock_global_config(config_values).__enter__()

    def with_security(self, **kwargs):
        """
        Set up security layer mocking for the test.

        Args:
            **kwargs: Arguments to pass to MockSecurityLayer.create()
        """
        self.mock_security = MockSecurityLayer.create(**kwargs)

    def create_temp_file(self, suffix: str = "", content: str = "") -> str:
        """
        Create a temporary file that will be cleaned up automatically.

        Args:
            suffix: File suffix/extension
            content: Initial content to write to the file

        Returns:
            Path to the temporary file
        """
        temp_file = tempfile.NamedTemporaryFile(
            suffix=suffix, prefix="autobot_test_", delete=False
        )
        temp_path = temp_file.name

        if content:
            temp_file.write(content.encode())

        temp_file.close()
        self.temp_files.append(temp_path)

        return temp_path


class TestDataFactory:
    """Factory methods for creating common test data."""

    @staticmethod
    def agent_request(
        agent_type: str = "test_agent",
        action: str = "test_action",
        payload: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a standard agent request for testing."""
        return {
            "request_id": request_id or f"test_req_{int(time.time())}",
            "agent_type": agent_type,
            "action": action,
            "payload": payload or {},
            "context": context or {},
            "timestamp": time.time(),
        }

    @staticmethod
    def websocket_message(
        action: str = "test",
        data: Optional[Dict[str, Any]] = None,
        session_id: str = "test_session",
    ) -> Dict[str, Any]:
        """Create a standard WebSocket message for testing."""
        return {
            "action": action,
            "data": data or {},
            "session_id": session_id,
            "timestamp": time.time(),
        }

    @staticmethod
    def mock_callback():
        """Create a standard mock callback function."""
        callback = MagicMock()
        callback.return_value = None
        return callback


# Pytest fixtures for even more convenience
try:
    import pytest

    @pytest.fixture
    def mock_config():
        """Pytest fixture for configuration mocking."""
        with MockConfig.mock_global_config(MockConfig.standard_test_config()) as config:
            yield config

    @pytest.fixture
    def mock_security():
        """Pytest fixture for security layer mocking."""
        return MockSecurityLayer.create()

    @pytest.fixture
    def temp_file():
        """Pytest fixture for temporary file handling."""
        with TempFileContext() as temp_path:
            yield temp_path

    @pytest.fixture
    def test_client():
        """Pytest fixture for FastAPI test client."""
        app, client = FastAPITestSetup.create_test_app()
        yield client

except ImportError:
    # Pytest not available, skip fixture definitions
    pass
