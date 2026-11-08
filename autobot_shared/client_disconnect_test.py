# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Client disconnects are expected events, real errors stay errors (#20939)."""

import logging

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect
from starlette.websockets import WebSocketDisconnect

from autobot_shared.client_disconnect import is_client_disconnect
from autobot_shared.error_boundaries.decorators import with_error_handling


@pytest.mark.parametrize(
    "exc",
    [ClientDisconnect(), WebSocketDisconnect(1001), anyio.EndOfStream(), anyio.BrokenResourceError()],
)
def test_peer_closed_signals_are_disconnects(exc):
    assert is_client_disconnect(exc)


def test_reset_counts_only_on_a_send():
    assert is_client_disconnect(ConnectionResetError(), on_send=True)
    assert not is_client_disconnect(ConnectionResetError())


def test_group_qualifies_only_when_every_member_does():
    assert is_client_disconnect(BaseExceptionGroup("g", [ClientDisconnect(), anyio.EndOfStream()]))
    assert not is_client_disconnect(BaseExceptionGroup("g", [ClientDisconnect(), ValueError("x")]))


def _app(exc: Exception) -> FastAPI:
    import sys
    from pathlib import Path

    backend = str(Path(__file__).resolve().parents[1] / "autobot-backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app_factory import _register_exception_handlers

    app = FastAPI()
    _register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise exc

    return app


def _error_records(caplog):
    # Importing app_factory logs unrelated start-up errors; only the code under test counts.
    own = ("app_factory", "autobot_shared.error_boundaries.decorators")
    return [r for r in caplog.records if r.levelno >= logging.ERROR and r.name in own]


def test_http_disconnect_logs_no_error_and_builds_no_500(caplog):
    client = TestClient(_app(ClientDisconnect()), raise_server_exceptions=False)
    with caplog.at_level(logging.DEBUG):
        resp = client.get("/boom")
    assert resp.status_code == 499 and resp.content == b""
    assert not _error_records(caplog)


def test_a_real_error_still_logs_at_error_with_a_traceback(caplog):
    client = TestClient(_app(ValueError("real")), raise_server_exceptions=False)
    with caplog.at_level(logging.DEBUG):
        resp = client.get("/boom")
    assert resp.status_code == 500
    assert any(r.exc_info for r in _error_records(caplog))


def test_websocket_disconnect_in_a_boundary_ends_quietly(caplog):
    @with_error_handling(operation="ws_op", error_code_prefix="T")
    async def endpoint():
        raise WebSocketDisconnect(1006)

    import asyncio

    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(endpoint()) is None
    assert not _error_records(caplog)


def test_boundary_reraises_an_http_disconnect_unlogged_as_error(caplog):
    @with_error_handling(operation="http_op", error_code_prefix="T")
    async def endpoint():
        raise ClientDisconnect()

    import asyncio

    with caplog.at_level(logging.DEBUG), pytest.raises(ClientDisconnect):
        asyncio.run(endpoint())
    assert not _error_records(caplog)


def test_boundary_still_converts_a_real_error_and_logs_it(caplog):
    from fastapi import HTTPException

    @with_error_handling(operation="real_op", error_code_prefix="T")
    async def endpoint():
        raise RuntimeError("real")

    import asyncio

    with caplog.at_level(logging.DEBUG), pytest.raises(HTTPException):
        asyncio.run(endpoint())
    assert _error_records(caplog)


def _drive_asgi(app: FastAPI, path: str) -> list:
    """Run one request through the whole ASGI stack; return what escaped to the server."""
    import asyncio

    sent: list = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    escaped: list = []

    async def run():
        try:
            await app(scope, receive, send)
        except BaseException as exc:  # what the ASGI server (uvicorn) would log as an error
            escaped.append(exc)

    asyncio.run(run())
    return escaped


def test_a_disconnect_does_not_escape_the_asgi_stack_to_the_server(caplog):
    """uvicorn logs anything that escapes the app at ERROR ("Exception in ASGI application")."""
    with caplog.at_level(logging.DEBUG):
        escaped = _drive_asgi(_app(ClientDisconnect()), "/boom")
    assert escaped == []
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR and r.name in ("app_factory", "uvicorn.error")]


def test_a_real_error_still_escapes_the_asgi_stack_control():
    assert [type(e) for e in _drive_asgi(_app(ValueError("real")), "/boom")] == [ValueError]


def test_sync_boundary_handles_a_disconnect_like_the_async_one(caplog):
    @with_error_handling(operation="sync_ws", error_code_prefix="T")
    def endpoint():
        raise WebSocketDisconnect(1006)

    with caplog.at_level(logging.DEBUG):
        assert endpoint() is None
    assert not _error_records(caplog)


def test_error_boundary_neither_retries_nor_reports_a_disconnect(caplog):
    import asyncio

    from autobot_shared.error_boundaries.decorators import error_boundary
    from autobot_shared.error_boundaries.types import RecoveryStrategy

    calls = []

    @error_boundary(component="c", function="f", recovery_strategy=RecoveryStrategy.RETRY, max_retries=3)
    async def endpoint():
        calls.append(1)
        raise ClientDisconnect()

    with caplog.at_level(logging.DEBUG), pytest.raises(ClientDisconnect):
        asyncio.run(endpoint())
    assert calls == [1]
    assert not _error_records(caplog)


def test_handle_error_reraises_a_disconnect_unchanged():
    import asyncio

    from autobot_shared.error_boundaries.boundary_manager import get_error_boundary_manager
    from autobot_shared.error_boundaries.types import ErrorContext

    exc = WebSocketDisconnect(1001)
    ctx = ErrorContext(component="c", function="f", args=(), kwargs={})
    with pytest.raises(WebSocketDisconnect) as info:
        asyncio.run(get_error_boundary_manager().handle_error(exc, ctx))
    assert info.value is exc


class _Socket:
    def __init__(self, client_state, application_state=None):
        self.client_state = client_state
        self.application_state = application_state or client_state


def test_receive_after_disconnect_is_classified_by_socket_state_not_text():
    from starlette.websockets import WebSocketState

    err = RuntimeError("anything at all")
    assert is_client_disconnect(err, websocket=_Socket(WebSocketState.DISCONNECTED))
    assert is_client_disconnect(err, websocket=_Socket(WebSocketState.CONNECTED, WebSocketState.DISCONNECTED))


def test_the_same_runtime_error_on_a_live_socket_stays_an_error():
    from starlette.websockets import WebSocketState

    err = RuntimeError('Cannot call "receive" once a disconnect message has been received.')
    assert not is_client_disconnect(err, websocket=_Socket(WebSocketState.CONNECTED))
    assert not is_client_disconnect(err)


def _middleware_app(exc: Exception) -> FastAPI:
    """The real app wiring plus an outermost-user middleware that raises ``exc``."""
    from starlette.middleware.base import BaseHTTPMiddleware

    from autobot_shared.client_disconnect import install_client_disconnect_guard

    app = _app(RuntimeError("never reached"))
    install_client_disconnect_guard(app)

    async def raising(request, call_next):
        raise exc

    app.add_middleware(BaseHTTPMiddleware, dispatch=raising)
    return app


def test_a_disconnect_from_an_outer_middleware_is_consumed_quietly(caplog):
    with caplog.at_level(logging.DEBUG):
        escaped = _drive_asgi(_middleware_app(ClientDisconnect()), "/boom")
    assert escaped == []
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR and r.name in ("app_factory", "uvicorn.error")]


def test_a_real_error_from_an_outer_middleware_still_escapes_and_logs(caplog):
    with caplog.at_level(logging.DEBUG):
        escaped = _drive_asgi(_middleware_app(ValueError("real")), "/boom")
    assert [type(e) for e in escaped] == [ValueError]
    assert any(r.levelno >= logging.ERROR and r.name == "app_factory" and r.exc_info for r in caplog.records)
