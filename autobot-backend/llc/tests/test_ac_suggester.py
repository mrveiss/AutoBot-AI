# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for AcSuggester (GH#8240)."""

import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from llc.kb.ac_suggester import AcSuggester, _format_chunks, _parse_bullet_list, _zip_results

# ------------------------------------------------------------------ Helpers


def _make_chroma_result(ids, docs, metas=None):
    if metas is None:
        metas = [{}] * len(ids)
    return {"ids": [ids], "documents": [docs], "metadatas": [metas]}


# ------------------------------------------------------------------ Unit: helpers


def test_parse_bullet_list_dash():
    raw = "- Criterion one\n- Criterion two\n- Criterion three"
    assert _parse_bullet_list(raw) == ["Criterion one", "Criterion two", "Criterion three"]


def test_parse_bullet_list_asterisk():
    raw = "* Item A\n* Item B"
    assert _parse_bullet_list(raw) == ["Item A", "Item B"]


def test_parse_bullet_list_bullet():
    raw = "• Point one\n• Point two"
    assert _parse_bullet_list(raw) == ["Point one", "Point two"]


def test_parse_bullet_list_skips_non_bullets():
    raw = "Some preamble\n- Real criterion\nTrailing text"
    assert _parse_bullet_list(raw) == ["Real criterion"]


def test_parse_bullet_list_empty():
    assert _parse_bullet_list("") == []


def test_zip_results_normal():
    result = _make_chroma_result(["id1", "id2"], ["doc1", "doc2"], [{"k": 1}, {"k": 2}])
    chunks = _zip_results(result)
    assert len(chunks) == 2
    assert chunks[0] == {"id": "id1", "document": "doc1", "metadata": {"k": 1}}


def test_format_chunks_joins_with_blank_line():
    chunks = [{"document": "A"}, {"document": "B"}, {"id": "x"}]
    assert _format_chunks(chunks) == "A\n\nB"


def test_format_chunks_empty():
    assert _format_chunks([]) == ""


# ------------------------------------------------------------------ AcSuggester.suggest — cache hit


@pytest.mark.asyncio
async def test_suggest_returns_cached_result():
    suggester = AcSuggester()
    cached_value = {"suggestions": ["AC 1", "AC 2"], "sources": ["doc:1"]}

    with patch.object(suggester, "_get_cached", new=AsyncMock(return_value=cached_value)):
        with patch.object(suggester, "_call_llm", new=AsyncMock()) as mock_llm:
            result = await suggester.suggest("co1", "proj1", "Login page", "Allow users to log in")

    assert result == cached_value
    mock_llm.assert_not_called()


# ------------------------------------------------------------------ AcSuggester.suggest — full path


@pytest.mark.asyncio
async def test_suggest_full_path_calls_llm_and_caches():
    suggester = AcSuggester()

    policies = [{"id": "pol:1", "document": "Policy text", "metadata": {}}]
    past_items = [{"id": "pbi:1", "document": "Past PBI text", "metadata": {}}]
    suggestions = [
        "System accepts valid credentials",
        "System rejects invalid credentials",
        "Lockout after 5 attempts",
    ]

    mock_set_cached = AsyncMock()

    with patch.object(suggester, "_get_cached", new=AsyncMock(return_value=None)):
        with patch.object(suggester, "_query_policies", new=AsyncMock(return_value=policies)):
            with patch.object(suggester, "_query_past_items", new=AsyncMock(return_value=past_items)):
                with patch.object(suggester, "_call_llm", new=AsyncMock(return_value=suggestions)):
                    with patch.object(suggester, "_set_cached", new=mock_set_cached):
                        result = await suggester.suggest("co1", "proj1", "Login page", "desc")

    assert result["suggestions"] == suggestions
    assert "pol:1" in result["sources"]
    assert "pbi:1" in result["sources"]
    mock_set_cached.assert_called_once()


# ------------------------------------------------------------------ AcSuggester.suggest — empty collections


@pytest.mark.asyncio
async def test_suggest_with_empty_collections_still_calls_llm():
    suggester = AcSuggester()

    with patch.object(suggester, "_get_cached", new=AsyncMock(return_value=None)):
        with patch.object(suggester, "_query_policies", new=AsyncMock(return_value=[])):
            with patch.object(suggester, "_query_past_items", new=AsyncMock(return_value=[])):
                with patch.object(suggester, "_call_llm", new=AsyncMock(return_value=["Generic criterion"])):
                    with patch.object(suggester, "_set_cached", new=AsyncMock()):
                        result = await suggester.suggest("co1", "proj1", "New feature", "")

    assert result["suggestions"] == ["Generic criterion"]
    assert result["sources"] == []


# ------------------------------------------------------------------ AcSuggester.suggest — LLM failure


@pytest.mark.asyncio
async def test_suggest_llm_failure_returns_empty_suggestions():
    suggester = AcSuggester()

    with patch.object(suggester, "_get_cached", new=AsyncMock(return_value=None)):
        with patch.object(suggester, "_query_policies", new=AsyncMock(return_value=[])):
            with patch.object(suggester, "_query_past_items", new=AsyncMock(return_value=[])):
                with patch.object(suggester, "_call_llm", new=AsyncMock(return_value=[])):
                    with patch.object(suggester, "_set_cached", new=AsyncMock()):
                        result = await suggester.suggest("co1", "proj1", "Feature", "desc")

    assert result["suggestions"] == []


# ------------------------------------------------------------------ AcSuggester — parallel queries


@pytest.mark.asyncio
async def test_suggest_runs_queries_in_parallel():
    """Both _query_policies and _query_past_items must be awaited."""
    import asyncio

    suggester = AcSuggester()
    call_log = []

    async def _fake_policies(*_):
        call_log.append("policies")
        await asyncio.sleep(0)
        return []

    async def _fake_past(*_):
        call_log.append("past")
        await asyncio.sleep(0)
        return []

    with patch.object(suggester, "_get_cached", new=AsyncMock(return_value=None)):
        with patch.object(suggester, "_query_policies", side_effect=_fake_policies):
            with patch.object(suggester, "_query_past_items", side_effect=_fake_past):
                with patch.object(suggester, "_call_llm", new=AsyncMock(return_value=[])):
                    with patch.object(suggester, "_set_cached", new=AsyncMock()):
                        await suggester.suggest("co1", "proj1", "T", "D")

    assert set(call_log) == {"policies", "past"}


# ------------------------------------------------------------------ AcSuggester — cache key stability


def test_cache_key_is_deterministic():
    s = AcSuggester()
    k1 = s._cache_key("Title", "Description")
    k2 = s._cache_key("Title", "Description")
    assert k1 == k2
    assert k1.startswith("llc:ac_suggestions:")


def test_cache_key_differs_on_different_inputs():
    s = AcSuggester()
    assert s._cache_key("A", "B") != s._cache_key("A", "C")
    assert s._cache_key("A", "B") != s._cache_key("B", "B")


def test_cache_key_matches_sha256():
    s = AcSuggester()
    expected = "llc:ac_suggestions:" + hashlib.sha256("Title\x00Desc".encode("utf-8")).hexdigest()
    assert s._cache_key("Title", "Desc") == expected


def test_cache_key_no_collision_with_concat():
    s = AcSuggester()
    # "AB"+"C" must not collide with "A"+"BC" — the \x00 separator prevents this
    assert s._cache_key("AB", "C") != s._cache_key("A", "BC")
