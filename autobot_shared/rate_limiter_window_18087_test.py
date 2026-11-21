# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Behaviour of the canonical window limiter's failure policies (#18087, #7271).

These pin the properties the folded forks relied on, each against the real
``RateLimiter`` with a stateful fake Redis -- not against a mock that returns
truthy:

* cross-process: two workers sharing Redis admit ``limit`` requests in total,
  not ``limit`` each (the per-worker multiplication the dict counters had);
* a REJECTED request is not recorded, so it never extends the window (the
  ``IPRateLimiter`` ZADD-before-ZCARD defect);
* what happens when Redis is down is the caller's explicit choice, and each of
  the three choices behaves as documented.
"""

from __future__ import annotations

import asyncio
from collections import deque
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from autobot_shared.rate_limiter import RateLimiter
from autobot_shared.rate_limiter_window import (
    LocalWindowCounter,
    WindowFailurePolicy,
    WindowQuota,
)

_REDIS = "autobot_shared.rate_limiter.get_async_redis_client"


class FakeWindowRedis:
    """Python re-statement of the canonical window Lua over shared state."""

    def __init__(self) -> None:
        self.zsets: dict[str, list[float]] = {}

    async def eval(self, script, numkeys, win_key, seq_key, now, window, max_requests):
        hits = [t for t in self.zsets.get(win_key, []) if t > now - window]
        self.zsets[win_key] = hits
        if len(hits) >= max_requests:
            return [0, str(window - (now - hits[0]))]
        hits.append(now)
        return [1, "0"]

    async def zcount(self, win_key, low, high):
        return len([t for t in self.zsets.get(win_key, []) if t >= low])

    async def zrangebyscore(self, win_key, low, high, start=0, num=1, withscores=False):
        live = sorted(t for t in self.zsets.get(win_key, []) if t >= low)[start : start + num]
        return [(b"m", t) for t in live]


def _quota(policy=WindowFailurePolicy.FAIL_OPEN, limit=3, **kw) -> WindowQuota:
    return WindowQuota.for_scope("t18087", policy=policy, max_requests=limit, window_seconds=60, **kw)


def _run(coro):
    return asyncio.run(coro)


async def _burst(quota: WindowQuota, n: int, key: str | None = None) -> list[bool]:
    return [await quota.acquire(key) for _ in range(n)]


class TestCrossProcess:
    def test_two_workers_share_one_limit(self):
        redis = FakeWindowRedis()
        worker_a, worker_b = _quota(limit=5), _quota(limit=5)
        with patch(_REDIS, AsyncMock(return_value=redis)):
            a = _run(_burst(worker_a, 5))
            b = _run(_burst(worker_b, 5))
        assert sum(a) + sum(b) == 5, "the limit is global, not per worker"

    def test_contrast_outage_local_state_is_per_worker(self):
        """The cost of LOCAL, stated: two workers admit the limit EACH while Redis is down."""
        worker_a, worker_b = _quota(WindowFailurePolicy.LOCAL, 5), _quota(WindowFailurePolicy.LOCAL, 5)
        with patch(_REDIS, AsyncMock(return_value=None)):
            admitted = sum(_run(_burst(worker_a, 9))) + sum(_run(_burst(worker_b, 9)))
        assert admitted == 10


class TestRejectDoesNotExtendTheWindow:
    def test_rejected_requests_are_not_recorded(self):
        redis = FakeWindowRedis()
        quota = _quota(limit=3)
        with patch(_REDIS, AsyncMock(return_value=redis)):
            results = _run(_burst(quota, 20))
        assert results == [True] * 3 + [False] * 17
        (hits,) = redis.zsets.values()
        assert len(hits) == 3, "IPRateLimiter recorded all 20, so a retrying client never recovered"

    def test_local_path_does_not_record_rejections_either(self):
        counter = LocalWindowCounter()
        for _ in range(10):
            counter.try_acquire("k", 2, 60)
        assert counter.usage("k", 60)[0] == 2


class TestFailurePolicy:
    @pytest.mark.parametrize("fault", ["none", "raises"])
    def test_open_allows_everything(self, fault):
        quota = _quota(WindowFailurePolicy.FAIL_OPEN)
        patched = AsyncMock(return_value=None) if fault == "none" else AsyncMock(side_effect=ConnectionError("down"))
        with patch(_REDIS, patched):
            assert all(_run(_burst(quota, 10)))

    @pytest.mark.parametrize("fault", ["none", "raises"])
    def test_local_keeps_enforcing(self, fault):
        quota = _quota(WindowFailurePolicy.LOCAL)
        patched = AsyncMock(return_value=None) if fault == "none" else AsyncMock(side_effect=ConnectionError("down"))
        with patch(_REDIS, patched):
            assert _run(_burst(quota, 5)) == [True] * 3 + [False] * 2

    @pytest.mark.parametrize("fault", ["none", "raises"])
    def test_closed_denies_everything(self, fault):
        quota = _quota(WindowFailurePolicy.FAIL_CLOSED)
        patched = AsyncMock(return_value=None) if fault == "none" else AsyncMock(side_effect=ConnectionError("down"))
        with patch(_REDIS, patched):
            assert not any(_run(_burst(quota, 3)))

    def test_default_policy_is_open(self):
        assert RateLimiter("x")._window_policy is WindowFailurePolicy.FAIL_OPEN

    def test_local_policy_is_per_key(self):
        quota = _quota(WindowFailurePolicy.LOCAL, limit=1)
        with patch(_REDIS, AsyncMock(return_value=None)):
            assert _run(quota.acquire("1.1.1.1")) and _run(quota.acquire("2.2.2.2"))
            assert not _run(quota.acquire("1.1.1.1"))

    def test_concurrent_local_acquires_admit_exactly_the_limit(self):
        quota = _quota(WindowFailurePolicy.LOCAL, limit=40)

        async def run() -> list[bool]:
            return await asyncio.gather(*[quota.acquire() for _ in range(100)])

        with patch(_REDIS, AsyncMock(return_value=None)):
            assert sum(_run(run())) == 40


class TestQuota:
    def test_check_or_429_raises_with_the_documented_detail(self):
        quota = _quota(WindowFailurePolicy.LOCAL, limit=1)
        with patch(_REDIS, AsyncMock(return_value=None)):
            _run(quota.check_or_429("ip"))
            with pytest.raises(HTTPException) as err:
                _run(quota.check_or_429("ip"))
        assert err.value.status_code == 429
        assert err.value.detail == "Rate limit exceeded (1 requests/60s). Try again later."

    def test_limit_is_reread_from_env_each_call(self, monkeypatch):
        quota = _quota(limit=7, limit_env="T18087_LIMIT")
        assert quota.max_requests == 7
        monkeypatch.setenv("T18087_LIMIT", "2")
        assert quota.max_requests == 2
        monkeypatch.setenv("T18087_LIMIT", "not-a-number")
        assert quota.max_requests == 7

    def test_scopes_do_not_share_state(self):
        redis = FakeWindowRedis()
        one = WindowQuota.for_scope("scope_one", max_requests=1)
        two = WindowQuota.for_scope("scope_two", max_requests=1)
        with patch(_REDIS, AsyncMock(return_value=redis)):
            assert _run(one.acquire("k")) and _run(two.acquire("k"))
            assert not _run(one.acquire("k"))

    def test_status_reports_usage_from_redis(self):
        redis = FakeWindowRedis()
        quota = _quota(limit=5)
        with patch(_REDIS, AsyncMock(return_value=redis)):
            _run(_burst(quota, 2))
            status = _run(quota.status())
        assert status["current"] == 2 and status["max"] == 5
        assert 0 < status["reset_in_seconds"] <= 60

    def test_status_reports_usage_from_local_fallback(self):
        quota = _quota(WindowFailurePolicy.LOCAL, limit=5)
        with patch(_REDIS, AsyncMock(return_value=None)):
            _run(_burst(quota, 3))
            assert _run(quota.status())["current"] == 3

    def test_remaining_under_local_policy_reflects_local_hits(self):
        quota = _quota(WindowFailurePolicy.LOCAL, limit=5)
        with patch(_REDIS, AsyncMock(return_value=None)):
            _run(_burst(quota, 2))
            assert _run(quota.limiter.get_remaining_in_window("global", 5, 60)) == 3


class TestLocalWindowCounter:
    def test_hits_expire_out_of_the_window(self):
        counter = LocalWindowCounter()
        counter._hits["k"] = deque([0.0] * 5)  # the epoch: far outside any window
        assert counter.try_acquire("k", 5, 60)[0] is True

    def test_stale_keys_are_evicted_past_the_cap(self):
        counter = LocalWindowCounter(max_keys=2)
        counter._hits.update({"old1": deque([0.0]), "old2": deque([0.0])})
        counter._windows.update({"old1": 60.0, "old2": 60.0})
        counter.try_acquire("live", 5, 60)
        assert set(counter._hits) == {"live"}

    def test_a_zero_limit_refuses_with_the_full_window(self):
        allowed, retry_after = LocalWindowCounter().try_acquire("k", 0, 60)
        assert allowed is False and retry_after == 60

    def test_live_keys_are_never_evicted_and_the_cap_holds(self):
        counter = LocalWindowCounter(max_keys=2)
        assert counter.try_acquire("a", 1, 60)[0] and counter.try_acquire("b", 1, 60)[0]
        assert counter.try_acquire("c", 1, 60)[0] is False
        counter.record("d", 60)
        assert set(counter._hits) == {"a", "b"}
        assert counter.try_acquire("a", 1, 60)[0] is False  # history preserved

    def test_usage_does_not_create_a_key(self):
        counter = LocalWindowCounter()
        assert counter.usage("ghost", 60) == (0, 0.0)
        assert counter._hits == {}

    def test_a_key_is_evicted_by_its_own_window_not_the_callers(self):
        counter = LocalWindowCounter(max_keys=2)
        counter.try_acquire("long", 1, 3600)
        counter._hits["long"][0] -= 61  # 61s old: expired for a 60s window, live for 3600s
        counter.try_acquire("short", 1, 60)
        assert counter.try_acquire("new", 1, 60)[0] is False  # full of live keys; "long" kept
        assert counter.try_acquire("long", 1, 3600)[0] is False

    def test_retry_after_is_time_until_the_oldest_hit_expires(self):
        counter = LocalWindowCounter()
        counter.try_acquire("k", 1, 60)
        allowed, retry_after = counter.try_acquire("k", 1, 60)
        assert allowed is False and 59 < retry_after <= 60


class TestSweepThrottle:
    """#21907: a full table of live keys is scanned at most once per interval."""

    @staticmethod
    def _full(interval: float = 10.0):
        counter = LocalWindowCounter(max_keys=2, sweep_interval=interval)
        counter.try_acquire("a", 1, 60)
        counter.try_acquire("b", 1, 60)
        scans = []
        real = counter._evict_stale
        counter._evict_stale = lambda now: (scans.append(now), real(now))[1]
        return counter, scans

    def test_n_new_keys_on_a_full_live_table_sweep_once_per_interval(self):
        counter, scans = self._full()
        results = [counter.try_acquire(f"new{i}", 1, 60)[0] for i in range(50)]
        assert results == [False] * 50
        assert len(scans) == 1
        assert set(counter._hits) == {"a", "b"}

    def test_a_sweep_after_the_interval_still_evicts_stale_keys(self):
        counter, scans = self._full(interval=10.0)
        counter.try_acquire("new0", 1, 60)  # first sweep, nothing stale
        counter._hits["a"][0] = 0.0  # now stale
        assert counter.try_acquire("new1", 1, 60)[0] is False  # inside the interval: no scan
        assert len(scans) == 1
        with patch("autobot_shared.rate_limiter_window.time.monotonic", return_value=counter._last_sweep + 11):
            assert counter.try_acquire("new2", 1, 60)[0] is True
        assert len(scans) == 2 and set(counter._hits) == {"b", "new2"}

    def test_refusal_reports_the_full_window(self):
        counter, _ = self._full()
        assert counter.try_acquire("new", 1, 60) == (False, 60.0)
        counter.record("new", 60)
        assert "new" not in counter._hits


class TestLocalWindowCounterRecord:
    def test_record_counts_without_checking(self):
        counter = LocalWindowCounter()
        for _ in range(3):
            counter.record("k", 60)
        used, reset_in = counter.usage("k", 60)
        assert used == 3 and 59 < reset_in <= 60
        assert counter.try_acquire("k", 3, 60)[0] is False
