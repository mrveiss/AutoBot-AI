# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /search and POST /search/rag filter local KB results by the caller's
access (#16665). Uses a real KnowledgeOwnership.check_access rather than
mocking it away, so this proves the route's own filtering wiring.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.knowledge_ai_stack import search
from api.schemas_knowledge import AIStackRAGQueryRequest, AIStackSearchRequest
from knowledge.ownership import KnowledgeOwnership


def _make_kb(search_results: list) -> MagicMock:
    kb = MagicMock()
    kb.ownership_manager = KnowledgeOwnership(redis_client=object())
    kb.search = AsyncMock(return_value=search_results)
    return kb


def _current_user(user_id: str, role: str = "user") -> dict:
    return {"user_id": user_id, "role": role}


@pytest.mark.asyncio
async def test_search_hides_another_users_private_fact_from_local_results():
    mine = {"id": "f1", "content": "mine", "score": 0.9, "metadata": {"owner_id": "u1", "visibility": "private"}}
    others_private = {
        "id": "f2",
        "content": "not mine",
        "score": 0.9,
        "metadata": {"owner_id": "u99", "visibility": "private"},
    }
    kb = _make_kb([mine, others_private])

    mock_ai_client = AsyncMock()
    mock_ai_client.search_knowledge.return_value = {"results": []}

    with (
        patch("api.knowledge_ai_stack.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("api.knowledge_ai_stack.get_ai_stack_client", AsyncMock(return_value=mock_ai_client)),
    ):
        result = await search(
            request_data=AIStackSearchRequest(query="test", include_rag=False),
            req=MagicMock(),
            knowledge_base=kb,
            current_user=_current_user("u1"),
        )

    local_results = result.data["source_breakdown"]["local_knowledge_base"]["results"]
    ids = {r["id"] for r in local_results}
    assert ids == {"f1"}, f"user u1 must not see u99's private fact: {local_results}"


@pytest.mark.asyncio
async def test_rag_search_hides_another_users_private_fact_from_rag_context():
    from api.knowledge_ai_stack import rag_search

    others_private = {
        "id": "f2",
        "content": "not mine",
        "metadata": {"owner_id": "u99", "visibility": "private"},
    }
    kb = _make_kb([others_private])

    mock_ai_client = AsyncMock()
    mock_ai_client.rag_query.return_value = {"answer": "ok"}

    with patch("api.knowledge_ai_stack.get_ai_stack_client", AsyncMock(return_value=mock_ai_client)):
        result = await rag_search(
            request_data=AIStackRAGQueryRequest(query="test"),
            knowledge_base=kb,
            current_user=_current_user("u1"),
        )

    assert result.data["documents_used"] == 0, "the private fact must not reach the RAG context"
    mock_ai_client.rag_query.assert_called_once()
    assert mock_ai_client.rag_query.call_args.kwargs["documents"] == []


@pytest.mark.asyncio
async def test_search_lets_an_admin_read_another_users_private_fact():
    others_private = {
        "id": "f2",
        "content": "not mine",
        "score": 0.9,
        "metadata": {"owner_id": "u99", "visibility": "private"},
    }
    kb = _make_kb([others_private])

    mock_ai_client = AsyncMock()
    mock_ai_client.search_knowledge.return_value = {"results": []}

    with (
        patch("api.knowledge_ai_stack.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("api.knowledge_ai_stack.get_ai_stack_client", AsyncMock(return_value=mock_ai_client)),
    ):
        result = await search(
            request_data=AIStackSearchRequest(query="test", include_rag=False),
            req=MagicMock(),
            knowledge_base=kb,
            current_user=_current_user("u2", role="admin"),
        )

    local_results = result.data["source_breakdown"]["local_knowledge_base"]["results"]
    ids = {r["id"] for r in local_results}
    assert ids == {"f2"}, "an explicit admin read must see every fact (#16665)"
