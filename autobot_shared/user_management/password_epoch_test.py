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
and a token issued after it is not. The failure path is pinned too: a check that
cannot run raises, so both callers deny the token rather than honour one that
may be revoked (#16411, owner decision; the SLM's rule since #16387).
"""

from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from redis.exceptions import RedisError

from autobot_shared.ssot_constants import TTL_1_HOUR
from autobot_shared.user_management import password_epoch as password_epoch_module
from autobot_shared.user_management.password_epoch import (
    PASSWORD_EPOCH_PREFIX,
    PASSWORD_EPOCH_TTL_SECONDS,
    REFRESH_GRACE_SECONDS,
    MalformedTokenClaims,
    PasswordEpochMark,
    PasswordEpochWriteError,
    RevocationCheckUnavailable,
    get_password_epoch,
    is_token_revoked_by_password_change,
    set_password_epoch,
)

_MOD = "autobot_shared.user_management.password_epoch.get_async_redis_client"


def _redis(get_value=None):
    r = AsyncMock()
    r.get = AsyncMock(return_value=get_value)
    r.eval = AsyncMock(return_value=1)
    return r


def _fake_redis():
    """A real in-process Redis, so the Lua script that records the epoch actually runs."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


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
async def test_a_login_token_with_only_a_username_claim_is_revoked():
    """Backend login tokens carry ``username`` and no ``sub``; the epoch must still apply (#19061)."""
    with patch(_MOD, AsyncMock(return_value=_redis(get_value="1000"))):
        assert await is_token_revoked_by_password_change({"username": "alice", "iat": 999}) is True
        assert await is_token_revoked_by_password_change({"username": "alice", "iat": 1001}) is False


@pytest.mark.asyncio
async def test_token_without_subject_is_not_revoked():
    with patch(_MOD, AsyncMock(return_value=_redis(get_value="1000"))):
        assert await is_token_revoked_by_password_change({"iat": 1}) is False


@pytest.mark.asyncio
async def test_fails_closed_when_there_is_no_redis_client():
    """#16411: "could not check" must never read as "not revoked"."""
    with patch(_MOD, AsyncMock(return_value=None)):
        with pytest.raises(RevocationCheckUnavailable):
            await is_token_revoked_by_password_change({"sub": "alice", "iat": 1})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RedisError("down"), ConnectionError("refused"), TimeoutError("slow"), OSError("reset")]
)
async def test_fails_closed_when_redis_raises(error):
    r = AsyncMock()
    r.get = AsyncMock(side_effect=error)
    with patch(_MOD, AsyncMock(return_value=r)):
        with pytest.raises(RevocationCheckUnavailable) as raised:
            await is_token_revoked_by_password_change({"sub": "alice", "iat": 1})

    assert raised.value.__cause__ is error


@pytest.mark.asyncio
async def test_fails_closed_when_no_client_can_be_had():
    with patch(_MOD, AsyncMock(side_effect=RedisError("no pool"))):
        with pytest.raises(RevocationCheckUnavailable):
            await get_password_epoch("alice")


@pytest.mark.asyncio
async def test_a_bug_is_not_passed_off_as_an_outage():
    """Only store failures are converted; anything else surfaces as itself."""
    r = AsyncMock()
    r.get = AsyncMock(side_effect=RuntimeError("bug"))
    with patch(_MOD, AsyncMock(return_value=r)):
        with pytest.raises(RuntimeError):
            await get_password_epoch("alice")


def test_the_failure_is_one_the_slm_already_answers_with_401():
    """The SLM catches ``(asyncio.TimeoutError, ConnectionError, OSError, RedisError)``
    around this check and denies with 401 (#16387); an error outside that tuple
    would reach it as a 500 instead."""
    assert issubclass(RevocationCheckUnavailable, ConnectionError)


@pytest.mark.asyncio
async def test_a_corrupt_epoch_marker_fails_closed():
    """#16422: a marker the check cannot read must not read as "no password change"."""
    with patch(_MOD, AsyncMock(return_value=_redis(get_value="not-a-number"))):
        with pytest.raises(RevocationCheckUnavailable):
            await is_token_revoked_by_password_change({"sub": "alice", "iat": 1})


@pytest.mark.asyncio
@pytest.mark.parametrize("epoch", ["1000", None])
async def test_a_non_integer_iat_fails_closed(epoch):
    """#16422: denied whether or not the subject has a marker; #18892: as a bad credential, not an outage."""
    with patch(_MOD, AsyncMock(return_value=_redis(get_value=epoch))):
        with pytest.raises(MalformedTokenClaims):
            await is_token_revoked_by_password_change({"sub": "alice", "iat": "not-a-number"})


@pytest.mark.asyncio
async def test_well_formed_string_values_still_parse():
    """The control: Redis returns the marker as a string, and a numeric-string iat is readable."""
    with patch(_MOD, AsyncMock(return_value=_redis(get_value="1000"))):
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": "1001"}) is False
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": "999"}) is True


@pytest.mark.asyncio
async def test_set_password_epoch_writes_a_ttl_bounded_key():
    r = _redis()
    with patch(_MOD, AsyncMock(return_value=r)):
        epoch = await set_password_epoch("alice", now=1234)

    assert epoch == 1234
    _script, _numkeys, key, value, ttl = r.eval.await_args.args
    assert key == f"{PASSWORD_EPOCH_PREFIX}alice"
    assert int(ttl) > 0, "epoch must expire, or the key set grows without bound"
    assert value == "1234"


@pytest.mark.asyncio
async def test_set_password_epoch_reports_failure_rather_than_pretending():
    """Returning None tells the caller no revocation happened."""
    with patch(_MOD, AsyncMock(return_value=None)):
        assert await set_password_epoch("alice") is None

    r = AsyncMock()
    r.eval = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch(_MOD, AsyncMock(return_value=r)):
        assert await set_password_epoch("alice") is None


@pytest.mark.asyncio
async def test_epoch_and_check_agree_end_to_end():
    """Write an epoch, then verify tokens either side of it."""
    r = _fake_redis()

    with patch(_MOD, AsyncMock(return_value=r)):
        epoch = await set_password_epoch("alice", now=5000)
        assert epoch == 5000

        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 4999}) is True
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 5000}) is False
        # a different user is untouched
        assert await is_token_revoked_by_password_change({"sub": "bob", "iat": 1}) is False


@pytest.mark.asyncio
async def test_recording_an_epoch_never_logs_its_value():
    """The success line names the subject only, never the epoch it wrote -- the same
    rule as the rejection path (CodeQL py/clear-text-logging-sensitive-data)."""
    import autobot_shared.user_management.password_epoch as password_epoch_mod

    with patch(_MOD, AsyncMock(return_value=_redis())):
        with patch.object(password_epoch_mod.logger, "info") as log_info:
            assert await set_password_epoch("alice", now=987654321) == 987654321

    message, *args = log_info.call_args.args
    rendered = message % tuple(args)
    assert "alice" in rendered
    assert "987654321" not in rendered


def test_encode_jwt_now_stamps_iat():
    """The epoch check is meaningless without iat on minted tokens (#12924)."""
    import jwt as pyjwt

    from autobot_shared.auth.jwt_core import encode_jwt

    token = encode_jwt({"sub": "alice"}, secret="s" * 32, expiry_hours=1)
    claims = pyjwt.decode(token, "s" * 32, algorithms=["HS256"])

    assert "iat" in claims


def test_encoded_iat_is_an_integer_timestamp():
    """PyJWT >= 2.10 rejects a non-integer ``iat`` on decode.

    ``encode_jwt`` hands PyJWT a ``datetime`` and relies on it normalising to a
    Unix timestamp. This repo has already been bitten by a non-integer ``iat``
    once — it silently 401'd every authenticated request and produced a login
    redirect loop (see the comment on ``create_jwt_token`` in
    ``autobot-backend/auth_middleware.py``). Pinned so a PyJWT change or a
    refactor of the encoder cannot reintroduce it quietly.
    """
    import jwt as pyjwt

    from autobot_shared.auth.jwt_core import encode_jwt

    token = encode_jwt({"sub": "alice"}, secret="s" * 32, expiry_hours=1)
    claims = pyjwt.decode(token, "s" * 32, algorithms=["HS256"])

    assert isinstance(claims["iat"], int), f"iat must be an int, got {type(claims['iat']).__name__}"


def test_encode_jwt_does_not_override_a_caller_supplied_iat():
    import jwt as pyjwt

    from autobot_shared.auth.jwt_core import encode_jwt

    token = encode_jwt({"sub": "alice", "iat": 4242}, secret="s" * 32, expiry_hours=1)
    claims = pyjwt.decode(token, "s" * 32, algorithms=["HS256"])

    assert claims["iat"] == 4242


@pytest.mark.asyncio
async def test_the_marker_is_kept_past_the_last_moment_a_token_it_revokes_can_refresh():
    """A token issued before the marker lives its lifetime and refreshes for the grace after: the TTL covers both."""
    r = _redis()
    with patch(_MOD, AsyncMock(return_value=r)):
        await set_password_epoch("alice", now=1234)

    ttl = int(r.eval.await_args.args[4])
    assert ttl == PASSWORD_EPOCH_TTL_SECONDS
    assert ttl > password_epoch_module.LOGIN_TOKEN_LIFETIME_SECONDS + REFRESH_GRACE_SECONDS


@pytest.mark.asyncio
async def test_in_redis_bypasses_a_process_that_routes_its_epochs_elsewhere():
    """The SLM keeps its own epochs in its database; the backend's users' markers still have to reach Redis (#20443)."""
    own = AsyncMock(return_value=7)
    r = _redis()
    password_epoch_module.use_epoch_store(get_epoch=AsyncMock(), set_epoch=own)
    try:
        with patch(_MOD, AsyncMock(return_value=r)):
            assert await set_password_epoch("alice", now=5) == 7
            assert await set_password_epoch("alice", now=5, in_redis=True) == 5
    finally:
        password_epoch_module.reset_epoch_store()

    own.assert_awaited_once()
    assert r.eval.await_args.args[3] == "5"


@pytest.mark.asyncio
async def test_a_mark_reads_the_clock_when_it_runs_and_leads_it_by_its_lead():
    r = _redis()
    with patch(_MOD, AsyncMock(return_value=r)), patch.object(password_epoch_module.time, "time", return_value=1000.9):
        assert await PasswordEpochMark("alice", lead_seconds=1)() == 1001
        assert await PasswordEpochMark("alice")() == 1000
    assert PasswordEpochMark("alice", 1) == PasswordEpochMark("alice", 1), "equal marks queue once"


@pytest.mark.asyncio
async def test_an_earlier_dated_write_never_lowers_the_epoch_or_shortens_its_life():
    """Deactivate at T+1, then a password change at T: the order that used to revive iat=T tokens (#20443)."""
    r = _fake_redis()
    key = f"{PASSWORD_EPOCH_PREFIX}alice"
    with patch(_MOD, AsyncMock(return_value=r)):
        await set_password_epoch("alice", now=1001)
        await r.expire(key, TTL_1_HOUR)
        await set_password_epoch("alice", now=1000)

        assert await get_password_epoch("alice") == 1001
        assert await is_token_revoked_by_password_change({"sub": "alice", "iat": 1000}) is True
        assert await r.ttl(key) > TTL_1_HOUR, "a write that changes nothing still refreshes the marker's life"

        await set_password_epoch("alice", now=1002)
        assert await get_password_epoch("alice") == 1002


@pytest.mark.asyncio
async def test_an_unreadable_stored_marker_is_replaced_by_the_new_epoch():
    r = _fake_redis()
    await r.set(f"{PASSWORD_EPOCH_PREFIX}alice", "garbage")
    with patch(_MOD, AsyncMock(return_value=r)):
        await set_password_epoch("alice", now=5)
        assert await get_password_epoch("alice") == 5


@pytest.fixture
def no_backoff(monkeypatch):
    monkeypatch.setattr(password_epoch_module, "MEMBERSHIP_EPOCH_BUMP_BACKOFF_SECONDS", 0.0)


@pytest.mark.asyncio
async def test_a_mark_retries_a_failed_write_and_then_succeeds(no_backoff):
    r = _redis()
    r.eval = AsyncMock(side_effect=[RuntimeError("down"), RuntimeError("down"), 1])
    with patch(_MOD, AsyncMock(return_value=r)):
        assert await PasswordEpochMark("alice")() > 0
    assert r.eval.await_count == 3 == password_epoch_module.MEMBERSHIP_EPOCH_BUMP_ATTEMPTS


@pytest.mark.asyncio
async def test_a_mark_that_never_lands_raises_instead_of_reporting_success(no_backoff):
    r = _redis()
    r.eval = AsyncMock(side_effect=RuntimeError("down"))
    with patch(_MOD, AsyncMock(return_value=r)), pytest.raises(PasswordEpochWriteError):
        await PasswordEpochMark("alice")()
    assert r.eval.await_count == password_epoch_module.MEMBERSHIP_EPOCH_BUMP_ATTEMPTS


@pytest.mark.asyncio
async def test_a_mark_with_no_redis_client_or_a_store_that_returns_none_raises(no_backoff):
    with patch(_MOD, AsyncMock(return_value=None)), pytest.raises(PasswordEpochWriteError):
        await PasswordEpochMark("alice")()

    password_epoch_module.use_epoch_store(get_epoch=AsyncMock(), set_epoch=AsyncMock(return_value=None))
    try:
        with pytest.raises(PasswordEpochWriteError):
            await PasswordEpochMark("alice")()
    finally:
        password_epoch_module.reset_epoch_store()


@pytest.mark.asyncio
async def test_a_password_change_still_reports_a_failed_write_as_none_and_does_not_retry():
    """Only deactivation and deletion changed; change_password's behaviour is as it was."""
    r = _redis()
    r.eval = AsyncMock(side_effect=RuntimeError("down"))
    with patch(_MOD, AsyncMock(return_value=r)):
        assert await set_password_epoch("alice") is None
    assert r.eval.await_count == 1
