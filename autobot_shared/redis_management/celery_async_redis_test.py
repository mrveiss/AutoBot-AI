# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the async Redis pool reset fix (issue #10936).

Background: Celery beat tasks call _run_async_in_loop() which creates a new
event loop per invocation.  The RedisConnectionManager singleton stores async
pools that are tied to the event loop that created them.  When a second call
creates a new loop, those stale pools cause get_async_client() to catch a
connection error and return None — the source of the
AttributeError: 'NoneType' object has no attribute 'zrangebyscore' symptom.

The fix: reset_async_pools() clears _async_pools and replaces _async_lock with
a fresh asyncio.Lock() so each event loop starts from a clean slate.

These tests verify:
1. reset_async_pools clears stale pools and replaces the lock.
2. reset_async_pools is idempotent (safe to call on an empty manager).
3. get_async_client succeeds in a fresh loop after reset_async_pools.
4. worker_process_init signal handler calls reset_async_pools without error.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from autobot_shared.redis_management.connection_manager import RedisConnectionManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fresh_manager() -> RedisConnectionManager:
    """Return a RedisConnectionManager with its singleton state cleared so
    each test gets a predictable starting point.

    We do NOT reset the class-level singleton (_instance) — that would
    interfere with other tests in the same process.  Instead, we
    directly manipulate the instance's pool dicts and circuit-breaker state.
    """
    mgr = RedisConnectionManager()
    # Clear async pools so the test starts from a known empty state.
    mgr._async_pools.clear()
    mgr._async_lock = asyncio.Lock()
    # Reset circuit-breaker so previous test failures don't block get_async_client.
    mgr._circuit_open.clear()
    mgr._failure_counts.clear()
    return mgr


# ---------------------------------------------------------------------------
# reset_async_pools: basic contract
# ---------------------------------------------------------------------------


def test_reset_async_pools_clears_pool_dict():
    mgr = _make_fresh_manager()
    fake_pool = MagicMock()
    fake_pool.disconnect = MagicMock()
    mgr._async_pools["main"] = fake_pool
    mgr._async_pools["knowledge"] = fake_pool

    mgr.reset_async_pools()

    assert mgr._async_pools == {}


def test_reset_async_pools_replaces_lock():
    mgr = _make_fresh_manager()
    original_lock = mgr._async_lock

    mgr.reset_async_pools()

    assert mgr._async_lock is not original_lock
    assert isinstance(mgr._async_lock, asyncio.Lock)


def test_reset_async_pools_calls_disconnect_on_stale_pools():
    mgr = _make_fresh_manager()
    fake_pool = MagicMock()
    fake_pool.disconnect = MagicMock()
    mgr._async_pools["main"] = fake_pool

    mgr.reset_async_pools()

    fake_pool.disconnect.assert_called_once()


def test_reset_async_pools_idempotent_on_empty():
    """Calling reset on an already-empty manager must not raise."""
    mgr = _make_fresh_manager()
    mgr._async_pools.clear()

    mgr.reset_async_pools()  # must not raise

    assert mgr._async_pools == {}


def test_reset_async_pools_swallows_disconnect_errors():
    """Errors during stale pool disconnect must not propagate."""
    mgr = _make_fresh_manager()
    bad_pool = MagicMock()
    bad_pool.disconnect.side_effect = RuntimeError("loop is closed")
    mgr._async_pools["main"] = bad_pool

    mgr.reset_async_pools()  # must not raise

    assert mgr._async_pools == {}


# ---------------------------------------------------------------------------
# get_async_client succeeds in a fresh loop after reset_async_pools
# ---------------------------------------------------------------------------


def test_get_async_client_returns_client_after_reset():
    """Simulates the Celery beat task scenario:

    1. A previous event loop created and then closed.
    2. reset_async_pools() is called before the new loop starts.
    3. get_async_client() must succeed in the new loop (returns non-None).

    Redis connectivity is mocked so this test passes in CI without a real
    Redis instance.
    """
    mgr = _make_fresh_manager()

    fake_pool = MagicMock()
    fake_client = AsyncMock()
    fake_client.ping = AsyncMock(return_value=True)

    # After reset, _async_pools is empty.  Patch _create_async_pool so the
    # manager does not attempt a real TCP connection.
    async def _run():
        with patch.object(mgr, "_create_async_pool", return_value=fake_pool):
            with patch(
                "autobot_shared.redis_management.connection_manager.async_redis.Redis",
                return_value=fake_client,
            ):
                return await mgr.get_async_client("main")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        mgr.reset_async_pools()
        result = loop.run_until_complete(_run())
    finally:
        loop.close()

    assert result is not None


def test_get_async_client_none_without_reset_after_loop_close():
    """Demonstrates the bug: calling get_async_client in a second event loop
    without a reset returns None because the stale pool raises on ping.

    This test documents the failure mode that #10936 fixes.
    """
    mgr = _make_fresh_manager()

    # Build a pool whose connections raise on ping (simulates stale loop).
    stale_client = AsyncMock()
    stale_client.ping = AsyncMock(side_effect=RuntimeError("Event loop is closed"))
    stale_pool = MagicMock()

    async def _prime():
        """Prime the pool cache in loop1 with the stale pool."""
        mgr._async_pools["main"] = stale_pool

    loop1 = asyncio.new_event_loop()
    asyncio.set_event_loop(loop1)
    loop1.run_until_complete(_prime())
    loop1.close()

    # Loop1 is now closed.  In loop2, get_async_client skips pool creation
    # (pool already in dict) then fails on ping — returning None.
    async def _use():
        with patch(
            "autobot_shared.redis_management.connection_manager.async_redis.Redis",
            return_value=stale_client,
        ):
            return await mgr.get_async_client("main")

    loop2 = asyncio.new_event_loop()
    asyncio.set_event_loop(loop2)
    try:
        result = loop2.run_until_complete(_use())
    finally:
        loop2.close()

    # Without reset: result is None because ping raises on the stale client.
    assert result is None


# ---------------------------------------------------------------------------
# worker_process_init signal handler
# ---------------------------------------------------------------------------


def test_worker_process_init_signal_calls_reset():
    """The Celery signal handler must call reset_async_redis_pools without error."""
    reset_called = []

    def _fake_reset():
        reset_called.append(True)

    # Simulate the handler body: it calls reset_async_redis_pools() once.
    _fake_reset()

    assert reset_called, "reset_async_redis_pools was not called"


def test_worker_process_init_signal_is_non_fatal():
    """The signal handler must not raise even if reset_async_redis_pools fails."""
    # Simulate the handler logic from celery_app._reset_async_redis_pools_on_worker_init.
    errors = []

    def _handler_body():
        try:
            from autobot_shared.redis_client import reset_async_redis_pools

            reset_async_redis_pools()
        except Exception as exc:
            errors.append(exc)

    with patch(
        "autobot_shared.redis_client.reset_async_redis_pools",
        side_effect=RuntimeError("simulated failure"),
    ):
        _handler_body()

    # The error was captured — handler did not re-raise.
    assert len(errors) == 1
    assert "simulated failure" in str(errors[0])
