# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One home for "the client went away" (#20939).

A peer that drops mid-request or mid-handshake is an expected event, not a
server defect. Before this module each catch-all (the app-level handler, the
``with_error_handling`` boundary) logged it as an error with a traceback.
``is_client_disconnect`` is the single classifier; ``log_client_disconnect``
the single log line. Every other exception is left for the caller to handle
unchanged.
"""

import logging

import anyio
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response
from starlette.websockets import WebSocketDisconnect, WebSocketState

# Status for a request whose client left before the answer (nginx's 499); never read by anyone.
CLIENT_CLOSED_REQUEST = 499

# Exceptions Starlette raises only from the client socket itself. Usable directly as an
# ``except`` clause so a handler keeps its own follow-up action.
PEER_CLOSED_ERRORS = (ClientDisconnect, WebSocketDisconnect)
# anyio's stream errors and OS errors are raised by every internal task group, memory
# channel, client session and socket too, so on their own they are real failures. They mean
# a disconnect only when they came out of the client channel: the guard tags an error
# raised by the ``receive`` / ``send`` it hands inward, and only a tagged one counts.
_CHANNEL_ERRORS = (anyio.EndOfStream, anyio.BrokenResourceError, OSError)
_CHANNEL_TAG = "__autobot_client_channel__"
# A reset on a *send* is the peer; the same class from an upstream call (Redis,
# a model server) is a real failure, so it only counts when the caller says so.
_RESET_ON_SEND = (ConnectionResetError, BrokenPipeError)
_CHAIN_DEPTH = 8


def _socket_is_gone(websocket) -> bool:
    """Structural check: either side of the socket has reached DISCONNECTED."""
    return WebSocketState.DISCONNECTED in (
        getattr(websocket, "client_state", None),
        getattr(websocket, "application_state", None),
    )


def _tag_channel_error(exc: BaseException) -> None:
    setattr(exc, _CHANNEL_TAG, True)


def _is_channel_error(exc: BaseException) -> bool:
    """True when ``exc`` or something on its cause/context chain was tagged by the guard."""
    link: BaseException | None = exc
    for _ in range(_CHAIN_DEPTH):
        if link is None:
            return False
        if getattr(link, _CHANNEL_TAG, False):
            return True
        link = link.__cause__ or link.__context__
    return False


def is_client_disconnect(
    exc: BaseException, *, on_send: bool = False, websocket=None, at_boundary: bool = False
) -> bool:
    """True when ``exc`` means the client closed its side of the connection.

    ``on_send`` marks an exception raised while writing to the client socket,
    where ``ConnectionResetError`` / ``BrokenPipeError`` also mean a disconnect.
    ``at_boundary`` marks the ASGI boundary, where an anyio stream error or an
    ``OSError`` also means one, but only if the guard tagged it as raised by the
    client channel (an internal memory channel's ``EndOfStream`` is not). A (nested)
    ``ExceptionGroup`` qualifies only if every member does, so a disconnect
    never hides a real error raised beside it.

    ``websocket`` lets the catch site classify Starlette's ``RuntimeError`` for
    a receive/send after the disconnect: it counts only while the socket's own
    ``client_state`` / ``application_state`` is DISCONNECTED, never by message
    text, so the same ``RuntimeError`` on a live socket stays a real error.
    """
    if websocket is not None and type(exc) is RuntimeError and _socket_is_gone(websocket):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return bool(exc.exceptions) and all(
            is_client_disconnect(e, on_send=on_send, websocket=websocket, at_boundary=at_boundary)
            for e in exc.exceptions
        )
    if isinstance(exc, PEER_CLOSED_ERRORS):
        return True
    if at_boundary and isinstance(exc, _CHANNEL_ERRORS) and _is_channel_error(exc):
        return True
    return on_send and isinstance(exc, _RESET_ON_SEND)


def _caused_by_disconnect(exc: BaseException) -> bool:
    """True when a boundary disconnect sits on ``exc``'s ``__cause__`` / ``__context__`` chain."""
    link: BaseException | None = exc
    for _ in range(_CHAIN_DEPTH):
        link = link.__cause__ or link.__context__ if link else None
        if link is None:
            return False
        if is_client_disconnect(link, at_boundary=True):
            return True
    return False


def is_boundary_disconnect(exc: BaseException) -> bool:
    """:func:`is_client_disconnect` at the ASGI boundary, also through a wrapping ``RuntimeError``.

    Starlette re-raises a handled exception as ``RuntimeError("... response already
    started")`` ``from`` the original, so the disconnect sits on the cause chain.
    """
    if is_client_disconnect(exc, at_boundary=True):
        return True
    return type(exc) is RuntimeError and _caused_by_disconnect(exc)


def log_client_disconnect(log: logging.Logger, exc: BaseException, where: str) -> None:
    """Record an expected disconnect at DEBUG, without a traceback."""
    log.debug("Client disconnected during %s (%s)", where, type(exc).__name__)


def propagate_client_disconnect(log: logging.Logger, exc: BaseException, where: str) -> None:
    """Re-raise ``exc`` unchanged after a DEBUG line if it is a disconnect; else return.

    For recovery layers (retry, fallback, error reports) that must neither retry
    nor report a peer that left, and must leave the response to the caller.
    """
    if is_client_disconnect(exc):
        log_client_disconnect(log, exc, where)
        raise exc


async def client_disconnect_handler(request: Request, exc: Exception) -> Response:
    """Answer a disconnect with an empty 499 and a DEBUG line (nobody is reading).

    Registered per exception *type* so Starlette's inner ``ExceptionMiddleware``
    consumes it. The catch-all ``Exception`` handler runs in the outermost
    ``ServerErrorMiddleware``, which re-raises after responding, so the server
    would still log the exception as an error (#20939).
    """
    log_client_disconnect(logging.getLogger(__name__), exc, f"{request.method} {request.url.path}")
    return Response(status_code=CLIENT_CLOSED_REQUEST)


def register_client_disconnect_handlers(app) -> None:
    """Install :func:`client_disconnect_handler` for ``ClientDisconnect``.

    Channel errors (anyio / OS) are not registered by type: only the guard's tag says
    whether one came from the client, so the catch-all and the guard classify those.
    """
    app.add_exception_handler(ClientDisconnect, client_disconnect_handler)


class ClientDisconnectGuard:
    """Outermost pure-ASGI layer: consume a client disconnect from any inner layer.

    ``ServerErrorMiddleware`` re-raises after its handler, and an outer
    middleware's disconnect never reaches an inner handler, so the server would
    log either as an error. It wraps the ``receive`` / ``send`` it passes inward and tags a
    stream or OS error raised there as a client-channel error. If nothing was sent yet the guard answers an empty
    499 (HTTP) or closes the socket (WebSocket), so the server does not report
    "returned without starting response". Anything that is not a disconnect
    propagates unchanged.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked_receive():
            try:
                return await receive()
            except _CHANNEL_ERRORS as exc:
                _tag_channel_error(exc)
                raise

        async def tracked_send(message) -> None:
            nonlocal started
            started = started or message["type"] in ("http.response.start", "websocket.accept")
            try:
                await send(message)
            except _CHANNEL_ERRORS as exc:
                _tag_channel_error(exc)
                raise

        try:
            await self.app(scope, tracked_receive, tracked_send)
        except Exception as exc:
            if not is_boundary_disconnect(exc):
                raise
            log_client_disconnect(logging.getLogger(__name__), exc, str(scope.get("path", scope["type"])))
            if not started:
                await self._answer_unstarted(scope, tracked_send)

    @staticmethod
    async def _answer_unstarted(scope, send) -> None:
        try:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1001})
                return
            await send({"type": "http.response.start", "status": CLIENT_CLOSED_REQUEST, "headers": []})
            await send({"type": "http.response.body", "body": b""})
        except Exception as exc:  # the peer is already gone; only a non-disconnect is news
            if not is_client_disconnect(exc, on_send=True, at_boundary=True):
                raise


def install_client_disconnect_guard(app) -> None:
    """Make :class:`ClientDisconnectGuard` the outermost layer of ``app``'s stack."""
    build = app.build_middleware_stack
    app.build_middleware_stack = lambda: ClientDisconnectGuard(build())
