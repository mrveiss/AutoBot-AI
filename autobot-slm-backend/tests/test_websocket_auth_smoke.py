# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Focused unit tests for WebSocket auth (revocation-aware).

These test ``_authenticate_websocket_token`` directly with a fake WebSocket and
a patched ``decode_token_async`` — no FastAPI app, TestClient, or router import.
That keeps them isolation-safe (the previous TestClient-based smoke shared
app/router module state and was order-dependent in the full suite).

Key behavior under test (issue #10151 / M1): WS auth must use the **async**
``decode_token_async`` so the JWT denylist is enforced — a revoked token
(``decode_token_async`` returns ``None``) is rejected with close code 4001.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.websocket import _authenticate_websocket_token


def _fake_ws() -> AsyncMock:
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_missing_token_rejected_4001():
    ws = _fake_ws()
    with patch("api.websocket._extract_ws_token", return_value=None):
        result = await _authenticate_websocket_token(ws)
    assert result is None
    ws.close.assert_awaited_once()
    assert ws.close.call_args.kwargs.get("code") == 4001


@pytest.mark.asyncio
async def test_valid_token_returns_payload_and_uses_async_decode():
    ws = _fake_ws()
    payload = {"sub": "alice", "jti": "abc"}
    async_decode = AsyncMock(return_value=payload)
    with (
        patch("api.websocket._extract_ws_token", return_value="good-token"),
        patch("api.websocket.auth_service.decode_token_async", async_decode),
        # the sync path must NOT be used (it skips the denylist)
        patch("api.websocket.auth_service.decode_token", side_effect=AssertionError("sync decode used")),
    ):
        result = await _authenticate_websocket_token(ws)
    assert result == payload
    async_decode.assert_awaited_once_with("good-token")
    ws.close.assert_not_called()


@pytest.mark.asyncio
async def test_revoked_or_invalid_token_rejected_4001():
    """decode_token_async returning None (revoked jti / invalid) → close 4001."""
    ws = _fake_ws()
    async_decode = AsyncMock(return_value=None)
    with (
        patch("api.websocket._extract_ws_token", return_value="revoked-jti-token"),
        patch("api.websocket.auth_service.decode_token_async", async_decode),
    ):
        result = await _authenticate_websocket_token(ws)
    assert result is None
    async_decode.assert_awaited_once_with("revoked-jti-token")
    ws.close.assert_awaited_once()
    assert ws.close.call_args.kwargs.get("code") == 4001
