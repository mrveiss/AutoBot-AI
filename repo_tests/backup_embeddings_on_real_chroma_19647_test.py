# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A backup's vector returns only through the KB's write path, for its own model, into a gap (#19647).

The old path called a method the store does not have, so no vector ever came back, and it would have
written a vector from any model with the metadata replaced, un-hiding quarantined facts. These run on
an in-memory Chroma: add() on an existing id silently keeps the old vector, which a mock cannot show.
They live in repo_tests because the backend conftest stubs chromadb.
"""

from __future__ import annotations

import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llama_index.vector_stores.chroma import ChromaVectorStore

from knowledge import backup_embeddings as be
from knowledge.bulk import BulkOperationsMixin
from knowledge.facts import FactsMixin
from knowledge.write_buffer import VectorWriteBuffer, make_chromadb_flush_fn

chromadb = pytest.importorskip("chromadb")
if not list(getattr(chromadb, "__path__", []) or []):
    pytest.skip("chromadb is stubbed, not the real library", allow_module_level=True)

MODEL = "nomic-embed-text:latest"
_STORED = {"content": "stored text", "metadata": {"collection": "research_quarantine", "owner_id": "u1", "tags": ["a"]}}


class _KB(BulkOperationsMixin):
    """The write path reduced to the collection call the real store makes."""

    def __init__(self):
        self.collection = chromadb.EphemeralClient().get_or_create_collection(f"t-{uuid.uuid4().hex}")
        self.vector_store = types.SimpleNamespace(_collection=self.collection)
        self._get_fact_for_vectorization = AsyncMock(return_value=dict(_STORED))
        self._mark_vectorization_succeeded = AsyncMock()

    async def _write_vector(self, _space, fact_id, embedding, content, metadata, _ctx):
        self.collection.add(ids=[fact_id], embeddings=[embedding], documents=[content], metadatas=[metadata])
        return True


def _patched(kb):
    space = types.SimpleNamespace(model=MODEL, vector_store=kb.vector_store, write_buffer=None)
    return patch("knowledge.backup_embeddings.current_space", new=AsyncMock(return_value=space))


async def _restore(kb, backup):
    with _patched(kb):
        return await kb._restore_fact_embedding("f1", backup)


@pytest.mark.asyncio
async def test_a_vector_of_the_bound_model_fills_a_gap():
    kb = _KB()
    result = await _restore(kb, {"embedding": [0.1, 0.2], "embedding_model": MODEL})
    assert result == {"action": "restored", "embedding": True}
    stored = kb.collection.get(ids=["f1"], include=["embeddings", "documents"])
    assert stored["documents"] == ["stored text"]
    assert stored["embeddings"][0].tolist() == pytest.approx([0.1, 0.2])
    kb._mark_vectorization_succeeded.assert_awaited_once_with("f1")


@pytest.mark.asyncio
async def test_a_fact_store_fact_already_embedded_is_reported_as_a_skip_not_a_write():
    kb = _KB()
    kb.collection.add(ids=["f1"], embeddings=[[1.0, 0.0]], documents=["fresh"], metadatas=[{"k": "v"}])
    result = await _restore(kb, {"embedding": [0.0, 1.0], "embedding_model": MODEL})
    assert result == {"action": "restored", "embedding": False}
    assert kb.collection.get(ids=["f1"], include=["embeddings"])["embeddings"][0].tolist() == [1.0, 0.0]
    kb._mark_vectorization_succeeded.assert_not_awaited()


@pytest.mark.parametrize("backup_model", ["bge-m3:latest", None])
@pytest.mark.asyncio
async def test_a_vector_of_another_or_unknown_model_is_never_written(backup_model):
    kb = _KB()
    result = await _restore(kb, {"embedding": [0.1, 0.2], "embedding_model": backup_model})
    assert result["embedding"] is False and kb.collection.count() == 0


@pytest.mark.asyncio
async def test_a_vector_of_the_wrong_dimension_is_not_reported_as_restored():
    kb = _KB()
    kb.collection.add(ids=["other"], embeddings=[[1.0, 0.0]], documents=["x"])
    result = await _restore(kb, {"embedding": [0.1, 0.2, 0.3], "embedding_model": MODEL})
    assert result["embedding"] is False
    assert kb.collection.get(ids=["f1"])["ids"] == []


@pytest.mark.asyncio
async def test_a_quarantined_fact_keeps_its_marker_so_the_ne_filter_still_hides_it():
    kb = _KB()
    await _restore(kb, {"embedding": [0.1, 0.2], "embedding_model": MODEL, "content": "raw backup copy"})
    assert kb.collection.get(ids=["f1"], include=["documents"])["documents"] == ["stored text"]
    visible = kb.collection.get(where={"collection": {"$ne": "research_quarantine"}})
    assert visible["ids"] == [], "a restored quarantined fact is visible to the search filter"
    assert kb.collection.get(ids=["f1"], include=["metadatas"])["metadatas"][0]["owner_id"] == "u1"


@pytest.mark.asyncio
async def test_a_refused_write_is_not_reported_as_restored():
    kb = _KB()
    kb._write_vector = AsyncMock(return_value=False)
    result = await _restore(kb, {"embedding": [0.1], "embedding_model": MODEL})
    assert result["embedding"] is False
    kb._mark_vectorization_succeeded.assert_not_awaited()


@pytest.mark.asyncio
async def test_export_records_each_vector_s_own_model_as_plain_floats():
    kb = _KB()
    kb.collection.add(
        ids=["f1", "f2"],
        embeddings=[[0.5, 0.25], [0.25, 0.5]],
        documents=["a", "b"],
        metadatas=[{"embedding_model": MODEL}, {"embedding_model": "older:model"}],
    )
    with _patched(kb):
        fetched = await kb._fetch_embeddings_from_vector_store(["f1", "f2"])
    assert fetched["f1"] == {"embedding": [0.5, 0.25], "embedding_model": MODEL}
    assert fetched["f2"]["embedding_model"] == "older:model"
    assert all(type(v) is float for v in fetched["f1"]["embedding"])


@pytest.mark.asyncio
async def test_export_reads_in_batches():
    kb = _KB()
    collection = MagicMock()
    collection.get.return_value = {"ids": [], "embeddings": [], "metadatas": []}
    kb.vector_store = types.SimpleNamespace(_collection=collection)
    with _patched(kb), patch.object(be, "EXPORT_BATCH_SIZE", 2):
        await kb._fetch_embeddings_from_vector_store(["a", "b", "c", "d", "e"])
    assert [call.kwargs["ids"] for call in collection.get.call_args_list] == [["a", "b"], ["c", "d"], ["e"]]


class _RealPathKB(FactsMixin, BulkOperationsMixin):
    """The real _write_vector, real LlamaIndex store and real write buffer over one in-memory collection."""

    def __init__(self):
        self.collection = chromadb.EphemeralClient().get_or_create_collection(f"t-{uuid.uuid4().hex}")
        self.vector_store = ChromaVectorStore(chroma_collection=self.collection)
        self.buffer = VectorWriteBuffer(flush_fn=make_chromadb_flush_fn(self.vector_store))
        self._get_fact_for_vectorization = AsyncMock(return_value=dict(_STORED))
        self._mark_vectorization_succeeded = AsyncMock()


@pytest.mark.asyncio
async def test_real_path_a_vector_still_queued_by_store_fact_is_seen_and_kept():
    """The look at the collection would miss a queued write without the flush, and report a false restore."""
    kb = _RealPathKB()
    space = types.SimpleNamespace(model=MODEL, vector_store=kb.vector_store, write_buffer=kb.buffer)
    await kb.buffer.write("f1", [1.0, 0.0], "fresh", {"k": "v"})
    assert kb.collection.get(ids=["f1"])["ids"] == [], "the buffer flushed early; this test proves nothing"
    with patch("knowledge.backup_embeddings.current_space", new=AsyncMock(return_value=space)):
        result = await kb._restore_fact_embedding("f1", {"embedding": [0.0, 1.0], "embedding_model": MODEL})
    assert result == {"action": "restored", "embedding": False}
    assert kb.collection.get(ids=["f1"], include=["embeddings"])["embeddings"][0].tolist() == [1.0, 0.0]
    kb._mark_vectorization_succeeded.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_path_a_gap_is_filled_through_the_real_write_buffer():
    kb = _RealPathKB()
    space = types.SimpleNamespace(model=MODEL, vector_store=kb.vector_store, write_buffer=kb.buffer)
    with patch("knowledge.backup_embeddings.current_space", new=AsyncMock(return_value=space)):
        result = await kb._restore_fact_embedding("f1", {"embedding": [0.1, 0.2], "embedding_model": MODEL})
    assert result == {"action": "restored", "embedding": True}
    await kb.buffer.flush_now()
    stored = kb.collection.get(ids=["f1"], include=["documents", "metadatas"])
    assert stored["documents"] == ["stored text"] and stored["metadatas"][0]["collection"] == "research_quarantine"


@pytest.mark.asyncio
async def test_real_path_a_gap_is_filled_when_the_buffer_has_stopped():
    """A rebind stops the buffer mid-operation; _write_vector then goes straight to the store."""
    kb = _RealPathKB()
    await kb.buffer.stop()
    space = types.SimpleNamespace(model=MODEL, vector_store=kb.vector_store, write_buffer=kb.buffer)
    with patch("knowledge.backup_embeddings.current_space", new=AsyncMock(return_value=space)):
        result = await kb._restore_fact_embedding("f1", {"embedding": [0.1, 0.2], "embedding_model": MODEL})
    assert result["embedding"] is True and kb.collection.get(ids=["f1"])["ids"] == ["f1"]
