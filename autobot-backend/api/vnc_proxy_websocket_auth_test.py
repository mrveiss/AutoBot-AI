# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard tests for api.vnc_proxy.websocket_proxy authentication (#14959).

VNC/RFB proxy WebSocket -- full keyboard, mouse and framebuffer access to
the canonical desktop -- must reject an unauthenticated handshake before
websocket.accept(), so no RFB frame is ever forwarded.

Drives the real route object registered on the router (the decorated
``websocket_proxy`` callable), not the auth helper in isolation, and
asserts at the far boundary: which close code was sent, and whether
accept() was ever awaited. ``authenticate_websocket`` is patched at its
import site (``auth_middleware``) rather than reimplementing JWT
verification here -- these tests exercise the route's wiring to that
helper, not the helper's own internals.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.vnc_proxy import websocket_proxy


def _fake_websocket(*, origin: str | None = None) -> MagicMock:
    """A minimal WebSocket double: no Origin header by default -- the
    reproduction described in #14959 (no Origin, no credentials).
    """
    ws = MagicMock()
    ws.headers = {"origin": origin} if origin else {}
    ws.query_params = {}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestVncWebsocketProxyAuthentication:
    @pytest.mark.asyncio
    async def test_unauthenticated_handshake_is_rejected_before_accept(self):
        """#14959 AC: unauthenticated -> close(1008), accept() never called."""
        ws = _fake_websocket()

        with patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=None)):
            await websocket_proxy(ws, "desktop")

        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
        ws.accept.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_authenticated_handshake_reaches_accept(self):
        """#14959 AC: an authenticated caller clears the gate and reaches accept();
        the connection observation names them.
        """
        ws = _fake_websocket()
        fake_user = {"username": "alice", "role": "user"}

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=fake_user)),
            patch(
                "api.vnc_proxy.get_http_client",
                side_effect=RuntimeError("stop the test after the auth gate"),
            ),
            patch("api.vnc_proxy.record_observation", new=AsyncMock()) as mock_observe,
        ):
            await websocket_proxy(ws, "desktop")

        ws.accept.assert_awaited_once()
        connect_call = mock_observe.await_args_list[0]
        assert connect_call.args[2]["user"] == "alice"
