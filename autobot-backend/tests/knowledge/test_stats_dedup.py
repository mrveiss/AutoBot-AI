# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Verify that both stats endpoints share the same canonical source (Issue #11554).

Tests:
1. ``fetch_kb_core_stats`` delegates to ``kb.get_stats()`` with no transformation.
2. Both ``get_knowledge_stats`` and ``get_health_dashboard`` call
   ``fetch_kb_core_stats`` — confirmed by patching it and asserting one call
   per endpoint invocation with the same KB instance.
3. Core numbers emitted by both endpoints originate from the same dict, so they
   cannot drift independently.

Heavy transitive deps (Redis, ChromaDB, llama_index, FastAPI request context)
are stubbed via sys.modules and AsyncMock so no live infrastructure is needed.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy modules BEFORE any knowledge/* or api/* import
# ---------------------------------------------------------------------------

for _mod_name in (
    "llama_index",
    "llama_index.core",
    "llama_index.vector_stores",
    "llama_index.vector_stores.chroma",
    "llama_index.llms",
    "llama_index.llms.ollama",
    "llama_index.embeddings",
    "llama_index.embeddings.ollama",
    "chromadb",
    "redis",
    "redis.asyncio",
):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

# Redis stubs need concrete attributes
_redis_mod = sys.modules["redis"]
_redis_mod.RedisError = Exception  # type: ignore[attr-defined]
_redis_mod.Redis = MagicMock  # type: ignore[attr-defined]
_redis_mod.asyncio = sys.modules["redis.asyncio"]  # type: ignore[attr-defined]
sys.modules["redis.asyncio"].Redis = MagicMock  # type: ignore[attr-defined]

from services.knowledge.stats_service import fetch_kb_core_stats  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STATS_FIXTURE = {
    "total_facts": 42,
    "total_vectors": 38,
    "db_size": 12345,
    "categories": ["system/manpages", "user_knowledge"],
    "status": "online",
    "initialized": True,
    "last_updated": "2026-07-11T00:00:00+00:00",
    "embedding_cache": {"size": 10},
}


class _FakeKB:
    """Minimal KB stub with controllable get_stats() return value."""

    def __init__(self, stats: dict | None = None) -> None:
        self._stats = stats if stats is not None else dict(_STATS_FIXTURE)
        # Track call count so we can assert exactly one call per endpoint.
        self.get_stats_call_count = 0

    async def get_stats(self) -> dict:
        self.get_stats_call_count += 1
        return dict(self._stats)

    async def get_data_quality_metrics(self) -> dict:
        return {
            "overall_score": 87.5,
            "dimensions": {},
            "summary": {"critical_issues": 0, "warnings": 1},
            "recommendations": [],
        }


# ---------------------------------------------------------------------------
# Tests: fetch_kb_core_stats (the shared function itself)
# ---------------------------------------------------------------------------


class TestFetchKbCoreStats:
    @pytest.mark.asyncio
    async def test_returns_exact_dict_from_get_stats(self):
        """fetch_kb_core_stats must return whatever kb.get_stats() returns, unchanged."""
        kb = _FakeKB()
        result = await fetch_kb_core_stats(kb)
        assert result["total_facts"] == 42
        assert result["total_vectors"] == 38
        assert result["db_size"] == 12345
        assert result["categories"] == ["system/manpages", "user_knowledge"]
        assert result["status"] == "online"

    @pytest.mark.asyncio
    async def test_calls_get_stats_exactly_once(self):
        """fetch_kb_core_stats must call kb.get_stats() exactly once per invocation."""
        kb = _FakeKB()
        await fetch_kb_core_stats(kb)
        assert kb.get_stats_call_count == 1

    @pytest.mark.asyncio
    async def test_propagates_error_dict(self):
        """When kb.get_stats() returns an error sentinel, it is passed through."""
        error_stats = {"status": "error", "total_facts": 0, "total_vectors": 0, "db_size": 0, "categories": []}
        kb = _FakeKB(stats=error_stats)
        result = await fetch_kb_core_stats(kb)
        assert result["status"] == "error"
        assert result["total_facts"] == 0


# ---------------------------------------------------------------------------
# Tests: both endpoints read from the same source via fetch_kb_core_stats
# ---------------------------------------------------------------------------


class TestBothEndpointsShareSameSource:
    """Patch fetch_kb_core_stats and assert both endpoint code-paths call it.

    This is the regression guard: if either endpoint were ever changed to call
    kb.get_stats() directly again (bypassing the shared function), these tests
    would fail — surfacing the drift risk before it reaches production.
    """

    @pytest.mark.asyncio
    async def test_get_knowledge_stats_calls_fetch_kb_core_stats(self):
        """api.knowledge.get_knowledge_stats must delegate to fetch_kb_core_stats."""
        kb = _FakeKB()
        fetch_mock = AsyncMock(return_value=dict(_STATS_FIXTURE))

        # Patch at the import site inside api.knowledge
        with patch("api.knowledge.fetch_kb_core_stats", fetch_mock), patch(
            "api.knowledge.get_or_create_knowledge_base", AsyncMock(return_value=kb)
        ), patch("api.knowledge.RAG_AVAILABLE", False):
            from api.knowledge import get_knowledge_stats

            # Build a minimal fake FastAPI request
            mock_req = MagicMock()
            mock_req.app = MagicMock()

            await get_knowledge_stats(admin_check=True, req=mock_req)

        fetch_mock.assert_called_once_with(kb)

    @pytest.mark.asyncio
    async def test_get_health_dashboard_calls_fetch_kb_core_stats(self):
        """api.knowledge_maintenance.get_health_dashboard must delegate to fetch_kb_core_stats."""
        kb = _FakeKB()
        fetch_mock = AsyncMock(return_value=dict(_STATS_FIXTURE))

        with patch("api.knowledge_maintenance.fetch_kb_core_stats", fetch_mock), patch(
            "api.knowledge_maintenance.get_or_create_knowledge_base", AsyncMock(return_value=kb)
        ):
            from api.knowledge_maintenance import get_health_dashboard

            mock_req = MagicMock()
            mock_req.app = MagicMock()

            await get_health_dashboard(admin_check=True, req=mock_req)

        fetch_mock.assert_called_once_with(kb)

    @pytest.mark.asyncio
    async def test_both_endpoints_see_same_core_numbers(self):
        """Core stat numbers from both endpoints originate from the same dict."""
        shared_stats = {
            "total_facts": 99,
            "total_vectors": 77,
            "db_size": 55555,
            "categories": ["alpha", "beta"],
            "status": "online",
            "initialized": True,
            "last_updated": "2026-07-11T00:00:00+00:00",
            "embedding_cache": {"size": 5},
        }
        kb = _FakeKB(stats=shared_stats)

        # Simulate what each endpoint does after receiving stats from fetch_kb_core_stats
        stats_result = await fetch_kb_core_stats(kb)

        # stats endpoint returns these fields directly
        assert stats_result["total_facts"] == 99
        assert stats_result["total_vectors"] == 77
        assert stats_result["db_size"] == 55555

        # health/dashboard endpoint extracts via _build_stats_summary
        from api.knowledge_maintenance import _build_stats_summary

        summary = _build_stats_summary(stats_result)
        assert summary["total_facts"] == 99
        assert summary["total_vectors"] == 77
        assert summary["db_size"] == 55555
        assert summary["categories"] == 2  # count of categories list
