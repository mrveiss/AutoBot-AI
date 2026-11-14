# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The WebSocket gates refuse a password-change-revoked JWT (#18688).

``authenticate_ws_admin`` and ``enforce_ws_authentication`` decided on the synchronous
``get_user_from_request``, which cannot await the Redis password-epoch check, so a JWT minted
before its subject's password changed still opened the socket. Both now resolve through the
REAL ``auth_middleware.resolve_human_user``; only the identity and the epoch lookup are stood in.
A revoked token, and an epoch store that cannot answer, are denied; the same JWT, not revoked, passes.
"""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.ws_security import authenticate_ws_admin, enforce_ws_admin, enforce_ws_authentication
from tests.conftest import load_real_auth_middleware

_JWT_ADMIN = {"username": "alice", "role": "admin", "sub": "alice", "iat": 1, "auth_method": "jwt"}


@pytest.fixture
def real_gate(monkeypatch):
    real = load_real_auth_middleware()
    middleware = SimpleNamespace(get_user_from_request=lambda _ws: dict(_JWT_ADMIN))
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(real, "verify_internal_api_key", lambda _key: False)
    monkeypatch.setattr(real, "authenticate_websocket", AsyncMock(return_value=None))
    monkeypatch.setitem(sys.modules, "auth_middleware", real)
    monkeypatch.setenv("AUTOBOT_REQUIRE_WS_AUTH", "1")
    return real


def _epoch(monkeypatch, outcome) -> None:
    """*outcome*: True revoked, False fresh, or an exception the store raises."""
    import auth_revocation  # noqa: PLC0415

    stub = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", stub)


def _unavailable() -> Exception:
    from autobot_shared.user_management.password_epoch import RevocationCheckUnavailable  # noqa: PLC0415

    return RevocationCheckUnavailable("epoch store unreachable")


def _ws() -> SimpleNamespace:
    return SimpleNamespace(headers={}, accept=AsyncMock(), close=AsyncMock())


@pytest.mark.asyncio
async def test_the_admin_gate_denies_a_revoked_jwt(real_gate, monkeypatch):
    _epoch(monkeypatch, True)
    assert await authenticate_ws_admin(_ws()) is False


@pytest.mark.asyncio
async def test_the_admin_gate_allows_a_fresh_jwt(real_gate, monkeypatch):
    _epoch(monkeypatch, False)
    assert await authenticate_ws_admin(_ws()) is True


@pytest.mark.asyncio
async def test_the_admin_gate_denies_when_the_epoch_store_cannot_answer(real_gate, monkeypatch):
    _epoch(monkeypatch, _unavailable())
    assert await authenticate_ws_admin(_ws()) is False


@pytest.mark.asyncio
async def test_a_revoked_jwt_is_closed_4001_at_the_admin_endpoint_gate(real_gate, monkeypatch):
    _epoch(monkeypatch, True)
    ws = _ws()
    assert await enforce_ws_admin(ws) is False
    assert ws.close.await_args.kwargs.get("code") == 4001


@pytest.mark.asyncio
async def test_the_authentication_gate_closes_1008_for_a_revoked_jwt(real_gate, monkeypatch):
    _epoch(monkeypatch, True)
    ws = _ws()
    assert await enforce_ws_authentication(ws) is None
    assert ws.close.await_args.kwargs == {"code": 1008, "reason": "Authentication required"}


@pytest.mark.asyncio
async def test_the_authentication_gate_admits_a_fresh_jwt(real_gate, monkeypatch):
    _epoch(monkeypatch, False)
    ws = _ws()
    user = await enforce_ws_authentication(ws)
    assert user["username"] == "alice"
    ws.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_authentication_gate_denies_when_the_epoch_store_cannot_answer(real_gate, monkeypatch):
    _epoch(monkeypatch, _unavailable())
    ws = _ws()
    assert await enforce_ws_authentication(ws) is None
    assert ws.close.await_args.kwargs.get("code") == 1008
