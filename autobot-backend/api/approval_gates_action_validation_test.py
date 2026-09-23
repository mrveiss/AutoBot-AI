# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /approval-gates refuses an action no handler is registered for (#17315).

``context`` reaches ``run_post_approval_actions`` verbatim and it dispatches on
``context["action"]``. Before this, any authenticated caller could name a
string that never existed; on approve, the dispatcher recorded a durable
``approval.post_action_failed`` anomaly -- which its own docstring calls "a
real defect, not a no-op" -- so a user could mint defect records at will, and
a reviewer had already been asked to approve something that could not run.
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.approval_gates as route
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from models.approval import Approval
from services import approval_execution
from services.approval_gate_service import ApprovalGateService

_USER = {"username": "u1", "role": "user", "user_id": "u1"}


class _FakeSession:
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


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    """Both maps, so nothing here leaks into the proposer guard (#17315)."""
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())


async def _noop():
    return None


def _client(session):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app)


def _body(**context):
    return {
        "title": "please do the thing",
        "approval_type": "destructive_action",
        "context": context or None,
    }


def test_an_unregistered_action_is_refused_at_creation(monkeypatch):
    session = _FakeSession()
    response = _client(session).post("/approval-gates", json=_body(action="no_such_action"))

    assert response.status_code == 400
    assert "no registered post-approval handler" in response.json()["detail"]
    assert not [
        o for o in session.added if isinstance(o, Approval)
    ], "a refused proposal must not reach the review queue at all"


def test_the_rejection_does_not_echo_the_caller_s_value_or_list_the_registry():
    approval_execution.register_post_approval_action("secret_action", lambda a, s: None, proposed_by="x")
    response = _client(_FakeSession()).post("/approval-gates", json=_body(action="probe_me"))

    assert response.status_code == 400
    assert "probe_me" not in response.text
    assert "secret_action" not in response.text


def test_a_registered_action_is_admitted():
    approval_execution.register_post_approval_action(
        "orphan_storage_delete", lambda a, s: None, proposed_by="api.admin_orphan_storage"
    )
    session = _FakeSession()
    response = _client(session).post(
        "/approval-gates", json=_body(action="orphan_storage_delete", provider="p", candidate_id="c")
    )

    assert response.status_code == 201, response.text
    approval = next(o for o in session.added if isinstance(o, Approval))
    assert approval.context["action"] == "orphan_storage_delete"


def test_an_approval_with_no_action_key_is_still_ordinary_and_allowed():
    """compose_tool_handler creates exactly this; the dispatcher returns early."""
    session = _FakeSession()
    response = _client(session).post("/approval-gates", json=_body(program="x", budgets={}))

    assert response.status_code == 201, response.text


def test_a_non_string_action_is_refused_rather_than_dispatched_on():
    session = _FakeSession()
    response = _client(session).post("/approval-gates", json=_body(action={"nested": "dict"}))

    assert response.status_code == 400
