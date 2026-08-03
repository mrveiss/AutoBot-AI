# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LatencyRouter._refresh_p95 must populate _p95_cache on the decoded client (#13272).

``zrangebyscore`` on the shared client (``decode_responses=True``) yields ``str``
members. The old comprehension was::

    latencies = [float(m.decode().split(":", 1)[1]) for m in members if b":" in m]

``b":" in m`` raises ``TypeError: 'in <string>' requires string as left operand,
not bytes`` **before** ``.decode()`` is ever reached, and the surrounding
``except Exception: logger.debug(...)`` swallowed it. ``_p95_cache`` therefore
never populated, ``_lowest_latency`` saw ``_DEFAULT_P95_MS`` for every candidate,
and latency-aware routing silently returned the first candidate forever — with
only a debug-level log line to show for it.

Both halves are pinned here: the cache must fill from str members, and the
cached values must actually drive model selection.
"""

import pytest

from llm_shared.tiered_routing.latency_router import LatencyRouter
from llm_shared.tiered_routing.tier_config import TierConfig, TierModels

SIMPLE = "model-simple"
COMPLEX = "model-complex"


class _FakeAsyncRedis:
    """Returns pre-seeded sorted-set members for llm:latency:{model} keys."""

    def __init__(self, samples):
        self._samples = samples
        self.queried_keys = []

    async def zrangebyscore(self, key, minimum, maximum):
        self.queried_keys.append(key)
        return self._samples.get(key, [])


def _install(monkeypatch, samples):
    from llm_shared.tiered_routing import latency_router as lr

    fake = _FakeAsyncRedis(samples)

    async def _factory(*args, **kwargs):
        return fake

    monkeypatch.setattr(lr, "get_async_redis_client", _factory)
    return fake


def _router():
    return LatencyRouter(TierConfig(models=TierModels(simple=SIMPLE, complex=COMPLEX)))


def _members(count, latency_ms, *, as_bytes=False):
    """Build '{epoch_s}:{latency_ms}' members the way record_latency writes them."""
    out = [f"{1700000000 + i}:{latency_ms:.1f}" for i in range(count)]
    return [m.encode() for m in out] if as_bytes else out


@pytest.mark.asyncio
async def test_p95_cache_populates_from_str_members(monkeypatch):
    """The live configuration. Pre-fix _p95_cache stayed empty."""
    # 100 samples of 1.0..100.0 ms -> idx = int(0.95 * 100) = 95 -> sorted[95] = 96.0
    members = [f"{1700000000 + i}:{float(i + 1):.1f}" for i in range(100)]
    fake = _install(monkeypatch, {f"llm:latency:{SIMPLE}": members})
    router = _router()

    await router._refresh_p95()

    assert fake.queried_keys, "zrangebyscore was never issued"
    assert router._p95_cache[SIMPLE] == 96.0


@pytest.mark.asyncio
async def test_cached_p95_drives_model_selection(monkeypatch):
    """The behavioural consequence: the genuinely faster model must win."""
    _install(
        monkeypatch,
        {
            f"llm:latency:{SIMPLE}": _members(20, 900.0),
            f"llm:latency:{COMPLEX}": _members(20, 50.0),
        },
    )
    router = _router()

    await router._refresh_p95()

    assert router._p95_cache == {SIMPLE: 900.0, COMPLEX: 50.0}
    # Pre-fix the cache was empty, so _lowest_latency scored both candidates at
    # _DEFAULT_P95_MS and min() returned the first one (SIMPLE) regardless of
    # the real measured latency.
    assert router._lowest_latency([SIMPLE, COMPLEX]) == COMPLEX


@pytest.mark.asyncio
async def test_bytes_members_still_work(monkeypatch):
    """A client without decode_responses must not regress."""
    members = [f"{1700000000 + i}:{float(i + 1):.1f}".encode() for i in range(100)]
    _install(monkeypatch, {f"llm:latency:{SIMPLE}": members})
    router = _router()

    await router._refresh_p95()

    assert router._p95_cache[SIMPLE] == 96.0


@pytest.mark.asyncio
async def test_malformed_members_are_skipped_not_fatal(monkeypatch):
    """Members without the '{epoch}:{ms}' separator are ignored, the rest still count."""
    _install(monkeypatch, {f"llm:latency:{SIMPLE}": ["garbage", *_members(20, 120.0)]})
    router = _router()

    await router._refresh_p95()

    assert router._p95_cache[SIMPLE] == 120.0


@pytest.mark.asyncio
async def test_no_samples_leaves_model_uncached(monkeypatch):
    """No data must not invent a p95; route() then falls back by design."""
    _install(monkeypatch, {})
    router = _router()

    await router._refresh_p95()

    assert router._p95_cache == {}
