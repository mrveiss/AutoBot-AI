#!/usr/bin/env python3
"""
Unit tests for the retry mechanism
Tests various retry strategies, exception handling, and integration with AutoBot components
"""

import time

import pytest
from src.retry_mechanism import (
    RetryConfig,
    RetryExhaustedError,
    RetryMechanism,
    RetryStrategy,
    retry_async,
    retry_database_operation,
    retry_file_operation,
    retry_network_operation,
    retry_sync,
)


class TestRetryMechanism:
    """Test RetryMechanism class functionality"""

    def test_retry_config_defaults(self):
        """Test default retry configuration"""
        config = RetryConfig()

        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_multiplier == 2.0
        assert config.jitter is True
        assert config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF

    def test_delay_calculation_exponential(self):
        """Test exponential backoff delay calculation"""
        config = RetryConfig(
            base_delay=1.0,
            backoff_multiplier=2.0,
            jitter=False,  # Disable for predictable testing
        )

        retry_mechanism = RetryMechanism(config)

        assert retry_mechanism.calculate_delay(1) == 1.0  # 1.0 * 2^0
        assert retry_mechanism.calculate_delay(2) == 2.0  # 1.0 * 2^1
        assert retry_mechanism.calculate_delay(3) == 4.0  # 1.0 * 2^2
        assert retry_mechanism.calculate_delay(4) == 8.0  # 1.0 * 2^3

    def test_delay_calculation_linear(self):
        """Test linear backoff delay calculation"""
        config = RetryConfig(
            base_delay=0.5, strategy=RetryStrategy.LINEAR_BACKOFF, jitter=False
        )

        retry_mechanism = RetryMechanism(config)

        assert retry_mechanism.calculate_delay(1) == 0.5  # 0.5 * 1
        assert retry_mechanism.calculate_delay(2) == 1.0  # 0.5 * 2
        assert retry_mechanism.calculate_delay(3) == 1.5  # 0.5 * 3

    def test_delay_calculation_fixed(self):
        """Test fixed delay calculation"""
        config = RetryConfig(
            base_delay=2.0, strategy=RetryStrategy.FIXED_DELAY, jitter=False
        )

        retry_mechanism = RetryMechanism(config)

        assert retry_mechanism.calculate_delay(1) == 2.0
        assert retry_mechanism.calculate_delay(2) == 2.0
        assert retry_mechanism.calculate_delay(3) == 2.0

    def test_delay_max_limit(self):
        """Test that delays don't exceed maximum"""
        config = RetryConfig(
            base_delay=1.0, max_delay=5.0, backoff_multiplier=3.0, jitter=False
        )

        retry_mechanism = RetryMechanism(config)

        # Should cap at max_delay
        assert retry_mechanism.calculate_delay(5) == 5.0  # Would be 81.0 without cap

    def test_jitter_adds_randomness(self):
        """Test that jitter adds randomness to delays"""
        config = RetryConfig(
            base_delay=1.0, jitter=True, strategy=RetryStrategy.FIXED_DELAY
        )

        retry_mechanism = RetryMechanism(config)

        # Generate multiple delays and verify they're different
        delays = [retry_mechanism.calculate_delay(1) for _ in range(10)]

        # Not all delays should be identical (jitter should add variance)
        assert len(set(delays)) > 1

        # All delays should be reasonably close to base_delay
        for delay in delays:
            assert 0.8 <= delay <= 1.2  # ±20% jitter

    def test_retryable_exception_detection(self):
        """Test detection of retryable vs non-retryable exceptions"""
        retry_mechanism = RetryMechanism()

        # These should be retryable
        assert retry_mechanism.is_retryable_exception(ConnectionError("test"))
        assert retry_mechanism.is_retryable_exception(TimeoutError("test"))
        assert retry_mechanism.is_retryable_exception(OSError("test"))

        # These should NOT be retryable
        assert not retry_mechanism.is_retryable_exception(KeyboardInterrupt())
        assert not retry_mechanism.is_retryable_exception(SystemExit())
        assert not retry_mechanism.is_retryable_exception(ValueError("test"))
        assert not retry_mechanism.is_retryable_exception(TypeError("test"))

    @pytest.mark.asyncio
    async def test_successful_execution_first_attempt(self):
        """Test successful execution on first attempt"""
        retry_mechanism = RetryMechanism()

        async def successful_func():
            return "success"

        result = await retry_mechanism.execute_async(successful_func)
        assert result == "success"

        # Should have one attempt
        stats = retry_mechanism.get_stats()
        assert stats["total_attempts"] == 1
        assert stats["successful_retries"] == 0
        assert stats["failed_operations"] == 0

    @pytest.mark.asyncio
    async def test_successful_execution_after_retries(self):
        """Test successful execution after retries"""
        retry_mechanism = RetryMechanism(RetryConfig(max_attempts=3, base_delay=0.01))

        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        result = await retry_mechanism.execute_async(
            flaky_func, operation_name="flaky_operation"
        )
        assert result == "success"
        assert call_count == 3

        # Should have successful retry
        stats = retry_mechanism.get_stats()
        assert stats["total_attempts"] == 3
        assert stats["successful_retries"] == 1
        assert stats["failed_operations"] == 0

    @pytest.mark.asyncio
    async def test_retry_exhausted_failure(self):
        """Test failure after all retry attempts exhausted"""
        retry_mechanism = RetryMechanism(RetryConfig(max_attempts=2, base_delay=0.01))

        async def always_fail():
            raise ConnectionError("Always fails")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await retry_mechanism.execute_async(
                always_fail, operation_name="always_fail"
            )

        assert exc_info.value.attempts == 2
        assert isinstance(exc_info.value.last_exception, ConnectionError)

        # Should have failed operation
        stats = retry_mechanism.get_stats()
        assert stats["total_attempts"] == 2
        assert stats["successful_retries"] == 0
        assert stats["failed_operations"] == 1

    @pytest.mark.asyncio
    async def test_non_retryable_exception_immediate_failure(self):
        """Test immediate failure for non-retryable exceptions"""
        retry_mechanism = RetryMechanism(RetryConfig(max_attempts=3))

        async def non_retryable_fail():
            raise ValueError("Bad input")

        # Should raise immediately, not retry
        with pytest.raises(ValueError):
            await retry_mechanism.execute_async(non_retryable_fail)

        # Should have only one attempt
        stats = retry_mechanism.get_stats()
        assert stats["total_attempts"] == 1

    def test_sync_execution_successful(self):
        """Test synchronous execution with retry mechanism"""
        retry_mechanism = RetryMechanism(RetryConfig(max_attempts=3, base_delay=0.01))

        call_count = 0

        def flaky_sync_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Temporary failure")
            return "sync_success"

        result = retry_mechanism.execute_sync(
            flaky_sync_func, operation_name="sync_operation"
        )
        assert result == "sync_success"
        assert call_count == 2

        stats = retry_mechanism.get_stats()
        assert stats["successful_retries"] == 1

    def test_sync_execution_failure(self):
        """Test synchronous execution failure after retries"""
        retry_mechanism = RetryMechanism(RetryConfig(max_attempts=2, base_delay=0.01))

        def always_fail_sync():
            raise TimeoutError("Always times out")

        with pytest.raises(RetryExhaustedError):
            retry_mechanism.execute_sync(always_fail_sync)

    def test_operation_statistics(self):
        """Test operation statistics tracking"""
        retry_mechanism = RetryMechanism(RetryConfig(max_attempts=3, base_delay=0.01))

        def successful_op():
            return "ok"

        def retry_needed_op():
            retry_needed_op.calls = getattr(retry_needed_op, "calls", 0) + 1
            if retry_needed_op.calls == 1:
                raise ConnectionError("First attempt fails")
            return "ok_after_retry"

        # Execute operations
        retry_mechanism.execute_sync(successful_op, operation_name="success_op")
        retry_mechanism.execute_sync(retry_needed_op, operation_name="retry_op")

        stats = retry_mechanism.get_stats()

        # Check per-operation stats
        success_stats = stats["operations_by_type"]["success_op"]
        assert success_stats["total"] == 1
        assert success_stats["succeeded"] == 1
        assert success_stats["retries_needed"] == 0

        retry_stats = stats["operations_by_type"]["retry_op"]
        assert retry_stats["total"] == 1
        assert retry_stats["succeeded"] == 1
        assert retry_stats["retries_needed"] == 1


class TestRetryDecorators:
    """Test retry decorators"""

    @pytest.mark.asyncio
    async def test_async_decorator_success(self):
        """Test async retry decorator with successful execution"""

        call_count = 0

        @retry_async(max_attempts=3, base_delay=0.01)
        async def decorated_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("First attempt fails")
            return "decorated_success"

        result = await decorated_func()
        assert result == "decorated_success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_decorator_failure(self):
        """Test async retry decorator with failure"""

        @retry_async(max_attempts=2, base_delay=0.01)
        async def always_fail_decorated():
            raise TimeoutError("Always fails")

        with pytest.raises(RetryExhaustedError):
            await always_fail_decorated()

    def test_sync_decorator_success(self):
        """Test sync retry decorator with successful execution"""

        call_count = 0

        @retry_sync(max_attempts=3, base_delay=0.01)
        def decorated_sync_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Needs retries")
            return "sync_decorated_success"

        result = decorated_sync_func()
        assert result == "sync_decorated_success"
        assert call_count == 3

    def test_sync_decorator_custom_exceptions(self):
        """Test sync decorator with custom retryable exceptions"""

        class CustomError(Exception):
            pass

        @retry_sync(
            max_attempts=2, base_delay=0.01, retryable_exceptions=(CustomError,)
        )
        def custom_exception_func():
            raise CustomError("Should retry this")

        with pytest.raises(RetryExhaustedError):
            custom_exception_func()


class TestSpecializedRetryFunctions:
    """Test specialized retry functions for different use cases"""

    @pytest.mark.asyncio
    async def test_network_operation_retry(self):
        """Test network operation retry with appropriate configuration"""

        call_count = 0

        async def mock_network_call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "network_success"

        result = await retry_network_operation(mock_network_call)
        assert result == "network_success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_database_operation_retry(self):
        """Test database operation retry with database-specific configuration"""
        import sqlite3

        call_count = 0

        async def mock_db_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise sqlite3.OperationalError("Database locked")
            return "db_success"

        result = await retry_database_operation(mock_db_operation)
        assert result == "db_success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_file_operation_retry(self):
        """Test file operation retry with file-specific configuration"""

        call_count = 0

        async def mock_file_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("Temporary file system error")
            return "file_success"

        result = await retry_file_operation(mock_file_operation)
        assert result == "file_success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_file_operation_non_retryable(self):
        """Test file operation with non-retryable exception"""

        async def file_not_found_operation():
            raise FileNotFoundError("File doesn't exist")

        # Should not retry FileNotFoundError
        with pytest.raises(FileNotFoundError):
            await retry_file_operation(file_not_found_operation)


class TestRetryMechanismIntegration:
    """Test integration with AutoBot components"""

    @pytest.mark.asyncio
    async def test_llm_interface_integration(self):
        """Test retry integration with LLM interface"""

        # This would test actual integration, but we'll mock it
        call_count = 0

        async def mock_llm_call():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("API temporarily unavailable")
            return {"choices": [{"message": {"content": "LLM response"}}]}

        result = await retry_network_operation(mock_llm_call)
        assert result["choices"][0]["message"]["content"] == "LLM response"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_knowledge_base_integration(self):
        """Test retry integration with knowledge base operations"""

        call_count = 0

        async def mock_kb_search():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Vector store temporarily unavailable")
            return [{"content": "KB result", "score": 0.95}]

        result = await retry_database_operation(mock_kb_search)
        assert len(result) == 1
        assert result[0]["content"] == "KB result"
        assert call_count == 2

    def test_performance_under_load(self):
        """Test retry mechanism performance under load"""
        retry_mechanism = RetryMechanism(
            RetryConfig(
                max_attempts=2,
                base_delay=0.001,  # Very fast for performance test
                jitter=False,
            )
        )

        def fast_operation():
            return "fast_result"

        # Measure time for many operations
        start_time = time.time()

        for _ in range(100):
            result = retry_mechanism.execute_sync(fast_operation)
            assert result == "fast_result"

        end_time = time.time()
        duration = end_time - start_time

        # Should be fast (less than 1 second for 100 operations)
        assert duration < 1.0

        # All operations should succeed
        stats = retry_mechanism.get_stats()
        assert stats["failed_operations"] == 0
        assert stats["total_attempts"] == 100

    def test_stats_accuracy(self):
        """Test statistics accuracy across multiple operations"""
        retry_mechanism = RetryMechanism(RetryConfig(max_attempts=3, base_delay=0.01))

        # Mix of operations
        def success_op():
            return "success"

        def retry_once_op():
            if not hasattr(retry_once_op, "called"):
                retry_once_op.called = True
                raise ConnectionError("Fail once")
            return "success_after_retry"

        def always_fail_op():
            raise TimeoutError("Always fails")

        # Execute operations
        retry_mechanism.execute_sync(success_op, operation_name="success")
        retry_mechanism.execute_sync(retry_once_op, operation_name="retry_once")

        try:
            retry_mechanism.execute_sync(always_fail_op, operation_name="always_fail")
        except RetryExhaustedError:
            pass  # Expected

        stats = retry_mechanism.get_stats()

        # Verify overall stats
        assert stats["total_attempts"] == 6  # 1 + 2 + 3
        assert stats["successful_retries"] == 1  # retry_once_op
        assert stats["failed_operations"] == 1  # always_fail_op
        assert 80 <= stats["success_rate"] <= 90  # Approximately 83.3%

        # Verify per-operation stats
        success_stats = stats["operations_by_type"]["success"]
        assert success_stats["total"] == 1
        assert success_stats["succeeded"] == 1
        assert success_stats["retries_needed"] == 0

        retry_stats = stats["operations_by_type"]["retry_once"]
        assert retry_stats["total"] == 1
        assert retry_stats["succeeded"] == 1
        assert retry_stats["retries_needed"] == 1

        fail_stats = stats["operations_by_type"]["always_fail"]
        assert fail_stats["total"] == 1
        assert fail_stats["succeeded"] == 0

    def test_reset_stats(self):
        """Test statistics reset functionality"""
        retry_mechanism = RetryMechanism(RetryConfig(base_delay=0.01))

        # Execute some operations
        retry_mechanism.execute_sync(lambda: "test", operation_name="test_op")

        # Verify stats exist
        stats = retry_mechanism.get_stats()
        assert stats["total_attempts"] > 0

        # Reset and verify
        retry_mechanism.reset_stats()
        stats = retry_mechanism.get_stats()
        assert stats["total_attempts"] == 0
        assert stats["successful_retries"] == 0
        assert stats["failed_operations"] == 0
        assert len(stats["operations_by_type"]) == 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
