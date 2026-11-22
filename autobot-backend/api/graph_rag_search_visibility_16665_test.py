# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /search (graph_rag) feeds RAG synthesis through a real GraphRAGService, scoped to the caller (#16665).

User A reads their private fact, B never does, an admin never does (owner decision 2026-10-26: prompt-feeding
routes give an admin no bypass), and a research-quarantined fact is never returned.
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import graph_rag
from api.user_management.dependencies import get_tenant_context
from knowledge.read_path_fakes_16665 import PRIVATE_A, RESEARCH, SHARED, FakeKB, QuarantineGatedKB
from services.graph_rag_service import GraphRAGService
from services.rag_service import RAGService


def _tenant(user_id: str, admin: bool = False):
    return SimpleNamespace(user_id=user_id, org_id=None, is_platform_admin=admin, is_authenticated=True)


ALICE, BOB, ADMIN = _tenant("alice"), _tenant("bob"), _tenant("root", admin=True)


def _search(tenant, kb):
    app = FastAPI()
    app.include_router(graph_rag.router)
    service = GraphRAGService(
        rag_service=RAGService(kb), memory_graph=MagicMock(initialized=True), enable_entity_extraction=False
    )
    app.dependency_overrides[graph_rag.get_graph_rag_service] = lambda: service
    app.dependency_overrides[get_tenant_context] = lambda: tenant
    with (
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
        # an empty hash cache skips the host's document-provenance check, which is not under test
        patch.dict("knowledge.stale_filter._cache", paths={}, loaded_at=time.monotonic()),
    ):
        return TestClient(app).post("/search", json={"query": "q", "enable_reranking": False})


def test_user_a_reads_their_private_fact_and_user_b_never_does():
    for_alice, for_bob = _search(ALICE, FakeKB()), _search(BOB, FakeKB())

    assert for_alice.status_code == 200 and PRIVATE_A in for_alice.text
    assert for_bob.status_code == 200 and PRIVATE_A not in for_bob.text and SHARED in for_bob.text


def test_an_admin_gets_no_bypass_of_another_users_private_fact():
    response = _search(ADMIN, FakeKB())

    assert response.status_code == 200 and PRIVATE_A not in response.text and SHARED in response.text


@pytest.mark.parametrize("tenant", [ALICE, BOB, ADMIN])
def test_a_research_quarantined_fact_is_never_returned(tenant):
    response = _search(tenant, QuarantineGatedKB())

    assert response.status_code == 200 and RESEARCH not in response.text and SHARED in response.text
