# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Central cache coordinator with memory-pressure-aware eviction."""

import asyncio
import logging
from typing import Any, Dict, Optional

from .protocols import CacheProtocol

logger = logging.getLogger(__name__)


class CacheCoordinator:
    """
    Orchestrates all registered caches with memory-aware eviction.

    Singleton pattern ensures a single coordinator manages all caches.

    Features:
    - Register/unregister caches dynamically
    - Monitor system memory pressure via psutil
    - Coordinate eviction across all caches when pressure detected
    - Provide unified statistics

    Usage:
        coordinator = CacheCoordinator.get_instance()
        coordinator.register(my_cache)
        await coordinator.check_pressure()
        stats = coordinator.get_unified_stats()
    """

    _instance: Optional["CacheCoordinator"] = None

    def __init__(self):
        self._caches: Dict[str, CacheProtocol] = {}
        self._pressure_threshold = 0.80  # 80% system memory
        self._eviction_ratio = 0.20  # Evict 20% per cache
        self._pressure_triggered_count = 0
        self._lock = asyncio.Lock()
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "CacheCoordinator":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    def register(self, cache: CacheProtocol) -> None:
        """
        Register a cache for coordinated management.

        Args:
            cache: Cache implementing CacheProtocol

        Raises:
            TypeError: If cache doesn't implement CacheProtocol
        """
        if not isinstance(cache, CacheProtocol):
            raise TypeError(f"Cache must implement CacheProtocol, got {type(cache)}")
        self._caches[cache.name] = cache
        logger.info(f"Registered cache: {cache.name} (max_size={cache.max_size})")

    def unregister(self, name: str) -> bool:
        """
        Unregister a cache by name.

        Returns:
            True if cache was found and removed, False otherwise
        """
        if name in self._caches:
            del self._caches[name]
            logger.info(f"Unregistered cache: {name}")
            return True
        return False

    def get_memory_percent(self) -> float:
        """Get current system memory usage percentage."""
        try:
            import psutil

            return psutil.virtual_memory().percent / 100.0
        except ImportError:
            logger.warning("psutil not available, cannot monitor memory")
            return 0.0

    async def check_pressure(self) -> bool:
        """
        Check memory pressure, trigger eviction if needed.

        Returns:
            True if eviction was triggered, False otherwise
        """
        async with self._lock:
            mem_percent = self.get_memory_percent()
            if mem_percent > self._pressure_threshold:
                logger.warning(f"Memory pressure detected: {mem_percent:.1%}")
                await self._coordinated_evict()
                self._pressure_triggered_count += 1
                return True
            return False

    async def _coordinated_evict(self) -> Dict[str, int]:
        """
        Evict from all caches proportionally.

        Returns:
            Dict mapping cache names to number of items evicted
        """
        results = {}
        for name, cache in self._caches.items():
            evict_count = int(cache.size * self._eviction_ratio)
            if evict_count > 0:
                evicted = cache.evict(evict_count)
                results[name] = evicted
                logger.info(f"Evicted {evicted} items from {name}")
        return results

    def get_unified_stats(self) -> Dict[str, Any]:
        """
        Aggregate stats from all registered caches.

        Returns:
            Dict with cache stats, totals, and system info
        """
        cache_stats = {}
        total_items = 0
        total_capacity = 0

        for name, cache in self._caches.items():
            stats = cache.get_stats()
            cache_stats[name] = stats
            total_items += cache.size
            total_capacity += cache.max_size if cache.max_size > 0 else 0

        return {
            "caches": cache_stats,
            "registered_count": len(self._caches),
            "total_items": total_items,
            "total_capacity": total_capacity,
            "pressure_threshold": self._pressure_threshold,
            "eviction_ratio": self._eviction_ratio,
            "pressure_triggered_count": self._pressure_triggered_count,
            "system_memory_percent": self.get_memory_percent(),
        }

    def configure(
        self,
        pressure_threshold: Optional[float] = None,
        eviction_ratio: Optional[float] = None,
    ) -> None:
        """
        Configure coordinator settings.

        Args:
            pressure_threshold: Memory usage % to trigger eviction (0.0-1.0)
            eviction_ratio: % of each cache to evict (0.0-1.0)
        """
        if pressure_threshold is not None:
            self._pressure_threshold = max(0.0, min(1.0, pressure_threshold))
        if eviction_ratio is not None:
            self._eviction_ratio = max(0.0, min(1.0, eviction_ratio))


def get_cache_coordinator() -> CacheCoordinator:
    """Get the global cache coordinator instance."""
    return CacheCoordinator.get_instance()
