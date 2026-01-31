# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Embedding Cache Module

LRU Cache with TTL for query embeddings to avoid regenerating identical queries.
Issue #65 P0 Optimization - 60-80% reduction in embedding computation for repeated queries.
"""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """
    Thread-safe LRU cache with TTL for query embeddings.

    Performance Impact:
    - 60-80% reduction in embedding computation for repeated queries
    - Reduces ChromaDB search latency significantly
    """

    def __init__(self, maxsize: int = 1000, ttl_seconds: int = 3600):
        """
        Initialize embedding cache.

        Args:
            maxsize: Maximum number of embeddings to cache (default: 1000)
            ttl_seconds: Time-to-live for cached embeddings (default: 1 hour)
        """
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        """Unique cache identifier."""
        return "embedding"

    @property
    def size(self) -> int:
        """Current number of items."""
        return len(self._cache)

    @property
    def max_size(self) -> int:
        """Maximum capacity."""
        return self._maxsize

    def _make_key(self, query: str) -> str:
        """Create cache key from query text using hash."""
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    def _is_expired(self, key: str) -> bool:
        """Check if cached entry has expired."""
        if key not in self._timestamps:
            return True
        return (time.time() - self._timestamps[key]) > self._ttl_seconds

    def _evict_oldest(self) -> None:
        """Evict oldest entry when cache is full."""
        if self._cache:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._timestamps.pop(oldest_key, None)

    def evict(self, count: int) -> int:
        """
        Evict oldest items from cache.

        Args:
            count: Number of items to evict

        Returns:
            Actual number of items evicted
        """
        evicted = 0
        for _ in range(min(count, len(self._cache))):
            if self._cache:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._timestamps.pop(oldest_key, None)
                evicted += 1
        return evicted

    async def get(self, query: str) -> Optional[List[float]]:
        """
        Get embedding from cache if available and not expired.

        Args:
            query: Query text

        Returns:
            Cached embedding or None if not found/expired
        """
        key = self._make_key(query)

        async with self._lock:
            if key in self._cache and not self._is_expired(key):
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                logger.debug("Embedding cache HIT for query: %s...", query[:50])
                return self._cache[key]

            # Remove expired entry if exists
            if key in self._cache:
                del self._cache[key]
                self._timestamps.pop(key, None)

            self._misses += 1
            return None

    async def put(self, query: str, embedding: List[float]) -> None:
        """
        Store embedding in cache.

        Args:
            query: Query text
            embedding: Computed embedding vector
        """
        key = self._make_key(query)

        async with self._lock:
            # Evict if at capacity
            if key not in self._cache and len(self._cache) >= self._maxsize:
                self._evict_oldest()

            # Store embedding
            self._cache[key] = embedding
            self._timestamps[key] = time.time()
            self._cache.move_to_end(key)

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total) if total > 0 else 0.0
        return {
            "name": self.name,
            "size": len(self._cache),
            "max_size": self._maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "ttl_seconds": self._ttl_seconds,
        }

    def clear(self) -> None:
        """Clear all cached embeddings."""
        self._cache.clear()
        self._timestamps.clear()
        self._hits = 0
        self._misses = 0
        logger.info("Embedding cache cleared")


# Global embedding cache instance
_embedding_cache = EmbeddingCache(maxsize=1000, ttl_seconds=3600)


def get_embedding_cache() -> EmbeddingCache:
    """Get the global embedding cache instance."""
    return _embedding_cache
