# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SprintKbSummarizer (GH#8238)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.kb.collections import KbCollectionManager
from llc.kb.sprint_summarizer import SprintKbSummarizer, _SUMMARIZE_THRESHOLD


def _make_docs(n: int) -> list:
    return [
        {"id": f"doc-{i}", "document": f"content {i}", "metadata": {}, "embedding": None}
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_archive_collection_omits_embeddings_when_none():
    """Bug 1 fix: archive_collection must not pass embeddings=None to ChromaDB."""
    from llc.kb.collections import KbCollectionManager

    km = KbCollectionManager.__new__(KbCollectionManager)

    original_col = AsyncMock()
    original_col.get = AsyncMock(
        return_value={
            "ids": ["id1", "id2"],
            "documents": ["doc1", "doc2"],
            "metadatas": [{}, {}],
            # embeddings key absent (ChromaDB default) → documents.get("embeddings") is None
        }
    )

    archived_col = AsyncMock()
    archived_col.add = AsyncMock()

    async_chroma_client = AsyncMock()
    async_chroma_client.get_collection = AsyncMock(return_value=original_col)
    async_chroma_client.create_collection = AsyncMock(return_value=archived_col)
    async_chroma_client.delete_collection = AsyncMock()

    kb_mock = MagicMock()
    kb_mock._async_chroma_client = async_chroma_client

    entity_type = "sprint"
    entity_id = uuid.uuid4()

    with patch("llc.kb.collections._get_kb", new=AsyncMock(return_value=kb_mock)):
        await KbCollectionManager.archive_collection(km, entity_type, entity_id)

    call_kwargs = archived_col.add.call_args.kwargs
    # embeddings must NOT be present — omitting it prevents the ChromaDB ValueError
    assert "embeddings" not in call_kwargs
    assert call_kwargs["ids"] == ["id1", "id2"]
    assert call_kwargs["documents"] == ["doc1", "doc2"]


@pytest.fixture
def km_mock():
    km = MagicMock()
    km.archive_collection = AsyncMock(return_value="sprint:xxx:archived:2026-01-01")
    return km


@pytest.fixture
def summarizer(km_mock):
    s = SprintKbSummarizer(kb_collection_manager=km_mock)
    return s


@pytest.mark.asyncio
async def test_empty_collection_skips_merge(summarizer, km_mock):
    sprint_id = uuid.uuid4()
    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, uuid.uuid4()))),
        patch.object(summarizer, "_fetch_documents", new=AsyncMock(return_value=[])),
    ):
        result = await summarizer.summarize_and_merge(sprint_id)

    assert result is None
    km_mock.archive_collection.assert_called_once()


@pytest.mark.asyncio
async def test_small_collection_direct_merge(summarizer, km_mock):
    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(_SUMMARIZE_THRESHOLD)  # exactly at threshold → direct merge

    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, project_id))),
        patch.object(summarizer, "_fetch_documents", new=AsyncMock(return_value=docs)),
        patch.object(summarizer, "_direct_merge", new=AsyncMock()) as dm,
        patch.object(summarizer, "_llm_summarize_and_index", new=AsyncMock()) as lsi,
    ):
        result = await summarizer.summarize_and_merge(sprint_id)

    dm.assert_called_once()
    lsi.assert_not_called()
    assert result is None  # direct merge returns None


@pytest.mark.asyncio
async def test_large_collection_llm_summarize(summarizer, km_mock):
    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(_SUMMARIZE_THRESHOLD + 1)

    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, project_id))),
        patch.object(summarizer, "_fetch_documents", new=AsyncMock(return_value=docs)),
        patch.object(summarizer, "_direct_merge", new=AsyncMock()) as dm,
        patch.object(summarizer, "_llm_summarize_and_index", new=AsyncMock(return_value="summary text")) as lsi,
    ):
        result = await summarizer.summarize_and_merge(sprint_id)

    lsi.assert_called_once()
    dm.assert_not_called()
    assert result == "summary text"


@pytest.mark.asyncio
async def test_no_project_id_archives_and_skips_merge(summarizer, km_mock):
    """Bug 2 fix: archive must be called even when project_id is None."""
    sprint_id = uuid.uuid4()

    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, None))),
    ):
        result = await summarizer.summarize_and_merge(sprint_id)

    assert result is None
    km_mock.archive_collection.assert_called_once_with(
        KbCollectionManager.SPRINT_PREFIX, sprint_id
    )


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_direct_merge(summarizer, km_mock):
    """Bug 3 fix: LLM failure must return non-empty sentinel so kb_summary is persisted."""
    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(20)
    _SENTINEL = "[direct-merged: LLM summarization failed]"

    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, project_id))),
        patch.object(summarizer, "_fetch_documents", new=AsyncMock(return_value=docs)),
        patch.object(summarizer, "_direct_merge", new=AsyncMock()) as dm,
        patch.object(summarizer, "_llm_summarize_and_index", new=AsyncMock(return_value=_SENTINEL)) as lsi,
    ):
        result = await summarizer.summarize_and_merge(sprint_id)

    # LLM fallback returns sentinel so caller if-guard fires and persists kb_summary
    lsi.assert_called_once()
    assert result == _SENTINEL


@pytest.mark.asyncio
async def test_archive_always_called_on_success(summarizer, km_mock):
    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(5)

    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, project_id))),
        patch.object(summarizer, "_fetch_documents", new=AsyncMock(return_value=docs)),
        patch.object(summarizer, "_direct_merge", new=AsyncMock()),
    ):
        await summarizer.summarize_and_merge(sprint_id)

    km_mock.archive_collection.assert_called_once_with(
        KbCollectionManager.SPRINT_PREFIX, sprint_id
    )
    assert km_mock.archive_collection.call_count == 1
