# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM WebSocket authenticated-handshake smoke tests (#6699).

Exercises the JWT auth gate on /ws/events (SLM backend) using starlette's
TestClient — no real server or network needed.

Happy path:
  - Valid bearer → connection accepted, connected frame received
  - Ping → pong round-trip

Negative paths:
  - No bearer → close code 4001
  - Invalid / expired bearer → close code 4001
  - Revoked bearer → close code 4001 (denylist enforced via decode_token_async)
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

_SLM = Path(__file__).resolve().parent.parent
if str(_SLM) not in sys.path:
    sys.path.insert(0, str(_SLM))

_VALID_PAYLOAD = {"sub": "smoke", "username": "smoketest"}
_SMOKE_BEARER = "smoke"


def _build_app() -> FastAPI:
    """Build a fresh FastAPI app with the WebSocket router included."""
    from api.websocket import router as ws_router

    app = FastAPI()
    app.include_router(ws_router)
    return app


@contextmanager
def _patched_client(decode_async_fn):
    """Context manager that yields a TestClient with decode_token_async patched.

    The patch stays active for the entire lifetime of the context so that
    WS connections made inside the block use the controlled auth function.
    ``decode_token_async`` is an async method, so we replace it with an
    ``AsyncMock`` whose ``side_effect`` drives the test-controlled return value.
    """
    app = _build_app()
    mock = AsyncMock(side_effect=decode_async_fn)
    with patch("api.websocket.auth_service.decode_token_async", mock):
        yield TestClient(app, raise_server_exceptions=False)


class TestWsEventsHappyPath:
    """Valid bearer → accepted connection with connected frame."""

    def test_connection_established_frame(self):
        async def decode(t):
            return _VALID_PAYLOAD if t == _SMOKE_BEARER else None

        with _patched_client(decode) as client:
            with client.websocket_connect(f"/ws/events?token={_SMOKE_BEARER}") as ws:
                frame = ws.receive_json()
                assert frame["type"] == "connected"

    def test_ping_receives_pong(self):
        async def decode(t):
            return _VALID_PAYLOAD if t == _SMOKE_BEARER else None

        with _patched_client(decode) as client:
            with client.websocket_connect(f"/ws/events?token={_SMOKE_BEARER}") as ws:
                ws.receive_json()  # connected
                ws.send_text("ping")
                pong = ws.receive_text()
                assert pong == "pong"

    def test_clean_close_code_1000(self):
        async def decode(t):
            return _VALID_PAYLOAD if t == _SMOKE_BEARER else None

        with _patched_client(decode) as client:
            with client.websocket_connect(f"/ws/events?token={_SMOKE_BEARER}") as ws:
                ws.receive_json()  # connected
                ws.close(1000)


class TestWsEventsNegativePaths:
    """Missing or invalid bearer → close before accept (code 4001)."""

    def test_no_bearer_rejected(self):
        async def decode(t):
            return None

        with _patched_client(decode) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/events") as ws:
                    ws.receive_json()

        assert exc_info.value.code == 4001

    def test_invalid_bearer_rejected(self):
        async def decode(t):
            return None

        with _patched_client(decode) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/events?token=bad") as ws:
                    ws.receive_json()

        assert exc_info.value.code == 4001

    def test_expired_bearer_rejected(self):
        async def decode(t):
            return None

        with _patched_client(decode) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/events?token=exp") as ws:
                    ws.receive_json()

        assert exc_info.value.code == 4001

    def test_revoked_bearer_rejected(self):
        """decode_token_async returning None (revoked jti) must close with 4001."""

        async def decode(t):
            # Simulates denylist: decode_token_async returns None for a revoked token
            return None

        with _patched_client(decode) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/events?token=revoked-jti-token") as ws:
                    ws.receive_json()

        assert exc_info.value.code == 4001
