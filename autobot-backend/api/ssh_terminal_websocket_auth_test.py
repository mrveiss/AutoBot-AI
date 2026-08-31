# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard tests for api.terminal.ssh_terminal_websocket auth + authorization
(#14991).

This deprecated infrastructure-SSH WebSocket had no authentication at all,
reachable live from the primary chat UI (SSHTerminal.vue -> ChatTabContent.vue).
It must (1) authenticate before accept(), (2) require admin role -- the
strictest reading available without inventing a new capability model, since
no per-admin-host ownership model exists anywhere in the codebase (#14964 is
open and unimplemented, and is scoped to paired-device capabilities, not
admin-host association) -- and (3) resolve host_id against the real
infrastructure-host registry (``resolve_ssh_host_id``,
``api/terminal_ssh.py``), refusing an unknown host_id distinctly from an
admin-role refusal. Per-admin host scoping stays deferred to #14964; this is
the decidable slice of AC2 only.

Drives the real route object registered on the router. ``_setup_ssh_terminal``
is patched with ``AsyncMock`` so a rejection test proves no SSH handler is
ever constructed.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.terminal import ssh_terminal_websocket
from api.terminal_ssh import resolve_ssh_host_id


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
        """#14991: an authenticated admin, for a host_id the registry knows
        about, clears both gates and reaches accept()."""
        ws = _fake_websocket()
        fake_terminal = MagicMock()
        fake_terminal.start = AsyncMock(return_value=False)  # stub always declines to start

        with (
            patch(
                "auth_middleware.authenticate_websocket",
                new=AsyncMock(return_value={"username": "admin-bob", "role": "admin"}),
            ),
            patch("api.terminal.resolve_ssh_host_id", new=AsyncMock(return_value=True)),
            patch("api.terminal._setup_ssh_terminal", new=AsyncMock(return_value=fake_terminal)) as mock_setup,
            patch("api.terminal.ssh_terminal_manager.close_session", new=AsyncMock()),
        ):
            await ssh_terminal_websocket(ws, "prod-host-1")

        ws.accept.assert_awaited_once()
        mock_setup.assert_awaited_once()
        ws.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_with_unknown_host_id_is_rejected(self, caplog):
        """#14991 AC2: an admin is refused for a host_id the registry does not
        know about -- refused before accept(), and never reaches
        ``_setup_ssh_terminal``. ``caplog`` proves the rejection is logged as
        an unknown-host refusal, not conflated with the admin-role refusal
        exercised above -- the two share no text and must stay that way."""
        ws = _fake_websocket()

        with (
            patch(
                "auth_middleware.authenticate_websocket",
                new=AsyncMock(return_value={"username": "admin-bob", "role": "admin"}),
            ),
            patch("api.terminal.resolve_ssh_host_id", new=AsyncMock(return_value=False)),
            patch("api.terminal._setup_ssh_terminal", new=AsyncMock()) as mock_setup,
            caplog.at_level(logging.WARNING, logger="api.terminal"),
        ):
            await ssh_terminal_websocket(ws, "no-such-host")

        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
        ws.accept.assert_not_awaited()
        mock_setup.assert_not_awaited()
        assert any("unknown host_id" in r.message for r in caplog.records)
        assert not any("is not an admin" in r.message for r in caplog.records)


class TestResolveSshHostId:
    """Unit coverage for ``resolve_ssh_host_id`` itself (#14991 AC2) -- the
    registry lookup the route-level tests above stub out."""

    @pytest.mark.asyncio
    async def test_known_host_id_resolves_true(self):
        """Non-vacuity witness: a host_id the registry actually carries must
        resolve positively before the absence case below means anything --
        see ``terminal_websocket_route_test.py`` for why a fail-closed store
        makes 'unknown' and 'unreachable' look identical otherwise."""
        with patch(
            "api.infrastructure._load_secrets_hosts",
            return_value=[{"id": "prod-host-1", "name": "prod-host-1"}],
        ):
            assert await resolve_ssh_host_id("prod-host-1") is True

    @pytest.mark.asyncio
    async def test_unknown_host_id_resolves_false(self):
        with patch(
            "api.infrastructure._load_secrets_hosts",
            return_value=[{"id": "prod-host-1", "name": "prod-host-1"}],
        ):
            assert await resolve_ssh_host_id("no-such-host") is False

    @pytest.mark.asyncio
    async def test_unreachable_registry_fails_closed(self):
        """#14991: the backing store being unavailable must deny, never pass.
        ``_load_secrets_hosts`` already swallows its own read failures into
        ``[]`` (api/infrastructure.py) -- this asserts the caller-visible
        contract holds through that boundary, not just the implementation
        detail of how it holds."""
        with patch("api.infrastructure._load_secrets_hosts", return_value=[]):
            assert await resolve_ssh_host_id("prod-host-1") is False
