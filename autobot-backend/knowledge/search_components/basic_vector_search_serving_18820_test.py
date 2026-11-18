# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""KB search is the store's grounding read; it never returns a rejected fact (#18820, #18829).

The shared grounding filter (``knowledge/quarantine.py``) already excludes rejected
facts store-side. These tests simulate the vector store ignoring that ``where`` -- a
backend bug -- and require ``KB.search`` to apply the serving predicate as the final
check on both legs, whether or not the query carried the grounding filter.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge.search import SearchMixin
from knowledge.vector_search_engine import VectorSearchResult

_ENGINE = "knowledge.search_components.basic_vector_search.get_vector_search_engine"

_METADATA = {
    "ok": {"fact_id": "ok", "verification_status": "verified"},
    "rejected": {"fact_id": "rejected", "verification_status": "rejected"},
    "garbage": {"fact_id": "garbage", "valid_to": "garbage"},
    "expired": {"fact_id": "expired", "valid_until": "2020-01-01T00:00:00+00:00"},
    "open": {"fact_id": "open", "valid_until": "2999-01-01T00:00:00+00:00"},
    "unverified": {"fact_id": "unverified", "verification_status": "unverified"},
    "pending": {"fact_id": "pending", "verification_status": "pending_review"},
}
_SERVED = ["ok", "open", "unverified", "pending"]


class _Store(SearchMixin):
    """A SearchMixin host whose vector store returns every fact, ignoring ``where``."""

    def __init__(self, fallback_hits=()) -> None:
        super().__init__()
        self.vector_store = MagicMock()
        self._fallback_hits = list(fallback_hits)

    def ensure_initialized(self) -> None:
        """No-op: the real impl lives in KnowledgeBaseCore."""

    async def record_fact_access(self, fact_ids) -> None:
        """No-op: usage tracking is not under test."""

    async def _execute_vector_search(self, query, similarity_top_k, filters=None):
        return list(self._fallback_hits)


def _engine_returning_everything() -> MagicMock:
    engine = MagicMock()
    engine.search = AsyncMock(
        return_value=[VectorSearchResult(text=k, score=0.9, metadata=m, source=k) for k, m in _METADATA.items()]
    )
    return engine


def _ids(results) -> list:
    return [r["metadata"]["fact_id"] for r in results]


@pytest.mark.asyncio
async def test_a_grounding_search_never_returns_a_rejected_or_invalid_fact():
    with patch(_ENGINE, AsyncMock(return_value=_engine_returning_everything())):
        results = await _Store().search("what is autobot", top_k=10, filters=RESEARCH_QUARANTINE_FILTER)

    assert _ids(results) == _SERVED


@pytest.mark.asyncio
async def test_the_fallback_leg_gets_the_same_final_check():
    hits = [{"content": k, "score": 0.9, "metadata": m} for k, m in _METADATA.items()]
    with patch(_ENGINE, AsyncMock(side_effect=RuntimeError("engine down"))):
        results = await _Store(hits).search("what is autobot", top_k=10, filters=RESEARCH_QUARANTINE_FILTER)

    assert _ids(results) == _SERVED


@pytest.mark.asyncio
async def test_a_search_without_the_grounding_filter_is_filtered_too():
    """The check does not depend on the caller's `where`: a reader that forgot the clause is covered."""
    with patch(_ENGINE, AsyncMock(return_value=_engine_returning_everything())):
        results = await _Store().search("what is autobot", top_k=10, filters={"category": "docs"})

    assert _ids(results) == _SERVED


@pytest.mark.asyncio
async def test_include_unservable_is_the_explicit_opt_out():
    with patch(_ENGINE, AsyncMock(return_value=_engine_returning_everything())):
        results = await _Store().search("what is autobot", top_k=10, include_unservable=True)

    assert _ids(results) == list(_METADATA)
