# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`PricingCacheScheduler`'s tick contract (#16230, #16233 AC3).

Separate from `sync_cache_test.py` because this is the half that needs
`llc.scheduler.base`, and therefore Python 3.11+. Keeping it here means a
sub-floor interpreter loses these tests and nothing else -- rather than losing
every cache test at collect time, which is what the combined file did.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from llm_shared.pricing import sync_cache, sync_cache_scheduler
from llm_shared.pricing.sources import ModelPricing

_PRICE = ModelPricing(provider="anthropic", model_id="claude-sonnet-4-0", input_per_1m=3.0, output_per_1m=15.0)


@pytest.fixture(autouse=True)
def _cold_cache():
    sync_cache._reset_for_tests()
    yield
    sync_cache._reset_for_tests()


def _populate(prices: dict, age_s: float = 0.0) -> None:
    sync_cache._snapshot = sync_cache._Snapshot(prices=prices, fetched_at=time.monotonic() - age_s)


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

    scheduler = sync_cache_scheduler.PricingCacheScheduler()
    with patch.object(sync_cache, "refresh_snapshot", AsyncMock(side_effect=RuntimeError("redis down"))):
        await scheduler._tick()

    assert sync_cache._snapshot is snapshot_before
    assert sync_cache.get_cached_price("claude-sonnet-4-0") is _PRICE
