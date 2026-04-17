# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Contract tests for ``BaseCollection`` / ``BaseClient`` (Issue #5062).

Every test is parametrized over all adapters so a new backend (Qdrant,
LanceDB, pgvector ...) only needs a fixture added to ``_BACKENDS`` below.
"""

from __future__ import annotations

from typing import Callable

import pytest

from knowledge.backends import (
    BaseClient,
    BaseCollection,
    ChromaDBClient,
    InMemoryClient,
)


# --- fixture factories ------------------------------------------------------
#
# ChromaDB 1.x ``EphemeralClient()`` shares an in-memory database across
# instances in the same process, so naively creating one per test leaks
# state between parametrized cases. We use a per-test ``PersistentClient``
# pointed at a fresh temp directory to get full isolation — still fast
# (~20ms per instantiation), still avoids any network/HTTP dependency.

def _memory_client(tmp_path) -> BaseClient:  # tmp_path unused, kept for uniform signature
    return InMemoryClient()


def _chromadb_client(tmp_path) -> BaseClient:
    chromadb = pytest.importorskip("chromadb")
    return ChromaDBClient(chromadb.PersistentClient(path=str(tmp_path)))


# Adding a new adapter? Append ``(name, factory)`` here.
_BACKENDS: list[tuple[str, Callable[..., BaseClient]]] = [
    ("memory", _memory_client),
    ("chromadb", _chromadb_client),
]


@pytest.fixture(params=_BACKENDS, ids=[name for name, _ in _BACKENDS])
def client(request, tmp_path) -> BaseClient:
    _name, factory = request.param
    return factory(tmp_path)


@pytest.fixture
def collection(client: BaseClient) -> BaseCollection:
    return client.get_or_create_collection("contract-test")


# --- collection contract ----------------------------------------------------

def test_add_then_count(collection: BaseCollection) -> None:
    collection.add(
        ids=["a", "b", "c"],
        documents=["doc-a", "doc-b", "doc-c"],
        metadatas=[{"n": 1}, {"n": 2}, {"n": 3}],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
    )
    assert collection.count() == 3


def test_add_duplicate_retains_original(collection: BaseCollection) -> None:
    """ChromaDB 1.x contract: add() on a duplicate id is a no-op.
    Callers that want replace semantics must use upsert()."""
    collection.add(
        ids=["dup"], documents=["first"], embeddings=[[1.0, 0.0]]
    )
    collection.add(
        ids=["dup"], documents=["second"], embeddings=[[0.0, 1.0]]
    )
    assert collection.count() == 1
    assert collection.get(ids=["dup"])["documents"] == ["first"]


def test_get_by_ids_returns_flat_lists(collection: BaseCollection) -> None:
    collection.add(
        ids=["a", "b"],
        documents=["doc-a", "doc-b"],
        metadatas=[{"n": 1}, {"n": 2}],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
    )
    got = collection.get(ids=["a"])
    assert got["ids"] == ["a"]
    assert got["documents"] == ["doc-a"]
    # flat list, not nested
    assert not isinstance(got["ids"][0], list)


def test_query_returns_nested_lists_ordered_by_distance(
    collection: BaseCollection,
) -> None:
    collection.add(
        ids=["near", "far"],
        documents=["near-doc", "far-doc"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
    )
    got = collection.query(
        query_embeddings=[[1.0, 0.0]],
        n_results=2,
    )
    # nested: one inner list per query vector
    assert isinstance(got["ids"], list)
    assert isinstance(got["ids"][0], list)
    assert got["ids"][0][0] == "near"


def test_delete_by_ids_reduces_count(collection: BaseCollection) -> None:
    collection.add(
        ids=["a", "b"], documents=["x", "y"], embeddings=[[1.0, 0.0], [0.0, 1.0]]
    )
    collection.delete(ids=["a"])
    assert collection.count() == 1
    assert collection.get(ids=["a"])["ids"] == []


def test_upsert_replaces_existing(collection: BaseCollection) -> None:
    collection.add(
        ids=["a"], documents=["first"], embeddings=[[1.0, 0.0]]
    )
    collection.upsert(
        ids=["a"], documents=["second"], embeddings=[[0.0, 1.0]]
    )
    assert collection.count() == 1
    got = collection.get(ids=["a"])
    assert got["documents"] == ["second"]


def test_empty_query_returns_empty_inner_lists(
    collection: BaseCollection,
) -> None:
    got = collection.query(query_embeddings=[[1.0, 0.0]], n_results=5)
    assert got["ids"] == [[]]


def test_peek_returns_flat_lists(collection: BaseCollection) -> None:
    collection.add(
        ids=["a", "b"], documents=["x", "y"], embeddings=[[1.0, 0.0], [0.0, 1.0]]
    )
    peek = collection.peek(limit=1)
    assert len(peek["ids"]) == 1
    assert not isinstance(peek["ids"][0], list)


# --- client contract --------------------------------------------------------

def test_get_or_create_is_idempotent(client: BaseClient) -> None:
    a = client.get_or_create_collection("dup-collection")
    b = client.get_or_create_collection("dup-collection")
    a.add(ids=["x"], documents=["hello"], embeddings=[[1.0, 0.0]])
    assert b.count() == 1


def test_get_collection_missing_raises(client: BaseClient) -> None:
    with pytest.raises(ValueError):
        client.get_collection("does-not-exist")


def test_create_collection_twice_raises(client: BaseClient) -> None:
    client.create_collection("only-once")
    with pytest.raises(ValueError):
        client.create_collection("only-once")


def test_delete_collection_missing_raises(client: BaseClient) -> None:
    with pytest.raises(ValueError):
        client.delete_collection("never-existed")


def test_list_collections_reflects_state(client: BaseClient) -> None:
    client.create_collection("alpha")
    client.create_collection("beta")
    cols = client.list_collections()
    assert len(cols) >= 2
