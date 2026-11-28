# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /api/auth/login is rate limited per IP and per username (#20600).

The limiter is the shared ``RateLimiter``; here it is replaced by a counting stand-in so the
tests exercise this module's bucket logic (keys, address bucket per attempt,
username bucket per failure, refusal audited), not
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
        self.failed: Counter = Counter()
        self.fail_open_count = 0

    async def acquire(self, key: str) -> bool:
        self.seen[key] += 1
        return self.seen[key] <= self.limit

    async def is_allowed(self, key: str) -> bool:
        return self.failed[key] < self.limit

    async def record(self, key: str) -> None:
        self.failed[key] += 1

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
async def test_a_username_bucket_does_not_lock_another_username(module) -> None:
    limiters = {"ip_limiter": _CountingLimiter(100), "username_limiter": _CountingLimiter(1)}
    db = MagicMock(commit=AsyncMock())
    await module.record_failed_login("alice", username_limiter=limiters["username_limiter"])
    assert await module.enforce_login_rate_limit(db, "192.0.2.2", "alice", **limiters) == 42
    assert await module.enforce_login_rate_limit(db, "192.0.2.3", "bob", **limiters) is None


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
    limiters = {"ip_limiter": _CountingLimiter(100), "username_limiter": _CountingLimiter(1)}
    db = MagicMock(commit=AsyncMock())
    await module.record_failed_login("Alice", username_limiter=limiters["username_limiter"])
    assert await module.enforce_login_rate_limit(db, "192.0.2.2", " alice ", **limiters) == 42


def test_the_module_carries_no_limit_numbers() -> None:
    text = (_BACKEND / "api" / "login_rate_limit.py").read_text(encoding="utf-8")
    assert "requests_per_minute" not in text and "requests_per_hour" not in text
    assert text.count('default_tier="') == 3


def _nginx_request(peer: str, forwarded_for: str):
    """A request as the SLM's own nginx forwards it: peer is loopback, XFF is appended."""
    request = MagicMock()
    request.client.host = peer
    request.headers = {"x-forwarded-for": forwarded_for}
    return request


@pytest.mark.asyncio
async def test_one_client_does_not_lock_out_another_behind_the_slm_nginx(module) -> None:
    """The backend's default trusted list (loopback) resolves the real client per request (#20600)."""
    from fastapi import HTTPException

    from autobot_shared.proxy_utils import get_client_ip

    default_trusted = ["127.0.0.1", "::1"]
    first = get_client_ip(_nginx_request("127.0.0.1", "198.51.100.7"), trusted_proxies=default_trusted)
    second = get_client_ip(_nginx_request("127.0.0.1", "203.0.113.9"), trusted_proxies=default_trusted)
    assert (first, second) == ("198.51.100.7", "203.0.113.9")
    # A forged leftmost entry never selects the address the limiter keys on.
    forged = get_client_ip(_nginx_request("127.0.0.1", "203.0.113.9, 198.51.100.7"), trusted_proxies=default_trusted)
    assert forged == "198.51.100.7"

    limiters = {"ip_limiter": _CountingLimiter(1), "username_limiter": _CountingLimiter(100)}
    db = MagicMock(commit=AsyncMock())
    await module.enforce_login_rate_limit(db, first, "alice", **limiters)
    with pytest.raises(HTTPException):
        await module.enforce_login_rate_limit(db, first, "alice2", **limiters)
    await module.enforce_login_rate_limit(db, second, "bob", **limiters)


@pytest.mark.asyncio
async def test_enforcing_never_charges_the_username_bucket(module) -> None:
    """Only a failed password charges it: attempts (incl. successful ones) and refused IPs do not."""
    from fastapi import HTTPException

    limiters = {"ip_limiter": _CountingLimiter(1), "username_limiter": _CountingLimiter(2)}
    db = MagicMock(commit=AsyncMock())
    await module.enforce_login_rate_limit(db, "192.0.2.66", "admin", **limiters)
    for _ in range(10):
        with pytest.raises(HTTPException):
            await module.enforce_login_rate_limit(db, "192.0.2.66", "admin", **limiters)
    assert limiters["username_limiter"].failed["username:admin"] == 0
    assert limiters["username_limiter"].seen["username:admin"] == 0


@pytest.mark.asyncio
async def test_failures_from_other_addresses_do_not_keep_the_real_admin_out(module) -> None:
    """Four addresses burn the failed budget; the right password from a clean address is not refused."""
    limiters = {"ip_limiter": _CountingLimiter(100), "username_limiter": _CountingLimiter(8)}
    db = MagicMock(commit=AsyncMock())
    for i in range(4):
        for _ in range(5):
            await module.enforce_login_rate_limit(db, f"203.0.113.{i}", "admin", **limiters)
            await module.record_failed_login("admin", username_limiter=limiters["username_limiter"])
    locked = await module.enforce_login_rate_limit(db, "198.51.100.1", "admin", **limiters)
    assert locked is not None  # the name is over its limit...
    # ...but the endpoint (right password) never calls refuse_locked_username: no exception here,
    # and a success records nothing.
    assert limiters["username_limiter"].failed["username:admin"] == 20
    module.audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_wrong_password_over_the_username_limit_is_refused_with_429(module) -> None:
    from fastapi import HTTPException

    limiters = {"ip_limiter": _CountingLimiter(100), "username_limiter": _CountingLimiter(2)}
    db = MagicMock(commit=AsyncMock())
    for _ in range(2):
        assert await module.enforce_login_rate_limit(db, "192.0.2.1", "admin", **limiters) is None
        await module.record_failed_login("admin", username_limiter=limiters["username_limiter"])
    locked = await module.enforce_login_rate_limit(db, "192.0.2.9", "admin", **limiters)
    with pytest.raises(HTTPException) as err:
        await module.refuse_locked_username(db, "192.0.2.9", "admin", locked)
    assert err.value.status_code == 429
    assert err.value.headers["Retry-After"] == "42"
    assert module.audit.await_args.kwargs["response_status"] == 429


@pytest.mark.asyncio
async def test_unknown_addresses_share_a_loose_bucket(module) -> None:
    unknown = _CountingLimiter(100)
    limiters = {
        "ip_limiter": _CountingLimiter(1),
        "username_limiter": _CountingLimiter(2),
        "unknown_ip_limiter": unknown,
    }
    db = MagicMock(commit=AsyncMock())
    for name in ("a", "b", "c"):  # unknown clients do not lock each other out
        await module.enforce_login_rate_limit(db, None, name, **limiters)
    assert limiters["ip_limiter"].seen == Counter()
    assert unknown.seen["ip:unknown"] == 3


@pytest.mark.asyncio
async def test_fail_open_is_logged_loudly_and_login_still_allowed(module, caplog) -> None:
    class _FailOpen(_CountingLimiter):
        async def acquire(self, key: str) -> bool:
            self.fail_open_count += 1
            return True

    limiters = {"ip_limiter": _FailOpen(1), "username_limiter": _FailOpen(1)}
    db = MagicMock(commit=AsyncMock())
    with caplog.at_level("ERROR"):
        await module.enforce_login_rate_limit(db, "192.0.2.1", "alice", **limiters)
    assert any("FAILED OPEN" in r.message and r.levelname == "ERROR" for r in caplog.records)


@pytest.mark.asyncio
async def test_audit_rows_are_bounded_in_a_flood(module, monkeypatch) -> None:
    from fastapi import HTTPException

    limiters = {"ip_limiter": _CountingLimiter(0), "username_limiter": _CountingLimiter(100)}
    db = MagicMock(commit=AsyncMock())
    for _ in range(50):
        with pytest.raises(HTTPException):
            await module.enforce_login_rate_limit(db, "192.0.2.1", "alice", **limiters)
    assert module.audit.await_count == 1  # first refusal per bucket per window

    monkeypatch.setattr(module, "AUDIT_MAX_ROWS_PER_WINDOW", 3)
    for i in range(20):  # many distinct buckets: the global cap holds
        with pytest.raises(HTTPException):
            await module.enforce_login_rate_limit(db, f"203.0.113.{i}", "alice", **limiters)
    assert module.audit.await_count == 3


@pytest.mark.asyncio
async def test_a_bucket_is_audited_again_in_the_next_window(module, monkeypatch) -> None:
    from fastapi import HTTPException

    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    limiters = {"ip_limiter": _CountingLimiter(0), "username_limiter": _CountingLimiter(100)}
    db = MagicMock(commit=AsyncMock())
    for _ in range(3):
        with pytest.raises(HTTPException):
            await module.enforce_login_rate_limit(db, "192.0.2.1", "alice", **limiters)
    clock[0] += module.AUDIT_WINDOW_SECONDS + 1
    with pytest.raises(HTTPException):
        await module.enforce_login_rate_limit(db, "192.0.2.1", "alice", **limiters)
    assert module.audit.await_count == 2
