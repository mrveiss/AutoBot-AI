# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat grounding never carries a rejected or invalid fact (#18820, #18829).

``ChatKnowledgeService`` is the chat turn's KB grounding read. Its results come from
``RAGService.advanced_search``, whose semantic/topic caches and basic fallback do not
pass through the store's grounding filter, so the serving predicate is applied here
as the final check before anything is formatted into the prompt or cited.
"""

from __future__ import annotations

import pytest

from advanced_rag_optimizer import RAGMetrics, RankedResult
from services.chat_knowledge_service import ChatKnowledgeService

# mock_rag_service: services/conftest.py


def _ranked(fact_id: str, **metadata) -> RankedResult:
    return RankedResult(
        content=f"content of {fact_id}",
        metadata={"id": fact_id, **metadata},
        semantic_score=0.9,
        keyword_score=0.9,
        hybrid_score=0.9,
        relevance_rank=1,
        source_path="kb",
        chunk_index=0,
        rerank_score=0.9,
    )


_RESULTS = [
    _ranked("verified", verification_status="verified"),
    _ranked("rejected", verification_status="rejected"),
    _ranked("garbage-valid-to", valid_to="garbage"),
    _ranked("past-valid-to", valid_to="2020-01-01T00:00:00+00:00"),
    _ranked("future-valid-to", valid_to="2999-01-01T00:00:00+00:00"),
    _ranked("unverified", verification_status="unverified"),
    _ranked("pending", verification_status="pending_review"),
]


@pytest.mark.asyncio
async def test_chat_grounding_cites_only_servable_facts(mock_rag_service) -> None:
    mock_rag_service.advanced_search.return_value = (list(_RESULTS), RAGMetrics())
    service = ChatKnowledgeService(mock_rag_service)

    context, citations = await service.retrieve_relevant_knowledge(query="q", top_k=10, score_threshold=0.0)

    # unverified and pending_review are served until #18077 decides otherwise.
    assert [c["id"] for c in citations] == ["verified", "future-valid-to", "unverified", "pending"]
    for withheld in ("rejected", "garbage-valid-to", "past-valid-to"):
        assert f"content of {withheld}" not in context
    assert "content of verified" in context
