# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for ChatHistoryManager.initialize() — Issue #3886.

Confirms that:
- initialize() is not a no-op: it sets self._initialized and calls _init_memory_graph
- initialize() is idempotent: a second call is a safe no-op
- _initialized starts False after construction
- lifespan can call await manager.initialize() without error
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_config_stub() -> MagicMock:
    """Return a config manager stub that answers minimal queries for data section."""
    cfg = MagicMock()
    cfg.get.return_value = {}
    return cfg


def _make_ssot_stub() -> MagicMock:
    """Return a ssot_config stub supplying Redis connection defaults."""
    ssot = MagicMock()
    ssot.redis.enabled = False
    ssot.vm.redis = "127.0.0.1"
    ssot.port.redis = 6379
    return ssot


@pytest.fixture()
def manager():
    """
    Build a ChatHistoryManager with all heavy deps stubbed out.

    The fixture patches at the module level so that __init__ itself can run
    without touching Redis, the filesystem, or Memory Graph.
    """
    with (
        patch("chat_history.base.global_config_manager", _make_config_stub()),
        patch("chat_history.base._ssot_config", _make_ssot_stub()),
        patch("chat_history.base.get_redis_client", return_value=None),
        patch("chat_history.base.is_encryption_enabled", return_value=False),
        patch("chat_history.base.ContextWindowManager", return_value=MagicMock()),
        patch("chat_history.base.AutoBotMemoryGraph"),
        patch("chat_history.base.get_encryption_service"),
        patch("chat_history.base.os.path.exists", return_value=True),
        patch("chat_history.base.os.makedirs"),
        patch("chat_history.base.os.path.dirname", return_value="data"),
    ):
        from chat_history import ChatHistoryManager

        m = ChatHistoryManager(history_file="data/chat_history.json", use_redis=False)
        yield m


class TestInitializeNotNoOp:
    """initialize() must perform real work and set _initialized."""

    @pytest.mark.asyncio
    async def test_initialized_flag_starts_false(self, manager):
        """_initialized must be False immediately after construction."""
        assert manager._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_sets_flag(self, manager):
        """After awaiting initialize(), _initialized must be True."""
        manager._init_memory_graph = AsyncMock()
        await manager.initialize()
        assert manager._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_calls_memory_graph_init(self, manager):
        """initialize() must call _init_memory_graph exactly once."""
        manager._init_memory_graph = AsyncMock()
        await manager.initialize()
        manager._init_memory_graph.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, manager):
        """A second call to initialize() must be a safe no-op."""
        manager._init_memory_graph = AsyncMock()
        await manager.initialize()
        await manager.initialize()
        # _init_memory_graph must still have been called only once
        manager._init_memory_graph.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_idempotent_flag_stays_true(self, manager):
        """_initialized stays True after two calls."""
        manager._init_memory_graph = AsyncMock()
        await manager.initialize()
        await manager.initialize()
        assert manager._initialized is True

    @pytest.mark.asyncio
    async def test_memory_graph_failure_does_not_prevent_initialized_flag(self, manager, caplog):
        """
        If _init_memory_graph raises, initialize() should still propagate the
        exception (not silently swallow it) — the Memory Graph failure is
        already handled inside _init_memory_graph itself with a warning log.
        But if _init_memory_graph handles errors internally (as the real impl
        does), _initialized must still be set to True.
        """

        # Simulate the real _init_memory_graph: it catches all errors internally
        # and sets memory_graph = None, so it never raises.
        async def _safe_stub():
            manager.memory_graph = None
            manager.memory_graph_enabled = False

        manager._init_memory_graph = AsyncMock(side_effect=_safe_stub)

        await manager.initialize()
        assert manager._initialized is True
