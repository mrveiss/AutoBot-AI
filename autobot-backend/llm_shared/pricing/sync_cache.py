# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Synchronous, process-local mirror of `PricingRedisStore` (#16230, #16316).

`llm_cost_tracker.py::calculate_cost` and `tiered_routing/cost_router.py::
_blended_cost` are both plain `def`s reached from hot paths -- the router
scores candidate models to pick one, and neither can `await` a Redis
round-trip without either going async themselves (an untraced ripple to every
caller) or putting network I/O in a routing decision that is currently pure
in-memory. `budget.py::ingest_cost_event` is already async and could call
`PricingRedisStore` directly, but reads this same snapshot instead, so there
is one price-lookup path, not two that can drift apart.

This module never talks to Redis on the request path. A `PricingCacheScheduler`
(a `PollLoopScheduler`, #9842 -- its first use outside `llc/scheduler/`, since
nothing about it is LLC-specific) refreshes the snapshot periodically by
reading `PricingRedisStore`, which the `pricing-refresh-daily` beat task
already populates from the live catalogues (#16229). This is a mirror of that
existing machinery, not a second refresh path: this process never calls
LiteLLM/OpenRouter itself.

**The cold-cache rule (#16316), the one thing this module exists to get
right:** a snapshot that has never been populated is "cannot compute", not
"unpriced", and never a fabricated $0 -- the exact distinction #15860 protects
for the "genuinely never priced" case. `get_cached_price` raises
`PricingCacheCold` for that state, distinct from returning `None` for "the
snapshot is real and this model is not in it". A caller must not conflate the
two, and must not treat either as authorization to charge zero -- only
`autobot_shared.local_models.is_local_model` does that, checked by the caller
BEFORE this module is consulted at all, because a local model's zero has
nothing to do with whether a pricing snapshot exists.

The same rule extends to a snapshot that WAS populated and has since gone
stale: a refresh that keeps failing degrades "Redis had a hiccup" into "Redis
has been down for a week" with no bound, and a week-old price served through a
budget-enforcement path with no signal is worse than a refusal -- refusal is
visible, a stale number is a fact-shaped guess. `get_cached_price` tracks each
snapshot's `fetched_at` and raises `PricingCacheStale` (a `PricingCacheCold`
subclass) past `MAX_SNAPSHOT_AGE_S`, so a sustained outage fails the same way
a cold cache does rather than serving arbitrarily old numbers silently.

`PollLoopScheduler._tick()` runs immediately on `.start()`, before any wait
(see its own docstring) -- so the cold window is "however long one Redis read
takes", not up to a full refresh interval.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from llc.scheduler.base import PollLoopScheduler

if TYPE_CHECKING:
    from llm_shared.pricing.sources import ModelPricing

logger = get_logger(__name__)

#: How often this process re-reads Redis into its own memory. Independent of
#: `PricingRedisStore.REFRESH_INTERVAL_HOURS` (how often the beat task refreshes
#: Redis FROM the live catalogues) -- this only needs to stay close enough to
#: that upstream write to be a mirror, and a short interval also recovers a
#: worker that restarted mid-cycle quickly rather than leaving it cold for
#: however long is left of the daily cadence.
LOCAL_CACHE_REFRESH_INTERVAL_S: int = env_int("AUTOBOT_PRICING_LOCAL_CACHE_REFRESH_INTERVAL_S", 300)

#: How old the snapshot may get before `get_cached_price` stops trusting it.
#: A failed tick keeps the previous snapshot rather than clearing it (see
#: `PricingCacheScheduler._tick`), which is correct for one Redis hiccup --
#: but with no bound that same behaviour degrades into serving arbitrarily
#: old prices through a budget-enforcement path with no signal that anything
#: is wrong. 12 missed ticks at the default refresh interval (5 min each) --
#: long enough to ride out a brief blip, short enough that a real, sustained
#: outage is caught before the snapshot is meaningfully stale. Independent of
#: `LOCAL_CACHE_REFRESH_INTERVAL_S`: that is how often this process retries,
#: this is how many failed retries it takes before the result is no longer
#: trusted.
MAX_SNAPSHOT_AGE_S: int = env_int("AUTOBOT_PRICING_LOCAL_CACHE_MAX_AGE_S", 3600)


class PricingCacheCold(Exception):
    """The local pricing snapshot has never been populated.

    Distinct from "populated, and this model is unpriced" -- that case returns
    `None` from `get_cached_price`, not this. A caller seeing this exception
    knows nothing about whether the model in question is priced; the snapshot
    has not been read from Redis even once yet.
    """


class PricingCacheStale(PricingCacheCold):
    """The local pricing snapshot is real but older than `MAX_SNAPSHOT_AGE_S`.

    A subclass of `PricingCacheCold`, not a sibling, so every existing
    `except PricingCacheCold` (`budget.py::ingest_cost_event`) keeps refusing
    when a refresh stops succeeding instead of never having started -- the two
    states mean the same thing to a caller: "cannot compute a trustworthy
    price right now". Kept as a distinct subclass, not folded into the same
    class, so a caller that does care can still tell "never populated" apart
    from "was populated, now too old to trust".
    """


@dataclass(frozen=True)
class _Snapshot:
    """The cached prices plus when they were fetched, so age is part of the value.

    `time.monotonic()`, not wall-clock: this is only ever compared against
    another `time.monotonic()` reading taken in the same process, and must
    not jump backwards or forwards with a system clock adjustment.
    """

    prices: dict[str, "ModelPricing"]
    fetched_at: float


# Module-level, not per-instance: every sync caller in this process shares one
# mirror, matching the single Redis store it mirrors. `None` is the sentinel
# for "never populated" -- distinguished from a `_Snapshot` with an empty
# `prices` dict ("populated; the catalogue is genuinely empty"), which the
# cold-cache rule above requires.
_snapshot: "_Snapshot | None" = None


async def refresh_snapshot() -> int:
    """Re-read `PricingRedisStore`'s by-model index into `_snapshot`.

    Returns the number of models in the new snapshot. Replaces the module
    global with a freshly-built `_Snapshot` in one assignment -- readers never
    see a partially-populated snapshot, only the previous complete one or the
    new complete one, because a name rebind is atomic under the GIL and this
    process is single-threaded (one asyncio event loop).
    """
    global _snapshot
    from llm_shared.pricing.redis_store import PricingRedisStore

    store = PricingRedisStore()
    new_prices = await store.get_all_by_model()
    _snapshot = _Snapshot(prices=new_prices, fetched_at=time.monotonic())
    return len(new_prices)


def _live_snapshot() -> _Snapshot:
    """The current `_Snapshot`, after the cold- and stale-cache checks.

    Shared by every reader below so "cannot compute right now" is decided in
    exactly one place -- `get_cached_price` and `get_cached_snapshot` must
    refuse under the same conditions, or a caller could dodge the freshness
    bound by switching which one it calls.
    """
    if _snapshot is None:
        raise PricingCacheCold(
            "pricing snapshot has not been read from Redis yet -- PricingCacheScheduler "
            "has not completed its first tick"
        )
    age_s = time.monotonic() - _snapshot.fetched_at
    if age_s > MAX_SNAPSHOT_AGE_S:
        raise PricingCacheStale(
            f"pricing snapshot is {age_s:.0f}s old, past the {MAX_SNAPSHOT_AGE_S}s freshness bound "
            "-- PricingCacheScheduler has not completed a successful refresh in that time"
        )
    return _snapshot


def get_cached_price(model_id: str) -> "ModelPricing | None":
    """The cached price for *model_id*, or `None` if the snapshot has it absent.

    Raises `PricingCacheCold` if the snapshot has never been populated at all,
    or `PricingCacheStale` (a `PricingCacheCold` subclass) if it was populated
    but the last successful refresh is older than `MAX_SNAPSHOT_AGE_S` -- see
    the module docstring for why neither of those is the same as `None`.
    """
    return _live_snapshot().prices.get(model_id.lower())


def get_cached_snapshot() -> dict[str, "ModelPricing"]:
    """Every cached model->price entry, for a caller that must scan them all.

    `llm_cost_tracker.py::calculate_cost` prefix-matches a model id against
    every known key (`sorted(MODEL_PRICING, key=len, reverse=True)` in the
    table this replaces) rather than looking up one exact id, so it needs the
    whole snapshot, not a single price. Same cold/stale rules as
    `get_cached_price` -- a caller iterating a snapshot that is either
    nonexistent or untrustworthy would be scanning fabricated data and not
    know it.
    """
    return _live_snapshot().prices


def is_snapshot_populated() -> bool:
    """Whether `refresh_snapshot` has completed at least once in this process.

    Says nothing about staleness -- a snapshot past `MAX_SNAPSHOT_AGE_S` is
    still "populated" by this check; `get_cached_price` is what enforces the
    freshness bound.
    """
    return _snapshot is not None


def _reset_for_tests() -> None:
    """Test-only: return the module to its cold, never-populated state."""
    global _snapshot
    _snapshot = None


class PricingCacheScheduler(PollLoopScheduler):
    """Periodically mirrors `PricingRedisStore` into this process's memory (#16230).

    First non-LLC use of `PollLoopScheduler` -- nothing about the base class
    is LLC-specific, and hand-rolling a second poll loop with its own
    cancellation-safety contract was the alternative this reuses instead of
    repeating.
    """

    _task_name = "PricingCacheScheduler"

    def __init__(self, poll_interval: float = LOCAL_CACHE_REFRESH_INTERVAL_S) -> None:
        super().__init__(poll_interval)

    async def _tick(self) -> None:
        try:
            count = await refresh_snapshot()
            logger.info("PricingCacheScheduler: mirrored %d model price(s) from Redis", count)
        except Exception:
            # #16316: a failed refresh must not clear an already-populated
            # snapshot -- that would turn "Redis had a hiccup" into "every
            # model looks unpriced". `refresh_snapshot` only replaces
            # `_snapshot` on success (the exception is raised before the
            # module global is touched), so a failed tick here leaves the
            # previous snapshot, stale but real, in place.
            logger.exception("PricingCacheScheduler: refresh failed, keeping the previous snapshot")


async def start_pricing_cache_scheduler(app) -> None:
    """Start `PricingCacheScheduler` and store it on `app.state` (#16230).

    Defined here, not in `initialization/lifespan.py`, which is at its
    file-size ratchet ceiling -- the scheduler this starts already lives in
    this module, so this is where its own startup wrapper belongs too, matched
    against the try/except-and-store-on-app.state shape every sibling
    scheduler in that file uses.

    NON-CRITICAL: a failed start leaves the snapshot permanently cold, which
    every caller already treats as "cannot compute" rather than crashing --
    the same posture `_init_llm_key_rotation_scheduler` and its siblings take
    for their own optional background work.
    """
    logger.info("Pricing cache scheduler: starting")
    try:
        scheduler = PricingCacheScheduler()
        scheduler.start()
        app.state.pricing_cache_scheduler = scheduler
        logger.info("Pricing cache scheduler: started")
    except Exception as exc:
        logger.warning("Pricing cache scheduler failed to start (non-critical): %s", exc)
        app.state.pricing_cache_scheduler = None


async def stop_pricing_cache_scheduler(app) -> None:
    """Drain `PricingCacheScheduler`, mirroring the community-clustering shutdown shape."""
    scheduler = getattr(app.state, "pricing_cache_scheduler", None)
    if scheduler:
        await scheduler.aclose()
