# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent-terminal sessions act only for their owner or an admin (#17052, #17053, #17057).

Before this, any signed-in user could list every agent-terminal session, read
one, run commands in it, approve its pending command as anyone they named, take
control of it, and answer or redirect its host selection. Here every route is
exercised as the owner (alice), a second non-admin user (bob) and an admin,
against sessions that are owned, unowned (recorded before the change) or
missing. The decision routes also get a negative control per non-human
credential kind, resolved by production code (tests/security/credential_harness).
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import api.agent_terminal as terminal_api
import api.agent_terminal_access as access
import api.agent_terminal_host_selection as host_selection
import api.security as security_api
import api.websockets as websockets_api
from api.user_management.human_decider import HUMAN_DECISION_REQUIRED
from constants.error_constants import ERR_SESSION_NOT_FOUND
from services.agent_terminal.models import AgentTerminalSession
from services.command_approval_manager import AgentRole
from tests.security.credential_harness import (
    ASYNC_ROUTE_EXPECTED,
    REFUSED_BY_HUMAN_CHECK,
    credentials,
    install_real_resolution,
)

ALICE = {"username": "alice", "role": "user", "auth_method": "session"}  # the harness's HUMAN, too
BOB = {"username": "bob", "role": "user", "auth_method": "session"}
ADMIN = {"username": "root", "role": "admin", "auth_method": "session"}
#: The internal service key's real shape: an admin, but not a person.
SERVICE_KEY = {"username": "service:slm", "role": "admin", "service": True}

#: Route -> (method, url, body, the service method that runs only if the caller got through).
SESSION_ROUTES = {
    "get": ("GET", "/api/agent-terminal/sessions/{sid}", None, "get_session_info"),
    "delete": ("DELETE", "/api/agent-terminal/sessions/{sid}", None, "close_session"),
    "execute": ("POST", "/api/agent-terminal/execute?session_id={sid}", {"command": "ls"}, "execute_command"),
    "approve": ("POST", "/api/agent-terminal/sessions/{sid}/approve", {"approved": True}, "approve_command"),
    "interrupt": ("POST", "/api/agent-terminal/sessions/{sid}/interrupt", None, "user_interrupt"),
    "resume": ("POST", "/api/agent-terminal/sessions/{sid}/resume", None, "agent_resume"),
}
DECISION_ROUTES = ("approve", "interrupt")


def _session(session_id: str, owner, pty: str) -> AgentTerminalSession:
    return AgentTerminalSession(
        session_id=session_id,
        agent_id="agent-1",
        agent_role=AgentRole.CHAT_AGENT,
        conversation_id="conv-1",
        pty_session_id=pty,
        owner=owner,
    )


class _FakeService:
    """The AgentTerminalService surface these routes use; each call is an AsyncMock to await-check."""

    def __init__(self):
        self.sessions = {
            "s-alice": _session("s-alice", "alice", "pty-alice"),
            "s-legacy": _session("s-legacy", None, "pty-legacy"),  # recorded before owners were stamped
        }
        self.get_session_info = AsyncMock(return_value={"session_id": "s"})
        self.close_session = AsyncMock(return_value=True)
        self.execute_command = AsyncMock(return_value={"status": "success"})
        self.approve_command = AsyncMock(return_value={"status": "approved"})
        self.user_interrupt = AsyncMock(return_value={"status": "success"})
        self.agent_resume = AsyncMock(return_value={"status": "success"})

    async def get_session(self, session_id):
        return self.sessions.get(session_id)

    async def list_sessions(self, agent_id=None, conversation_id=None):
        return list(self.sessions.values())


def _command(command_id: str, terminal_session_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        command_id=command_id,
        terminal_session_id=terminal_session_id,
        chat_id="conv-1",
        command="whoami",
        purpose=None,
        state=SimpleNamespace(value="completed"),
        output="secret output",
        stderr="",
        return_code=0,
        risk_level=SimpleNamespace(value="safe"),
        risk_reasons=[],
        requested_at=None,
        approved_at=None,
        execution_started_at=None,
        execution_completed_at=None,
        approved_by_user_id=None,
        approval_comment=None,
    )


@pytest.fixture
def terminal(monkeypatch):
    service = _FakeService()
    identity = SimpleNamespace(user=dict(ALICE))
    commands = {
        "c-alice": _command("c-alice", "pty-alice"),
        "c-legacy": _command("c-legacy", "pty-legacy"),
        "c-orphan": _command("c-orphan", "pty-gone"),  # its session is no longer in memory
    }
    queue = SimpleNamespace(get_command=AsyncMock(side_effect=lambda cid: commands.get(cid)))
    monkeypatch.setattr(terminal_api, "get_command_queue", lambda: queue)
    monkeypatch.setattr(host_selection, "_pending_host_selections", {})
    monkeypatch.setattr(access, "logger", MagicMock())
    app = FastAPI()
    app.include_router(terminal_api.router, prefix="/api")
    app.dependency_overrides[access.get_current_user] = lambda: identity.user
    app.dependency_overrides[access.get_agent_terminal_service] = lambda: service
    return SimpleNamespace(client=TestClient(app), service=service, identity=identity, app=app)


def _call(terminal, route: str, session_id: str, as_user: dict, body=None):
    method, url, default_body, _ = SESSION_ROUTES[route]
    terminal.identity.user = dict(as_user)
    payload = body if body is not None else default_body
    return terminal.client.request(method, url.format(sid=session_id), json=payload)


def _ran(terminal, route: str) -> AsyncMock:
    return getattr(terminal.service, SESSION_ROUTES[route][3])


# --- every session route: owner, second user, admin, unowned, missing ----------


def test_every_session_scoped_route_is_in_the_table():
    """A session route added later fails here until it is given the ownership check and a row above."""
    scoped = {
        (method, route.path)
        for route in terminal_api.router.routes
        if isinstance(route, APIRoute)
        and "session_id" in {p.name for p in route.dependant.path_params + route.dependant.query_params}
        for method in route.methods
    }
    tabled = {
        (m, "/" + u.split("/api/", 1)[1].split("?")[0].replace("{sid}", "{session_id}"))
        for m, u, _, _ in SESSION_ROUTES.values()
    }
    assert scoped == tabled


@pytest.mark.parametrize("route", sorted(SESSION_ROUTES))
def test_a_second_user_is_refused_on_every_session_route(terminal, route):
    response = _call(terminal, route, "s-alice", BOB)

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == ERR_SESSION_NOT_FOUND
    _ran(terminal, route).assert_not_awaited()


@pytest.mark.parametrize("route", sorted(SESSION_ROUTES))
@pytest.mark.parametrize("who", [ALICE, ADMIN], ids=["owner", "admin"])
def test_the_owner_and_an_admin_get_through(terminal, route, who):
    response = _call(terminal, route, "s-alice", who)

    assert response.status_code == 200, response.text
    _ran(terminal, route).assert_awaited()


@pytest.mark.parametrize("route", sorted(SESSION_ROUTES))
def test_a_session_with_no_recorded_owner_is_admin_only(terminal, route):
    assert _call(terminal, route, "s-legacy", ALICE).status_code == 404
    _ran(terminal, route).assert_not_awaited()
    assert _call(terminal, route, "s-legacy", ADMIN).status_code == 200


@pytest.mark.parametrize("route", sorted(SESSION_ROUTES))
def test_someone_elses_session_and_a_missing_one_answer_alike(terminal, route):
    foreign = _call(terminal, route, "s-alice", BOB)
    missing = _call(terminal, route, "s-missing", BOB)

    assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())


def test_execute_without_a_session_is_refused_before_anything_runs(terminal):
    """``session_id`` was optional on the handler; the ownership check now requires it."""
    response = terminal.client.post("/api/agent-terminal/execute", json={"command": "ls"})

    assert response.status_code == 422, response.text
    terminal.service.execute_command.assert_not_awaited()


# --- decisions: a person, recorded as the verified caller ----------------------


@pytest.mark.parametrize("route", DECISION_ROUTES)
def test_a_decision_needs_a_person_even_from_an_admin_credential(terminal, route):
    response = _call(terminal, route, "s-alice", SERVICE_KEY)

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == HUMAN_DECISION_REQUIRED
    _ran(terminal, route).assert_not_awaited()
    assert _call(terminal, "get", "s-alice", SERVICE_KEY).status_code == 200  # reading is not deciding


@pytest.mark.parametrize("route", DECISION_ROUTES)
def test_a_body_naming_someone_else_is_recorded_as_the_real_caller(terminal, route):
    body = {"approved": True, "user_id": "mallory"} if route == "approve" else {"user_id": "mallory"}

    assert _call(terminal, route, "s-alice", ALICE, body).status_code == 200
    assert _ran(terminal, route).await_args.kwargs["user_id"] == "alice"
    warned = [call.args for call in access.logger.warning.call_args_list]
    assert any("mallory" in args for args in warned), warned


# --- list and command state -----------------------------------------------------


def _listed(terminal, as_user):
    terminal.identity.user = dict(as_user)
    response = terminal.client.get("/api/agent-terminal/sessions")
    assert response.status_code == 200, response.text
    return response


def test_the_list_shows_only_the_callers_own_sessions(terminal):
    alice = _listed(terminal, ALICE)
    assert [s["session_id"] for s in alice.json()["sessions"]] == ["s-alice"]
    assert alice.json()["total"] == 1
    assert "pty-legacy" not in alice.text

    bob = _listed(terminal, BOB)
    assert bob.json()["total"] == 0
    assert "s-alice" not in bob.text and "pty-alice" not in bob.text

    assert {s["session_id"] for s in _listed(terminal, ADMIN).json()["sessions"]} == {"s-alice", "s-legacy"}


@pytest.mark.parametrize(
    ("command_id", "who", "status"),
    [
        ("c-alice", ALICE, 200),
        ("c-alice", BOB, 404),
        ("c-alice", ADMIN, 200),
        ("c-legacy", ALICE, 404),
        ("c-orphan", ALICE, 404),
        ("c-orphan", ADMIN, 200),
        ("c-missing", ALICE, 404),
    ],
)
def test_command_state_is_readable_only_through_its_session(terminal, command_id, who, status):
    terminal.identity.user = dict(who)
    response = terminal.client.get(f"/api/agent-terminal/commands/{command_id}")

    assert response.status_code == status, response.text
    if status == 404:
        assert "secret output" not in response.text


# --- host selection (#17057) -----------------------------------------------------


def _request_host(terminal, as_user, session_id="s-alice"):
    terminal.identity.user = dict(as_user)
    return terminal.client.post(
        "/api/agent-terminal/host-selection/request", json={"agent_session_id": session_id, "command": "uptime"}
    )


def test_a_host_selection_can_only_be_opened_for_a_session_you_may_act_on(terminal):
    assert _request_host(terminal, BOB).status_code == 404
    assert _request_host(terminal, ALICE, session_id=None).status_code == 404
    assert _request_host(terminal, ALICE).status_code == 200


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("GET", ""), ("POST", "/select?host=target-host"), ("POST", "/cancel")],
    ids=["get", "select", "cancel"],
)
def test_a_second_user_cannot_see_answer_or_cancel_a_host_selection(terminal, method, suffix):
    request_id = _request_host(terminal, ALICE).json()["request_id"]
    url = f"/api/agent-terminal/host-selection/{request_id}{suffix}"

    terminal.identity.user = dict(BOB)
    refused = terminal.client.request(method, url)
    assert refused.status_code == 404, refused.text
    assert host_selection._pending_host_selections[request_id]["status"] == "pending_selection"

    terminal.identity.user = dict(ADMIN)
    assert terminal.client.request(method, url).status_code == 200


@pytest.mark.parametrize("suffix", ["/select?host=target-host", "/cancel"], ids=["select", "cancel"])
def test_answering_a_host_selection_needs_a_person(terminal, suffix):
    request_id = _request_host(terminal, ALICE).json()["request_id"]
    terminal.identity.user = dict(SERVICE_KEY)

    response = terminal.client.post(f"/api/agent-terminal/host-selection/{request_id}{suffix}")

    assert response.status_code == 403
    assert response.json()["detail"] == HUMAN_DECISION_REQUIRED


def test_the_pending_list_hides_other_users_requests(terminal):
    request_id = _request_host(terminal, ALICE).json()["request_id"]
    terminal.identity.user = dict(BOB)

    response = terminal.client.get("/api/agent-terminal/host-selection")

    assert response.json()["pending_count"] == 0
    assert request_id not in response.text


# --- the WebSocket approval path (path 2) ---------------------------------------


def _ws_approve(terminal, monkeypatch, user, data):
    monkeypatch.setattr(access, "get_agent_terminal_service", lambda redis_client=None: terminal.service)
    monkeypatch.setattr(access, "get_redis_client", lambda: None)
    websocket = SimpleNamespace(send_json=AsyncMock())
    asyncio.run(websockets_api._handle_command_approval(websocket, data, user))
    return websocket.send_json.await_args.args[0]


def test_a_websocket_approval_is_recorded_as_the_connected_owner(terminal, monkeypatch):
    sent = _ws_approve(
        terminal, monkeypatch, ALICE, {"terminal_session_id": "s-alice", "approved": True, "user_id": "mallory"}
    )

    assert sent["type"] == "approval_processed"
    assert terminal.service.approve_command.await_args.kwargs["user_id"] == "alice"


@pytest.mark.parametrize(
    "user",
    [BOB, {"username": "alice", "role": "user", "auth_method": "jwt_websocket"}],
    ids=["second_user", "websocket_token_without_login_marker"],
)
def test_a_websocket_approval_is_refused_for_anyone_else(terminal, monkeypatch, user):
    sent = _ws_approve(terminal, monkeypatch, user, {"terminal_session_id": "s-alice", "approved": True})

    assert sent["type"] == "approval_error"
    terminal.service.approve_command.assert_not_awaited()


# --- /api/security/approve-command (path 3) -------------------------------------


@pytest.fixture
def security(monkeypatch):
    identity = SimpleNamespace(user=dict(ADMIN))
    layer = SimpleNamespace(pending_approvals={"cmd-1": object()}, approve_command=MagicMock(), audit_log=MagicMock())
    app = FastAPI()
    app.include_router(security_api.router, prefix="/api/security")
    app.dependency_overrides[security_api.check_admin_permission] = lambda: True
    app.dependency_overrides[security_api.get_current_user] = lambda: identity.user
    app.state.security_layer = layer
    return SimpleNamespace(client=TestClient(app), identity=identity, layer=layer, app=app)


def test_the_security_approval_records_its_admin_approver(security):
    response = security.client.post("/api/security/approve-command", json={"command_id": "cmd-1", "approved": True})

    assert response.status_code == 200, response.text
    security.layer.approve_command.assert_called_once_with("cmd-1", True)
    kwargs = security.layer.audit_log.call_args.kwargs
    assert (kwargs["user"], kwargs["outcome"], kwargs["details"]) == (
        "root",
        "approved",
        {"command_id": "cmd-1", "was_pending": True},
    )


def test_the_security_approval_needs_a_person(security):
    security.identity.user = dict(SERVICE_KEY)

    response = security.client.post("/api/security/approve-command", json={"command_id": "cmd-1", "approved": True})

    assert response.status_code == 403
    assert response.json()["detail"] == HUMAN_DECISION_REQUIRED
    security.layer.approve_command.assert_not_called()
    security.layer.audit_log.assert_not_called()


# --- a negative control per non-human credential kind, real resolution ------------


@pytest.mark.parametrize("path", ["approve", "host_select", "security"])
@pytest.mark.parametrize("kind", sorted(ASYNC_ROUTE_EXPECTED))
def test_every_decision_path_refuses_each_non_human_credential(
    terminal, security, real_auth_middleware, monkeypatch, path, kind
):
    resolution = install_real_resolution(real_auth_middleware, monkeypatch)
    request_id = _request_host(terminal, ALICE).json()["request_id"]
    for app in (terminal.app, security.app):
        app.dependency_overrides[access.get_current_user] = real_auth_middleware.get_current_user
        app.dependency_overrides[security_api.get_current_user] = real_auth_middleware.get_current_user
    resolution.configure(kind)
    client, url, body = {
        "approve": (terminal.client, "/api/agent-terminal/sessions/s-alice/approve", {"approved": True}),
        "host_select": (terminal.client, f"/api/agent-terminal/host-selection/{request_id}/select", None),
        "security": (security.client, "/api/security/approve-command", {"command_id": "cmd-1", "approved": True}),
    }[path]

    response = client.post(url, json=body, headers=credentials()[kind])

    status, refuser = ASYNC_ROUTE_EXPECTED[kind]
    assert response.status_code == status, response.text
    if refuser == REFUSED_BY_HUMAN_CHECK:
        assert response.json()["detail"] == HUMAN_DECISION_REQUIRED
    terminal.service.approve_command.assert_not_awaited()
    security.layer.approve_command.assert_not_called()
    assert host_selection._pending_host_selections[request_id]["status"] == "pending_selection"


@pytest.mark.parametrize("kind", ["login_jwt", "session"])
def test_a_person_gets_through_the_same_resolution(terminal, real_auth_middleware, monkeypatch, kind):
    """The positive control for the table above: the owner's own login decides."""
    resolution = install_real_resolution(real_auth_middleware, monkeypatch)
    terminal.app.dependency_overrides[access.get_current_user] = real_auth_middleware.get_current_user
    resolution.configure(kind)

    response = terminal.client.post(
        "/api/agent-terminal/sessions/s-alice/approve", json={"approved": True}, headers=credentials()[kind]
    )

    assert response.status_code == 200, response.text
    assert terminal.service.approve_command.await_args.kwargs["user_id"] == "alice"
