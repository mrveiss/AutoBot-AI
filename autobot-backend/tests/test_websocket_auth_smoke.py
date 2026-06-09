# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
WebSocket authenticated-handshake smoke tests (#6699).

Exercises the JWT auth gate on /ws/live using starlette's TestClient —
no real server, Redis, or network needed.

Happy path:
  - Valid bearer → connection accepted, connection_established frame received
  - Subscribe action → subscribed ack returned

Negative paths:
  - No bearer → close code 4001 (auth required)
  - Invalid / expired bearer → close code 4001

Relationship to #6540: same CI pattern (pure import + starlette TestClient),
no external services.  Add both files to the same CI matrix step.
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

_BACKEND = Path(__file__).resolve().parent.parent
for _p in (str(_BACKEND), str(_BACKEND.parent / "autobot_shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_VALID_PAYLOAD = {"user_id": "u-smoke", "username": "smoketest", "roles": ["user"]}
_SMOKE_BEARER = "smoke"  # short sentinel; matched by mock only


# ---------------------------------------------------------------------------
# Context manager — keeps patches alive while the TestClient makes requests
# ---------------------------------------------------------------------------


def _mock_live_event_manager() -> AsyncMock:
    lem = AsyncMock()
    lem.subscribe = AsyncMock(return_value=True)
    lem.unsubscribe = AsyncMock()
    lem.remove_client = AsyncMock()
    return lem


@contextmanager
def _live_events_client(*, auth_required: bool, verify_fn):
    """Yield a TestClient with live_events router and controlled auth.

    Patches remain active for the lifetime of the context so that WebSocket
    handler calls inside the TestClient see the mocks.
    """
    lem = _mock_live_event_manager()
    with (
        patch("api.live_events._auth_required", return_value=auth_required),
        patch("api.live_events._verify_token", side_effect=verify_fn),
        patch("api.live_events.get_live_event_manager", return_value=lem),
    ):
        from api.live_events import router as live_events_router

        app = FastAPI()
        app.include_router(live_events_router)
        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# /ws/live — happy path
# ---------------------------------------------------------------------------


class TestWsLiveHappyPath:
    """Valid bearer → accepted connection with subscribe/subscribed round-trip."""

    def test_connection_established_frame(self):
        verify = lambda t: _VALID_PAYLOAD if t == _SMOKE_BEARER else None
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with client.websocket_connect(f"/ws/live?token={_SMOKE_BEARER}") as ws:
                frame = ws.receive_json()
            assert frame["type"] == "connection_established"

    def test_subscribe_receives_subscribed_ack(self):
        verify = lambda t: _VALID_PAYLOAD if t == _SMOKE_BEARER else None
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with client.websocket_connect(f"/ws/live?token={_SMOKE_BEARER}") as ws:
                ws.receive_json()  # connection_established
                ws.send_json({"action": "subscribe", "channel": "global"})
                ack = ws.receive_json()
            assert ack["type"] == "subscribed"
            assert ack["channel"] == "global"

    def test_ping_receives_pong(self):
        verify = lambda t: _VALID_PAYLOAD if t == _SMOKE_BEARER else None
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with client.websocket_connect(f"/ws/live?token={_SMOKE_BEARER}") as ws:
                ws.receive_json()  # connection_established
                ws.send_json({"action": "ping"})
                pong = ws.receive_json()
            assert pong["type"] == "pong"

    def test_clean_close_code_1000(self):
        verify = lambda t: _VALID_PAYLOAD if t == _SMOKE_BEARER else None
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with client.websocket_connect(f"/ws/live?token={_SMOKE_BEARER}") as ws:
                ws.receive_json()  # connection_established
                ws.close(1000)


# ---------------------------------------------------------------------------
# /ws/live — negative paths
# ---------------------------------------------------------------------------


class TestWsLiveNegativePaths:
    """Missing or invalid bearer → close before accept (code 4001)."""

    def test_no_bearer_rejected(self):
        verify = lambda t: None  # always fail auth
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/live") as ws:
                    ws.receive_json()
        assert exc_info.value.code == 4001

    def test_invalid_bearer_rejected(self):
        verify = lambda t: None  # simulate bad bearer value
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/live?token=bad") as ws:
                    ws.receive_json()
        assert exc_info.value.code == 4001

    def test_expired_bearer_rejected(self):
        verify = lambda t: None  # same code path as invalid
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/live?token=exp") as ws:
                    ws.receive_json()
        assert exc_info.value.code == 4001


# ---------------------------------------------------------------------------
# /ws/live — auth disabled (SERVICE_AUTH_ENFORCEMENT_MODE=false)
# ---------------------------------------------------------------------------


class TestWsLiveAuthDisabled:
    """When auth is off, any connection is accepted without a bearer value."""

    def test_anonymous_accepted_when_auth_disabled(self):
        verify = lambda t: None  # never called when auth disabled
        with _live_events_client(auth_required=False, verify_fn=verify) as client:
            with client.websocket_connect("/ws/live") as ws:
                frame = ws.receive_json()
            assert frame["type"] == "connection_established"
