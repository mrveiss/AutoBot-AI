# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM websocket refuses a session that is not an admin's, with close code 4001 (#20631, #20628).

``service.management`` is held by the operator role; it does not open the SLM, on the socket
any more than on the HTTP routers. The root conftest stubs ``services.auth`` with a MagicMock, so
``api.websocket.is_admin_session`` would answer truthy for anyone; the REAL decision is loaded by
path (``_real_auth_import``) and patched in. The fake WebSocket mirrors
``test_websocket_purpose_bound_18338``'s.
"""

from __future__ import annotations

import importlib
import secrets
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_HELPER_DIR = str(Path(__file__).resolve().parent)
sys.path.insert(0, _HELPER_DIR)
try:
    load_real_auth = importlib.import_module("_real_auth_import").load_real_auth
finally:
    sys.path.remove(_HELPER_DIR)  # the helper dir is only needed for this one import

from api.websocket import _authenticate_websocket_token  # noqa: E402

_auth = load_real_auth(secrets.token_hex(32))


def _fake_ws() -> AsyncMock:
    """A WebSocket stand-in with the sync request properties the reject logger reads."""
    ws = AsyncMock()
    ws.headers = MagicMock()
    ws.headers.get = MagicMock(side_effect=lambda key, default=None: default)
    ws.url = MagicMock(path="/ws/test")
    ws.client = ("127.0.0.1", 12345)
    return ws


async def _authenticate(payload: dict):
    ws = _fake_ws()
    with (
        patch("api.websocket._extract_ws_token", return_value="tok"),
        patch("api.websocket.is_admin_session", _auth.is_admin_session),
        patch("api.websocket.auth_service.decode_token_async", AsyncMock(return_value=payload)),
    ):
        return await _authenticate_websocket_token(ws), ws


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"sub": "op1", "role": "operator", "admin": False},
        {"sub": "op1", "role": "operator", "permissions": ["service.management"]},
        {"sub": "user1", "role": "user"},
        {"sub": "nobody"},
    ],
    ids=["operator", "operator with service.management", "user", "token that does not say"],
)
async def test_a_non_admin_session_is_refused_4001(payload):
    result, ws = await _authenticate(payload)
    assert result is None
    ws.close.assert_awaited_once()
    assert ws.close.call_args.kwargs.get("code") == 4001


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [{"sub": "a1", "admin": True, "role": "admin"}, {"sub": "service:backend", "service": True}],
    ids=["admin", "backend service token"],
)
async def test_the_controls_are_accepted(payload):
    result, ws = await _authenticate(payload)
    assert result == payload
    ws.close.assert_not_awaited()
