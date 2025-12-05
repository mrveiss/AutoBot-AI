# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal Input Handler for AutoBot

Provides non-blocking terminal input handling that works in both interactive
and automated testing environments, preventing test timeouts and CI/CD failures.
"""

import asyncio
import logging
import os
import queue
import sys
import threading
from contextlib import contextmanager
from typing import Dict, List, Optional

from src.constants.network_constants import NetworkConstants

from ..utils.service_registry import get_service_url

logger = logging.getLogger(__name__)

# Import configuration for fallback defaults
try:
    from src.unified_config_manager import unified_config_manager

    _config_available = True
except ImportError:
    _config_available = False


def _get_config_default(key: str, fallback: str) -> str:
    """Get configuration value with fallback."""
    if _config_available:
        try:
            return str(
                unified_config_manager.get_config_section("terminal_input", {}).get(
                    key, fallback
                )
            )
        except Exception:
            return fallback
    return fallback


class InputTimeoutError(Exception):
    """Raised when input operation times out."""


class TerminalInputHandler:
    """
    Handles terminal input in a way that's compatible with both interactive
    and automated testing environments.
    """

    def __init__(self):
        self.is_testing = self._detect_testing_environment()
        self.default_responses: Dict[str, str] = {}
        self.input_queue = queue.Queue()
        self.mock_responses = []
        self._mock_index = 0

    def _detect_testing_environment(self) -> bool:
        """Detect if we're running in a testing environment."""
        # Check various indicators of testing environment
        testing_indicators = [
            "pytest" in sys.modules,
            "unittest" in sys.modules,
            os.getenv("PYTEST_CURRENT_TEST") is not None,
            os.getenv("CI") is not None,
            os.getenv("GITHUB_ACTIONS") is not None,
            os.getenv("JENKINS_URL") is not None,
            os.getenv("TRAVIS") is not None,
            "--test" in sys.argv,
            "--automated" in sys.argv,
            not sys.stdin.isatty(),  # Not attached to a terminal
        ]

        return any(testing_indicators)

    def set_default_response(self, prompt_pattern: str, response: str):
        """
        Set a default response for a specific prompt pattern.

        Args:
            prompt_pattern: Pattern to match in the prompt
            response: Default response to return
        """
        self.default_responses[prompt_pattern.lower()] = response

    def set_mock_responses(self, responses: List[str]):
        """
        Set a sequence of mock responses for testing.

        Args:
            responses: List of responses to return in order
        """
        self.mock_responses = responses
        self._mock_index = 0

    def get_input(
        self, prompt: str = "", timeout: float = None, default: str = ""
    ) -> str:
        """
        Get input from user with timeout and testing support.

        Args:
            prompt: Prompt to display to user
            timeout: Timeout in seconds (ignored in testing, uses environment default if None)
            default: Default value to return if no input

        Returns:
            User input string

        Raises:
            InputTimeoutError: If timeout exceeded in interactive mode
        """
        # Use environment default for timeout if not specified
        if timeout is None:
            timeout = float(os.getenv("AUTOBOT_INPUT_TIMEOUT", "30.0"))

        # In testing mode, return mock or default responses
        if self.is_testing:
            return self._get_testing_response(prompt, default)

        # Interactive mode - use timeout
        try:
            return self._get_interactive_input(prompt, timeout, default)
        except KeyboardInterrupt:
            logger.info("Operation cancelled by user")
            return default

    def _get_testing_response(self, prompt: str, default: str) -> str:
        """Get response in testing environment."""
        # Use mock responses if available
        if self.mock_responses and self._mock_index < len(self.mock_responses):
            response = self.mock_responses[self._mock_index]
            self._mock_index += 1
            logger.debug(f"Mock response for '{prompt}': {response}")
            return response

        # Check for pattern-based default responses
        prompt_lower = prompt.lower()
        for pattern, response in self.default_responses.items():
            if pattern in prompt_lower:
                logger.debug(f"Default response for '{prompt}': {response}")
                return response

        # Return default or reasonable fallback
        if default:
            logger.debug(f"Using default for '{prompt}': {default}")
            return default

        # Intelligent defaults based on prompt content
        return self._generate_intelligent_default(prompt)

    def _generate_intelligent_default(self, prompt: str) -> str:
        """Generate intelligent default responses based on prompt content."""
        prompt_lower = prompt.lower()

        # Common prompt patterns and their defaults
        if any(word in prompt_lower for word in ["yes", "no", "y/n"]):
            return "y"
        elif "choice" in prompt_lower and any(char.isdigit() for char in prompt):
            # Extract numbers from prompt and return the first one
            numbers = [char for char in prompt if char.isdigit()]
            return (
                numbers[0]
                if numbers
                else os.getenv(
                    "AUTOBOT_DEFAULT_CHOICE", _get_config_default("default_choice", "1")
                )
            )
        elif "enter" in prompt_lower and "command" in prompt_lower:
            return os.getenv(
                "AUTOBOT_DEFAULT_COMMAND",
                _get_config_default("default_command", "help"),
            )
        elif "file" in prompt_lower or "path" in prompt_lower:
            return os.getenv(
                "AUTOBOT_TEST_FILE_PATH",
                _get_config_default("test_file_path", "/tmp/test_file"),
            )
        elif "name" in prompt_lower:
            return os.getenv(
                "AUTOBOT_TEST_USER_NAME",
                _get_config_default("test_user_name", "test_user"),
            )
        elif "port" in prompt_lower:
            return os.getenv(
                "AUTOBOT_DEFAULT_PORT",
                _get_config_default(
                    "default_port", str(NetworkConstants.AI_STACK_PORT)
                ),
            )
        elif "host" in prompt_lower:
            return os.getenv(
                "AUTOBOT_DEFAULT_HOST", _get_config_default("default_host", "localhost")
            )
        else:
            return ""  # Empty string for unknown prompts

    def _get_interactive_input(self, prompt: str, timeout: float, default: str) -> str:
        """Get input in interactive mode with timeout."""
        if timeout <= 0:
            # No timeout, use regular input
            try:
                response = input(prompt).strip()
                return response if response else default
            except EOFError:
                return default

        # Use threading for timeout support
        input_queue = queue.Queue()

        def input_thread():
            try:
                response = input(prompt).strip()
                input_queue.put(response if response else default)
            except EOFError:
                input_queue.put(default)
            except Exception as e:
                input_queue.put(f"ERROR: {e}")

        # Start input thread
        thread = threading.Thread(target=input_thread)
        thread.daemon = True
        thread.start()

        # Wait for input with timeout
        try:
            response = input_queue.get(timeout=timeout)
            if response.startswith("ERROR:"):
                logger.warning(f"Input error: {response}")
                return default
            return response
        except queue.Empty:
            raise InputTimeoutError(f"Input timeout after {timeout} seconds")

    async def get_input_async(
        self, prompt: str = "", timeout: float = None, default: str = ""
    ) -> str:
        """
        Asynchronous version of get_input.

        Args:
            prompt: Prompt to display
            timeout: Timeout in seconds (uses environment default if None)
            default: Default response

        Returns:
            User input string
        """
        # Use environment default for timeout if not specified
        if timeout is None:
            timeout = float(
                os.getenv(
                    "AUTOBOT_INPUT_TIMEOUT",
                    _get_config_default("default_timeout", "30.0"),
                )
            )

        if self.is_testing:
            return self._get_testing_response(prompt, default)

        # Run input in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None, lambda: self.get_input(prompt, timeout, default)
            )
        except InputTimeoutError:
            logger.warning(f"Async input timeout for prompt: {prompt}")
            return default

    @contextmanager
    def mock_input_context(self, responses: List[str]):
        """
        Context manager for mocking input in tests.

        Args:
            responses: List of responses to return
        """
        old_responses = self.mock_responses.copy()
        old_index = self._mock_index

        try:
            self.set_mock_responses(responses)
            yield self
        finally:
            self.mock_responses = old_responses
            self._mock_index = old_index

    def configure_for_testing(
        self,
        responses: Optional[List[str]] = None,
        defaults: Optional[Dict[str, str]] = None,
    ):
        """
        Configure handler for testing environment.

        Args:
            responses: Mock responses to use
            defaults: Default responses for prompt patterns
        """
        self.is_testing = True

        if responses:
            self.set_mock_responses(responses)

        if defaults:
            self.default_responses.update(defaults)


# Global instance (thread-safe)
_terminal_input_handler = None
_terminal_input_handler_lock = threading.Lock()


def get_terminal_input_handler() -> TerminalInputHandler:
    """Get or create global terminal input handler (thread-safe)."""
    global _terminal_input_handler
    if _terminal_input_handler is None:
        with _terminal_input_handler_lock:
            # Double-check after acquiring lock
            if _terminal_input_handler is None:
                _terminal_input_handler = TerminalInputHandler()
    return _terminal_input_handler


def safe_input(prompt: str = "", timeout: float = None, default: str = "") -> str:
    """
    Safe input function that works in both interactive and testing environments.

    This function should be used instead of the built-in input() to prevent
    test timeouts and provide consistent behavior across environments.

    Args:
        prompt: Prompt to display to user
        timeout: Timeout in seconds (ignored in testing environments, uses environment default if None)
        default: Default value to return if no input or timeout

    Returns:
        User input string or default
    """
    # Use environment default for timeout if not specified
    if timeout is None:
        timeout = float(os.getenv("AUTOBOT_INPUT_TIMEOUT", "30.0"))

    handler = get_terminal_input_handler()
    try:
        return handler.get_input(prompt, timeout, default)
    except InputTimeoutError:
        logger.warning(f"Input timeout for prompt: {prompt}")
        return default


async def safe_input_async(
    prompt: str = "", timeout: float = None, default: str = ""
) -> str:
    """
    Asynchronous safe input function.

    Args:
        prompt: Prompt to display
        timeout: Timeout in seconds (uses environment default if None)
        default: Default response

    Returns:
        User input string or default
    """
    # Use environment default for timeout if not specified
    if timeout is None:
        timeout = float(
            os.getenv(
                "AUTOBOT_INPUT_TIMEOUT", _get_config_default("default_timeout", "30.0")
            )
        )

    handler = get_terminal_input_handler()
    return await handler.get_input_async(prompt, timeout, default)


@contextmanager
def mock_terminal_input(responses: List[str]):
    """
    Context manager for mocking terminal input in tests.

    Usage:
        with mock_terminal_input(['y', '1', 'test_name']):
            # Code that uses safe_input() will get these responses
            pass

    Args:
        responses: List of responses to return in order
    """
    handler = get_terminal_input_handler()
    with handler.mock_input_context(responses):
        yield


def configure_testing_defaults():
    """Configure common default responses for testing."""
    handler = get_terminal_input_handler()

    # Common testing defaults - use configuration-driven fallbacks
    testing_defaults = {
        "yes/no": os.getenv(
            "AUTOBOT_DEFAULT_YES_NO", _get_config_default("default_yes_no", "y")
        ),
        "y/n": os.getenv(
            "AUTOBOT_DEFAULT_YES_NO", _get_config_default("default_yes_no", "y")
        ),
        "continue": os.getenv(
            "AUTOBOT_DEFAULT_CONTINUE", _get_config_default("default_continue", "y")
        ),
        "choice": os.getenv(
            "AUTOBOT_DEFAULT_CHOICE", _get_config_default("default_choice", "1")
        ),
        "select": os.getenv(
            "AUTOBOT_DEFAULT_CHOICE", _get_config_default("default_choice", "1")
        ),
        "enter your choice": os.getenv(
            "AUTOBOT_DEFAULT_CHOICE", _get_config_default("default_choice", "1")
        ),
        "command": os.getenv(
            "AUTOBOT_DEFAULT_COMMAND", _get_config_default("default_command", "help")
        ),
        "filename": os.getenv(
            "AUTOBOT_TEST_FILENAME",
            _get_config_default("test_filename", "test_file.txt"),
        ),
        "path": os.getenv(
            "AUTOBOT_TEST_PATH", _get_config_default("test_path", "/tmp/test")
        ),
        "name": os.getenv(
            "AUTOBOT_TEST_USER_NAME", _get_config_default("test_user_name", "test_user")
        ),
        "port": os.getenv(
            "AUTOBOT_AI_STACK_PORT",
            _get_config_default("default_port", str(NetworkConstants.AI_STACK_PORT)),
        ),
        "host": os.getenv(
            "AUTOBOT_AI_STACK_HOST",
            _get_config_default("default_host", NetworkConstants.AI_STACK_VM_IP),
        ),
        "url": get_service_url("ai-stack"),
        "email": os.getenv(
            "AUTOBOT_TEST_EMAIL", _get_config_default("test_email", "test@example.com")
        ),
    }

    handler.default_responses.update(testing_defaults)


# Monkey patch for backward compatibility
def patch_builtin_input():
    """
    Monkey patch the built-in input function to use safe_input.

    This should be called early in test initialization to ensure
    all input() calls use the safe version.
    """
    import builtins

    original_input = builtins.input

    def patched_input(prompt=""):
        timeout = float(
            os.getenv(
                "AUTOBOT_INPUT_TIMEOUT", _get_config_default("default_timeout", "30.0")
            )
        )
        return safe_input(prompt, timeout=timeout, default="")

    builtins.input = patched_input
    return original_input


def restore_builtin_input(original_input):
    """Restore the original input function."""
    import builtins

    builtins.input = original_input
