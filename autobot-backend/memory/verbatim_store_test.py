# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for VerbatimStore (Issue #5070).

Tests cover:
- append + search roundtrip (mocked ChromaDB)
- append-only semantics (no deletes during write)
- session_filter scoping
- delete_session
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from memory.verbatim_store import VerbatimStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_collection(stored: List[Dict[str, Any]] | None = None) -> MagicMock:
    """Return a mock AsyncChromaCollection pre-wired with canned query results."""
    if stored is None:
        stored = []

    collection = MagicMock()
    collection.add = AsyncMock()
    collection.delete = AsyncMock()

    async def _query(
        query_texts=None,
        n_results=10,
        where=None,
        include=None,
    ):
        items = stored
        if where and "$eq" in str(where):
            # Simple session_id filter emulation
            sid = where.get("session_id", {}).get("$eq")
            if sid:
                items = [i for i in stored if i.get("session_id") == sid]
        limit = min(n_results, len(items))
        return {
            "ids": [[i["id"] for i in items[:limit]]],
            "documents": [[i["text"] for i in items[:limit]]],
            "metadatas": [[{"session_id": i.get("session_id", ""), "role": i.get("role", "")} for i in items[:limit]]],
            "distances": [[0.1 * j for j in range(limit)]],
        }

    async def _get(where=None, include=None):
        sid = (where or {}).get("session_id", {}).get("$eq")
        items = [i for i in stored if i.get("session_id") == sid] if sid else stored
        return {"ids": [i["id"] for i in items]}

    collection.query = _query
    collection.get = _get
    return collection


async def _store_with_collection(collection: MagicMock) -> VerbatimStore:
    """Return a VerbatimStore whose internal collection is already set."""
    store = VerbatimStore()
    store._collection = collection
    return store


# ---------------------------------------------------------------------------
# Tests: append
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_returns_chunk_id():
    col = _make_collection()
    store = await _store_with_collection(col)

    chunk_id = await store.append(
        session_id="sess-1",
        turn=0,
        role="user",
        text="Hello, world!",
    )

    assert chunk_id.startswith("sess-1_t0_user_")
    col.add.assert_called_once()


@pytest.mark.asyncio
async def test_append_uses_add_not_upsert():
    """Append must be append-only — must call add(), never upsert()."""
    col = _make_collection()
    col.upsert = AsyncMock()
    store = await _store_with_collection(col)

    await store.append(session_id="sess-2", turn=1, role="assistant", text="Hi!")

    col.add.assert_called_once()
    col.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_append_stores_metadata():
    captured = {}

    async def _add(ids, documents, metadatas, **_):
        captured["ids"] = ids
        captured["metadatas"] = metadatas

    col = _make_collection()
    col.add = _add
    store = await _store_with_collection(col)

    ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await store.append(
        session_id="s1",
        turn=3,
        role="user",
        text="query text",
        timestamp=ts,
        user_id="u42",
    )

    meta = captured["metadatas"][0]
    assert meta["session_id"] == "s1"
    assert meta["turn"] == 3
    assert meta["role"] == "user"
    assert meta["user_id"] == "u42"
    assert "2025-01-01" in meta["timestamp"]


@pytest.mark.asyncio
async def test_append_rejects_empty_text():
    col = _make_collection()
    store = await _store_with_collection(col)

    with pytest.raises(ValueError, match="text cannot be empty"):
        await store.append(session_id="s1", turn=0, role="user", text="")


@pytest.mark.asyncio
async def test_append_rejects_invalid_role():
    col = _make_collection()
    store = await _store_with_collection(col)

    with pytest.raises(ValueError, match="role must be"):
        await store.append(session_id="s1", turn=0, role="system", text="ok")


# ---------------------------------------------------------------------------
# Tests: search
# ---------------------------------------------------------------------------

_STORED = [
    {"id": "s1_t0_user_aa", "text": "How do I reset the system?", "session_id": "s1", "role": "user"},
    {"id": "s1_t0_asst_bb", "text": "Use the reset command.", "session_id": "s1", "role": "assistant"},
    {"id": "s2_t0_user_cc", "text": "What is the weather?", "session_id": "s2", "role": "user"},
]


@pytest.mark.asyncio
async def test_search_returns_results():
    col = _make_collection(_STORED)
    store = await _store_with_collection(col)

    results = await store.search("reset system")

    assert len(results) >= 1
    assert all("text" in r and "score" in r and "id" in r for r in results)


@pytest.mark.asyncio
async def test_search_session_filter():
    col = _make_collection(_STORED)
    store = await _store_with_collection(col)

    results = await store.search("weather", session_filter="s2")

    # All returned results should be from session s2
    assert all(r["metadata"]["session_id"] == "s2" for r in results)


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty():
    col = _make_collection(_STORED)
    store = await _store_with_collection(col)

    results = await store.search("")
    assert results == []


@pytest.mark.asyncio
async def test_search_invalid_limit_raises():
    col = _make_collection()
    store = await _store_with_collection(col)

    with pytest.raises(ValueError, match="limit must be positive"):
        await store.search("query", limit=0)


# ---------------------------------------------------------------------------
# Tests: delete_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_session_removes_chunks():
    col = _make_collection(list(_STORED))
    store = await _store_with_collection(col)

    deleted = await store.delete_session("s1")

    assert deleted == 2  # Two chunks in session s1
    col.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_session_empty_returns_zero():
    col = _make_collection([])
    store = await _store_with_collection(col)

    deleted = await store.delete_session("nonexistent-session")

    assert deleted == 0
    col.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_session_rejects_empty_id():
    col = _make_collection()
    store = await _store_with_collection(col)

    with pytest.raises(ValueError, match="session_id cannot be empty"):
        await store.delete_session("")
