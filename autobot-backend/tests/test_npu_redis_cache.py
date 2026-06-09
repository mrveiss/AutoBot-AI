# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for NPU Redis L2 embedding cache (#8159).

Verifies that _l2_cache_get / _l2_cache_set and the integrated
_generate_optimized_embedding L1→L2→NPU path work correctly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_search_instance():
    """Return an NPUSemanticSearch with __init__ bypassed to avoid real I/O."""
    from npu_semantic_search import NPUSemanticSearch

    obj = NPUSemanticSearch.__new__(NPUSemanticSearch)
    obj._l1_hits = 0
    obj._l2_hits = 0
    obj._cache_misses = 0

    # Minimal embedding_cache stub
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.put = AsyncMock()
    obj.embedding_cache = cache

    return obj


def _embedding_bytes(arr: np.ndarray) -> bytes:
    return arr.astype(np.float32).tobytes()


# ---------------------------------------------------------------------------
# _l2_cache_get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_l2_cache_get_returns_array_on_hit():
    obj = _make_search_instance()
    expected = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=_embedding_bytes(expected))

    with patch("npu_semantic_search.get_async_redis_client", return_value=mock_redis):
        result = await obj._l2_cache_get("hello world")

    assert result is not None
    np.testing.assert_array_almost_equal(result, expected)


@pytest.mark.asyncio
async def test_l2_cache_get_returns_none_on_miss():
    obj = _make_search_instance()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("npu_semantic_search.get_async_redis_client", return_value=mock_redis):
        result = await obj._l2_cache_get("no such text")

    assert result is None


@pytest.mark.asyncio
async def test_l2_cache_get_returns_none_when_redis_unavailable():
    obj = _make_search_instance()

    with patch("npu_semantic_search.get_async_redis_client", return_value=None):
        result = await obj._l2_cache_get("text")

    assert result is None


@pytest.mark.asyncio
async def test_l2_cache_get_swallows_redis_exceptions():
    obj = _make_search_instance()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("redis down"))

    with patch("npu_semantic_search.get_async_redis_client", return_value=mock_redis):
        result = await obj._l2_cache_get("text")

    assert result is None


# ---------------------------------------------------------------------------
# _l2_cache_set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_l2_cache_set_stores_bytes():
    obj = _make_search_instance()
    embedding = np.array([1.0, 2.0, 3.0], dtype=np.float32)

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()

    with patch("npu_semantic_search.get_async_redis_client", return_value=mock_redis):
        await obj._l2_cache_set("store me", embedding)

    mock_redis.set.assert_awaited_once()
    call_args = mock_redis.set.call_args
    # key, value positional + ex keyword
    stored_bytes = call_args.args[1]
    recovered = np.frombuffer(stored_bytes, dtype=np.float32)
    np.testing.assert_array_almost_equal(recovered, embedding)
    assert call_args.kwargs.get("ex") is not None


@pytest.mark.asyncio
async def test_l2_cache_set_noop_when_redis_unavailable():
    obj = _make_search_instance()
    embedding = np.array([1.0], dtype=np.float32)

    with patch("npu_semantic_search.get_async_redis_client", return_value=None):
        # Should not raise
        await obj._l2_cache_set("text", embedding)


@pytest.mark.asyncio
async def test_l2_cache_set_swallows_redis_exceptions():
    obj = _make_search_instance()
    embedding = np.array([1.0], dtype=np.float32)

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(side_effect=ConnectionError("redis down"))

    with patch("npu_semantic_search.get_async_redis_client", return_value=mock_redis):
        await obj._l2_cache_set("text", embedding)  # must not raise


# ---------------------------------------------------------------------------
# _generate_optimized_embedding — L2 hit path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_optimized_embedding_l2_hit_warms_l1():
    """L2 hit must warm L1 and return 'l2_cached' device label."""
    obj = _make_search_instance()
    l2_embedding = np.array([0.5, 0.6], dtype=np.float32)

    with patch.object(obj, "_l2_cache_get", AsyncMock(return_value=l2_embedding)):
        with patch.object(obj, "_l2_cache_set", AsyncMock()):
            embedding, label = await obj._generate_optimized_embedding("query", True, None)

    assert label == "l2_cached"
    np.testing.assert_array_almost_equal(embedding, l2_embedding)
    # L1 must have been warmed
    obj.embedding_cache.put.assert_awaited_once()
    assert obj._l2_hits == 1
    assert obj._l1_hits == 0
    assert obj._cache_misses == 0


@pytest.mark.asyncio
async def test_generate_optimized_embedding_l1_hit_skips_l2():
    """L1 hit must not touch Redis at all."""
    obj = _make_search_instance()
    l1_embedding = [0.1, 0.2]
    obj.embedding_cache.get = AsyncMock(return_value=l1_embedding)

    with patch.object(obj, "_l2_cache_get", AsyncMock()) as mock_l2_get:
        embedding, label = await obj._generate_optimized_embedding("query", True, None)

    assert label == "l1_cached"
    mock_l2_get.assert_not_awaited()
    assert obj._l1_hits == 1
    assert obj._l2_hits == 0
    assert obj._cache_misses == 0


@pytest.mark.asyncio
async def test_generate_optimized_embedding_miss_populates_both_caches():
    """Full miss must call NPU, then populate L1 and L2."""
    obj = _make_search_instance()
    npu_embedding = np.array([9.0, 8.0], dtype=np.float32)

    with patch.object(obj, "_l2_cache_get", AsyncMock(return_value=None)):
        with patch.object(obj, "_l2_cache_set", AsyncMock()) as mock_l2_set:
            with patch.object(
                obj,
                "_generate_embedding_with_device",
                AsyncMock(return_value=(npu_embedding, "npu")),
            ):
                embedding, label = await obj._generate_optimized_embedding("new query", True, None)

    assert label == "npu"
    np.testing.assert_array_almost_equal(embedding, npu_embedding)
    obj.embedding_cache.put.assert_awaited_once()
    mock_l2_set.assert_awaited_once()
    assert obj._cache_misses == 1
    assert obj._l1_hits == 0
    assert obj._l2_hits == 0
