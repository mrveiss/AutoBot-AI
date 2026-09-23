# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The orphan-storage admin routes: admin-only, every detector, no host paths, and PROPOSE-only deletion (#17038, #17039, #17315)."""

import uuid
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.admin_orphan_storage as route
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from models.approval import Approval
from services import orphan_storage
from services.approval_gate_service import ApprovalGateService

_ADMIN = {"username": "admin", "role": "admin", "user_id": "admin-1"}


class _FakeSession:
    """Enough of an AsyncSession for create_approval: add/flush/commit/refresh.

    ``flush`` is where a real session assigns the primary key, so the fake
    assigns one too -- the route puts ``approval.id`` in its response.
    """

    def __init__(self):
        self.added = []

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None


def _client(session=None) -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: _ADMIN
    app.dependency_overrides[get_db_session] = lambda: session or _FakeSession()
    return TestClient(app)


def test_a_non_admin_is_refused(monkeypatch):
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"username": "u2", "role": "user", "user_id": "u2"}

    with patch("auth_rbac.get_auth_middleware", return_value=auth):
        response = _client().get("/api/admin/orphan-storage")

    assert response.status_code in (401, 403)


def test_lists_candidates_from_every_registered_detector_with_totals(monkeypatch):
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})

    async def _list_a():
        return [
            orphan_storage.OrphanCandidate(
                provider="a",
                id="1",
                location="a/1",
                size_bytes=100,
                modified_at="2026-01-01T00:00:00+00:00",
                reason="test-a",
            )
        ]

    async def _list_b():
        return [
            orphan_storage.OrphanCandidate(
                provider="b",
                id="1",
                location="b/1",
                size_bytes=50,
                modified_at="2026-01-01T00:00:00+00:00",
                reason="test-b",
            )
        ]

    orphan_storage.register_detector(orphan_storage.OrphanDetector(provider="a", list_candidates=_list_a, delete=None))
    orphan_storage.register_detector(orphan_storage.OrphanDetector(provider="b", list_candidates=_list_b, delete=None))

    auth = MagicMock()
    auth.get_user_from_request.return_value = _ADMIN

    with patch("auth_rbac.get_auth_middleware", return_value=auth):
        response = _client().get("/api/admin/orphan-storage")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert body["total_size_bytes"] == 150
    assert {c["provider"] for c in body["candidates"]} == {"a", "b"}
    assert {s["provider"]: s["available"] for s in body["provider_statuses"]} == {"a": True, "b": True}


def test_an_unavailable_detector_names_itself_rather_than_reading_as_success(monkeypatch):
    """66's review: an outage response must not look like an empty success."""
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})

    async def _broken():
        raise RuntimeError("connection refused: redis.internal:6379")

    orphan_storage.register_detector(
        orphan_storage.OrphanDetector(provider="broken", list_candidates=_broken, delete=None)
    )

    auth = MagicMock()
    auth.get_user_from_request.return_value = _ADMIN

    with patch("auth_rbac.get_auth_middleware", return_value=auth):
        response = _client().get("/api/admin/orphan-storage")

    assert response.status_code == 200
    body = response.json()
    assert body["candidates"] == []
    assert body["provider_statuses"] == [{"provider": "broken", "available": False, "error": "RuntimeError"}]
    assert "redis.internal" not in response.text, "#17065: never the raw exception text"


# -- POST /admin/orphan-storage/deletion-requests (#17315) --------------------


def _a_detector(provider: str, deleted: list) -> None:
    """Register a detector whose delete records the call instead of deleting."""

    async def _list():
        return []

    async def _delete(candidate_id: str):
        deleted.append((provider, candidate_id))
        return orphan_storage.DeleteResult(deleted=True)

    orphan_storage.register_detector(
        orphan_storage.OrphanDetector(provider=provider, list_candidates=_list, delete=_delete)
    )


def test_a_non_admin_cannot_propose_a_deletion(monkeypatch):
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})
    _a_detector("code_source_clone", [])
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"username": "u2", "role": "user", "user_id": "u2"}

    with patch("auth_rbac.get_auth_middleware", return_value=auth):
        response = _client().post(
            "/api/admin/orphan-storage/deletion-requests",
            json={"provider": "code_source_clone", "candidate_id": "abc"},
        )

    assert response.status_code in (401, 403)


def test_an_unknown_provider_is_refused_before_a_human_is_ever_asked(monkeypatch):
    """A proposal that could not execute must not reach the review queue."""
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})
    auth = MagicMock()
    auth.get_user_from_request.return_value = _ADMIN

    with patch("auth_rbac.get_auth_middleware", return_value=auth):
        response = _client().post(
            "/api/admin/orphan-storage/deletion-requests",
            json={"provider": "not_a_provider", "candidate_id": "abc"},
        )

    assert response.status_code == 404


def test_a_proposal_creates_a_pending_approval_and_deletes_nothing(monkeypatch):
    """#17315 AC1: the production path that was missing.

    The context shape is the one ``orphan_storage_cleanup_action`` documents
    and dispatches on -- asserted key by key, because a proposal whose context
    drifts from it is exactly as unreachable as having no proposer at all.
    """
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})
    deleted: list = []
    _a_detector("code_source_clone", deleted)
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())

    session = _FakeSession()
    auth = MagicMock()
    auth.get_user_from_request.return_value = _ADMIN

    with patch("auth_rbac.get_auth_middleware", return_value=auth):
        response = _client(session).post(
            "/api/admin/orphan-storage/deletion-requests",
            json={"provider": "code_source_clone", "candidate_id": "abc"},
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["action"] == "orphan_storage_delete"
    assert (body["provider"], body["candidate_id"]) == ("code_source_clone", "abc")

    approval = next(o for o in session.added if isinstance(o, Approval))
    assert approval.context == {
        "action": "orphan_storage_delete",
        "provider": "code_source_clone",
        "candidate_id": "abc",
    }
    assert approval.approval_type == "destructive_action"
    assert approval.status == "pending"
    assert deleted == [], "proposing must not delete -- only an approved gate may (#17038)"


async def _noop():
    return None
