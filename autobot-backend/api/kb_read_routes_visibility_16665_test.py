# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Suggestion, librarian and diary routes return only what the caller may read (#16665).

Each route is called through its real router, as user A (the owner), user B and a caller the
auth layer cannot resolve to a user id.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.kb_librarian_agent import KBLibrarianAgent
from api import agent_diary, kb_librarian, knowledge_suggestions
from auth_middleware import get_current_user
from knowledge.ownership import KnowledgeOwnership
from knowledge.read_path_fakes_16665 import PRIVATE_A, RESEARCH, FakeKB, QuarantineGatedKB, all_facts, quarantined_fact
from knowledge.suggestions import SuggestionsMixin

ALICE, BOB, NOBODY = {"user_id": "alice"}, {"user_id": "bob"}, {"role": "user"}
ADMIN = {"user_id": "root", "role": "admin"}


class _SuggestKB(SuggestionsMixin):
    ownership_manager = KnowledgeOwnership(None)

    def ensure_initialized(self):
        return None

    async def search(self, *args, **kwargs):
        return all_facts()


class _QuarantinedSuggestKB(_SuggestKB):
    """Reads through the real quarantine gate, with a quarantined research fact among the facts."""

    async def search(self, *args, **kwargs):
        return await QuarantineGatedKB().search(*args, **kwargs)


def _client(router, user, prefix="") -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _suggest(route, user, body, kb_class=_SuggestKB):
    with (
        patch.object(knowledge_suggestions, "get_knowledge_base", AsyncMock(return_value=kb_class())),
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
    ):
        return _client(knowledge_suggestions.router, user).post(route, json=body)


SUGGEST_ROUTES = [
    ("/suggestions/context", {"context": "anything at all"}),
    ("/suggestions/tags", {"content": "anything at all"}),
    ("/suggestions/categories", {"content": "anything at all"}),
    ("/suggestions/all", {"content": "anything at all"}),
]


@pytest.mark.parametrize("route,body", SUGGEST_ROUTES)
def test_suggestions_never_derive_from_another_users_private_fact(route, body):
    for_bob, for_alice = _suggest(route, BOB, body), _suggest(route, ALICE, body)

    assert for_bob.status_code == 200 and for_alice.status_code == 200
    assert PRIVATE_A not in for_bob.text
    assert for_alice.json().get("total_candidates", for_alice.json().get("similar_docs_analyzed")) == 2


def test_context_suggestions_return_the_owner_their_own_private_snippet():
    body = {"context": "anything at all", "min_score": 0.0}

    assert PRIVATE_A in _suggest("/suggestions/context", ALICE, body).text
    assert PRIVATE_A not in _suggest("/suggestions/context", BOB, body).text


def test_context_suggestions_give_an_admin_another_users_private_snippet():
    response = _suggest("/suggestions/context", ADMIN, {"context": "anything at all", "min_score": 0.0})

    assert response.status_code == 200 and PRIVATE_A in response.text


@pytest.mark.parametrize("user", [ALICE, BOB, ADMIN])
@pytest.mark.parametrize("route,body", SUGGEST_ROUTES)
def test_suggestions_never_derive_from_a_quarantined_research_fact(route, body, user):
    body = {**body, "min_score": 0.0}
    response = _suggest(route, user, body, _QuarantinedSuggestKB)

    assert response.status_code == 200 and RESEARCH not in response.text
    if route != "/suggestions/context":  # context returns snippets, not a candidate count
        counted = response.json().get("total_candidates", response.json().get("similar_docs_analyzed"))
        assert counted == (3 if user is ADMIN else 2)  # one more would be the quarantined fact


def test_the_suggestion_quarantine_test_is_sensitive_to_a_leak():
    class _Leaky(_SuggestKB):
        async def search(self, *args, **kwargs):
            return [quarantined_fact()]

    assert (
        RESEARCH
        in _suggest("/suggestions/context", ALICE, {"context": "anything at all", "min_score": 0.0}, _Leaky).text
    )


@pytest.mark.parametrize("route,body", SUGGEST_ROUTES)
def test_suggestions_deny_a_caller_with_no_user_id(route, body):
    assert _suggest(route, NOBODY, body).status_code == 401


def _librarian(user):
    agent = object.__new__(KBLibrarianAgent)
    agent.knowledge_base, agent.enabled = FakeKB(), True
    agent.max_results, agent.similarity_threshold, agent.auto_summarize = 5, 0.0, False
    with patch.object(kb_librarian, "get_kb_librarian", return_value=agent):
        return _client(kb_librarian.router, user).post("/query", json={"query": "anything"})


def test_librarian_route_never_returns_another_users_private_fact():
    for_bob, for_alice = _librarian(BOB), _librarian(ALICE)

    assert for_bob.status_code == 200 and PRIVATE_A not in for_bob.text
    assert PRIVATE_A in for_alice.text
    assert _librarian(NOBODY).status_code == 401


@pytest.mark.parametrize("route", ["/agent_a/entries", "/agent_a/search?q=x", "/summary"])
def test_diary_routes_never_return_another_users_private_entry(route):
    entry = {
        "id": "d1",
        "content": PRIVATE_A,
        "score": 0.9,
        "metadata": {"category": "AGENT_DIARY", "source": "agent_a", "owner_id": "alice", "visibility": "private"},
    }
    kb = FakeKB()
    kb.search, kb.get_all_facts = AsyncMock(return_value=[entry]), AsyncMock(return_value=[entry])

    def get(user):
        with patch("memory.agent_diary._get_kb", AsyncMock(return_value=kb)):
            return _client(agent_diary.router, user).get(route)

    assert PRIVATE_A not in get(BOB).text
    if route != "/summary":
        assert PRIVATE_A in get(ALICE).text
    assert get(NOBODY).status_code == 401
