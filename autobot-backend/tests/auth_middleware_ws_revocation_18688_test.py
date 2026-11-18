# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``authenticate_websocket`` refuses a JWT revoked by a password change (#18688).

The browser path (subprotocol offer, query-param fallback) verified the signature and built the
user with no password-epoch check, so a token minted before its subject's password changed still
opened the socket. The REAL ``authenticate_websocket`` runs; only the singleton accessor and the
epoch lookup are stood in. Revoked and an unanswerable store are refused; the same JWT fresh passes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_TOKEN = "-".join(["fixture", "revocation", "token"])
_CLAIMS = {"username": "alice", "role": "user", "email": "a@x.com", "sub": "alice", "iat": 1}


def _ws(*, via_subprotocol: bool) -> MagicMock:
    ws = MagicMock()
    protocols = f"bearer, {_TOKEN}" if via_subprotocol else ""
    ws.headers.get = MagicMock(
        side_effect=lambda key, default="": protocols if key == "sec-websocket-protocol" else default
    )
    ws.query_params.get.return_value = None if via_subprotocol else _TOKEN
    ws.url.path = "/ws/example"
    return ws


def _epoch(monkeypatch, outcome) -> None:
    import auth_revocation  # noqa: PLC0415

    stub = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", stub)


async def _authenticate(real, ws):
    instance = MagicMock()
    instance.verify_jwt_token.return_value = dict(_CLAIMS)
    with patch.object(real, "get_auth_middleware", return_value=instance):
        return await real.authenticate_websocket(ws)


def _unavailable() -> Exception:
    from autobot_shared.user_management.password_epoch import RevocationCheckUnavailable  # noqa: PLC0415

    return RevocationCheckUnavailable("epoch store unreachable")


@pytest.mark.asyncio
@pytest.mark.parametrize("via_subprotocol", [True, False], ids=["subprotocol", "query"])
async def test_a_revoked_jwt_is_refused(real_auth_middleware, monkeypatch, via_subprotocol):
    _epoch(monkeypatch, True)
    assert await _authenticate(real_auth_middleware, _ws(via_subprotocol=via_subprotocol)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("via_subprotocol", [True, False], ids=["subprotocol", "query"])
async def test_a_fresh_jwt_is_accepted(real_auth_middleware, monkeypatch, via_subprotocol):
    _epoch(monkeypatch, False)
    user = await _authenticate(real_auth_middleware, _ws(via_subprotocol=via_subprotocol))
    assert user is not None and user["username"] == "alice"


@pytest.mark.asyncio
@pytest.mark.parametrize("via_subprotocol", [True, False], ids=["subprotocol", "query"])
async def test_an_epoch_store_outage_is_refused(real_auth_middleware, monkeypatch, via_subprotocol):
    _epoch(monkeypatch, _unavailable())
    assert await _authenticate(real_auth_middleware, _ws(via_subprotocol=via_subprotocol)) is None
