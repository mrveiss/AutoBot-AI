# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /knowledge/search returns local KB hits only for facts the caller may read (#16665).

An explicit, admin-gated read API (not prompt grounding): user A reads their private fact, user B
never does, an admin does, and a research-quarantined fact is never returned.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import ai_stack_integration
from auth_middleware import check_admin_permission, get_current_user
from dependencies import provide_knowledge_base
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge.read_path_fakes_16665 import PRIVATE_A, RESEARCH, SHARED, FakeKB, QuarantineGatedKB, all_facts

ALICE = {"user_id": "alice", "role": "user"}
BOB = {"user_id": "bob", "role": "user"}
ADMIN = {"user_id": "root", "role": "admin"}


def _search_http(user, kb):
    """Through the real router, so the route's response model is exercised too."""
    app = FastAPI()
    app.include_router(ai_stack_integration.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[check_admin_permission] = lambda: True
    app.dependency_overrides[provide_knowledge_base] = lambda: kb
    client = AsyncMock()
    client.search_knowledge.return_value = {}
    with (
        patch.object(ai_stack_integration, "get_ai_stack_client", AsyncMock(return_value=client)),
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
    ):
        return TestClient(app).post("/knowledge/search", params={"query": "q"})


async def _search(user, kb) -> str:
    return _search_http(user, kb).text


def test_the_response_matches_its_declared_model():
    response = _search_http(ALICE, FakeKB())

    assert response.status_code == 200
    assert set(response.json()["data"]) == {"local_kb", "rag_augmented"}


def test_a_caller_without_a_user_id_gets_401_not_an_empty_result():
    """The unresolved-caller 401 from filter_for_caller is re-raised, never swallowed into []."""
    response = _search_http({"role": "user"}, FakeKB())

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_a_reads_their_private_fact_and_user_b_never_does():
    for_alice, for_bob = await _search(ALICE, FakeKB()), await _search(BOB, FakeKB())

    assert PRIVATE_A in for_alice
    assert PRIVATE_A not in for_bob and SHARED in for_bob


@pytest.mark.asyncio
async def test_an_admin_reads_another_users_private_fact():
    assert PRIVATE_A in await _search(ADMIN, FakeKB())


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [ALICE, BOB, ADMIN])
async def test_a_research_quarantined_fact_is_never_returned(user):
    body = await _search(user, QuarantineGatedKB())

    assert RESEARCH not in body and SHARED in body


def test_the_route_is_admin_gated():
    """The suite stubs ``auth_middleware`` (the same walk as knowledge_crud_admin_gate_16665_test.py), so a 403
    cannot be provoked over HTTP; the claim is that the route's resolved dependency tree reaches the gate."""
    route = next(r for r in ai_stack_integration.router.routes if getattr(r, "path", "") == "/knowledge/search")

    assert check_admin_permission in [dep.call for dep in route.dependant.dependencies]


@pytest.mark.asyncio
async def test_the_quarantine_filter_reaches_the_kb_search():
    kb = FakeKB()
    kb.search = AsyncMock(return_value=[])
    await _search(ALICE, kb)

    assert kb.search.await_args.kwargs["filters"] == RESEARCH_QUARANTINE_FILTER


@pytest.mark.asyncio
async def test_an_enhanced_mode_dict_answer_is_unwrapped_not_dropped():
    kb = FakeKB()
    kb.search = AsyncMock(return_value={"results": all_facts()})

    assert PRIVATE_A in await _search(ALICE, kb)


def _remote_search(user, audit):
    app = FastAPI()
    app.include_router(ai_stack_integration.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[check_admin_permission] = lambda: True
    app.dependency_overrides[provide_knowledge_base] = lambda: FakeKB()
    client = AsyncMock()
    client.search_knowledge.return_value = {"hits": ["remote-hit"]}
    with (
        patch.object(ai_stack_integration, "get_ai_stack_client", AsyncMock(return_value=client)),
        patch("services.audit_logger.audit_log", new=audit),
    ):
        return TestClient(app).post("/knowledge/search", params={"query": "q"}), client


def test_the_remote_half_is_audited_as_an_admin_read_before_it_is_returned():
    audit = AsyncMock(return_value=True)
    response, _ = _remote_search(ADMIN, audit)

    assert "remote-hit" in response.text
    sources = [c.kwargs["details"].get("source") for c in audit.await_args_list]
    assert "ai_stack_remote" in sources and audit.await_args.args[0] == "kb.admin_read"


def test_the_remote_half_is_withheld_when_its_audit_cannot_be_written():
    response, client = _remote_search(ADMIN, AsyncMock(side_effect=RuntimeError("down")))

    assert response.status_code == 503 and "remote-hit" not in response.text
    client.search_knowledge.assert_not_awaited()


def test_a_caller_who_is_not_an_admin_never_reaches_the_remote_half():
    response, client = _remote_search(ALICE, AsyncMock(return_value=True))

    assert response.status_code == 200 and "remote-hit" not in response.text
    client.search_knowledge.assert_not_awaited()


def test_knowledge_system_is_audited_as_an_admin_read_and_withheld_when_the_audit_fails():
    def call(audit):
        app = FastAPI()
        app.include_router(ai_stack_integration.router)
        app.dependency_overrides[get_current_user] = lambda: ADMIN
        app.dependency_overrides[check_admin_permission] = lambda: True
        client = AsyncMock()
        client.get_system_knowledge.return_value = {"x": "remote-system"}
        with (
            patch.object(ai_stack_integration, "get_ai_stack_client", AsyncMock(return_value=client)),
            patch("services.audit_logger.audit_log", new=audit),
        ):
            return TestClient(app).get("/knowledge/system"), client

    audit = AsyncMock(return_value=True)
    ok, _ = call(audit)
    refused, client = call(AsyncMock(side_effect=RuntimeError("down")))

    assert ok.status_code == 200 and audit.await_args.args[0] == "kb.admin_read"
    assert refused.status_code == 503
    client.get_system_knowledge.assert_not_awaited()
