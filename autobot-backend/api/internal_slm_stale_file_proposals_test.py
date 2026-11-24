# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#22033: stale code-sync files are proposed once per location, and claimed only under a human's approval.

The real routes and the real claim logic run; only the database session, the approval service and the audit
write are faked. Each check has a contrast: the shape that passes and the shape that must not.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import internal_slm_stale_file_proposals as route
from autobot_shared.slm_stale_file_actions import (
    CLAIM_PATH_TEMPLATE,
    LOCATION_KEY,
    MAX_FILES_PER_PROPOSAL,
    PROPOSAL_PATH,
    STALE_SYNC_FILES_CLEANUP,
)
from models.approval import ApprovalStatus
from testkit.fake_async_session import FakeAsyncSession, FakeResult

ACTION = STALE_SYNC_FILES_CLEANUP.name
_KEY = "k" * 40  # pragma: allowlist secret
_ID = uuid.UUID("00000000-0000-4000-8000-000000000022")
_NEW_ID = uuid.UUID("00000000-0000-4000-8000-000000000023")
_BLOB = "a" * 40
_FILE = {"path": "main.py", "size_bytes": 12, "modified_at": "2026-01-02T03:04:05Z", "blob": _BLOB}
_TARGET = "/opt/node-root"


def _body(**overrides) -> dict:
    body = {"node_id": "node-a", "old_target": _TARGET, "commit": "abc1234", "files": [_FILE], "total_found": 1}
    return {**body, **overrides}


@pytest.fixture(autouse=True)
def _env(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    monkeypatch.setattr(route, "is_split_without_tls", lambda: False)


def _client(session: FakeAsyncSession | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    app.dependency_overrides[route.get_db_session] = lambda: session or FakeAsyncSession()
    return TestClient(app)


def _service(existing: list):
    service = MagicMock()
    service.list_approvals = AsyncMock(return_value=existing)
    service.create_approval = AsyncMock(return_value=SimpleNamespace(id=_NEW_ID, status="pending"))
    return service


def _propose(service, body=None, headers=None, audit=True):
    headers = {"X-Internal-API-Key": _KEY} if headers is None else headers
    with (
        patch.object(route, "ApprovalGateService", return_value=service),
        patch("services.kb_cleanup_proposals.audit_log", AsyncMock(return_value=audit)) as written,
    ):
        response = _client().post(PROPOSAL_PATH, json=body or _body(), headers=headers)
    return response, written


def test_the_proposal_route_refuses_without_the_key() -> None:
    service = _service([])
    assert _propose(service, headers={})[0].status_code == 403
    assert _propose(service, headers={"X-Internal-API-Key": "wrong"})[0].status_code == 403
    service.create_approval.assert_not_awaited()


def test_a_proposal_lists_every_file_and_freezes_them_in_the_context() -> None:
    service = _service([])
    response, _ = _propose(service)
    assert response.status_code == 201 and response.json()["created"] is True
    kwargs = service.create_approval.await_args.kwargs
    assert kwargs["approval_type"] == "destructive_action" and kwargs["requested_by_agent"] == "slm-code-sync:node-a"
    assert kwargs["context"]["action"] == ACTION and kwargs["context"][LOCATION_KEY] == f"node-a:{_TARGET}"
    assert kwargs["context"]["files"][0]["path"] == "main.py" and kwargs["context"]["old_target"] == _TARGET
    assert f"{_TARGET}/main.py" in kwargs["description"] and "12 B" in kwargs["description"]


def test_a_location_with_a_pending_proposal_gets_that_one_not_a_second() -> None:
    service = _service([SimpleNamespace(id=_ID, status="pending")])
    response, _ = _propose(service)
    assert response.json() == {"approval_id": str(_ID), "status": "pending", "created": False}
    service.create_approval.assert_not_awaited()


def test_the_audit_row_is_written_first_and_a_failed_write_creates_no_approval() -> None:
    created, written = _propose(_service([]))
    assert created.status_code == 201 and written.await_args.kwargs["durable"] is True
    service = _service([])
    refused, _ = _propose(service, audit=False)
    assert refused.status_code == 503
    service.create_approval.assert_not_awaited()


@pytest.mark.parametrize("path", ["/etc/passwd", "../x", "a/../b", "a\nb", "a\tb", "", "a" * 2000])
def test_a_path_that_could_leave_the_location_or_split_a_line_is_refused(path: str) -> None:
    assert _propose(_service([]), _body(files=[{**_FILE, "path": path}]))[0].status_code == 422


def test_contrast_a_plain_nested_relative_path_is_accepted() -> None:
    assert _propose(_service([]), _body(files=[{**_FILE, "path": "api/v1/x y.py"}]))[0].status_code == 201


def test_the_file_count_is_capped_but_a_path_is_never_truncated() -> None:
    over = [{**_FILE, "path": f"f{i}.py"} for i in range(MAX_FILES_PER_PROPOSAL + 1)]
    assert _propose(_service([]), _body(files=over, total_found=len(over)))[0].status_code == 422
    assert (
        _propose(_service([]), _body(files=over[:MAX_FILES_PER_PROPOSAL], total_found=len(over)))[0].status_code == 201
    )
    long_path = "d/" * 400 + "x.py"
    service = _service([])
    _propose(service, _body(files=[{**_FILE, "path": long_path}]))
    assert service.create_approval.await_args.kwargs["context"]["files"][0]["path"] == long_path


@pytest.mark.parametrize("old_target", ["relative/dir", "/opt/../etc", "/opt/./x", "/", "/opt", "//"])
def test_an_old_target_must_be_an_absolute_plain_path(old_target: str) -> None:
    assert _propose(_service([]), _body(old_target=old_target))[0].status_code == 422


# --- the claim route ------------------------------------------------------


def _approval(**overrides) -> SimpleNamespace:
    fields = {
        "id": _ID,
        "company_id": None,
        "status": ApprovalStatus.APPROVED.value,
        "decided_by_user": "alice",
        "decided_at": datetime.now(timezone.utc),
        "context": {
            "action": ACTION,
            "node_id": "node-a",
            "credential_kind": "stale_sync_files",
            "old_target": _TARGET,
            "files": [_FILE],
        },
    }
    return SimpleNamespace(**{**fields, **overrides})


def _claim(approval, node_id: str = "node-a", audit: bool = True, rowcount: int = 1):
    session = FakeAsyncSession(default_result=FakeResult(rowcount=rowcount), on_get=lambda entity, ident: approval)
    with patch.object(route, "audit_log", AsyncMock(return_value=audit)) as written:
        response = _client(session).post(
            CLAIM_PATH_TEMPLATE.format(approval_id=_ID),
            json={"action": ACTION, "node_id": node_id},
            headers={"X-Internal-API-Key": _KEY},
        )
    return response, session, written


def test_a_human_approved_claim_is_spent_once_and_returns_the_approved_files() -> None:
    response, session, written = _claim(_approval())
    body = response.json()
    assert response.status_code == 200 and body["old_target"] == _TARGET and body["files"][0]["path"] == "main.py"
    assert session.commits == 1 and len(session.statements) == 1
    assert written.await_args.kwargs["durable"] is True and written.await_args.kwargs["details"]["phase"] == "claimed"


@pytest.mark.parametrize(
    "approval",
    [
        None,
        _approval(status=ApprovalStatus.PENDING.value),
        _approval(status=ApprovalStatus.REJECTED.value),
        _approval(decided_by_user="service:slm"),
        _approval(context={"action": "other", "node_id": "node-a", "credential_kind": "stale_sync_files"}),
        _approval(context={"action": ACTION, "node_id": "node-a", "credential_kind": "ssh_password"}),
        _approval(
            context={"action": ACTION, "node_id": "node-a", "credential_kind": "stale_sync_files", "consumed_at": "x"}
        ),
    ],
)
def test_a_claim_for_anything_but_an_unused_human_approval_is_refused_and_spends_nothing(approval) -> None:
    response, session, _ = _claim(approval)
    assert response.status_code == 403 and session.commits == 0 and session.statements == []


def test_a_claim_naming_another_node_is_refused() -> None:
    assert _claim(_approval(), node_id="node-b")[0].status_code == 403
    assert _claim(_approval(), node_id="node-a")[0].status_code == 200


def test_a_second_claim_that_loses_the_spend_race_is_refused() -> None:
    assert _claim(_approval(), rowcount=0)[0].status_code == 403


def test_a_claim_whose_audit_row_cannot_be_written_spends_nothing() -> None:
    response, session, _ = _claim(_approval(), audit=False)
    assert response.status_code == 503 and session.commits == 0 and session.statements == []


def test_contrast_a_two_segment_old_target_is_accepted() -> None:
    assert _propose(_service([]), _body(old_target="/opt/root"))[0].status_code == 201


def test_a_user_jwt_without_the_internal_key_is_refused_on_both_internal_routes() -> None:
    """A bearer token is not the service key: the key check refuses it before any handler runs (#22033)."""
    service = _service([])
    jwt = {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.e30.sig"}  # pragma: allowlist secret
    assert _propose(service, headers=jwt)[0].status_code == 403
    service.create_approval.assert_not_awaited()
    session = FakeAsyncSession(default_result=FakeResult(rowcount=1), on_get=lambda entity, ident: _approval())
    claim = _client(session).post(
        CLAIM_PATH_TEMPLATE.format(approval_id=_ID), json={"action": ACTION, "node_id": "node-a"}, headers=jwt
    )
    assert claim.status_code == 403 and session.commits == 0 and session.statements == []
