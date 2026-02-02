# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Response Cache - Dual-tier L1/L2 caching for LLM responses.

Restored from archived async_llm_interface.py as part of Issue #551.
Provides significant performance improvements:
- L1: In-memory LRU cache (fastest, 100 items default)
- L2: Redis cache with TTL (persistence across restarts)
- 3-5x faster cache lookups for repeated queries
"""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import xxhash

from src.config.ssot_config import config
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class CachedResponse:
    """Cached LLM response data structure."""

    content: str
    model: str
    tokens_used: Optional[int] = None
    processing_time: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class LLMResponseCache:
    """
    Dual-tier L1/L2 caching system for LLM responses.

    L1 Cache: In-memory LRU cache for fastest access (sub-millisecond)
    L2 Cache: Redis cache with TTL for persistence and cross-process sharing

    Performance Impact:
    - L1 hit: ~0.001ms (memory access)
    - L2 hit: ~1-5ms (Redis network call)
    - Cache miss: 100-10000ms (LLM API call)

    This provides 3-5x faster cache lookups compared to single-tier caching.

    Issue: #743 - Memory Optimization (Phase 3.3)
    Reads default L1 size from config.cache.l1.llm_response
    Reads default L2 TTL from config.cache.l2.llm_response
    """

    def __init__(
        self,
        memory_cache_max_size: int = None,
        redis_ttl: int = None,
        redis_database: str = "main",
    ):
        """
        Initialize the dual-tier cache.

        Args:
            memory_cache_max_size: Max L1 items (default from SSOT config.cache.l1.llm_response)
            redis_ttl: L2 TTL seconds (default from SSOT config.cache.l2.llm_response)
            redis_database: Redis database name for L2 cache
        """
        # L1 In-memory cache
        self._memory_cache: Dict[str, CachedResponse] = {}
        self._memory_cache_access: List[str] = []  # LRU tracking
        # Issue #743: Read from SSOT config, allow explicit override
        self._memory_cache_max_size = (
            memory_cache_max_size
            if memory_cache_max_size is not None
            else config.cache.l1.llm_response
        )

        # L2 Redis cache configuration
        # Issue #743: Read from SSOT config, allow explicit override
        self._redis_ttl = (
            redis_ttl if redis_ttl is not None else config.cache.l2.llm_response
        )
        self._redis_database = redis_database

        # Cache metrics
        self._metrics = {
            "l1_hits": 0,
            "l2_hits": 0,
            "misses": 0,
            "total_requests": 0,
            "l1_evictions": 0,
        }

        # Lock for thread safety
        self._lock = asyncio.Lock()

        logger.info(
            f"LLM Response Cache initialized: L1={memory_cache_max_size} items, "
            f"L2 TTL={redis_ttl}s, Redis DB={redis_database}"
        )

    @property
    def name(self) -> str:
        """Unique cache identifier."""
        return "llm_l1"

    @property
    def size(self) -> int:
        """Current number of items in L1 cache."""
        return len(self._memory_cache)

    @property
    def max_size(self) -> int:
        """Maximum capacity of L1 cache."""
        return self._memory_cache_max_size

    def generate_cache_key(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        top_k: int = 40,
        top_p: float = 0.9,
    ) -> str:
        """
        Generate cache key with high-performance xxhash (3-5x faster than MD5).

        Uses tuple-based key construction for better performance than JSON
        serialization.

        Args:
            messages: List of message dicts with role and content
            model: Model name
            temperature: LLM temperature setting
            top_k: Top-k sampling parameter
            top_p: Top-p (nucleus) sampling parameter

        Returns:
            Cache key string in format "llm_cache:{hash}"
        """
        # Use tuple instead of JSON for better performance
        key_data = (
            tuple((m.get("role", ""), m.get("content", "")) for m in messages),
            model,
            temperature,
            top_k,
            top_p,
        )

        # xxhash is 3-5x faster than MD5 for cache key generation
        content_hash = xxhash.xxh64(str(key_data)).hexdigest()
        return f"llm_cache:{content_hash}"

    async def get(self, cache_key: str) -> Optional[CachedResponse]:
        """
        Get cached response with L1/L2 lookup.

        First checks L1 memory cache (fastest), then falls back to L2 Redis.
        Automatically promotes L2 hits to L1 for future fast access.

        Args:
            cache_key: Cache key from generate_cache_key()

        Returns:
            CachedResponse if found, None if cache miss
        """
        async with self._lock:
            self._metrics["total_requests"] += 1

            # L1 Memory Cache Check (fastest)
            if cache_key in self._memory_cache:
                # Update LRU access order
                self._memory_cache_access.remove(cache_key)
                self._memory_cache_access.append(cache_key)
                self._metrics["l1_hits"] += 1
                logger.debug(f"L1 memory cache hit: {cache_key[:24]}...")
                return self._memory_cache[cache_key]

        # L2 Redis Cache Check (outside lock for non-blocking)
        try:
            redis_client = await get_redis_client(
                async_client=True, database=self._redis_database
            )
            if redis_client:
                cached_data = await redis_client.get(cache_key)
                if cached_data:
                    data = json.loads(cached_data.decode("utf-8"))
                    response = CachedResponse(
                        content=data.get("content", ""),
                        model=data.get("model", ""),
                        tokens_used=data.get("tokens_used"),
                        processing_time=data.get("processing_time", 0.0),
                        metadata=data.get("metadata", {}),
                    )

                    # Promote to L1 cache for future fast access
                    await self._store_memory_cache(cache_key, response)

                    self._metrics["l2_hits"] += 1
                    logger.debug(f"L2 Redis cache hit: {cache_key[:24]}...")
                    return response
        except Exception as e:
            logger.debug(f"L2 cache retrieval failed (non-critical): {e}")

        self._metrics["misses"] += 1
        return None

    def evict(self, count: int) -> int:
        """
        Evict oldest items from L1 memory cache.

        Args:
            count: Number of items to evict

        Returns:
            Actual number of items evicted
        """
        evicted = 0
        for _ in range(min(count, len(self._memory_cache))):
            if self._memory_cache_access:
                oldest_key = self._memory_cache_access.pop(0)
                if oldest_key in self._memory_cache:
                    del self._memory_cache[oldest_key]
                    evicted += 1
                    self._metrics["l1_evictions"] += 1
        return evicted

    async def _store_memory_cache(
        self, cache_key: str, response: CachedResponse
    ) -> None:
        """
        Store response in L1 memory cache with LRU eviction.

        Args:
            cache_key: Cache key
            response: Response to cache
        """
        async with self._lock:
            # LRU eviction if cache is full
            if len(self._memory_cache) >= self._memory_cache_max_size:
                oldest_key = self._memory_cache_access.pop(0)
                del self._memory_cache[oldest_key]
                self._metrics["l1_evictions"] += 1
                logger.debug(f"L1 cache eviction: {oldest_key[:24]}...")

            self._memory_cache[cache_key] = response
            if cache_key not in self._memory_cache_access:
                self._memory_cache_access.append(cache_key)

    async def set(
        self, cache_key: str, response: CachedResponse, skip_redis: bool = False
    ) -> None:
        """
        Cache response in both L1 memory and L2 Redis.

        Args:
            cache_key: Cache key
            response: Response to cache
            skip_redis: If True, only cache in L1 (useful for large responses)
        """
        # Store in L1 memory cache
        await self._store_memory_cache(cache_key, response)

        if skip_redis:
            return

        # Store in L2 Redis cache
        try:
            redis_client = await get_redis_client(
                async_client=True, database=self._redis_database
            )
            if redis_client:
                # Optimize metadata storage - only keep essential data
                essential_metadata = {
                    "request_id": response.metadata.get("request_id")
                    if response.metadata
                    else None,
                    "chunks_received": response.metadata.get("chunks_received")
                    if response.metadata
                    else None,
                    "streaming": response.metadata.get("streaming", False)
                    if response.metadata
                    else False,
                }

                data = {
                    "content": response.content,
                    "model": response.model,
                    "tokens_used": response.tokens_used,
                    "processing_time": response.processing_time,
                    "metadata": essential_metadata,
                }

                await redis_client.set(cache_key, json.dumps(data), ex=self._redis_ttl)
                logger.debug(
                    f"Cached in L1+L2: {cache_key[:24]}... (TTL={self._redis_ttl}s)"
                )
        except Exception as e:
            logger.debug(f"L2 Redis cache storage failed (non-critical): {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics for CacheProtocol compliance."""
        total = self._metrics["total_requests"]
        total_hits = self._metrics["l1_hits"] + self._metrics["l2_hits"]
        hit_rate = (total_hits / total) if total > 0 else 0.0

        return {
            "name": self.name,
            "size": len(self._memory_cache),
            "max_size": self._memory_cache_max_size,
            "hits": total_hits,
            "misses": self._metrics["misses"],
            "hit_rate": hit_rate,
        }

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get cache performance metrics (detailed version for monitoring).

        Returns:
            Dictionary with cache statistics including hit rates
        """
        total = self._metrics["total_requests"]
        l1_hits = self._metrics["l1_hits"]
        l2_hits = self._metrics["l2_hits"]
        self._metrics["misses"]

        l1_hit_rate = (l1_hits / total * 100) if total > 0 else 0.0
        l2_hit_rate = (l2_hits / total * 100) if total > 0 else 0.0
        total_hit_rate = ((l1_hits + l2_hits) / total * 100) if total > 0 else 0.0

        return {
            **self._metrics,
            "l1_hit_rate": round(l1_hit_rate, 2),
            "l2_hit_rate": round(l2_hit_rate, 2),
            "total_hit_rate": round(total_hit_rate, 2),
            "l1_cache_size": len(self._memory_cache),
            "l1_max_size": self._memory_cache_max_size,
        }

    def clear(self) -> None:
        """Clear L1 memory cache (CacheProtocol compliance)."""
        self._memory_cache.clear()
        self._memory_cache_access.clear()
        logger.info("L1 cache cleared")

    def clear_l1(self) -> int:
        """
        Clear L1 memory cache.

        Returns:
            Number of entries cleared
        """
        count = len(self._memory_cache)
        self._memory_cache.clear()
        self._memory_cache_access.clear()
        logger.info(f"L1 cache cleared: {count} entries removed")
        return count

    async def clear_l2(self, pattern: str = "llm_cache:*") -> int:
        """
        Clear L2 Redis cache entries matching pattern.

        Args:
            pattern: Redis key pattern to match (default: all LLM cache keys)

        Returns:
            Number of entries deleted
        """
        try:
            redis_client = await get_redis_client(
                async_client=True, database=self._redis_database
            )
            if redis_client:
                keys = []
                async for key in redis_client.scan_iter(match=pattern):
                    keys.append(key)
                if keys:
                    deleted = await redis_client.delete(*keys)
                    logger.info(f"L2 cache cleared: {deleted} entries removed")
                    return deleted
        except Exception as e:
            logger.warning(f"L2 cache clear failed: {e}")
        return 0

    async def clear_all(self) -> Dict[str, int]:
        """
        Clear both L1 and L2 caches.

        Returns:
            Dictionary with counts of cleared entries
        """
        l1_count = self.clear_l1()
        l2_count = await self.clear_l2()
        return {"l1_cleared": l1_count, "l2_cleared": l2_count}


# Global cache instance with thread-safe initialization (Issue #662)
_llm_response_cache: Optional[LLMResponseCache] = None
_cache_init_lock = asyncio.Lock()
_cache_sync_lock = threading.Lock()  # Issue #662: Thread-safe sync initialization


def get_llm_cache() -> LLMResponseCache:
    """
    Get or create the global LLM response cache instance (thread-safe).

    Issue #662: Now uses double-checked locking for thread safety.
    For async contexts needing guaranteed single initialization, use get_llm_cache_async().

    Returns:
        LLMResponseCache singleton instance
    """
    global _llm_response_cache
    if _llm_response_cache is None:
        with _cache_sync_lock:
            # Double-check after acquiring lock
            if _llm_response_cache is None:
                _llm_response_cache = LLMResponseCache()
    return _llm_response_cache


async def get_llm_cache_async() -> LLMResponseCache:
    """
    Get or create the global LLM response cache instance (async-safe).

    Issue #551 Code Review: Thread-safe singleton with async lock
    to prevent race conditions during initialization in async contexts.

    Returns:
        LLMResponseCache singleton instance
    """
    global _llm_response_cache
    if _llm_response_cache is None:
        async with _cache_init_lock:
            # Double-check pattern for thread safety
            if _llm_response_cache is None:
                _llm_response_cache = LLMResponseCache()
    return _llm_response_cache


__all__ = [
    "LLMResponseCache",
    "CachedResponse",
    "get_llm_cache",
    "get_llm_cache_async",
]
