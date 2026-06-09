# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for ContextTracker (#2005)."""

from knowledge.search_components.context_tracker import ContextTracker


def make_chunks(chunk_ids: list[str]) -> list[dict]:
    return [{"chunk_id": cid, "text": f"text_{cid}"} for cid in chunk_ids]


def test_filter_returns_all_first_call():
    tracker = ContextTracker(query_session_id="session-1")
    chunks = make_chunks(["a", "b", "c"])
    result = tracker.filter_unseen(chunks)
    assert result == chunks


def test_filter_removes_seen_chunks():
    tracker = ContextTracker(query_session_id="session-2")
    chunks = make_chunks(["a", "b", "c"])
    tracker.record(["a", "b"], tokens=100)
    result = tracker.filter_unseen(chunks)
    assert len(result) == 1
    assert result[0]["chunk_id"] == "c"


def test_token_budget_tracking():
    tracker = ContextTracker(query_session_id="session-3", token_budget=500)
    assert tracker.tokens_remaining == 500
    tracker.record(["x"], tokens=200)
    assert tracker.tokens_remaining == 300
    tracker.record(["y"], tokens=400)
    assert tracker.tokens_remaining == 0


def test_summary_returns_stats():
    tracker = ContextTracker(query_session_id="session-4", token_budget=1000)
    tracker.record(["a", "b"], tokens=150)
    summary = tracker.summary()
    assert summary["session_id"] == "session-4"
    assert summary["chunks_seen"] == 2
    assert summary["tokens_used"] == 150
    assert summary["tokens_remaining"] == 850


def test_empty_chunks_list():
    tracker = ContextTracker(query_session_id="session-5")
    result = tracker.filter_unseen([])
    assert result == []
