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

_KEY = "k" * 40  # pragma: allowlist secret
_ID = uuid.uuid4()
_REALIGN = INTERNAL_KEY_REALIGN.name


def _client(existing_by_status: dict | None = None, approval: SimpleNamespace | None = None):
    """The routes over a fake approval service and session; `existing_by_status` answers list_approvals."""
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    session = MagicMock(commit=AsyncMock(), get=AsyncMock(return_value=approval))
    session.execute = AsyncMock(return_value=MagicMock(rowcount=1))  # the one-outcome UPDATE wins
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
    with patch.object(routes, "claim_approval", AsyncMock(return_value=_approval())) as claim:
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
    assert session.add.call_args.args[0].body == note


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
    session.add.assert_not_called()


async def test_approving_changes_nothing_and_says_it_waits_for_the_next_update() -> None:
    session = MagicMock(commit=AsyncMock())
    await realign.execute_internal_key_realign(_approval(), session)
    assert "next update through the builtin updater" in session.add.call_args.args[0].body
    assert approval_execution.is_server_only_action(_REALIGN)
    assert approval_execution.registered_action_proposers()[_REALIGN] == realign.PROPOSED_BY


def test_the_realign_audit_members_close_the_block() -> None:
    """Appended at the END of AuditAction, as the vocabulary's convention asks."""
    names = [member.name for member in AuditAction]
    assert names[-4:] == [
        "INTERNAL_KEY_REALIGN_PROPOSED",
        "INTERNAL_KEY_REALIGN_CLAIMED",
        "INTERNAL_KEY_REALIGN_APPLIED",
        "INTERNAL_KEY_REALIGN_APPLY_FAILED",
    ]


def test_an_ssh_approval_whose_executor_failed_does_not_block_a_new_proposal(audit) -> None:
    """#20046's executor runs inside approve(); reusing a failed, unspent approval would block every retry."""
    stuck = SimpleNamespace(id=uuid.uuid4(), status=ApprovalStatus.APPROVED.value)
    client, service, _ = _client({ApprovalStatus.APPROVED.value: [stuck]})
    response = _post(client, service, PROPOSAL_PATH, {"action": SSH_PASSWORD_DELETE.name, "node_id": "node-b"})
    assert response.json()["created"] is True, "a fresh proposal, so a person can approve the retry"
    assert SSH_PASSWORD_DELETE.reuse_approved is False and INTERNAL_KEY_REALIGN.reuse_approved is True


def test_a_second_outcome_is_refused_not_overwritten(audit) -> None:
    client, service, session = _client(approval=_approval(consumed_at="2026-11-03T22:01:00+00:00"))
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))  # an outcome is already recorded
    body = {"action": _REALIGN, "node_id": "node-b", "result": "applied"}
    assert _post(client, service, outcome_path(str(_ID)), body).status_code == 409
    audit.assert_not_awaited()
    session.add.assert_not_called()


def test_a_reported_detail_is_one_capped_line_of_plain_text(audit) -> None:
    client, service, session = _client(approval=_approval(consumed_at="2026-11-03T22:01:00+00:00"))
    body = {"action": _REALIGN, "node_id": "node-b", "result": "apply_failed", "detail": "a\nb\x00\tc " + "x" * 450}
    assert _post(client, service, outcome_path(str(_ID)), body).status_code == 204
    kept = audit.await_args.kwargs["details"]["detail"]
    assert kept.startswith("a b c ") and len(kept) == 300 and "\n" not in kept and "\x00" not in kept
    assert session.add.call_args.args[0].body == f"Applying it failed: {kept}"
