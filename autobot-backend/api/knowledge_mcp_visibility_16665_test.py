# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The knowledge MCP read routes return only what the caller may read (#16665)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api import knowledge_mcp
from knowledge.read_path_fakes_16665 import (
    PRIVATE_A,
    PRIVATE_B,
    RESEARCH,
    FakeKB,
    QuarantineGatedKB,
    quarantined_fact,
    text_of,
)
from knowledge.schemas.mcp import KnowledgeSearchRequest

ALICE = {"user_id": "alice"}
BOB = {"user_id": "bob"}


@pytest.fixture(autouse=True)
def _kb():
    with (
        patch.object(knowledge_mcp, "get_knowledge_base", return_value=FakeKB()),
        patch.object(knowledge_mcp, "_get_chat_ollama", return_value=None),
    ):
        yield


async def _search(user):
    return await knowledge_mcp.mcp_search_knowledge_base(KnowledgeSearchRequest(query="q"), user)


async def _summarize(user):
    return await knowledge_mcp.mcp_summarize_knowledge_topic({"topic": "t"}, user)


async def _vector(user):
    return await knowledge_mcp.mcp_vector_similarity_search({"query": "q", "threshold": 0.1}, user)


async def _qa(user):
    return await knowledge_mcp.mcp_langchain_qa_chain({"question": "q", "context_size": 5}, user)


ROUTES = [_search, _summarize, _vector, _qa]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_another_users_private_fact_is_never_returned(route):
    body = text_of(await route(BOB))

    assert PRIVATE_A not in body
    assert PRIVATE_B in body


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_the_owner_still_reads_their_own_private_fact(route):
    body = text_of(await route(ALICE))

    assert PRIVATE_A in body
    assert PRIVATE_B not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_an_unresolvable_caller_is_denied_not_read_as_anonymous(route):
    with pytest.raises(HTTPException) as denied:
        await route({"role": "user"})

    assert denied.value.status_code == 401


@pytest.mark.asyncio
async def test_read_resource_withholds_another_users_private_fact():
    async def read(user):
        return await knowledge_mcp.read_kb_resource({"uri": "kb://doc/f-a"}, user)

    assert PRIVATE_A not in text_of(await read(BOB))
    assert PRIVATE_A in text_of(await read(ALICE))
    with pytest.raises(HTTPException):
        await read({})


ADMIN = {"user_id": "root", "role": "admin"}
USERS = [ALICE, BOB, ADMIN]


async def _read_doc(user):
    return await knowledge_mcp.read_kb_resource({"uri": "kb://doc/f-q"}, user)


async def _read_chunk(user):
    return await knowledge_mcp.read_kb_resource({"uri": "kb://chunk/f-q"}, user)


QUARANTINE_ROUTES = [_search, _summarize, _vector, _qa, _read_doc, _read_chunk]


async def _as(route, user, kb):
    with (
        patch.object(knowledge_mcp, "get_knowledge_base", return_value=kb),
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
    ):
        return text_of(await route(user))


@pytest.mark.asyncio
@pytest.mark.parametrize("user", USERS)
@pytest.mark.parametrize("route", QUARANTINE_ROUTES)
async def test_mcp_tool_never_returns_a_research_quarantined_fact(route, user):
    """AC3 (#16665): the quarantined fact is the only fact held; the ungated twin proves it would be returned."""
    ungated = QuarantineGatedKB(only_quarantined=True)
    ungated.search = AsyncMock(return_value=[quarantined_fact()])

    assert RESEARCH in await _as(route, user, ungated), "control: ungated, the fact is returned"
    assert RESEARCH not in await _as(route, user, QuarantineGatedKB(only_quarantined=True))
