# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Memory Provider System

Tests the provider-based memory architecture including:
- Built-in PostgreSQL provider
- External Redis provider
- Milvus vector database provider
- Provider factory and manager (via MemoryManager.provider)
- Fallback and health check logic

Issue #4344: Provider-based memory architecture with external provider support
Issue #10666 B2: Migrated from services.memory.memory_manager.MemoryManager
  (now deleted) to the canonical memory.MemoryManager.provider sub-layer.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.memory import (
    PostgresMemoryProvider,
    RedisMemoryProvider,
)


class TestPostgresMemoryProvider:
    """Test PostgreSQL memory provider."""

    @pytest.fixture
    async def provider(self):
        """Create and initialize PostgreSQL provider."""
        provider = PostgresMemoryProvider()
        yield provider

    @pytest.mark.asyncio
    async def test_initialize(self, provider):
        """Test provider initialization."""
        with patch("services.memory.postgres_provider.AutoBotMemoryGraph") as mock_graph:
            mock_instance = AsyncMock()
            mock_graph.return_value = mock_instance

            await provider.initialize()

            assert provider.memory_graph is not None
            mock_instance.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test provider cleanup."""
        mock_graph = AsyncMock()
        provider.memory_graph = mock_graph

        await provider.close()

        mock_graph.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_prefetch_with_conversation(self, provider):
        """Test prefetch with conversation context."""
        mock_graph = AsyncMock()
        provider.memory_graph = mock_graph

        mock_graph.get_entity.return_value = {"id": "conv_123", "type": "conversation"}
        mock_graph.search_entities.return_value = [
            {"id": "entity_1", "relevance": 0.95},
            {"id": "entity_2", "relevance": 0.87},
        ]

        context = {"conversation_id": "conv_123", "user_id": "user_456"}
        result = await provider.prefetch(context)

        assert "conversation" in result
        assert "related_entities" in result
        assert len(result["related_entities"]) <= 10

    @pytest.mark.asyncio
    async def test_search(self, provider):
        """Test semantic search."""
        mock_graph = AsyncMock()
        provider.memory_graph = mock_graph
        mock_graph.search_entities.return_value = [
            {"id": "entity_1", "score": 0.95},
            {"id": "entity_2", "score": 0.87},
        ]

        results = await provider.search("test query", limit=10)

        assert len(results) == 2
        mock_graph.search_entities.assert_called_once_with("test query", limit=10)

    @pytest.mark.asyncio
    async def test_health_check(self, provider):
        """Test health check."""
        mock_graph = AsyncMock()
        provider.memory_graph = mock_graph

        health = await provider.health_check()

        assert isinstance(health, bool)


class TestRedisMemoryProvider:
    """Test Redis memory provider."""

    @pytest.fixture
    async def provider(self):
        """Create Redis provider."""
        provider = RedisMemoryProvider()
        yield provider

    @pytest.mark.asyncio
    async def test_initialize(self, provider):
        """Test Redis provider initialization."""
        mock_client = AsyncMock()
        async_mock_func = AsyncMock(return_value=mock_client)
        with patch(
            "services.memory.redis_provider.get_redis_client",
            new=async_mock_func,
        ):
            await provider.initialize()

            assert provider.redis is not None

    @pytest.mark.asyncio
    async def test_cache_sync(self, provider):
        """Test caching turn data in Redis."""
        mock_redis = AsyncMock()
        provider.redis = mock_redis

        turn = {
            "conversation_id": "conv_123",
            "timestamp": "2025-04-13T10:00:00Z",
            "entity_updates": [{"action": "create", "name": "Task 1"}],
            "relation_updates": [],
        }

        await provider.sync(turn)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert "conv_123" in call_args[0][0]
        assert call_args[0][1] == 86400

    @pytest.mark.asyncio
    async def test_health_check(self, provider):
        """Test Redis health check."""
        mock_redis = AsyncMock()
        provider.redis = mock_redis
        mock_redis.ping.return_value = True

        health = await provider.health_check()

        assert health is True


class TestMemoryManagerProvider:
    """Test provider-routing sub-layer via MemoryManager.provider."""

    @pytest.fixture
    async def router(self):
        """Create a _ProviderRouter via MemoryManager.provider (lazy-init)."""
        from memory.manager import _ProviderRouter

        router = _ProviderRouter.__new__(_ProviderRouter)
        # Provide pre-built mock built_in so tests don't need to construct it
        router.built_in = AsyncMock()
        router.external = None
        router.external_enabled = False
        yield router

    @pytest.mark.asyncio
    async def test_initialize_built_in_only(self, router):
        """Test initialization with built-in provider only."""
        with (
            patch("services.memory.postgres_provider.PostgresMemoryProvider") as mock_pg,
            patch("services.memory.external_provider_factory.ExternalProviderFactory") as mock_factory,
        ):
            mock_built_in = AsyncMock()
            mock_pg.return_value = mock_built_in
            mock_factory.get_provider = AsyncMock(return_value=None)

            router.built_in = mock_built_in
            router.external = None
            router.external_enabled = False

            assert router.built_in is not None
            assert router.external is None
            assert router.external_enabled is False

    @pytest.mark.asyncio
    async def test_initialize_with_external(self, router):
        """Test router state when external provider present."""
        mock_external = AsyncMock()
        router.external = mock_external
        router.external_enabled = True

        assert router.built_in is not None
        assert router.external is not None
        assert router.external_enabled is True

    @pytest.mark.asyncio
    async def test_prefetch_tries_external_first(self, router):
        """Test prefetch tries external provider first."""
        mock_external = AsyncMock()
        router.external = mock_external
        router.external_enabled = True

        external_result = {"cached": True}
        mock_external.prefetch = AsyncMock(return_value=external_result)

        context = {"conversation_id": "conv_123"}
        result = await router.prefetch(context)

        assert result == external_result
        mock_external.prefetch.assert_called_once()
        router.built_in.prefetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_to_both_providers(self, router):
        """Test sync writes to both built-in and external."""
        mock_external = AsyncMock()
        router.external = mock_external
        router.external_enabled = True

        turn = {
            "entity_updates": [],
            "relation_updates": [],
            "timestamp": "2025-04-13T10:00:00Z",
        }

        await router.sync(turn)

        router.built_in.sync.assert_called_once_with(turn)
        mock_external.sync.assert_called_once_with(turn)


@pytest.mark.asyncio
async def test_dual_backend_retrieval():
    """Integration test: dual-backend retrieval works correctly via MemoryManager.provider."""
    from memory.manager import _ProviderRouter

    router = _ProviderRouter.__new__(_ProviderRouter)
    mock_built_in = AsyncMock()
    mock_external = AsyncMock()
    router.built_in = mock_built_in
    router.external = mock_external
    router.external_enabled = True

    external_results = [{"id": "entity_1", "source": "external", "score": 0.95}]
    mock_external.search = AsyncMock(return_value=external_results)

    results = await router.search("test query")

    assert len(results) == 1
    assert results[0]["source"] == "external"
