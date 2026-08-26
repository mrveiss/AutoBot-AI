# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Route-level guard tests for the terminal WebSocket 500 (#14998).

``terminal_websocket_auth_test.py`` and ``ssh_terminal_websocket_auth_test.py``
call the decorated handler *functions* directly (``await terminal_websocket(ws,
session_id)``). That bypasses FastAPI's routing and dependency-resolution layer
entirely, so neither file could ever have caught #14998: a router-level
``Depends(check_admin_permission)`` (``Request``-typed) 500s the handshake
inside ``solve_dependencies``, before the handler is ever invoked -- a failure
mode a handler-direct call cannot reach. This file drives the routes the way a
real client does, through ``starlette.testclient.TestClient``, which runs the
actual ASGI app including route matching and dependency resolution.

Covers:
- Structural proof the merged router puts ``check_admin_permission`` on the
  HTTP routes and NOT on either ``@router.websocket`` route (the fix itself).
- A real handshake on ``/ws/{session_id}``: authenticated owner connects,
  unauthenticated caller is refused before ``accept()``.
- A real handshake on ``/ws/ssh/{host_id}``: authenticated admin connects,
  unauthenticated caller is refused before ``accept()``.
- The HTTP routes on the same router still reject a non-admin caller.
- Contrast mutation: an isolated router shaped exactly like the reported bug
  (router-level ``Depends`` of a ``Request``-typed callable, owning a
  ``@router.websocket`` route) fails the handshake with the same ``TypeError``
  ``solve_dependencies`` raises; the split-router shape this fix uses does not.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, WebSocket
from starlette.testclient import TestClient

from api.terminal import check_admin_permission
from api.terminal import router as terminal_router
from api.terminal import session_manager, ssh_terminal_manager

_original_accept = WebSocket.accept


async def _spy_accept(self, *args, **kwargs):
    """A real function (not a Mock) so instance attribute lookup binds ``self``
    the normal descriptor way -- see #14998 investigation notes. Records every
    call and still performs the real accept so the "connects" tests observe a
    genuine handshake, not a short-circuited one.
    """
    _spy_accept.calls.append(self)
    return await _original_accept(self, *args, **kwargs)


_spy_accept.calls = []


@contextmanager
def _accept_spy():
    _spy_accept.calls = []
    with patch.object(WebSocket, "accept", new=_spy_accept):
        yield _spy_accept.calls


@contextmanager
def _no_ws_credentials():
    """See api/terminal_websocket_auth_test.py::_no_ws_credentials -- same
    union of credential sources must be closed off for "unauthenticated".
    """
    with (
        patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=None)),
        patch("auth_middleware.verify_internal_api_key", return_value=False),
        patch("auth_middleware.get_auth_middleware") as mock_get_auth_middleware,
    ):
        mock_get_auth_middleware.return_value.get_user_from_request.return_value = None
        yield


@pytest.fixture
def terminal_app():
    """A real FastAPI app mounting the production terminal router, exactly as
    ``initialization/router_registry/terminal_routers.py`` does (minus the
    ``/api/terminal`` prefix, irrelevant to dependency resolution).
    """
    app = FastAPI()
    app.include_router(terminal_router)
    return app


@pytest.fixture
def terminal_client(terminal_app):
    return TestClient(terminal_app, raise_server_exceptions=False)


def _ws_route(path: str):
    matches = [r for r in terminal_router.routes if getattr(r, "path", None) == path]
    assert len(matches) == 1, f"expected exactly one route for {path}, found {len(matches)}"
    return matches[0]


class TestTerminalRouterDependencyWiring:
    """Structural proof of the fix: the admin dependency moved off the WS
    routes and stayed on the HTTP ones. This is the assertion #14998 itself
    is about -- independent of any test-harness auth stub, since it compares
    against ``api.terminal.check_admin_permission`` by identity rather than
    exercising its behaviour.
    """

    def test_websocket_routes_carry_no_admin_dependency(self):
        for path in ("/ws/{session_id}", "/ws/ssh/{host_id}"):
            route = _ws_route(path)
            deps = [d.dependency for d in route.dependencies]
            assert check_admin_permission not in deps, f"{path} must not carry the router-level admin Depends"

    def test_http_routes_keep_the_admin_dependency(self):
        route = _ws_route("/")
        deps = [d.dependency for d in route.dependencies]
        assert check_admin_permission in deps, "HTTP routes must keep check_admin_permission"


class TestTerminalWebsocketRouteHandshake:
    """Real handshake on /ws/{session_id} via TestClient -- not a handler call."""

    @pytest.fixture
    def owned_session_id(self):
        import uuid

        session_id = str(uuid.uuid4())
        session_manager.session_configs[session_id] = {
            "session_id": session_id,
            "owner": "alice",
            "security_level": "standard",
        }
        yield session_id
        session_manager.session_configs.pop(session_id, None)

    def test_authenticated_owner_connects(self, terminal_client, owned_session_id):
        """#14960 AC3, made checkable: the real route accepts the owner."""
        fake_terminal = MagicMock()
        fake_terminal.cleanup = AsyncMock()

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "alice"})),
            patch("api.terminal._init_terminal_handler", new=AsyncMock(return_value=fake_terminal)),
            patch("api.terminal._run_terminal_message_loop", new=AsyncMock()),
            _accept_spy() as calls,
        ):
            with terminal_client.websocket_connect(f"/ws/{owned_session_id}") as ws:
                pass

        assert len(calls) == 1

    def test_unauthenticated_caller_is_refused_not_500(self, terminal_client, owned_session_id):
        """#14998: before the fix this handshake 500s inside solve_dependencies
        for EVERY caller, admin or not. After the fix, an unauthenticated
        caller reaches the explicit per-route guard and is refused cleanly.
        """
        from starlette.websockets import WebSocketDisconnect

        with _no_ws_credentials(), _accept_spy() as calls:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect(f"/ws/{owned_session_id}"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0


class TestSshTerminalWebsocketRouteHandshake:
    """Real handshake on /ws/ssh/{host_id} via TestClient -- not a handler call."""

    def test_authenticated_admin_connects(self, terminal_client):
        fake_terminal = MagicMock()
        fake_terminal.start = AsyncMock(return_value=False)

        with (
            patch(
                "auth_middleware.authenticate_websocket",
                new=AsyncMock(return_value={"username": "admin-bob", "role": "admin"}),
            ),
            patch("api.terminal._setup_ssh_terminal", new=AsyncMock(return_value=fake_terminal)),
            patch.object(ssh_terminal_manager, "close_session", new=AsyncMock()),
            _accept_spy() as calls,
        ):
            with terminal_client.websocket_connect("/ws/ssh/prod-host-1") as ws:
                pass

        assert len(calls) == 1

    def test_unauthenticated_caller_is_refused_not_500(self, terminal_client):
        from starlette.websockets import WebSocketDisconnect

        with _no_ws_credentials(), _accept_spy() as calls:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect("/ws/ssh/prod-host-1"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0


class TestTerminalHttpRouteAdminGate:
    """The HTTP routes on this router keep check_admin_permission, exercised
    through the real ASGI request path via FastAPI's dependency_overrides --
    the standard way to prove a specific dependency actually gates a route
    without depending on this test harness's always-pass auth stub.
    """

    def test_non_admin_is_rejected(self, terminal_app, terminal_client):
        def _deny():
            raise HTTPException(status_code=403, detail="Admin permission required for this operation")

        terminal_app.dependency_overrides[check_admin_permission] = _deny
        try:
            response = terminal_client.get("/")
        finally:
            terminal_app.dependency_overrides.pop(check_admin_permission, None)

        assert response.status_code == 403

    def test_admin_reaches_the_handler(self, terminal_app, terminal_client):
        terminal_app.dependency_overrides[check_admin_permission] = lambda: True
        try:
            response = terminal_client.get("/")
        finally:
            terminal_app.dependency_overrides.pop(check_admin_permission, None)

        assert response.status_code == 200


class TestRouterLevelDependsBreaksWebSocketScope:
    """Contrast mutation (#14998): reproduces the reported cause in isolation,
    with a genuinely ``Request``-typed dependency (the test harness's
    ``auth_middleware`` stub deliberately uses a no-arg signature to dodge an
    unrelated FastAPI validation issue -- #10472 -- so it can't reproduce this
    one). Proves both that the broken shape fails, and that the shape this fix
    uses does not.
    """

    @staticmethod
    def _admin_dep(request: Request) -> bool:
        return True

    def test_router_level_request_typed_depends_breaks_the_handshake(self):
        """The exact shape #14998 reports: one router, dependencies=[...] at
        construction, owning a @router.websocket route. Mirrors terminal.py
        before this fix.
        """
        broken_router = APIRouter(dependencies=[Depends(self._admin_dep)])

        @broken_router.websocket("/ws/broken")
        async def _ws_broken(websocket: WebSocket):
            await websocket.accept()
            await websocket.close()

        app = FastAPI()
        app.include_router(broken_router)
        client = TestClient(app, raise_server_exceptions=False)

        with pytest.raises(TypeError):
            with client.websocket_connect("/ws/broken"):
                pass

    def test_split_router_shape_does_not_break_the_handshake(self):
        """The shape this fix uses: the WS route stays on a router carrying no
        dependencies; the same admin Depends only reaches an HTTP-only router
        merged in afterward. Mirrors terminal.py's router/admin_router split.
        """
        plain_router = APIRouter()
        admin_router = APIRouter(dependencies=[Depends(self._admin_dep)])

        @plain_router.websocket("/ws/fixed")
        async def _ws_fixed(websocket: WebSocket):
            await websocket.accept()
            await websocket.close()

        @admin_router.get("/http-fixed")
        def _http_fixed():
            return {"ok": True}

        plain_router.include_router(admin_router)

        app = FastAPI()
        app.include_router(plain_router)
        client = TestClient(app, raise_server_exceptions=False)

        with client.websocket_connect("/ws/fixed"):
            pass
