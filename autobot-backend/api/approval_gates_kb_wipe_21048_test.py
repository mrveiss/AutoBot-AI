# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Approving a knowledge wipe needs an admin who is a person, through the REAL auth stack (#21048, #17038).

Mirrors ``approval_gates_admin_only_20046_test.py``: the real ``get_current_user`` resolves the caller, the
interactive-human check stays in force beside the role check, and a refused approval records a durable audit
row and approves nothing.
"""

import importlib
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.approval_gate_service import ApprovalGateService
from services.kb_wipe_action import ACTION, register_kb_wipe_action
from testkit.fake_async_session import FakeAsyncSession
from tests.conftest import load_real_auth_middleware

_ID = uuid.UUID(
    "00000000-0000-4000-8000-00000000000c"
)  # fixed: a random id gives each xdist worker a different test id
_USER_ID = "00000000-0000-4000-8000-00000000000d"


def _person(role: str, **over) -> dict:
    return {
        "username": role,
        "role": role,
        "user_id": _USER_ID,
        "iat": 1,
        "auth_method": "jwt",
        "login_token": True,
        **over,
    }


def _row():
    return SimpleNamespace(
        id=_ID, title="t", description=None, approval_type="destructive_action", status="approved",
        requested_by_agent=None, decided_by_user="x", workflow_id=None, workflow_step=None,
        context={"action": ACTION}, decided_at=None, created_at=None, updated_at=None,
        source=None, risk_tier="high", expires_at=None, payload_hash=None, resume_ref=None, owner_user=None,
        comments=[], task_links=[],
    )  # fmt: skip


@pytest.fixture
def world(monkeypatch):
    register_kb_wipe_action()  # the production registration, admin_only included
    real = load_real_auth_middleware()
    monkeypatch.setitem(sys.modules, "auth_middleware", real)
    monkeypatch.delitem(sys.modules, "api.approval_gates", raising=False)
    route = importlib.import_module("api.approval_gates")
    state = SimpleNamespace(user=None, row=_row())
    resolve = AsyncMock(side_effect=lambda _request: state.user)
    monkeypatch.setattr(real, "resolve_human_user", resolve)
    monkeypatch.setattr(real, "admit_opted_in_service", AsyncMock(return_value=None))
    monkeypatch.setattr(ApprovalGateService, "get_visible", AsyncMock(side_effect=lambda *a, **k: state.row))
    approve = AsyncMock(side_effect=lambda *a, **k: state.row)
    monkeypatch.setattr(ApprovalGateService, "approve", approve)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_db_session] = lambda: FakeAsyncSession()
    with patch("api.approval_gates_approver.audit_log", AsyncMock(return_value=True)) as audit:
        yield SimpleNamespace(
            client=TestClient(app, raise_server_exceptions=False), state=state, approve=approve, audit=audit
        )
    sys.modules.pop("api.approval_gates", None)


def _post(world):
    return world.client.post(f"/approval-gates/{_ID}/approve", json={})


def test_an_admin_person_approves_the_wipe(world) -> None:
    world.state.user = _person("admin")
    assert 200 <= _post(world).status_code < 300
    world.approve.assert_awaited_once()


@pytest.mark.parametrize("role", ["user", "operator"])
def test_a_person_without_the_admin_role_is_refused_403_and_audited_and_nothing_is_approved(world, role) -> None:
    world.state.user = _person(role)
    assert _post(world).status_code == 403
    world.approve.assert_not_awaited()
    kwargs = world.audit.await_args.kwargs
    assert world.audit.await_args.args[0] == "approval.approve" and kwargs["result"] == "denied"
    assert kwargs["durable"] is True and kwargs["details"]["action"] == ACTION


@pytest.mark.parametrize(
    "over",
    [{"auth_method": "api_key"}, {"service": True}, {"login_token": False}, {"auth_method": "run_jwt"}],
    ids=["api_key", "service_key", "jwt_without_login_token", "run_token"],
)
def test_a_non_interactive_principal_is_refused_even_with_the_admin_role(world, over) -> None:
    world.state.user = _person("admin", **over)
    assert _post(world).status_code == 403
    world.approve.assert_not_awaited()
