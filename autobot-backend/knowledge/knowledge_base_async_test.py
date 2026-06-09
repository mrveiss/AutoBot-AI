# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for KnowledgeBase async Redis initialization.

Covers _init_redis_connections() which uses get_async_redis_client() (#3962).

Root cause of #3962: the original code called get_redis_client(async_client=True)
without await.  get_redis_client is a *sync* function that returns the coroutine
produced by RedisConnectionManager.get_async_client() without awaiting it.
Storing that coroutine in self._aioredis_client then caused:
    AttributeError: 'coroutine' object has no attribute 'ping'

Fix: autobot_shared.redis_client now exposes get_async_redis_client(), a true
async def that always awaits the underlying coroutine before returning.
_init_redis_connections() uses get_async_redis_client() so the correct usage is
structurally impossible to get wrong.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.logging_manager import get_logger
from tests.fixtures import make_async_redis

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Patch paths
# ---------------------------------------------------------------------------

# These patch the canonical source (``autobot_shared.redis_client``) rather
# than a consumer namespace because ``KnowledgeBase._init_redis_connections``
# imports ``get_async_redis_client`` lazily inside the method body
# (``knowledge/base.py:322``) — there is no module-top binding to patch in
# the consumer namespace at patch time.
_SYNC_CLIENT_PATH = "autobot_shared.redis_client.get_redis_client"
_ASYNC_CLIENT_PATH = "autobot_shared.redis_client.get_async_redis_client"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_async_redis():
    # Migrated to canonical ``make_async_redis()`` (#7280 round 3).
    # ``ping=True`` flows through ``**extra_methods`` to attach
    # ``AsyncMock(return_value=True)`` — ``ping`` is not in the canonical
    # fixture's core defaults.
    return make_async_redis(ping=True)


# ---------------------------------------------------------------------------
# Tests: _init_redis_connections async Redis path
# ---------------------------------------------------------------------------


class TestInitRedisConnections:
    """Verify that _init_redis_connections properly awaits the async client."""

    def _make_kb(self):
        from knowledge import KnowledgeBase

        kb = KnowledgeBase.__new__(KnowledgeBase)
        kb.redis_client = None
        kb._aioredis_client = None
        kb.redis_db = 1
        return kb

    def _make_sync_client(self):
        sync_client = MagicMock()
        sync_client.ping = MagicMock(return_value=True)
        return sync_client

    @pytest.mark.asyncio
    async def test_stores_real_client_not_coroutine(self, mock_async_redis):
        """
        get_async_redis_client() must resolve to the actual Redis instance.
        self._aioredis_client must never be a coroutine object. (#3962, #5225)
        """
        kb = self._make_kb()
        sync_client = self._make_sync_client()

        with (
            patch(_SYNC_CLIENT_PATH, return_value=sync_client),
            patch(_ASYNC_CLIENT_PATH, new=AsyncMock(return_value=mock_async_redis)),
        ):
            await kb._init_redis_connections()

        assert kb._aioredis_client is mock_async_redis, "_aioredis_client should be the Redis instance, not a coroutine"
        assert not inspect.iscoroutine(
            kb._aioredis_client
        ), "_aioredis_client must not be a coroutine after _init_redis_connections"

    @pytest.mark.asyncio
    async def test_ping_called_on_async_client(self, mock_async_redis):
        """After initialization, ping() must have been called on the Redis client."""
        kb = self._make_kb()
        sync_client = self._make_sync_client()

        with (
            patch(_SYNC_CLIENT_PATH, return_value=sync_client),
            patch(_ASYNC_CLIENT_PATH, new=AsyncMock(return_value=mock_async_redis)),
        ):
            await kb._init_redis_connections()

        mock_async_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_when_async_client_returns_none(self):
        """
        If get_async_redis_client returns None (circuit breaker open / Redis
        disabled), _init_redis_connections must raise rather than silently
        store None and let a later .ping() fail with AttributeError.
        """
        kb = self._make_kb()
        sync_client = self._make_sync_client()

        with (
            patch(_SYNC_CLIENT_PATH, return_value=sync_client),
            patch(_ASYNC_CLIENT_PATH, new=AsyncMock(return_value=None)),
        ):
            with pytest.raises(Exception, match="Async Redis client initialization returned None"):
                await kb._init_redis_connections()

    @pytest.mark.asyncio
    async def test_raises_when_sync_client_returns_none(self):
        """If the sync client is None, _init_redis_connections must raise."""
        kb = self._make_kb()

        with patch(_SYNC_CLIENT_PATH, return_value=None):
            with pytest.raises(Exception, match="Redis client initialization returned None"):
                await kb._init_redis_connections()

    @pytest.mark.asyncio
    async def test_exception_propagates_from_async_ping(self, mock_async_redis):
        """
        If ping() raises (e.g. ConnectionError), the exception must propagate
        so the caller (initialize()) can handle it and set initialized=False.
        """
        kb = self._make_kb()
        sync_client = self._make_sync_client()
        mock_async_redis.ping = AsyncMock(side_effect=ConnectionError("Redis down"))

        with (
            patch(_SYNC_CLIENT_PATH, return_value=sync_client),
            patch(_ASYNC_CLIENT_PATH, new=AsyncMock(return_value=mock_async_redis)),
        ):
            with pytest.raises(ConnectionError, match="Redis down"):
                await kb._init_redis_connections()
