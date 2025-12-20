# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Redis-based Caching Manager
Implements intelligent caching strategies for different data types
"""

import asyncio
import hashlib
import inspect
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for user data types
_USER_DATA_TYPES = ("user_preferences", "user_history")


class CacheStrategy(Enum):
    """Cache strategies for different data types"""

    STATIC = "static"  # Rarely changing data (templates, configs)
    DYNAMIC = "dynamic"  # Frequently changing data (status, stats)
    USER_SCOPED = "user_scoped"  # User-specific data (preferences, history)
    COMPUTED = "computed"  # Expensive computation results
    TEMPORARY = "temporary"  # Short-lived data (session data)
    KNOWLEDGE = "knowledge"  # Knowledge base queries and embeddings


@dataclass
class CacheConfig:
    """Configuration for cache behavior"""

    strategy: CacheStrategy
    ttl: int  # Time to live in seconds
    max_size: Optional[int] = None  # Max items before eviction
    compress: bool = False  # Compress large data
    version: str = "1.0"  # Cache version for invalidation


class AdvancedCacheManager:
    """Enhanced cache manager with intelligent strategies"""

    def __init__(self):
        """Initialize cache manager with Redis clients and default configurations."""
        self.redis_client = None  # Will be initialized asynchronously
        self.sync_redis_client = get_redis_client(async_client=False)
        self.cache_prefix = "autobot:cache:"
        self.stats_prefix = "autobot:cache:stats:"
        self._redis_client_initialized = False

        # Lock for thread-safe async Redis client initialization
        self._lock = asyncio.Lock()

        # Cache configurations for different data types
        self.cache_configs = {
            # Static data - long TTL
            "templates": CacheConfig(CacheStrategy.STATIC, ttl=3600),  # 1 hour
            "configurations": CacheConfig(CacheStrategy.STATIC, ttl=1800),  # 30 min
            "model_info": CacheConfig(CacheStrategy.STATIC, ttl=900),  # 15 min
            # Dynamic data - medium TTL
            "system_status": CacheConfig(CacheStrategy.DYNAMIC, ttl=300),  # 5 min
            "project_status": CacheConfig(CacheStrategy.DYNAMIC, ttl=180),  # 3 min
            "health_checks": CacheConfig(CacheStrategy.DYNAMIC, ttl=60),  # 1 min
            # User-scoped data - medium TTL
            "user_preferences": CacheConfig(CacheStrategy.USER_SCOPED, ttl=3600),
            "user_history": CacheConfig(CacheStrategy.USER_SCOPED, ttl=1800),
            # Computed results - long TTL for expensive operations
            "code_analysis": CacheConfig(CacheStrategy.COMPUTED, ttl=7200),  # 2 hours
            "search_results": CacheConfig(CacheStrategy.COMPUTED, ttl=1800),  # 30 min
            "ai_responses": CacheConfig(CacheStrategy.COMPUTED, ttl=900),  # 15 min
            # Temporary data - short TTL
            "session_data": CacheConfig(CacheStrategy.TEMPORARY, ttl=300),
            "api_rate_limits": CacheConfig(CacheStrategy.TEMPORARY, ttl=60),
            # Knowledge base data - medium TTL with size limits
            "knowledge_queries": CacheConfig(
                CacheStrategy.KNOWLEDGE, ttl=300, max_size=1000
            ),  # 5 min
            "knowledge_embeddings": CacheConfig(
                CacheStrategy.KNOWLEDGE, ttl=3600, max_size=5000
            ),  # 1 hour
        }

        if self.sync_redis_client:
            logger.info("AdvancedCacheManager initialized with Redis backend")
        else:
            logger.warning(
                "AdvancedCacheManager initialized without Redis - caching disabled"
            )

    async def _ensure_redis_client(self):
        """Ensure async Redis client is initialized (thread-safe)"""
        # Fast path: check without lock first
        if self._redis_client_initialized:
            return

        # Slow path: acquire lock and double-check
        async with self._lock:
            if self._redis_client_initialized:
                return  # Another coroutine initialized while we waited
            try:
                self.redis_client = await get_redis_client(async_client=True)
                self._redis_client_initialized = True
                logger.debug("Async Redis client initialized successfully")
            except Exception as e:
                logger.error("Failed to initialize async Redis client: %s", e)
                self.redis_client = None
                self._redis_client_initialized = True  # Prevent retry loops

    def _make_cache_key(
        self, data_type: str, key: str, user_id: Optional[str] = None
    ) -> str:
        """Generate hierarchical cache key"""
        config = self.cache_configs.get(
            data_type, CacheConfig(CacheStrategy.DYNAMIC, 300)
        )

        if config.strategy == CacheStrategy.USER_SCOPED and user_id:
            return f"{self.cache_prefix}{data_type}:user:{user_id}:{key}"
        else:
            return f"{self.cache_prefix}{data_type}:{key}"

    def _make_stats_key(self, data_type: str) -> str:
        """Generate statistics key"""
        return f"{self.stats_prefix}{data_type}"

    async def get(
        self, data_type: str, key: str, user_id: Optional[str] = None
    ) -> Optional[Any]:
        """Get cached data with automatic deserialization"""
        await self._ensure_redis_client()
        if not self.redis_client:
            return None

        try:
            cache_key = self._make_cache_key(data_type, key, user_id)
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                # Update hit statistics
                await self._update_stats(data_type, hit=True)

                data = json.loads(cached_data)
                logger.debug("Cache HIT for %s:%s", data_type, key)
                return data
            else:
                # Update miss statistics
                await self._update_stats(data_type, hit=False)
                logger.debug("Cache MISS for %s:%s", data_type, key)
                return None

        except Exception as e:
            logger.error("Error getting cached data for %s:%s: %s", data_type, key, e)
            return None

    async def set(
        self,
        data_type: str,
        key: str,
        data: Any,
        user_id: Optional[str] = None,
        custom_ttl: Optional[int] = None,
    ) -> bool:
        """Set cached data with automatic configuration"""
        await self._ensure_redis_client()
        if not self.redis_client:
            return False

        try:
            cache_key = self._make_cache_key(data_type, key, user_id)
            config = self.cache_configs.get(
                data_type, CacheConfig(CacheStrategy.DYNAMIC, 300)
            )
            ttl = custom_ttl or config.ttl

            # Add metadata
            cache_entry = {
                "data": data,
                "timestamp": int(time.time()),
                "data_type": data_type,
                "version": config.version,
            }

            serialized_data = json.dumps(cache_entry, default=str)
            await self.redis_client.setex(cache_key, ttl, serialized_data)

            logger.debug("Cache SET for %s:%s (TTL: %ds)", data_type, key, ttl)
            return True

        except Exception as e:
            logger.error("Error setting cached data for %s:%s: %s", data_type, key, e)
            return False

    async def get_or_compute(
        self,
        data_type: str,
        key: str,
        compute_func: Callable[[], Any],
        user_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Any:
        """Get from cache or compute and cache the result"""
        if not force_refresh:
            cached_result = await self.get(data_type, key, user_id)
            if cached_result is not None:
                return cached_result.get("data")

        # Compute new value
        try:
            if hasattr(compute_func, "__call__"):
                result = compute_func()
                if inspect.iscoroutine(result):
                    # Result is a coroutine, await it
                    computed_data = await result
                else:
                    # Result is a regular value
                    computed_data = result
            else:
                computed_data = compute_func

            # Cache the result
            await self.set(data_type, key, computed_data, user_id)
            return computed_data

        except Exception as e:
            logger.error("Error computing data for %s:%s: %s", data_type, key, e)
            raise

    async def invalidate(
        self, data_type: str, key: str = "*", user_id: Optional[str] = None
    ) -> int:
        """Invalidate cache entries by pattern"""
        await self._ensure_redis_client()
        if not self.redis_client:
            return 0

        try:
            if key == "*":
                # Invalidate all entries for data type
                if user_id:
                    pattern = f"{self.cache_prefix}{data_type}:user:{user_id}:*"
                else:
                    pattern = f"{self.cache_prefix}{data_type}:*"
            else:
                cache_key = self._make_cache_key(data_type, key, user_id)
                pattern = cache_key

            keys = await self.redis_client.keys(pattern)
            if keys:
                deleted_count = await self.redis_client.delete(*keys)
                logger.info(
                    "Cache INVALIDATE: %d keys deleted for %s", deleted_count, data_type
                )
                return deleted_count
            return 0

        except Exception as e:
            logger.error("Error invalidating cache for %s: %s", data_type, e)
            return 0

    async def _update_stats(self, data_type: str, hit: bool):
        """Update cache statistics"""
        await self._ensure_redis_client()
        if not self.redis_client:
            return

        try:
            stats_key = self._make_stats_key(data_type)
            current_time = int(time.time())

            # Use Redis pipeline for atomic updates
            pipe = self.redis_client.pipeline()

            if hit:
                pipe.hincrby(stats_key, "hits", 1)
            else:
                pipe.hincrby(stats_key, "misses", 1)

            pipe.hset(stats_key, "last_access", current_time)
            pipe.expire(stats_key, 86400)  # Stats expire after 24 hours

            await pipe.execute()

        except Exception as e:
            logger.error("Error updating cache stats for %s: %s", data_type, e)

    async def _get_single_type_stats(self, data_type: str) -> Dict[str, Any]:
        """Get stats for a specific data type (Issue #315: extracted).

        Args:
            data_type: The data type to get stats for

        Returns:
            Stats dict for the data type
        """
        stats_key = self._make_stats_key(data_type)
        stats = await self.redis_client.hgetall(stats_key)

        hits = int(stats.get("hits", 0))
        misses = int(stats.get("misses", 0))
        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0

        return {
            "data_type": data_type,
            "hits": hits,
            "misses": misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "last_access": stats.get("last_access"),
        }

    async def _aggregate_stats(self, stats_keys: List[str]) -> tuple:
        """Aggregate hits/misses from all stats keys (Issue #315: extracted).

        Args:
            stats_keys: List of stats key names

        Returns:
            Tuple of (total_hits, total_misses)
        """
        if not stats_keys:
            return 0, 0

        total_hits = 0
        total_misses = 0

        async with self.redis_client.pipeline() as pipe:
            for stats_key in stats_keys:
                await pipe.hgetall(stats_key)
            all_stats = await pipe.execute()

        for stats in all_stats:
            total_hits += int(stats.get("hits", 0))
            total_misses += int(stats.get("misses", 0))

        return total_hits, total_misses

    async def _get_redis_memory_usage(self) -> str:
        """Get Redis memory usage safely (Issue #315: extracted).

        Returns:
            Memory usage string or 'N/A'
        """
        try:
            info = await self.redis_client.info("memory")
            return info.get("used_memory_human", "N/A")
        except Exception:
            return "N/A"

    async def _get_global_stats(self) -> Dict[str, Any]:
        """Get global cache statistics (Issue #315: extracted).

        Returns:
            Global stats dict
        """
        cache_keys = await self.redis_client.keys(f"{self.cache_prefix}*")
        stats_keys = await self.redis_client.keys(f"{self.stats_prefix}*")

        total_hits, total_misses = await self._aggregate_stats(stats_keys)
        total_requests = total_hits + total_misses
        global_hit_rate = (
            (total_hits / total_requests * 100) if total_requests > 0 else 0
        )

        memory_usage = await self._get_redis_memory_usage()

        return {
            "status": "enabled",
            "total_cache_keys": len(cache_keys),
            "total_hits": total_hits,
            "total_misses": total_misses,
            "global_hit_rate": f"{global_hit_rate:.1f}%",
            "memory_usage": memory_usage,
            "configured_data_types": list(self.cache_configs.keys()),
        }

    async def get_stats(self, data_type: Optional[str] = None) -> Dict[str, Any]:
        """Get comprehensive cache statistics.

        Issue #315: Refactored to use helper methods for reduced nesting.
        """
        await self._ensure_redis_client()
        if not self.redis_client:
            return {"status": "disabled"}

        try:
            if data_type:
                return await self._get_single_type_stats(data_type)
            return await self._get_global_stats()

        except Exception as e:
            logger.error("Error getting cache stats: %s", e)
            return {"status": "error", "error": str(e)}

    async def warm_cache(self, data_type: str, warm_data: Dict[str, Any]):
        """Warm up cache with predefined data"""
        await self._ensure_redis_client()
        if not self.redis_client:
            return False

        try:
            warmed_count = 0
            for key, data in warm_data.items():
                success = await self.set(data_type, key, data)
                if success:
                    warmed_count += 1

            logger.info("Cache WARM: %d entries warmed for %s", warmed_count, data_type)
            return warmed_count > 0

        except Exception as e:
            logger.error("Error warming cache for %s: %s", data_type, e)
            return False

    # =========================================================================
    # KNOWLEDGE-SPECIFIC CACHING METHODS (from knowledge_cache.py)
    # =========================================================================

    def _generate_knowledge_key(
        self, query: str, top_k: int, filters: Optional[Dict] = None
    ) -> str:
        """Generate cache key for knowledge base queries"""
        cache_data = {
            "query": query.lower().strip(),
            "top_k": top_k,
            "filters": filters or {},
        }
        cache_string = json.dumps(cache_data, sort_keys=True)
        cache_hash = hashlib.sha256(cache_string.encode()).hexdigest()[:16]
        return f"kb_query:{cache_hash}"

    async def get_cached_knowledge_results(
        self, query: str, top_k: int, filters: Optional[Dict] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieve cached knowledge base search results.
        Compatible with knowledge_cache.py API.
        """
        cache_key = self._generate_knowledge_key(query, top_k, filters)
        result = await self.get("knowledge_queries", cache_key)

        if result and "data" in result:
            logger.debug("Knowledge cache HIT for query: '%s' (top_k=%d)", query, top_k)
            return result["data"]

        logger.debug("Knowledge cache MISS for query: '%s'", query)
        return None

    async def cache_knowledge_results(
        self,
        query: str,
        top_k: int,
        results: List[Dict[str, Any]],
        filters: Optional[Dict] = None,
    ) -> bool:
        """
        Cache knowledge base search results.
        Compatible with knowledge_cache.py API.
        """
        cache_key = self._generate_knowledge_key(query, top_k, filters)
        success = await self.set(
            "knowledge_queries",
            cache_key,
            results,
            custom_ttl=None,  # Use default TTL from config
        )

        if success:
            # Manage cache size for knowledge queries
            await self._manage_cache_size("knowledge_queries")
            logger.debug(
                "Cached %d knowledge results for query: '%s'", len(results), query
            )

        return success

    async def _collect_cache_keys(self, pattern: str) -> List[str]:
        """Collect all cache keys matching pattern (Issue #315: extracted).

        Args:
            pattern: Redis key pattern to match

        Returns:
            List of matching keys
        """
        all_keys = []
        async for key in self.redis_client.scan_iter(match=pattern):
            all_keys.append(key)
        return all_keys

    async def _get_keys_with_timestamps(
        self, keys: List[str]
    ) -> List[tuple]:
        """Get keys with their timestamps for LRU sorting (Issue #315: extracted).

        Args:
            keys: List of Redis keys to fetch

        Returns:
            List of (timestamp, key) tuples
        """
        if not keys:
            return []

        keys_with_time = []
        all_cached_data = await self.redis_client.mget(keys)

        for key, cached_data in zip(keys, all_cached_data):
            if not cached_data:
                continue
            try:
                entry = json.loads(cached_data)
                timestamp = entry.get("timestamp", 0)
                keys_with_time.append((timestamp, key))
            except Exception:
                continue

        return keys_with_time

    async def _evict_excess_keys(
        self, keys_with_time: List[tuple], max_size: int, data_type: str
    ) -> int:
        """Evict excess keys using LRU policy (Issue #315: extracted).

        Args:
            keys_with_time: List of (timestamp, key) tuples
            max_size: Maximum allowed cache size
            data_type: Data type for logging

        Returns:
            Number of keys deleted
        """
        if len(keys_with_time) <= max_size:
            return 0

        # Sort by timestamp (oldest first) and remove excess
        keys_with_time.sort()
        excess_count = len(keys_with_time) - max_size + 100  # Buffer
        keys_to_remove = [key for _, key in keys_with_time[:excess_count]]

        if not keys_to_remove:
            return 0

        deleted_count = await self.redis_client.delete(*keys_to_remove)
        logger.info(
            "LRU eviction: Removed %d old entries from %s cache", deleted_count, data_type
        )
        return deleted_count

    async def _manage_cache_size(self, data_type: str):
        """Manage cache size using LRU eviction.

        Issue #315: Refactored to use helper methods for reduced nesting.
        Implements max_size limits from CacheConfig.
        """
        await self._ensure_redis_client()
        if not self.redis_client:
            return

        try:
            config = self.cache_configs.get(data_type)
            if not config or not config.max_size:
                return  # No size limit configured

            # Collect and process cache entries
            pattern = f"{self.cache_prefix}{data_type}:*"
            all_keys = await self._collect_cache_keys(pattern)
            keys_with_time = await self._get_keys_with_timestamps(all_keys)

            # Evict excess entries
            await self._evict_excess_keys(keys_with_time, config.max_size, data_type)

        except Exception as e:
            logger.error("Error managing cache size for %s: %s", data_type, e)

    # =========================================================================
    # BACKWARD COMPATIBILITY METHODS (from backend/utils/cache_manager.py)
    # =========================================================================

    async def simple_get(self, key: str) -> Optional[Any]:
        """
        Simple cache get (backward compatible with CacheManager).
        Uses DYNAMIC strategy with default TTL.
        """
        result = await self.get("session_data", key)
        return result.get("data") if result else None

    async def simple_set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Simple cache set (backward compatible with CacheManager).
        Uses DYNAMIC strategy with custom or default TTL.
        """
        return await self.set("session_data", key, value, custom_ttl=ttl)

    async def simple_delete(self, key: str) -> int:
        """Simple cache delete (backward compatible with CacheManager)"""
        return await self.invalidate("session_data", key)

    async def simple_clear(self) -> int:
        """Simple cache clear all (backward compatible with CacheManager)"""
        return await self.invalidate("session_data", "*")


# Global advanced cache manager instance
advanced_cache = AdvancedCacheManager()


def smart_cache(
    data_type: str,
    key_func: Optional[Callable] = None,
    user_id_func: Optional[Callable] = None,
    ttl: Optional[int] = None,
):
    """
    Decorator for intelligent caching of function results

    Args:
        data_type: Type of data being cached (determines strategy)
        key_func: Function to generate cache key from args
        user_id_func: Function to extract user ID from args
        ttl: Custom TTL override
    """

    def decorator(func):
        """Inner decorator that wraps function with intelligent caching."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """Async wrapper that checks cache and computes if needed."""
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default key generation from function name and args
                args_hash = hashlib.md5(
                    str(args + tuple(kwargs.items())).encode(),
                    usedforsecurity=False
                ).hexdigest()[:8]
                cache_key = f"{func.__name__}:{args_hash}"

            # Extract user ID if needed
            user_id = None
            if user_id_func:
                user_id = user_id_func(*args, **kwargs)

            # Use get_or_compute for intelligent caching
            async def compute():
                """Execute the wrapped function asynchronously."""
                return await func(*args, **kwargs)

            return await advanced_cache.get_or_compute(
                data_type=data_type,
                key=cache_key,
                compute_func=compute,
                user_id=user_id,
            )

        return wrapper

    return decorator


# Convenience functions for common caching patterns
async def cache_template_data(template_id: str, data: Any) -> bool:
    """Cache workflow template data"""
    return await advanced_cache.set("templates", template_id, data)


async def get_cached_template(template_id: str) -> Optional[Any]:
    """Get cached workflow template"""
    result = await advanced_cache.get("templates", template_id)
    return result.get("data") if result else None


async def cache_system_status(status_data: Dict[str, Any]) -> bool:
    """Cache system status data"""
    return await advanced_cache.set("system_status", "current", status_data)


async def get_cached_system_status() -> Optional[Dict[str, Any]]:
    """Get cached system status"""
    result = await advanced_cache.get("system_status", "current")
    return result.get("data") if result else None


async def invalidate_user_cache(user_id: str) -> int:
    """Invalidate all cache entries for a specific user"""
    count = 0
    # Issue #380: Use module-level tuple
    for data_type in _USER_DATA_TYPES:
        count += await advanced_cache.invalidate(data_type, "*", user_id)
    return count


# ============================================================================
# KNOWLEDGE CACHE CONVENIENCE FUNCTIONS (knowledge_cache.py compatibility)
# ============================================================================


async def get_cached_knowledge_results(
    query: str, top_k: int, filters: Optional[Dict] = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Get cached knowledge base search results.
    Drop-in replacement for knowledge_cache.KnowledgeCache.get_cached_results().
    """
    return await advanced_cache.get_cached_knowledge_results(query, top_k, filters)


async def cache_knowledge_results(
    query: str,
    top_k: int,
    results: List[Dict[str, Any]],
    filters: Optional[Dict] = None,
) -> bool:
    """
    Cache knowledge base search results.
    Drop-in replacement for knowledge_cache.KnowledgeCache.cache_results().
    """
    return await advanced_cache.cache_knowledge_results(query, top_k, results, filters)


async def clear_knowledge_cache(pattern: Optional[str] = None) -> int:
    """Clear knowledge base cache (optionally by pattern)"""
    if pattern:
        # Pattern-based clearing
        return await advanced_cache.invalidate("knowledge_queries", pattern)
    else:
        # Clear all knowledge queries
        return await advanced_cache.invalidate("knowledge_queries", "*")


async def get_knowledge_cache_stats() -> Dict[str, Any]:
    """Get knowledge cache statistics"""
    return await advanced_cache.get_stats("knowledge_queries")


def get_knowledge_cache():
    """
    Get knowledge cache instance (backward compatibility).
    Returns AdvancedCacheManager with knowledge-specific methods.
    """
    return advanced_cache


# ============================================================================
# SIMPLE CACHE CONVENIENCE FUNCTIONS (cache_manager.py compatibility)
# ============================================================================


class SimpleCacheManager:
    """
    Backward compatibility wrapper for backend/utils/cache_manager.py.
    Provides simple TTL-based caching API using AdvancedCacheManager backend.
    """

    def __init__(self, default_ttl: int = 300):
        """Initialize simple cache manager with default TTL in seconds."""
        self.default_ttl = default_ttl
        self._cache = advanced_cache
        self.cache_prefix = "cache:"  # Match original CacheManager prefix

    @property
    def _redis_client(self):
        """Access to underlying Redis client (for backward compatibility)"""
        return self._cache.redis_client

    @property
    def _redis_initialized(self):
        """Check if Redis is initialized"""
        return self._cache.redis_client is not None

    async def _ensure_redis_client(self):
        """Ensure Redis client is initialized (backward compatibility)"""
        # AdvancedCacheManager auto-initializes, so this is a no-op
        # But we keep it for API compatibility

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value"""
        return await self._cache.simple_get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set cached value with TTL"""
        return await self._cache.simple_set(key, value, ttl or self.default_ttl)

    async def delete(self, key: str) -> int:
        """Delete cached value"""
        return await self._cache.simple_delete(key)

    async def clear(self) -> int:
        """Clear all cached values"""
        return await self._cache.simple_clear()

    async def clear_pattern(self, pattern: str) -> int:
        """
        Clear multiple cache keys matching pattern.
        Backward compatibility for CacheManager.clear_pattern()
        """
        try:
            # Build search pattern with cache prefix
            search_pattern = f"{self.cache_prefix}{pattern}"

            if not self._cache.redis_client:
                logger.warning("Redis client not available for pattern clear")
                return 0

            # Find matching keys
            keys = []
            async for key in self._cache.redis_client.scan_iter(match=search_pattern):
                keys.append(key)

            # Delete all matching keys
            if keys:
                deleted_count = await self._cache.redis_client.delete(*keys)
                logger.info(
                    "Cache CLEAR: %d keys deleted for pattern: %s", deleted_count, pattern
                )
                return deleted_count
            else:
                logger.debug("Cache CLEAR: No keys found for pattern: %s", pattern)
                return 0

        except Exception as e:
            logger.error("Error clearing cache for pattern %s: %s", pattern, e)
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        Backward compatibility for CacheManager.get_stats()
        """
        if not self._cache.redis_client:
            return {"status": "disabled", "total_keys": 0}

        try:
            # Count keys with cache prefix
            cache_keys = []
            async for key in self._cache.redis_client.scan_iter(
                match=f"{self.cache_prefix}*"
            ):
                cache_keys.append(key)
            total_keys = len(cache_keys)

            # Get memory usage info if available
            try:
                info = await self._cache.redis_client.info("memory")
                memory_usage = info.get("used_memory_human", "N/A")
            except Exception:
                memory_usage = "N/A"

            return {
                "status": "enabled",
                "total_keys": total_keys,
                "memory_usage": memory_usage,
                "default_ttl": self.default_ttl,
            }

        except Exception as e:
            logger.error("Error getting cache stats: %s", e)
            return {"status": "error", "error": str(e)}

    def cache_response(self, cache_key: str = None, ttl: int = None):
        """
        Decorator for caching HTTP responses.
        Compatible with original CacheManager.cache_response().
        Supports FastAPI Request objects for automatic key generation.
        """
        actual_ttl = ttl or self.default_ttl

        def decorator(func):
            """Inner decorator that wraps endpoint with response caching."""

            @wraps(func)
            async def wrapper(*args, **kwargs):
                """Async wrapper that caches successful HTTP responses."""
                from fastapi import Request

                # Extract request object from FastAPI dependency injection
                request = None

                # Check for Request object in kwargs
                for key, value in kwargs.items():
                    if isinstance(value, Request):
                        request = value
                        break

                # Fallback: check args for Request object
                if not request:
                    for arg in args:
                        if isinstance(arg, Request):
                            request = arg
                            break

                # Generate cache key based on request or function
                if cache_key:
                    key = cache_key
                elif request:
                    # Include query parameters in cache key for uniqueness
                    query_hash = hash(str(sorted(request.query_params.items())))
                    key = f"endpoint:{request.url.path}:{query_hash}"
                else:
                    # Fallback for non-HTTP endpoints
                    params_hash = hash(str(sorted(kwargs.items())))
                    key = f"func:{func.__name__}:{params_hash}"

                # Try to get from cache first
                try:
                    cached_result = await self.get(key)
                    if cached_result is not None:
                        logger.debug("Cache HIT: %s - serving from cache", key)
                        return cached_result
                except Exception as e:
                    logger.error("Cache retrieval error for key %s: %s", key, e)

                # Execute function and cache result
                logger.debug("Cache MISS: %s - executing function", key)
                result = await func(*args, **kwargs)

                # Cache successful responses
                if self._is_cacheable_response(result):
                    try:
                        await self.set(key, result, actual_ttl)
                        logger.debug("Cache SET: %s - cached for %ds", key, actual_ttl)
                    except Exception as e:
                        logger.error("Cache storage error for key %s: %s", key, e)

                return result

            return wrapper

        return decorator

    @staticmethod
    def _is_cacheable_response(result: Any) -> bool:
        """Check if a response should be cached"""
        if not isinstance(result, dict):
            return False

        # Don't cache error responses
        if result.get("error") or result.get("status") == "error":
            return False

        # Don't cache empty responses
        if not result:
            return False

        return True


# ============================================================================
# GLOBAL INSTANCE & CONVENIENCE FUNCTIONS (cache_manager.py compatibility)
# ============================================================================

# Create global cache manager instance (backward compatibility)
cache_manager = SimpleCacheManager()


# Standalone cache_response decorator (backward compatibility)
def cache_response(cache_key: str = None, ttl: int = 300):
    """
    Standalone decorator for caching API endpoint responses.
    Backward compatibility for: from backend.utils.cache_manager import cache_response

    Args:
        cache_key: Custom cache key (optional, defaults to endpoint path)
        ttl: Time to live in seconds (default: 5 minutes)
    """
    return cache_manager.cache_response(cache_key=cache_key, ttl=ttl)


# Simple cache decorator for non-HTTP functions (backward compatibility)
def cache_function(cache_key: str = None, ttl: int = 300):
    """
    Simple cache decorator for non-FastAPI functions.
    Backward compatibility for original cache_manager.cache_function()

    Args:
        cache_key: Custom cache key (optional, defaults to function name + args hash)
        ttl: Time to live in seconds (default: 5 minutes)
    """

    def decorator(func):
        """Inner decorator that wraps function with simple caching."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """Async wrapper that caches function results by key."""
            # Generate cache key
            if cache_key:
                key = cache_key
            else:
                args_hash = hash(str(args) + str(sorted(kwargs.items())))
                key = f"func:{func.__name__}:{args_hash}"

            # Try to get from cache
            try:
                cached_result = await cache_manager.get(key)
                if cached_result is not None:
                    return cached_result
            except Exception as e:
                logger.error("Cache retrieval error for key %s: %s", key, e)

            # Execute and cache
            result = await func(*args, **kwargs)

            if cache_manager._is_cacheable_response(result):
                try:
                    await cache_manager.set(key, result, ttl)
                except Exception as e:
                    logger.error("Cache storage error for key %s: %s", key, e)

            return result

        return wrapper

    return decorator
