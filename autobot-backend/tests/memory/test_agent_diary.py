# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for AgentDiaryService (issue #3789).

All KB calls are mocked so these tests run without Redis / ChromaDB.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from memory.agent_diary import AgentDiaryService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_kb_mock(store_result=None, search_result=None):
    """Return an async mock KnowledgeBase stub."""
    kb = MagicMock()
    kb.store_fact = AsyncMock(
        return_value=store_result or {"status": "success", "fact_id": "fact-001"}
    )
    kb.search = AsyncMock(return_value=search_result or [])
    return kb


def _result_with_ts(ts: str) -> dict:
    """Build a minimal KB search result dict."""
    return {"content": "entry", "metadata": {"diary_timestamp": ts, "source": "a"}}


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------

class TestWrite:
    @pytest.mark.asyncio
    async def test_write_returns_fact_id(self):
        kb = _make_kb_mock(store_result={"status": "success", "fact_id": "abc-123"})
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            diary = AgentDiaryService()
            fact_id = await diary.write("agent_a", "sess-1", "did something", topic="work")
        assert fact_id == "abc-123"

    @pytest.mark.asyncio
    async def test_write_passes_correct_metadata(self):
        kb = _make_kb_mock()
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            diary = AgentDiaryService()
            await diary.write("agent_b", "sess-2", "log entry", topic="ops")

        _, kwargs = kb.store_fact.call_args
        meta = kwargs["metadata"]
        assert meta["category"] == AgentDiaryService.CATEGORY
        assert meta["source"] == "agent_b"
        assert meta["session_id"] == "sess-2"
        assert meta["topic"] == "ops"
        assert "diary_timestamp" in meta

    @pytest.mark.asyncio
    async def test_write_graceful_on_kb_error(self):
        kb = MagicMock()
        kb.store_fact = AsyncMock(side_effect=RuntimeError("KB down"))
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            diary = AgentDiaryService()
            fact_id = await diary.write("agent_c", "sess-3", "entry")
        # Must not raise; returns empty string
        assert fact_id == ""


# ---------------------------------------------------------------------------
# read()
# ---------------------------------------------------------------------------

class TestRead:
    @pytest.mark.asyncio
    async def test_read_returns_newest_first(self):
        results = [
            _result_with_ts("2026-01-01T10:00:00+00:00"),
            _result_with_ts("2026-01-03T10:00:00+00:00"),
            _result_with_ts("2026-01-02T10:00:00+00:00"),
        ]
        kb = _make_kb_mock(search_result=results)
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            diary = AgentDiaryService()
            entries = await diary.read("agent_a", last_n=3)

        timestamps = [e["metadata"]["diary_timestamp"] for e in entries]
        assert timestamps == sorted(timestamps, reverse=True)

    @pytest.mark.asyncio
    async def test_read_respects_last_n(self):
        results = [_result_with_ts(f"2026-01-0{i}T00:00:00+00:00") for i in range(1, 6)]
        kb = _make_kb_mock(search_result=results)
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            diary = AgentDiaryService()
            entries = await diary.read("agent_a", last_n=2)
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_read_empty_diary_returns_empty_list(self):
        kb = _make_kb_mock(search_result=[])
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            diary = AgentDiaryService()
            entries = await diary.read("agent_x")
        assert entries == []

    @pytest.mark.asyncio
    async def test_read_graceful_on_kb_error(self):
        kb = MagicMock()
        kb.search = AsyncMock(side_effect=RuntimeError("KB down"))
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            diary = AgentDiaryService()
            entries = await diary.read("agent_y")
        assert entries == []


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------

class TestSearch:
    @pytest.mark.asyncio
    async def test_search_passes_correct_filters(self):
        kb = _make_kb_mock(search_result=[{"content": "match", "metadata": {}}])
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            diary = AgentDiaryService()
            results = await diary.search("agent_a", "some query", n=3)

        assert len(results) == 1
        _, kwargs = kb.search.call_args
        assert kwargs["filters"]["source"] == "agent_a"
        assert kwargs["filters"]["category"] == AgentDiaryService.CATEGORY
        assert kwargs["top_k"] == 3

    @pytest.mark.asyncio
    async def test_search_empty_result(self):
        kb = _make_kb_mock(search_result=[])
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            diary = AgentDiaryService()
            results = await diary.search("agent_a", "nothing here")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_graceful_on_kb_error(self):
        kb = MagicMock()
        kb.search = AsyncMock(side_effect=RuntimeError("KB down"))
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            diary = AgentDiaryService()
            results = await diary.search("agent_z", "query")
        assert results == []
