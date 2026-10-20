# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every KB search mode is covered by the one serving check in ``SearchMixin.search`` (#18820, #18829).

Basic returns a list; enhanced (``_run_search``) and advanced (``search_ctx``) return a response dict.
Each mode below is fed a store that returns a rejected, an expired and a valid fact, and with NO
grounding ``where`` on the call -- the reader that forgot the clause -- must return only the valid one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.search import SearchMixin
from knowledge.vector_search_engine import VectorSearchResult

_ENGINE = "knowledge.search_components.basic_vector_search.get_vector_search_engine"

_METADATA = {
    "good": {"fact_id": "good"},
    "rejected": {"fact_id": "rejected", "verification_status": "rejected"},
    "expired": {"fact_id": "expired", "valid_until": "2020-01-01T00:00:00+00:00"},
}


def _hits():
    """Fresh result dicts per call: the pipeline mutates them (scores, matched_query)."""
    return [{"content": k, "score": 0.9, "metadata": dict(m), "node_id": k} for k, m in _METADATA.items()]


class _Store(SearchMixin):
    """A SearchMixin whose every retrieval leg returns all three facts, ignoring any filter."""

    def __init__(self) -> None:
        super().__init__()
        self.vector_store = MagicMock()

    def ensure_initialized(self) -> None:
        """No-op: the real impl lives in KnowledgeBaseCore."""

    async def record_fact_access(self, fact_ids) -> None:
        """No-op: usage tracking is not under test."""

    async def _keyword_search(self, query, limit, category=None):
        return _hits()

    async def _hybrid_search(self, query, limit, category=None, board_filter=None):
        return _hits()


def _engine() -> MagicMock:
    engine = MagicMock()
    engine.search = AsyncMock(
        return_value=[VectorSearchResult(text=k, score=0.9, metadata=dict(m), source=k) for k, m in _METADATA.items()]
    )
    return engine


def _ids(results) -> list:
    return [r["metadata"]["fact_id"] for r in results]


@pytest.mark.asyncio
async def test_basic_mode_is_covered():
    with patch(_ENGINE, AsyncMock(return_value=_engine())):
        assert _ids(await _Store().search("autobot", top_k=10)) == ["good"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["keyword", "semantic", "hybrid"])
async def test_enhanced_mode_is_covered_in_every_retrieval_mode(mode):
    with patch(_ENGINE, AsyncMock(return_value=_engine())):
        response = await _Store().search("autobot", limit=10, mode=mode)

    assert response["success"] is True
    assert _ids(response["results"]) == ["good"]
    assert response["total_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["keyword", "semantic", "hybrid"])
async def test_advanced_mode_is_covered_in_every_retrieval_mode(mode):
    with patch(_ENGINE, AsyncMock(return_value=_engine())):
        response = await _Store().search("autobot", limit=10, mode=mode, session_id="s", track_analytics=False)

    assert response["success"] is True
    assert _ids(response["results"]) == ["good"]
    assert response["total_count"] == 1


@pytest.mark.asyncio
async def test_include_unservable_reaches_the_pipeline_unfiltered_in_every_shape():
    store = _Store()
    with patch(_ENGINE, AsyncMock(return_value=_engine())):
        basic = await store.search("autobot", top_k=10, include_unservable=True)
        enhanced = await store.search("autobot", limit=10, mode="keyword", include_unservable=True)
        advanced = await store.search(
            "autobot", limit=10, mode="keyword", session_id="s", track_analytics=False, include_unservable=True
        )

    assert _ids(basic) == list(_METADATA)
    assert _ids(enhanced["results"]) == list(_METADATA)
    assert _ids(advanced["results"]) == list(_METADATA)
