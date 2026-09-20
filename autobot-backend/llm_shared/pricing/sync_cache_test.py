# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the synchronous pricing cache mirror (#16230, #16316).

Exercises the module's own logic directly rather than through
``PricingCacheScheduler``'s asyncio poll loop, which is
``PollLoopScheduler``'s responsibility and already covered by
``llc/tests/test_poll_loop_scheduler.py`` and its concrete-subclass sibling
suites (e.g. ``community_cluster_scheduler_test.py``). What is specific to
this module -- and therefore what needs its own coverage -- is: the cold/
populated/stale three-state snapshot, and that a failed refresh cannot make
pricing look fresh (the property #16233's guard also checks for, per its
AC3).
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from llm_shared.pricing import sync_cache
from llm_shared.pricing.sources import ModelPricing

_PRICE = ModelPricing(provider="anthropic", model_id="claude-sonnet-4-0", input_per_1m=3.0, output_per_1m=15.0)


@pytest.fixture(autouse=True)
def _cold_cache():
    """Every test starts from the never-populated state and leaves it that way."""
    sync_cache._reset_for_tests()
    yield
    sync_cache._reset_for_tests()


def _populate(prices: dict[str, ModelPricing], age_s: float = 0.0) -> None:
    """Set `_snapshot` directly, `age_s` seconds old, bypassing Redis and the scheduler."""
    sync_cache._snapshot = sync_cache._Snapshot(prices=prices, fetched_at=time.monotonic() - age_s)


# --- cold cache ---------------------------------------------------------


def test_get_cached_price_raises_cold_when_never_populated():
    with pytest.raises(sync_cache.PricingCacheCold):
        sync_cache.get_cached_price("claude-sonnet-4-0")


def test_get_cached_snapshot_raises_cold_when_never_populated():
    with pytest.raises(sync_cache.PricingCacheCold):
        sync_cache.get_cached_snapshot()


def test_is_snapshot_populated_false_when_cold():
    assert sync_cache.is_snapshot_populated() is False


# --- populated and fresh -------------------------------------------------


def test_get_cached_price_returns_the_priced_model():
    _populate({"claude-sonnet-4-0": _PRICE})
    assert sync_cache.get_cached_price("claude-sonnet-4-0") is _PRICE


def test_get_cached_price_is_case_insensitive_on_the_key():
    _populate({"claude-sonnet-4-0": _PRICE})
    assert sync_cache.get_cached_price("Claude-Sonnet-4-0") is _PRICE


def test_get_cached_price_returns_none_for_a_model_not_in_the_catalogue():
    _populate({"claude-sonnet-4-0": _PRICE})
    assert sync_cache.get_cached_price("some-unpriced-model") is None


def test_get_cached_snapshot_returns_the_whole_dict():
    prices = {"claude-sonnet-4-0": _PRICE}
    _populate(prices)
    assert sync_cache.get_cached_snapshot() is prices


def test_is_snapshot_populated_true_once_populated():
    _populate({})
    assert sync_cache.is_snapshot_populated() is True


# --- populated and stale --------------------------------------------------


def test_get_cached_price_raises_stale_past_the_freshness_bound(monkeypatch):
    monkeypatch.setattr(sync_cache, "MAX_SNAPSHOT_AGE_S", 10)
    _populate({"claude-sonnet-4-0": _PRICE}, age_s=11)

    with pytest.raises(sync_cache.PricingCacheStale):
        sync_cache.get_cached_price("claude-sonnet-4-0")


def test_pricing_cache_stale_is_a_pricing_cache_cold():
    """A caller that only catches `PricingCacheCold` (budget.py) must still refuse.

    #16316's rule is that "cannot compute a trustworthy price" always refuses
    rather than falling through to a guess -- staleness reaching an existing
    ``except PricingCacheCold`` unnoticed would silently reopen that hole.
    """
    assert issubclass(sync_cache.PricingCacheStale, sync_cache.PricingCacheCold)


def test_get_cached_price_within_the_freshness_bound_still_succeeds(monkeypatch):
    monkeypatch.setattr(sync_cache, "MAX_SNAPSHOT_AGE_S", 10)
    _populate({"claude-sonnet-4-0": _PRICE}, age_s=1)

    assert sync_cache.get_cached_price("claude-sonnet-4-0") is _PRICE


def test_get_cached_snapshot_also_refuses_once_stale(monkeypatch):
    monkeypatch.setattr(sync_cache, "MAX_SNAPSHOT_AGE_S", 10)
    _populate({"claude-sonnet-4-0": _PRICE}, age_s=11)

    with pytest.raises(sync_cache.PricingCacheStale):
        sync_cache.get_cached_snapshot()


def test_is_snapshot_populated_stays_true_when_stale():
    """Staleness is `get_cached_price`'s concern, not `is_snapshot_populated`'s."""
    _populate({}, age_s=10_000_000)
    assert sync_cache.is_snapshot_populated() is True


# --- refresh_snapshot ------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_snapshot_populates_from_the_redis_store():
    store = AsyncMock()
    store.get_all_by_model.return_value = {"claude-sonnet-4-0": _PRICE}

    with patch("llm_shared.pricing.redis_store.PricingRedisStore", return_value=store):
        count = await sync_cache.refresh_snapshot()

    assert count == 1
    assert sync_cache.get_cached_price("claude-sonnet-4-0") is _PRICE


@pytest.mark.asyncio
async def test_refresh_snapshot_replaces_a_stale_snapshot_with_a_fresh_one(monkeypatch):
    monkeypatch.setattr(sync_cache, "MAX_SNAPSHOT_AGE_S", 10)
    _populate({"old-model": _PRICE}, age_s=100)

    store = AsyncMock()
    store.get_all_by_model.return_value = {"claude-sonnet-4-0": _PRICE}
    with patch("llm_shared.pricing.redis_store.PricingRedisStore", return_value=store):
        await sync_cache.refresh_snapshot()

    assert sync_cache.get_cached_price("old-model") is None
    assert sync_cache.get_cached_price("claude-sonnet-4-0") is _PRICE


# --- PricingCacheScheduler._tick: a failed refresh cannot make pricing look fresh ---


@pytest.mark.asyncio
async def test_a_failed_tick_keeps_the_previous_snapshot_unchanged():
    """#16316's cold-cache rule, exercised through the scheduler's own tick.

    Mirrors #16233 AC3 ("a failed refresh cannot make pricing look fresh"):
    a tick that raises must neither clear `_snapshot` nor bump its
    `fetched_at` -- either would let a Redis outage masquerade as a healthy,
    freshly-refreshed cache.
    """
    _populate({"claude-sonnet-4-0": _PRICE}, age_s=5)
    snapshot_before = sync_cache._snapshot

    scheduler = sync_cache.PricingCacheScheduler()
    with patch.object(sync_cache, "refresh_snapshot", AsyncMock(side_effect=RuntimeError("redis down"))):
        await scheduler._tick()

    assert sync_cache._snapshot is snapshot_before
    assert sync_cache.get_cached_price("claude-sonnet-4-0") is _PRICE
