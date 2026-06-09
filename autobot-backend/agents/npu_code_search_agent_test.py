# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for NPU code search agent - Issue #3290.

Covers:
- NPU device is used (not CPU fallback) when OpenVINO model is compiled on NPU
- CPU fallback is reported accurately when NPU is unavailable
- search_code() stats reflect actual device used, not just npu_available flag
- _fallback_word_matching sets npu_acceleration_used=False
- get_index_status exposes NPU utilisation fields
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.npu_code_search_agent import CodeSearchResult, NPUCodeSearchAgent, SearchStats

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_agent(npu_available: bool = True) -> NPUCodeSearchAgent:
    """Construct a minimally-initialised NPUCodeSearchAgent for testing."""
    with (
        patch("agents.npu_code_search_agent.get_redis_client", return_value=MagicMock()),
        patch("agents.npu_code_search_agent.WorkerNode") as mock_worker,
    ):
        mock_worker.return_value.detect_capabilities.return_value = {
            "openvino_npu_available": npu_available,
        }
        # Patch Core so _init_npu doesn't need real OpenVINO
        with patch("agents.npu_code_search_agent.Core", MagicMock(), create=True):
            agent = NPUCodeSearchAgent.__new__(NPUCodeSearchAgent)
            # Manually set required attributes to avoid full __init__
            agent.logger = MagicMock()
            agent.redis_client = MagicMock()
            agent.redis_async_client = None
            agent.npu_available = npu_available
            agent.npu_search_engine = None
            agent.index_prefix = "autobot:code:index:"
            agent.search_cache_prefix = "autobot:search:cache:"
            agent.cache_ttl = 3600
            agent.stats = SearchStats(0, 0.0, False, False, 0)
            agent.supported_extensions = NPUCodeSearchAgent._get_supported_extensions()
            agent.language_patterns = NPUCodeSearchAgent._get_language_patterns()
    return agent


def _make_code_result(file_path: str = "foo.py", confidence: float = 0.9) -> CodeSearchResult:
    return CodeSearchResult(
        file_path=file_path,
        content="def foo(): pass",
        line_number=1,
        confidence=confidence,
        context_lines=[],
        metadata={"search_type": "semantic_embedding", "device_used": "npu"},
    )


# ---------------------------------------------------------------------------
# Tests: search_code() stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_code_stats_reflect_actual_device_npu():
    """search_code() must not overwrite npu_acceleration_used set by sub-methods."""
    agent = _make_agent(npu_available=True)
    expected_result = [_make_code_result()]

    # Simulate _execute_search_by_type setting stats via _search_code_embeddings
    async def _fake_execute(query, search_type, language, max_results):
        agent.stats.npu_acceleration_used = True  # set by real embedding path
        return expected_result

    agent.redis_client.get = MagicMock(return_value=None)  # no cache hit

    async def _fake_redis_get(cache_key):
        return None

    async def _fake_redis_setex(key, ttl, value):
        pass

    with (
        patch.object(agent, "_execute_search_by_type", side_effect=_fake_execute),
        patch(
            "agents.npu_code_search_agent.asyncio.to_thread",
            new=AsyncMock(return_value=None),
        ),
    ):
        results = await agent.search_code("find auth function", search_type="semantic")

    assert results == expected_result
    # Issue #3290: npu_acceleration_used must reflect what _fake_execute set (True)
    assert agent.stats.npu_acceleration_used is True


@pytest.mark.asyncio
async def test_search_code_stats_reflect_actual_device_cpu_fallback():
    """When embedding search fails and word-matching runs, npu_acceleration_used=False."""
    agent = _make_agent(npu_available=True)

    async def _fake_execute(query, search_type, language, max_results):
        # Simulate the fallback path having run (sets False)
        agent.stats.npu_acceleration_used = False
        return []

    with (
        patch.object(agent, "_execute_search_by_type", side_effect=_fake_execute),
        patch(
            "agents.npu_code_search_agent.asyncio.to_thread",
            new=AsyncMock(return_value=None),
        ),
    ):
        await agent.search_code("find something", search_type="semantic")

    # Issue #3290: must NOT override False with True just because npu_available=True
    assert agent.stats.npu_acceleration_used is False


# ---------------------------------------------------------------------------
# Tests: _fallback_word_matching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_word_matching_marks_npu_not_used():
    """_fallback_word_matching must set npu_acceleration_used=False."""
    agent = _make_agent(npu_available=True)
    agent.stats.npu_acceleration_used = True  # pretend it was set earlier

    with patch(
        "agents.npu_code_search_agent.asyncio.to_thread",
        new=AsyncMock(return_value=[]),  # no indexed files
    ):
        results = await agent._fallback_word_matching("auth", None, 10)

    assert results == []
    # Issue #3290: word-matching path must mark NPU as NOT used
    assert agent.stats.npu_acceleration_used is False


# ---------------------------------------------------------------------------
# Tests: get_index_status NPU fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_index_status_exposes_npu_fields():
    """get_index_status must include npu_acceleration_used and last_search_device."""
    agent = _make_agent(npu_available=True)
    agent.stats.npu_acceleration_used = True

    def _fake_thread_call(fn, *args, **kwargs):
        # Return (file_count, language_stats, cache_count)
        return fn()

    def _fetch_status():
        return 5, {"python": 3, "javascript": 2}, 1

    with patch(
        "agents.npu_code_search_agent.asyncio.to_thread",
        new=AsyncMock(return_value=(5, {"python": 3}, 1)),
    ):
        status = await agent.get_index_status()

    assert "npu_acceleration_used" in status
    assert "last_search_device" in status
    assert status["npu_acceleration_used"] is True
    assert status["last_search_device"] == "npu"


@pytest.mark.asyncio
async def test_get_index_status_last_device_cpu_when_not_npu():
    """last_search_device must be 'cpu' when npu_acceleration_used=False."""
    agent = _make_agent(npu_available=False)
    agent.stats.npu_acceleration_used = False

    with patch(
        "agents.npu_code_search_agent.asyncio.to_thread",
        new=AsyncMock(return_value=(0, {}, 0)),
    ):
        status = await agent.get_index_status()

    assert status["last_search_device"] == "cpu"
