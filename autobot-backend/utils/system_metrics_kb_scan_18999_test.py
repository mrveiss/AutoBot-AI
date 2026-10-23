# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""KB gauges walk doc:* / kb_cache:* once per refresh window, not every 5 s cycle (#18999)."""

import fnmatch

import pytest

from autobot_shared import redis_scan
from utils import system_metrics as sm


class CountingRedis:
    def __init__(self, keys):
        self.keys_ = list(keys)
        self.scan_calls = 0

    async def scan_iter(self, match=None, count=10):
        for i in range(0, len(self.keys_), count):
            self.scan_calls += 1
            for k in self.keys_[i : i + count]:
                if fnmatch.fnmatchcase(k, match):
                    yield k

    async def hgetall(self, name):
        return {}


KEYS = [f"doc:{i}" for i in range(1569)] + [f"kb_cache:{i}" for i in range(7)]


@pytest.fixture(autouse=True)
def _pin_scan_count(monkeypatch):
    monkeypatch.setattr(redis_scan, "REDIS_SCAN_COUNT", 1000)  # independent of AUTOBOT_REDIS_SCAN_COUNT


def _collector():
    return sm.SystemMetricsCollector.__new__(sm.SystemMetricsCollector)


async def _cycle(c, r):
    out = {}
    await c._collect_kb_vector_metrics(r, 0.0, out)
    await c._collect_kb_cache_metrics(r, 0.0, out)
    return out


@pytest.mark.asyncio
async def test_counts_match_the_old_full_walk_and_repeat_cycles_are_free(monkeypatch):
    c = _collector()
    c._kb_counts = {}
    r = CountingRedis(KEYS)
    first = await _cycle(c, r)
    assert first["kb_vector_count"].value == 1569
    assert first["kb_cache_entries"].value == 7
    calls_after_first = r.scan_calls
    assert calls_after_first == 4  # 2 patterns x 2 COUNT=1000 pages (old code: ~316)
    for _ in range(100):  # 100 collection cycles inside the window
        await _cycle(c, r)
    # Breaks if `_cached_key_count` stops returning the cached value (the `return cached[1]` line).
    assert r.scan_calls == calls_after_first


@pytest.mark.asyncio
async def test_count_refreshes_after_window_and_sees_new_and_expired_keys(monkeypatch):
    c = _collector()
    c._kb_counts = {}
    r = CountingRedis(KEYS)
    await _cycle(c, r)
    r.keys_ = [k for k in r.keys_ if k != "doc:0"] + ["kb_cache:new1", "kb_cache:new2"]
    monkeypatch.setattr(sm, "KB_COUNT_REFRESH_SECONDS", 0.0)
    out = await _cycle(c, r)
    assert out["kb_vector_count"].value == 1568
    assert out["kb_cache_entries"].value == 9


class FailingRedis(CountingRedis):
    async def scan_iter(self, match=None, count=10):
        self.scan_calls += 1
        raise ConnectionError("redis busy")
        yield  # pragma: no cover - makes this an async generator


@pytest.mark.asyncio
async def test_failed_walk_keeps_the_old_count_and_does_not_retry_next_cycle(monkeypatch):
    c = _collector()
    c._kb_counts = {}
    good = CountingRedis(KEYS)
    await _cycle(c, good)
    monkeypatch.setattr(sm, "KB_COUNT_REFRESH_SECONDS", 0.0)  # window expired
    bad = FailingRedis(KEYS)
    out = await _cycle(c, bad)
    assert out["kb_vector_count"].value == 1569  # stale value, never 0
    assert out["kb_cache_entries"].value == 7
    assert bad.scan_calls == 2  # one failed attempt per pattern
    monkeypatch.setattr(sm, "KB_COUNT_REFRESH_SECONDS", 300.0)  # the failure stamped the attempt
    await _cycle(c, bad)
    assert bad.scan_calls == 2  # waits a full window; no retry


@pytest.mark.asyncio
async def test_failed_walk_with_no_prior_value_omits_the_metric_and_waits_a_window():
    c = _collector()
    c._kb_counts = {}
    bad = FailingRedis(KEYS)
    out = await _cycle(c, bad)
    assert "kb_vector_count" not in out and "kb_cache_entries" not in out
    await _cycle(c, bad)
    assert bad.scan_calls == 2  # not retried inside the window


@pytest.mark.asyncio
async def test_metric_carries_count_age_seconds(monkeypatch):
    c = _collector()
    c._kb_counts = {}
    r = CountingRedis(KEYS)
    out = await _cycle(c, r)
    assert out["kb_vector_count"].metadata["count_age_seconds"] == 0.0
    t0 = sm.time.monotonic()
    monkeypatch.setattr(sm.time, "monotonic", lambda: t0 + 120)
    out = await _cycle(c, r)
    assert out["kb_vector_count"].metadata["count_age_seconds"] >= 119.9
