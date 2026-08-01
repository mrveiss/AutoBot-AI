# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The run-JWT denylist lookup must fail fast, never stall the request (#12751).

`_is_denied` runs inside `auth_middleware.get_current_user`, which is a
dependency on most authenticated routes:

    get_current_user -> _extract_user_from_run_jwt -> validate_run_jwt -> _is_denied -> Redis

Before this, both the client acquisition and the `exists` call were unbounded,
so a slow Redis stalled the whole request with no HTTP status — the caller saw a
hang rather than a 401, which is strictly worse than a fast rejection.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.auth.jwt_core import JWTDecodeError
from services import run_jwt


@pytest.fixture(autouse=True)
def _fail_closed(monkeypatch):
    """Default policy is fail-closed; tests opt into fail-open explicitly."""
    monkeypatch.delenv("RUN_JWT_REDIS_FAIL_OPEN", raising=False)


@pytest.fixture
def _fast_timeout(monkeypatch):
    """Keep the tests quick without depending on the shipped default."""
    monkeypatch.setattr(run_jwt, "DENYLIST_TIMEOUT_S", 0.05)


def _hanging_redis() -> AsyncMock:
    redis = AsyncMock()

    async def _never_returns(*_a, **_kw):
        await asyncio.sleep(3600)

    redis.exists.side_effect = _never_returns
    return redis


@pytest.mark.asyncio
async def test_hanging_redis_raises_instead_of_stalling(_fast_timeout):
    with patch.object(run_jwt, "get_async_redis_client", AsyncMock(return_value=_hanging_redis())):
        started = time.monotonic()
        with pytest.raises(JWTDecodeError, match="timed out"):
            await run_jwt._is_denied("some-jti")
        elapsed = time.monotonic() - started

    # The point of the fix: bounded, not "eventually".
    assert elapsed < 1.0, f"denylist check took {elapsed:.2f}s — it is not bounded"


@pytest.mark.asyncio
async def test_hanging_client_acquisition_is_also_bounded(_fast_timeout):
    """get_async_redis_client itself retries with backoff — it must be inside the bound."""

    async def _slow_client(*_a, **_kw):
        await asyncio.sleep(3600)

    with patch.object(run_jwt, "get_async_redis_client", _slow_client):
        started = time.monotonic()
        with pytest.raises(JWTDecodeError, match="timed out"):
            await run_jwt._is_denied("some-jti")
        assert time.monotonic() - started < 1.0


@pytest.mark.asyncio
async def test_timeout_honours_fail_open_opt_out(monkeypatch, _fast_timeout):
    """Operators who accepted the revocation risk must not start seeing hard failures."""
    monkeypatch.setenv("RUN_JWT_REDIS_FAIL_OPEN", "1")

    with patch.object(run_jwt, "get_async_redis_client", AsyncMock(return_value=_hanging_redis())):
        assert await run_jwt._is_denied("some-jti") is False


@pytest.mark.asyncio
async def test_unavailable_redis_still_fails_closed():
    """Pre-existing policy must be unchanged: no client means no revocation proof."""
    with patch.object(run_jwt, "get_async_redis_client", AsyncMock(return_value=None)):
        with pytest.raises(JWTDecodeError, match="Redis unavailable"):
            await run_jwt._is_denied("some-jti")


@pytest.mark.asyncio
async def test_unavailable_redis_honours_fail_open(monkeypatch):
    monkeypatch.setenv("RUN_JWT_REDIS_FAIL_OPEN", "1")
    with patch.object(run_jwt, "get_async_redis_client", AsyncMock(return_value=None)):
        assert await run_jwt._is_denied("some-jti") is False


@pytest.mark.asyncio
@pytest.mark.parametrize("exists_result,expected", [(1, True), (0, False)])
async def test_healthy_redis_reports_revocation_state(exists_result, expected):
    """The happy path must be untouched by the timeout wrapper."""
    redis = AsyncMock()
    redis.exists.return_value = exists_result

    with patch.object(run_jwt, "get_async_redis_client", AsyncMock(return_value=redis)):
        assert await run_jwt._is_denied("some-jti") is expected

    redis.exists.assert_awaited_once_with(run_jwt._DENYLIST_PREFIX + "some-jti")


def test_timeout_is_configurable_and_short():
    """A long default would defeat the purpose on an auth path."""
    assert 0 < run_jwt.DENYLIST_TIMEOUT_S <= 5.0
