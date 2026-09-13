# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend refuses a token whose password-epoch check cannot run (#16411).

Owner decision 2026-09-12: fail closed, the rule the SLM follows (#16387).
These tests drive the REAL ``get_current_user`` -- under pytest
``auth_middleware`` is the conftest stub, so it comes from
``real_auth_middleware`` -- and fail only the Redis read inside the real shared
helper, so each one judges the whole path: helper, gate, 401.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from redis.exceptions import RedisError

import auth_revocation

_REDIS = "autobot_shared.user_management.password_epoch.get_async_redis_client"
_JWT_USER = {"username": "alice", "sub": "alice", "iat": 1, "auth_method": "jwt", "role": "user"}
_REQUEST = SimpleNamespace(headers={}, url=SimpleNamespace(path="/api/chat"))


def _redis_answering(value=None, error=None) -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=value, side_effect=error)
    return AsyncMock(return_value=client)


def _signed_in_as(real_auth_middleware, monkeypatch, user: dict):
    """The real dependency, seeing *user* as the signed-in JWT caller."""
    middleware = SimpleNamespace(get_user_from_request=lambda _request: dict(user))
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)
    return real_auth_middleware.get_current_user


@pytest.fixture
def get_current_user(real_auth_middleware, monkeypatch):
    return _signed_in_as(real_auth_middleware, monkeypatch, _JWT_USER)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RedisError("down"), ConnectionError("refused"), TimeoutError("slow")])
async def test_a_redis_error_denies_the_token(get_current_user, error):
    with patch(_REDIS, _redis_answering(error=error)):
        with pytest.raises(HTTPException) as denied:
            await get_current_user(_REQUEST)

    assert denied.value.status_code == 401
    assert denied.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.asyncio
async def test_no_redis_client_denies_the_token(get_current_user):
    with patch(_REDIS, AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as denied:
            await get_current_user(_REQUEST)

    assert denied.value.status_code == 401


@pytest.mark.asyncio
async def test_a_healthy_redis_admits_a_token_with_no_password_change(get_current_user):
    """The control: the 401s above come from the failed check, not from the harness."""
    with patch(_REDIS, _redis_answering(value=None)):
        user = await get_current_user(_REQUEST)

    assert user["username"] == "alice"


@pytest.mark.asyncio
async def test_a_token_from_before_a_password_change_is_still_refused(get_current_user):
    with patch(_REDIS, _redis_answering(value="1000")):
        with pytest.raises(HTTPException) as denied:
            await get_current_user(_REQUEST)

    assert denied.value.status_code == 401
    assert "password was changed" in denied.value.detail


@pytest.mark.asyncio
async def test_the_denial_names_the_check_and_error_type_never_the_token(get_current_user):
    with patch(_REDIS, _redis_answering(error=RedisError("down"))):
        with patch.object(auth_revocation.logger, "error") as log_error:
            with pytest.raises(HTTPException):
                await get_current_user(_REQUEST)

    message, *args = log_error.call_args.args
    rendered = message % tuple(args)
    assert "password-epoch" in rendered
    assert "RedisError" in rendered
    assert "alice" not in rendered


@pytest.mark.asyncio
async def test_a_corrupt_epoch_marker_denies_the_token(get_current_user):
    """#16422: a marker the check cannot read denies, like a store that cannot answer."""
    with patch(_REDIS, _redis_answering(value="not-a-number")):
        with pytest.raises(HTTPException) as denied:
            await get_current_user(_REQUEST)

    assert denied.value.status_code == 401


@pytest.mark.asyncio
async def test_a_non_integer_iat_denies_the_token(real_auth_middleware, monkeypatch):
    get_current_user = _signed_in_as(real_auth_middleware, monkeypatch, dict(_JWT_USER, iat="not-a-number"))
    with patch(_REDIS, _redis_answering(value=None)):
        with pytest.raises(HTTPException) as denied:
            await get_current_user(_REQUEST)

    assert denied.value.status_code == 401


@pytest.mark.asyncio
async def test_a_corrupt_marker_is_logged_without_its_value(get_current_user):
    with patch(_REDIS, _redis_answering(value="not-a-number")):
        with patch.object(auth_revocation.logger, "error") as log_error:
            with pytest.raises(HTTPException):
                await get_current_user(_REQUEST)

    message, *args = log_error.call_args.args
    rendered = message % tuple(args)
    assert "password-epoch" in rendered
    assert "not-a-number" not in rendered
    assert "alice" not in rendered
