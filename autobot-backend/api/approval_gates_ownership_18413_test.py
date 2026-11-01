# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /approval-gates and GET /approval-gates/{id} apply the inbox's viewer-or-admin rule (#18413)."""

import uuid
from types import SimpleNamespace

import pytest
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


# -- Every write route applies the same rule (#18413, #17161) -------------------
_HUMAN = {"auth_method": "session"}
_W_ALICE, _W_BOB, _W_ADMIN = ({**u, **_HUMAN} for u in (_ALICE, _BOB, _ADMIN))
_ROUTES = (
    ("post", "approve", "approve", {"comment": "ok"}),
    ("post", "reject", "reject", {"comment": "no"}),
    ("post", "request-revision", "request_revision", {"comment": "fix"}),
    ("post", "resubmit", "resubmit", {"description": "again"}),
    ("post", "comments", "add_comment", {"body": "hi"}),
    ("post", "tasks", "link_task", {"task_id": "1"}),
    ("delete", "tasks/1", "unlink_task", None),
)


def _write_client(monkeypatch, row, user):
    """Like ``_client`` plus every mutating service method recorded; returns (client, calls)."""
    calls = []

    def recorder(name, result):
        async def call(self, *args, **kwargs):
            calls.append(name)
            return result

        return call

    link = SimpleNamespace(id=uuid.uuid4(), approval_id=uuid.uuid4(), task_id="1", task_type="github_issue")
    comment = SimpleNamespace(
        id=uuid.uuid4(), approval_id=uuid.uuid4(), author="x", author_type="human", body="hi", created_at=None
    )
    results = {"add_comment": comment, "link_task": link, "unlink_task": True}
    for _, _, name, _ in _ROUTES:
        monkeypatch.setattr(ApprovalGateService, name, recorder(name, results.get(name, row)))
    return _client(monkeypatch, row, user), calls


def _send(client, row, verb, suffix, body):
    return client.request(verb, f"/approval-gates/{row.id}/{suffix}", json=body)


@pytest.mark.parametrize("verb,suffix,method,body", _ROUTES)
def test_another_users_write_is_the_identical_404_and_changes_nothing(monkeypatch, verb, suffix, method, body):
    row = _row("alice")
    client, calls = _write_client(monkeypatch, row, _W_BOB)
    resp = _send(client, row, verb, suffix, body)
    missing_client, _ = _write_client(monkeypatch, None, _W_BOB)
    missing = _send(missing_client, row, verb, suffix, body)
    assert (resp.status_code, resp.json()) == (404, missing.json()) and missing.status_code == 404
    assert calls == [] and "secret" not in resp.text and "alice" not in resp.text


@pytest.mark.parametrize("verb,suffix,method,body", _ROUTES)
def test_the_owner_still_writes_their_own_approval(monkeypatch, verb, suffix, method, body):
    row = _row("alice")
    row.requested_by_agent = "alice"  # resubmit stays the requester's (#17349)
    client, calls = _write_client(monkeypatch, row, _W_ALICE)
    assert _send(client, row, verb, suffix, body).status_code in (200, 201, 204)
    assert calls == [method]


@pytest.mark.parametrize("verb,suffix,method,body", [r for r in _ROUTES if r[2] != "resubmit"])
def test_an_admin_still_decides_anyones_approval(monkeypatch, verb, suffix, method, body):
    row = _row("alice")
    client, calls = _write_client(monkeypatch, row, _W_ADMIN)
    assert _send(client, row, verb, suffix, body).status_code in (200, 201, 204)
    assert calls == [method]


def test_an_admin_is_not_the_requester_so_resubmit_keeps_its_own_403(monkeypatch):
    row = _row("alice")
    row.requested_by_agent = "alice"
    client, calls = _write_client(monkeypatch, row, _W_ADMIN)
    assert _send(client, row, "post", "resubmit", {"description": "x"}).status_code == 403
    assert calls == []


def test_a_legacy_unsourced_unowned_gate_is_still_decided_by_any_person(monkeypatch):
    row = _row(None, source=None)
    client, calls = _write_client(monkeypatch, row, _W_BOB)
    assert _send(client, row, "post", "approve", {"comment": "ok"}).status_code == 200
    assert calls == ["approve"]


def test_an_agent_credential_is_still_refused_before_visibility(monkeypatch):
    row = _row("alice")
    client, calls = _write_client(monkeypatch, row, {**_ALICE, "auth_method": "run_token"})
    assert _send(client, row, "post", "approve", {"comment": "ok"}).status_code == 403
    assert calls == []
