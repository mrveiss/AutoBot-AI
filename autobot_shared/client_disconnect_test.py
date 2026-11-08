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
