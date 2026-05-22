# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Embedding Cache Module

Adaptive Replacement Cache (ARC) with TTL for query embeddings to avoid
regenerating identical queries. ARC dynamically balances recency (T1) and
frequency (T2) lists, providing scan-resistant eviction superior to fixed LRU.

Issue #65 P0 Optimization - 60-80% reduction in embedding computation for repeated queries.
Issue #8156 - Replace fixed LRU with ARC for hot-query resilience.
"""

import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.ttl_constants import TTL_1_HOUR

logger = get_logger(__name__)


class EmbeddingCache:
    """
    Thread-safe Adaptive Replacement Cache (ARC) with TTL for query embeddings.

    ARC maintains four lists:
    - T1: recently seen once (recency list)
    - T2: seen more than once (frequency list)
    - B1: ghost list of recently evicted T1 keys (no embeddings stored)
    - B2: ghost list of recently evicted T2 keys (no embeddings stored)

    The adaptive parameter p tracks the target size of T1. Hits in B1 ghost
    increase p (bias toward recency); hits in B2 ghost decrease p (bias toward
    frequency). This makes ARC resilient to both scan workloads and repeated
    hot-key access patterns.

    Performance Impact:
    - 60-80% reduction in embedding computation for repeated queries
    - Reduces ChromaDB search latency significantly
    - Scan-resistant: one-time sequential scans do not evict hot entries

    Issue: #743 - Memory Optimization (Phase 3.3)
    Issue: #8156 - ARC replacement for fixed LRU
    Reads default maxsize from SSOT config.cache.l1.embedding
    """

    def __init__(self, maxsize: int = None, ttl_seconds: int = TTL_1_HOUR):
        """
        Initialize ARC embedding cache.

        Args:
            maxsize: Maximum items across T1+T2 (default from SSOT config.cache.l1.embedding)
            ttl_seconds: Time-to-live for cached embeddings (default: 1 hour)
        """
        # Issue #743: Read from SSOT config, allow explicit override
        self._maxsize = maxsize if maxsize is not None else config.cache.l1.embedding
        self._ttl_seconds = ttl_seconds

        # ARC lists: T1 (recent once), T2 (frequent), B1/B2 (ghost directories)
        # OrderedDict maintains insertion order — oldest key is first (LRU tail).
        self._t1: OrderedDict[str, List[float]] = OrderedDict()
        self._t2: OrderedDict[str, List[float]] = OrderedDict()
        self._b1: OrderedDict[str, None] = OrderedDict()  # ghost keys only
        self._b2: OrderedDict[str, None] = OrderedDict()  # ghost keys only

        # Timestamps cover T1 + T2 entries only
        self._timestamps: Dict[str, float] = {}

        # Adaptive target size of T1 (0 <= p <= maxsize)
        self._p: int = 0

        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Unique cache identifier."""
        return "embedding"

    @property
    def size(self) -> int:
        """Current number of live items (T1 + T2)."""
        return len(self._t1) + len(self._t2)

    @property
    def max_size(self) -> int:
        """Maximum capacity."""
        return self._maxsize

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_key(self, query: str) -> str:
        """Create cache key from query text using SHA-256 hash."""
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    def _is_expired(self, key: str) -> bool:
        """Return True if the cached entry has exceeded its TTL."""
        ts = self._timestamps.get(key)
        if ts is None:
            return True
        return (time.time() - ts) > self._ttl_seconds

    def _remove_live(self, key: str) -> None:
        """Remove a key from whichever live list (T1 or T2) contains it."""
        if key in self._t1:
            del self._t1[key]
        elif key in self._t2:
            del self._t2[key]
        self._timestamps.pop(key, None)

    def _replace(self) -> None:
        """
        ARC REPLACE sub-routine.

        Evicts the LRU entry from T1 (if |T1| > p or T2 is empty) or from T2,
        moving the evicted key to the corresponding ghost list (B1 or B2).
        Ghost lists are capped at maxsize entries each.
        """
        t1_len = len(self._t1)
        if t1_len > 0 and (t1_len > self._p or (len(self._b2) > 0 and t1_len == self._p)):
            # Evict LRU from T1 → B1
            evicted_key, _ = self._t1.popitem(last=False)
            self._timestamps.pop(evicted_key, None)
            self._b1[evicted_key] = None
            if len(self._b1) > self._maxsize:
                self._b1.popitem(last=False)
        elif len(self._t2) > 0:
            # Evict LRU from T2 → B2
            evicted_key, _ = self._t2.popitem(last=False)
            self._timestamps.pop(evicted_key, None)
            self._b2[evicted_key] = None
            if len(self._b2) > self._maxsize:
                self._b2.popitem(last=False)
        elif len(self._t1) > 0:
            # Fallback: T2 empty, evict from T1 → B1
            evicted_key, _ = self._t1.popitem(last=False)
            self._timestamps.pop(evicted_key, None)
            self._b1[evicted_key] = None
            if len(self._b1) > self._maxsize:
                self._b1.popitem(last=False)

    def _make_room(self) -> None:
        """Ensure |T1| + |T2| < maxsize by calling _replace if needed."""
        if self.size >= self._maxsize:
            self._replace()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get(self, query: str) -> Optional[List[float]]:
        """
        Get embedding from cache if available and not expired.

        On a live hit: promotes key to T2 (frequent list).
        On a TTL-expired entry: removes from live list, treats as miss.

        Args:
            query: Query text

        Returns:
            Cached embedding or None if not found/expired
        """
        key = self._make_key(query)

        async with self._lock:
            # --- Check T1 ---
            if key in self._t1:
                if self._is_expired(key):
                    del self._t1[key]
                    self._timestamps.pop(key, None)
                    self._misses += 1
                    return None
                embedding = self._t1.pop(key)
                self._t2[key] = embedding
                self._timestamps[key] = time.time()  # refresh timestamp on promotion
                self._hits += 1
                logger.debug("Embedding cache HIT (T1->T2 promotion) for query: %s...", query[:50])
                return embedding

            # --- Check T2 ---
            if key in self._t2:
                if self._is_expired(key):
                    del self._t2[key]
                    self._timestamps.pop(key, None)
                    self._misses += 1
                    return None
                # Move to MRU end of T2
                self._t2.move_to_end(key)
                self._timestamps[key] = time.time()
                self._hits += 1
                logger.debug("Embedding cache HIT (T2) for query: %s...", query[:50])
                return self._t2[key]

            self._misses += 1
            return None

    async def put(self, query: str, embedding: List[float]) -> None:
        """
        Store embedding in cache using ARC insertion policy.

        - Ghost hit in B1: increase p, insert into T2
        - Ghost hit in B2: decrease p, insert into T2
        - Cold miss: insert into T1

        Args:
            query: Query text
            embedding: Computed embedding vector
        """
        key = self._make_key(query)

        async with self._lock:
            # If already live, update value and timestamp (update in place)
            if key in self._t1:
                self._t1[key] = embedding
                self._t1.move_to_end(key)
                self._timestamps[key] = time.time()
                return
            if key in self._t2:
                self._t2[key] = embedding
                self._t2.move_to_end(key)
                self._timestamps[key] = time.time()
                return

            if key in self._b1:
                # Ghost hit in B1: adapt p upward
                delta = max(1, len(self._b2) // max(len(self._b1), 1))
                self._p = min(self._p + delta, self._maxsize)
                del self._b1[key]
                self._make_room()
                self._t2[key] = embedding
                self._timestamps[key] = time.time()
                logger.debug("ARC B1 ghost hit — p increased to %d", self._p)
                return

            if key in self._b2:
                # Ghost hit in B2: adapt p downward
                delta = max(1, len(self._b1) // max(len(self._b2), 1))
                self._p = max(self._p - delta, 0)
                del self._b2[key]
                self._make_room()
                self._t2[key] = embedding
                self._timestamps[key] = time.time()
                logger.debug("ARC B2 ghost hit — p decreased to %d", self._p)
                return

            # Cold miss: insert into T1
            total_ghost = len(self._b1) + len(self._b2)
            if self.size + total_ghost >= self._maxsize:
                if total_ghost > 0:
                    # Directory full: evict from ghost list to make directory room
                    if len(self._b1) >= self._maxsize:
                        self._b1.popitem(last=False)
                    elif len(self._b2) >= self._maxsize:
                        self._b2.popitem(last=False)
            self._make_room()
            self._t1[key] = embedding
            self._timestamps[key] = time.time()

    def evict(self, count: int) -> int:
        """
        Evict oldest items from cache (T1 first, then T2).

        Args:
            count: Number of items to evict

        Returns:
            Actual number of items evicted
        """
        evicted = 0
        remaining = min(count, self.size)

        # Evict from T1 first (recency list)
        while evicted < remaining and self._t1:
            key, _ = self._t1.popitem(last=False)
            self._timestamps.pop(key, None)
            evicted += 1

        # Then from T2 (frequency list)
        while evicted < remaining and self._t2:
            key, _ = self._t2.popitem(last=False)
            self._timestamps.pop(key, None)
            evicted += 1

        return evicted

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics including ARC-specific t1_size and t2_size."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total) if total > 0 else 0.0
        return {
            "name": self.name,
            "cache_size": self.size,
            "max_size": self._maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "hit_rate_percent": round(hit_rate * 100, 2),
            "ttl_seconds": self._ttl_seconds,
            "t1_size": len(self._t1),
            "t2_size": len(self._t2),
            "b1_size": len(self._b1),
            "b2_size": len(self._b2),
            "arc_p": self._p,
        }

    async def clear(self) -> None:
        """Clear all cached embeddings and reset ARC state."""
        self._t1.clear()
        self._t2.clear()
        self._b1.clear()
        self._b2.clear()
        self._timestamps.clear()
        self._p = 0
        self._hits = 0
        self._misses = 0
        logger.info("Embedding cache cleared")


# Global embedding cache instance
# Issue #743: Uses SSOT config defaults (no explicit size needed)
_embedding_cache = EmbeddingCache(ttl_seconds=3600)


def get_embedding_cache() -> EmbeddingCache:
    """Get the global embedding cache instance."""
    return _embedding_cache
