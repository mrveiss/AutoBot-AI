# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``/auth/refresh`` never renews the token of a closed account, marker or no marker (#20443).

A real signed token goes through the REAL ``refresh_token`` endpoint, the real decode (with its
grace past expiry), the real epoch gate and the real account check. Only storage is stood in for:
the epoch store (in memory) and the user lookup.
"""

import importlib
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from autobot_shared.auth.interactive_principal import LOGIN_TOKEN_TYPE
from autobot_shared.auth.jwt_core import encode_jwt
from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.password_epoch import PASSWORD_EPOCH_TTL_SECONDS, REFRESH_GRACE_SECONDS
from tests.security._credential_harness import PLATFORM_SECRET, real_middleware

HOUR = 3600


@pytest.fixture
def refresh(real_auth_middleware, monkeypatch):
    """The real endpoint over a real-key middleware; ``state`` is the account, ``epochs`` the marker store."""
    api_auth = importlib.import_module("api.auth")
    auth_refresh = importlib.import_module("auth_refresh")
    middleware = real_middleware(real_auth_middleware, enable_auth=True)
    middleware.create_jwt_token = MagicMock(return_value="renewed")
    middleware.jwt_expiry_hours = 24
    for module in (api_auth, auth_refresh):
        monkeypatch.setattr(module, "get_auth_middleware", lambda: middleware)

    state = {"user": SimpleNamespace(username="alice", is_active=True, deleted_at=None), "down": False}

    class _Users:
        def __init__(self, _session):
            pass

        async def get_user_by_username(self, _name):
            if state["down"]:
                raise ConnectionError("database down")
            return state["user"]

    class _Scope:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(auth_refresh, "UserService", _Users)
    monkeypatch.setattr(auth_refresh, "db_session_context", _Scope)

    epochs: dict[str, int] = {}
    password_epoch.use_epoch_store(
        get_epoch=AsyncMock(side_effect=lambda subject: epochs.get(subject)), set_epoch=AsyncMock()
    )
    yield SimpleNamespace(call=api_auth.refresh_token, state=state, epochs=epochs, middleware=middleware)
    password_epoch.reset_epoch_store()


def _request(expired_seconds_ago: int, issued_seconds_ago: int = 25 * HOUR) -> Request:
    claims = {"username": "alice", "role": "user", "token_type": LOGIN_TOKEN_TYPE}
    claims["iat"] = int(time.time()) - issued_seconds_ago
    claims["exp"] = int(time.time()) - expired_seconds_ago
    token = encode_jwt(claims, secret=PLATFORM_SECRET)
    scope = {"type": "http", "method": "POST", "path": "/api/auth/refresh", "query_string": b""}
    scope.update({"headers": [(b"authorization", f"Bearer {token}".encode())], "client": ("t", 1), "app": FastAPI()})
    return Request(scope)


async def _refused(refresh, request, status_code: int = 401) -> None:
    with pytest.raises(HTTPException) as denied:
        await refresh.call(request)
    assert denied.value.status_code == status_code
    refresh.middleware.create_jwt_token.assert_not_called()


@pytest.mark.asyncio
async def test_a_live_user_refreshes_inside_the_grace_window(refresh):
    """The control: the refusals below come from the change, not from the harness."""
    result = await refresh.call(_request(expired_seconds_ago=HOUR - 60))
    assert result["token"] == "renewed"


@pytest.mark.asyncio
async def test_a_token_past_the_grace_window_is_refused(refresh):
    await _refused(refresh, _request(expired_seconds_ago=REFRESH_GRACE_SECONDS + 60))


@pytest.mark.asyncio
async def test_a_deactivated_user_cannot_refresh_even_when_the_marker_is_gone(refresh):
    """The hole: past the marker's old 24h life the epoch said nothing, so refresh minted a new token."""
    refresh.state["user"].is_active = False
    assert refresh.epochs == {}
    await _refused(refresh, _request(expired_seconds_ago=HOUR - 60))


@pytest.mark.asyncio
async def test_a_deleted_or_missing_user_cannot_refresh(refresh):
    refresh.state["user"] = SimpleNamespace(username="alice", is_active=True, deleted_at=time.time())
    await _refused(refresh, _request(expired_seconds_ago=60))
    refresh.state["user"] = None
    await _refused(refresh, _request(expired_seconds_ago=60))


@pytest.mark.asyncio
async def test_an_unreadable_account_store_denies_with_a_retryable_503(refresh):
    refresh.state["down"] = True
    await _refused(refresh, _request(expired_seconds_ago=60), status_code=503)


@pytest.mark.asyncio
async def test_a_marker_still_refuses_a_live_users_older_token(refresh):
    """The epoch gate is on this path too (#18688): an older token cannot be refreshed."""
    refresh.epochs["alice"] = int(time.time()) - 10
    await _refused(refresh, _request(expired_seconds_ago=60, issued_seconds_ago=HOUR))


def test_the_last_refreshable_moment_of_the_oldest_revoked_token_is_inside_the_marker_life():
    """Revoked at T: its token was issued before T, so it dies by T + lifetime and refreshes until + grace."""
    from autobot_shared.user_management.password_epoch import LOGIN_TOKEN_LIFETIME_SECONDS  # noqa: PLC0415

    assert LOGIN_TOKEN_LIFETIME_SECONDS + REFRESH_GRACE_SECONDS < PASSWORD_EPOCH_TTL_SECONDS
