# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard tests for api.terminal.terminal_websocket auth + ownership
(#14960, #14961).

The terminal WebSocket attaches an interactive shell to a live session; it
must (1) authenticate the handshake before accept(), (2) treat an unknown
session_id as a terminal condition rather than a default-configured
session, and (3) require the authenticated caller to own the session.

Drives the real route object registered on the router (the decorated
``terminal_websocket`` callable). ``_init_terminal_handler`` and
``_run_terminal_message_loop`` are patched with ``AsyncMock`` so a
rejection test proves "no shell starts" by asserting the handler
constructor was never awaited, and an acceptance test proves the route
reaches it without spawning a real PTY.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.terminal import session_manager, terminal_websocket


def _fake_websocket() -> MagicMock:
    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def owned_session_id():
    """A session config owned by 'alice', cleaned up after the test."""
    session_id = str(uuid.uuid4())
    session_manager.session_configs[session_id] = {
        "session_id": session_id,
        "owner": "alice",
        "security_level": "standard",
    }
    yield session_id
    session_manager.session_configs.pop(session_id, None)


class TestTerminalWebsocketAuthentication:
    @pytest.mark.asyncio
    async def test_unauthenticated_handshake_is_rejected_before_accept(self, owned_session_id):
        """#14960 AC: unauthenticated -> close(1008), no handler constructed.

        Asserts _lookup_terminal_session (the ownership check) is never
        reached, so this fails distinctly from a same-outcome ownership
        rejection if the auth guard itself were removed.
        """
        ws = _fake_websocket()

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=None)),
            patch("api.terminal._lookup_terminal_session") as mock_lookup,
            patch("api.terminal._init_terminal_handler", new=AsyncMock()) as mock_init,
        ):
            await terminal_websocket(ws, owned_session_id)

        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
        ws.accept.assert_not_awaited()
        mock_lookup.assert_not_called()
        mock_init.assert_not_awaited()


class TestTerminalWebsocketUnknownSession:
    @pytest.mark.asyncio
    async def test_unknown_session_id_is_rejected_no_default(self):
        """#14961 AC: a session_id that was never created is rejected; no
        TerminalWebSocket is constructed and no default SecurityLevel is used.
        """
        ws = _fake_websocket()
        unknown_session_id = str(uuid.uuid4())
        assert unknown_session_id not in session_manager.session_configs

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "alice"})),
            patch("api.terminal._init_terminal_handler", new=AsyncMock()) as mock_init,
        ):
            await terminal_websocket(ws, unknown_session_id)

        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
        ws.accept.assert_not_awaited()
        mock_init.assert_not_awaited()


class TestTerminalWebsocketOwnership:
    @pytest.mark.asyncio
    async def test_non_owner_is_rejected(self, owned_session_id):
        """#14960 AC: an authenticated user connecting to another user's
        session is rejected."""
        ws = _fake_websocket()

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "mallory"})),
            patch("api.terminal._init_terminal_handler", new=AsyncMock()) as mock_init,
        ):
            await terminal_websocket(ws, owned_session_id)

        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
        ws.accept.assert_not_awaited()
        mock_init.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_owner_connects_normally(self, owned_session_id):
        """#14960 AC: the authenticated owner still connects normally."""
        ws = _fake_websocket()
        fake_terminal = MagicMock()
        fake_terminal.cleanup = AsyncMock()

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "alice"})),
            patch("api.terminal._init_terminal_handler", new=AsyncMock(return_value=fake_terminal)) as mock_init,
            patch("api.terminal._run_terminal_message_loop", new=AsyncMock()),
        ):
            await terminal_websocket(ws, owned_session_id)

        ws.accept.assert_awaited_once()
        mock_init.assert_awaited_once()
        ws.close.assert_not_awaited()
