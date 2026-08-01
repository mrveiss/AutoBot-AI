# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Password-change revocation actually revokes (#12924).

Before this, neither backend stopped a session when its password changed:
autobot-backend wrote a blacklist nothing read (``is_token_blacklisted`` has no
production caller, and its token extraction is synchronous so it cannot await
one), and the SLM had a working jti denylist that password change never
triggered.

These tests pin the two properties that make the epoch check a real control
rather than another inert one: a token issued before the change is rejected,
and a token issued after it is not. The fail-open paths are pinned too, because
"fails open" is a deliberate availability choice here and a silent change to it
would lock every user out during a Redis outage.
"""

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.user_management.password_epoch import (
    PASSWORD_EPOCH_PREFIX,
    get_password_epoch,
    is_token_revoked_by_password_change,
    set_password_epoch,
)

_MOD = "autobot_shared.user_management.password_epoch.get_async_redis_client"


def _redis(get_value=None):
    r = AsyncMock()
    r.get = AsyncMock(return_value=get_value)
    r.setex = AsyncMock(return_value=True)
    return r


@pytest.mark.asyncio
async def test_token_issued_before_the_change_is_revoked():
    """The whole point of the issue."""
    with patch(_MOD, AsyncMock(return_value=_redis(get_value="1000"))):
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 999}) is True


@pytest.mark.asyncio
async def test_token_issued_after_the_change_survives():
    """A password change must not log the user out of the new session."""
    with patch(_MOD, AsyncMock(return_value=_redis(get_value="1000"))):
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 1000}) is False
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 1001}) is False


@pytest.mark.asyncio
async def test_no_epoch_means_no_revocation():
    """Users who never changed a password are unaffected."""
    with patch(_MOD, AsyncMock(return_value=_redis(get_value=None))):
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 1}) is False


@pytest.mark.asyncio
async def test_pre_12924_token_without_iat_is_not_revoked():
    """Deploying this must not sign out everyone holding an older token."""
    with patch(_MOD, AsyncMock(return_value=_redis(get_value="1000"))):
        assert await is_token_revoked_by_password_change({"sub": "alice"}) is False


@pytest.mark.asyncio
async def test_token_without_subject_is_not_revoked():
    with patch(_MOD, AsyncMock(return_value=_redis(get_value="1000"))):
        assert await is_token_revoked_by_password_change({"iat": 1}) is False


@pytest.mark.asyncio
async def test_fails_open_when_redis_is_down():
    """Deliberate: a Redis outage must not lock every user out."""
    with patch(_MOD, AsyncMock(return_value=None)):
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 1}) is False


@pytest.mark.asyncio
async def test_fails_open_when_redis_raises():
    r = AsyncMock()
    r.get = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch(_MOD, AsyncMock(return_value=r)):
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 1}) is False


@pytest.mark.asyncio
async def test_corrupt_epoch_value_is_ignored():
    with patch(_MOD, AsyncMock(return_value=_redis(get_value="not-a-number"))):
        assert await get_password_epoch("alice") is None


@pytest.mark.asyncio
async def test_set_password_epoch_writes_a_ttl_bounded_key():
    r = _redis()
    with patch(_MOD, AsyncMock(return_value=r)):
        epoch = await set_password_epoch("alice", now=1234)

    assert epoch == 1234
    key, ttl, value = r.setex.await_args.args
    assert key == f"{PASSWORD_EPOCH_PREFIX}alice"
    assert ttl > 0, "epoch must expire, or the key set grows without bound"
    assert value == "1234"


@pytest.mark.asyncio
async def test_set_password_epoch_reports_failure_rather_than_pretending():
    """Returning None tells the caller no revocation happened."""
    with patch(_MOD, AsyncMock(return_value=None)):
        assert await set_password_epoch("alice") is None

    r = AsyncMock()
    r.setex = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch(_MOD, AsyncMock(return_value=r)):
        assert await set_password_epoch("alice") is None


@pytest.mark.asyncio
async def test_epoch_and_check_agree_end_to_end():
    """Write an epoch, then verify tokens either side of it."""
    store: dict[str, str] = {}
    r = AsyncMock()
    r.setex = AsyncMock(side_effect=lambda k, ttl, v: store.__setitem__(k, v))
    r.get = AsyncMock(side_effect=lambda k: store.get(k))

    with patch(_MOD, AsyncMock(return_value=r)):
        epoch = await set_password_epoch("alice", now=5000)
        assert epoch == 5000

        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 4999}) is True
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 5000}) is False
        # a different user is untouched
        assert await is_token_revoked_by_password_change({"sub": "bob", "iat": 1}) is False


def test_encode_jwt_now_stamps_iat():
    """The epoch check is meaningless without iat on minted tokens (#12924)."""
    import jwt as pyjwt

    from autobot_shared.auth.jwt_core import encode_jwt

    token = encode_jwt({"sub": "alice"}, secret="s" * 32, expiry_hours=1)
    claims = pyjwt.decode(token, "s" * 32, algorithms=["HS256"])

    assert "iat" in claims


def test_encode_jwt_does_not_override_a_caller_supplied_iat():
    import jwt as pyjwt

    from autobot_shared.auth.jwt_core import encode_jwt

    token = encode_jwt({"sub": "alice", "iat": 4242}, secret="s" * 32, expiry_hours=1)
    claims = pyjwt.decode(token, "s" * 32, algorithms=["HS256"])

    assert claims["iat"] == 4242
