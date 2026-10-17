# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The MCP bridges and the password-change limiter share ONE global count (#18087).

Each used to keep a per-worker dict, so N workers meant N times the configured limit. They now
use the canonical ``RateLimiter.acquire_window``. Contrast per module: under the limit is
allowed; over it is the same 429 and detail as before; a second worker (a second limiter
instance on the same Redis) sees the first one's count; Redis down lets the request through.
"""

from __future__ import annotations

import logging
import re
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api import auth, browser_mcp, database_mcp, git_mcp, http_client_mcp
from api.schemas_code import GitStatusRequest, TableListRequest
from api.schemas_system import BrowserNavigateRequest
from api.schemas_workflows import HTTPGetRequest
from autobot_shared import rate_limiter as rl_mod
from autobot_shared.rate_limiter import RateLimiter

try:
    import fakeredis
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None
    fakeredis = None  # type: ignore[assignment]

SHORT = "Rate limit exceeded. Try again later."
PLAIN = "Rate limit exceeded"


async def _past_limiter(coro, refusal_prefix: str):
    """Run *coro*; the one expected 403 from the guard AFTER the limiter counts as a normal return.

    Reaching that exact guard proves the limiter admitted the call. Any other exception, or a 403 with a
    different detail, propagates.
    """
    try:
        return await coro
    except HTTPException as exc:
        if exc.status_code == 403 and str(exc.detail).startswith(refusal_prefix):
            return None
        raise


async def _git():
    return await git_mcp.git_status_mcp(GitStatusRequest())


async def _browser():
    coro = browser_mcp.navigate_mcp(BrowserNavigateRequest(url="ftp://example.org/x"))
    return await _past_limiter(coro, "Refused: 'ftp' is not a browsable scheme")


async def _database():
    coro = database_mcp.database_list_tables_mcp(TableListRequest(database="no-such-db"))
    return await _past_limiter(coro, "Database not in whitelist")


async def _http():
    return await _past_limiter(
        http_client_mcp.http_get_mcp(HTTPGetRequest(url="http://example.invalid/")), "Domain not in allowed whitelist"
    )


# module, handler, limit attr, default limit, detail
CASES = [
    pytest.param(git_mcp, _git, "MAX_GIT_OPS_PER_MINUTE", 60, SHORT, id="git"),
    pytest.param(browser_mcp, _browser, "MAX_REQUESTS_PER_MINUTE", 60, PLAIN, id="browser"),
    pytest.param(database_mcp, _database, "MAX_QUERIES_PER_MINUTE", 60, SHORT, id="database"),
    pytest.param(http_client_mcp, _http, "MAX_REQUESTS_PER_MINUTE", 120, SHORT, id="http_client"),
]


@pytest_asyncio.fixture
async def server(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed")
    return fakeredis.FakeServer()


def _use_redis(monkeypatch, server) -> None:
    client = fakeredis_async.FakeRedis(server=server, decode_responses=True)

    async def _client(database: str = "main"):
        return client

    monkeypatch.setattr(rl_mod, "get_async_redis_client", _client)


async def _outcome(call) -> str | None:
    """None if the handler returned normally (allowed); the 429 detail if it was rate limited.

    Anything else -- a different status, or any other exception -- propagates, so a test cannot
    pass by accident on an unrelated failure.
    """
    try:
        await call()
    except HTTPException as exc:
        if exc.status_code == 429:
            return exc.detail
        raise
    return None


@pytest.mark.parametrize("module, call, limit_attr, default, detail", CASES)
@pytest.mark.asyncio
async def test_default_limits_unchanged(module, call, limit_attr, default, detail):
    assert getattr(module, limit_attr) == default
    assert module.RATE_LIMIT_WINDOW_SECONDS == 60
    assert not hasattr(module, "check_rate_limit")


@pytest.mark.parametrize("module, call, limit_attr, default, detail", CASES)
@pytest.mark.asyncio
async def test_under_limit_allowed_over_limit_429(
    monkeypatch, caplog, server, module, call, limit_attr, default, detail
):
    _use_redis(monkeypatch, server)
    monkeypatch.setattr(module, limit_attr, 3)
    for _ in range(3):
        assert await _outcome(call) is None
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        assert await _outcome(call) == detail
    assert [r for r in caplog.records if "Rate limit exceeded" in r.getMessage() and "3" in r.getMessage()]


@pytest.mark.parametrize("module, call, limit_attr, default, detail", CASES)
@pytest.mark.asyncio
async def test_two_workers_share_one_count(monkeypatch, server, module, call, limit_attr, default, detail):
    _use_redis(monkeypatch, server)
    monkeypatch.setattr(module, limit_attr, 4)
    other_worker = RateLimiter(module._rate_limiter._prefix)
    for _ in range(2):
        assert await module._rate_limiter.acquire_window(module._RATE_LIMIT_KEY, 4, 60)
    for _ in range(2):
        assert await other_worker.acquire_window(module._RATE_LIMIT_KEY, 4, 60)
    assert await _outcome(call) == detail


@pytest.mark.parametrize("module, call, limit_attr, default, detail", CASES)
@pytest.mark.asyncio
async def test_redis_down_fails_open(monkeypatch, caplog, module, call, limit_attr, default, detail):
    async def _down(database: str = "main"):
        raise ConnectionError("redis down")

    monkeypatch.setattr(rl_mod, "get_async_redis_client", _down)
    monkeypatch.setattr(module, limit_attr, 1)
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert await _outcome(call) is None
    assert any("redis down" in r.getMessage() or "fail" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_password_change_limit_is_global_and_429_text_unchanged(monkeypatch, caplog, server):
    _use_redis(monkeypatch, server)
    monkeypatch.setattr(auth, "SESSION_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth, "SESSION_WINDOW_SECONDS", 300)
    other_worker = RateLimiter(auth._password_change_limiter._prefix)
    assert await other_worker.acquire_window("alice:1.2.3.4", 2, 300)
    with patch.object(auth, "get_auth_middleware", return_value=MagicMock()):
        await auth._check_password_change_rate_limit("alice", "1.2.3.4")  # second attempt: allowed
        caplog.clear()
        with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as exc:
            await auth._check_password_change_rate_limit("alice", "1.2.3.4")
        await auth._check_password_change_rate_limit("alice", "5.6.7.8")  # another client id: own count
    assert [r for r in caplog.records if "Rate limit exceeded" in r.getMessage()]
    assert "alice" not in caplog.text and "1.2.3.4" not in caplog.text
    assert exc.value.status_code == 429
    assert exc.value.detail == "Too many password change attempts. Please try again in 5 minutes."


@pytest.mark.asyncio
async def test_password_change_redis_down_fails_open(monkeypatch, caplog):
    async def _down(database: str = "main"):
        raise ConnectionError("redis down")

    monkeypatch.setattr(rl_mod, "get_async_redis_client", _down)
    monkeypatch.setattr(auth, "SESSION_MAX_ATTEMPTS", 1)
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            await auth._check_password_change_rate_limit("alice", "1.2.3.4")
    assert any("fail-open" in r.getMessage() for r in caplog.records)
    assert "alice" not in caplog.text and "1.2.3.4" not in caplog.text
    assert not re.search(r"\b[0-9a-f]{12}\b", caplog.text)  # no key digest either


@pytest.mark.asyncio
async def test_password_change_redis_error_log_never_carries_the_key(monkeypatch, caplog):
    async def _down(database: str = "main"):
        raise ConnectionError("redis down")

    monkeypatch.setattr(rl_mod, "get_async_redis_client", _down)
    monkeypatch.setattr(auth._password_change_limiter, "_last_fail_open_warn", None)  # fresh warn window (#18617)
    with caplog.at_level(logging.WARNING):
        await auth._check_password_change_rate_limit("alice", "1.2.3.4")
    assert [r for r in caplog.records if "window acquire error" in r.getMessage() and "fail-open" in r.getMessage()]
    assert "alice" not in caplog.text and "1.2.3.4" not in caplog.text
    assert not re.search(r"\b[0-9a-f]{12}\b", caplog.text)  # no key digest either
