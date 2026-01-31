# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LRU Cache Manager - In-memory LRU caching with statistics
"""

import logging
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LRUCacheManager:
    """
    LRU cache implementation (ICacheManager)

    Responsibility: Provide in-memory LRU caching with statistics
    """

    def __init__(self, max_size: int = 1000):
        """Initialize LRU cache with specified maximum size and statistics."""
        self._max_size = max_size
        self._cache: OrderedDict = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()  # Lock for thread-safe cache access

    @property
    def name(self) -> str:
        """Unique cache identifier."""
        return "lru_memory"

    @property
    def size(self) -> int:
        """Current number of items."""
        with self._lock:
            return len(self._cache)

    @property
    def max_size(self) -> int:
        """Maximum capacity."""
        return self._max_size

    def get(self, key: str) -> Optional[Any]:
        """Get item from cache (thread-safe)"""
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                value = self._cache.pop(key)
                self._cache[key] = value
                self._hits += 1
                return value
            else:
                self._misses += 1
                return None

    def put(self, key: str, value: Any) -> None:
        """Put item in cache with LRU eviction (thread-safe)"""
        with self._lock:
            # Remove if exists
            if key in self._cache:
                self._cache.pop(key)

            # Add to end
            self._cache[key] = value

            # Enforce size limit
            while len(self._cache) > self._max_size:
                oldest_key = next(iter(self._cache))
                self._cache.pop(oldest_key)
                logger.debug("Evicted %s from cache (LRU)", oldest_key)

    def evict(self, count: int) -> int:
        """Evict oldest N items (thread-safe)"""
        with self._lock:
            evicted = 0
            while evicted < count and self._cache:
                oldest_key = next(iter(self._cache))
                self._cache.pop(oldest_key)
                evicted += 1

            return evicted

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

            return {
                "name": self.name,
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
            }

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics (thread-safe) - legacy method for backward compatibility."""
        stats = self.get_stats()
        stats["enabled"] = True
        return stats

    def clear(self) -> None:
        """Clear all items from cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


__all__ = ["LRUCacheManager"]
