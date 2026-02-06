# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Adaptive Memory Manager - Intelligent Memory Management with LRU Caching
Addresses unbounded growth in chat history, source attribution, and conversation data
Implements LRU eviction and adaptive cleanup to prevent memory growth
"""

import asyncio
import gc
import logging
from collections import OrderedDict
from typing import Any, Dict, Optional

import psutil

logger = logging.getLogger(__name__)


class AdaptiveMemoryManager:
    """
    Intelligent memory management with LRU eviction and adaptive cleanup
    """

    def __init__(self):
        """Initialize memory manager with thresholds and LRU cache storage."""
        self.memory_threshold = 0.8  # 80% memory usage threshold
        self.cleanup_percentage = 0.2  # Clean up 20% of data
        self.monitoring_interval = 60  # Check every minute
        self.lru_caches = {}
        self.monitoring_task = None

    def create_lru_cache(self, name: str, max_size: int = 1000) -> OrderedDict:
        """Create named LRU cache with size limit"""
        if name not in self.lru_caches:
            self.lru_caches[name] = {
                "cache": OrderedDict(),
                "max_size": max_size,
                "hits": 0,
                "misses": 0,
            }
        return self.lru_caches[name]["cache"]

    def get_from_cache(self, cache_name: str, key: str) -> Optional[Any]:
        """Get item from LRU cache"""
        if cache_name not in self.lru_caches:
            return None

        cache_info = self.lru_caches[cache_name]
        cache = cache_info["cache"]

        if key in cache:
            # Move to end (most recently used)
            value = cache.pop(key)
            cache[key] = value
            cache_info["hits"] += 1
            return value
        else:
            cache_info["misses"] += 1
            return None

    def put_in_cache(self, cache_name: str, key: str, value: Any):
        """Put item in LRU cache with size management"""
        if cache_name not in self.lru_caches:
            self.create_lru_cache(cache_name)

        cache_info = self.lru_caches[cache_name]
        cache = cache_info["cache"]
        max_size = cache_info["max_size"]

        # Remove if already exists
        if key in cache:
            cache.pop(key)

        # Add new item
        cache[key] = value

        # Enforce size limit
        while len(cache) > max_size:
            oldest_key = next(iter(cache))
            cache.pop(oldest_key)
            logger.debug("Evicted %s from %s cache", oldest_key, cache_name)

    def get_cache_stats(self) -> Dict[str, Dict]:
        """Get statistics for all caches"""
        stats = {}
        for name, cache_info in self.lru_caches.items():
            cache = cache_info["cache"]
            hit_rate = 0
            total_requests = cache_info["hits"] + cache_info["misses"]
            if total_requests > 0:
                hit_rate = cache_info["hits"] / total_requests

            stats[name] = {
                "size": len(cache),
                "max_size": cache_info["max_size"],
                "hit_rate": hit_rate,
                "hits": cache_info["hits"],
                "misses": cache_info["misses"],
            }
        return stats

    def _cleanup_cache_entries(self, cache: "OrderedDict", count: int) -> int:
        """Remove oldest entries from a cache (Issue #315: extracted).

        Args:
            cache: The OrderedDict cache to clean
            count: Number of entries to remove

        Returns:
            Number of entries actually removed
        """
        removed = 0
        for _ in range(count):
            if not cache:
                break
            removed_key = next(iter(cache))
            cache.pop(removed_key)
            removed += 1
        return removed

    def _cleanup_all_caches(self) -> int:
        """Clean up all LRU caches by cleanup percentage (Issue #315: extracted).

        Returns:
            Total number of entries cleaned
        """
        total_cleaned = 0
        for cache_name, cache_info in self.lru_caches.items():
            cache = cache_info["cache"]
            cleanup_count = int(len(cache) * self.cleanup_percentage)
            if cleanup_count > 0:
                total_cleaned += self._cleanup_cache_entries(cache, cleanup_count)
        return total_cleaned

    async def adaptive_memory_cleanup(self):
        """Adaptive memory cleanup based on system pressure.

        Issue #315: Refactored to use helper methods for reduced nesting.
        """
        try:
            memory = psutil.virtual_memory()

            if memory.percent <= (self.memory_threshold * 100):
                logger.debug("Memory usage normal: %.1f%%", memory.percent)
                return

            logger.warning(
                f"Memory usage high: {memory.percent:.1f}%, starting cleanup"
            )

            # Clean up LRU caches using helper
            total_cleaned = self._cleanup_all_caches()
            logger.info("Cleaned %s cache entries", total_cleaned)

            # Force garbage collection
            collected = gc.collect()

            # Check memory after cleanup
            memory_after = psutil.virtual_memory()
            logger.info(
                "Memory cleanup completed: %.1f%% -> %.1f%%, collected %d objects",
                memory.percent,
                memory_after.percent,
                collected,
            )

        except Exception as e:
            logger.error("Error during memory cleanup: %s", e)

    async def start_memory_monitor(self):
        """Start background memory monitoring"""
        logger.info("Starting adaptive memory monitor")

        try:
            while True:
                await self.adaptive_memory_cleanup()
                await asyncio.sleep(self.monitoring_interval)
        except asyncio.CancelledError:
            logger.info("Memory monitor stopped")
            raise
        except Exception as e:
            logger.error("Memory monitor error: %s", e)

    def start_monitoring(self):
        """Start memory monitoring task"""
        if self.monitoring_task is None or self.monitoring_task.done():
            self.monitoring_task = asyncio.create_task(self.start_memory_monitor())
            logger.info("Memory monitoring task started")

    def stop_monitoring(self):
        """Stop memory monitoring task"""
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            logger.info("Memory monitoring task stopped")

    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics"""
        memory = psutil.virtual_memory()
        return {
            "total_gb": memory.total / (1024**3),
            "used_gb": memory.used / (1024**3),
            "available_gb": memory.available / (1024**3),
            "percent": memory.percent,
            "threshold": self.memory_threshold * 100,
        }

    def cleanup_specific_cache(self, cache_name: str, percentage: float = 0.5):
        """Clean up specific cache by percentage"""
        if cache_name not in self.lru_caches:
            logger.warning("Cache %s not found", cache_name)
            return 0

        cache = self.lru_caches[cache_name]["cache"]
        cleanup_count = int(len(cache) * percentage)

        cleaned = 0
        for _ in range(cleanup_count):
            if cache:
                removed_key = next(iter(cache))
                cache.pop(removed_key)
                cleaned += 1

        logger.info("Cleaned %s entries from %s cache", cleaned, cache_name)
        return cleaned


# Global adaptive memory manager instance (thread-safe)
import threading

_memory_manager = None
_memory_manager_lock = threading.Lock()


def get_adaptive_memory_manager() -> AdaptiveMemoryManager:
    """Get global adaptive memory manager instance (thread-safe)"""
    global _memory_manager
    if _memory_manager is None:
        with _memory_manager_lock:
            # Double-check after acquiring lock
            if _memory_manager is None:
                _memory_manager = AdaptiveMemoryManager()
                _memory_manager.start_monitoring()
    return _memory_manager


# Helper functions for common memory operations
def create_managed_cache(name: str, max_size: int = 1000) -> OrderedDict:
    """Create a managed LRU cache"""
    manager = get_adaptive_memory_manager()
    return manager.create_lru_cache(name, max_size)


def cache_get(cache_name: str, key: str) -> Optional[Any]:
    """Get item from managed cache"""
    manager = get_adaptive_memory_manager()
    return manager.get_from_cache(cache_name, key)


def cache_put(cache_name: str, key: str, value: Any):
    """Put item in managed cache"""
    manager = get_adaptive_memory_manager()
    return manager.put_in_cache(cache_name, key, value)
