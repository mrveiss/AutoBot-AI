# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""knowledge_rag /advanced_search and /context through a real RAGService over the shared fake KB (#16665).

These feed RAG synthesis, so per the 2026-10-26 owner decision an admin gets no bypass: user A reads their
private fact, B never does, an admin never does, and a research-quarantined fact is never returned.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import knowledge_rag
from auth_middleware import get_current_user
from knowledge.search import SearchMixin
from services.rag_service import RAGService
from testkit.read_path_fakes_16665 import (
    PRIVATE_A,
    RESEARCH,
    SHARED,
    FakeKB,
    QuarantineGatedKB,
    all_facts,
    quarantined_fact,
)

ALICE = {"user_id": "alice", "role": "user"}
BOB = {"user_id": "bob", "role": "user"}
ADMIN = {"user_id": "root", "role": "admin"}

ROUTES = [
    ("/advanced_search", {"query": "q", "enable_reranking": False, "max_results": 10}),
    ("/context", {"query": "q", "mode": "rag"}),
]


def _post(user, path, body, kb):
    app = FastAPI()
    app.include_router(knowledge_rag.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.state.graph_rag_service = None
    service = RAGService(kb)
    app.dependency_overrides[knowledge_rag.get_rag_service_dependency] = lambda: service
    with (
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
        # an empty hash cache skips the host's document-provenance check, which is not under test
        patch.dict("knowledge.stale_filter._cache", paths={}, loaded_at=time.monotonic()),
    ):
        return TestClient(app).post(path, json=body)


@pytest.mark.parametrize("path,body", ROUTES)
def test_user_a_reads_their_private_fact_and_user_b_never_does(path, body):
    for_alice, for_bob = _post(ALICE, path, body, FakeKB()), _post(BOB, path, body, FakeKB())

    assert for_alice.status_code == 200 and PRIVATE_A in for_alice.text
    assert for_bob.status_code == 200 and PRIVATE_A not in for_bob.text and SHARED in for_bob.text


@pytest.mark.parametrize("path,body", ROUTES)
def test_an_admin_gets_no_bypass_of_another_users_private_fact(path, body):
    response = _post(ADMIN, path, body, FakeKB())

    assert response.status_code == 200 and PRIVATE_A not in response.text and SHARED in response.text


@pytest.mark.parametrize("user", [ALICE, BOB, ADMIN])
@pytest.mark.parametrize("path,body", ROUTES)
def test_a_research_quarantined_fact_is_never_returned(user, path, body):
    response = _post(user, path, body, QuarantineGatedKB())

    assert response.status_code == 200 and RESEARCH not in response.text and SHARED in response.text


class _RealGateKB(SearchMixin, FakeKB):
    """The real ``SearchMixin.search`` (and its ``gate_response``) over a store that returns the quarantined fact.

    Unlike ``QuarantineGatedKB`` it does not apply the gate itself, so this proves the RAG legs reach
    the gate through ``KnowledgeBaseAdapter.search`` -> ``KnowledgeBase.search`` (#16665 AC3).
    """

    def __init__(self, leak: bool = False):
        FakeKB.__init__(self)
        self.leak = leak

    async def _dispatch_search(self, *args, **kwargs):
        return all_facts() + [quarantined_fact()]

    async def search(self, *args, **kwargs):
        if self.leak:  # the sensitivity control: a search that skips the gate
            return await self._dispatch_search()
        return await SearchMixin.search(self, *args, **kwargs)


@pytest.mark.parametrize("user", [ALICE, ADMIN])
@pytest.mark.parametrize("path,body", ROUTES)
def test_the_adapter_path_reaches_the_real_search_gate(user, path, body):
    response = _post(user, path, body, _RealGateKB())

    assert response.status_code == 200 and RESEARCH not in response.text and SHARED in response.text


def test_the_real_gate_test_is_sensitive_to_a_leak():
    response = _post(ALICE, "/advanced_search", ROUTES[0][1], _RealGateKB(leak=True))

    assert response.status_code == 200 and RESEARCH in response.text
