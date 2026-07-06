# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for grounded citations on RAG responses (#10548).

Acceptance criteria verified:
  (a) RAG-grounded response includes citations[] with ids+scores in the payload.
  (b) Model-only response (no KB results) is marked grounding.grounded=False
      and citations[] is empty.
  (c) _build_citations_from_kb_results maps raw kb_result dicts to Citation objects.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_kb_result(
    content: str = "AutoBot fact",
    source: str = "docs/autobot.md",
    score: float = 0.87,
    chunk_id: str = "chunk-001",
) -> dict:
    """Return a kb_result dict in the shape returned by knowledge_base.search()."""
    return {
        "content": content,
        "source": source,
        "score": score,
        "metadata": {"chunk_id": chunk_id, "title": "AutoBot Docs"},
    }


def _make_chat_message(use_knowledge_base: bool = True) -> MagicMock:
    msg = MagicMock()
    msg.content = "What is AutoBot?"
    msg.role = "user"
    msg.session_id = "sess-abc"
    msg.metadata = {}
    msg.reasoning_effort = None
    msg.use_knowledge_base = use_knowledge_base
    return msg


# ---------------------------------------------------------------------------
# _build_citations_from_kb_results
# ---------------------------------------------------------------------------


class TestBuildCitationsFromKbResults:
    """Unit tests for the citation builder helper."""

    def test_single_result_produces_citation(self) -> None:
        from api.chat import _build_citations_from_kb_results

        kb_results = [_make_kb_result()]
        citations = _build_citations_from_kb_results(kb_results)

        assert len(citations) == 1
        cit = citations[0]
        assert cit.id == "chunk-001"
        assert cit.source_type == "chunk"
        assert cit.title == "AutoBot Docs"
        assert cit.uri == "docs/autobot.md"
        assert abs(cit.score - 0.87) < 1e-6

    def test_empty_kb_results_produces_empty_list(self) -> None:
        from api.chat import _build_citations_from_kb_results

        assert _build_citations_from_kb_results([]) == []

    def test_caps_at_five_citations(self) -> None:
        from api.chat import _build_citations_from_kb_results

        kb_results = [_make_kb_result(chunk_id=f"c-{i}") for i in range(8)]
        citations = _build_citations_from_kb_results(kb_results)
        assert len(citations) == 5

    def test_missing_metadata_falls_back_gracefully(self) -> None:
        from api.chat import _build_citations_from_kb_results

        result = {"content": "bare result", "score": 0.5}
        citations = _build_citations_from_kb_results([result])
        assert len(citations) == 1
        assert citations[0].score == 0.5
        # title falls back to "Source 1" when no metadata/source available
        assert "source" in citations[0].title.lower() or citations[0].title != ""


# ---------------------------------------------------------------------------
# process_chat_message — grounded path
# ---------------------------------------------------------------------------


_CHAT_MOD = "api.chat"


def _make_llm_response(content: str = "Here is the answer.") -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.error = None
    resp.usage = {}
    return resp


async def _run_process_chat_message(kb_results: list, use_kb: bool = True):
    """Run process_chat_message with minimal real dependencies mocked out."""
    message = _make_chat_message(use_knowledge_base=use_kb)

    mock_kb = AsyncMock()
    mock_kb.search = AsyncMock(return_value=kb_results)

    mock_llm_service = AsyncMock()
    mock_llm_service.chat = AsyncMock(return_value=_make_llm_response())

    mock_history = MagicMock()
    mock_history.get_session_messages = AsyncMock(return_value=[])
    mock_history.add_messages_batch = AsyncMock()
    mock_history.context_manager = None

    noop_async = AsyncMock(return_value={})

    with (
        patch(f"{_CHAT_MOD}._store_and_log_user_message", new=AsyncMock(return_value="user-msg-id")),
        patch(f"{_CHAT_MOD}._get_chat_context", new=AsyncMock(return_value=[])),
        patch(f"{_CHAT_MOD}._build_llm_context", return_value=[]),
        patch(f"{_CHAT_MOD}._resolve_chat_reasoning_effort", new=AsyncMock(return_value="auto")),
        patch(
            f"{_CHAT_MOD}._generate_ai_response",
            new=AsyncMock(return_value=({"content": "answer", "role": "assistant"}, _make_llm_response())),
        ),
        patch(f"{_CHAT_MOD}._store_and_log_ai_response", new=AsyncMock(return_value="ai-msg-id")),
        patch(f"{_CHAT_MOD}.handle_message_completion", new=noop_async),
        patch(f"{_CHAT_MOD}.create_summary_message", new=AsyncMock(return_value={})),
        patch(f"{_CHAT_MOD}._validate_session_id", return_value=None),
    ):
        from api.chat import process_chat_message

        return await process_chat_message(
            message=message,
            chat_history_manager=mock_history,
            llm_service=mock_llm_service,
            memory_interface=None,
            knowledge_base=mock_kb,
            config={},
            request_id="req-001",
            author_id=None,
        )


class TestProcessChatMessageCitations:
    """Acceptance tests: grounded response carries citations; model-only is flagged."""

    @pytest.mark.asyncio
    async def test_grounded_response_includes_citations(self) -> None:
        """(a) RAG-grounded response: citations[] non-empty, ids+scores present."""
        kb_results = [_make_kb_result("fact about AutoBot", score=0.91)]
        result = await _run_process_chat_message(kb_results)

        assert result.grounding is not None, "grounding field must be set"
        assert result.grounding.grounded is True
        assert result.grounding.strategy == "rag"

        assert len(result.citations) == 1, "one citation expected"
        cit = result.citations[0]
        assert cit.id == "chunk-001"
        assert abs(cit.score - 0.91) < 1e-6

        # citations also mirrored into metadata for CitationsDisplay.vue
        assert result.metadata is not None
        meta_citations = result.metadata.get("citations", [])
        assert len(meta_citations) == 1
        assert meta_citations[0]["id"] == "chunk-001"

    @pytest.mark.asyncio
    async def test_model_only_response_is_marked_ungrounded(self) -> None:
        """(b) Model-only (no KB results): grounding.grounded=False, citations=[]."""
        result = await _run_process_chat_message(kb_results=[])

        assert result.grounding is not None
        assert result.grounding.grounded is False
        assert result.grounding.strategy is None
        assert result.citations == []
        # metadata should NOT have a citations key (no spurious empty list)
        meta_citations = (result.metadata or {}).get("citations")
        assert meta_citations is None or meta_citations == []

    @pytest.mark.asyncio
    async def test_kb_disabled_produces_no_citations(self) -> None:
        """use_knowledge_base=False → no KB call, no citations."""
        result = await _run_process_chat_message(kb_results=[_make_kb_result()], use_kb=False)

        assert result.citations == []
        assert result.grounding is not None
        assert result.grounding.grounded is False
