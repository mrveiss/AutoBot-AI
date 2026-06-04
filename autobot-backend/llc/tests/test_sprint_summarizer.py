# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SprintKbSummarizer (GH#8238)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.kb.collections import KbCollectionManager
from llc.kb.sprint_summarizer import _MAX_PROMPT_CHARS, _SUMMARIZE_PROMPT, _SUMMARIZE_THRESHOLD, SprintKbSummarizer


def _make_docs(n: int) -> list:
    return [{"id": f"doc-{i}", "document": f"content {i}", "metadata": {}, "embedding": None} for i in range(n)]


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
        result = await summarizer.summarize_and_merge(sprint_id, session=MagicMock())

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
        result = await summarizer.summarize_and_merge(sprint_id, session=MagicMock())

    dm.assert_called_once()
    lsi.assert_not_called()
    assert result == f"[direct-merged: {_SUMMARIZE_THRESHOLD} docs]"


@pytest.mark.asyncio
async def test_small_collection_writes_kb_summary(summarizer, km_mock):
    """Bug fix: small sprints (<=10 docs) must write kb_summary on the sprint row."""
    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(5)
    sprint_mock = MagicMock()
    session_mock = MagicMock()
    session_mock.flush = AsyncMock()

    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(sprint_mock, project_id))),
        patch.object(summarizer, "_fetch_documents", new=AsyncMock(return_value=docs)),
        patch.object(summarizer, "_direct_merge", new=AsyncMock()),
    ):
        result = await summarizer.summarize_and_merge(sprint_id, session=session_mock)

    assert result == "[direct-merged: 5 docs]"
    assert sprint_mock.kb_summary == "[direct-merged: 5 docs]"
    session_mock.flush.assert_called_once()


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
        result = await summarizer.summarize_and_merge(sprint_id, session=MagicMock())

    lsi.assert_called_once()
    dm.assert_not_called()
    assert result == "summary text"


@pytest.mark.asyncio
async def test_no_project_id_archives_and_skips_merge(summarizer, km_mock):
    """Bug 2 fix: archive must be called even when project_id is None."""
    sprint_id = uuid.uuid4()

    with (patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, None))),):
        result = await summarizer.summarize_and_merge(sprint_id, session=MagicMock())

    assert result is None
    km_mock.archive_collection.assert_called_once_with(KbCollectionManager.SPRINT_PREFIX, sprint_id)


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
        result = await summarizer.summarize_and_merge(sprint_id, session=MagicMock())

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
        await summarizer.summarize_and_merge(sprint_id, session=MagicMock())

    km_mock.archive_collection.assert_called_once_with(KbCollectionManager.SPRINT_PREFIX, sprint_id)
    assert km_mock.archive_collection.call_count == 1


@pytest.mark.asyncio
async def test_llm_empty_content_falls_back_to_direct_merge(summarizer, km_mock):
    """Fix 1: empty LLM content must trigger direct merge, not index empty doc."""
    import sys

    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(20)
    dst_collection = KbCollectionManager.collection_name(KbCollectionManager.PROJECT_PREFIX, project_id)

    llm_response = MagicMock()
    llm_response.error = None
    llm_response.content = ""

    llm_instance = MagicMock()
    llm_instance.chat = AsyncMock(return_value=llm_response)

    fake_llm_module = MagicMock()
    fake_llm_module.get_llm_service = MagicMock(return_value=llm_instance)

    with (
        patch.dict(sys.modules, {"services.llm_service": fake_llm_module}),
        patch.object(summarizer, "_direct_merge", new=AsyncMock()) as dm,
    ):
        result = await summarizer._llm_summarize_and_index(docs, dst_collection, sprint_id, project_id)

    dm.assert_called_once()
    assert result == "[direct-merged: LLM returned empty content]"


@pytest.mark.asyncio
async def test_fetch_documents_reraises_non_notfound_exception(summarizer, km_mock):
    """Fix 2: transient ChromaDB errors must propagate, not silently return []."""
    kb_mock = AsyncMock()
    kb_mock._async_chroma_client = AsyncMock()
    kb_mock._async_chroma_client.get_collection = AsyncMock(side_effect=RuntimeError("connection refused"))

    import sys

    fake_kb_module = MagicMock()
    fake_kb_module.get_knowledge_base = AsyncMock(return_value=kb_mock)
    with patch.dict(sys.modules, {"knowledge": fake_kb_module}):
        with pytest.raises(RuntimeError, match="connection refused"):
            await summarizer._fetch_documents("sprint:xxx")


@pytest.mark.asyncio
async def test_no_session_skips_load_sprint_context(summarizer, km_mock):
    """Fix 3: calling without session must skip _load_sprint_context and archive."""
    sprint_id = uuid.uuid4()

    with patch.object(summarizer, "_load_sprint_context", new=AsyncMock()) as load_mock:
        result = await summarizer.summarize_and_merge(sprint_id)

    assert load_mock.call_count == 0
    km_mock.archive_collection.assert_called_once()
    assert result is None


@pytest.mark.asyncio
async def test_llm_exception_falls_back_to_direct_merge(summarizer, km_mock):
    """GH#8656: llm.chat() raising must fall back to direct merge, not propagate."""
    import sys

    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(20)
    dst_collection = KbCollectionManager.collection_name(KbCollectionManager.PROJECT_PREFIX, project_id)

    llm_instance = MagicMock()
    llm_instance.chat = AsyncMock(side_effect=TimeoutError("LLM timed out"))

    fake_llm_module = MagicMock()
    fake_llm_module.get_llm_service = MagicMock(return_value=llm_instance)

    with (
        patch.dict(sys.modules, {"services.llm_service": fake_llm_module}),
        patch.object(summarizer, "_direct_merge", new=AsyncMock()) as dm,
    ):
        result = await summarizer._llm_summarize_and_index(docs, dst_collection, sprint_id, project_id)

    dm.assert_called_once()
    assert result == "[direct-merged: LLM summarization raised]"


@pytest.mark.asyncio
async def test_archive_called_even_if_write_raises(summarizer, km_mock):
    """GH#8654: archive must ALWAYS be called (finally) so the collection is released."""
    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(_SUMMARIZE_THRESHOLD + 1)

    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, project_id))),
        patch.object(summarizer, "_fetch_documents", new=AsyncMock(return_value=docs)),
        patch.object(
            summarizer,
            "_llm_summarize_and_index",
            new=AsyncMock(side_effect=RuntimeError("unexpected")),
        ),
    ):
        with pytest.raises(RuntimeError, match="unexpected"):
            await summarizer.summarize_and_merge(sprint_id, session=MagicMock())

    km_mock.archive_collection.assert_called_once_with(KbCollectionManager.SPRINT_PREFIX, sprint_id)


@pytest.mark.asyncio
async def test_archive_called_even_if_direct_merge_raises(summarizer, km_mock):
    """GH#8654: archive must ALWAYS be called (finally) so the collection is released."""
    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(_SUMMARIZE_THRESHOLD)  # <= threshold → takes direct-merge path

    with (
        patch.object(summarizer, "_load_sprint_context", new=AsyncMock(return_value=(None, project_id))),
        patch.object(summarizer, "_fetch_documents", new=AsyncMock(return_value=docs)),
        patch.object(
            summarizer,
            "_direct_merge",
            new=AsyncMock(side_effect=RuntimeError("chroma write failed")),
        ),
    ):
        with pytest.raises(RuntimeError, match="chroma write failed"):
            await summarizer.summarize_and_merge(sprint_id, session=MagicMock())

    km_mock.archive_collection.assert_called_once_with(KbCollectionManager.SPRINT_PREFIX, sprint_id)


@pytest.mark.asyncio
async def test_prompt_truncated_for_oversized_combined_input(summarizer, km_mock):
    """GH#8656: combined input exceeding _MAX_PROMPT_CHARS must be truncated before LLM call."""
    import sys

    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    dst_collection = KbCollectionManager.collection_name(KbCollectionManager.PROJECT_PREFIX, project_id)

    # Build docs whose combined text exceeds the cap
    big_text = "x" * (_MAX_PROMPT_CHARS + 1000)
    docs = [{"id": "doc-0", "document": big_text, "metadata": {}, "embedding": None}]

    captured_prompts: list[str] = []

    llm_response = MagicMock()
    llm_response.error = None
    llm_response.content = "summary"

    async def capture_chat(messages, **_kwargs):
        captured_prompts.append(messages[0]["content"])
        return llm_response

    llm_instance = MagicMock()
    llm_instance.chat = capture_chat

    fake_llm_module = MagicMock()
    fake_llm_module.get_llm_service = MagicMock(return_value=llm_instance)

    fake_kb_module = MagicMock()
    dst_col = AsyncMock()
    dst_col.upsert = AsyncMock()
    fake_kb_module.get_knowledge_base = AsyncMock(
        return_value=MagicMock(_async_chroma_client=AsyncMock(get_or_create_collection=AsyncMock(return_value=dst_col)))
    )

    with patch.dict(sys.modules, {"services.llm_service": fake_llm_module, "knowledge": fake_kb_module}):
        await summarizer._llm_summarize_and_index(docs, dst_collection, sprint_id, project_id)

    assert captured_prompts, "llm.chat() was never called"
    # The {documents} section must not exceed the cap
    prompt_sent = captured_prompts[0]
    doc_section = prompt_sent.split("{documents}")[-1] if "{documents}" in prompt_sent else prompt_sent
    assert len(doc_section) <= _MAX_PROMPT_CHARS + len(_SUMMARIZE_PROMPT.replace("{documents}", ""))


@pytest.mark.asyncio
async def test_direct_merge_uses_upsert_for_idempotency(summarizer, km_mock):
    """GH#8655: _direct_merge must use upsert (not add) so duplicate IDs don't raise."""
    import sys

    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(3)
    dst_collection = KbCollectionManager.collection_name(KbCollectionManager.PROJECT_PREFIX, project_id)

    dst_col = AsyncMock()
    dst_col.upsert = AsyncMock()
    fake_kb_module = MagicMock()
    fake_kb_module.get_knowledge_base = AsyncMock(
        return_value=MagicMock(_async_chroma_client=AsyncMock(get_or_create_collection=AsyncMock(return_value=dst_col)))
    )

    with patch.dict(sys.modules, {"knowledge": fake_kb_module}):
        await summarizer._direct_merge(docs, dst_collection, sprint_id, project_id)

    dst_col.upsert.assert_called_once()
    assert "add" not in {m for m in dir(dst_col) if dst_col.__dict__.get(m) is not None}


@pytest.mark.asyncio
async def test_llm_index_uses_upsert_for_idempotency(summarizer, km_mock):
    """GH#8655: _llm_summarize_and_index must use upsert so re-runs don't raise on duplicate sprint_summary ID."""
    import sys

    sprint_id = uuid.uuid4()
    project_id = uuid.uuid4()
    docs = _make_docs(20)
    dst_collection = KbCollectionManager.collection_name(KbCollectionManager.PROJECT_PREFIX, project_id)

    llm_response = MagicMock()
    llm_response.error = None
    llm_response.content = "the summary"

    llm_instance = MagicMock()
    llm_instance.chat = AsyncMock(return_value=llm_response)
    fake_llm_module = MagicMock()
    fake_llm_module.get_llm_service = MagicMock(return_value=llm_instance)

    dst_col = AsyncMock()
    dst_col.upsert = AsyncMock()
    fake_kb_module = MagicMock()
    fake_kb_module.get_knowledge_base = AsyncMock(
        return_value=MagicMock(_async_chroma_client=AsyncMock(get_or_create_collection=AsyncMock(return_value=dst_col)))
    )

    with patch.dict(sys.modules, {"services.llm_service": fake_llm_module, "knowledge": fake_kb_module}):
        result = await summarizer._llm_summarize_and_index(docs, dst_collection, sprint_id, project_id)

    assert result == "the summary"
    dst_col.upsert.assert_called_once()
    call_kwargs = dst_col.upsert.call_args.kwargs
    assert call_kwargs["ids"] == [f"sprint_summary:{sprint_id}"]
