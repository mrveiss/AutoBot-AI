# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The poll loop that keeps `sync_cache`'s mirror fresh, and its lifespan hooks.

Split out of `sync_cache.py` (#16230). The mirror is read by anything that
prices a model; the scheduler is started once, by the app. Keeping them in one
module meant `llc.scheduler.base` -- which hard-refuses to import below Python
3.11 -- was pulled in by every price read, putting an interpreter floor on
modules that schedule nothing. `sync_cache.py` now has no LLC dependency at all;
this module is where it belongs, because this is the only part that schedules.
"""

from __future__ import annotations

import asyncio

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger
from llc.scheduler.base import PollLoopScheduler
from llm_shared.pricing.sync_cache import LOCAL_CACHE_REFRESH_INTERVAL_S, refresh_snapshot

logger = get_logger(__name__)

#: Bound on the one refresh awaited before the app serves traffic. Long enough
#: for a healthy Redis round-trip, short enough that an unreachable one does not
#: hold up startup -- the cache then begins cold, which is a handled state.
#: Clamped to > 0 (#16230 review): `env_float` rejects malformed input but accepts
#: 0 and negatives, and `asyncio.wait_for` with either cancels the refresh
#: immediately -- turning the bound meant to CLOSE the cold-cache window into a
#: guarantee of it, silently, with the timeout log line to explain it away.
FIRST_REFRESH_TIMEOUT_S: float = env_float_clamped("AUTOBOT_PRICING_FIRST_REFRESH_TIMEOUT_S", 10.0, min_v=0.1)


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
        # One refresh awaited BEFORE the poll task, not left to the first tick
        # (#16230 review). `start()` creates the task without awaiting it, so
        # the cache stayed cold until that tick's Redis read returned -- and in
        # that window `budget.py::ingest_cost_event` converts cold to
        # UnpricedModel and rejects the request outright. It does not record a
        # zero cost; it refuses. Moving the scheduler earlier in lifespan only
        # narrows the window, it does not close it, because the width is a
        # Redis round-trip and not an ordering question.
        #
        # Bounded and non-fatal: a slow or unreachable Redis must not hold up
        # startup, and failing here leaves exactly the cold cache that every
        # caller already handles. What it buys is that the common case -- Redis
        # up -- has no window at all.
        try:
            count = await asyncio.wait_for(refresh_snapshot(), timeout=FIRST_REFRESH_TIMEOUT_S)
            logger.info("Pricing cache scheduler: seeded %d model price(s) before serving", count)
        except Exception as exc:  # noqa: BLE001 -- degrades to cold, which is a handled state
            logger.warning(
                "Pricing cache scheduler: initial refresh did not complete (%s); the cache starts "
                "cold and pricing-dependent requests will refuse until the first tick succeeds",
                exc,
            )

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
