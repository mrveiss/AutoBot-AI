# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""/search/rag, /rag/query and /chat feed KB facts to the model, scoped to the caller (#16665).

User A's private fact reaches A's prompt, never B's, and never an admin's (owner decision 2026-10-26:
prompt-feeding routes give an admin no bypass). A research-quarantined fact reaches nobody's.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api import ai_stack_integration, knowledge_ai_stack
from api.schemas_knowledge import AIStackRAGQueryRequest, ChatRequest, RAGQueryRequest
from knowledge.read_path_fakes_16665 import PRIVATE_A, RESEARCH, SHARED, FakeKB, QuarantineGatedKB, text_of

ALICE = {"user_id": "alice", "role": "user"}
BOB = {"user_id": "bob", "role": "user"}
ADMIN = {"user_id": "root", "role": "admin"}


def _client() -> AsyncMock:
    client = AsyncMock()
    client.rag_query.return_value = {"answer": "ok"}
    client.chat_message.return_value = {"content": "ok"}
    return client


async def _search_rag(user, kb) -> str:
    client = _client()
    with patch.object(knowledge_ai_stack, "get_ai_stack_client", AsyncMock(return_value=client)):
        await knowledge_ai_stack.rag_search(AIStackRAGQueryRequest(query="q"), knowledge_base=kb, current_user=user)
    return text_of(client.rag_query.call_args.kwargs["documents"])


async def _rag_query(user, kb) -> str:
    client = _client()
    with patch.object(ai_stack_integration, "get_ai_stack_client", AsyncMock(return_value=client)):
        await ai_stack_integration.rag_query(
            RAGQueryRequest(query="q"), admin_check=True, knowledge_base=kb, current_user=user
        )
    return text_of(client.rag_query.call_args.kwargs["documents"])


async def _chat(user, kb) -> str:
    client = _client()
    with patch.object(ai_stack_integration, "get_ai_stack_client", AsyncMock(return_value=client)):
        await ai_stack_integration.chat(
            ChatRequest(message="q", use_knowledge_base=True), admin_check=True, knowledge_base=kb, current_user=user
        )
    return text_of(client.chat_message.call_args.kwargs["context"])


ROUTES = [_search_rag, _rag_query, _chat]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_user_a_gets_their_private_fact_in_context_and_user_b_never_does(route):
    assert PRIVATE_A in await route(ALICE, FakeKB())
    for_bob = await route(BOB, FakeKB())

    assert PRIVATE_A not in for_bob and SHARED in for_bob


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_an_admin_gets_no_bypass_of_another_users_private_fact(route):
    body = await route(ADMIN, FakeKB())

    assert PRIVATE_A not in body and SHARED in body


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [ALICE, BOB, ADMIN])
@pytest.mark.parametrize("route", ROUTES)
async def test_a_research_quarantined_fact_never_reaches_the_context(route, user):
    body = await route(user, QuarantineGatedKB())

    assert RESEARCH not in body and SHARED in body
