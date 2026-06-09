# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for AgentDiaryService and list_with_diaries.

Mocks ``memory.agent_diary._get_kb`` so no real KB connection is required.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

# Add backend root and repo root (for autobot_shared) to path
_backend_root = os.path.join(os.path.dirname(__file__), "..")
_repo_root = os.path.join(_backend_root, "..")
sys.path.insert(0, _backend_root)
sys.path.insert(0, _repo_root)

from memory.agent_diary import AgentDiaryService, list_with_diaries

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_kb_mock(
    store_result: dict | None = None,
    all_facts: list | None = None,
    search_results: list | None = None,
):
    """Return an AsyncMock knowledge base with configurable responses."""
    kb = AsyncMock()
    kb.store_fact.return_value = store_result or {"fact_id": "fact-001", "status": "created"}
    kb.get_all_facts.return_value = all_facts or []
    kb.search.return_value = search_results or []
    return kb


def _make_diary_fact(
    agent_name: str,
    content: str = "did something",
    timestamp: str = "2025-01-01T00:00:00+00:00",
    topic: str = "turn",
) -> dict:
    return {
        "content": content,
        "metadata": {
            "category": AgentDiaryService.CATEGORY,
            "source": agent_name,
            "agent_name": agent_name,
            "session_id": "sess-1",
            "topic": topic,
            "diary_timestamp": timestamp,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_write_returns_fact_id():
    """write() returns the fact_id from KB store_fact."""
    kb = _make_kb_mock(store_result={"fact_id": "abc123", "status": "created"})
    with patch("memory.agent_diary._get_kb", new=AsyncMock(return_value=kb)):
        diary = AgentDiaryService()
        fact_id = await diary.write("chat", "sess-1", "processed hello", topic="turn")
    assert fact_id == "abc123", f"Expected 'abc123', got {fact_id!r}"
    kb.store_fact.assert_awaited_once()
    print("[PASS] test_write_returns_fact_id")


async def test_write_swallows_errors():
    """write() returns '' and does not raise on KB failure."""
    kb = AsyncMock()
    kb.store_fact.side_effect = RuntimeError("KB unavailable")
    with patch("memory.agent_diary._get_kb", new=AsyncMock(return_value=kb)):
        diary = AgentDiaryService()
        result = await diary.write("chat", "sess-1", "entry", topic="turn")
    assert result == "", f"Expected empty string, got {result!r}"
    print("[PASS] test_write_swallows_errors")


async def test_read_filters_by_agent_and_category():
    """read() returns only facts matching agent_name and AGENT_DIARY category."""
    facts = [
        _make_diary_fact("chat", "entry A", "2025-01-02T10:00:00+00:00"),
        _make_diary_fact("rag", "entry B", "2025-01-02T09:00:00+00:00"),
        _make_diary_fact("chat", "entry C", "2025-01-02T11:00:00+00:00"),
        {"content": "unrelated", "metadata": {"category": "OTHER", "source": "chat"}},
    ]
    kb = _make_kb_mock(all_facts=facts)
    with patch("memory.agent_diary._get_kb", new=AsyncMock(return_value=kb)):
        diary = AgentDiaryService()
        entries = await diary.read("chat", last_n=10)

    assert len(entries) == 2, f"Expected 2 entries for 'chat', got {len(entries)}"
    # Newest first: entry C (11:00) before entry A (10:00)
    assert entries[0]["content"] == "entry C"
    assert entries[1]["content"] == "entry A"
    print("[PASS] test_read_filters_by_agent_and_category")


async def test_read_respects_last_n():
    """read() caps results at last_n."""
    facts = [_make_diary_fact("rag", f"entry {i}", f"2025-01-01T{i:02d}:00:00+00:00") for i in range(10)]
    kb = _make_kb_mock(all_facts=facts)
    with patch("memory.agent_diary._get_kb", new=AsyncMock(return_value=kb)):
        diary = AgentDiaryService()
        entries = await diary.read("rag", last_n=3)
    assert len(entries) == 3, f"Expected 3, got {len(entries)}"
    print("[PASS] test_read_respects_last_n")


async def test_read_swallows_errors():
    """read() returns [] and does not raise on KB failure."""
    kb = AsyncMock()
    kb.get_all_facts.side_effect = RuntimeError("KB down")
    with patch("memory.agent_diary._get_kb", new=AsyncMock(return_value=kb)):
        diary = AgentDiaryService()
        result = await diary.read("chat")
    assert result == []
    print("[PASS] test_read_swallows_errors")


async def test_search_delegates_to_kb():
    """search() calls kb.search with correct filters and returns results."""
    hits = [{"content": "found it", "score": 0.9}]
    kb = _make_kb_mock(search_results=hits)
    with patch("memory.agent_diary._get_kb", new=AsyncMock(return_value=kb)):
        diary = AgentDiaryService()
        results = await diary.search("research", "processed", n=3)
    assert results == hits
    kb.search.assert_awaited_once_with(
        query="processed",
        top_k=3,
        filters={"source": "research", "category": AgentDiaryService.CATEGORY},
    )
    print("[PASS] test_search_delegates_to_kb")


async def test_search_swallows_errors():
    """search() returns [] and does not raise on KB failure."""
    kb = AsyncMock()
    kb.search.side_effect = RuntimeError("search failed")
    with patch("memory.agent_diary._get_kb", new=AsyncMock(return_value=kb)):
        diary = AgentDiaryService()
        result = await diary.search("chat", "query")
    assert result == []
    print("[PASS] test_search_swallows_errors")


async def test_list_with_diaries_parallel():
    """list_with_diaries() returns one dict per agent with recent_entries."""
    facts_chat = [_make_diary_fact("chat", "chat entry")]
    facts_rag: list = []  # no entries

    async def fake_kb_for_agent(*_args, **_kwargs):
        return _make_kb_mock(all_facts=facts_chat + facts_rag)

    # Use real read() but patch _get_kb so chat and rag use same fact pool;
    # filtering separates them.
    all_facts = [
        _make_diary_fact("chat", "chat entry", "2025-01-01T12:00:00+00:00"),
    ]
    kb = _make_kb_mock(all_facts=all_facts)
    with patch("memory.agent_diary._get_kb", new=AsyncMock(return_value=kb)):
        result = await list_with_diaries(["chat", "rag"], last_n=3)

    assert len(result) == 2
    by_name = {r["agent_name"]: r for r in result}
    assert by_name["chat"]["entry_count"] == 1
    assert by_name["rag"]["entry_count"] == 0
    assert by_name["rag"]["recent_entries"] == []
    print("[PASS] test_list_with_diaries_parallel")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_all():
    await test_write_returns_fact_id()
    await test_write_swallows_errors()
    await test_read_filters_by_agent_and_category()
    await test_read_respects_last_n()
    await test_read_swallows_errors()
    await test_search_delegates_to_kb()
    await test_search_swallows_errors()
    await test_list_with_diaries_parallel()
    print("\n[ALL TESTS PASSED]")


if __name__ == "__main__":
    asyncio.run(run_all())
