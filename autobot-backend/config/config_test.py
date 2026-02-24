"""
Test Configuration Module

Provides global test configuration and setup, including patching of
terminal input functions to prevent hanging in automated test environments.
"""

import os
import sys
from typing import List

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.terminal_input_handler import (
    configure_testing_defaults,
    get_terminal_input_handler,
    patch_builtin_input,
)


def configure_test_environment():
    """Configure the test environment for non-blocking input."""
    # Set environment variables to indicate testing
    os.environ["CI"] = "1"
    os.environ["TESTING"] = "1"
    os.environ["PYTEST_RUNNING"] = "1"

    # Configure terminal input handler for testing
    handler = get_terminal_input_handler()
    handler.configure_for_testing()

    # Set up common testing defaults
    configure_testing_defaults()

    # Patch built-in input function globally
    original_input = patch_builtin_input()

    return original_input


# Pytest fixtures for input handling
@pytest.fixture
def mock_input():
    """Fixture to mock input function with predefined responses."""
    from utils.terminal_input_handler import mock_terminal_input

    def _mock_input(responses: List[str]):
        return mock_terminal_input(responses)

    return _mock_input


@pytest.fixture
def non_interactive_environment():
    """Fixture to ensure non-interactive test environment."""
    original_env = os.environ.copy()

    # Set testing environment variables
    os.environ["CI"] = "1"
    os.environ["TESTING"] = "1"
    os.environ["PYTEST_RUNNING"] = "1"

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(autouse=True)
def configure_for_tests():
    """Auto-use fixture to configure every test for non-blocking input."""
    configure_test_environment()
    yield


# Test helper functions
def run_with_timeout(func, timeout=30, *args, **kwargs):
    """Run a function with timeout to prevent hanging tests."""
    import threading

    result = [None]
    exception = [None]

    def target():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        raise TimeoutError(
            f"Function {func.__name__} timed out after {timeout} seconds"
        )

    if exception[0]:
        raise exception[0]

    return result[0]


def ensure_non_blocking(test_func):
    """Decorator to ensure test functions don't block on input."""

    def wrapper(*args, **kwargs):
        # Configure testing environment
        configure_test_environment()

        # Run test with timeout
        return run_with_timeout(test_func, 60, *args, **kwargs)

    return wrapper


# Common test responses for different scenarios
TEST_RESPONSES = {
    "yes_no": ["y", "n", "yes", "no"],
    "choices": ["1", "2", "3", "4", "5"],
    "commands": ["help", "status", "exit", "quit"],
    "files": ["test.txt", "/tmp/test", "example.json"],
    "names": ["test_user", "admin", "user"],
    "urls": ["http://localhost:8080", "http://example.com"],
    "default": ["", "default", "skip"],
}


def get_test_responses(scenario: str = "default") -> List[str]:
    """Get predefined test responses for common scenarios."""
    return TEST_RESPONSES.get(scenario, TEST_RESPONSES["default"])


# Pytest configuration hooks
def pytest_configure(config):
    """Configure pytest for non-blocking tests."""
    configure_test_environment()


def pytest_runtest_setup(item):
    """Setup each test for non-blocking input."""
    configure_test_environment()


# Context managers for specific test scenarios
class MockInputContext:
    """Context manager for mocking input with specific responses."""

    def __init__(self, responses: List[str]):
        self.responses = responses
        self.handler = get_terminal_input_handler()
        self.original_responses = []
        self.original_index = 0

    def __enter__(self):
        self.original_responses = self.handler.mock_responses.copy()
        self.original_index = self.handler._mock_index
        self.handler.set_mock_responses(self.responses)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.handler.mock_responses = self.original_responses
        self.handler._mock_index = self.original_index


# Test utilities for specific components
def setup_classification_agent_test():
    """Setup test environment for classification agent tests."""
    responses = ["test message", "classification test", "exit"]
    handler = get_terminal_input_handler()
    handler.set_mock_responses(responses)

    defaults = {
        "enter message": "test message",
        "classification": "test classification",
        "choice": "1",
    }
    handler.default_responses.update(defaults)


def setup_terminal_test():
    """Setup test environment for terminal-related tests."""
    responses = ["help", "status", "exit"]
    handler = get_terminal_input_handler()
    handler.set_mock_responses(responses)

    defaults = {"command": "help", "choice": "1", "continue": "y"}
    handler.default_responses.update(defaults)


def setup_workflow_test():
    """Setup test environment for workflow tests."""
    responses = ["y", "1", "test_workflow", "exit"]
    handler = get_terminal_input_handler()
    handler.set_mock_responses(responses)


# Initialization - run when module is imported
if __name__ != "__main__":
    # Only configure if imported, not when run directly
    configure_test_environment()


if __name__ == "__main__":
    print("Test Configuration Module")  # noqa: print
    print("=" * 40)  # noqa: print

    # Test the configuration
    print("Testing terminal input handler...")  # noqa: print

    from utils.terminal_input_handler import safe_input

    # Test with mock responses
    handler = get_terminal_input_handler()
    handler.set_mock_responses(["test1", "test2", "test3"])

    result1 = safe_input("Test prompt 1: ")
    result2 = safe_input("Test prompt 2: ")
    result3 = safe_input("Test prompt 3: ")

    print(f"Response 1: '{result1}'")  # noqa: print
    print(f"Response 2: '{result2}'")  # noqa: print
    print(f"Response 3: '{result3}'")  # noqa: print

    # Test default behavior
    result4 = safe_input("Test prompt 4: ", default="default_value")
    print(f"Response 4: '{result4}'")  # noqa: print

    print("✅ Test configuration working correctly!")  # noqa: print
