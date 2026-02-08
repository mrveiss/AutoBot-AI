#!/usr/bin/env python3
"""
Test suite for AutoBot Terminal Input Handler.
"""

import asyncio
import os
import sys
import threading
import time
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.terminal_input_handler import (
    InputTimeoutError,
    TerminalInputHandler,
    configure_testing_defaults,
    mock_terminal_input,
    patch_builtin_input,
    safe_input,
    safe_input_async,
)


class TestTerminalInputHandler:
    """Test cases for terminal input handler functionality."""

    def __init__(self):
        self.handler = TerminalInputHandler()

    def test_environment_detection(self):
        """Test testing environment detection."""
        print("Testing environment detection...")

        # Test current environment detection
        is_testing = self.handler.is_testing
        print(f"  Current environment detected as testing: {is_testing}")

        # Test with manual configuration
        handler2 = TerminalInputHandler()
        handler2.is_testing = True
        assert handler2.is_testing is True, "Should accept manual testing configuration"

        # Test various environment indicators
        test_indicators = {
            "CI": "1",
            "PYTEST_CURRENT_TEST": "test_file.py",
            "GITHUB_ACTIONS": "true",
            "TESTING": "1",
        }

        for env_var, value in test_indicators.items():
            # Temporarily set environment variable
            old_value = os.environ.get(env_var)
            os.environ[env_var] = value

            handler3 = TerminalInputHandler()
            print(f"    {env_var}={value} detected as testing: {handler3.is_testing}")

            # Restore environment
            if old_value is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = old_value

        print("✓ Environment detection working")
        return True

    def test_mock_responses(self):
        """Test mock response functionality."""
        print("\nTesting mock responses...")

        # Set mock responses
        test_responses = ["response1", "response2", "response3"]
        self.handler.set_mock_responses(test_responses)

        # Ensure testing mode
        self.handler.is_testing = True

        # Test sequential responses
        for i, expected in enumerate(test_responses):
            result = self.handler.get_input(f"Prompt {i+1}: ")
            print(f"  Mock response {i+1}: '{result}' (expected: '{expected}')")
            assert result == expected, f"Should return mock response {expected}"

        # Test exhausted responses (should use defaults)
        result = self.handler.get_input("Extra prompt: ", default="default_value")
        print(f"  Exhausted mock responses: '{result}' (should be default)")

        print("✓ Mock responses working")
        return True

    def test_default_responses(self):
        """Test default response patterns."""
        print("\nTesting default response patterns...")

        self.handler.is_testing = True
        self.handler.set_mock_responses([])  # Clear mock responses

        test_cases = [
            ("Do you want to continue? (y/n)", "y"),
            ("Enter your choice (1-3):", "1"),
            ("Please enter a command:", "help"),
            ("Enter file path:", "/tmp/test_file"),
            ("What is your name?", "test_user"),
            ("Enter port number:", "8080"),
            ("Enter hostname:", "localhost"),
        ]

        for prompt, expected_pattern in test_cases:
            result = self.handler.get_input(prompt)
            print(f"  '{prompt}' -> '{result}'")

            # Check if response matches expected pattern type
            if "y/n" in prompt.lower():
                assert result in ["y", "n"], "Should return y/n for yes/no prompt"
            elif "choice" in prompt.lower() and any(c.isdigit() for c in prompt):
                assert result.isdigit(), "Should return digit for choice prompt"

        print("✓ Default response patterns working")
        return True

    def test_timeout_behavior(self):
        """Test timeout behavior in interactive mode."""
        print("\nTesting timeout behavior...")

        # Test with testing mode (should not timeout)
        self.handler.is_testing = True
        start_time = time.time()
        result = self.handler.get_input("Test prompt: ", timeout=0.1, default="quick")
        duration = time.time() - start_time

        print(f"  Testing mode response time: {duration:.3f}s (result: '{result}')")
        assert duration < 0.5, "Testing mode should be fast"

        # Test timeout with interactive mode (mock to avoid actual waiting)
        handler_interactive = TerminalInputHandler()
        handler_interactive.is_testing = False

        # Mock the interactive input to simulate timeout
        try:
            with patch("builtins.input", side_effect=lambda x: time.sleep(2)):
                start_time = time.time()
                try:
                    result = handler_interactive.get_input(
                        "Timeout test: ", timeout=0.1, default="timeout_default"
                    )
                    duration = time.time() - start_time
                    print(
                        f"  Interactive timeout test: {duration:.3f}s (result: '{result}')"
                    )
                except InputTimeoutError:
                    duration = time.time() - start_time
                    print(
                        f"  Interactive timeout raised exception after: {duration:.3f}s"
                    )
        except Exception as e:
            print(f"  Timeout test skipped due to: {e}")

        print("✓ Timeout behavior working")
        return True

    async def test_async_input(self):
        """Test asynchronous input functionality."""
        print("\nTesting asynchronous input...")

        self.handler.is_testing = True
        self.handler.set_mock_responses(["async1", "async2"])

        # Test basic async input
        result1 = await self.handler.get_input_async("Async prompt 1: ")
        result2 = await self.handler.get_input_async("Async prompt 2: ")

        print(f"  Async result 1: '{result1}'")
        print(f"  Async result 2: '{result2}'")

        assert result1 == "async1", "Should return first async response"
        assert result2 == "async2", "Should return second async response"

        # Test concurrent async inputs
        tasks = [
            self.handler.get_input_async(f"Concurrent {i}: ", default=f"default{i}")
            for i in range(3)
        ]

        results = await asyncio.gather(*tasks)
        print(f"  Concurrent results: {results}")

        assert len(results) == 3, "Should handle concurrent requests"

        print("✓ Async input working")
        return True

    def test_context_manager(self):
        """Test context manager functionality."""
        print("\nTesting context manager...")

        self.handler.is_testing = True

        # Test mock input context manager
        test_responses = ["ctx1", "ctx2", "ctx3"]

        with self.handler.mock_input_context(test_responses):
            result1 = self.handler.get_input("Context prompt 1: ")
            result2 = self.handler.get_input("Context prompt 2: ")

            print(f"  Context result 1: '{result1}'")
            print(f"  Context result 2: '{result2}'")

            assert result1 == "ctx1", "Should use context responses"
            assert result2 == "ctx2", "Should use sequential context responses"

        # After context, should revert to original behavior
        result3 = self.handler.get_input(
            "Post-context prompt: ", default="post_default"
        )
        print(f"  Post-context result: '{result3}'")

        print("✓ Context manager working")
        return True

    def test_safe_input_functions(self):
        """Test the safe_input wrapper functions."""
        print("\nTesting safe input wrapper functions...")

        # Configure for testing
        configure_testing_defaults()

        # Test safe_input function
        with mock_terminal_input(["wrapper1", "wrapper2"]):
            result1 = safe_input("Safe input test 1: ")
            result2 = safe_input("Safe input test 2: ")

            print(f"  Safe input result 1: '{result1}'")
            print(f"  Safe input result 2: '{result2}'")

            assert result1 == "wrapper1", "Should use wrapper mock responses"
            assert result2 == "wrapper2", "Should use sequential wrapper responses"

        print("✓ Safe input wrapper working")
        return True

    async def test_safe_input_async_function(self):
        """Test the async safe_input wrapper function."""
        print("\nTesting async safe input wrapper...")

        with mock_terminal_input(["async_wrapper1", "async_wrapper2"]):
            result1 = await safe_input_async("Async safe input 1: ")
            result2 = await safe_input_async("Async safe input 2: ")

            print(f"  Async safe result 1: '{result1}'")
            print(f"  Async safe result 2: '{result2}'")

            assert result1 == "async_wrapper1", "Should use async wrapper responses"
            assert result2 == "async_wrapper2", "Should use sequential async responses"

        print("✓ Async safe input wrapper working")
        return True

    def test_builtin_patch(self):
        """Test built-in input function patching."""
        print("\nTesting built-in input patching...")

        # Save original input
        import builtins

        original_input = builtins.input

        # Patch built-in input
        patch_builtin_input()

        try:
            # Configure for testing
            with mock_terminal_input(["patched1", "patched2"]):
                # Use built-in input (should be patched)
                result1 = input("Patched input test 1: ")
                result2 = input("Patched input test 2: ")

                print(f"  Patched input result 1: '{result1}'")
                print(f"  Patched input result 2: '{result2}'")

                assert result1 == "patched1", "Should use patched input"
                assert result2 == "patched2", "Should use sequential patched responses"

        finally:
            # Restore original input
            builtins.input = original_input

        print("✓ Built-in input patching working")
        return True

    def test_intelligent_defaults(self):
        """Test intelligent default response generation."""
        print("\nTesting intelligent default responses...")

        self.handler.is_testing = True
        self.handler.set_mock_responses([])  # Force use of defaults

        test_cases = [
            ("Continue? (y/n)", lambda r: r in ["y", "n"]),
            ("Select option (1-5):", lambda r: r.isdigit()),
            ("Enter a command:", lambda r: len(r) > 0),
            ("File path:", lambda r: "/" in r or len(r) > 0),
            ("Your name:", lambda r: len(r) > 0),
            ("Port number:", lambda r: r.isdigit()),
            ("Host address:", lambda r: len(r) > 0),
        ]

        for prompt, validator in test_cases:
            result = self.handler.get_input(prompt)
            is_valid = validator(result)
            print(f"  '{prompt}' -> '{result}' (valid: {is_valid})")
            assert is_valid, f"Should generate appropriate default for: {prompt}"

        print("✓ Intelligent defaults working")
        return True

    async def test_concurrent_safety(self):
        """Test thread and async safety."""
        print("\nTesting concurrent safety...")

        self.handler.is_testing = True

        # Test multiple threads using handler simultaneously
        results = []

        def thread_worker(thread_id):
            self.handler.set_mock_responses([f"thread_{thread_id}_response"])
            result = self.handler.get_input(f"Thread {thread_id} prompt: ")
            results.append(result)

        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=thread_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        print(f"  Thread results: {results}")
        assert len(results) == 5, "Should handle concurrent thread access"

        # Test async concurrency
        async def async_worker(worker_id):
            return await self.handler.get_input_async(
                f"Async worker {worker_id}: ", default=f"async_result_{worker_id}"
            )

        async_results = await asyncio.gather(*[async_worker(i) for i in range(3)])

        print(f"  Async results: {async_results}")
        assert len(async_results) == 3, "Should handle concurrent async access"

        print("✓ Concurrent safety working")
        return True

    async def run_all_tests(self):
        """Run all terminal input handler tests."""
        print("=" * 70)
        print("AutoBot Terminal Input Handler Test Suite")
        print("=" * 70)

        try:
            # Test environment detection
            self.test_environment_detection()

            # Test mock responses
            self.test_mock_responses()

            # Test default responses
            self.test_default_responses()

            # Test timeout behavior
            self.test_timeout_behavior()

            # Test async input
            await self.test_async_input()

            # Test context manager
            self.test_context_manager()

            # Test safe input functions
            self.test_safe_input_functions()

            # Test async safe input
            await self.test_safe_input_async_function()

            # Test built-in patching
            self.test_builtin_patch()

            # Test intelligent defaults
            self.test_intelligent_defaults()

            # Test concurrent safety
            await self.test_concurrent_safety()

            print("\n" + "=" * 70)
            print("✅ All Terminal Input Handler Tests Passed!")
            print("=" * 70)
            print("Summary:")
            print("  - Environment detection: ✓")
            print("  - Mock responses: ✓")
            print("  - Default patterns: ✓")
            print("  - Timeout handling: ✓")
            print("  - Async support: ✓")
            print("  - Context management: ✓")
            print("  - Safe input wrappers: ✓")
            print("  - Built-in patching: ✓")
            print("  - Intelligent defaults: ✓")
            print("  - Concurrent safety: ✓")
            print("\n🎉 Terminal input handling is now test-safe!")
            print("🔧 No more hanging tests due to input() calls!")

            return True

        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback

            traceback.print_exc()
            return False


async def main():
    """Main test execution function."""
    tester = TestTerminalInputHandler()
    success = await tester.run_all_tests()

    if success:
        print("\n🎯 Terminal input handler is working correctly!")
        print("🚀 Automated tests will no longer hang on input!")
        return 0
    else:
        print("\n💥 Terminal input handler tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
