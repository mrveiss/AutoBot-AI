# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /events and /events/{entity}/timeline serve only events of documents the caller may read (#16665).

A temporal event carries no owner: it derives from its ``source_document_id``, so it is readable exactly
when that source fact is. User A reads events of their private document, user B never does, an admin does
(audited), a platform-wide document's events are visible to everyone, an event whose source cannot be
found is withheld, and an event of a research-quarantined document is never returned.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import knowledge_graph_routes
from auth_middleware import get_current_user
from autobot_shared.ssot_config import config
from knowledge.read_path_fakes_16665 import FakeKB

DOC_A, DOC_S, DOC_Q = (f"{n}{n}{n}{n}{n}{n}{n}{n}-0000-4000-8000-000000000000" for n in "123")
ORPHAN = "99999999-0000-4000-8000-000000000000"
ALICE, BOB = {"user_id": "alice", "role": "user"}, {"user_id": "bob", "role": "user"}
ADMIN = {"user_id": "root", "role": "admin"}
PATHS = ["/events", "/events/Acme/timeline"]


def _event(doc, name):
    return {"id": f"e-{name}", "name": name, "timestamp": "2026-01-01T00:00:00+00:00", "source_document_id": doc}


EVENTS = [
    _event(DOC_A, "alice-private-event"),
    _event(DOC_S, "platform-event"),
    _event(DOC_Q, "quarantined-event"),
    _event(ORPHAN, "orphan-event"),
]


class _EventKB(FakeKB):
    def get_fact(self, fact_id):
        meta = {
            DOC_A: {"owner_id": "alice", "visibility": "private"},
            DOC_S: {"owner_id": "admin", "visibility": "system"},
            DOC_Q: {"owner_id": "admin", "visibility": "system", "collection": config.research_quarantine_collection},
        }
        return {"fact_id": fact_id, "content": "x", "metadata": meta[fact_id]} if fact_id in meta else None


class _Service:
    def __init__(self, _redis):
        pass

    async def search_events_in_range(self, **_):
        return list(EVENTS)

    async def get_event_timeline(self, **_):
        return list(EVENTS)


def _get(user, path, audit=None, service=_Service):
    app = FastAPI()
    app.include_router(knowledge_graph_routes.router)
    app.dependency_overrides[get_current_user] = lambda: user
    with (
        patch("autobot_shared.redis_client.get_async_redis_client", AsyncMock(return_value=object())),
        patch("knowledge.temporal_search.TemporalSearchService", service),
        patch("knowledge.get_knowledge_base", AsyncMock(return_value=_EventKB())),
        patch("services.audit_logger.audit_log", new=audit or AsyncMock(return_value=True)),
    ):
        return TestClient(app).get(path)


@pytest.mark.parametrize("path", PATHS)
def test_user_a_reads_their_private_events_and_user_b_never_does(path):
    for_alice, for_bob = _get(ALICE, path), _get(BOB, path)

    assert "alice-private-event" in for_alice.text and "platform-event" in for_alice.text
    assert "alice-private-event" not in for_bob.text and "platform-event" in for_bob.text


@pytest.mark.parametrize("path", PATHS)
def test_an_admin_reads_another_users_private_events_and_the_read_is_audited(path):
    audit = AsyncMock(return_value=True)
    response = _get(ADMIN, path, audit)

    assert "alice-private-event" in response.text
    assert audit.await_args.args[0] == "kb.admin_read" and audit.await_args.kwargs["user_id"] == "root"


@pytest.mark.parametrize("path", PATHS)
def test_an_admin_read_whose_audit_cannot_be_written_is_refused_with_503_and_returns_no_events(path):
    response = _get(ADMIN, path, AsyncMock(side_effect=RuntimeError("audit down")))

    assert response.status_code == 503 and "alice-private-event" not in response.text  # not an empty 200 (#19860)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("user", [ALICE, BOB, ADMIN])
def test_an_event_of_a_quarantined_document_or_an_unresolvable_source_is_never_returned(user, path):
    body = _get(user, path).text

    assert "quarantined-event" not in body and "orphan-event" not in body and "platform-event" in body


@pytest.mark.parametrize("path", PATHS)
def test_an_unresolvable_caller_is_denied(path):
    assert _get({"role": "user"}, path).status_code == 401


@pytest.mark.parametrize("path", PATHS + ["/summaries/search?query=q"])
def test_a_503_from_the_visibility_pass_is_not_turned_into_a_500(path):
    from fastapi import HTTPException

    boom = AsyncMock(side_effect=HTTPException(status_code=503, detail="audit unavailable"))
    with (
        patch.object(knowledge_graph_routes, "visible_events", boom),
        patch.object(knowledge_graph_routes, "visible_summaries", boom),
        patch("knowledge.summary_search.SummarySearchService", _SummaryService),
        patch("knowledge.backends.get_async_default_client", AsyncMock(return_value=object())),
    ):
        assert _get(ALICE, path).status_code == 503


class _SummaryService:
    def __init__(self, _client):
        pass

    async def search_summaries(self, **_):
        return [{"id": "s", "metadata": {"document_id": DOC_S}}]


class _CrowdedService(_Service):
    """The oldest events belong to another user; the caller's one visible event sits beyond ``limit``."""

    async def search_events_in_range(self, limit, **_):
        crowd = [_event(DOC_A, f"alice-{i}") for i in range(5)] + [_event(DOC_S, "late-platform-event")]
        return crowd[:limit]

    async def get_event_timeline(self, entity_name, limit):
        return await self.search_events_in_range(limit)


@pytest.mark.parametrize("path", ["/events?limit=2", "/events/Acme/timeline?limit=2"])
def test_a_visible_event_beyond_the_page_is_found_and_the_page_is_cut_to_limit(path):
    body = _get(BOB, path, service=_CrowdedService).json()

    assert [e["name"] for e in body["events"]] == ["late-platform-event"] and body["total"] == 1


def test_the_page_never_exceeds_limit():
    body = _get(ALICE, "/events?limit=2", service=_CrowdedService).json()

    assert body["total"] == 2
