# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Contract tests for ``AsyncBaseCollection`` / ``AsyncBaseClient`` (Issue #5316).

Mirror of ``test_base.py`` — same semantics, same parametrization, but every
test awaits async methods. Any new async backend (Qdrant, LanceDB, pgvector…)
only needs a fixture appended to ``_BACKENDS`` below.
"""

from __future__ import annotations

from typing import Callable

import pytest

from knowledge.backends.async_base import AsyncBaseClient, AsyncBaseCollection
from knowledge.backends.async_chromadb_adapter import AsyncChromaDBClient
from knowledge.backends.async_memory_adapter import AsyncInMemoryClient

# --- fixture factories ------------------------------------------------------
#
# Same rationale as test_base.py: ChromaDB 1.x EphemeralClient leaks state
# across instances in the same process, so we use a per-test PersistentClient
# pointed at a fresh temp directory. The async adapter wraps an
# AsyncChromaClient, which itself wraps the raw PersistentClient.


def _memory_client(tmp_path) -> AsyncBaseClient:  # tmp_path unused
    return AsyncInMemoryClient()


def _chromadb_client(tmp_path) -> AsyncBaseClient:
    chromadb = pytest.importorskip("chromadb")
    from utils.async_chromadb_client import AsyncChromaClient

    raw_sync = chromadb.PersistentClient(path=str(tmp_path))
    return AsyncChromaDBClient(AsyncChromaClient(raw_sync))


# Adding a new adapter? Append (name, factory) here.
_BACKENDS: list[tuple[str, Callable[..., AsyncBaseClient]]] = [
    ("memory", _memory_client),
    ("chromadb", _chromadb_client),
]


@pytest.fixture(params=_BACKENDS, ids=[name for name, _ in _BACKENDS])
def client(request, tmp_path) -> AsyncBaseClient:
    _name, factory = request.param
    return factory(tmp_path)


@pytest.fixture
async def collection(client: AsyncBaseClient) -> AsyncBaseCollection:
    return await client.get_or_create_collection("contract-test")


# --- collection contract ----------------------------------------------------


async def test_add_then_count(collection: AsyncBaseCollection) -> None:
    await collection.add(
        ids=["a", "b", "c"],
        documents=["doc-a", "doc-b", "doc-c"],
        metadatas=[{"n": 1}, {"n": 2}, {"n": 3}],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
    )
    assert await collection.count() == 3


async def test_add_duplicate_retains_original(
    collection: AsyncBaseCollection,
) -> None:
    """ChromaDB 1.x contract: add() on a duplicate id is a no-op."""
    await collection.add(ids=["dup"], documents=["first"], embeddings=[[1.0, 0.0]])
    await collection.add(ids=["dup"], documents=["second"], embeddings=[[0.0, 1.0]])
    assert await collection.count() == 1
    got = await collection.get(ids=["dup"])
    assert got["documents"] == ["first"]


async def test_get_by_ids_returns_flat_lists(
    collection: AsyncBaseCollection,
) -> None:
    await collection.add(
        ids=["a", "b"],
        documents=["doc-a", "doc-b"],
        metadatas=[{"n": 1}, {"n": 2}],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
    )
    got = await collection.get(ids=["a"])
    assert got["ids"] == ["a"]
    assert got["documents"] == ["doc-a"]
    assert not isinstance(got["ids"][0], list)


async def test_query_returns_nested_lists_ordered_by_distance(
    collection: AsyncBaseCollection,
) -> None:
    await collection.add(
        ids=["near", "far"],
        documents=["near-doc", "far-doc"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
    )
    got = await collection.query(
        query_embeddings=[[1.0, 0.0]],
        n_results=2,
    )
    assert isinstance(got["ids"], list)
    assert isinstance(got["ids"][0], list)
    assert got["ids"][0][0] == "near"


async def test_delete_by_ids_reduces_count(
    collection: AsyncBaseCollection,
) -> None:
    await collection.add(ids=["a", "b"], documents=["x", "y"], embeddings=[[1.0, 0.0], [0.0, 1.0]])
    await collection.delete(ids=["a"])
    assert await collection.count() == 1
    got_a = await collection.get(ids=["a"])
    assert got_a["ids"] == []


async def test_upsert_replaces_existing(
    collection: AsyncBaseCollection,
) -> None:
    await collection.add(ids=["a"], documents=["first"], embeddings=[[1.0, 0.0]])
    await collection.upsert(ids=["a"], documents=["second"], embeddings=[[0.0, 1.0]])
    assert await collection.count() == 1
    got = await collection.get(ids=["a"])
    assert got["documents"] == ["second"]


async def test_empty_query_returns_empty_inner_lists(
    collection: AsyncBaseCollection,
) -> None:
    got = await collection.query(query_embeddings=[[1.0, 0.0]], n_results=5)
    assert got["ids"] == [[]]


async def test_peek_returns_flat_lists(
    collection: AsyncBaseCollection,
) -> None:
    await collection.add(ids=["a", "b"], documents=["x", "y"], embeddings=[[1.0, 0.0], [0.0, 1.0]])
    peek = await collection.peek(limit=1)
    assert len(peek["ids"]) == 1
    assert not isinstance(peek["ids"][0], list)


# --- client contract --------------------------------------------------------


async def test_get_or_create_is_idempotent(client: AsyncBaseClient) -> None:
    a = await client.get_or_create_collection("dup-collection")
    b = await client.get_or_create_collection("dup-collection")
    await a.add(ids=["x"], documents=["hello"], embeddings=[[1.0, 0.0]])
    assert await b.count() == 1


async def test_get_collection_missing_raises(client: AsyncBaseClient) -> None:
    with pytest.raises(ValueError):
        await client.get_collection("does-not-exist")


async def test_create_collection_twice_raises(client: AsyncBaseClient) -> None:
    await client.create_collection("only-once")
    with pytest.raises(ValueError):
        await client.create_collection("only-once")


async def test_delete_collection_missing_raises(
    client: AsyncBaseClient,
) -> None:
    with pytest.raises(ValueError):
        await client.delete_collection("never-existed")


async def test_list_collections_reflects_state(
    client: AsyncBaseClient,
) -> None:
    await client.create_collection("alpha")
    await client.create_collection("beta")
    cols = await client.list_collections()
    assert len(cols) >= 2


async def test_list_collections_returns_async_base_collection_instances(
    client: AsyncBaseClient,
) -> None:
    """Every adapter MUST return ``AsyncBaseCollection`` instances so callers
    can await .add/.get/.query uniformly regardless of backend (#5134)."""
    await client.create_collection("alpha")
    cols = await client.list_collections()
    assert cols, "list_collections returned empty"
    for col in cols:
        assert isinstance(
            col, AsyncBaseCollection
        ), f"list_collections must wrap raw backend objects, got {type(col)!r}"


# --- update / where-filter / pagination contract (Issue #5135) --------------


async def test_update_replaces_document_and_metadata(
    collection: AsyncBaseCollection,
) -> None:
    await collection.add(
        ids=["a", "b", "c"],
        documents=["doc-a", "doc-b", "doc-c"],
        metadatas=[{"n": 1}, {"n": 2}, {"n": 3}],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
    )
    await collection.update(
        ids=["b"],
        documents=["doc-b-v2"],
        metadatas=[{"n": 20}],
        embeddings=[[0.0, 1.0]],
    )
    got_b = await collection.get(ids=["b"])
    assert got_b["documents"] == ["doc-b-v2"]
    assert got_b["metadatas"] == [{"n": 20}]
    got_a = await collection.get(ids=["a"])
    assert got_a["documents"] == ["doc-a"]
    assert got_a["metadatas"] == [{"n": 1}]
    got_c = await collection.get(ids=["c"])
    assert got_c["documents"] == ["doc-c"]
    assert got_c["metadatas"] == [{"n": 3}]


async def test_update_preserves_ordering(
    collection: AsyncBaseCollection,
) -> None:
    await collection.add(
        ids=["a", "b", "c", "d"],
        documents=["doc-a", "doc-b", "doc-c", "doc-d"],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.5, 0.5]],
    )
    before = (await collection.get(ids=["a", "b", "c", "d"]))["ids"]
    await collection.update(ids=["c"], documents=["doc-c-v2"], embeddings=[[1.0, 1.0]])
    after = (await collection.get(ids=["a", "b", "c", "d"]))["ids"]
    assert before == after == ["a", "b", "c", "d"]


async def test_update_duplicate_id_raises(
    collection: AsyncBaseCollection,
) -> None:
    """Regression for #5133: duplicate ids in a single update() call must
    surface an error rather than silently reusing the first occurrence's
    aligned values."""
    await collection.add(
        ids=["a"],
        documents=["doc-a"],
        embeddings=[[1.0, 0.0]],
    )
    with pytest.raises(Exception):
        await collection.update(
            ids=["a", "a"],
            documents=["first", "second"],
            embeddings=[[0.5, 0.5], [0.25, 0.75]],
        )


async def test_query_with_where_filter_matches_metadata(
    collection: AsyncBaseCollection,
) -> None:
    await collection.add(
        ids=["a", "b", "c"],
        documents=["doc-a", "doc-b", "doc-c"],
        metadatas=[
            {"source": "x"},
            {"source": "y"},
            {"source": "x"},
        ],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]],
    )
    got = await collection.query(
        query_embeddings=[[1.0, 0.0]],
        n_results=5,
        where={"source": "x"},
    )
    assert set(got["ids"][0]) == {"a", "c"}
    for meta in got["metadatas"][0]:
        assert meta["source"] == "x"


async def test_get_with_where_filter_returns_only_matching(
    collection: AsyncBaseCollection,
) -> None:
    await collection.add(
        ids=["a", "b", "c"],
        documents=["doc-a", "doc-b", "doc-c"],
        metadatas=[
            {"source": "x"},
            {"source": "y"},
            {"source": "x"},
        ],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]],
    )
    got = await collection.get(where={"source": "x"})
    assert set(got["ids"]) == {"a", "c"}


async def test_get_with_offset_and_limit_paginates_correctly(
    collection: AsyncBaseCollection,
) -> None:
    ids = [f"id-{i}" for i in range(10)]
    await collection.add(
        ids=ids,
        documents=[f"doc-{i}" for i in range(10)],
        embeddings=[[float(i), 0.0] for i in range(10)],
    )
    full = (await collection.get(ids=ids))["ids"]
    page = (await collection.get(ids=ids, offset=2, limit=3))["ids"]
    assert len(page) == 3
    assert page == full[2:5]
