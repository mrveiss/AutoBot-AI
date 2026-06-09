# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Circuit Breaker Manager

Issue #4342: Circuit breaker prevents cascading failures.
Tests detect timeouts, connection errors, rate limits.
"""

import asyncio
import time

import pytest

from services.resilience.circuit_breaker_manager import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    CircuitBreakerTimeout,
)


class TestCircuitBreaker:
    """Test suite for circuit breaker."""

    def test_closed_state_allows_calls(self):
        """Test that circuit breaker in CLOSED state allows calls."""
        breaker = CircuitBreaker("redis", CircuitBreakerConfig(failure_threshold=3))
        result = breaker.call(lambda: "success")
        assert result == "success"
        assert breaker.stats.successful_calls == 1

    def test_circuit_opens_after_threshold(self):
        """Test that circuit opens after failure threshold reached."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker("api", config)

        # First failure
        with pytest.raises(ZeroDivisionError):
            breaker.call(lambda: 1 / 0)

        # Second failure - circuit should open
        with pytest.raises(ZeroDivisionError):
            breaker.call(lambda: 1 / 0)

        # Circuit should now be open
        assert breaker.state == CircuitBreakerState.OPEN

    def test_open_circuit_rejects_calls(self):
        """Test that open circuit rejects calls immediately."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("api", config)

        # Open the circuit
        with pytest.raises(ZeroDivisionError):
            breaker.call(lambda: 1 / 0)

        # Circuit is open, next call should be rejected
        with pytest.raises(CircuitBreakerOpenError):
            breaker.call(lambda: "success")

        assert breaker.stats.blocked_calls == 1

    def test_half_open_state_tests_recovery(self):
        """Test that circuit attempts recovery in HALF_OPEN state."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.1, success_threshold=1)
        breaker = CircuitBreaker("api", config)

        # Open circuit
        with pytest.raises(ZeroDivisionError):
            breaker.call(lambda: 1 / 0)

        assert breaker.state == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        time.sleep(0.2)

        # Should be in HALF_OPEN, allow test call
        result = breaker.call(lambda: "recovered")
        assert result == "recovered"
        assert breaker.state == CircuitBreakerState.CLOSED

    def test_half_open_returns_to_open_on_failure(self):
        """Test that HALF_OPEN returns to OPEN if recovery fails."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.1, success_threshold=1)
        breaker = CircuitBreaker("api", config)

        # Open circuit
        with pytest.raises(ZeroDivisionError):
            breaker.call(lambda: 1 / 0)

        # Wait for recovery timeout
        time.sleep(0.2)

        # Test call fails
        with pytest.raises(ZeroDivisionError):
            breaker.call(lambda: 1 / 0)

        assert breaker.state == CircuitBreakerState.OPEN

    def test_circuit_tracks_statistics(self):
        """Test that circuit breaker tracks call statistics."""
        breaker = CircuitBreaker("redis", CircuitBreakerConfig(failure_threshold=5))

        # Successful calls
        for _ in range(3):
            breaker.call(lambda: "success")

        # Failed call
        with pytest.raises(ZeroDivisionError):
            breaker.call(lambda: 1 / 0)

        assert breaker.stats.total_calls == 4
        assert breaker.stats.successful_calls == 3
        assert breaker.stats.failed_calls == 1

    @pytest.mark.asyncio
    async def test_async_call_success(self):
        """Test successful async call."""
        breaker = CircuitBreaker("api", CircuitBreakerConfig())

        async def async_task():
            await asyncio.sleep(0.01)
            return "async_success"

        result = await breaker.call_async(async_task)
        assert result == "async_success"

    @pytest.mark.asyncio
    async def test_async_call_timeout(self):
        """Test async call timeout."""
        config = CircuitBreakerConfig(timeout=0.01)
        breaker = CircuitBreaker("api", config)

        async def slow_task():
            await asyncio.sleep(1.0)
            return "slow"

        with pytest.raises(CircuitBreakerTimeout):
            await breaker.call_async(slow_task)

    @pytest.mark.asyncio
    async def test_async_open_circuit_rejects(self):
        """Test that open circuit rejects async calls."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("api", config)

        async def failing_task():
            raise RuntimeError("Task failed")

        # Open circuit
        with pytest.raises(RuntimeError):
            await breaker.call_async(failing_task)

        # Open circuit should reject
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call_async(failing_task)


class TestCircuitBreakerManager:
    """Test suite for circuit breaker manager."""

    def test_manager_creates_breaker_on_demand(self):
        """Test that manager creates breaker on first access."""
        manager = CircuitBreakerManager()
        breaker1 = manager.get_breaker("redis")
        breaker2 = manager.get_breaker("redis")

        assert breaker1 is breaker2
        assert breaker1.name == "redis"

    def test_manager_tracks_multiple_breakers(self):
        """Test that manager tracks multiple service breakers."""
        manager = CircuitBreakerManager()

        manager.get_breaker("redis")
        manager.get_breaker("chromadb")
        manager.get_breaker("external_api")

        status = manager.get_status()
        assert "redis" in status
        assert "chromadb" in status
        assert "external_api" in status

    def test_manager_reset_breaker(self):
        """Test that manager can reset breaker."""
        manager = CircuitBreakerManager()
        breaker = manager.get_breaker("redis")

        # Open circuit
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker.config = config
        with pytest.raises(ValueError):
            breaker.call(lambda: 1 / 0)

        assert breaker.state == CircuitBreakerState.OPEN

        # Reset
        manager.reset_breaker("redis")
        assert breaker.state == CircuitBreakerState.CLOSED

    def test_manager_status_includes_metrics(self):
        """Test that manager status includes all metrics."""
        manager = CircuitBreakerManager()
        breaker = manager.get_breaker("api")

        # Make some calls
        breaker.call(lambda: "success")
        with pytest.raises(ValueError):
            breaker.call(lambda: 1 / 0)

        status = manager.get_status()
        assert status["api"]["total_calls"] == 2
        assert status["api"]["successful_calls"] == 1
        assert status["api"]["failed_calls"] == 1


class TestCircuitBreakerIntegration:
    """Integration tests with real scenarios."""

    def test_redis_failure_detection(self):
        """Test that circuit breaker detects Redis failures."""
        manager = CircuitBreakerManager()
        breaker = manager.get_breaker("redis")

        config = CircuitBreakerConfig(failure_threshold=2)
        breaker.config = config

        # Simulate connection errors
        with pytest.raises(ConnectionError):
            breaker.call(lambda: (_ for _ in ()).throw(ConnectionError("Redis down")))

        with pytest.raises(ConnectionError):
            breaker.call(lambda: (_ for _ in ()).throw(ConnectionError("Redis down")))

        # Circuit should be open
        assert breaker.state == CircuitBreakerState.OPEN

        # Next call should be rejected
        with pytest.raises(CircuitBreakerOpenError):
            breaker.call(lambda: "success")

    def test_chromadb_timeout_detection(self):
        """Test that circuit breaker detects ChromaDB timeouts."""
        manager = CircuitBreakerManager()
        breaker = manager.get_breaker("chromadb")

        config = CircuitBreakerConfig(failure_threshold=2)
        breaker.config = config

        # Simulate timeout errors
        with pytest.raises(TimeoutError):
            breaker.call(lambda: (_ for _ in ()).throw(TimeoutError("ChromaDB timeout")))

        with pytest.raises(TimeoutError):
            breaker.call(lambda: (_ for _ in ()).throw(TimeoutError("ChromaDB timeout")))

        assert breaker.state == CircuitBreakerState.OPEN

    def test_rate_limit_handling(self):
        """Test that circuit breaker handles rate limiting."""
        manager = CircuitBreakerManager()
        breaker = manager.get_breaker("external_api")

        config = CircuitBreakerConfig(failure_threshold=3)
        breaker.config = config

        # Simulate rate limit errors
        call_count = [0]

        def failing_call():
            call_count[0] += 1
            raise OSError("HTTP 429: Too Many Requests")

        # Make calls until circuit opens
        for _ in range(3):
            with pytest.raises(OSError):
                breaker.call(failing_call)

        # Circuit should be open
        assert breaker.state == CircuitBreakerState.OPEN
