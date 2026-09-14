# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /advanced_search filters results by the caller's access (#16665).

Uses a real KnowledgeOwnership.check_access rather than mocking it away, so
this proves the route's own filtering wiring, not just that a mock was called.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from advanced_rag_optimizer import RAGMetrics, SearchResult
from api.knowledge_rag import advanced_search
from api.schemas_knowledge import AdvancedSearchRequest
from knowledge.ownership import KnowledgeOwnership


def _result(fact_id: str, owner_id: str, visibility: str = "private") -> SearchResult:
    return SearchResult(
        content=fact_id,
        metadata={"id": fact_id, "owner_id": owner_id, "visibility": visibility},
        semantic_score=0.9,
        keyword_score=0.5,
        hybrid_score=0.8,
        relevance_rank=1,
        source_path="kb",
    )


def _make_rag_service(results: list) -> MagicMock:
    rag_service = MagicMock()
    rag_service.kb_adapter.kb.ownership_manager = KnowledgeOwnership(redis_client=object())
    rag_service.advanced_search = AsyncMock(return_value=(results, RAGMetrics()))
    return rag_service


def _current_user(user_id: str, role: str = "user") -> dict:
    return {"user_id": user_id, "role": role}


@pytest.mark.asyncio
async def test_advanced_search_hides_another_users_private_fact():
    mine = _result("f1", owner_id="u1")
    others_private = _result("f2", owner_id="u99")
    rag_service = _make_rag_service([mine, others_private])

    result = await advanced_search(
        request=AdvancedSearchRequest(query="test"),
        rag_service=rag_service,
        current_user=_current_user("u1"),
    )

    ids = {r["metadata"]["id"] for r in result["results"]}
    assert ids == {"f1"}, f"user u1 must not see u99's private fact: {result['results']}"
    assert result["total_results"] == 1


@pytest.mark.asyncio
async def test_advanced_search_lets_an_admin_read_another_users_private_fact():
    others_private = _result("f2", owner_id="u99")
    rag_service = _make_rag_service([others_private])

    result = await advanced_search(
        request=AdvancedSearchRequest(query="test"),
        rag_service=rag_service,
        current_user=_current_user("u2", role="admin"),
    )

    ids = {r["metadata"]["id"] for r in result["results"]}
    assert ids == {"f2"}, "an explicit admin read must see every fact (#16665)"
