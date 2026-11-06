# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Approving a stored-credential deletion needs the admin role, through the REAL auth stack (#20046, #20899).

The real ``get_current_user`` resolves the caller; the interactive-human check stays in force beside the
role check. A non-admin person gets 403 and a durable audit row, and nothing is approved.
"""

import importlib
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autobot_shared.slm_credential_deletion import ACTION
from services.approval_gate_service import ApprovalGateService
from services.slm_ssh_password_action import register_ssh_password_action
from tests.conftest import load_real_auth_middleware

_ID = uuid.uuid4()


def _person(role: str, **over) -> dict:
    return {
        "username": role,
        "role": role,
        "user_id": str(uuid.uuid4()),
        "iat": 1,
        "auth_method": "jwt",
        "login_token": True,
        **over,
    }


def _row(action: str | None):
    return SimpleNamespace(
        id=_ID, title="t", description=None, approval_type="destructive_action", status="approved",
        requested_by_agent=None, decided_by_user="x", workflow_id=None, workflow_step=None,
        context={"action": action} if action else {}, decided_at=None, created_at=None, updated_at=None,
        source=None, risk_tier="high", expires_at=None, payload_hash=None, resume_ref=None, owner_user=None,
        comments=[], task_links=[],
    )  # fmt: skip


@pytest.fixture
def world(monkeypatch):
    register_ssh_password_action()  # the production registration, admin_only included
    real = load_real_auth_middleware()
    monkeypatch.setitem(sys.modules, "auth_middleware", real)
    monkeypatch.delitem(sys.modules, "api.approval_gates", raising=False)
    route = importlib.import_module("api.approval_gates")
    state = SimpleNamespace(user=None, row=_row(ACTION))
    resolve = AsyncMock(side_effect=lambda _request: state.user)
    monkeypatch.setattr(real, "resolve_human_user", resolve)
    monkeypatch.setattr(real, "admit_opted_in_service", AsyncMock(return_value=None))
    monkeypatch.setattr(ApprovalGateService, "get_visible", AsyncMock(side_effect=lambda *a, **k: state.row))
    approve = AsyncMock(side_effect=lambda *a, **k: state.row)
    monkeypatch.setattr(ApprovalGateService, "approve", approve)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_db_session] = lambda: MagicMock()
    with patch("api.approval_gates_approver.audit_log", AsyncMock(return_value=True)) as audit:
        yield SimpleNamespace(
            client=TestClient(app, raise_server_exceptions=False), state=state, approve=approve, audit=audit
        )
    sys.modules.pop("api.approval_gates", None)


def _post(world):
    return world.client.post(f"/approval-gates/{_ID}/approve", json={})


def test_an_admin_approves_the_credential_deletion(world) -> None:
    world.state.user = _person("admin")
    assert 200 <= _post(world).status_code < 300
    world.approve.assert_awaited_once()


@pytest.mark.parametrize("role", ["user", "operator"])
def test_a_non_admin_person_is_refused_403_and_audited_and_nothing_is_approved(world, role) -> None:
    world.state.user = _person(role)
    assert _post(world).status_code == 403
    world.approve.assert_not_awaited()
    kwargs = world.audit.await_args.kwargs
    assert world.audit.await_args.args[0] == "approval.approve" and kwargs["result"] == "denied"
    assert kwargs["durable"] is True and kwargs["details"]["action"] == ACTION


def test_the_interactive_human_check_still_applies_to_an_admin_credential(world) -> None:
    world.state.user = _person("admin", auth_method="api_key")
    assert _post(world).status_code == 403
    world.approve.assert_not_awaited()


def test_other_actions_keep_their_existing_approver_rule(world) -> None:
    world.state.row = _row(None)
    world.state.user = _person("user")
    assert 200 <= _post(world).status_code < 300
    world.audit.assert_not_awaited()
