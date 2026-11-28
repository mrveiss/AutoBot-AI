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

from autobot_shared.client_disconnect import PEER_CLOSED_ERRORS, is_client_disconnect
from autobot_shared.error_boundaries.decorators import with_error_handling


@pytest.mark.parametrize(
    "exc",
    [ClientDisconnect(), WebSocketDisconnect(1001)],
)
def test_peer_closed_signals_are_disconnects(exc):
    assert is_client_disconnect(exc)


def test_reset_counts_only_on_a_send():
    assert is_client_disconnect(ConnectionResetError(), on_send=True)
    assert not is_client_disconnect(ConnectionResetError())


@pytest.mark.parametrize("exc", [anyio.EndOfStream(), anyio.BrokenResourceError()])
def test_anyio_stream_errors_are_disconnects_only_at_the_asgi_boundary(exc):
    assert not is_client_disconnect(exc)
    assert not isinstance(exc, PEER_CLOSED_ERRORS)
    assert not is_client_disconnect(exc, at_boundary=True)  # untagged: an internal stream, a real error
    setattr(exc, "__autobot_client_channel__", True)
    assert is_client_disconnect(exc, at_boundary=True)
    wrapper = RuntimeError("wrapped")
    wrapper.__cause__ = exc
    assert is_client_disconnect(exc, at_boundary=True) and not is_client_disconnect(wrapper, at_boundary=True)


def test_group_qualifies_only_when_every_member_does():
    assert is_client_disconnect(BaseExceptionGroup("g", [ClientDisconnect(), WebSocketDisconnect(1001)]))
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


@pytest.fixture(autouse=True)
def _no_log_flood_suppression(monkeypatch):
    """The flood guard drops a call site's 6th ERROR per window; these tests count ERROR records."""
    from autobot_shared.logging_manager import LogFloodSuppressionFilter

    monkeypatch.setattr(LogFloodSuppressionFilter, "filter", lambda self, record: True)


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
    return _drive_full(app, path)[0]


def _drive_full(app, path: str, scope_type: str = "http", server_receive=None) -> tuple[list, list]:
    """Like ``_drive_asgi`` but also return every message the app sent to the server."""
    import asyncio

    sent: list = []

    delivered = []

    async def receive():
        if server_receive is not None:
            return await server_receive()
        if delivered:  # a live client sends nothing more; block so listeners do not spin
            await asyncio.Event().wait()
        delivered.append(1)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": scope_type,
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
    return escaped, sent


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


def _boundary_app(exc: Exception, *, stream: bool = False) -> FastAPI:
    from fastapi.responses import StreamingResponse

    from autobot_shared.client_disconnect import install_client_disconnect_guard

    app = _app(exc)
    install_client_disconnect_guard(app)
    if stream:

        async def chunks():
            yield b"first"
            raise exc

        @app.get("/stream")
        async def stream_route():
            return StreamingResponse(chunks())

    return app


def test_the_guard_answers_499_when_nothing_was_started(caplog):
    """A recording ``send`` proves the server is never left with 'returned without starting response'."""
    from starlette.middleware.base import BaseHTTPMiddleware

    app = _boundary_app(RuntimeError("unused"))

    async def raising(request, call_next):
        raise ClientDisconnect()

    app.add_middleware(BaseHTTPMiddleware, dispatch=raising)
    with caplog.at_level(logging.DEBUG):
        escaped, sent = _drive_full(app, "/boom")
    assert escaped == []
    assert [m["type"] for m in sent] == ["http.response.start", "http.response.body"]
    assert sent[0]["status"] == 499


def test_the_guard_closes_an_unaccepted_websocket():
    from autobot_shared.client_disconnect import ClientDisconnectGuard

    async def inner(scope, receive, send):
        raise WebSocketDisconnect(1006)

    escaped, sent = _drive_full(ClientDisconnectGuard(inner), "/ws", scope_type="websocket")
    assert escaped == [] and [m["type"] for m in sent] == ["websocket.close"]


def test_a_disconnect_after_the_response_started_is_consumed_through_the_chain(caplog):
    """Starlette wraps it in RuntimeError('...response already started'); the cause is the disconnect."""
    with caplog.at_level(logging.DEBUG):
        escaped, sent = _drive_full(_boundary_app(ClientDisconnect(), stream=True), "/stream")
    assert escaped == []
    assert [m["type"] for m in sent][:1] == ["http.response.start"]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR and r.name == "app_factory"]


def test_a_started_response_with_a_real_cause_still_escapes():
    escaped, _ = _drive_full(_boundary_app(ValueError("real"), stream=True), "/stream")
    assert [type(e) for e in escaped] == [ValueError]


def test_a_group_holding_the_socket_runtime_error_is_classified_with_the_websocket():
    from starlette.websockets import WebSocketState

    group = BaseExceptionGroup("g", [RuntimeError("x"), WebSocketDisconnect(1001)])
    assert is_client_disconnect(group, websocket=_Socket(WebSocketState.DISCONNECTED))
    assert not is_client_disconnect(group, websocket=_Socket(WebSocketState.CONNECTED))


def test_http_boundary_reraises_instead_of_answering_a_200_null_body():
    @with_error_handling(operation="http_group", error_code_prefix="T")
    async def endpoint():
        raise BaseExceptionGroup("g", [ClientDisconnect(), ClientDisconnect()])

    import asyncio

    with pytest.raises(BaseExceptionGroup):
        asyncio.run(endpoint())


def test_http_boundary_treats_an_internal_end_of_stream_as_a_real_error(caplog):
    from fastapi import HTTPException

    @with_error_handling(operation="internal_stream", error_code_prefix="T")
    async def endpoint():
        raise anyio.EndOfStream()

    import asyncio

    with caplog.at_level(logging.DEBUG), pytest.raises(HTTPException):
        asyncio.run(endpoint())
    assert _error_records(caplog)


def test_websocket_handler_end_of_stream_is_an_error_and_error_boundary_retries_and_reports(caplog, monkeypatch):
    """An internal memory-channel EndOfStream inside a websocket handler body is NOT a peer disconnect."""
    import asyncio

    from fastapi import WebSocket

    from autobot_shared.error_boundaries import decorators
    from autobot_shared.error_boundaries.decorators import error_boundary
    from autobot_shared.error_boundaries.types import RecoveryStrategy

    async def no_sleep(_):
        return None

    monkeypatch.setattr(decorators.asyncio, "sleep", no_sleep)
    calls = []

    @error_boundary(component="c", function="ws_body", recovery_strategy=RecoveryStrategy.RETRY, max_retries=2)
    async def body():
        calls.append(1)
        send, receive = anyio.create_memory_object_stream(1)
        send.close()
        await receive.receive()  # raises EndOfStream: an internal channel, not the client

    with caplog.at_level(logging.DEBUG):
        try:
            asyncio.run(body())
        except Exception:  # the boundary may surface an ErrorBoundaryException once recovery is exhausted
            pass
    assert len(calls) == 3
    assert any(r.levelno >= logging.ERROR for r in caplog.records if "error_boundaries" in r.name)

    @with_error_handling(operation="ws_endpoint", error_code_prefix="T")
    async def endpoint(websocket: WebSocket):
        raise anyio.EndOfStream()

    from fastapi import HTTPException

    ws = WebSocket({"type": "websocket", "headers": [], "query_string": b""}, None, None)
    with pytest.raises(HTTPException):
        asyncio.run(endpoint(ws))


def _body_app() -> FastAPI:
    """Real wiring (handlers + guard) with a route that reads the request body and one that fails internally."""
    from fastapi import Request

    from autobot_shared.client_disconnect import install_client_disconnect_guard

    app = _app(RuntimeError("unused"))
    install_client_disconnect_guard(app)

    @app.get("/read")
    async def read(request: Request):
        return len(await request.body())

    @app.get("/internal")
    async def internal():
        send, receive = anyio.create_memory_object_stream(1)
        send.close()
        await receive.receive()  # EndOfStream from a channel that has nothing to do with the client

    return app


async def _receive_raises_end_of_stream():
    raise anyio.EndOfStream()


def test_end_of_stream_from_the_wrapped_receive_is_a_quiet_499(caplog):
    with caplog.at_level(logging.DEBUG):
        escaped, sent = _drive_full(_body_app(), "/read", server_receive=_receive_raises_end_of_stream)
    assert escaped == []
    assert sent[0]["status"] == 499
    assert not _error_records(caplog)


def test_an_internal_end_of_stream_in_an_http_body_escapes_logs_error_and_is_a_500(caplog):
    with caplog.at_level(logging.DEBUG):
        escaped, sent = _drive_full(_body_app(), "/internal")
    assert [type(e) for e in escaped] == [anyio.EndOfStream]
    assert sent[0]["status"] == 500
    assert any(r.exc_info for r in _error_records(caplog))


def test_end_of_stream_from_the_wrapped_websocket_receive_closes_quietly(caplog):
    from autobot_shared.client_disconnect import ClientDisconnectGuard

    async def inner(scope, receive, send):
        await receive()

    with caplog.at_level(logging.DEBUG):
        escaped, sent = _drive_full(
            ClientDisconnectGuard(inner), "/ws", scope_type="websocket", server_receive=_receive_raises_end_of_stream
        )
    assert escaped == [] and [m["type"] for m in sent] == ["websocket.close"]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_an_internal_end_of_stream_in_a_websocket_body_escapes(caplog):
    from autobot_shared.client_disconnect import ClientDisconnectGuard

    async def inner(scope, receive, send):
        stream_send, stream_receive = anyio.create_memory_object_stream(1)
        stream_send.close()
        await stream_receive.receive()

    escaped, sent = _drive_full(ClientDisconnectGuard(inner), "/ws", scope_type="websocket")
    assert [type(e) for e in escaped] == [anyio.EndOfStream] and sent == []


def test_a_runtime_error_raised_inside_a_disconnect_handler_is_not_a_disconnect():
    try:
        try:
            raise ClientDisconnect()
        except ClientDisconnect:
            raise RuntimeError("bug in the handler")  # __context__ only, no `from`
    except RuntimeError as bug:
        from autobot_shared.client_disconnect import is_boundary_disconnect

        assert not is_boundary_disconnect(bug)
        chained = RuntimeError("wrapped")
        chained.__cause__ = ClientDisconnect()
        assert is_boundary_disconnect(chained)


def test_an_oserror_raised_in_the_handler_of_a_tagged_error_escapes_and_logs(caplog):
    from fastapi import Request

    app = _body_app()

    @app.get("/handler-bug")
    async def handler_bug(request: Request):
        try:
            await request.body()
        except OSError:
            open("/nonexistent/autobot-20939", encoding="utf-8")  # FileNotFoundError, context = tagged reset

    async def receive_reset():
        raise ConnectionResetError()

    with caplog.at_level(logging.DEBUG):
        escaped, sent = _drive_full(app, "/handler-bug", server_receive=receive_reset)
    assert [type(e) for e in escaped] == [FileNotFoundError]
    assert sent[0]["status"] == 500
    assert any(r.exc_info for r in _error_records(caplog))


def test_a_runtime_error_in_a_disconnect_handler_escapes_the_stack(caplog):
    app = _body_app()

    @app.get("/ctx-bug")
    async def ctx_bug():
        try:
            raise ClientDisconnect()
        except ClientDisconnect:
            raise RuntimeError("bug in the handler")

    with caplog.at_level(logging.DEBUG):
        escaped, _ = _drive_full(app, "/ctx-bug")
    assert [type(e) for e in escaped] == [RuntimeError]


def test_the_guard_does_not_send_a_second_close():
    from autobot_shared.client_disconnect import ClientDisconnectGuard

    async def inner(scope, receive, send):
        await send({"type": "websocket.close", "code": 4001})  # rejected before accept
        raise WebSocketDisconnect(1006)

    escaped, sent = _drive_full(ClientDisconnectGuard(inner), "/ws", scope_type="websocket")
    assert escaped == [] and [m["type"] for m in sent] == ["websocket.close"]
