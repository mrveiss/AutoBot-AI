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
        self.max_size = max_size
        self.cache: OrderedDict = OrderedDict()
        self.hits = 0
        self.misses = 0
        self._lock = threading.Lock()  # Lock for thread-safe cache access

    def get(self, key: str) -> Optional[Any]:
        """Get item from cache (thread-safe)"""
        with self._lock:
            if key in self.cache:
                # Move to end (most recently used)
                value = self.cache.pop(key)
                self.cache[key] = value
                self.hits += 1
                return value
            else:
                self.misses += 1
                return None

    def put(self, key: str, value: Any) -> None:
        """Put item in cache with LRU eviction (thread-safe)"""
        with self._lock:
            # Remove if exists
            if key in self.cache:
                self.cache.pop(key)

            # Add to end
            self.cache[key] = value

            # Enforce size limit
            while len(self.cache) > self.max_size:
                oldest_key = next(iter(self.cache))
                self.cache.pop(oldest_key)
                logger.debug(f"Evicted {oldest_key} from cache (LRU)")

    def evict(self, count: int) -> int:
        """Evict oldest N items (thread-safe)"""
        with self._lock:
            evicted = 0
            while evicted < count and self.cache:
                oldest_key = next(iter(self.cache))
                self.cache.pop(oldest_key)
                evicted += 1

            return evicted

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics (thread-safe)"""
        with self._lock:
            total_requests = self.hits + self.misses
            hit_rate = self.hits / total_requests if total_requests > 0 else 0.0

            return {
                "enabled": True,
                "size": len(self.cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
            }


__all__ = ["LRUCacheManager"]
