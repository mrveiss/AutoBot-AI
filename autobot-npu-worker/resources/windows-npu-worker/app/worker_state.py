# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Lock-guarded in-process state shared across request handlers (#15642).

Both classes here exist for the same reason (Issue #68): handlers run
concurrently on one event loop, and the embedding cache and the stats counters
were being read and written from several of them at once. Each guards its own
state with an ``asyncio.Lock`` and exposes only awaitable accessors, so no
caller can touch the underlying mapping directly.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import asyncio
import time
from collections import OrderedDict
from typing import Any, Dict, List

from worker_settings import DEFAULT_EMBEDDING_CACHE_SIZE, DEFAULT_EMBEDDING_CACHE_TTL

# =============================================================================
# LRU Cache Implementation (Issue #68 - Bounded cache to prevent memory growth)
# =============================================================================


class LRUCache:
    """
    Thread-safe LRU cache with TTL support.

    Fixes unbounded cache growth race condition identified in Issue #68.
    """

    def __init__(
        self,
        max_size: int = DEFAULT_EMBEDDING_CACHE_SIZE,
        ttl: int = DEFAULT_EMBEDDING_CACHE_TTL,
    ):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Get item from cache, returns None if not found or expired."""
        async with self._lock:
            if key not in self._cache:
                return None

            item = self._cache[key]
            # Check TTL expiration
            if time.time() - item["timestamp"] > self._ttl:
                del self._cache[key]
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return item["value"]

    async def set(self, key: str, value: Any) -> None:
        """Set item in cache with automatic eviction if full."""
        async with self._lock:
            # If key exists, update and move to end
            if key in self._cache:
                self._cache[key] = {"value": value, "timestamp": time.time()}
                self._cache.move_to_end(key)
                return

            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            # Add new item
            self._cache[key] = {"value": value, "timestamp": time.time()}

    async def size(self) -> int:
        """Get current cache size."""
        async with self._lock:
            return len(self._cache)

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()


# =============================================================================
# Thread-safe Stats Counter (Issue #68 - Race condition fix)
# =============================================================================


class ThreadSafeStats:
    """
    Thread-safe statistics counter.

    Fixes stats counter race condition identified in Issue #68.
    """

    def __init__(self):
        self._stats = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "average_response_time_ms": 0.0,
            "npu_utilization_percent": 0.0,
            "embedding_generations": 0,
            "semantic_searches": 0,
            "cache_hits": 0,
        }
        self._lock = asyncio.Lock()
        self._response_times: List[float] = []

    async def increment(self, stat_name: str, amount: int = 1) -> None:
        """Thread-safe increment of a stat."""
        async with self._lock:
            if stat_name in self._stats:
                self._stats[stat_name] += amount

    async def record_response_time(self, time_ms: float) -> None:
        """Record a response time and update average."""
        async with self._lock:
            self._response_times.append(time_ms)
            # Keep only last 100 for rolling average
            if len(self._response_times) > 100:
                self._response_times.pop(0)
            self._stats["average_response_time_ms"] = sum(self._response_times) / len(self._response_times)

    async def set(self, stat_name: str, value: Any) -> None:
        """Thread-safe set of a stat value."""
        async with self._lock:
            self._stats[stat_name] = value

    async def get_all(self) -> Dict[str, Any]:
        """Get a copy of all stats."""
        async with self._lock:
            return dict(self._stats)

    async def get(self, stat_name: str) -> Any:
        """Get a single stat value."""
        async with self._lock:
            return self._stats.get(stat_name, 0)
