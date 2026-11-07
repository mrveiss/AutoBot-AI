# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM websocket accepts sessions and the backend's service token, never a pre-MFA token (#18338).

``_authenticate_websocket_token`` is a second token-to-principal path beside
``get_current_user``. A blanket ``is_purpose_bound`` refusal would also drop the
backend->SLM service token this socket exists for, so the rule is "purpose-bound
and not a service token" (``is_service_token``). The fake WebSocket mirrors
``test_websocket_auth_smoke``'s.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.websocket import _authenticate_websocket_token


def _fake_ws() -> AsyncMock:
    """A WebSocket stand-in with the sync request properties the reject logger reads."""
    ws = AsyncMock()
    ws.headers = MagicMock()
    ws.headers.get = MagicMock(side_effect=lambda key, default=None: default)
    ws.url = MagicMock(path="/ws/test")
    ws.client = ("127.0.0.1", 12345)
    return ws


_MFA_PENDING = {"sub": "admin1", "mfa_pending": True, "user_id": "u-1", "admin": True}
_SERVICE = {"sub": "service:backend", "service": True}  # services/slm_client.py::_mint_service_jwt
_SESSION = {"sub": "admin1", "admin": True, "role": "admin"}


async def _authenticate(payload: dict):
    ws = _fake_ws()
    with (
        patch("api.websocket._extract_ws_token", return_value="tok"),
        patch("api.websocket.auth_service.decode_token_async", AsyncMock(return_value=payload)),
    ):
        return await _authenticate_websocket_token(ws), ws


@pytest.mark.asyncio
async def test_an_mfa_pending_token_is_refused_4001():
    result, ws = await _authenticate(_MFA_PENDING)
    assert result is None and ws.close.call_args.kwargs.get("code") == 4001


@pytest.mark.asyncio
async def test_a_service_token_carrying_mfa_pending_is_refused():
    """``service`` cannot launder a pre-MFA token."""
    result, _ = await _authenticate({**_SERVICE, "mfa_pending": True})
    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [_SERVICE, _SESSION], ids=["backend service token", "session"])
async def test_the_controls_are_accepted(payload):
    result, ws = await _authenticate(payload)
    assert result == payload
    ws.close.assert_not_awaited()
