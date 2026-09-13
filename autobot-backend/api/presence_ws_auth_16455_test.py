# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""WS /ws/sessions/{session_id}/presence trusts a verified identity only (#16455).

Before this fix, ``session_presence`` took ``user_id`` as a bare, unverified
query parameter and handed it straight to ``presence_websocket_handler`` --
any caller could join any session's presence channel as any user, see who was
genuinely online, and broadcast under a spoofed identity. It now authenticates
via ``auth_middleware.authenticate_websocket`` (the same primitive
``api/live_events.py``'s ``/ws/live`` already uses) and additionally
authorizes: a verified caller must be the session's owner or a listed
collaborator (``models.session_collaboration.SessionCollaboration``), or the
connection is refused.

Same accept-then-close convention as ``tests/test_websockets_auth_reject_12366.py``
(#12366): a rejected socket gets a real WS close frame (4001/1008 + reason),
not a raw handshake rejection indistinguishable from a missing route.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.presence_ws import router as presence_router

_PATH = "/ws/sessions/session-1/presence"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(presence_router)
    return TestClient(app, raise_server_exceptions=False)


def _patch_auth(user_payload: dict | None):
    """``api.presence_ws`` imports ``authenticate_websocket`` at module scope
    (like ``api/websockets.py``, not ``api/live_events.py``'s deferred
    import) -- the patch target is the bound name in ``api.presence_ws``."""
    return patch("api.presence_ws.authenticate_websocket", new=AsyncMock(return_value=user_payload))


def _patch_authorized(is_authorized: bool):
    return patch("api.presence_ws._authorized_participant", new=AsyncMock(return_value=is_authorized))


async def _fake_handler_accepts(websocket, session_id: str, user_id: str) -> None:
    """Stand-in for ``presence_websocket_handler``: the real one calls
    ``websocket.accept()`` as its own first act (unlike this router's
    reject paths, which accept-then-close themselves) -- a bare ``AsyncMock``
    skips that, so the client's handshake ``__enter__`` blocks forever
    waiting for an accept or close that never comes."""
    await websocket.accept()


def test_no_token_closes_4001() -> None:
    with _patch_auth(None):
        client = _client()
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(_PATH) as ws:
                ws.receive_text()
    assert exc_info.value.code == 4001


def test_a_bad_token_closes_4001() -> None:
    # authenticate_websocket itself returns None for an invalid/expired JWT --
    # indistinguishable, from this router's perspective, from no token at all.
    with _patch_auth(None):
        client = _client()
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"{_PATH}?token=garbage") as ws:
                ws.receive_text()
    assert exc_info.value.code == 4001


def test_a_verified_user_not_on_the_session_is_refused() -> None:
    with _patch_auth({"user_id": "22222222-2222-2222-2222-222222222222"}), _patch_authorized(False):
        client = _client()
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"{_PATH}?token=real") as ws:
                ws.receive_text()
    assert exc_info.value.code == 1008


def test_a_spoofed_user_id_query_param_has_no_effect_on_identity() -> None:
    """The route no longer even declares a ``user_id`` parameter -- passing one
    must be inert, and the handler must receive the VERIFIED id, never the
    query string's."""
    real_id = "11111111-1111-1111-1111-111111111111"
    with (
        _patch_auth({"user_id": real_id}),
        _patch_authorized(True),
        patch(
            "api.presence_ws.presence_websocket_handler", new=AsyncMock(side_effect=_fake_handler_accepts)
        ) as mock_handler,
    ):
        client = _client()
        with client.websocket_connect(f"{_PATH}?user_id=someone-else&token=real"):
            pass

    mock_handler.assert_awaited_once()
    called_session_id, called_user_id = mock_handler.await_args.args[1], mock_handler.await_args.args[2]
    assert called_session_id == "session-1"
    assert called_user_id == real_id


def test_an_authorized_participant_connects_under_their_real_identity() -> None:
    real_id = "11111111-1111-1111-1111-111111111111"
    with (
        _patch_auth({"user_id": real_id}),
        _patch_authorized(True),
        patch(
            "api.presence_ws.presence_websocket_handler", new=AsyncMock(side_effect=_fake_handler_accepts)
        ) as mock_handler,
    ):
        client = _client()
        with client.websocket_connect(f"{_PATH}?token=real"):
            pass

    mock_handler.assert_awaited_once_with(mock_handler.await_args.args[0], "session-1", real_id)
