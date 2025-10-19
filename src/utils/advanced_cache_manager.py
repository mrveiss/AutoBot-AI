"""
Advanced Redis-based Caching Manager
Implements intelligent caching strategies for different data types
"""

import hashlib
import inspect
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional

from src.constants.network_constants import NetworkConstants
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class CacheStrategy(Enum):
    """Cache strategies for different data types"""

    STATIC = "static"  # Rarely changing data (templates, configs)
    DYNAMIC = "dynamic"  # Frequently changing data (status, stats)
    USER_SCOPED = "user_scoped"  # User-specific data (preferences, history)
    COMPUTED = "computed"  # Expensive computation results
    TEMPORARY = "temporary"  # Short-lived data (session data)


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
        self.redis_client = None  # Will be initialized asynchronously
        self.sync_redis_client = get_redis_client(async_client=False)
        self.cache_prefix = "autobot:cache:"
        self.stats_prefix = "autobot:cache:stats:"
        self._redis_client_initialized = False

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
        }

        if self.sync_redis_client:
            logger.info("AdvancedCacheManager initialized with Redis backend")
        else:
            logger.warning(
                "AdvancedCacheManager initialized without Redis - caching disabled"
            )

    async def _ensure_redis_client(self):
        """Ensure async Redis client is initialized"""
        if not self._redis_client_initialized:
            try:
                self.redis_client = await get_redis_client(async_client=True)
                self._redis_client_initialized = True
                logger.debug("Async Redis client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize async Redis client: {e}")
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
                logger.debug(f"Cache HIT for {data_type}:{key}")
                return data
            else:
                # Update miss statistics
                await self._update_stats(data_type, hit=False)
                logger.debug(f"Cache MISS for {data_type}:{key}")
                return None

        except Exception as e:
            logger.error(f"Error getting cached data for {data_type}:{key}: {e}")
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

            logger.debug(f"Cache SET for {data_type}:{key} (TTL: {ttl}s)")
            return True

        except Exception as e:
            logger.error(f"Error setting cached data for {data_type}:{key}: {e}")
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
            logger.error(f"Error computing data for {data_type}:{key}: {e}")
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
                    f"Cache INVALIDATE: {deleted_count} keys deleted for {data_type}"
                )
                return deleted_count
            return 0

        except Exception as e:
            logger.error(f"Error invalidating cache for {data_type}: {e}")
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
            logger.error(f"Error updating cache stats for {data_type}: {e}")

    async def get_stats(self, data_type: Optional[str] = None) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        await self._ensure_redis_client()
        if not self.redis_client:
            return {"status": "disabled"}

        try:
            if data_type:
                # Get stats for specific data type
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
            else:
                # Get global stats
                cache_keys = await self.redis_client.keys(f"{self.cache_prefix}*")
                stats_keys = await self.redis_client.keys(f"{self.stats_prefix}*")

                total_hits = 0
                total_misses = 0

                for stats_key in stats_keys:
                    stats = await self.redis_client.hgetall(stats_key)
                    total_hits += int(stats.get("hits", 0))
                    total_misses += int(stats.get("misses", 0))

                total_requests = total_hits + total_misses
                global_hit_rate = (
                    (total_hits / total_requests * 100) if total_requests > 0 else 0
                )

                # Get memory usage
                try:
                    info = await self.redis_client.info("memory")
                    memory_usage = info.get("used_memory_human", "N/A")
                except Exception:
                    memory_usage = "N/A"

                return {
                    "status": "enabled",
                    "total_cache_keys": len(cache_keys),
                    "total_hits": total_hits,
                    "total_misses": total_misses,
                    "global_hit_rate": f"{global_hit_rate:.1f}%",
                    "memory_usage": memory_usage,
                    "configured_data_types": list(self.cache_configs.keys()),
                }

        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
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

            logger.info(f"Cache WARM: {warmed_count} entries warmed for {data_type}")
            return warmed_count > 0

        except Exception as e:
            logger.error(f"Error warming cache for {data_type}: {e}")
            return False


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
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default key generation from function name and args
                args_hash = hashlib.md5(
                    str(args + tuple(kwargs.items())).encode()
                ).hexdigest()[:8]
                cache_key = f"{func.__name__}:{args_hash}"

            # Extract user ID if needed
            user_id = None
            if user_id_func:
                user_id = user_id_func(*args, **kwargs)

            # Use get_or_compute for intelligent caching
            async def compute():
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
    for data_type in ["user_preferences", "user_history"]:
        count += await advanced_cache.invalidate(data_type, "*", user_id)
    return count
