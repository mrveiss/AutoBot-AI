# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LatencyRouter — routes to the provider with the lowest recent p95 latency.

Issue #6595: Latency-aware routing strategy.

Latency samples are stored in Redis as a sorted-set per model:
  Key:   llm:latency:{model_name}
  Score: epoch-seconds of the sample (used for sliding-window TTL)
  Value: "{epoch_s}:{latency_ms}"

``record_latency()`` must be called by the LLM caller after each response.
``route()`` is synchronous; it reads an in-process cache that a background
asyncio task refreshes every REFRESH_INTERVAL_S seconds.
"""

import asyncio
import time
from typing import Dict, List, Optional, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

from .complexity_scorer import TaskComplexityScorer
from .tier_config import ComplexityResult, TierConfig, TierMetrics

logger = get_logger(__name__)

WINDOW_SECONDS = 300  # 5-minute sliding window
REFRESH_INTERVAL_S = 30  # How often to refresh p95 from Redis
_P95_PERCENTILE = 0.95
_DEFAULT_P95_MS = 5_000.0  # Assumed latency for unknown models


class LatencyRouter:
    """
    Routes to the lowest-p95-latency model available for the request tier.

    p95 values are loaded from Redis on a background refresh cadence rather
    than on every call so ``route()`` stays synchronous and fast.
    """

    def __init__(self, config: TierConfig | None = None) -> None:
        self.config = config or TierConfig.from_config()
        self._scorer = TaskComplexityScorer(self.config)
        self._metrics = TierMetrics()
        # In-process p95 cache: {model_name: p95_ms}
        self._p95_cache: Dict[str, float] = {}
        self._last_refresh: float = 0.0
        self._refresh_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def route(
        self,
        messages: List[Dict],
        requested_model: str | None = None,
    ) -> Tuple[str, ComplexityResult]:
        complexity = self._scorer.score(messages)
        candidates = self._candidates(complexity)
        selected = self._lowest_latency(candidates)

        p95 = self._p95_cache.get(selected, _DEFAULT_P95_MS)
        result = ComplexityResult(
            score=complexity.score,
            factors=complexity.factors,
            tier="simple" if selected == self.config.models.simple else "complex",
            reasoning=f"LatencyRouter selected {selected} (p95={p95:.0f}ms over {WINDOW_SECONDS}s)",
        )
        self._metrics.record(result)
        logger.debug("LatencyRouter: %s (p95=%.0f ms)", selected, p95)
        return selected, result

    def get_metrics(self) -> Dict:
        base = self._metrics.to_dict()
        base["p95_cache"] = {k: round(v, 1) for k, v in self._p95_cache.items()}
        return base

    # ------------------------------------------------------------------ #
    # Latency recording (called by LLM caller after each response)         #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def record_latency(model: str, latency_ms: float) -> None:
        """
        Persist a latency sample to Redis for the given model.

        Fire-and-forget; failures are logged, not raised.
        """
        redis = await get_async_redis_client()
        if redis is None:
            return
        now = time.time()
        key = f"llm:latency:{model}"
        try:
            member = f"{now}:{latency_ms:.1f}"
            await redis.zadd(key, {member: now})
            # Prune samples outside the sliding window
            cutoff = now - WINDOW_SECONDS
            await redis.zremrangebyscore(key, "-inf", cutoff)
            # Cap cardinality to 1000 samples per model
            await redis.zremrangebyrank(key, 0, -1001)
        except Exception:
            logger.debug("LatencyRouter: failed to record latency for %s", model, exc_info=True)

    # ------------------------------------------------------------------ #
    # Background refresh                                                    #
    # ------------------------------------------------------------------ #

    async def start_refresh_task(self) -> None:
        """Start the background p95 refresh loop (call once at app startup)."""
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def _refresh_loop(self) -> None:
        while True:
            try:
                await self._refresh_p95()
            except Exception:
                logger.debug("LatencyRouter: p95 refresh error", exc_info=True)
            await asyncio.sleep(REFRESH_INTERVAL_S)

    async def _refresh_p95(self) -> None:
        redis = await get_async_redis_client()
        if redis is None:
            return
        models = [self.config.models.simple, self.config.models.complex]
        now = time.time()
        cutoff = now - WINDOW_SECONDS
        for model in models:
            key = f"llm:latency:{model}"
            try:
                members = await redis.zrangebyscore(key, cutoff, "+inf")
                latencies = [float(m.decode().split(":", 1)[1]) for m in members if b":" in m]
                if latencies:
                    latencies.sort()
                    idx = int(_P95_PERCENTILE * len(latencies))
                    self._p95_cache[model] = latencies[min(idx, len(latencies) - 1)]
            except Exception:
                logger.debug("LatencyRouter: failed to refresh p95 for %s", model, exc_info=True)
        self._last_refresh = now

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _candidates(self, complexity: ComplexityResult) -> List[str]:
        if complexity.is_simple:
            return [self.config.models.simple, self.config.models.complex]
        return [self.config.models.complex]

    def _lowest_latency(self, candidates: List[str]) -> str:
        if len(candidates) == 1:
            return candidates[0]
        return min(candidates, key=lambda m: self._p95_cache.get(m, _DEFAULT_P95_MS))


__all__ = ["LatencyRouter", "WINDOW_SECONDS"]
