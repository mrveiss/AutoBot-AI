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

Repaired for the current contract (#11791): the endpoint no longer has a
local ``_verify_token`` helper — since #9963 it delegates to the canonical
``auth_middleware.authenticate_websocket`` (imported at call time), which
reads the JWT from the ``?token=`` query param and returns a user payload or
None (#2818). The auth seam here patches ``authenticate_websocket`` on the
``auth_middleware`` module (the conftest stub, resolved by the endpoint's
call-time import) with an async shim that reads ``?token=`` exactly like the
real function and maps it through the test's ``verify_fn``. Event fan-out
moved from LiveEventManager to ``events.bus.get_event_bus`` (subscribe_ws /
unsubscribe_ws / remove_client).
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


def _verify_valid(token: str | None) -> dict | None:
    """Accept only the smoke sentinel bearer."""
    return _VALID_PAYLOAD if token == _SMOKE_BEARER else None


def _verify_none(token: str | None) -> None:
    """Always fail auth (missing / invalid / expired bearer)."""
    return None


# ---------------------------------------------------------------------------
# Context manager — keeps patches alive while the TestClient makes requests
# ---------------------------------------------------------------------------


def _repair_stubbed_packages() -> None:
    """Whole-dir suite runs: earlier-collected test modules stub or clobber
    ``services`` / ``api`` / ``events`` in sys.modules (``__path__ = []``),
    breaking the late import of ``api.live_events`` below (#11791). Mirror the
    backend root-conftest repair so this file stays collection-order-proof.
    """
    for pkg in ("services", "api", "events"):
        mod = sys.modules.get(pkg)
        # NB: probe __dict__ directly — stub modules define a module-level
        # __getattr__ that returns a truthy MagicMock for ANY attribute,
        # including __path__.
        if mod is not None and not mod.__dict__.get("__path__"):
            mod.__path__ = [str(_BACKEND / pkg)]


def _mock_event_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.subscribe_ws = AsyncMock(return_value=True)
    bus.unsubscribe_ws = AsyncMock()
    bus.remove_client = AsyncMock()
    return bus


@contextmanager
def _live_events_client(*, auth_required: bool, verify_fn):
    """Yield a TestClient with live_events router and controlled auth.

    Patches remain active for the lifetime of the context so that WebSocket
    handler calls inside the TestClient see the mocks. The auth seam mirrors
    the real ``authenticate_websocket`` contract (#2818): read the JWT from
    the ``?token=`` query param, return a payload dict or None (the endpoint
    then closes with 4001 when auth is required and the payload is None).
    """

    async def _fake_authenticate_websocket(websocket) -> dict | None:
        return verify_fn(websocket.query_params.get("token"))

    _repair_stubbed_packages()
    bus = _mock_event_bus()
    with (
        patch("api.live_events._auth_required", return_value=auth_required),
        patch("auth_middleware.authenticate_websocket", new=_fake_authenticate_websocket, create=True),
        patch("api.live_events.get_event_bus", return_value=bus),
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
        verify = _verify_valid
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with client.websocket_connect(f"/ws/live?token={_SMOKE_BEARER}") as ws:
                frame = ws.receive_json()
            assert frame["type"] == "connection_established"

    def test_subscribe_receives_subscribed_ack(self):
        verify = _verify_valid
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with client.websocket_connect(f"/ws/live?token={_SMOKE_BEARER}") as ws:
                ws.receive_json()  # connection_established
                ws.send_json({"action": "subscribe", "channel": "global"})
                ack = ws.receive_json()
            assert ack["type"] == "subscribed"
            assert ack["channel"] == "global"

    def test_ping_receives_pong(self):
        verify = _verify_valid
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with client.websocket_connect(f"/ws/live?token={_SMOKE_BEARER}") as ws:
                ws.receive_json()  # connection_established
                ws.send_json({"action": "ping"})
                pong = ws.receive_json()
            assert pong["type"] == "pong"

    def test_clean_close_code_1000(self):
        verify = _verify_valid
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with client.websocket_connect(f"/ws/live?token={_SMOKE_BEARER}") as ws:
                ws.receive_json()  # connection_established
                ws.close(1000)


# ---------------------------------------------------------------------------
# /ws/live — negative paths
# ---------------------------------------------------------------------------


class TestWsLiveNegativePaths:
    """Missing or invalid bearer → accept-then-close (code 4001, #12366)."""

    def test_no_bearer_rejected(self):
        verify = _verify_none  # always fail auth
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/live") as ws:
                    ws.receive_json()
        assert exc_info.value.code == 4001

    def test_invalid_bearer_rejected(self):
        verify = _verify_none  # simulate bad bearer value
        with _live_events_client(auth_required=True, verify_fn=verify) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/live?token=bad") as ws:
                    ws.receive_json()
        assert exc_info.value.code == 4001

    def test_expired_bearer_rejected(self):
        verify = _verify_none  # same code path as invalid
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
        verify = _verify_none  # never called when auth disabled
        with _live_events_client(auth_required=False, verify_fn=verify) as client:
            with client.websocket_connect("/ws/live") as ws:
                frame = ws.receive_json()
            assert frame["type"] == "connection_established"
