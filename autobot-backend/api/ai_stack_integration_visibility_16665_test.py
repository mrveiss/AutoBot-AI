# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /chat and POST /rag/query filter local KB context by the caller's access,
including for an admin caller (#16716, #16665, #16654, #16745).

Both endpoints are gated by ``check_admin_permission`` (403 for non-admins), but
that gate is not fact-visibility filtering: KB content read here feeds either the
chat prompt or the RAG synthesis documents. Owner rulings #16654 ("an admin's
chat gets no bypass") and #16745 ("chat, RAG and agent synthesis stay blocked
from the admin bypass") rule out an unconditional admin read for both.

Uses a real ``KnowledgeOwnership.check_access`` rather than mocking it away, so
this proves the routes' own filtering wiring, not just that a mock was called.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.ai_stack_integration import chat, rag_query
from api.schemas_knowledge import ChatRequest, RAGQueryRequest
from knowledge.ownership import KnowledgeOwnership


def _make_kb(search_results: list) -> MagicMock:
    kb = MagicMock()
    kb.ownership_manager = KnowledgeOwnership(redis_client=object())
    kb.search = AsyncMock(return_value=search_results)
    return kb


def _current_user(user_id: str, role: str = "user") -> dict:
    return {"user_id": user_id, "role": role}


def _fake_ai_client() -> AsyncMock:
    client = AsyncMock()
    client.rag_query.return_value = {"answer": "ok"}
    client.chat_message.return_value = {"content": "ok"}
    return client


def _others_private_fact() -> dict:
    return {
        "id": "f2",
        "content": "user u99's private fact",
        "metadata": {"owner_id": "u99", "visibility": "private"},
    }


@pytest.mark.asyncio
async def test_rag_query_hides_another_users_private_fact_from_rag_context():
    kb = _make_kb([_others_private_fact()])
    mock_ai_client = _fake_ai_client()

    with patch("api.ai_stack_integration.get_ai_stack_client", AsyncMock(return_value=mock_ai_client)):
        await rag_query(
            request=RAGQueryRequest(query="test"),
            admin_check=True,
            knowledge_base=kb,
            current_user=_current_user("u1"),
        )

    mock_ai_client.rag_query.assert_called_once()
    assert mock_ai_client.rag_query.call_args.kwargs["documents"] == [], "u1 must not see u99's private fact"


@pytest.mark.asyncio
async def test_rag_query_gives_an_admin_no_bypass_of_another_users_private_fact():
    """Negative control: an ADMIN caller must not get another user's private fact into RAG
    context either. Exercises the real filter -> check_access call; fails if the
    ``is_admin=`` bypass were restored.
    """
    kb = _make_kb([_others_private_fact()])
    mock_ai_client = _fake_ai_client()

    with patch("api.ai_stack_integration.get_ai_stack_client", AsyncMock(return_value=mock_ai_client)):
        await rag_query(
            request=RAGQueryRequest(query="test"),
            admin_check=True,
            knowledge_base=kb,
            current_user=_current_user("u2", role="admin"),
        )

    mock_ai_client.rag_query.assert_called_once()
    assert (
        mock_ai_client.rag_query.call_args.kwargs["documents"] == []
    ), "admin u2 must not get u99's private fact into RAG context (#16654/#16745)"


@pytest.mark.asyncio
async def test_chat_hides_another_users_private_fact_from_kb_context():
    kb = _make_kb([_others_private_fact()])
    mock_ai_client = _fake_ai_client()

    with patch("api.ai_stack_integration.get_ai_stack_client", AsyncMock(return_value=mock_ai_client)):
        await chat(
            request=ChatRequest(message="test", use_knowledge_base=True),
            admin_check=True,
            knowledge_base=kb,
            current_user=_current_user("u1"),
        )

    mock_ai_client.chat_message.assert_called_once()
    enhanced_context = mock_ai_client.chat_message.call_args.kwargs["context"] or ""
    assert "u99" not in enhanced_context and "private fact" not in enhanced_context


@pytest.mark.asyncio
async def test_chat_gives_an_admin_no_bypass_of_another_users_private_fact():
    """Negative control: an ADMIN caller must not get another user's private fact into the
    chat prompt either. Exercises the real filter -> check_access call; fails if the
    ``is_admin=`` bypass were restored.
    """
    kb = _make_kb([_others_private_fact()])
    mock_ai_client = _fake_ai_client()

    with patch("api.ai_stack_integration.get_ai_stack_client", AsyncMock(return_value=mock_ai_client)):
        await chat(
            request=ChatRequest(message="test", use_knowledge_base=True),
            admin_check=True,
            knowledge_base=kb,
            current_user=_current_user("u2", role="admin"),
        )

    mock_ai_client.chat_message.assert_called_once()
    enhanced_context = mock_ai_client.chat_message.call_args.kwargs["context"] or ""
    assert "u99" not in enhanced_context and "private fact" not in enhanced_context, (
        "admin u2 must not get u99's private fact into the chat prompt (#16654/#16745): " f"{enhanced_context!r}"
    )
