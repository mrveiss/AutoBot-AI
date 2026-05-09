# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Tests for AsyncSyncBridge (Issue #6970)."""

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _reset_bridge():
    """Tear down the singleton between tests."""
    from plugin_sdk.async_bridge import AsyncSyncBridge

    AsyncSyncBridge.reset_for_tests()
    yield
    AsyncSyncBridge.reset_for_tests()


def test_async_bridge_run_coro_returns_result():
    from plugin_sdk.async_bridge import AsyncSyncBridge

    async def add(a, b):
        return a + b

    result = AsyncSyncBridge().run_coro(add(2, 3))
    assert result == 5


def test_async_bridge_propagates_exception():
    from plugin_sdk.async_bridge import AsyncSyncBridge

    async def boom():
        raise ValueError("explicit failure")

    with pytest.raises(ValueError) as exc_info:
        AsyncSyncBridge().run_coro(boom())
    assert "explicit failure" in str(exc_info.value)


def test_async_bridge_singleton_returns_same_instance():
    from plugin_sdk.async_bridge import AsyncSyncBridge

    a = AsyncSyncBridge()
    b = AsyncSyncBridge()
    assert a is b
    assert a._loop is b._loop
    assert a._thread is b._thread


def test_async_bridge_reset_for_tests_creates_fresh_instance():
    from plugin_sdk.async_bridge import AsyncSyncBridge

    a = AsyncSyncBridge()
    AsyncSyncBridge.reset_for_tests()
    b = AsyncSyncBridge()
    assert a is not b
    assert a._loop is not b._loop


def test_async_bridge_thread_is_daemon():
    from plugin_sdk.async_bridge import AsyncSyncBridge

    bridge = AsyncSyncBridge()
    assert bridge._thread.daemon is True
    assert bridge._thread.name == "AsyncSyncBridge"


def test_async_bridge_run_coro_with_sleep():
    """Verify the loop can actually run a coroutine that yields control."""
    from plugin_sdk.async_bridge import AsyncSyncBridge

    async def yield_then_return():
        await asyncio.sleep(0)
        return "done"

    assert AsyncSyncBridge().run_coro(yield_then_return()) == "done"
