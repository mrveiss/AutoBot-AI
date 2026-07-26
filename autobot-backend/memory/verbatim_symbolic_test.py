# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for B1 (#12555) — symbolic drawer index over the verbatim store.

Covers term extraction, the flag-off/no-term/no-candidate fallback contract
(returns None so the caller uses semantic search), index write/cleanup, and the
overlap+recency ranking of the symbolic search path. Redis and the ChromaDB
collection are faked so no infra is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import memory.verbatim_store as vs
from memory.verbatim_store import VerbatimStore, _extract_terms


class _FakePipe:
    def __init__(self, redis):
        self._redis = redis
        self.ops = []

    def sadd(self, key, *vals):
        self.ops.append(("sadd", key, vals))
        self._redis.sets.setdefault(key, set()).update(vals)
        return self

    def srem(self, key, *vals):
        self.ops.append(("srem", key, vals))
        self._redis.sets.get(key, set()).difference_update(vals)
        return self

    def delete(self, key):
        self.ops.append(("delete", key))
        self._redis.sets.pop(key, None)
        return self

    async def execute(self):
        return [True] * len(self.ops)


class _FakeRedis:
    def __init__(self):
        self.sets: dict = {}

    def pipeline(self):
        return _FakePipe(self)

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def sunion(self, keys):
        out: set = set()
        for k in keys:
            out |= self.sets.get(k, set())
        return out


@pytest.fixture
def fake_redis(monkeypatch):
    r = _FakeRedis()
    monkeypatch.setattr(
        "autobot_shared.redis_client.get_redis_client",
        AsyncMock(return_value=r),
    )
    return r


def _store_with_collection(collection):
    store = VerbatimStore()
    store._collection = collection  # bypass lazy init
    return store


# ---- term extraction -------------------------------------------------------


def test_extract_terms_drops_stopwords_and_short():
    terms = _extract_terms("What did we decide about ClientX pricing in March")
    assert "clientx" in terms
    assert "pricing" in terms
    assert "march" in terms
    assert "did" not in terms  # stopword
    assert "we" not in terms  # too short


# ---- fallback contract -----------------------------------------------------


@pytest.mark.asyncio
async def test_search_symbolic_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(vs, "_SYMBOLIC_INDEX_ENABLED", False)
    store = VerbatimStore()
    assert await store.search_symbolic("clientx pricing") is None


@pytest.mark.asyncio
async def test_search_symbolic_returns_none_without_terms(monkeypatch, fake_redis):
    monkeypatch.setattr(vs, "_SYMBOLIC_INDEX_ENABLED", True)
    store = VerbatimStore()
    assert await store.search_symbolic("did we the") is None  # all stopwords/short


@pytest.mark.asyncio
async def test_search_symbolic_returns_none_when_no_candidates(monkeypatch, fake_redis):
    monkeypatch.setattr(vs, "_SYMBOLIC_INDEX_ENABLED", True)
    store = VerbatimStore()
    assert await store.search_symbolic("clientx pricing") is None  # empty index


# ---- index write + search --------------------------------------------------


@pytest.mark.asyncio
async def test_index_and_search_roundtrip(monkeypatch, fake_redis):
    monkeypatch.setattr(vs, "_SYMBOLIC_INDEX_ENABLED", True)
    collection = MagicMock()
    collection.get = AsyncMock(
        return_value={
            "ids": ["c1", "c2"],
            "documents": [
                "We agreed ClientX pricing stays flat",
                "Unrelated note about lunch",
            ],
            "metadatas": [
                {"session_id": "s1", "timestamp": "2026-07-25T00:00:00+00:00"},
                {"session_id": "s1", "timestamp": "2026-07-01T00:00:00+00:00"},
            ],
        }
    )
    store = _store_with_collection(collection)
    # Seed the inverted index as append() would.
    await store._index_symbolic("c1", "We agreed ClientX pricing stays flat")
    await store._index_symbolic("c2", "Unrelated note about lunch")

    results = await store.search_symbolic("ClientX pricing")
    assert results is not None
    assert results[0]["id"] == "c1"  # highest term overlap
    assert results[0]["score"] > results[-1]["score"]


@pytest.mark.asyncio
async def test_search_symbolic_respects_session_filter(monkeypatch, fake_redis):
    monkeypatch.setattr(vs, "_SYMBOLIC_INDEX_ENABLED", True)
    collection = MagicMock()
    collection.get = AsyncMock(
        return_value={
            "ids": ["c1"],
            "documents": ["ClientX pricing note"],
            "metadatas": [{"session_id": "other", "timestamp": "2026-07-25T00:00:00+00:00"}],
        }
    )
    store = _store_with_collection(collection)
    await store._index_symbolic("c1", "ClientX pricing note")
    results = await store.search_symbolic("clientx pricing", session_filter="s1")
    assert results == []  # candidate belongs to a different session


@pytest.mark.asyncio
async def test_over_broad_query_defers_to_semantic(monkeypatch, fake_redis):
    # A term matching more than the cap => not an entity query => return None so
    # the caller falls back to semantic search (no giant ChromaDB fetch).
    monkeypatch.setattr(vs, "_SYMBOLIC_INDEX_ENABLED", True)
    monkeypatch.setattr(vs, "_SYM_MAX_CANDIDATES", 3)
    for i in range(5):
        await VerbatimStore()._index_symbolic(f"c{i}", "pricing pricing pricing")
    collection = MagicMock()
    collection.get = AsyncMock()
    store = _store_with_collection(collection)
    assert await store.search_symbolic("pricing") is None
    collection.get.assert_not_awaited()  # never fetched the oversized set


@pytest.mark.asyncio
async def test_deindex_removes_chunk_from_terms(monkeypatch, fake_redis):
    monkeypatch.setattr(vs, "_SYMBOLIC_INDEX_ENABLED", True)
    store = VerbatimStore()
    await store._index_symbolic("c1", "ClientX pricing")
    assert "c1" in fake_redis.sets[vs._SYM_TERM_KEY.format(term="clientx")]
    await store._deindex_symbolic(["c1"])
    assert "c1" not in fake_redis.sets.get(vs._SYM_TERM_KEY.format(term="clientx"), set())
    assert vs._SYM_CHUNK_KEY.format(chunk_id="c1") not in fake_redis.sets
