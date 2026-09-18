# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Nine WebSocket endpoints authenticate before accepting; long-running routes are admin-only (#17009, #17010).

Each endpoint is mounted on a bare app and connected to through Starlette's
TestClient, with the real ``open_authenticated_ws`` in the path. Only credential
resolution (``_resolve_ws_user``) is stood in for, so origin, authentication, the
admin check, the per-endpoint ``allow`` and the accept all run for real. A socket
closed before it is accepted raises ``WebSocketDisconnect`` on connect; one that
was accepted does not.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

USER = {"username": "alice", "user_id": "u-alice", "role": "user"}
ADMIN = {"username": "root", "user_id": "u-root", "role": "admin"}


def _connect(router, path: str, caller):
    app = FastAPI()
    app.include_router(router)
    with patch("api.ws_security._resolve_ws_user", new=AsyncMock(return_value=caller)):
        with TestClient(app).websocket_connect(path):
            return "accepted"


def _refused(router, path: str, caller) -> int:
    with pytest.raises(WebSocketDisconnect) as closed:
        _connect(router, path, caller)
    return closed.value.code


def _routers():
    from api import analytics, analytics_quality, knowledge_research_ws, logs, monitoring

    return {
        "analytics realtime": (analytics.router, "/ws/realtime", False),
        "analytics live": (analytics.router, "/ws/analytics/live", False),
        "quality": (analytics_quality.router, "/ws", True),
        "knowledge research": (knowledge_research_ws.router, "/ws/knowledge/research", False),
        "log tail": (logs.router, "/tail/backend.log", True),
        "monitoring": (monitoring.router, "/realtime", False),
    }


CASES = ["analytics realtime", "analytics live", "quality", "knowledge research", "log tail", "monitoring"]


@pytest.mark.parametrize("name", CASES)
def test_an_unauthenticated_client_is_refused_before_accept(name):
    router, path, _admin = _routers()[name]
    assert _refused(router, path, None) == 1008


@pytest.mark.parametrize("name", CASES)
def test_the_right_caller_is_accepted(name):
    router, path, admin = _routers()[name]
    with patch("api.analytics_quality.get_quality_snapshot", new=AsyncMock(return_value={})):  # no scan in a test
        assert _connect(router, path, ADMIN if admin else USER) == "accepted"


@pytest.mark.parametrize("name", ["quality", "log tail"])
def test_a_non_admin_is_refused_where_the_rest_twin_is_admin_only(name):
    router, path, _admin = _routers()[name]
    assert _refused(router, path, USER) == 1008


@pytest.fixture
def operations(monkeypatch):
    """The long-running module with its framework present and one operation of nobody's."""
    from api import long_running_operations as lro

    manager = MagicMock(websocket_connections={})
    manager.operation_manager.get_operation.return_value = None
    monkeypatch.setattr(lro, "_OPERATIONS_AVAILABLE", True)
    monkeypatch.setattr(lro, "operation_integration_manager", manager)
    return lro


def test_operation_progress_is_admin_only(operations):
    """#17009 row 8: operations record no creator, so another user's progress is an admin's alone."""
    assert _refused(operations.router, "/op-1/progress", None) == 1008
    assert _refused(operations.router, "/op-1/progress", USER) == 1008
    assert _connect(operations.router, "/op-1/progress", ADMIN) == "accepted"


def test_every_long_running_http_route_requires_admin():
    """#17010: each HTTP route carries the admin dependency; none is left open."""
    from api import long_running_operations as lro
    from auth_middleware import check_admin_permission

    http = [r for r in lro.router.routes if hasattr(r, "methods")]
    assert len(http) >= 9, f"found {len(http)} HTTP routes; this check would pass on an empty router"
    open_routes = [r.path for r in http if check_admin_permission not in {d.call for d in r.dependant.dependencies}]
    assert open_routes == []


class TestTheOverseerSocket:
    """#17009 row 2: it runs commands in the session's PTY, so it needs the session's owner."""

    def _router(self):
        from api import overseer_handlers

        return overseer_handlers

    def test_unauthenticated_is_refused(self):
        module = self._router()
        assert _refused(module.router, "/ws/s-1", None) == 1008

    def test_another_users_session_is_refused(self):
        module = self._router()
        with patch.object(module, "owns_chat_session", new=AsyncMock(return_value=False)):
            assert _refused(module.router, "/ws/s-1", USER) == 1008

    def test_the_owner_is_accepted(self):
        module = self._router()
        with patch.object(module, "owns_chat_session", new=AsyncMock(return_value=True)):
            assert _connect(module.router, "/ws/s-1", USER) == "accepted"


class TestOwnsChatSession:
    """The ownership check itself: strict, never degraded to log-only."""

    @pytest.fixture
    def owners(self):
        from api import ws_security

        redis_owner, durable_owner = MagicMock(), MagicMock()
        validator = MagicMock()
        validator.return_value.get_session_owner = AsyncMock(side_effect=lambda _s: redis_owner.value)
        manager = MagicMock(get_session_owner=AsyncMock(side_effect=lambda _s: durable_owner.value))
        with (
            patch("security.session_ownership.SessionOwnershipValidator", validator),
            patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()),
            patch("utils.chat_utils.get_chat_history_manager", return_value=manager),
        ):
            yield ws_security.owns_chat_session, redis_owner, durable_owner

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("redis_value", "durable_value", "caller", "expected"),
        [
            ("alice", None, USER, True),
            (None, "alice", USER, True),
            ("bob", None, USER, False),
            (None, None, USER, False),
            ("bob", None, ADMIN, True),
        ],
        ids=["owner via Redis", "owner via the session file", "another user's", "unowned", "admin"],
    )
    async def test_ownership(self, owners, redis_value, durable_value, caller, expected):
        owns, redis_owner, durable_owner = owners
        redis_owner.value, durable_owner.value = redis_value, durable_value
        assert await owns(SimpleNamespace(app=None), "s-1", caller) is expected


class TestTheWorkflowSocket:
    """#17009 row 3: no check at all before; any caller took any slot and steered any workflow."""

    def _manager(self, owner_id=None):
        from services.workflow_automation.messaging import WorkflowMessenger

        workflow = SimpleNamespace(owner_id=owner_id)
        return SimpleNamespace(
            messenger=WorkflowMessenger(),
            active_workflows={"wf-1": workflow},
            handle_workflow_control=AsyncMock(),
        )

    def test_a_slot_held_by_another_user_is_refused_and_its_socket_kept(self):
        messenger = self._manager().messenger
        theirs, mine = object(), object()
        assert messenger.claim_session("s-1", theirs, "bob")

        assert not messenger.claim_session("s-1", mine, "alice")
        assert messenger.terminal_sessions["s-1"] is theirs
        assert messenger.claim_session("s-1", mine, "bob")  # the holder may reconnect

    def test_a_stale_socket_never_frees_a_newer_one(self):
        messenger = self._manager().messenger
        old, new = object(), object()
        messenger.claim_session("s-1", old, "bob")
        messenger.claim_session("s-1", new, "bob")

        messenger.release_session("s-1", old)

        assert messenger.terminal_sessions["s-1"] is new

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("owner_id", "caller", "allowed"),
        [(None, USER, False), ("u-bob", USER, False), ("u-alice", USER, True), (None, ADMIN, True)],
        ids=["no owner recorded", "another user's", "its owner", "admin"],
    )
    async def test_control_is_for_the_owner_or_an_admin(self, owner_id, caller, allowed):
        from services.workflow_automation import ws_endpoint

        manager, websocket = self._manager(owner_id), MagicMock(send_json=AsyncMock())
        message = {"type": "automation_control", "workflow_id": "wf-1", "action": "approve_step"}

        await ws_endpoint._control(websocket, manager, message, caller)

        assert manager.handle_workflow_control.await_count == (1 if allowed else 0)
        if not allowed:
            assert websocket.send_json.await_args.args[0]["type"] == "automation_control_refused"

    def test_unauthenticated_is_refused_before_accept(self):
        from services.workflow_automation import routes

        assert _refused(routes.router, "/workflow_ws/s-1", None) == 1008

    def test_an_authenticated_caller_is_accepted(self):
        from services.workflow_automation import routes

        assert _connect(routes.router, "/workflow_ws/s-1", USER) == "accepted"
