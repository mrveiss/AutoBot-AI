# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A backup's vector reaches the KB only through its write path, and only for its own model (#19647).

The old path called a method the store does not have, so no vector ever came back, and it would have
written a vector from any model with the metadata replaced, un-hiding quarantined facts.
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from knowledge.bulk import BulkOperationsMixin

MODEL = "nomic-embed-text:latest"
_STORED = {"content": "stored text", "metadata": {"collection": "research_quarantine", "owner_id": "u1", "tags": ["a"]}}


class _KB(BulkOperationsMixin):
    def __init__(self, stored=None):
        self.vector_store = MagicMock()
        self._get_fact_for_vectorization = AsyncMock(return_value=stored or dict(_STORED))
        self._write_vector = AsyncMock(return_value=True)
        self._mark_vectorization_succeeded = AsyncMock()


def _space(kb, model=MODEL):
    return types.SimpleNamespace(model=model, vector_store=kb.vector_store, write_buffer=None)


async def _restore(kb, backup):
    with patch("knowledge.bulk.current_space", new=AsyncMock(return_value=_space(kb))):
        return await kb._restore_fact_embedding("f1", backup)


@pytest.mark.asyncio
async def test_a_vector_of_the_bound_model_is_written_through_the_write_path():
    kb = _KB()
    result = await _restore(kb, {"embedding": [0.1, 0.2], "embedding_model": MODEL})
    assert result == {"action": "restored", "embedding": True}
    kb._write_vector.assert_awaited_once()
    kb._mark_vectorization_succeeded.assert_awaited_once_with("f1")


@pytest.mark.parametrize("backup_model", ["bge-m3:latest", None])
@pytest.mark.asyncio
async def test_a_vector_of_another_or_unknown_model_is_never_written(backup_model):
    kb = _KB()
    result = await _restore(kb, {"embedding": [0.1, 0.2], "embedding_model": backup_model})
    assert result == {"action": "restored", "embedding": False}
    kb._write_vector.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_write_carries_the_stored_metadata_and_content_so_a_quarantined_fact_stays_filtered():
    kb = _KB()
    await _restore(kb, {"embedding": [0.1], "embedding_model": MODEL, "content": "raw backup copy"})
    _space_arg, _fid, _vec, content, metadata, _ctx = kb._write_vector.await_args.args
    assert content == "stored text", "the backup's raw copy reached the vector store"
    assert metadata["collection"] == "research_quarantine" and metadata["owner_id"] == "u1"


@pytest.mark.asyncio
async def test_a_refused_write_is_not_reported_as_restored():
    kb = _KB()
    kb._write_vector = AsyncMock(return_value=False)
    result = await _restore(kb, {"embedding": [0.1], "embedding_model": MODEL})
    assert result["embedding"] is False
    kb._mark_vectorization_succeeded.assert_not_awaited()


@pytest.mark.asyncio
async def test_export_reads_the_raw_collection_and_records_the_model():
    """Chroma returns numpy here: a truth test on it raises, and it is not JSON-serializable."""
    kb = _KB()
    kb.vector_store._collection.get.return_value = {"ids": ["f1"], "embeddings": np.array([[0.5, 0.25]])}
    with patch("knowledge.bulk.current_space", new=AsyncMock(return_value=_space(kb))):
        fetched = await kb._fetch_embeddings_from_vector_store(["f1"])
    assert fetched == {"f1": {"embedding": [0.5, 0.25], "embedding_model": MODEL}}
    assert all(type(v) is float for v in fetched["f1"]["embedding"])
