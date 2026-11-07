# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shapes both ChromaDB adapters send (#18557), and that each adapter really sends them."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.backends._chroma_args import (
    collection_provenance,
    delete_args,
    get_args,
    optional_list,
    query_args,
    write_args,
)
from knowledge.backends.async_chromadb_adapter import AsyncChromaDBCollection
from knowledge.backends.chromadb_adapter import ChromaDBCollection


def test_write_args_copy_to_lists_and_keep_none():
    assert write_args(("a",), ("d",), None, None) == {
        "ids": ["a"],
        "documents": ["d"],
        "metadatas": None,
        "embeddings": None,
    }


def test_optional_list_keeps_none_and_an_empty_sequence_apart():
    assert optional_list(None) is None
    assert optional_list(()) == []


def test_get_args_leave_out_what_was_not_set_and_keep_a_zero():
    assert get_args(None, None, None, None, None, None) == {}
    assert get_args(("a",), {"w": 1}, {"d": 1}, 0, 0, ("documents",)) == {
        "ids": ["a"],
        "where": {"w": 1},
        "where_document": {"d": 1},
        "limit": 0,
        "offset": 0,
        "include": ["documents"],
    }


def test_query_args_always_carry_n_results_and_listify_each_embedding():
    assert query_args(None, None, 3, None, None, None) == {"n_results": 3}
    assert query_args(((1.0, 2.0),), ("t",), 3, {"w": 1}, None, ("documents",)) == {
        "n_results": 3,
        "query_embeddings": [[1.0, 2.0]],
        "query_texts": ["t"],
        "where": {"w": 1},
        "include": ["documents"],
    }


def test_delete_refuses_no_filter_and_accepts_an_empty_where():
    with pytest.raises(ValueError, match="delete requires ids or where"):
        delete_args(None, None, None)
    assert delete_args(None, {}, None) == {"where": {}}


def test_provenance_lets_the_caller_override_created_at():
    assert "created_at" in collection_provenance(None)
    assert collection_provenance({"created_at": "x", "k": 1}) == {"created_at": "x", "k": 1}


def test_the_sync_adapter_sends_the_shared_shapes():
    raw = MagicMock()
    col = ChromaDBCollection(raw)
    col.upsert(ids=("a",), documents=("d",))
    raw.upsert.assert_called_once_with(ids=["a"], documents=["d"], metadatas=None, embeddings=None)
    col.get(ids=("a",))
    raw.get.assert_called_once_with(ids=["a"])
    col.query(query_texts=("t",), n_results=2)
    raw.query.assert_called_once_with(n_results=2, query_texts=["t"])
    col.delete(ids=("a",))
    raw.delete.assert_called_once_with(ids=["a"])


@pytest.mark.asyncio
async def test_the_async_adapter_sends_the_shared_shapes():
    raw = AsyncMock()
    col = AsyncChromaDBCollection(raw)
    await col.upsert(ids=("a",), documents=("d",))
    raw.upsert.assert_awaited_once_with(ids=["a"], documents=["d"], metadatas=None, embeddings=None)
    await col.get(ids=("a",))
    raw.get.assert_awaited_once_with(ids=["a"])
    await col.query(query_texts=("t",), n_results=2)
    raw.query.assert_awaited_once_with(n_results=2, query_texts=["t"])
    await col.query_batch(((1.0,),), include=("documents",))
    raw.query_batch.assert_awaited_once_with(
        query_embeddings=[[1.0]], n_results=10, where=None, where_document=None, include=["documents"]
    )
    await col.delete(ids=("a",))
    raw.delete.assert_awaited_once_with(ids=["a"])
