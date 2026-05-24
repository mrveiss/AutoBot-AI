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
async def test_no_project_id_skips_everything(summarizer, km_mock):
    sprint_id = uuid.uuid4()

    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, None))),
    ):
        result = await summarizer.summarize_and_merge(sprint_id)

    assert result is None
    km_mock.archive_collection.assert_not_called()


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_direct_merge(summarizer, km_mock):
    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(20)

    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, project_id))),
        patch.object(summarizer, "_fetch_documents", new=AsyncMock(return_value=docs)),
        patch.object(summarizer, "_direct_merge", new=AsyncMock()) as dm,
        patch.object(summarizer, "_llm_summarize_and_index", new=AsyncMock(return_value="")) as lsi,
    ):
        result = await summarizer.summarize_and_merge(sprint_id)

    # LLM fallback path returns "" (direct merge happened inside _llm_summarize_and_index)
    lsi.assert_called_once()
    assert result == ""


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
