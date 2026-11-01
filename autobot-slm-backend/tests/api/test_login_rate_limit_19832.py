# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /api/auth/login is rate limited per IP and per username (#19832).

The limiter is the shared ``RateLimiter``; here it is replaced by a counting stand-in so the
tests exercise this module's bucket logic (keys, both buckets charged, refusal audited), not
Redis. Limits and the real limiter's configuration are not exercised.
"""

import importlib.util
import sys
import types
from collections import Counter
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_BACKEND.parent))


class _CountingLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.seen: Counter = Counter()

    async def acquire(self, key: str) -> bool:
        self.seen[key] += 1
        return self.seen[key] <= self.limit

    async def get_retry_after_seconds(self, key: str) -> int:
        return 42


@pytest.fixture()
def module(monkeypatch):
    audit = AsyncMock()
    security = types.ModuleType("api.security")
    security.create_audit_log = audit
    monkeypatch.setitem(sys.modules, "api", types.ModuleType("api"))
    monkeypatch.setitem(sys.modules, "api.security", security)
    spec = importlib.util.spec_from_file_location(
        "login_rate_limit_under_test", _BACKEND / "api" / "login_rate_limit.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.audit = audit
    return mod


def _limiters(limit: int) -> dict:
    return {"ip_limiter": _CountingLimiter(limit), "username_limiter": _CountingLimiter(limit)}


@pytest.mark.asyncio
async def test_under_the_limit_passes_and_nothing_is_audited(module) -> None:
    limiters = _limiters(3)
    db = MagicMock(commit=AsyncMock())
    for _ in range(3):
        await module.enforce_login_rate_limit(db, "192.0.2.1", "alice", **limiters)
    module.audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_over_the_limit_refuses_with_429_retry_after_and_an_audited_failure(module) -> None:
    from fastapi import HTTPException

    limiters = _limiters(2)
    db = MagicMock(commit=AsyncMock())
    for _ in range(2):
        await module.enforce_login_rate_limit(db, "192.0.2.1", "alice", **limiters)
    with pytest.raises(HTTPException) as err:
        await module.enforce_login_rate_limit(db, "192.0.2.1", "alice", **limiters)
    assert err.value.status_code == 429
    assert err.value.headers["Retry-After"] == "42"
    kwargs = module.audit.await_args.kwargs
    assert kwargs["success"] is False
    assert kwargs["response_status"] == 429
    assert kwargs["action"] == "auth.login"
    assert kwargs["username"] == "alice"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_a_username_bucket_does_not_block_another_username(module) -> None:
    from fastapi import HTTPException

    # Different IPs, so only the username bucket can be the one exhausted.
    limiters = {"ip_limiter": _CountingLimiter(100), "username_limiter": _CountingLimiter(1)}
    db = MagicMock(commit=AsyncMock())
    await module.enforce_login_rate_limit(db, "192.0.2.1", "alice", **limiters)
    with pytest.raises(HTTPException):
        await module.enforce_login_rate_limit(db, "192.0.2.2", "alice", **limiters)
    await module.enforce_login_rate_limit(db, "192.0.2.3", "bob", **limiters)


@pytest.mark.asyncio
async def test_an_ip_bucket_does_not_block_another_ip(module) -> None:
    from fastapi import HTTPException

    limiters = {"ip_limiter": _CountingLimiter(1), "username_limiter": _CountingLimiter(100)}
    db = MagicMock(commit=AsyncMock())
    await module.enforce_login_rate_limit(db, "192.0.2.1", "alice", **limiters)
    with pytest.raises(HTTPException):
        await module.enforce_login_rate_limit(db, "192.0.2.1", "bob", **limiters)
    await module.enforce_login_rate_limit(db, "192.0.2.9", "carol", **limiters)


@pytest.mark.asyncio
async def test_username_case_and_padding_share_one_bucket(module) -> None:
    from fastapi import HTTPException

    limiters = {"ip_limiter": _CountingLimiter(100), "username_limiter": _CountingLimiter(1)}
    db = MagicMock(commit=AsyncMock())
    await module.enforce_login_rate_limit(db, "192.0.2.1", "Alice", **limiters)
    with pytest.raises(HTTPException):
        await module.enforce_login_rate_limit(db, "192.0.2.2", " alice ", **limiters)


def test_the_module_carries_no_limit_numbers() -> None:
    text = (_BACKEND / "api" / "login_rate_limit.py").read_text(encoding="utf-8")
    assert "requests_per_minute" not in text and "requests_per_hour" not in text
    assert text.count('default_tier="anonymous"') == 2
