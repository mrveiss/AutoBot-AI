# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Central cache coordinator with memory-pressure-aware eviction."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from utils.async_initializable import AsyncInitializable

from .protocols import CacheProtocol

logger = get_logger(__name__)


class CacheCoordinator(AsyncInitializable):
    """
    Orchestrates all registered caches with memory-aware eviction.

    Singleton pattern ensures a single coordinator manages all caches.

    Features:
    - Register/unregister caches dynamically
    - Monitor system memory pressure via psutil
    - Coordinate eviction across all caches when pressure detected
    - Provide unified statistics

    Issue: #743 - Memory Optimization (Phase 3.3)
    Issue: #3390 - Migrated to AsyncInitializable lazy-init pattern
    Reads default thresholds from SSOT config.cache.coordinator

    Usage:
        coordinator = await get_cache_coordinator()
        coordinator.register(my_cache)
        await coordinator.check_pressure()
        stats = coordinator.get_cache_stats()
    """

    _instance: "CacheCoordinator" | None = None

    def __init__(self):
        super().__init__(component_name="cache_coordinator")
        self._caches: Dict[str, CacheProtocol] = {}
        self._pressure_threshold: float = 0.0
        self._eviction_ratio: float = 0.0
        self._pressure_triggered_count = 0
        self._eviction_lock = asyncio.Lock()

    async def _initialize_impl(self) -> bool:
        """Load SSOT config values. No blocking I/O required."""
        # Issue #743: Read from SSOT config
        self._pressure_threshold = config.cache.coordinator.pressure_threshold
        self._eviction_ratio = config.cache.coordinator.eviction_ratio
        return True

    @classmethod
    def get_sync_instance(cls) -> "CacheCoordinator":
        """Get singleton instance synchronously (skips async init — call initialize() first)."""
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
        async with self._eviction_lock:
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

    def get_cache_stats(self) -> Dict[str, Any]:
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
        pressure_threshold: float | None = None,
        eviction_ratio: float | None = None,
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


async def get_cache_coordinator() -> CacheCoordinator:
    """Get and lazily initialize the global cache coordinator instance."""
    coordinator = CacheCoordinator.get_sync_instance()
    await coordinator.initialize()
    return coordinator
