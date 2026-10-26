# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admins read any fact through the explicit read APIs, audited; every other path stays scoped (#16665)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.kb_librarian_agent import KBLibrarianAgent
from api import agent_diary, kb_librarian, knowledge_mcp
from auth_middleware import get_current_user
from knowledge.read_path_fakes_16665 import PRIVATE_A, PRIVATE_B, FakeKB, text_of
from knowledge.schemas.mcp import KnowledgeSearchRequest
from knowledge.search_filters import filter_for_caller, filter_for_user_id

ADMIN = {"user_id": "root", "role": "admin"}
BOB = {"user_id": "bob", "role": "user"}


@pytest.fixture
def audit():
    with patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)) as recorded:
        yield recorded


@pytest.mark.asyncio
async def test_admin_reads_every_fact_and_the_read_is_audited_by_id_never_content(audit):
    kb = FakeKB()
    kept = await filter_for_caller(await kb.search(), kb, ADMIN)

    assert {PRIVATE_A, PRIVATE_B} <= {r["content"] for r in kept}
    audit.assert_awaited_once()
    args, kwargs = audit.await_args
    assert args == ("kb.admin_read",) and kwargs["user_id"] == "root"
    assert kwargs["details"]["fact_ids"] == ["f-a", "f-b", "f-s"]
    assert PRIVATE_A not in repr(kwargs)


@pytest.mark.asyncio
async def test_a_non_admin_is_scoped_and_never_audited_as_admin(audit):
    kb = FakeKB()
    kept = await filter_for_caller(await kb.search(), kb, BOB)

    assert PRIVATE_A not in text_of(kept)
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_admin_read_is_withheld_when_the_audit_trail_cannot_record_it():
    kb = FakeKB()
    with patch("services.audit_logger.audit_log", new=AsyncMock(side_effect=RuntimeError("down"))):
        assert await filter_for_caller(await kb.search(), kb, ADMIN) == []


@pytest.mark.asyncio
async def test_a_bare_user_id_never_carries_the_admin_input(audit):
    """Chat and agent grounding pass an id: an admin's own chat stays scoped to what the normal rules give."""
    kb = FakeKB()
    kept = await filter_for_user_id(await kb.search(), kb, "root")

    assert PRIVATE_A not in text_of(kept)
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_search_gives_an_admin_every_fact_and_a_user_only_their_own(audit):
    with patch.object(knowledge_mcp, "get_knowledge_base", return_value=FakeKB()):
        as_admin = await knowledge_mcp.mcp_search_knowledge_base(KnowledgeSearchRequest(query="q"), ADMIN)
        as_bob = await knowledge_mcp.mcp_search_knowledge_base(KnowledgeSearchRequest(query="q"), BOB)

    assert PRIVATE_A in text_of(as_admin) and PRIVATE_A not in text_of(as_bob)


def _get(router, user, path):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app).get(path) if path.startswith("/") else None


def test_librarian_route_gives_an_admin_every_fact(audit):
    agent = object.__new__(KBLibrarianAgent)
    agent.knowledge_base, agent.enabled = FakeKB(), True
    agent.max_results, agent.similarity_threshold, agent.auto_summarize = 5, 0.0, False

    def post(user):
        app = FastAPI()
        app.include_router(kb_librarian.router)
        app.dependency_overrides[get_current_user] = lambda: user
        with patch.object(kb_librarian, "get_kb_librarian", return_value=agent):
            return TestClient(app).post("/query", json={"query": "x"})

    assert PRIVATE_A in post(ADMIN).text and PRIVATE_A not in post(BOB).text


def test_diary_route_gives_an_admin_another_users_entry(audit):
    entry = {
        "id": "d1",
        "content": PRIVATE_A,
        "metadata": {"category": "AGENT_DIARY", "source": "agent_a", "owner_id": "alice", "visibility": "private"},
    }
    kb = FakeKB()
    kb.get_all_facts = AsyncMock(return_value=[entry])

    def get(user):
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            return _get(agent_diary.router, user, "/agent_a/entries")

    assert PRIVATE_A in get(ADMIN).text and PRIVATE_A not in get(BOB).text


@pytest.mark.asyncio
async def test_the_claim_verifier_cache_does_not_share_a_partition_between_admin_and_user_reads():
    from knowledge.search_filters import KbReader, kb_principal
    from services.claim_verifier import ClaimVerifier
    from services.knowledge_grounding_models import Claim

    verifier = ClaimVerifier(AsyncMock(), AsyncMock())
    claim = Claim(claim_text="same claim")
    principal = kb_principal({"user_id": "root"})

    keys = {
        verifier._build_cache_key(claim, KbReader(principal, True)),
        verifier._build_cache_key(claim, KbReader(principal, False)),
        verifier._build_cache_key(claim, "root"),
    }
    assert len(keys) == 2  # admin partition differs; a scoped reader and a bare id share one on purpose
