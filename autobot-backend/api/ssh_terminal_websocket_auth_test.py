# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard tests for api.terminal.ssh_terminal_websocket auth + authorization
(#14991).

This deprecated infrastructure-SSH WebSocket had no authentication at all,
reachable live from the primary chat UI (SSHTerminal.vue -> ChatTabContent.vue)
with no per-host permission model anywhere in the codebase to scope a
host_id against a caller. It must (1) authenticate before accept(), and (2)
require admin role -- the strictest reading available without inventing a
new capability model -- for every host_id, since no finer grain exists.

Drives the real route object registered on the router. ``_setup_ssh_terminal``
is patched with ``AsyncMock`` so a rejection test proves no SSH handler is
ever constructed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.terminal import ssh_terminal_websocket


def _fake_websocket() -> MagicMock:
    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestSshTerminalWebsocketAuthentication:
    @pytest.mark.asyncio
    async def test_unauthenticated_handshake_is_rejected_before_accept(self):
        """#14991: unauthenticated -> close(1008), no SSH handler constructed."""
        ws = _fake_websocket()

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=None)),
            patch("auth_middleware.verify_internal_api_key", return_value=False),
            patch("auth_middleware.get_auth_middleware") as mock_get_auth_middleware,
            patch("api.terminal._setup_ssh_terminal", new=AsyncMock()) as mock_setup,
        ):
            mock_get_auth_middleware.return_value.get_user_from_request.return_value = None
            await ssh_terminal_websocket(ws, "prod-host-1")

        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
        ws.accept.assert_not_awaited()
        mock_setup.assert_not_awaited()


class TestSshTerminalWebsocketAuthorization:
    @pytest.mark.asyncio
    async def test_authenticated_non_admin_is_rejected(self):
        """#14991: an authenticated but non-admin caller is denied for every
        host_id -- there is no per-host permission model to consult, so the
        strictest available reading (admin-only) applies uniformly."""
        ws = _fake_websocket()

        with (
            patch(
                "auth_middleware.authenticate_websocket",
                new=AsyncMock(return_value={"username": "alice", "role": "user"}),
            ),
            patch("api.terminal._setup_ssh_terminal", new=AsyncMock()) as mock_setup,
        ):
            await ssh_terminal_websocket(ws, "prod-host-1")

        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
        ws.accept.assert_not_awaited()
        mock_setup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_authenticated_admin_reaches_accept(self):
        """#14991: an authenticated admin clears both gates and reaches accept()."""
        ws = _fake_websocket()
        fake_terminal = MagicMock()
        fake_terminal.start = AsyncMock(return_value=False)  # stub always declines to start

        with (
            patch(
                "auth_middleware.authenticate_websocket",
                new=AsyncMock(return_value={"username": "admin-bob", "role": "admin"}),
            ),
            patch("api.terminal._setup_ssh_terminal", new=AsyncMock(return_value=fake_terminal)) as mock_setup,
            patch("api.terminal.ssh_terminal_manager.close_session", new=AsyncMock()),
        ):
            await ssh_terminal_websocket(ws, "prod-host-1")

        ws.accept.assert_awaited_once()
        mock_setup.assert_awaited_once()
        ws.close.assert_not_awaited()
