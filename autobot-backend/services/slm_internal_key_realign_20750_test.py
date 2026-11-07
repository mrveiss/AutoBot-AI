# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20750: re-aligning the backend's internal key is proposed, approved by a human, claimed once and reported."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import internal_slm_credential_proposals as routes
from autobot_shared.slm_credential_actions import (
    INTERNAL_KEY_REALIGN,
    PROPOSAL_PATH,
    SSH_PASSWORD_DELETE,
    claim_path,
    outcome_path,
)
from models.approval import ApprovalStatus
from services import approval_execution, slm_credential_claim
from services import slm_internal_key_realign_action as realign
from services.audit.taxonomy import AuditAction
from testkit.fake_async_session import FakeAsyncSession, FakeResult

_KEY = "k" * 40  # pragma: allowlist secret
_ID = uuid.UUID(
    "00000000-0000-4000-8000-000000000001"
)  # fixed: a random id gives each xdist worker a different test id
_REALIGN = INTERNAL_KEY_REALIGN.name


def _client(existing_by_status: dict | None = None, approval: SimpleNamespace | None = None):
    """The routes over a fake approval service and session; `existing_by_status` answers list_approvals."""
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    # the one-outcome UPDATE wins (rowcount 1); get answers the approval under test
    session = FakeAsyncSession(default_result=FakeResult(rowcount=1), on_get=lambda _entity, _ident: approval)
    app.dependency_overrides[routes.get_db_session] = lambda: session
    service = MagicMock()
    by_status = existing_by_status or {}
    service.list_approvals = AsyncMock(side_effect=lambda status, **_kw: by_status.get(status, []))
    service.create_approval = AsyncMock(
        side_effect=lambda **kw: SimpleNamespace(id=_ID, status="pending", decided_by_user=None, **kw)
    )
    return TestClient(app), service, session


def _post(client, service, path, body, key=_KEY):
    with patch.object(routes, "ApprovalGateService", return_value=service):
        return client.post(path, json=body, headers={"X-Internal-API-Key": key})


@pytest.fixture(autouse=True)
def _internal_key(monkeypatch):
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)


@pytest.fixture
def audit():
    with patch("services.slm_credential_texts.audit_log", AsyncMock(return_value=True)) as recorded:
        yield recorded


def test_a_realign_proposal_says_when_it_applies_and_what_depends_on_the_key(audit) -> None:
    client, service, _ = _client()
    response = _post(client, service, PROPOSAL_PATH, {"action": _REALIGN, "node_id": "node-b"})
    assert response.status_code == 201 and response.json()["created"] is True
    kwargs = service.create_approval.await_args.kwargs
    assert kwargs["context"] == {"action": _REALIGN, "node_id": "node-b", "credential_kind": "internal_api_key"}
    assert kwargs["requested_by_agent"] == "slm-update:node-b"
    text = kwargs["description"]
    for needed in (
        "NEXT update through the builtin updater",
        "celery",
        "System vault",
        "voice, personality and memory",
    ):
        assert needed in text, needed
    assert "SLM agent role falls back" in text, "the slm_agent fallback is listed"
    assert audit.await_args.args[0] == AuditAction.INTERNAL_KEY_REALIGN_PROPOSED.value


def test_an_approved_unspent_realign_is_found_again_not_duplicated(audit) -> None:
    """The next update re-proposes and must get the approved one back, to claim it."""
    approved = SimpleNamespace(id=_ID, status=ApprovalStatus.APPROVED.value)
    client, service, _ = _client({ApprovalStatus.APPROVED.value: [approved]})
    response = _post(client, service, PROPOSAL_PATH, {"action": _REALIGN, "node_id": "node-b"})
    assert response.json() == {"approval_id": str(_ID), "status": "approved", "created": False}
    service.create_approval.assert_not_awaited()
    audit.assert_not_awaited()


def _approval(action: str = _REALIGN, **context) -> SimpleNamespace:
    return SimpleNamespace(
        id=_ID,
        company_id=None,
        status=ApprovalStatus.APPROVED.value,
        decided_by_user="owner",
        decided_at="2026-11-03T22:00:00+00:00",
        requested_by_agent="slm-update:node-b",
        context={"action": action, "node_id": "node-b", "credential_kind": "internal_api_key", **context},
    )


def test_a_claim_is_audited_and_an_ssh_approval_cannot_be_claimed_as_a_realign(audit) -> None:
    client, service, _ = _client()

    async def claim_then_record(_session, _id, _action, _node, record_first):
        assert await record_first(_approval())  # the route hands the audit write to run BEFORE the spend
        return _approval()

    with patch.object(routes, "claim_approval", AsyncMock(side_effect=claim_then_record)) as claim:
        ok = _post(client, service, claim_path(str(_ID)), {"action": _REALIGN, "node_id": "node-b"})
    assert ok.status_code == 200
    assert claim.await_args.args[2] is INTERNAL_KEY_REALIGN
    assert audit.await_args.args[0] == AuditAction.INTERNAL_KEY_REALIGN_CLAIMED.value
    ssh = _approval(SSH_PASSWORD_DELETE.name, credential_kind="ssh_password")
    assert slm_credential_claim._refusal(ssh, INTERNAL_KEY_REALIGN, "node-b") == "approval names another action"


@pytest.mark.parametrize(
    "result, member, note",
    [
        ("applied", AuditAction.INTERNAL_KEY_REALIGN_APPLIED, "Applied."),
        ("apply_failed", AuditAction.INTERNAL_KEY_REALIGN_APPLY_FAILED, "Applying it failed: backend refused it"),
    ],
)
def test_the_outcome_of_a_claimed_realign_is_audited_and_commented(audit, result, member, note) -> None:
    client, service, session = _client(approval=_approval(consumed_at="2026-11-03T22:01:00+00:00"))
    body = {"action": _REALIGN, "node_id": "node-b", "result": result, "detail": "backend refused it"}
    assert _post(client, service, outcome_path(str(_ID)), body).status_code == 204
    assert audit.await_args.args[0] == member.value
    assert session.added[-1].body == note


@pytest.mark.parametrize(
    "approval",
    [
        None,
        _approval(),
        _approval(SSH_PASSWORD_DELETE.name, consumed_at="x"),
        _approval(node_id="other", consumed_at="x"),
    ],
    ids=["missing", "not-claimed", "other-action", "other-node"],
)
def test_an_outcome_needs_a_claimed_realign_for_that_node(audit, approval) -> None:
    client, service, session = _client(approval=approval)
    body = {"action": _REALIGN, "node_id": "node-b", "result": "applied"}
    assert _post(client, service, outcome_path(str(_ID)), body).status_code == 409
    audit.assert_not_awaited()
    assert not session.added


async def test_approving_changes_nothing_and_says_it_waits_for_the_next_update() -> None:
    session = FakeAsyncSession()
    await realign.execute_internal_key_realign(_approval(), session)
    assert "next update through the builtin updater" in session.added[-1].body
    assert approval_execution.is_server_only_action(_REALIGN)
    assert approval_execution.registered_action_proposers()[_REALIGN] == realign.PROPOSED_BY


def test_the_realign_audit_members_close_the_block() -> None:
    """Appended at the END of AuditAction, as the vocabulary's convention asks."""
    names = [member.name for member in AuditAction]
    assert names[-5:] == [
        "INTERNAL_KEY_REALIGN_PROPOSED",
        "INTERNAL_KEY_REALIGN_CLAIMED",
        "INTERNAL_KEY_REALIGN_APPLIED",
        "INTERNAL_KEY_REALIGN_APPLY_FAILED",
        "INTERNAL_KEY_REALIGN_PROPOSAL_FAILED",
    ]


def test_an_ssh_approval_whose_executor_failed_does_not_block_a_new_proposal(audit) -> None:
    """#20046's executor runs inside approve(); reusing a failed, unspent approval would block every retry."""
    stuck = SimpleNamespace(id=uuid.UUID("00000000-0000-4000-8000-000000000002"), status=ApprovalStatus.APPROVED.value)
    client, service, _ = _client({ApprovalStatus.APPROVED.value: [stuck]})
    response = _post(client, service, PROPOSAL_PATH, {"action": SSH_PASSWORD_DELETE.name, "node_id": "node-b"})
    assert response.json()["created"] is True, "a fresh proposal, so a person can approve the retry"
    assert SSH_PASSWORD_DELETE.reuse_approved is False and INTERNAL_KEY_REALIGN.reuse_approved is True


def test_a_second_outcome_is_refused_not_overwritten(audit) -> None:
    client, service, session = _client(approval=_approval(consumed_at="2026-11-03T22:01:00+00:00"))
    session.default_result = FakeResult(rowcount=0)  # an outcome is already recorded
    body = {"action": _REALIGN, "node_id": "node-b", "result": "applied"}
    assert _post(client, service, outcome_path(str(_ID)), body).status_code == 409
    audit.assert_not_awaited()
    assert not session.added


def test_a_reported_detail_is_one_capped_line_of_plain_text(audit) -> None:
    client, service, session = _client(approval=_approval(consumed_at="2026-11-03T22:01:00+00:00"))
    body = {"action": _REALIGN, "node_id": "node-b", "result": "apply_failed", "detail": "a\nb\x00\tc " + "x" * 450}
    assert _post(client, service, outcome_path(str(_ID)), body).status_code == 204
    kept = audit.await_args.kwargs["details"]["detail"]
    assert kept.startswith("a b c ") and len(kept) == 300 and "\n" not in kept and "\x00" not in kept
    assert session.added[-1].body == f"Applying it failed: {kept}"


def test_a_claim_whose_audit_row_fails_spends_nothing_and_is_503() -> None:
    """The paper trail comes first (#17038): the row is written before the spend, and a failed row aborts it."""
    client, service, session = _client(approval=_approval())
    with patch("services.slm_credential_texts.audit_log", AsyncMock(return_value=False)) as recorded:
        response = _post(client, service, claim_path(str(_ID)), {"action": _REALIGN, "node_id": "node-b"})
    assert response.status_code == 503
    recorded.assert_awaited_once()
    assert not session.statements  # the spending UPDATE never ran
    assert session.commits == 0


def test_an_outcome_whose_audit_row_fails_is_not_stamped() -> None:
    client, service, session = _client(approval=_approval(consumed_at="2026-11-03T22:01:00+00:00"))
    body = {"action": _REALIGN, "node_id": "node-b", "result": "applied"}
    with patch("services.slm_credential_texts.audit_log", AsyncMock(return_value=False)):
        response = _post(client, service, outcome_path(str(_ID)), body)
    assert response.status_code == 503
    assert session.rollbacks == 1
    assert session.commits == 0


def test_a_proposal_whose_audit_row_fails_creates_nothing_and_is_503() -> None:
    """Paper trail first (#17038): no audit row means no proposal row, and nothing is withdrawn."""
    client, service, session = _client()
    service.reject = AsyncMock()
    with patch("services.slm_credential_texts.audit_log", AsyncMock(return_value=False)) as recorded:
        response = _post(client, service, PROPOSAL_PATH, {"action": _REALIGN, "node_id": "node-b"})
    assert response.status_code == 503
    recorded.assert_awaited_once()
    service.create_approval.assert_not_awaited()
    service.reject.assert_not_awaited()
    assert session.commits == 0


def test_a_proposal_writes_its_audit_row_before_the_approval_and_names_its_id() -> None:
    client, service, _ = _client()
    order: list[str] = []
    recorded = AsyncMock(side_effect=lambda *a, **kw: order.append("audit") or True)
    created = service.create_approval.side_effect
    service.create_approval = AsyncMock(side_effect=lambda **kw: order.append("approval") or created(**kw))
    with patch("services.slm_credential_texts.audit_log", recorded):
        response = _post(client, service, PROPOSAL_PATH, {"action": _REALIGN, "node_id": "node-b"})
    assert response.status_code == 201
    assert order == ["audit", "approval"]
    named = recorded.await_args.kwargs["details"]["approval_id"]
    assert named == str(service.create_approval.await_args.kwargs["approval_id"])


def _failing_create(client_service) -> None:
    client_service.create_approval = AsyncMock(side_effect=RuntimeError("db down password=hunter2"))


def test_a_proposal_whose_approval_fails_is_compensated_with_the_same_id_and_is_503(audit) -> None:
    client, service, session = _client()
    _failing_create(service)
    response = _post(client, service, PROPOSAL_PATH, {"action": _REALIGN, "node_id": "node-b"})
    assert response.status_code == 503
    first, second = audit.await_args_list
    assert first.args[0] == AuditAction.INTERNAL_KEY_REALIGN_PROPOSED.value
    assert second.args[0] == AuditAction.INTERNAL_KEY_REALIGN_PROPOSAL_FAILED.value
    assert second.kwargs["details"]["approval_id"] == first.kwargs["details"]["approval_id"]
    reason = second.kwargs["details"]["detail"]
    assert reason.startswith("RuntimeError: ") and "hunter2" not in reason
    assert session.commits == 0


def test_a_failing_compensating_write_is_logged_and_still_503(caplog) -> None:
    client, service, session = _client()
    _failing_create(service)
    rows = AsyncMock(side_effect=[True, RuntimeError("audit down")])
    with patch("services.slm_credential_texts.audit_log", rows), caplog.at_level("ERROR"):
        response = _post(client, service, PROPOSAL_PATH, {"action": _REALIGN, "node_id": "node-b"})
    assert response.status_code == 503
    assert rows.await_count == 2
    assert "NO compensating row" in caplog.text
    assert session.commits == 0
