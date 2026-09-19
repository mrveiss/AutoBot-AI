# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``session_presence``'s rejection paths echo the client's ``bearer`` subprotocol (#16457).

RFC 6455 4.2.2 requires a server that accepts a handshake carrying subprotocols
to choose and echo one of them, or the browser fails the handshake outright.
All three of this endpoint's accept()-before-close() rejection paths (missing
identity, malformed user_id, not a session participant) must pass
``subprotocol="bearer"`` whenever the client offered it -- mirroring
``api/process_management.py``'s convention (#16374). The success path defers
to ``presence_websocket_handler`` (``websocket/presence.py``), covered by its
own test file.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.presence_ws as presence_ws
from api.presence_ws import session_presence


def _fake_ws(*, protocols: str = "bearer, sometoken") -> AsyncMock:
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.headers = MagicMock()
    ws.headers.get = MagicMock(
        side_effect=lambda key, default="": protocols if key == "sec-websocket-protocol" else default
    )
    return ws


@pytest.fixture(autouse=True)
def _allow_origin():
    with patch.object(presence_ws, "enforce_ws_origin", new=AsyncMock(return_value=True)):
        yield


async def test_echoes_bearer_on_missing_identity_rejection():
    ws = _fake_ws(protocols="bearer, sometoken")
    with patch.object(presence_ws, "authenticate_websocket", new=AsyncMock(return_value=None)):
        await session_presence(ws, "session-1")
    assert ws.accept.call_args.kwargs.get("subprotocol") == "bearer"
    ws.close.assert_awaited_once_with(code=presence_ws._WS_CLOSE_UNAUTHENTICATED, reason="Unauthorized")


async def test_no_subprotocol_echoed_when_none_offered_on_missing_identity():
    ws = _fake_ws(protocols="")
    with patch.object(presence_ws, "authenticate_websocket", new=AsyncMock(return_value=None)):
        await session_presence(ws, "session-1")
    assert ws.accept.call_args.kwargs.get("subprotocol") is None


async def test_echoes_bearer_on_malformed_user_id_rejection():
    ws = _fake_ws(protocols="bearer, sometoken")
    payload = {"user_id": "not-a-uuid"}
    with patch.object(presence_ws, "authenticate_websocket", new=AsyncMock(return_value=payload)):
        await session_presence(ws, "session-1")
    assert ws.accept.call_args.kwargs.get("subprotocol") == "bearer"
    ws.close.assert_awaited_once_with(code=presence_ws._WS_CLOSE_UNAUTHENTICATED, reason="Unauthorized")


async def test_echoes_bearer_on_not_a_participant_rejection():
    ws = _fake_ws(protocols="bearer, sometoken")
    payload = {"user_id": "11111111-1111-1111-1111-111111111111"}
    with patch.object(presence_ws, "authenticate_websocket", new=AsyncMock(return_value=payload)):
        with patch.object(presence_ws, "_authorized_participant", new=AsyncMock(return_value=False)):
            await session_presence(ws, "session-1")
    assert ws.accept.call_args.kwargs.get("subprotocol") == "bearer"
    ws.close.assert_awaited_once_with(code=presence_ws._WS_CLOSE_POLICY_VIOLATION, reason="Not a session participant")
