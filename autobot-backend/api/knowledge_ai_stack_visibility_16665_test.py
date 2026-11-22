# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /search/rag filters local KB results used as RAG context by the caller's
access (#16665). Uses a real KnowledgeOwnership.check_access rather than
mocking it away, so this proves the route's own filtering wiring.

Issue #16654/#16745: this feeds RAG synthesis, so an admin caller gets no
bypass here either -- confirmed by the admin-role negative control below.

#16908: this file used to also cover POST /search (knowledge_ai_stack.search),
including its own admin-bypass negative control -- that handler was dead code
(shadowed by api/knowledge_search.py's own POST /search, registered earlier)
and was deleted rather than re-pathed, so its tests were deleted with it, not
carried forward.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas_knowledge import AIStackRAGQueryRequest
from knowledge.ownership import KnowledgeOwnership
from knowledge.read_path_fakes_16665 import RESEARCH, QuarantineGatedKB, quarantined_fact


def _make_kb(search_results: list) -> MagicMock:
    kb = MagicMock()
    kb.ownership_manager = KnowledgeOwnership(redis_client=object())
    kb.search = AsyncMock(return_value=search_results)
    return kb


def _current_user(user_id: str, role: str = "user") -> dict:
    return {"user_id": user_id, "role": role}


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
async def test_rag_search_gives_an_admin_no_bypass_of_another_users_private_fact_in_rag_context():
    """Negative control for #16716/#16665/#16654/#16745: an ADMIN caller must not get another
    user's private fact into the RAG synthesis context either. Exercises the real
    ``filter_search_results_by_permission`` -> ``KnowledgeOwnership.check_access`` call, not a
    mock that trivially returns nothing -- fails if the ``is_admin=`` bypass were restored.
    """
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
            current_user=_current_user("u2", role="admin"),
        )

    assert result.data["documents_used"] == 0, "admin u2 must not get u99's private fact into RAG context"
    mock_ai_client.rag_query.assert_called_once()
    assert mock_ai_client.rag_query.call_args.kwargs["documents"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "admin"])
async def test_rag_search_never_feeds_a_research_quarantined_fact_into_rag_context(role):
    """AC3 (#16665): the quarantined fact is the only fact held; the ungated twin proves it would reach the context."""
    from api.knowledge_ai_stack import rag_search

    async def documents_for(kb) -> list:
        ai_client = AsyncMock()
        ai_client.rag_query.return_value = {"answer": "ok"}
        with (
            patch("api.knowledge_ai_stack.get_ai_stack_client", AsyncMock(return_value=ai_client)),
            patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
        ):
            await rag_search(
                request_data=AIStackRAGQueryRequest(query="test"),
                knowledge_base=kb,
                current_user=_current_user("u1", role=role),
            )
        return ai_client.rag_query.call_args.kwargs["documents"]

    ungated = QuarantineGatedKB(only_quarantined=True)
    ungated.search = AsyncMock(return_value=[quarantined_fact()])

    assert RESEARCH in repr(await documents_for(ungated)), "control: ungated, the fact reaches the RAG context"
    assert await documents_for(QuarantineGatedKB(only_quarantined=True)) == []
