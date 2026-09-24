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

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.vnc_proxy import websocket_proxy


@contextmanager
def _no_ws_credentials():
    """Patch every credential source _resolve_ws_user tries (#14959) to deny.

    Widening enforce_ws_authentication to a union of credential checks means
    a test asserting "unauthenticated" must close off all of them, not just
    the query-param JWT -- otherwise it passes for the wrong reason if any
    one of the others is left to the conftest auth_middleware stub, whose
    ``__getattr__`` fabricates a truthy MagicMock for anything unpatched.
    """
    with (
        patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=None)),
        patch("auth_middleware.verify_internal_api_key", return_value=False),
        patch("auth_middleware.get_auth_middleware") as mock_get_auth_middleware,
    ):
        mock_get_auth_middleware.return_value.get_user_from_request.return_value = None
        yield


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

        with _no_ws_credentials():
            await websocket_proxy(ws, "desktop")

        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
        ws.accept.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_permitted_caller_reaches_accept(self):
        """#14959 AC: a caller who clears the gate reaches accept(); the
        connection observation names them.

        #17054: `operator` rather than `user`. The desktop socket now requires
        `mcp.desktop.control`, which only `admin` and `operator` hold, so a
        `user` is refused before the handshake and this test's subject -- the
        accept -- stops being reachable at all. `operator` is the LEAST
        privileged role that still reaches it, so the test exercises the gate it
        must pass rather than an admin bypassing everything.
        """
        ws = _fake_websocket()
        fake_user = {"username": "alice", "role": "operator"}

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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["user", "editor", "analyst", "readonly", "superadmin"])
    async def test_an_authenticated_but_unpermitted_caller_is_refused_before_accept(self, role):
        """#17054: authenticated is not enough, and nothing else covered this.

        The unauthenticated case has a test (above). The case this gate actually
        introduces -- a real signed-in account without `mcp.desktop.control` --
        had none: it was being exercised only by accident, by the test above
        using `role: "user"`, and that accident failed rather than asserted.

        `superadmin` is in the list deliberately. `ROLE_PERMISSIONS[SUPERADMIN]`
        is empty by #13854, so the role that sounds highest is refused; if that
        is ever ruled wrong, the fix is that table and this parameter moves to
        the permitted test -- one place, both asserted.
        """
        ws = _fake_websocket()

        with patch(
            "auth_middleware.authenticate_websocket",
            new=AsyncMock(return_value={"username": "mallory", "role": role}),
        ):
            await websocket_proxy(ws, "desktop")

        ws.accept.assert_not_awaited()
        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
