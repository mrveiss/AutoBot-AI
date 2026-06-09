# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Cache tier benchmark — measure L1 vs L2 hit latency.

Inspired by flash-moe's "Trust the OS" finding (removing custom cache = +38%).
Usage: python -m benchmarks.cache_benchmark
"""

import logging
import statistics
import time
from typing import Any, Dict, List

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from llm_shared.cache import CachedResponse, LLMResponseCache

logger = get_logger(__name__)


async def benchmark_l1_hit(cache: LLMResponseCache, keys: List[str]) -> List[float]:
    """Measure L1 cache hit latencies in microseconds."""
    latencies = []
    for key in keys:
        start = time.perf_counter_ns()
        await cache.get(key)
        elapsed_us = (time.perf_counter_ns() - start) / 1000
        latencies.append(elapsed_us)
    return latencies


async def benchmark_l2_hit(cache: LLMResponseCache, keys: List[str]) -> List[float]:
    """Measure L2-only hit latencies (bypass L1 by clearing it)."""
    latencies = []
    for key in keys:
        cache._memory_cache.pop(key, None)
        if key in cache._memory_cache_access:
            cache._memory_cache_access.remove(key)
        start = time.perf_counter_ns()
        await cache.get(key)
        elapsed_us = (time.perf_counter_ns() - start) / 1000
        latencies.append(elapsed_us)
    return latencies


async def run_benchmark(num_entries: int = 100, num_reads: int = 1000) -> Dict[str, Any]:
    """Run the full L1 vs L2 benchmark."""
    cache = LLMResponseCache(memory_cache_max_size=num_entries * 2, redis_ttl=300)

    keys: List[str] = []
    for i in range(num_entries):
        messages = [{"role": "user", "content": f"Test query {i}"}]
        key = cache.generate_cache_key(messages, "test-model", 0.7)
        response = CachedResponse(
            content=f"Response {i}" * 50,
            model="test-model",
            tokens_used=100,
        )
        await cache.set(key, response)
        keys.append(key)

    for key in keys[:10]:
        await cache.get(key)

    read_keys = (keys * ((num_reads // len(keys)) + 1))[:num_reads]
    l1_latencies = await benchmark_l1_hit(cache, read_keys)
    l2_latencies = await benchmark_l2_hit(cache, read_keys)

    l1_mean = statistics.mean(l1_latencies)
    l2_mean = statistics.mean(l2_latencies)

    results: Dict[str, Any] = {
        "num_entries": num_entries,
        "num_reads": num_reads,
        "l1": {
            "mean_us": l1_mean,
            "median_us": statistics.median(l1_latencies),
            "p99_us": sorted(l1_latencies)[int(len(l1_latencies) * 0.99)],
        },
        "l2": {
            "mean_us": l2_mean,
            "median_us": statistics.median(l2_latencies),
            "p99_us": sorted(l2_latencies)[int(len(l2_latencies) * 0.99)],
        },
        "speedup_mean": l2_mean / max(l1_mean, 0.01),
    }

    logger.info("=== Cache Tier Benchmark Results ===")
    logger.info("Entries: %d, Reads: %d", num_entries, num_reads)
    logger.info(
        "L1 mean: %.1fus  median: %.1fus  p99: %.1fus",
        results["l1"]["mean_us"],
        results["l1"]["median_us"],
        results["l1"]["p99_us"],
    )
    logger.info(
        "L2 mean: %.1fus  median: %.1fus  p99: %.1fus",
        results["l2"]["mean_us"],
        results["l2"]["median_us"],
        results["l2"]["p99_us"],
    )
    logger.info("L1 speedup: %.1fx over L2", results["speedup_mean"])

    if results["speedup_mean"] < 2.0:
        logger.info("Decision: L1 adds <2x benefit. Consider removing.")
    elif results["speedup_mean"] < 10.0:
        logger.info("Decision: L1 adds moderate benefit. Keep if hit rate high.")
    else:
        logger.info("Decision: L1 adds significant benefit. Keep L1 cache.")

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_or_schedule(run_benchmark())
