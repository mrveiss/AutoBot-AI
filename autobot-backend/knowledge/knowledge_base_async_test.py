"""
Unit tests for KnowledgeBase async Redis initialization.

Covers _init_redis_connections() which uses get_redis_client(async_client=True).
The fix for #3962: get_redis_client(async_client=True) returns a *coroutine*
(sync function returning the result of calling an async method).  The caller
must *await* that value to obtain the actual redis.asyncio.Redis instance.
Prior to the fix the code stored the un-awaited coroutine in
self.aioredis_client, causing 'coroutine' object has no attribute 'ping'.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REDIS_CLIENT_PATH = "autobot_shared.redis_client.get_redis_client"


def _make_mock_redis() -> AsyncMock:
    """Return an AsyncMock that behaves like redis.asyncio.Redis."""
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    return client


def _make_coroutine(return_value):
    """Return a coroutine that resolves to *return_value*."""

    async def _coro():
        return return_value

    return _coro()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_async_redis():
    return _make_mock_redis()


# ---------------------------------------------------------------------------
# Tests: _init_redis_connections async Redis path
# ---------------------------------------------------------------------------


class TestInitRedisConnections:
    """Verify that _init_redis_connections properly awaits the async client."""

    @pytest.mark.asyncio
    async def test_awaits_coroutine_and_stores_client(self, mock_async_redis):
        """
        get_redis_client(async_client=True) returns a coroutine.
        _init_redis_connections must await it; self.aioredis_client must be
        the resolved Redis instance, NOT the coroutine object itself. (#3962)
        """
        # Import here to avoid heavy module-level side-effects in test discovery
        from knowledge.base import KnowledgeBase

        kb = KnowledgeBase.__new__(KnowledgeBase)
        kb.redis_client = None
        kb.aioredis_client = None
        kb.redis_db = 1

        sync_client = MagicMock()
        sync_client.ping = MagicMock(return_value=True)

        def fake_get_redis_client(async_client=False, database="main"):
            if async_client:
                # Mimic the real function: sync wrapper that returns a coroutine
                return _make_coroutine(mock_async_redis)
            return sync_client

        with patch(_REDIS_CLIENT_PATH, side_effect=fake_get_redis_client):
            await kb._init_redis_connections()

        # Must be the actual client, not a coroutine
        assert kb.aioredis_client is mock_async_redis, (
            "aioredis_client should be the Redis instance, not a coroutine"
        )
        import inspect

        assert not inspect.iscoroutine(kb.aioredis_client), (
            "aioredis_client must not be a coroutine after _init_redis_connections"
        )

    @pytest.mark.asyncio
    async def test_ping_called_on_async_client(self, mock_async_redis):
        """After awaiting, ping() must be called on the Redis client."""
        from knowledge.base import KnowledgeBase

        kb = KnowledgeBase.__new__(KnowledgeBase)
        kb.redis_client = None
        kb.aioredis_client = None
        kb.redis_db = 1

        sync_client = MagicMock()
        sync_client.ping = MagicMock(return_value=True)

        def fake_get_redis_client(async_client=False, database="main"):
            if async_client:
                return _make_coroutine(mock_async_redis)
            return sync_client

        with patch(_REDIS_CLIENT_PATH, side_effect=fake_get_redis_client):
            await kb._init_redis_connections()

        mock_async_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_when_async_client_returns_none(self):
        """
        If get_redis_client returns None (circuit breaker open / Redis disabled),
        _init_redis_connections must raise rather than silently store None.
        """
        from knowledge.base import KnowledgeBase

        kb = KnowledgeBase.__new__(KnowledgeBase)
        kb.redis_client = None
        kb.aioredis_client = None
        kb.redis_db = 1

        sync_client = MagicMock()
        sync_client.ping = MagicMock(return_value=True)

        def fake_get_redis_client(async_client=False, database="main"):
            if async_client:
                return _make_coroutine(None)
            return sync_client

        with patch(_REDIS_CLIENT_PATH, side_effect=fake_get_redis_client):
            with pytest.raises(Exception, match="Async Redis client initialization returned None"):
                await kb._init_redis_connections()

    @pytest.mark.asyncio
    async def test_raises_when_sync_client_returns_none(self):
        """If the sync client is None, _init_redis_connections must raise."""
        from knowledge.base import KnowledgeBase

        kb = KnowledgeBase.__new__(KnowledgeBase)
        kb.redis_client = None
        kb.aioredis_client = None
        kb.redis_db = 1

        def fake_get_redis_client(async_client=False, database="main"):
            if async_client:
                return _make_coroutine(AsyncMock())
            return None

        with patch(_REDIS_CLIENT_PATH, side_effect=fake_get_redis_client):
            with pytest.raises(Exception, match="Redis client initialization returned None"):
                await kb._init_redis_connections()

    @pytest.mark.asyncio
    async def test_exception_propagates_from_ping(self, mock_async_redis):
        """
        If ping() raises (e.g. ConnectionError), the exception must propagate
        so the caller (initialize()) can handle it and set initialized=False.
        """
        from knowledge.base import KnowledgeBase

        kb = KnowledgeBase.__new__(KnowledgeBase)
        kb.redis_client = None
        kb.aioredis_client = None
        kb.redis_db = 1

        sync_client = MagicMock()
        sync_client.ping = MagicMock(return_value=True)
        mock_async_redis.ping = AsyncMock(side_effect=ConnectionError("Redis down"))

        def fake_get_redis_client(async_client=False, database="main"):
            if async_client:
                return _make_coroutine(mock_async_redis)
            return sync_client

        with patch(_REDIS_CLIENT_PATH, side_effect=fake_get_redis_client):
            with pytest.raises(Exception):
                await kb._init_redis_connections()
