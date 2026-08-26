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
- A real handshake on ``/ws/{session_id}``: authenticated owner connects;
  unauthenticated caller, non-owner and unknown ``session_id`` are each
  refused ``1008`` before ``accept()``, with ``caplog`` separating the two
  rejection branches that share one ``close()`` call site.
- A real handshake on ``/ws/ssh/{host_id}``: authenticated admin connects,
  unauthenticated caller is refused before ``accept()``.
- The HTTP routes on the same router still reject a non-admin caller
  (dependency_overrides, in-process -- this needs object identity with the
  live app/router, so it cannot move to a subprocess), including the
  tool-execution routes (#15084).
- Contrast mutation: an isolated router shaped exactly like the reported bug
  (router-level ``Depends`` of a ``Request``-typed callable, owning a
  ``@router.websocket`` route) fails the handshake with the same ``TypeError``
  ``solve_dependencies`` raises; the split-router shape this fix uses does not.

The structural half -- which dependency is attached to which route, read from
a clean subprocess import -- lives in ``terminal_router_dependency_wiring_test.py``
(split out under #14961; it needs none of this module's fixtures).
"""

import logging
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, WebSocket
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.terminal import check_admin_permission
from api.terminal import router as terminal_router
from api.terminal import session_manager, ssh_terminal_manager
from services.terminal_session_store import SessionConfigStore

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


def _request(client, method: str, path: str):
    """Issue *method* at *path*, sending a body only where one is accepted.

    ``TestClient.get()`` takes no ``json=`` -- passing one raises ``TypeError``
    rather than returning a status, which would have read as a routing failure.
    """
    if method == "get":
        return client.get(path)
    return getattr(client, method)(path, json={})


class TestTerminalToolRoutesKeepTheirGate:
    """`api/terminal_tools.py` declares no dependency of its own (#15084):
    those four routes install packages and run system commands, and have only
    ever been protected by inheriting the parent router's admin check.
    Splitting that parent for the WebSocket fix moved every HTTP route onto
    `admin_router` -- and would have handed these to anonymous callers had the
    include site not moved with them.

    Proved through the real ASGI request path, not by introspection. Under
    fastapi 0.141.1 a dependency inherited via ``include_router(dependencies=)``
    is **not** visible on the route object: CI job 98114928835 read an empty
    dependency list for routes that are in fact gated, because the merge happens
    at request-routing time. The prefix is invisible the same way. Asking the
    application what it *serves* is the only question that survives the version
    difference -- and it is the better question anyway.
    """

    #: Full paths as the mounted app serves them. Introspection cannot supply
    #: these under 0.141.1, but a request can, and a wrong path fails loudly as
    #: a 404 rather than silently matching nothing.
    _TOOL_ROUTES = (
        ("post", "/terminal/install-tool"),
        ("post", "/terminal/check-tool"),
        ("post", "/terminal/validate-command"),
        ("get", "/terminal/package-managers"),
    )

    @pytest.mark.parametrize("method,path", _TOOL_ROUTES)
    def test_tool_route_refuses_a_non_admin(self, terminal_app, terminal_client, method, path):
        def _deny():
            raise HTTPException(status_code=403, detail="Admin permission required for this operation")

        terminal_app.dependency_overrides[check_admin_permission] = _deny
        try:
            response = _request(terminal_client, method, path)
        finally:
            terminal_app.dependency_overrides.pop(check_admin_permission, None)

        assert response.status_code == 403, (
            f"{path} runs system commands and has no dependency of its own -- "
            f"it must stay on a router that carries the admin check, got {response.status_code}"
        )

    @pytest.mark.parametrize("method,path", _TOOL_ROUTES)
    def test_tool_route_is_actually_served(self, terminal_app, terminal_client, method, path):
        """Non-vacuity: a 404 would make the refusal test above pass for the
        wrong reason, since an unrouted path never reaches a dependency."""
        terminal_app.dependency_overrides[check_admin_permission] = lambda: True
        try:
            response = _request(terminal_client, method, path)
        finally:
            terminal_app.dependency_overrides.pop(check_admin_permission, None)

        assert response.status_code != 404, f"{path} is not served at all -- the gate test above proves nothing"


class TestTerminalWebsocketRouteHandshake:
    """Real handshake on /ws/{session_id} via TestClient -- not a handler call."""

    @pytest.fixture(autouse=True)
    def _fake_session_store(self, monkeypatch):
        """Back `session_manager` with fakeredis (#14961), never the live Redis.

        `session_configs` is Redis-backed now; this directory's conftest
        stubs `get_redis_client()` to None so unit tests never open a real
        socket, and the store fails closed on that -- so without this, the
        `owned_session_id` fixture below could never write a session.
        """
        fake_client = fakeredis.FakeRedis(server=fakeredis.FakeServer())
        monkeypatch.setattr(session_manager, "session_configs", SessionConfigStore(redis_client=fake_client))

    @pytest.fixture
    def owned_session_id(self):
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
        with _no_ws_credentials(), _accept_spy() as calls:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect(f"/ws/{owned_session_id}"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0

    def test_authenticated_non_owner_is_refused(self, terminal_client, owned_session_id, caplog):
        """#14960 AC2 at route level: a non-owner is refused 1008 before accept().
        caplog pins the ownership branch; #14961's unknown-session branch also closes 1008."""
        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "mallory"})),
            caplog.at_level(logging.WARNING, logger="api.terminal"),
            _accept_spy() as calls,
        ):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect(f"/ws/{owned_session_id}"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0
        assert any("is not the owner" in r.message for r in caplog.records)
        assert not any("unknown session_id" in r.message for r in caplog.records)

    def test_unknown_session_is_refused(self, terminal_client, owned_session_id, caplog):
        """#14961 AC4: the unknown-session rejection, driven through the real route.

        The sibling case in ``terminal_websocket_auth_test.py`` calls the
        decorated handler directly, which cannot observe a routing or
        dependency-resolution failure -- exactly how #14998 stayed invisible
        while this route 500'd for every caller and the handler-level guard
        tests stayed green. A criterion about what a client experiences has to
        go through the ASGI stack.

        ``owned_session_id`` is requested purely as a non-vacuity witness. The
        config store is Redis-backed (``services/terminal_session_store.py``)
        and **fails closed**, so an unreachable store answers every lookup with
        ``None`` and would produce this same ``1008`` for entirely the wrong
        reason. Reading that session back proves the fakeredis-backed store is
        live and round-trips, which makes the miss below a genuine absence.

        The ``caplog`` pair is the load-bearing part: the unknown-session and
        ownership branches both exit through the one ``close(code=1008)`` in
        ``terminal_websocket``, so the close code alone cannot tell them apart,
        and a regression that turned "unknown" into "not the owner" would pass
        silently. The non-owner test above pins the mirror direction.
        """
        unknown_session_id = str(uuid.uuid4())
        assert session_manager.session_configs.get(owned_session_id) is not None, (
            "the session store is not round-tripping -- a fail-closed store makes "
            "every session look unknown and this test would pass vacuously"
        )
        assert session_manager.session_configs.get(unknown_session_id) is None

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "alice"})),
            patch("api.terminal._init_terminal_handler", new=AsyncMock()) as init_handler,
            caplog.at_level(logging.WARNING, logger="api.terminal"),
            _accept_spy() as calls,
        ):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect(f"/ws/{unknown_session_id}"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0, "the handshake must be refused before accept()"
        init_handler.assert_not_awaited()
        assert any("unknown session_id" in r.message for r in caplog.records)
        assert not any("is not the owner" in r.message for r in caplog.records)


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
    without depending on this test harness's always-pass auth stub. Stays
    in-process (unlike the structural checks above): dependency_overrides
    needs object identity with the live app/router under test.
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
