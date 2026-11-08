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
from starlette.websockets import WebSocketDisconnect

# Status for a request whose client left before the answer (nginx's 499); never read by anyone.
CLIENT_CLOSED_REQUEST = 499

# Transport-level signals that only ever mean the peer's side of the stream closed.
# Usable directly as an ``except`` clause so a handler keeps its own follow-up action.
PEER_CLOSED_ERRORS = (ClientDisconnect, WebSocketDisconnect, anyio.EndOfStream, anyio.BrokenResourceError)
# A reset on a *send* is the peer; the same class from an upstream call (Redis,
# a model server) is a real failure, so it only counts when the caller says so.
_RESET_ON_SEND = (ConnectionResetError, BrokenPipeError)


def is_client_disconnect(exc: BaseException, *, on_send: bool = False) -> bool:
    """True when ``exc`` means the client closed its side of the connection.

    ``on_send`` marks an exception raised while writing to the client socket,
    where ``ConnectionResetError`` / ``BrokenPipeError`` also mean a disconnect.
    A (nested) ``ExceptionGroup`` qualifies only if every member does, so a
    disconnect never hides a real error raised beside it.
    """
    if isinstance(exc, BaseExceptionGroup):
        return bool(exc.exceptions) and all(is_client_disconnect(e, on_send=on_send) for e in exc.exceptions)
    if isinstance(exc, PEER_CLOSED_ERRORS):
        return True
    return on_send and isinstance(exc, _RESET_ON_SEND)


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
    """Install :func:`client_disconnect_handler` for every HTTP peer-closed type."""
    for exc_type in (ClientDisconnect, anyio.EndOfStream, anyio.BrokenResourceError):
        app.add_exception_handler(exc_type, client_disconnect_handler)
