# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for HandoffBriefGenerator — KB-powered handoff briefs (GH#8239)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.kb.handoff_brief import HandoffBriefGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(content: dict | None = None, error: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.error = error
    resp.content = json.dumps(content) if content is not None else ""
    return resp


def _make_rag_context(chunks: list | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.chunks = chunks or []
    return ctx


# ---------------------------------------------------------------------------
# generate_agent_to_human_brief
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2h_returns_structured_brief():
    llm_payload = {
        "completed": ["task A"],
        "remaining": ["task B"],
        "open_questions": ["Q1"],
        "next_steps": ["step 1"],
        "artifacts": ["file.py"],
    }

    with (
        patch("llc.kb.handoff_brief.LLCRAGAssembler") as MockRAG,
        patch("llc.kb.handoff_brief.HandoffBriefGenerator.__init__", return_value=None),
    ):
        gen = HandoffBriefGenerator.__new__(HandoffBriefGenerator)
        gen.rag = MagicMock()
        gen.rag.assemble = AsyncMock(return_value=_make_rag_context())

        with patch("llc.kb.handoff_brief.get_llm_service") as mock_llm_fn:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=_make_llm_response(llm_payload))
            mock_llm_fn.return_value = mock_llm

            with patch("services.llm_service.get_llm_service", mock_llm_fn, create=True):
                result = await gen.generate_agent_to_human_brief(
                    work_item_id="wi-1",
                    agent_id="ag-1",
                    company_id="co-1",
                    work_item_title="Fix bug",
                    work_item_description="desc",
                )

    assert result["completed"] == ["task A"]
    assert result["remaining"] == ["task B"]
    assert result["open_questions"] == ["Q1"]
    assert result["next_steps"] == ["step 1"]
    assert result["artifacts"] == ["file.py"]
    assert "generated_at" in result
    assert result["generator"] == "handoff_brief_generator"


@pytest.mark.asyncio
async def test_a2h_falls_back_on_llm_error():
    gen = HandoffBriefGenerator.__new__(HandoffBriefGenerator)
    gen.rag = MagicMock()
    gen.rag.assemble = AsyncMock(return_value=_make_rag_context())

    with patch("services.llm_service.get_llm_service", create=True) as mock_llm_fn:
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=_make_llm_response(error="timeout"))
        mock_llm_fn.return_value = mock_llm

        result = await gen.generate_agent_to_human_brief(
            work_item_id="wi-2",
            agent_id="ag-2",
            company_id="co-2",
        )

    assert result["generator"] == "fallback"
    assert result["completed"] == []


@pytest.mark.asyncio
async def test_a2h_falls_back_on_rag_exception():
    gen = HandoffBriefGenerator.__new__(HandoffBriefGenerator)
    gen.rag = MagicMock()
    gen.rag.assemble = AsyncMock(side_effect=RuntimeError("chromadb down"))

    result = await gen.generate_agent_to_human_brief(
        work_item_id="wi-3",
        agent_id="ag-3",
        company_id="co-3",
    )

    assert result["generator"] == "fallback"


@pytest.mark.asyncio
async def test_a2h_handles_non_json_llm_response():
    gen = HandoffBriefGenerator.__new__(HandoffBriefGenerator)
    gen.rag = MagicMock()
    gen.rag.assemble = AsyncMock(return_value=_make_rag_context())

    bad_resp = MagicMock()
    bad_resp.error = None
    bad_resp.content = "not valid json at all"

    with patch("services.llm_service.get_llm_service", create=True) as mock_llm_fn:
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=bad_resp)
        mock_llm_fn.return_value = mock_llm

        result = await gen.generate_agent_to_human_brief(
            work_item_id="wi-4",
            agent_id="ag-4",
            company_id="co-4",
        )

    assert "generated_at" in result
    assert "completed" in result


# ---------------------------------------------------------------------------
# generate_human_to_agent_brief
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_h2a_returns_structured_brief():
    llm_payload = {
        "company_standards": ["Use async I/O"],
        "project_context": ["Uses FastAPI"],
        "suggested_approach": "Implement X via Y",
    }

    gen = HandoffBriefGenerator.__new__(HandoffBriefGenerator)
    gen.rag = MagicMock()
    gen.rag.assemble = AsyncMock(return_value=_make_rag_context())

    with patch("services.llm_service.get_llm_service", create=True) as mock_llm_fn:
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=_make_llm_response(llm_payload))
        mock_llm_fn.return_value = mock_llm

        result = await gen.generate_human_to_agent_brief(
            work_item_id="wi-5",
            human_notes="Please fix the auth bug",
            company_id="co-5",
            work_item_title="Auth fix",
        )

    assert result["human_context"] == "Please fix the auth bug"
    assert result["company_standards"] == ["Use async I/O"]
    assert result["project_context"] == ["Uses FastAPI"]
    assert result["suggested_approach"] == "Implement X via Y"
    assert result["generator"] == "handoff_brief_generator"


@pytest.mark.asyncio
async def test_h2a_falls_back_on_llm_error():
    gen = HandoffBriefGenerator.__new__(HandoffBriefGenerator)
    gen.rag = MagicMock()
    gen.rag.assemble = AsyncMock(return_value=_make_rag_context())

    with patch("services.llm_service.get_llm_service", create=True) as mock_llm_fn:
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=_make_llm_response(error="overload"))
        mock_llm_fn.return_value = mock_llm

        result = await gen.generate_human_to_agent_brief(
            work_item_id="wi-6",
            human_notes="notes",
            company_id="co-6",
        )

    assert result["generator"] == "fallback"
    assert result["human_context"] == "notes"
    assert "suggested_approach" in result


# ---------------------------------------------------------------------------
# _format_context_for_llm
# ---------------------------------------------------------------------------


def test_format_context_empty():
    gen = HandoffBriefGenerator.__new__(HandoffBriefGenerator)
    result = gen._format_context_for_llm([], "agent_to_human")
    assert "No KB context" in result


def test_format_context_includes_source():
    gen = HandoffBriefGenerator.__new__(HandoffBriefGenerator)
    chunks = [{"content": "hello world", "source": "work_item:wi-1", "similarity_score": 0.87, "metadata": {}}]
    result = gen._format_context_for_llm(chunks, "agent_to_human")
    assert "work_item:wi-1" in result
    assert "hello world" in result
    assert "0.87" in result
