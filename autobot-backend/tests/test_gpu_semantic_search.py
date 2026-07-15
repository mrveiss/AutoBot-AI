# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for _gpu_semantic_search wire-in. Issue #10716.

Verifies:
  (a) query with KB hits → search_results populated + total_results > 0
  (b) empty/missing query → empty shape, no crash
  (c) kb.search raising → empty shape, no exception
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RAW_KB_ROW = {
    "content": "AutoBot is an AI platform",
    "node_id": "node-abc",
    "score": 0.92,
    "metadata": {"source": "readme"},
}

_EMPTY_SHAPE = {
    "search_results": [],
    "total_results": 0,
    "search_time_ms": 0,
    "device": "GPU",
}


def _make_accelerator():
    """Return an AIHardwareAccelerator with __init__ bypassed to avoid real I/O."""
    from ai_hardware_accelerator import AIHardwareAccelerator

    obj = AIHardwareAccelerator.__new__(AIHardwareAccelerator)
    return obj


def _make_kb_mock(rows):
    kb = AsyncMock()
    kb.search = AsyncMock(return_value=rows)
    return kb


# ---------------------------------------------------------------------------
# (a) Happy path — KB returns hits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gpu_semantic_search_returns_results_on_kb_hit():
    obj = _make_accelerator()
    kb_mock = _make_kb_mock([_RAW_KB_ROW])

    with patch(
        "knowledge_base_factory.get_knowledge_base",
        AsyncMock(return_value=kb_mock),
    ):
        result = await obj._gpu_semantic_search({"query": "what is AutoBot", "top_k": 3})

    assert result["device"] == "GPU"
    assert result["total_results"] == 1
    assert len(result["search_results"]) == 1
    assert result["search_time_ms"] >= 0
    item = result["search_results"][0]
    assert item["content"] == "AutoBot is an AI platform"
    assert item["source"] == "node-abc"
    assert item["score"] == pytest.approx(0.92)


# ---------------------------------------------------------------------------
# (b) Missing / empty query → empty shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gpu_semantic_search_empty_query_returns_empty():
    obj = _make_accelerator()

    with patch("knowledge_base_factory.get_knowledge_base", AsyncMock()) as mock_get_kb:
        result_missing = await obj._gpu_semantic_search({})
        result_empty = await obj._gpu_semantic_search({"query": ""})

    # get_knowledge_base should never be called when query is absent/empty
    mock_get_kb.assert_not_awaited()

    for result in (result_missing, result_empty):
        assert result["search_results"] == []
        assert result["total_results"] == 0
        assert result["device"] == "GPU"


# ---------------------------------------------------------------------------
# (b2) KB unavailable (returns None) → empty shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gpu_semantic_search_kb_none_returns_empty():
    obj = _make_accelerator()

    with patch("knowledge_base_factory.get_knowledge_base", AsyncMock(return_value=None)):
        result = await obj._gpu_semantic_search({"query": "some query"})

    assert result["search_results"] == []
    assert result["total_results"] == 0
    assert result["device"] == "GPU"


# ---------------------------------------------------------------------------
# (c) kb.search raises → empty shape, no exception propagated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gpu_semantic_search_kb_raises_returns_empty():
    obj = _make_accelerator()
    kb_mock = AsyncMock()
    kb_mock.search = AsyncMock(side_effect=RuntimeError("vector store offline"))

    with patch("knowledge_base_factory.get_knowledge_base", AsyncMock(return_value=kb_mock)):
        result = await obj._gpu_semantic_search({"query": "failing query"})

    assert result["search_results"] == []
    assert result["total_results"] == 0
    assert result["device"] == "GPU"


# ---------------------------------------------------------------------------
# Default top_k is applied when not in input_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gpu_semantic_search_uses_default_top_k():
    from ai_hardware_accelerator import _DEFAULT_SEMANTIC_SEARCH_TOP_K

    obj = _make_accelerator()
    kb_mock = _make_kb_mock([])

    with patch("knowledge_base_factory.get_knowledge_base", AsyncMock(return_value=kb_mock)):
        await obj._gpu_semantic_search({"query": "top-k default test"})

    kb_mock.search.assert_awaited_once_with(query="top-k default test", top_k=_DEFAULT_SEMANTIC_SEARCH_TOP_K)
