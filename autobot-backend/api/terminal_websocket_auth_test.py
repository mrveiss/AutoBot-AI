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

import logging
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest

from api.terminal import session_manager, terminal_websocket
from services.terminal_session_store import SessionConfigStore


@pytest.fixture(autouse=True)
def _fake_session_store(monkeypatch):
    """Back the module-global `session_manager` with an isolated fakeredis (#14961).

    `session_manager.session_configs` is Redis-backed now (shared across
    uvicorn workers, not a process-local dict), and this directory's
    conftest stubs `get_redis_client()` to always return None so unit tests
    never open a live socket. Left alone, every write in this file would hit
    that stub and the fail-closed path would refuse every fixture-created
    session. Swapping in a fakeredis client -- never the live Redis -- keeps
    this file's tests exercising the real dict-like protocol end to end
    without either hazard.
    """
    fake_client = fakeredis.FakeRedis(server=fakeredis.FakeServer())
    monkeypatch.setattr(session_manager, "session_configs", SessionConfigStore(redis_client=fake_client))
    yield


@contextmanager
def _no_ws_credentials():
    """Patch every credential source _resolve_ws_user tries (#14960) to deny.

    See api/vnc_proxy_websocket_auth_test.py::_no_ws_credentials for why all
    three must be closed off, not just the query-param JWT.
    """
    with (
        patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value=None)),
        patch("auth_middleware.verify_internal_api_key", return_value=False),
        patch("auth_middleware.get_auth_middleware") as mock_get_auth_middleware,
    ):
        mock_get_auth_middleware.return_value.get_user_from_request.return_value = None
        yield


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
            _no_ws_credentials(),
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
    async def test_unknown_session_id_is_rejected_no_default(self, caplog):
        """#14961 AC: a session_id that was never created is rejected; no
        TerminalWebSocket is constructed and no default SecurityLevel is used.

        Asserts the specific "unknown session_id" log line _lookup_terminal_session
        emits only on the missing-config branch, distinct from the
        "is not the owner" line the ownership-mismatch branch emits -- both
        exit through the same close(1008), so the outcome alone can't tell
        them apart. Reverting the existence check to `.get(id, {})` (the
        original #14961 shape) still passes through the owner check (an
        empty dict has no "owner" key either) and would pass this test for
        the wrong reason without this assertion.
        """
        ws = _fake_websocket()
        unknown_session_id = str(uuid.uuid4())
        assert unknown_session_id not in session_manager.session_configs

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "alice"})),
            patch("api.terminal._init_terminal_handler", new=AsyncMock()) as mock_init,
            caplog.at_level(logging.WARNING, logger="api.terminal"),
        ):
            await terminal_websocket(ws, unknown_session_id)

        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
        ws.accept.assert_not_awaited()
        mock_init.assert_not_awaited()
        assert any("unknown session_id" in record.message for record in caplog.records)
        assert not any("is not the owner" in record.message for record in caplog.records)


class TestTerminalWebsocketOwnership:
    @pytest.mark.asyncio
    async def test_non_owner_is_rejected(self, owned_session_id, caplog):
        """#14960 AC: an authenticated user connecting to another user's
        session is rejected."""
        ws = _fake_websocket()

        with (
            patch("auth_middleware.authenticate_websocket", new=AsyncMock(return_value={"username": "mallory"})),
            patch("api.terminal._init_terminal_handler", new=AsyncMock()) as mock_init,
            caplog.at_level(logging.WARNING, logger="api.terminal"),
        ):
            await terminal_websocket(ws, owned_session_id)

        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs.get("code") == 1008
        ws.accept.assert_not_awaited()
        mock_init.assert_not_awaited()
        assert any("is not the owner" in record.message for record in caplog.records)
        assert not any("unknown session_id" in record.message for record in caplog.records)

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
