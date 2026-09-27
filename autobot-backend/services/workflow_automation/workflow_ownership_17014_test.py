# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflow control is scoped to the owner or an admin (#17014).

The hole these tests pin: ``control_workflow`` authenticated its caller and stopped
there, so any signed-in user could pause, cancel or approve another user's workflow.
``owner_id`` existed on the model and no creation path ever set it, so the checks
that did exist compared against ``None`` and matched nobody.

The REST tests drive the real route functions through ``TestClient`` with only
``get_current_user`` and the workflow manager stood in for, so the ownership lookup,
the 403 and the ``except HTTPException`` re-raise all run for real. That re-raise
matters: without it the route's ``except Exception`` turns a 403 into a 500, and a
test asserting "not authorised" would pass on an unrelated crash.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from auth_middleware import get_current_user

from . import routes
from .models import ActiveWorkflow, AutomationMode
from .workflow_ownership import caller_id, is_owner_or_admin
from .ws_endpoint import may_control

ALICE = {"username": "alice", "user_id": "u-alice", "role": "user"}
BOB = {"username": "bob", "user_id": "u-bob", "role": "user"}
ADMIN = {"username": "root", "user_id": "u-root", "role": "admin"}


def _workflow(owner_id: str | None, workflow_id: str = "wf-1") -> ActiveWorkflow:
    return ActiveWorkflow(
        workflow_id=workflow_id,
        name="n",
        description="d",
        session_id="s-1",
        steps=[],
        automation_mode=AutomationMode.SEMI_AUTOMATIC,
        owner_id=owner_id,
    )


class _Manager:
    """Only what the ownership path touches."""

    def __init__(self, workflow):
        self.active_workflows = {workflow.workflow_id: workflow} if workflow else {}
        self.completed_workflows = {}
        self.controlled = []

    async def handle_workflow_control(self, request):
        self.controlled.append(request.action)
        return True

    def get_workflow_status(self, workflow_id):
        return {"workflow_id": workflow_id}

    def get_pending_approval(self, workflow_id):
        return None

    async def start_workflow_execution(self, workflow_id):
        return True


_DEFAULT = object()  # `None` means "no workflow in the store", so it cannot mean "default"


def _client(monkeypatch, caller: dict, workflow=_DEFAULT) -> tuple[TestClient, _Manager]:
    manager = _Manager(_workflow("u-alice") if workflow is _DEFAULT else workflow)
    monkeypatch.setattr(routes, "get_workflow_manager", lambda: manager)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: caller
    return TestClient(app, raise_server_exceptions=False), manager


# --------------------------------------------------------------------------
# caller_id: the identity recorded must be the identity compared against
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        ({"user_id": "u-1", "sub": "s-1", "username": "n"}, "u-1"),
        ({"sub": "s-1", "username": "n"}, "s-1"),
        ({"username": "n"}, "n"),
        ({}, None),
        (None, None),
    ],
)
def test_caller_id_claim_precedence(user, expected):
    assert caller_id(user) == expected


# --------------------------------------------------------------------------
# is_owner_or_admin
# --------------------------------------------------------------------------


def test_owner_may_and_other_user_may_not():
    workflow = _workflow("u-alice")
    assert is_owner_or_admin(workflow, ALICE) is True
    assert is_owner_or_admin(workflow, BOB) is False


def test_admin_may_even_when_not_owner():
    assert is_owner_or_admin(_workflow("u-alice"), ADMIN) is True


def test_unowned_workflow_is_admin_only_not_open_to_everyone():
    """The whole defect in one assertion: no owner must mean nobody, not anybody."""
    unowned = _workflow(None)
    assert is_owner_or_admin(unowned, ALICE) is False
    assert is_owner_or_admin(unowned, BOB) is False
    assert is_owner_or_admin(unowned, ADMIN) is True


def test_username_owner_matches_a_caller_identified_by_username():
    """A workflow created before user_id claims existed records the username."""
    assert is_owner_or_admin(_workflow("alice"), ALICE) is True


# --------------------------------------------------------------------------
# AC2: the REST routes, cross-user
# --------------------------------------------------------------------------

_CONTROL_BODY = {"workflow_id": "wf-1", "action": "cancel"}


def test_control_workflow_refuses_another_users_workflow(monkeypatch):
    client, manager = _client(monkeypatch, BOB)
    response = client.post("/control_workflow", json=_CONTROL_BODY)
    assert response.status_code == 403
    assert manager.controlled == [], "the control action must not have run"


def test_control_workflow_allows_the_owner(monkeypatch):
    client, manager = _client(monkeypatch, ALICE)
    assert client.post("/control_workflow", json=_CONTROL_BODY).status_code == 200
    assert manager.controlled == ["cancel"]


def test_control_workflow_allows_an_admin(monkeypatch):
    client, manager = _client(monkeypatch, ADMIN)
    assert client.post("/control_workflow", json=_CONTROL_BODY).status_code == 200
    assert manager.controlled == ["cancel"]


def test_control_workflow_404_is_not_masked_as_500(monkeypatch):
    """The re-raise guard: an absent workflow is a 404, not "Internal server error"."""
    client, _ = _client(monkeypatch, ALICE, workflow=None)
    assert client.post("/control_workflow", json=_CONTROL_BODY).status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/workflow_status/wf-1"),
        ("get", "/pending_approval/wf-1"),
        ("post", "/start_workflow/wf-1"),
        # present_plan was missing from this list in the first draft, and that is exactly
        # why its 403 was still being swallowed into a 500 -- an unlisted route is an
        # unchecked route.
        ("post", "/present_plan/wf-1"),
    ],
)
def test_state_and_control_routes_refuse_another_user(monkeypatch, method, path):
    client, _ = _client(monkeypatch, BOB)
    assert getattr(client, method)(path).status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/workflow_status/wf-1"),
        ("get", "/pending_approval/wf-1"),
    ],
)
def test_state_routes_allow_the_owner(monkeypatch, method, path):
    client, _ = _client(monkeypatch, ALICE)
    assert getattr(client, method)(path).status_code == 200


def test_create_workflow_records_the_caller_as_owner(monkeypatch):
    """AC1 at the REST route: the workflow must carry the creator, not None."""
    recorded = {}

    class _Creating(_Manager):
        async def create_automated_workflow(self, **kwargs):
            recorded.update(kwargs)
            return "wf-new"

    manager = _Creating(_workflow("u-alice"))
    monkeypatch.setattr(routes, "get_workflow_manager", lambda: manager)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: ALICE
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/create_workflow",
        json={"name": "w", "description": "", "steps": [], "session_id": "s-1"},
    )
    assert response.status_code == 200, response.text
    assert recorded["owner_id"] == "u-alice"


# --------------------------------------------------------------------------
# AC3: the WebSocket check admits owners, not only admins
# --------------------------------------------------------------------------


def test_may_control_admits_the_recorded_owner():
    manager = _Manager(_workflow("u-alice"))
    assert may_control(manager, "wf-1", ALICE) is True


def test_may_control_refuses_another_user_and_admits_an_admin():
    manager = _Manager(_workflow("u-alice"))
    assert may_control(manager, "wf-1", BOB) is False
    assert may_control(manager, "wf-1", ADMIN) is True


def test_may_control_refuses_everyone_but_admin_on_an_unowned_workflow():
    manager = _Manager(_workflow(None))
    assert may_control(manager, "wf-1", ALICE) is False
    assert may_control(manager, "wf-1", ADMIN) is True


# --------------------------------------------------------------------------
# AC4: the executor no longer treats a session id as a user
# --------------------------------------------------------------------------


def test_secret_resolution_without_an_owner_resolves_nothing(monkeypatch):
    """A workflow with no owner must resolve no user's secrets, not the session's."""
    from . import executor

    called = []
    monkeypatch.setattr(
        executor,
        "get_workflow_secret_service",
        lambda: SimpleNamespace(resolve_secrets=lambda c, o: called.append(o) or (c, frozenset())),
    )

    command, names = executor._resolve_command_secrets("echo ${secrets.TOKEN}", None)

    assert command == "echo ${secrets.TOKEN}"
    assert names == frozenset()
    assert called == [], "the secret service must not be asked on behalf of a non-user"


def test_secret_resolution_with_an_owner_still_uses_it(monkeypatch):
    from . import executor

    seen = []
    monkeypatch.setattr(
        executor,
        "get_workflow_secret_service",
        lambda: SimpleNamespace(resolve_secrets=lambda c, o: (seen.append(o), ("resolved", frozenset({"TOKEN"})))[1]),
    )

    command, names = executor._resolve_command_secrets("echo ${secrets.TOKEN}", "u-alice")

    assert (command, names) == ("resolved", frozenset({"TOKEN"}))
    assert seen == ["u-alice"]


def test_creating_without_an_owner_is_logged_not_silent(caplog):
    """An unowned workflow is admin-only and resolves no secrets; both are invisible
    where they bite, so creation says so once."""
    import asyncio
    import logging

    from .manager import WorkflowAutomationManager

    manager = WorkflowAutomationManager.__new__(WorkflowAutomationManager)
    manager.active_workflows = {}

    with caplog.at_level(logging.WARNING):
        asyncio.run(
            WorkflowAutomationManager.create_automated_workflow(
                manager, name="n", description="d", steps=[], session_id="s-1"
            )
        )

    assert any(
        "no owner" in record.getMessage() for record in caplog.records
    ), "creating an unowned workflow must be logged"
