# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /approval-gates and GET /approval-gates/{id} apply the inbox's viewer-or-admin rule (#18413)."""

import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

import api.approval_gates as route
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from services.approval_gate_service import ApprovalGateService

_ALICE = {"username": "alice", "role": "user", "user_id": "alice"}
_BOB = {"username": "bob", "role": "user", "user_id": "bob"}
_ADMIN = {"username": "root", "role": "admin", "user_id": "root"}


def _row(owner, source="agent_tool"):
    return SimpleNamespace(
        id=uuid.uuid4(), title="t", description=None, approval_type="workflow_gate", status="pending",
        requested_by_agent=None, decided_by_user=None, workflow_id=None, workflow_step=None,
        context={"secret": "x"}, decided_at=None, created_at=None, updated_at=None, source=source,
        risk_tier="high", expires_at=None, payload_hash=None, resume_ref=None, owner_user=owner,
        comments=[], task_links=[],
    )  # fmt: skip


def _client(monkeypatch, row, user):
    async def get(self, approval_id):
        return row

    monkeypatch.setattr(ApprovalGateService, "get", get)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: object()
    return TestClient(app)


def test_the_owner_reads_their_own_approval(monkeypatch):
    row = _row("alice")
    assert _client(monkeypatch, row, _ALICE).get(f"/approval-gates/{row.id}").status_code == 200


def test_another_users_approval_is_a_404_and_leaks_no_context(monkeypatch):
    row = _row("alice")
    resp = _client(monkeypatch, row, _BOB).get(f"/approval-gates/{row.id}")
    assert resp.status_code == 404
    assert "secret" not in resp.text and "alice" not in resp.text


def test_the_404_is_the_same_response_as_a_missing_approval(monkeypatch):
    row = _row("alice")
    other = _client(monkeypatch, row, _BOB).get(f"/approval-gates/{row.id}")
    missing = _client(monkeypatch, None, _BOB).get(f"/approval-gates/{row.id}")
    assert (other.status_code, other.json()) == (missing.status_code, missing.json())


def test_an_admin_reads_anyones(monkeypatch):
    row = _row("alice")
    assert _client(monkeypatch, row, _ADMIN).get(f"/approval-gates/{row.id}").status_code == 200


def test_a_sourced_row_with_no_owner_is_admin_only(monkeypatch):
    row = _row(None)
    assert _client(monkeypatch, row, _BOB).get(f"/approval-gates/{row.id}").status_code == 404
    assert _client(monkeypatch, row, _ADMIN).get(f"/approval-gates/{row.id}").status_code == 200


def test_a_legacy_unsourced_unowned_row_stays_readable_by_anyone(monkeypatch):
    row = _row(None, source=None)
    assert _client(monkeypatch, row, _BOB).get(f"/approval-gates/{row.id}").status_code == 200


def test_the_list_route_passes_the_ownership_clauses(monkeypatch):
    seen = {}

    async def list_approvals(self, *args, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(ApprovalGateService, "list_approvals", list_approvals)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_db_session] = lambda: object()
    for user, clauses in ((_BOB, 1), (_ADMIN, 0)):
        app.dependency_overrides[get_current_user] = lambda user=user: user
        assert TestClient(app).get("/approval-gates?status_filter=pending&source=agent_tool").status_code == 200
        assert len(seen["extra_where"]) == clauses


def test_the_clause_matches_the_viewers_rows_and_legacy_rows_only():
    (clause,) = ApprovalGateService.visibility("bob", False)
    sql = str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "owner_user = 'bob'" in sql and "source IS NULL" in sql and "owner_user IS NULL" in sql
    assert ApprovalGateService.visibility("root", True) == ()
    no_viewer = str(ApprovalGateService.visibility(None, False)[0].compile(dialect=postgresql.dialect()))
    assert "owner_user = " not in no_viewer
