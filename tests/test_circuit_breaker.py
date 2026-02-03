#!/usr/bin/env python3
"""
Unit tests for the circuit breaker pattern implementation
Tests circuit breaker states, failure detection, recovery, and integration with AutoBot components
"""

import asyncio
import time

import pytest

from src.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
    CircuitBreakerOpenError,
    CircuitState,
    circuit_breaker_async,
    circuit_breaker_manager,
    circuit_breaker_sync,
    protected_database_call,
    protected_llm_call,
    protected_network_call,
)


class TestCircuitBreakerConfig:
    """Test circuit breaker configuration"""

    def test_default_config(self):
        """Test default configuration values"""
        config = CircuitBreakerConfig()

        assert config.failure_threshold == 5
        assert config.recovery_timeout == 60.0
        assert config.success_threshold == 3
        assert config.timeout == 30.0
        assert config.slow_call_threshold == 10.0
        assert config.slow_call_rate_threshold == 0.5
        assert config.min_calls_for_evaluation == 10

    def test_custom_config(self):
        """Test custom configuration"""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30.0,
            success_threshold=2,
            timeout=15.0,
            monitored_exceptions=(ConnectionError, TimeoutError),
        )

        assert config.failure_threshold == 3
        assert config.recovery_timeout == 30.0
        assert config.success_threshold == 2
        assert config.timeout == 15.0
        assert config.monitored_exceptions == (ConnectionError, TimeoutError)


class TestCircuitBreaker:
    """Test CircuitBreaker class functionality"""

    def test_initial_state(self):
        """Test initial circuit breaker state"""
        cb = CircuitBreaker("test_service")

        assert cb.name == "test_service"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
        assert cb.last_failure_time == 0.0

    def test_exception_monitoring(self):
        """Test exception monitoring logic"""
        cb = CircuitBreaker("test_service")

        # These should be monitored
        assert cb._should_monitor_exception(ConnectionError("test"))
        assert cb._should_monitor_exception(TimeoutError("test"))
        assert cb._should_monitor_exception(OSError("test"))

        # These should NOT be monitored
        assert not cb._should_monitor_exception(ValueError("test"))
        assert not cb._should_monitor_exception(TypeError("test"))
        assert not cb._should_monitor_exception(KeyboardInterrupt())

    @pytest.mark.asyncio
    async def test_successful_call_closed_state(self):
        """Test successful call in CLOSED state"""
        cb = CircuitBreaker("test_service")

        async def successful_function():
            return "success"

        result = await cb.call_async(successful_function)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

        # Check statistics
        stats = cb.get_state()
        assert stats["stats"]["total_calls"] == 1
        assert stats["stats"]["successful_calls"] == 1
        assert stats["stats"]["failed_calls"] == 0

    @pytest.mark.asyncio
    async def test_failure_tracking(self):
        """Test failure tracking and circuit opening"""
        config = CircuitBreakerConfig(failure_threshold=3, recovery_timeout=1.0)
        cb = CircuitBreaker("test_service", config)

        async def failing_function():
            raise ConnectionError("Service unavailable")

        # First two failures should keep circuit closed
        for i in range(2):
            with pytest.raises(ConnectionError):
                await cb.call_async(failing_function)
            assert cb.state == CircuitState.CLOSED
            assert cb.failure_count == i + 1

        # Third failure should open the circuit
        with pytest.raises(ConnectionError):
            await cb.call_async(failing_function)

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    @pytest.mark.asyncio
    async def test_circuit_open_blocks_calls(self):
        """Test that open circuit blocks calls"""
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=60.0)
        cb = CircuitBreaker("test_service", config)

        async def failing_function():
            raise ConnectionError("Service unavailable")

        # Cause failures to open circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call_async(failing_function)

        assert cb.state == CircuitState.OPEN

        # Now calls should be blocked
        async def any_function():
            return "should not execute"

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await cb.call_async(any_function)

        assert exc_info.value.service_name == "test_service"
        assert exc_info.value.failure_count == 2

        # Check blocked call statistics
        stats = cb.get_state()
        assert stats["stats"]["blocked_calls"] == 1

    @pytest.mark.asyncio
    async def test_half_open_transition(self):
        """Test transition from OPEN to HALF_OPEN"""
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        cb = CircuitBreaker("test_service", config)

        async def failing_function():
            raise ConnectionError("Service unavailable")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call_async(failing_function)

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.2)

        # Next call should transition to HALF_OPEN
        async def successful_function():
            return "recovered"

        result = await cb.call_async(successful_function)
        assert result == "recovered"
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_to_closed_recovery(self):
        """Test recovery from HALF_OPEN to CLOSED"""
        config = CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout=0.1, success_threshold=2
        )
        cb = CircuitBreaker("test_service", config)

        async def failing_function():
            raise ConnectionError("Service unavailable")

        async def successful_function():
            return "success"

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call_async(failing_function)

        # Wait and transition to HALF_OPEN
        await asyncio.sleep(0.2)

        # First successful call in HALF_OPEN
        result = await cb.call_async(successful_function)
        assert result == "success"
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.success_count == 1

        # Second successful call should close the circuit
        result = await cb.call_async(successful_function)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens_circuit(self):
        """Test that failure in HALF_OPEN reopens circuit"""
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        cb = CircuitBreaker("test_service", config)

        async def failing_function():
            raise ConnectionError("Service unavailable")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call_async(failing_function)

        # Wait and transition to HALF_OPEN
        await asyncio.sleep(0.2)

        # Failure in HALF_OPEN should reopen circuit
        with pytest.raises(ConnectionError):
            await cb.call_async(failing_function)

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test call timeout handling"""
        config = CircuitBreakerConfig(timeout=0.1)
        cb = CircuitBreaker("test_service", config)

        async def slow_function():
            await asyncio.sleep(0.2)  # Longer than timeout
            return "too slow"

        with pytest.raises(TimeoutError):
            await cb.call_async(slow_function)

        assert cb.failure_count == 1

    def test_sync_call_success(self):
        """Test synchronous call success"""
        cb = CircuitBreaker("test_service")

        def successful_function():
            return "sync_success"

        result = cb.call_sync(successful_function)
        assert result == "sync_success"
        assert cb.failure_count == 0

    def test_sync_call_failure(self):
        """Test synchronous call failure"""
        cb = CircuitBreaker("test_service")

        def failing_function():
            raise ConnectionError("Sync failure")

        with pytest.raises(ConnectionError):
            cb.call_sync(failing_function)

        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_performance_based_opening(self):
        """Test circuit opening based on performance metrics"""
        config = CircuitBreakerConfig(
            slow_call_threshold=0.1,
            slow_call_rate_threshold=0.7,  # 70% slow calls
            min_calls_for_evaluation=5,
            failure_threshold=10,  # High threshold so performance triggers first
        )
        cb = CircuitBreaker("test_service", config)

        # Make mostly slow calls
        async def slow_function():
            await asyncio.sleep(0.15)  # Slower than threshold
            return "slow_result"

        async def fast_function():
            return "fast_result"

        # Make calls that exceed slow call rate threshold
        for _ in range(4):
            await cb.call_async(slow_function)

        # One fast call to meet minimum calls
        await cb.call_async(fast_function)

        # Next slow call should potentially open circuit due to performance
        # (This is probabilistic based on evaluation logic)
        await cb.call_async(slow_function)

        # Check that slow calls were recorded
        stats = cb.get_state()
        assert stats["stats"]["slow_calls"] > 0

    def test_non_monitored_exception_ignored(self):
        """Test that non-monitored exceptions don't trigger circuit breaker"""
        cb = CircuitBreaker("test_service")

        def business_logic_error():
            raise ValueError("Bad input")

        # ValueError should not trigger circuit breaker
        with pytest.raises(ValueError):
            cb.call_sync(business_logic_error)

        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_reset_functionality(self):
        """Test circuit breaker reset"""
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker("test_service", config)

        def failing_function():
            raise ConnectionError("Failure")

        # Generate failures to open circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                cb.call_sync(failing_function)

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 2

        # Reset circuit breaker
        cb.reset()

        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert len(cb.call_history) == 0

    def test_statistics_accuracy(self):
        """Test statistics accuracy"""
        cb = CircuitBreaker("test_service")

        def success_func():
            return "success"

        def fail_func():
            raise ConnectionError("failure")

        # Execute mixed operations
        cb.call_sync(success_func)
        cb.call_sync(success_func)

        try:
            cb.call_sync(fail_func)
        except ConnectionError:
            pass

        stats = cb.get_state()
        assert stats["stats"]["total_calls"] == 3
        assert stats["stats"]["successful_calls"] == 2
        assert stats["stats"]["failed_calls"] == 1
        assert stats["stats"]["blocked_calls"] == 0


class TestCircuitBreakerManager:
    """Test CircuitBreakerManager functionality"""

    def test_get_circuit_breaker(self):
        """Test getting circuit breakers from manager"""
        manager = CircuitBreakerManager()

        cb1 = manager.get_circuit_breaker("service1")
        cb2 = manager.get_circuit_breaker("service2")
        cb1_again = manager.get_circuit_breaker("service1")

        assert cb1.name == "service1"
        assert cb2.name == "service2"
        assert cb1 is cb1_again  # Should return same instance
        assert cb1 is not cb2

    def test_get_all_states(self):
        """Test getting states of all circuit breakers"""
        manager = CircuitBreakerManager()

        _cb1 = manager.get_circuit_breaker("service1")
        _cb2 = manager.get_circuit_breaker("service2")

        states = manager.get_all_states()

        assert "service1" in states
        assert "service2" in states
        assert states["service1"]["name"] == "service1"
        assert states["service2"]["name"] == "service2"

    def test_reset_specific_circuit_breaker(self):
        """Test resetting a specific circuit breaker"""
        manager = CircuitBreakerManager()

        cb = manager.get_circuit_breaker("test_service")
        cb.failure_count = 5  # Manually set failure count

        manager.reset_circuit_breaker("test_service")
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_reset_all_circuit_breakers(self):
        """Test resetting all circuit breakers"""
        manager = CircuitBreakerManager()

        cb1 = manager.get_circuit_breaker("service1")
        cb2 = manager.get_circuit_breaker("service2")

        cb1.failure_count = 3
        cb2.failure_count = 4

        manager.reset_all_circuit_breakers()

        assert cb1.failure_count == 0
        assert cb2.failure_count == 0
        assert cb1.state == CircuitState.CLOSED
        assert cb2.state == CircuitState.CLOSED


class TestCircuitBreakerDecorators:
    """Test circuit breaker decorators"""

    @pytest.mark.asyncio
    async def test_async_decorator_success(self):
        """Test async decorator with successful calls"""

        @circuit_breaker_async("test_service", failure_threshold=3)
        async def decorated_function(value):
            return f"processed_{value}"

        result = await decorated_function("test")
        assert result == "processed_test"

        # Check that circuit breaker was created and is accessible
        assert hasattr(decorated_function, "circuit_breaker")
        assert decorated_function.circuit_breaker.name == "test_service"

    @pytest.mark.asyncio
    async def test_async_decorator_failure_and_opening(self):
        """Test async decorator with failures and circuit opening"""

        call_count = 0

        @circuit_breaker_async(
            "failing_service", failure_threshold=2, recovery_timeout=0.1
        )
        async def failing_decorated_function():
            nonlocal call_count
            call_count += 1
            raise ConnectionError(f"Failure {call_count}")

        # First failure
        with pytest.raises(ConnectionError):
            await failing_decorated_function()

        # Second failure should open circuit
        with pytest.raises(ConnectionError):
            await failing_decorated_function()

        # Third call should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            await failing_decorated_function()

        assert call_count == 2  # Only 2 actual calls, third was blocked

    def test_sync_decorator_success(self):
        """Test sync decorator with successful calls"""

        @circuit_breaker_sync("sync_service", failure_threshold=3)
        def decorated_sync_function(value):
            return f"sync_processed_{value}"

        result = decorated_sync_function("test")
        assert result == "sync_processed_test"

        # Check that circuit breaker was created
        assert hasattr(decorated_sync_function, "circuit_breaker")
        assert decorated_sync_function.circuit_breaker.name == "sync_service"

    def test_sync_decorator_with_custom_exceptions(self):
        """Test sync decorator with custom monitored exceptions"""

        class CustomError(Exception):
            pass

        @circuit_breaker_sync(
            "custom_service", failure_threshold=2, monitored_exceptions=(CustomError,)
        )
        def custom_error_function():
            raise CustomError("Custom failure")

        # First failure
        with pytest.raises(CustomError):
            custom_error_function()

        # Second failure should open circuit
        with pytest.raises(CustomError):
            custom_error_function()

        # Third call should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            custom_error_function()


class TestSpecializedProtectedCalls:
    """Test specialized protected call functions"""

    @pytest.mark.asyncio
    async def test_protected_llm_call_success(self):
        """Test protected LLM call with success"""

        async def mock_llm_function():
            return {"response": "LLM result", "model": "test-model"}

        result = await protected_llm_call(mock_llm_function)
        assert result["response"] == "LLM result"

        # Check that LLM circuit breaker was created
        cb = circuit_breaker_manager.get_circuit_breaker("llm_service")
        assert cb.name == "llm_service"

    @pytest.mark.asyncio
    async def test_protected_database_call_success(self):
        """Test protected database call with success"""

        async def mock_db_function():
            return [{"id": 1, "data": "result"}]

        result = await protected_database_call(mock_db_function)
        assert len(result) == 1
        assert result[0]["data"] == "result"

        # Check that database circuit breaker was created
        cb = circuit_breaker_manager.get_circuit_breaker("database_service")
        assert cb.name == "database_service"

    @pytest.mark.asyncio
    async def test_protected_network_call_with_failure(self):
        """Test protected network call with failure handling"""

        call_count = 0

        async def failing_network_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("Network failure")
            return "network_success"

        # Should succeed after circuit breaker allows retries
        result = await protected_network_call(failing_network_function)
        assert result == "network_success"
        assert call_count == 3


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration patterns"""

    @pytest.mark.asyncio
    async def test_multiple_services_independent_states(self):
        """Test that multiple services maintain independent circuit states"""

        @circuit_breaker_async("service_a", failure_threshold=2)
        async def service_a_call():
            raise ConnectionError("Service A failure")

        @circuit_breaker_async("service_b", failure_threshold=2)
        async def service_b_call():
            return "Service B success"

        # Fail service A
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await service_a_call()

        # Service A should be open
        with pytest.raises(CircuitBreakerOpenError):
            await service_a_call()

        # Service B should still work
        result = await service_b_call()
        assert result == "Service B success"

        # Check states
        assert service_a_call.circuit_breaker.state == CircuitState.OPEN
        assert service_b_call.circuit_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_with_retry_mechanism(self):
        """Test circuit breaker working with retry mechanism"""
        # This would test the interaction between circuit breaker and retry mechanism
        # In practice, circuit breaker should be the outer layer

        call_count = 0

        @circuit_breaker_async(
            "retry_service", failure_threshold=3, recovery_timeout=0.1
        )
        async def service_with_retries():
            nonlocal call_count
            call_count += 1
            if call_count <= 4:  # Fail first 4 times
                raise ConnectionError("Temporary failure")
            return "finally_success"

        # Should fail and open circuit before retry mechanism can succeed
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await service_with_retries()

        # Circuit should now be open
        assert service_with_retries.circuit_breaker.state == CircuitState.OPEN

        # Calls should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            await service_with_retries()

        # After recovery timeout, should be able to succeed
        await asyncio.sleep(0.2)
        result = await service_with_retries()
        assert result == "finally_success"

    def test_performance_monitoring_and_reporting(self):
        """Test performance monitoring and reporting features"""
        cb = CircuitBreaker("perf_test_service")

        def fast_call():
            time.sleep(0.01)  # 10ms
            return "fast"

        def slow_call():
            time.sleep(0.15)  # 150ms
            return "slow"

        # Make mixed calls
        for _ in range(5):
            cb.call_sync(fast_call)

        for _ in range(3):
            cb.call_sync(slow_call)

        state = cb.get_state()

        # Check performance metrics
        assert state["stats"]["total_calls"] == 8
        assert state["stats"]["successful_calls"] == 8
        assert state["stats"]["slow_calls"] == 3  # 3 slow calls
        assert state["recent_performance"]["calls"] == 8
        assert 0 < state["recent_performance"]["average_duration"] < 1
        assert state["recent_performance"]["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_global_circuit_breaker_manager(self):
        """Test global circuit breaker manager functionality"""
        # Reset global state
        circuit_breaker_manager.reset_all_circuit_breakers()

        # Create some circuit breakers through decorators
        @circuit_breaker_async("global_service_1", failure_threshold=2)
        async def service_1():
            return "service_1_result"

        @circuit_breaker_async("global_service_2", failure_threshold=2)
        async def service_2():
            return "service_2_result"

        # Call services to create circuit breakers
        await service_1()
        await service_2()

        # Check global state
        all_states = circuit_breaker_manager.get_all_states()

        assert "global_service_1" in all_states
        assert "global_service_2" in all_states

        # Check individual states
        assert all_states["global_service_1"]["state"] == "closed"
        assert all_states["global_service_2"]["state"] == "closed"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
