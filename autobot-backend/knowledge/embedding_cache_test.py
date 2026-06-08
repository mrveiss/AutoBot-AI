# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for Embedding Cache - Issue #65 P0 Optimization / Issue #8156 ARC
Tests the ARC cache with TTL for ChromaDB query embeddings.
"""

import asyncio

import pytest
import pytest_asyncio

from knowledge_base import EmbeddingCache, get_embedding_cache


@pytest.fixture
def cache():
    """Create a fresh embedding cache for each test"""
    return EmbeddingCache(maxsize=3, ttl_seconds=2)


@pytest_asyncio.fixture
async def global_cache():
    """Get the global cache instance"""
    cache = get_embedding_cache()
    await cache.clear()  # Reset for testing
    return cache


class TestEmbeddingCache:
    """Test embedding cache functionality"""

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, cache):
        """Test that cache miss returns None"""
        result = await cache.get("unknown query")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_returns_embedding(self, cache):
        """Test that cached embedding is returned"""
        query = "test query"
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        await cache.put(query, embedding)
        result = await cache.get(query)

        assert result == embedding

    @pytest.mark.asyncio
    async def test_cache_stats_tracking(self, cache):
        """Test that cache statistics are tracked correctly"""
        query = "test query"
        embedding = [0.1, 0.2, 0.3]

        # Initial stats
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        # Cache miss
        await cache.get(query)
        stats = cache.get_stats()
        assert stats["misses"] == 1

        # Add to cache
        await cache.put(query, embedding)

        # Cache hit
        await cache.get(query)
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["hit_rate_percent"] == 50.0

    @pytest.mark.asyncio
    async def test_lru_eviction(self, cache):
        """Test eviction when cache is full (cold-miss path uses T1)"""
        # Fill cache to capacity (maxsize=3)
        await cache.put("query1", [0.1])
        await cache.put("query2", [0.2])
        await cache.put("query3", [0.3])

        stats = cache.get_stats()
        assert stats["cache_size"] == 3

        # Add fourth entry - should evict one of the existing entries
        await cache.put("query4", [0.4])

        stats = cache.get_stats()
        assert stats["cache_size"] == 3

        # query1 should be evicted (oldest T1 entry, p starts at 0 so T1 evicted first)
        result1 = await cache.get("query1")
        assert result1 is None

        # Others should still be present
        result2 = await cache.get("query2")
        assert result2 == [0.2]

        result4 = await cache.get("query4")
        assert result4 == [0.4]

    @pytest.mark.asyncio
    async def test_promotion_t1_to_t2_on_second_hit(self, cache):
        """ARC-specific: second access promotes entry from T1 to T2"""
        await cache.put("query1", [0.1])
        await cache.put("query2", [0.2])

        stats = cache.get_stats()
        assert stats["t1_size"] == 2
        assert stats["t2_size"] == 0

        # First hit on query1: still in T1 initially, promoted to T2 on get
        result = await cache.get("query1")
        assert result == [0.1]

        stats = cache.get_stats()
        assert stats["t1_size"] == 1  # query2 remains in T1
        assert stats["t2_size"] == 1  # query1 promoted to T2

    @pytest.mark.asyncio
    async def test_t2_entries_survive_scan(self, cache):
        """ARC-specific: scan workload (1001 unique queries) does not evict hot T2 entries"""
        # Use a larger cache for this test
        big_cache = EmbeddingCache(maxsize=100, ttl_seconds=3600)

        hot_queries = [f"hot_{i}" for i in range(5)]
        hot_embeddings = {q: [float(i)] for i, q in enumerate(hot_queries)}

        # Warm up hot set — put then get to promote into T2
        for q in hot_queries:
            await big_cache.put(q, hot_embeddings[q])
        for q in hot_queries:
            await big_cache.get(q)  # promotes to T2

        stats = big_cache.get_stats()
        assert stats["t2_size"] == 5

        # Scan 1001 unique queries to fill cache many times over
        for i in range(1001):
            scan_q = f"scan_unique_{i}"
            await big_cache.put(scan_q, [float(i)])

        # Hot set should still be retrievable (ARC protects T2 from scans)
        for q in hot_queries:
            result = await big_cache.get(q)
            assert result == hot_embeddings[q], f"Hot entry {q!r} was evicted by scan workload"

    @pytest.mark.asyncio
    async def test_eviction_prefers_t1_over_t2(self, cache):
        """ARC-specific: evict(count) removes from T1 before T2"""
        big_cache = EmbeddingCache(maxsize=10, ttl_seconds=3600)

        # Put 4 entries and promote 2 into T2
        for i in range(4):
            await big_cache.put(f"q{i}", [float(i)])
        await big_cache.get("q0")  # promotes q0 to T2
        await big_cache.get("q1")  # promotes q1 to T2

        stats = big_cache.get_stats()
        assert stats["t2_size"] == 2
        assert stats["t1_size"] == 2  # q2, q3

        # Evict 1 — should come from T1 (q2 is oldest T1 entry)
        evicted = big_cache.evict(1)
        assert evicted == 1

        stats = big_cache.get_stats()
        assert stats["t1_size"] == 1
        assert stats["t2_size"] == 2  # T2 untouched

    @pytest.mark.asyncio
    async def test_get_stats_returns_t1_and_t2_sizes(self, cache):
        """get_stats() must expose t1_size and t2_size for monitoring"""
        stats = cache.get_stats()
        assert "t1_size" in stats
        assert "t2_size" in stats
        assert isinstance(stats["t1_size"], int)
        assert isinstance(stats["t2_size"], int)

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, cache):
        """Test that entries expire after TTL"""
        query = "expiring query"
        embedding = [0.1, 0.2, 0.3]

        await cache.put(query, embedding)

        # Immediately should be available
        result = await cache.get(query)
        assert result == embedding

        # Wait for TTL to expire (2 seconds) - Issue #479: Use async sleep
        await asyncio.sleep(2.1)

        # Should be expired now
        result = await cache.get(query)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_clear(self, cache):
        """Test that clearing cache removes all entries"""
        await cache.put("query1", [0.1])
        await cache.put("query2", [0.2])

        stats = cache.get_stats()
        assert stats["cache_size"] == 2
        assert stats["misses"] == 0

        await cache.clear()

        stats = cache.get_stats()
        assert stats["cache_size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["t1_size"] == 0
        assert stats["t2_size"] == 0

        # Entries should be gone
        result = await cache.get("query1")
        assert result is None

    @pytest.mark.asyncio
    async def test_case_sensitive_keys(self, cache):
        """Test that query keys are case sensitive"""
        await cache.put("Query", [0.1])
        await cache.put("query", [0.2])
        await cache.put("QUERY", [0.3])

        result1 = await cache.get("Query")
        result2 = await cache.get("query")
        result3 = await cache.get("QUERY")

        assert result1 == [0.1]
        assert result2 == [0.2]
        assert result3 == [0.3]

        stats = cache.get_stats()
        assert stats["cache_size"] == 3

    @pytest.mark.asyncio
    async def test_global_cache_singleton(self, global_cache):
        """Test that global cache is a singleton"""
        cache1 = get_embedding_cache()
        cache2 = get_embedding_cache()

        assert cache1 is cache2

    @pytest.mark.asyncio
    async def test_stats_hit_rate_calculation(self, cache):
        """Test hit rate percentage calculation"""
        # 3 hits, 1 miss = 75% hit rate
        await cache.put("query", [0.1])

        await cache.get("nonexistent")  # miss
        await cache.get("query")  # hit
        await cache.get("query")  # hit
        await cache.get("query")  # hit

        stats = cache.get_stats()
        assert stats["hits"] == 3
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == 75.0

    @pytest.mark.asyncio
    async def test_update_existing_entry(self, cache):
        """Test that putting an existing key updates its value"""
        await cache.put("query", [0.1])
        await cache.put("query", [0.2])

        result = await cache.get("query")
        assert result == [0.2]

        # Should not increase cache size
        stats = cache.get_stats()
        assert stats["cache_size"] == 1

    @pytest.mark.asyncio
    async def test_large_embedding_vectors(self, cache):
        """Test caching of large embedding vectors (typical 384-1536 dimensions)"""
        large_embedding = [0.01 * i for i in range(1536)]

        await cache.put("large query", large_embedding)
        result = await cache.get("large query")

        assert result == large_embedding
        assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_concurrent_access(self, cache):
        """Test cache handles concurrent access correctly"""

        async def put_then_get(query, embedding):
            await cache.put(query, embedding)
            await asyncio.sleep(0.01)
            return await cache.get(query)

        # Run concurrent operations
        tasks = [put_then_get(f"query{i}", [float(i)]) for i in range(3)]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert results[0] == [0.0]
        assert results[1] == [1.0]
        assert results[2] == [2.0]


class TestEmbeddingCacheIntegration:
    """Integration tests for embedding cache with knowledge base"""

    @pytest.mark.asyncio
    async def test_cache_stats_in_knowledge_base(self, global_cache):
        """Test that cache stats appear in knowledge base stats"""
        # Simulate some cache activity
        await global_cache.put("test", [0.1, 0.2])
        await global_cache.get("test")
        await global_cache.get("miss")

        stats = global_cache.get_stats()

        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate_percent" in stats
        assert "cache_size" in stats
        assert "t1_size" in stats
        assert "t2_size" in stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
