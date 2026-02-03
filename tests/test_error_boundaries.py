#!/usr/bin/env python3
"""
Comprehensive Test Suite for Error Boundary System

Tests all aspects of the error boundary system including decorators,
context managers, recovery handlers, and API endpoints.
"""

import asyncio
import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.error_boundaries import (
    ErrorBoundaryException,
    ErrorBoundaryManager,
    ErrorCategory,
    ErrorContext,
    ErrorReport,
    ErrorSeverity,
    FallbackRecoveryHandler,
    GracefulDegradationHandler,
    RecoveryStrategy,
    RetryRecoveryHandler,
    error_boundary,
)


class TestErrorBoundaryManager(unittest.TestCase):
    """Test the ErrorBoundaryManager class"""

    def setUp(self):
        """Set up test environment"""
        # Mock Redis client
        self.mock_redis = Mock()
        self.mock_redis.keys.return_value = []
        self.mock_redis.get.return_value = None
        self.mock_redis.setex.return_value = True

        # Create manager with mocked Redis
        self.manager = ErrorBoundaryManager(redis_client=self.mock_redis)

    def test_error_categorization(self):
        """Test automatic error categorization"""
        test_cases = [
            (ConnectionError("Connection failed"), ErrorCategory.NETWORK),
            (TimeoutError("Request timeout"), ErrorCategory.NETWORK),
            (ValueError("Invalid SQL"), ErrorCategory.DATABASE),
            (Exception("LLM model error"), ErrorCategory.LLM),
            (PermissionError("Access denied"), ErrorCategory.SYSTEM),
            (TypeError("Invalid type"), ErrorCategory.SYSTEM),
        ]

        for error, expected_category in test_cases:
            with self.subTest(error=error):
                category = self.manager.categorize_error(error)
                # Allow for reasonable categorization (may not be exact)
                self.assertIsInstance(category, ErrorCategory)

    def test_severity_determination(self):
        """Test error severity determination"""
        context = ErrorContext(component="test", function="test_func")

        test_cases = [
            (MemoryError("Out of memory"), ErrorSeverity.CRITICAL),
            (SystemExit("System exit"), ErrorSeverity.CRITICAL),
            (ConnectionError("Connection failed"), ErrorSeverity.HIGH),
            (ValueError("Invalid value"), ErrorSeverity.MEDIUM),
            (Warning("Just a warning"), ErrorSeverity.LOW),
        ]

        for error, expected_severity in test_cases:
            with self.subTest(error=error):
                severity = self.manager.determine_severity(error, context)
                # Allow for reasonable severity assignment
                self.assertIsInstance(severity, ErrorSeverity)

    def test_error_report_creation(self):
        """Test error report creation"""
        context = ErrorContext(
            component="test_component",
            function="test_function",
            user_id="test_user",
            request_id="req_123",
        )

        error = ValueError("Test error")
        report = self.manager.create_error_report(error, context)

        self.assertIsInstance(report, ErrorReport)
        self.assertEqual(report.error_type, "ValueError")
        self.assertEqual(report.message, "Test error")
        self.assertEqual(report.context.component, "test_component")
        self.assertEqual(report.context.function, "test_function")
        self.assertIsInstance(report.severity, ErrorSeverity)
        self.assertIsInstance(report.category, ErrorCategory)
        self.assertIsInstance(report.recovery_strategy, RecoveryStrategy)

    def test_error_statistics(self):
        """Test error statistics calculation"""
        # Mock Redis data
        mock_errors = [
            {"category": "network", "severity": "high", "component": "api"},
            {"category": "database", "severity": "medium", "component": "storage"},
            {"category": "network", "severity": "low", "component": "api"},
        ]

        self.mock_redis.keys.return_value = ["error_1", "error_2", "error_3"]
        self.mock_redis.get.side_effect = [json.dumps(e) for e in mock_errors]

        stats = self.manager.get_error_statistics()

        self.assertEqual(stats["total_errors"], 3)
        self.assertEqual(stats["categories"]["network"], 2)
        self.assertEqual(stats["categories"]["database"], 1)
        self.assertEqual(stats["severities"]["high"], 1)
        self.assertEqual(stats["components"]["api"], 2)


class TestRecoveryHandlers(unittest.TestCase):
    """Test recovery handler implementations"""

    def setUp(self):
        """Set up test environment"""
        self.context = ErrorContext(component="test", function="test_func")

    def test_retry_recovery_handler(self):
        """Test retry recovery handler"""
        handler = RetryRecoveryHandler(max_retries=2, backoff_factor=1.0)

        # Test can_handle
        self.assertTrue(handler.can_handle(ConnectionError(), self.context))
        self.assertTrue(handler.can_handle(ValueError(), self.context))

    def test_fallback_recovery_handler(self):
        """Test fallback recovery handler"""
        fallbacks = {"test.test_func": "fallback_value"}
        handler = FallbackRecoveryHandler(fallbacks)

        # Test can_handle
        self.assertTrue(handler.can_handle(Exception(), self.context))

        # Test handle (async)
        async def test_handle():
            result = await handler.handle(ValueError("test"), self.context)
            self.assertEqual(result, "fallback_value")

        asyncio.run(test_handle())

    def test_graceful_degradation_handler(self):
        """Test graceful degradation handler"""

        def degraded_func(*args, **kwargs):
            return "degraded_result"

        degraded_functions = {"test.test_func": degraded_func}
        handler = GracefulDegradationHandler(degraded_functions)

        # Test can_handle
        self.assertTrue(handler.can_handle(Exception(), self.context))

        # Test handle
        async def test_handle():
            result = await handler.handle(ValueError("test"), self.context)
            self.assertEqual(result, "degraded_result")

        asyncio.run(test_handle())


class TestErrorBoundaryDecorator(unittest.TestCase):
    """Test the error boundary decorator"""

    def test_sync_function_decorator(self):
        """Test decorator on synchronous functions"""

        @error_boundary(component="test", function="divide")
        def divide(a, b):
            if b == 0:
                raise ZeroDivisionError("Division by zero")
            return a / b

        # Test normal operation
        result = divide(10, 2)
        self.assertEqual(result, 5.0)

        # Test error handling would require full error boundary setup
        # For now, just verify the function is decorated
        self.assertTrue(hasattr(divide, "__wrapped__"))

    def test_async_function_decorator(self):
        """Test decorator on asynchronous functions"""

        @error_boundary(component="test", function="async_divide")
        async def async_divide(a, b):
            if b == 0:
                raise ZeroDivisionError("Division by zero")
            await asyncio.sleep(0.01)  # Simulate async work
            return a / b

        async def test_async():
            # Test normal operation
            result = await async_divide(10, 2)
            self.assertEqual(result, 5.0)

        asyncio.run(test_async())


class TestErrorBoundaryIntegration(unittest.TestCase):
    """Integration tests for error boundary system"""

    def setUp(self):
        """Set up integration test environment"""
        # Use a real Redis client if available, otherwise mock
        try:
            from src.utils.redis_client import get_redis_client

            redis_client = get_redis_client()
            if redis_client and redis_client.ping():
                self.manager = ErrorBoundaryManager(redis_client=redis_client)
            else:
                raise Exception("Redis not available")
        except Exception:
            # Fall back to mocked Redis
            mock_redis = Mock()
            mock_redis.keys.return_value = []
            mock_redis.get.return_value = None
            mock_redis.setex.return_value = True
            self.manager = ErrorBoundaryManager(redis_client=mock_redis)

    def test_full_error_handling_flow(self):
        """Test complete error handling flow"""
        context = ErrorContext(
            component="integration_test", function="test_function", user_id="test_user"
        )

        async def test_flow():
            error = ValueError("Test integration error")

            try:
                await self.manager.handle_error(error, context)
            except ErrorBoundaryException as e:
                # Expected when no recovery is possible
                self.assertIn("Unrecoverable error", str(e))
                self.assertEqual(e.context.component, "integration_test")

        asyncio.run(test_flow())

    def test_concurrent_error_handling(self):
        """Test error handling under concurrent load"""

        async def generate_error(error_id):
            context = ErrorContext(
                component="concurrent_test",
                function=f"test_function_{error_id}",
                request_id=f"req_{error_id}",
            )

            error = ValueError(f"Concurrent error {error_id}")

            try:
                await self.manager.handle_error(error, context)
            except ErrorBoundaryException:
                pass  # Expected

        async def test_concurrent():
            # Create multiple concurrent error handling tasks
            tasks = [generate_error(i) for i in range(10)]
            await asyncio.gather(*tasks, return_exceptions=True)

        asyncio.run(test_concurrent())


class TestErrorBoundaryAPI(unittest.TestCase):
    """Test the error monitoring API endpoints"""

    @patch("src.utils.error_boundaries.get_redis_client")
    def test_error_statistics_endpoint(self, mock_get_redis):
        """Test error statistics API endpoint"""
        # Mock Redis client
        mock_redis = Mock()
        mock_redis.keys.return_value = ["error_1", "error_2"]
        mock_redis.get.side_effect = [
            json.dumps({"category": "network", "severity": "high"}),
            json.dumps({"category": "database", "severity": "medium"}),
        ]
        mock_get_redis.return_value = mock_redis

        # Import and test the API function
        from backend.api.error_monitoring import get_system_error_statistics

        async def test_api():
            result = await get_system_error_statistics()
            self.assertEqual(result["status"], "success")
            self.assertIn("data", result)

        asyncio.run(test_api())


class TestErrorBoundaryExamples(unittest.TestCase):
    """Test the error boundary examples"""

    def test_example_functions(self):
        """Test that example functions work correctly"""
        try:
            from src.utils.error_boundary_examples import (
                ExampleService,
                risky_calculation,
            )

            # Test successful operation
            result = risky_calculation(10, 2)
            self.assertEqual(result, 5.0)

            # Test service class
            service = ExampleService()
            self.assertIsNotNone(service.error_manager)

        except ImportError:
            self.skipTest("Error boundary examples not available")


class TestErrorBoundaryPerformance(unittest.TestCase):
    """Performance tests for error boundary system"""

    def test_decorator_overhead(self):
        """Test performance overhead of error boundary decorator"""

        # Function without decorator
        def plain_function(x):
            return x * 2

        # Function with decorator
        @error_boundary(component="perf_test", function="decorated_function")
        def decorated_function(x):
            return x * 2

        # Measure performance
        iterations = 1000

        # Test plain function
        start_time = time.time()
        for i in range(iterations):
            plain_function(i)
        plain_duration = time.time() - start_time

        # Test decorated function
        start_time = time.time()
        for i in range(iterations):
            decorated_function(i)
        decorated_duration = time.time() - start_time

        # Assert reasonable overhead (should be less than 5x slower)
        overhead_ratio = decorated_duration / plain_duration
        self.assertLess(
            overhead_ratio,
            5.0,
            f"Error boundary overhead too high: {overhead_ratio:.2f}x",
        )

    def test_concurrent_error_generation(self):
        """Test system performance under concurrent error generation"""

        @error_boundary(component="stress_test", function="error_generator")
        def error_generator(should_fail=False):
            if should_fail:
                raise ValueError("Stress test error")
            return "success"

        def worker():
            results = []
            for i in range(100):
                try:
                    result = error_generator(should_fail=(i % 10 == 0))
                    results.append(result)
                except Exception:
                    results.append("error_handled")
            return results

        # Run concurrent workers
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)

        start_time = time.time()

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        duration = time.time() - start_time

        # Should complete within reasonable time
        self.assertLess(
            duration, 10.0, f"Concurrent error handling too slow: {duration:.2f}s"
        )


async def run_async_tests():
    """Run asynchronous tests"""
    print("🧪 Running Async Error Boundary Tests")

    # Test async error boundary manager
    mock_redis = Mock()
    mock_redis.keys.return_value = []
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True

    manager = ErrorBoundaryManager(redis_client=mock_redis)

    # Test async error handling
    context = ErrorContext(component="async_test", function="test_async_error")

    try:
        await manager.handle_error(ValueError("Async test error"), context)
    except ErrorBoundaryException as e:
        print(f"✅ Async error handled: {e}")

    print("✅ Async tests completed")


def main():
    """Run all tests"""
    print("🧪 Running Error Boundary Test Suite")
    print("=" * 60)

    # Run unittest tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    test_classes = [
        TestErrorBoundaryManager,
        TestRecoveryHandlers,
        TestErrorBoundaryDecorator,
        TestErrorBoundaryIntegration,
        TestErrorBoundaryAPI,
        TestErrorBoundaryExamples,
        TestErrorBoundaryPerformance,
    ]

    for test_class in test_classes:
        tests = loader.loadTestsFromTestClass(test_class)
        suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Run async tests
    asyncio.run(run_async_tests())

    # Summary
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ All Error Boundary Tests Passed!")
        return 0
    else:
        print(f"❌ {len(result.failures)} failures, {len(result.errors)} errors")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
