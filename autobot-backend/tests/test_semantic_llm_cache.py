# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for SemanticLLMCache — Issue #8168.

Uses pure-Python / numpy assertions; does not import from llm_shared.cache
or any service module so the test runs without external infrastructure.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from llm_shared.semantic_cache import SemanticLLMCache


def _resp(content="answer"):
    """Minimal stand-in for CachedResponse — SemanticLLMCache is type-agnostic."""
    return SimpleNamespace(content=content, model="test")


def _unit_vec(dim=4, seed=0):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# Exact-cache tier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_hit_skips_semantic():
    """Tier-1 exact match must not invoke the semantic (embedding) tier."""
    exact = MagicMock()
    response = _resp("exact hit")
    exact.get = AsyncMock(return_value=response)
    exact.set = AsyncMock()

    sc = SemanticLLMCache(exact)

    with patch.object(sc, "_embed", new_callable=AsyncMock) as mock_embed:
        result = await sc.get("key1", prompt="What is Docker?")

    assert result.content == "exact hit"
    mock_embed.assert_not_called()


@pytest.mark.asyncio
async def test_exact_miss_without_prompt_returns_none():
    exact = MagicMock()
    exact.get = AsyncMock(return_value=None)

    sc = SemanticLLMCache(exact)

    result = await sc.get("key1", prompt=None)
    assert result is None


# ---------------------------------------------------------------------------
# Semantic tier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semantic_hit_for_similar_prompt():
    """Cosine-similar prompt (≥ threshold) should return a cached response."""
    exact = MagicMock()
    exact.get = AsyncMock(return_value=None)
    exact.set = AsyncMock()

    sc = SemanticLLMCache(exact, threshold=0.95)

    stored_vec = _unit_vec(dim=4, seed=1)
    stored_response = _resp("semantic cached answer")
    async with sc._lock:
        sc._add_entry(stored_vec, "key_stored", stored_response)

    # Identical vector → cosine similarity = 1.0 (well above 0.95 threshold)
    with patch.object(sc, "_embed", new_callable=AsyncMock, return_value=stored_vec.copy()):
        result = await sc.get("key_new", prompt="What is Docker?")

    assert result is not None
    assert result.content == "semantic cached answer"
    assert sc._stats["semantic_hits"] == 1


@pytest.mark.asyncio
async def test_semantic_miss_for_dissimilar_prompt():
    """Orthogonal (cosine = 0) prompt must produce a cache miss."""
    exact = MagicMock()
    exact.get = AsyncMock(return_value=None)

    sc = SemanticLLMCache(exact, threshold=0.95)

    stored_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    async with sc._lock:
        sc._add_entry(stored_vec, "key_stored", _resp("some answer"))

    orthogonal = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)

    with patch.object(sc, "_embed", new_callable=AsyncMock, return_value=orthogonal):
        result = await sc.get("key_ortho", prompt="install nginx")

    assert result is None
    assert sc._stats["semantic_misses"] >= 1


@pytest.mark.asyncio
async def test_long_prompt_skips_semantic():
    """Prompts exceeding max_prompt_chars must skip the semantic tier entirely."""
    exact = MagicMock()
    exact.get = AsyncMock(return_value=None)

    sc = SemanticLLMCache(exact, max_prompt_chars=100)
    long_prompt = "x" * 200

    with patch.object(sc, "_embed", new_callable=AsyncMock) as mock_embed:
        result = await sc.get("key_long", prompt=long_prompt)

    assert result is None
    mock_embed.assert_not_called()


# ---------------------------------------------------------------------------
# set() registers embedding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_registers_embedding_in_index():
    exact = MagicMock()
    exact.set = AsyncMock()

    sc = SemanticLLMCache(exact)
    stored_vec = _unit_vec(dim=4, seed=5)
    response = _resp("stored")

    with patch.object(sc, "_embed", new_callable=AsyncMock, return_value=stored_vec):
        await sc.set("key1", response, prompt="some prompt")

    assert sc._stats["entries"] == 1


# ---------------------------------------------------------------------------
# Eviction
# ---------------------------------------------------------------------------


def test_eviction_when_index_full():
    exact = MagicMock()
    sc = SemanticLLMCache(exact, max_entries=3)

    for i in range(4):
        sc._add_entry(_unit_vec(dim=4, seed=i), f"key{i}", _resp(f"resp{i}"))

    assert len(sc._entries) == 3, "Index should evict oldest when full"
    assert sc._entries[0][0] == "key1", "key0 (oldest) should have been evicted"
    assert "key0" not in sc._entry_keys, "Evicted key must be removed from _entry_keys"
    assert "key1" in sc._entry_keys


def test_add_entry_deduplicates_by_cache_key():
    exact = MagicMock()
    sc = SemanticLLMCache(exact)

    sc._add_entry(_unit_vec(dim=4, seed=1), "dup_key", _resp("first"))
    sc._add_entry(_unit_vec(dim=4, seed=2), "dup_key", _resp("second"))

    assert sc._stats["entries"] == 1, "Duplicate cache_key must not add a second entry"
    assert sc._entries[0][1].content == "first", "Original entry must be preserved"


# ---------------------------------------------------------------------------
# Delegate methods
# ---------------------------------------------------------------------------


def test_evict_delegates_to_exact():
    exact = MagicMock()
    exact.evict = MagicMock(return_value=3)
    sc = SemanticLLMCache(exact)
    assert sc.evict(3) == 3
    exact.evict.assert_called_once_with(3)


@pytest.mark.asyncio
async def test_clear_resets_index():
    exact = MagicMock()
    sc = SemanticLLMCache(exact)
    sc._add_entry(_unit_vec(4), "k", _resp())
    assert sc._stats["entries"] == 1

    await sc.clear()
    assert len(sc._entries) == 0
    assert len(sc._entry_keys) == 0
    assert sc._stats["entries"] == 0
    exact.clear.assert_called_once()


def test_generate_cache_key_delegates():
    exact = MagicMock()
    exact.generate_cache_key = MagicMock(return_value="delegated_key")
    sc = SemanticLLMCache(exact)
    key = sc.generate_cache_key([{"role": "user", "content": "hi"}], "gemma3", 0.5)
    assert key == "delegated_key"
