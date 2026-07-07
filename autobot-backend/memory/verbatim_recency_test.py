# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Recency-weighted verbatim recall (GH#11163).

Covers the exponential decay factor and that VerbatimStore.search() re-ranks
equally-similar chunks so recent turns win, while weight 0 preserves the prior
pure-semantic order.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from memory import verbatim_store
from memory.verbatim_store import VerbatimStore, _recency_factor


def _make_collection(items: List[Dict[str, Any]]) -> MagicMock:
    """Mock collection: each item is {id, text, distance, timestamp}."""
    collection = MagicMock()

    async def _query(query_texts=None, n_results=10, where=None, include=None):
        limit = min(n_results, len(items))
        sliced = items[:limit]
        return {
            "ids": [[i["id"] for i in sliced]],
            "documents": [[i["text"] for i in sliced]],
            "metadatas": [[{"timestamp": i["timestamp"]} for i in sliced]],
            "distances": [[i["distance"] for i in sliced]],
        }

    collection.query = _query
    return collection


def _store(items: List[Dict[str, Any]]) -> VerbatimStore:
    store = VerbatimStore()
    store._collection = _make_collection(items)
    return store


# --- _recency_factor -------------------------------------------------------


def test_recency_factor_now_is_one():
    now = datetime.now(tz=timezone.utc)
    assert _recency_factor(now.isoformat(), now) == 1.0


def test_recency_factor_halves_at_half_life():
    now = datetime.now(tz=timezone.utc)
    half_life = verbatim_store._RECENCY_HALFLIFE_SECONDS
    ts = (now - timedelta(seconds=half_life)).isoformat()
    assert _recency_factor(ts, now) == pytest.approx(0.5, abs=1e-6)


def test_recency_factor_missing_or_bad_returns_none():
    now = datetime.now(tz=timezone.utc)
    assert _recency_factor(None, now) is None
    assert _recency_factor("not-a-date", now) is None


def test_recency_factor_naive_timestamp_treated_as_utc():
    now = datetime.now(tz=timezone.utc)
    naive = now.replace(tzinfo=None).isoformat()
    assert _recency_factor(naive, now) == pytest.approx(1.0, abs=1e-3)


# --- search re-ranking -----------------------------------------------------


@pytest.mark.asyncio
async def test_search_recent_beats_equally_similar_stale(monkeypatch):
    monkeypatch.setattr(verbatim_store, "_RECENCY_WEIGHT", 0.5)
    now = datetime.now(tz=timezone.utc)
    old = (now - timedelta(days=60)).isoformat()
    # Same distance (equally similar); stale one is listed first by the vector store.
    store = _store(
        [
            {"id": "stale", "text": "old", "distance": 0.1, "timestamp": old},
            {"id": "fresh", "text": "new", "distance": 0.1, "timestamp": now.isoformat()},
        ]
    )
    results = await store.search("q")
    assert [r["id"] for r in results] == ["fresh", "stale"]
    assert results[0]["score"] > results[1]["score"]


@pytest.mark.asyncio
async def test_search_weight_zero_preserves_semantic_order(monkeypatch):
    monkeypatch.setattr(verbatim_store, "_RECENCY_WEIGHT", 0.0)
    now = datetime.now(tz=timezone.utc)
    old = (now - timedelta(days=60)).isoformat()
    store = _store(
        [
            {"id": "closer_old", "text": "a", "distance": 0.1, "timestamp": old},
            {"id": "farther_new", "text": "b", "distance": 0.4, "timestamp": now.isoformat()},
        ]
    )
    results = await store.search("q")
    # Weight 0 → pure semantic: the closer (lower distance) chunk stays first.
    assert [r["id"] for r in results] == ["closer_old", "farther_new"]
    assert results[0]["score"] == pytest.approx(0.9)
