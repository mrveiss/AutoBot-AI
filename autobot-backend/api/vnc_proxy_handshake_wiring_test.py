# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard tests for websocket_proxy's RFB-handshake wiring (#16299).

Drives the real route object (as vnc_proxy_websocket_auth_test.py does for
the auth gate), past accept() and into the aiohttp connection, mocking only
get_http_client's session chain and the handshake bridge functions -- proves
websocket_proxy actually calls the handshake before relaying, and that a
VncAuthError closes the socket instead of silently falling through to an
unauthenticated relay.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.vnc_proxy import websocket_proxy
from security.vnc_rfb_auth import VncAuthError


def _fake_websocket() -> MagicMock:
    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


def _fake_http_client(vnc_ws: MagicMock) -> MagicMock:
    """A get_http_client() double whose tracked_session().ws_connect(...)
    yields `vnc_ws` through the same nested-async-context-manager chain
    websocket_proxy actually awaits."""
    ws_connect_cm = MagicMock()
    ws_connect_cm.__aenter__ = AsyncMock(return_value=vnc_ws)
    ws_connect_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.ws_connect = MagicMock(return_value=ws_connect_cm)

    tracked_session_cm = MagicMock()
    tracked_session_cm.__aenter__ = AsyncMock(return_value=session)
    tracked_session_cm.__aexit__ = AsyncMock(return_value=False)

    http_client = MagicMock()
    http_client.tracked_session = MagicMock(return_value=tracked_session_cm)
    return http_client


@pytest.mark.asyncio
async def test_a_handshake_failure_closes_the_socket_before_any_relay():
    """The core #16299 guarantee: a VncAuthError -- wrong password, upstream
    refusing to offer VNC Auth, browser disconnecting mid-handshake, a
    missing secret -- must close(1011), never fall through to the plain
    byte relay with no auth performed."""
    ws = _fake_websocket()
    vnc_ws = MagicMock()

    with (
        patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "alice"})),
        patch("api.vnc_proxy.get_http_client", return_value=_fake_http_client(vnc_ws)),
        patch("api.vnc_proxy.record_observation", new=AsyncMock()),
        patch("api.vnc_proxy.get_vnc_password", new=AsyncMock(side_effect=VncAuthError("no secret registered"))),
        patch("api.vnc_proxy._forward_client_to_vnc", new=AsyncMock()) as mock_fwd_in,
        patch("api.vnc_proxy._forward_vnc_to_client", new=AsyncMock()) as mock_fwd_out,
    ):
        await websocket_proxy(ws, "desktop")

    mock_fwd_in.assert_not_awaited()
    mock_fwd_out.assert_not_awaited()
    ws.close.assert_awaited_once()
    assert ws.close.await_args.kwargs.get("code") == 1011
    assert "authentication failed" in ws.close.await_args.kwargs.get("reason", "").lower()


@pytest.mark.asyncio
async def test_a_successful_handshake_reaches_the_relay():
    """The other half: once both handshake legs succeed, the plain byte
    relay actually starts."""
    ws = _fake_websocket()
    vnc_ws = MagicMock()

    with (
        patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "alice"})),
        patch("api.vnc_proxy.get_http_client", return_value=_fake_http_client(vnc_ws)),
        patch("api.vnc_proxy.record_observation", new=AsyncMock()),
        patch("api.vnc_proxy.get_vnc_password", new=AsyncMock(return_value=b"the-password")),
        patch("api.vnc_proxy.authenticate_both_legs", new=AsyncMock(return_value=(b"", b""))) as mock_auth,
        patch("api.vnc_proxy._forward_client_to_vnc", new=AsyncMock()) as mock_fwd_in,
        patch("api.vnc_proxy._forward_vnc_to_client", new=AsyncMock()) as mock_fwd_out,
    ):
        await websocket_proxy(ws, "desktop")

    mock_auth.assert_awaited_once_with(vnc_ws, ws, b"the-password")
    mock_fwd_in.assert_awaited_once()
    mock_fwd_out.assert_awaited_once()
    ws.close.assert_not_awaited()
