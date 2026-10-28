# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The summary routes never serve a summary of a research-quarantined fact (#16665 AC3, #19163).

The real SummarySearchService runs against the in-memory collection, which honours the same
``where`` semantics as the store, so the quarantine clause the service builds is what is tested.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import knowledge_graph_routes
from auth_middleware import get_current_user
from autobot_shared.ssot_config import config
from knowledge.backends.memory_adapter import InMemoryCollection
from knowledge.read_path_fakes_16665 import FakeKB

DOC_OK, DOC_Q = "44444444-4444-4444-8444-444444444444", "55555555-5555-4555-8555-555555555555"
USERS = [{"user_id": "alice", "role": "user"}, {"user_id": "bob", "role": "user"}, {"user_id": "root", "role": "admin"}]


class _AsyncCollection:
    """The async face of the in-memory collection: text queries become a fixed embedding query."""

    def __init__(self, inner: InMemoryCollection):
        self.inner = inner

    async def query(self, query_texts, n_results, where):
        return self.inner.query(query_embeddings=[[1.0]], n_results=n_results, where=where)

    async def get(self, **kwargs):
        return self.inner.get(**kwargs)


class _Client:
    def __init__(self):
        self.inner = InMemoryCollection("knowledge_summaries")
        self.inner.add(
            ids=[DOC_OK, DOC_Q],
            documents=["ordinary summary", "quarantined summary"],
            metadatas=[
                {"document_id": DOC_OK, "level": "document"},
                {"document_id": DOC_Q, "level": "document", "collection": config.research_quarantine_collection},
            ],
        )

    async def get_collection(self, name):
        return _AsyncCollection(self.inner)


class _SystemKB(FakeKB):
    def get_fact(self, fact_id):
        return {"fact_id": fact_id, "content": "x", "metadata": {"owner_id": "admin", "visibility": "system"}}


def _get(user, path):
    app = FastAPI()
    app.include_router(knowledge_graph_routes.router)
    app.dependency_overrides[get_current_user] = lambda: user
    with (
        patch("knowledge.backends.get_async_default_client", AsyncMock(return_value=_Client())),
        patch("knowledge.get_knowledge_base", AsyncMock(return_value=_SystemKB())),
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
    ):
        return TestClient(app).get(path)


@pytest.mark.parametrize("user", USERS)
def test_search_never_returns_a_summary_of_a_quarantined_fact(user):
    response = _get(user, "/summaries/search?query=q")

    assert response.status_code == 200
    assert "ordinary summary" in response.text and "quarantined summary" not in response.text


@pytest.mark.parametrize("user", USERS)
def test_overview_never_returns_a_summary_of_a_quarantined_fact(user):
    ok, held = _get(user, f"/documents/{DOC_OK}/overview"), _get(user, f"/documents/{DOC_Q}/overview")

    assert "ordinary summary" in ok.text
    assert "quarantined summary" not in held.text


@pytest.mark.parametrize("user", USERS)
def test_drill_down_never_returns_a_summary_of_a_quarantined_fact(user):
    ok, held = _get(user, f"/summaries/{DOC_OK}/drill-down"), _get(user, f"/summaries/{DOC_Q}/drill-down")

    assert "ordinary summary" in ok.text
    assert "quarantined summary" not in held.text
