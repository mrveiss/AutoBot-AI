# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20046: a node's stored SSH password is deleted only by an approved proposal, with an audit record."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import internal_slm_credential_proposals as proposals
from autobot_shared.slm_credential_deletion import ACTION, PROPOSAL_PATH
from models.approval import ApprovalStatus
from services import approval_execution
from services import slm_ssh_password_action as action
from services.approval_gate_service import ApprovalGateService
from services.audit.taxonomy import AuditAction

_KEY = "k" * 40  # pragma: allowlist secret
_DECIDER = uuid.uuid4()


def _approval(decider: uuid.UUID | None = _DECIDER, node_id: str = "node-a") -> SimpleNamespace:
    approval = SimpleNamespace(
        id=uuid.uuid4(),
        decided_by_user="owner",
        status=ApprovalStatus.APPROVED.value,
        context={"action": ACTION, "node_id": node_id, "credential_kind": "ssh_password"},
    )
    approval_execution.set_verified_decider(approval, decider)
    return approval


def _session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    return session


def test_the_audit_name_is_a_taxonomy_member() -> None:
    assert action._AUDIT_ACTION in {member.value for member in AuditAction}


@pytest.mark.parametrize(("removed", "said"), [(True, "deleted"), (False, "no stored"), (None, "no longer exists")])
async def test_approval_deletes_and_audits(removed: bool | None, said: str) -> None:
    session = _session()
    with (
        patch.object(action, "_delete_in_slm", AsyncMock(return_value=removed)) as delete,
        patch.object(action, "audit_log", AsyncMock()) as audit,
    ):
        await action.execute_ssh_password_delete(_approval(), session)
    delete.assert_awaited_once_with("node-a")
    assert said in session.add.call_args.args[0].body
    kwargs = audit.await_args.kwargs
    assert kwargs["result"] == "success" and kwargs["resource"] == "node:node-a"
    assert kwargs["details"]["credential_kind"] == "ssh_password" and "password" not in str(kwargs["details"]).replace(
        "ssh_password", ""
    )


async def test_a_failed_deletion_is_audited_failed_and_raised() -> None:
    with (
        patch.object(action, "_delete_in_slm", AsyncMock(side_effect=RuntimeError("down"))),
        patch.object(action, "audit_log", AsyncMock()) as audit,
        pytest.raises(RuntimeError),
    ):
        await action.execute_ssh_password_delete(_approval(), _session())
    assert audit.await_args.kwargs["result"] == "failed"


async def test_no_verified_decider_deletes_nothing() -> None:
    with (
        patch.object(action, "_delete_in_slm", AsyncMock()) as delete,
        patch.object(action, "audit_log", AsyncMock()) as audit,
        pytest.raises(ValueError),
    ):
        await action.execute_ssh_password_delete(_approval(decider=None), _session())
    delete.assert_not_awaited()
    assert audit.await_args.kwargs["result"] == "denied"


async def _decide(method: str) -> AsyncMock:
    """Run approve or reject through the real gate service; returns the SLM deletion mock."""
    action.register_ssh_password_action()
    approval = _approval()
    service = ApprovalGateService(_session())
    with (
        patch.object(ApprovalGateService, "_transition", AsyncMock(return_value=approval)),
        patch.object(action, "_delete_in_slm", AsyncMock(return_value=True)) as delete,
        patch.object(action, "audit_log", AsyncMock()),
    ):
        kwargs = {"decider_id": _DECIDER} if method == "approve" else {}
        await getattr(service, method)(approval.id, "owner", author_type="user", **kwargs)
    return delete


async def test_approving_deletes_and_rejecting_keeps_it() -> None:
    (await _decide("approve")).assert_awaited_once_with("node-a")
    (await _decide("reject")).assert_not_awaited()


def test_the_action_is_server_only_with_the_proposer_named() -> None:
    action.register_ssh_password_action()
    assert approval_execution.is_server_only_action(ACTION)
    assert approval_execution.registered_action_proposers()[ACTION] == action.PROPOSED_BY


# --- the proposal route -------------------------------------------------


def _client(existing: list, created: SimpleNamespace | None = None):
    app = FastAPI()
    app.include_router(proposals.router, prefix="/api")
    app.dependency_overrides[proposals.get_db_session] = lambda: MagicMock()
    service = MagicMock()
    service.list_approvals = AsyncMock(return_value=existing)
    service.create_approval = AsyncMock(return_value=created or SimpleNamespace(id=uuid.uuid4(), status="pending"))
    return TestClient(app), service


def _post(client: TestClient, service: MagicMock, headers: dict | None = None, node_id: str = "node-a"):
    with patch.object(proposals, "ApprovalGateService", return_value=service):
        return client.post(PROPOSAL_PATH, json={"node_id": node_id}, headers=headers or {})


def test_the_route_refuses_without_the_key(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    client, service = _client([])
    assert _post(client, service).status_code == 403
    assert _post(client, service, {"X-Internal-API-Key": "wrong"}).status_code == 403
    service.create_approval.assert_not_awaited()


def test_a_proposal_names_the_node_and_kind_and_never_a_value(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    client, service = _client([])
    response = _post(client, service, {"X-Internal-API-Key": _KEY})
    assert response.status_code == 201 and response.json()["created"] is True
    kwargs = service.create_approval.await_args.kwargs
    assert kwargs["context"] == {"action": ACTION, "node_id": "node-a", "credential_kind": "ssh_password"}
    assert "node-a" in kwargs["title"] and kwargs["requested_by_agent"] == "slm-enrollment:node-a"


def test_a_retried_enrollment_does_not_duplicate_the_pending_proposal(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    pending = SimpleNamespace(id=uuid.uuid4(), status="pending")
    client, service = _client([pending])
    response = _post(client, service, {"X-Internal-API-Key": _KEY})
    assert response.status_code == 201 and response.json() == {
        "approval_id": str(pending.id),
        "status": "pending",
        "created": False,
    }
    service.create_approval.assert_not_awaited()


def test_a_node_id_cannot_smuggle_a_value(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    client, service = _client([])
    assert _post(client, service, {"X-Internal-API-Key": _KEY}, node_id="a b/../c").status_code == 422


async def test_require_internal_key_raises_403() -> None:
    with pytest.raises(HTTPException) as err:
        await proposals.require_internal_key(None)
    assert err.value.status_code == 403
