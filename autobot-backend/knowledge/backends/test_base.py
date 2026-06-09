# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
    collection.add(ids=["dup"], documents=["first"], embeddings=[[1.0, 0.0]])
    collection.add(ids=["dup"], documents=["second"], embeddings=[[0.0, 1.0]])
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
    collection.add(ids=["a", "b"], documents=["x", "y"], embeddings=[[1.0, 0.0], [0.0, 1.0]])
    collection.delete(ids=["a"])
    assert collection.count() == 1
    assert collection.get(ids=["a"])["ids"] == []


def test_upsert_replaces_existing(collection: BaseCollection) -> None:
    collection.add(ids=["a"], documents=["first"], embeddings=[[1.0, 0.0]])
    collection.upsert(ids=["a"], documents=["second"], embeddings=[[0.0, 1.0]])
    assert collection.count() == 1
    got = collection.get(ids=["a"])
    assert got["documents"] == ["second"]


def test_empty_query_returns_empty_inner_lists(
    collection: BaseCollection,
) -> None:
    got = collection.query(query_embeddings=[[1.0, 0.0]], n_results=5)
    assert got["ids"] == [[]]


def test_peek_returns_flat_lists(collection: BaseCollection) -> None:
    collection.add(ids=["a", "b"], documents=["x", "y"], embeddings=[[1.0, 0.0], [0.0, 1.0]])
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


def test_list_collections_returns_base_collection_instances(
    client: BaseClient,
) -> None:
    """Every adapter MUST return ``BaseCollection`` instances so callers
    can invoke .add/.get/.query uniformly regardless of backend (#5134)."""
    client.create_collection("alpha")
    cols = client.list_collections()
    assert cols, "list_collections returned empty"
    for col in cols:
        assert isinstance(col, BaseCollection), f"list_collections must wrap raw backend objects, got {type(col)!r}"


# --- update / where-filter / pagination contract (Issue #5135) --------------


def test_update_replaces_document_and_metadata(
    collection: BaseCollection,
) -> None:
    """update() must change both document and metadata for the targeted id
    and leave unaffected entries untouched."""
    collection.add(
        ids=["a", "b", "c"],
        documents=["doc-a", "doc-b", "doc-c"],
        metadatas=[{"n": 1}, {"n": 2}, {"n": 3}],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
    )
    collection.update(
        ids=["b"],
        documents=["doc-b-v2"],
        metadatas=[{"n": 20}],
        embeddings=[[0.0, 1.0]],
    )
    got_b = collection.get(ids=["b"])
    assert got_b["documents"] == ["doc-b-v2"]
    assert got_b["metadatas"] == [{"n": 20}]
    # Unaffected entries stay identical.
    got_a = collection.get(ids=["a"])
    assert got_a["documents"] == ["doc-a"]
    assert got_a["metadatas"] == [{"n": 1}]
    got_c = collection.get(ids=["c"])
    assert got_c["documents"] == ["doc-c"]
    assert got_c["metadatas"] == [{"n": 3}]


def test_update_preserves_ordering(collection: BaseCollection) -> None:
    """After update(), the order of existing ids in get() must be unchanged."""
    collection.add(
        ids=["a", "b", "c", "d"],
        documents=["doc-a", "doc-b", "doc-c", "doc-d"],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.5, 0.5]],
    )
    before = collection.get(ids=["a", "b", "c", "d"])["ids"]
    collection.update(ids=["c"], documents=["doc-c-v2"], embeddings=[[1.0, 1.0]])
    after = collection.get(ids=["a", "b", "c", "d"])["ids"]
    assert before == after == ["a", "b", "c", "d"]


def test_update_duplicate_id_raises(collection: BaseCollection) -> None:
    """Regression for #5133: duplicate ids in a single update() call must
    surface an error rather than silently reusing the first occurrence's
    aligned document/metadata/embedding.

    Both adapters must reject this — ChromaDB raises ``DuplicateIDError``,
    the in-memory adapter raises ``ValueError``. We accept any exception
    so the contract is ``raises SOMETHING``, not the specific class.
    """
    collection.add(
        ids=["a"],
        documents=["doc-a"],
        embeddings=[[1.0, 0.0]],
    )
    with pytest.raises(Exception):
        collection.update(
            ids=["a", "a"],
            documents=["first", "second"],
            embeddings=[[0.5, 0.5], [0.25, 0.75]],
        )


def test_query_with_where_filter_matches_metadata(
    collection: BaseCollection,
) -> None:
    """query() honours a ``where`` metadata filter and only returns matches."""
    collection.add(
        ids=["a", "b", "c"],
        documents=["doc-a", "doc-b", "doc-c"],
        metadatas=[
            {"source": "x"},
            {"source": "y"},
            {"source": "x"},
        ],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]],
    )
    got = collection.query(
        query_embeddings=[[1.0, 0.0]],
        n_results=5,
        where={"source": "x"},
    )
    assert set(got["ids"][0]) == {"a", "c"}
    for meta in got["metadatas"][0]:
        assert meta["source"] == "x"


def test_get_with_where_filter_returns_only_matching(
    collection: BaseCollection,
) -> None:
    """get() honours a ``where`` metadata filter (equality on top-level keys)."""
    collection.add(
        ids=["a", "b", "c"],
        documents=["doc-a", "doc-b", "doc-c"],
        metadatas=[
            {"source": "x"},
            {"source": "y"},
            {"source": "x"},
        ],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]],
    )
    got = collection.get(where={"source": "x"})
    assert set(got["ids"]) == {"a", "c"}


def test_get_with_offset_and_limit_paginates_correctly(
    collection: BaseCollection,
) -> None:
    """get() with offset=2, limit=3 returns exactly 3 items starting at
    index 2 of the underlying result order."""
    ids = [f"id-{i}" for i in range(10)]
    collection.add(
        ids=ids,
        documents=[f"doc-{i}" for i in range(10)],
        embeddings=[[float(i), 0.0] for i in range(10)],
    )
    full = collection.get(ids=ids)["ids"]
    page = collection.get(ids=ids, offset=2, limit=3)["ids"]
    assert len(page) == 3
    assert page == full[2:5]
