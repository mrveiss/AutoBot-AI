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
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

_SLM = Path(__file__).resolve().parent.parent
if str(_SLM) not in sys.path:
    sys.path.insert(0, str(_SLM))

_VALID_PAYLOAD = {"sub": "smoke", "username": "smoketest"}
_SMOKE_BEARER = "smoke"


def _make_client(*, decode_fn) -> TestClient:
    """Create a TestClient with SLM websocket router + controlled auth."""
    with patch("api.websocket.auth_service.decode_token", side_effect=decode_fn):
        from api.websocket import router as ws_router

        app = FastAPI()
        app.include_router(ws_router)
        return TestClient(app, raise_server_exceptions=False)


class TestWsEventsHappyPath:
    """Valid bearer → accepted connection with connected frame."""

    def test_connection_established_frame(self):
        decode = lambda t: _VALID_PAYLOAD if t == _SMOKE_BEARER else None
        client = _make_client(decode_fn=decode)

        with client.websocket_connect(f"/ws/events?token={_SMOKE_BEARER}") as ws:
            frame = ws.receive_json()
            assert frame["type"] == "connected"

    def test_ping_receives_pong(self):
        decode = lambda t: _VALID_PAYLOAD if t == _SMOKE_BEARER else None
        client = _make_client(decode_fn=decode)

        with client.websocket_connect(f"/ws/events?token={_SMOKE_BEARER}") as ws:
            ws.receive_json()  # connected
            ws.send_text("ping")
            pong = ws.receive_text()
            assert pong == "pong"

    def test_clean_close_code_1000(self):
        decode = lambda t: _VALID_PAYLOAD if t == _SMOKE_BEARER else None
        client = _make_client(decode_fn=decode)

        with client.websocket_connect(f"/ws/events?token={_SMOKE_BEARER}") as ws:
            ws.receive_json()  # connected
            ws.close(1000)


class TestWsEventsNegativePaths:
    """Missing or invalid bearer → close before accept (code 4001)."""

    def test_no_bearer_rejected(self):
        decode = lambda t: None
        client = _make_client(decode_fn=decode)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/events") as ws:
                ws.receive_json()

        assert exc_info.value.code == 4001

    def test_invalid_bearer_rejected(self):
        decode = lambda t: None
        client = _make_client(decode_fn=decode)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/events?token=bad") as ws:
                ws.receive_json()

        assert exc_info.value.code == 4001

    def test_expired_bearer_rejected(self):
        decode = lambda t: None
        client = _make_client(decode_fn=decode)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/events?token=exp") as ws:
                ws.receive_json()

        assert exc_info.value.code == 4001
