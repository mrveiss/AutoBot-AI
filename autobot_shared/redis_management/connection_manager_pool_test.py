# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for #11449: async pool creation must not serialize callers under the
global lock, and an empty Redis host must fail fast as a configuration error
instead of burning the exponential-backoff retry budget."""

import asyncio
from types import SimpleNamespace

import pytest

from autobot_shared.redis_management.connection_manager import (
    RedisConfigurationError,
    RedisConnectionManager,
)


def _bare_manager() -> RedisConnectionManager:
    """Manager instance with only the pool-registry state initialised —
    avoids the full config/circuit-breaker boot in __init__."""
    m = object.__new__(RedisConnectionManager)
    m._async_pools = {}
    m._async_pool_tasks = {}
    m._async_lock = asyncio.Lock()
    return m


class TestValidateConfigHost:
    def test_empty_host_raises_configuration_error(self):
        cfg = SimpleNamespace(host="")
        with pytest.raises(RedisConfigurationError):
            RedisConnectionManager._validate_config_host("main", cfg)

    def test_blank_host_raises_configuration_error(self):
        cfg = SimpleNamespace(host="   ")
        with pytest.raises(RedisConfigurationError):
            RedisConnectionManager._validate_config_host("main", cfg)

    def test_none_host_raises_configuration_error(self):
        cfg = SimpleNamespace(host=None)
        with pytest.raises(RedisConfigurationError):
            RedisConnectionManager._validate_config_host("main", cfg)

    def test_valid_host_passes(self):
        cfg = SimpleNamespace(host="127.0.0.1")
        RedisConnectionManager._validate_config_host("main", cfg)  # no raise

    def test_configuration_error_is_not_retryable_connection_error(self):
        """The retry mechanism keys on ConnectionError/TimeoutError — the
        config error must match neither the builtin nor redis-py's
        ConnectionError (which shadows the builtin in the module) (#11449)."""
        from redis.exceptions import ConnectionError as _RedisCE

        assert not issubclass(RedisConfigurationError, ConnectionError)
        assert not issubclass(RedisConfigurationError, _RedisCE)
        assert issubclass(RedisConfigurationError, ValueError)


class TestEnsureAsyncPoolLockScope:
    @pytest.mark.asyncio
    async def test_concurrent_callers_share_one_creation(self):
        m = _bare_manager()
        calls = {"n": 0}
        pool = object()

        async def _slow_create(name):
            calls["n"] += 1
            await asyncio.sleep(0.1)
            return pool

        m._create_async_pool = _slow_create
        await asyncio.gather(*[m._ensure_async_pool_exists("main") for _ in range(5)])
        assert calls["n"] == 1, "creation must run once for concurrent callers"
        assert m._async_pools["main"] is pool
        assert "main" not in m._async_pool_tasks

    @pytest.mark.asyncio
    async def test_deadline_cancelled_caller_does_not_kill_creation(self):
        """A caller cancelled by its own asyncio.wait_for must not cancel the
        shared creation for everyone else (shield semantics, #11449)."""
        m = _bare_manager()
        pool = object()

        async def _slow_create(name):
            await asyncio.sleep(0.2)
            return pool

        m._create_async_pool = _slow_create
        patient = asyncio.ensure_future(m._ensure_async_pool_exists("main"))
        await asyncio.sleep(0.01)  # let the creation task start
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(m._ensure_async_pool_exists("main"), timeout=0.05)
        await patient  # the patient caller still completes
        assert m._async_pools["main"] is pool

    @pytest.mark.asyncio
    async def test_lock_not_held_during_creation(self):
        """While a slow creation is in flight, the registry lock must be free
        (pre-#11449 it was held for the whole retry sequence)."""
        m = _bare_manager()

        async def _slow_create(name):
            await asyncio.sleep(0.2)
            return object()

        m._create_async_pool = _slow_create
        task = asyncio.ensure_future(m._ensure_async_pool_exists("main"))
        await asyncio.sleep(0.05)  # creation is now in flight
        assert not m._async_lock.locked(), "lock must not be held during creation"
        await task

    @pytest.mark.asyncio
    async def test_failed_creation_propagates_and_allows_retry(self):
        m = _bare_manager()
        attempts = {"n": 0}
        pool = object()

        async def _flaky_create(name):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RedisConfigurationError("empty host")
            return pool

        m._create_async_pool = _flaky_create
        with pytest.raises(RedisConfigurationError):
            await m._ensure_async_pool_exists("main")
        assert "main" not in m._async_pools
        await m._ensure_async_pool_exists("main")  # retry succeeds
        assert m._async_pools["main"] is pool
        assert attempts["n"] == 2

    @pytest.mark.asyncio
    async def test_completed_task_is_harvested_not_respawned(self):
        """A done-successful task whose waiter hasn't written the registry yet
        must be harvested — not respawned as a duplicate pool (#11451)."""
        m = _bare_manager()
        pool = object()

        async def _done_pool():
            return pool

        task = asyncio.ensure_future(_done_pool())
        await task  # completed, but registry never written (waiter "not yet run")
        m._async_pool_tasks["main"] = task

        async def _must_not_run(name):  # pragma: no cover - failure path
            raise AssertionError("duplicate creation spawned")

        m._create_async_pool = _must_not_run
        await m._ensure_async_pool_exists("main")
        assert m._async_pools["main"] is pool
        assert "main" not in m._async_pool_tasks
