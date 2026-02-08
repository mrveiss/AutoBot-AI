# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for Circuit Breaker - Issue #712."""

import time

import pytest
from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
    CircuitBreakerOpenError,
    CircuitState,
    circuit_breaker_async,
    circuit_breaker_sync,
    protected_database_call,
    protected_llm_call,
    protected_network_call,
)


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""

    def test_default_values(self):
        config = CircuitBreakerConfig()
        assert config.failure_threshold > 0
        assert config.recovery_timeout > 0

    def test_custom_values(self):
        config = CircuitBreakerConfig(failure_threshold=10, recovery_timeout=120.0)
        assert config.failure_threshold == 10
        assert config.recovery_timeout == 120.0


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker("test_svc")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_transition_to_open(self):
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test_svc", config)
        for _ in range(3):
            cb._record_failure(0.1, ConnectionError("test"))
        assert cb.state == CircuitState.OPEN

    def test_transition_to_half_open(self):
        config = CircuitBreakerConfig(recovery_timeout=0.1)
        cb = CircuitBreaker("test_svc", config)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time() - 1
        assert cb._can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_transition_to_closed(self):
        config = CircuitBreakerConfig(success_threshold=2)
        cb = CircuitBreaker("test_svc", config)
        cb.state = CircuitState.HALF_OPEN
        cb._record_success(0.1)
        cb._record_success(0.1)
        assert cb.state == CircuitState.CLOSED

    def test_failure_in_half_open(self):
        cb = CircuitBreaker("test_svc")
        cb.state = CircuitState.HALF_OPEN
        cb._record_failure(0.1, ConnectionError("test"))
        assert cb.state == CircuitState.OPEN

    def test_reset(self):
        cb = CircuitBreaker("test_svc")
        cb.state = CircuitState.OPEN
        cb.failure_count = 10
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_get_state(self):
        cb = CircuitBreaker("test_svc")
        state = cb.get_state()
        assert state["name"] == "test_svc"
        assert "stats" in state


class TestCircuitBreakerAsync:
    """Tests for async operations."""

    @pytest.mark.asyncio
    async def test_success(self):
        cb = CircuitBreaker("async_svc")

        async def func():
            return "ok"

        result = await cb.call_async(func)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_failure(self):
        cb = CircuitBreaker("async_fail_svc")

        async def func():
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            await cb.call_async(func)
        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_blocked_when_open(self):
        config = CircuitBreakerConfig(recovery_timeout=60.0)
        cb = CircuitBreaker("blocked_svc", config)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time()
        cb.failure_count = 5

        async def func():
            return "ok"

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call_async(func)


class TestCircuitBreakerSync:
    """Tests for sync operations."""

    def test_success(self):
        cb = CircuitBreaker("sync_svc")

        def func():
            return "ok"

        assert cb.call_sync(func) == "ok"

    def test_failure(self):
        cb = CircuitBreaker("sync_fail_svc")

        def func():
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            cb.call_sync(func)


class TestCircuitBreakerManager:
    """Tests for CircuitBreakerManager."""

    def test_create_and_get(self):
        mgr = CircuitBreakerManager()
        cb1 = mgr.get_circuit_breaker("svc1")
        cb2 = mgr.get_circuit_breaker("svc1")
        assert cb1 is cb2

    def test_reset_all(self):
        mgr = CircuitBreakerManager()
        cb = mgr.get_circuit_breaker("svc2")
        cb.failure_count = 5
        mgr.reset_all_circuit_breakers()
        assert cb.failure_count == 0


class TestDecorators:
    """Tests for decorators."""

    @pytest.mark.asyncio
    async def test_async_decorator(self):
        @circuit_breaker_async("dec_async_svc")
        async def func():
            return "decorated"

        assert await func() == "decorated"
        assert hasattr(func, "circuit_breaker")

    def test_sync_decorator(self):
        @circuit_breaker_sync("dec_sync_svc")
        def func():
            return "decorated"

        assert func() == "decorated"


class TestProtectedCalls:
    """Tests for protected call functions."""

    @pytest.mark.asyncio
    async def test_protected_llm(self):
        async def llm():
            return "response"

        assert await protected_llm_call(llm) == "response"

    @pytest.mark.asyncio
    async def test_protected_db(self):
        async def db():
            return "data"

        assert await protected_database_call(db) == "data"

    @pytest.mark.asyncio
    async def test_protected_network(self):
        async def net():
            return "result"

        assert await protected_network_call(net) == "result"
