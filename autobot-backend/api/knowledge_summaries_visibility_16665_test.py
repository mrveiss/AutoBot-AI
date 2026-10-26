# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The summary routes serve only summaries of facts the caller may read (#16665)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import knowledge_graph_routes
from auth_middleware import get_current_user
from knowledge.read_path_fakes_16665 import FakeKB

DOC_A, DOC_S = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
ORPHAN = "33333333-3333-4333-8333-333333333333"
ALICE, BOB = {"user_id": "alice", "role": "user"}, {"user_id": "bob", "role": "user"}


def _summary(doc, text):
    return {"id": f"s-{doc}", "content": text, "metadata": {"document_id": doc, "level": "document"}, "score": 0.9}


class _SummaryKB(FakeKB):
    """Source facts: DOC_A is alice's private fact, DOC_S is platform-wide."""

    def get_fact(self, fact_id):
        meta = {
            DOC_A: {"owner_id": "alice", "visibility": "private"},
            DOC_S: {"owner_id": "admin", "visibility": "system"},
        }
        return {"fact_id": fact_id, "content": "x", "metadata": meta[fact_id]} if fact_id in meta else None


class _Service:
    def __init__(self, _client):
        pass

    async def search_summaries(self, **_):
        return [_summary(DOC_A, "alice summary"), _summary(DOC_S, "platform summary"), _summary(ORPHAN, "orphan")]

    async def get_document_overview(self, document_id):
        return {
            "document_id": str(document_id),
            "document_summary": _summary(str(document_id), "overview text"),
            "section_summaries": [],
        }

    async def drill_down(self, summary_id):
        doc = DOC_A if str(summary_id) == DOC_A else DOC_S
        return {"summary": _summary(doc, "drill text"), "children": [], "level": "document"}


def _call(user, method, path):
    app = FastAPI()
    app.include_router(knowledge_graph_routes.router)
    app.dependency_overrides[get_current_user] = lambda: user
    with (
        patch("knowledge.summary_search.SummarySearchService", _Service),
        patch("knowledge.backends.get_async_default_client", AsyncMock(return_value=object())),
        patch("knowledge.get_knowledge_base", AsyncMock(return_value=_SummaryKB())),
    ):
        return getattr(TestClient(app), method)(path)


def test_search_never_returns_a_summary_of_another_users_private_fact():
    for_bob, for_alice = _call(BOB, "get", "/summaries/search?query=q"), _call(
        ALICE, "get", "/summaries/search?query=q"
    )

    assert "alice summary" not in for_bob.text and "platform summary" in for_bob.text
    assert "orphan" not in for_bob.text and "orphan" not in for_alice.text  # unresolvable source: withheld
    assert "alice summary" in for_alice.text


def test_overview_is_empty_for_a_document_the_caller_may_not_read():
    for_bob, for_alice = _call(BOB, "get", f"/documents/{DOC_A}/overview"), _call(
        ALICE, "get", f"/documents/{DOC_A}/overview"
    )

    assert "overview text" not in for_bob.text and for_bob.json()["document_summary"] is None
    assert "overview text" in for_alice.text


def test_drill_down_is_withheld_for_a_summary_the_caller_may_not_read():
    for_bob, for_alice = _call(BOB, "get", f"/summaries/{DOC_A}/drill-down"), _call(
        ALICE, "get", f"/summaries/{DOC_A}/drill-down"
    )

    assert "drill text" not in for_bob.text and for_bob.json()["summary"] is None
    assert "drill text" in for_alice.text


@pytest.mark.parametrize(
    "path", ["/summaries/search?query=q", f"/documents/{DOC_A}/overview", f"/summaries/{DOC_A}/drill-down"]
)
def test_an_unresolvable_caller_is_denied(path):
    assert _call({"role": "user"}, "get", path).status_code == 401
