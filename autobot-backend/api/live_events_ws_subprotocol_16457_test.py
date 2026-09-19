# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``live_events_endpoint`` echoes the client's ``bearer`` subprotocol (#16457).

RFC 6455 4.2.2 requires a server that accepts a handshake carrying subprotocols
to choose and echo one of them, or the browser fails the handshake outright --
so every ``websocket.accept()`` call in this endpoint (both the success path and
the pre-close-4001 rejection path) must pass ``subprotocol="bearer"`` whenever
the client offered it, mirroring ``api/process_management.py``'s convention
(#16374, see ``api/process_management_stream_subprotocol_test.py``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.websockets import WebSocketState

import api.live_events as live_events
from api.live_events import live_events_endpoint


def _fake_ws(*, protocols: str = "", client_state=WebSocketState.DISCONNECTED) -> AsyncMock:
    """A fake WebSocket that never enters the message loop (client_state != CONNECTED)."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    ws.headers = MagicMock()
    ws.headers.get = MagicMock(
        side_effect=lambda key, default="": protocols if key == "sec-websocket-protocol" else default
    )
    ws.client_state = client_state
    ws.client = "test-client"
    return ws


@pytest.fixture(autouse=True)
def _stub_event_bus():
    """The success path's finally-block calls get_event_bus().remove_client(); stub it inert."""
    bus = MagicMock()
    bus.remove_client = AsyncMock()
    with patch.object(live_events, "get_event_bus", return_value=bus):
        yield bus


async def test_accepts_with_bearer_subprotocol_on_success(monkeypatch):
    ws = _fake_ws(protocols="bearer, sometoken")
    monkeypatch.setattr(live_events, "_auth_required", lambda: False)
    with patch.object(live_events, "enforce_ws_origin", new=AsyncMock(return_value=True)):
        with patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=None)):
            await live_events_endpoint(ws)
    assert ws.accept.call_args.kwargs.get("subprotocol") == "bearer"


async def test_accepts_with_no_subprotocol_when_none_offered_on_success(monkeypatch):
    ws = _fake_ws(protocols="")
    monkeypatch.setattr(live_events, "_auth_required", lambda: False)
    with patch.object(live_events, "enforce_ws_origin", new=AsyncMock(return_value=True)):
        with patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=None)):
            await live_events_endpoint(ws)
    assert ws.accept.call_args.kwargs.get("subprotocol") is None


async def test_accepts_with_bearer_subprotocol_on_unauthorized_rejection():
    """The accept()-before-close(4001) rejection path must echo it too."""
    ws = _fake_ws(protocols="bearer, sometoken")
    with patch.object(live_events, "enforce_ws_origin", new=AsyncMock(return_value=True)):
        with patch.object(live_events, "_auth_required", return_value=True):
            with patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=None)):
                await live_events_endpoint(ws)
    assert ws.accept.call_args.kwargs.get("subprotocol") == "bearer"
    ws.close.assert_awaited_once_with(code=4001, reason="Unauthorized")
