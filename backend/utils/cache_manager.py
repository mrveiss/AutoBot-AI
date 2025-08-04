"""
Redis-based caching manager for performance optimization
Implements TTL-based caching for frequently requested API endpoints
"""

import json
import logging
import asyncio
from typing import Any, Dict, Optional, Union
from datetime import datetime, timedelta

# Import centralized Redis client utility
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class CacheManager:
    """Redis-based cache manager with TTL support"""

    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self.redis_client = get_redis_client(async_client=True)
        self.default_ttl = default_ttl
        self.cache_prefix = "cache:"

        if self.redis_client:
            logger.info("CacheManager initialized with Redis backend")
        else:
            logger.warning("CacheManager initialized without Redis - caching disabled")

    def _make_cache_key(self, key: str) -> str:
        """Generate cache key with prefix"""
        return f"{self.cache_prefix}{key}"

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached data by key"""
        if not self.redis_client:
            return None

        try:
            cache_key = self._make_cache_key(key)
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)
                logger.debug(f"Cache HIT for key: {key}")
                return data
            else:
                logger.debug(f"Cache MISS for key: {key}")
                return None

        except Exception as e:
            logger.error(f"Error getting cached data for key {key}: {e}")
            return None

    async def set(
        self, key: str, data: Dict[str, Any], ttl: Optional[int] = None
    ) -> bool:
        """Set cached data with TTL"""
        if not self.redis_client:
            return False

        try:
            cache_key = self._make_cache_key(key)
            ttl_seconds = ttl or self.default_ttl

            serialized_data = json.dumps(data, default=str)
            await self.redis_client.setex(cache_key, ttl_seconds, serialized_data)

            logger.debug(f"Cache SET for key: {key} (TTL: {ttl_seconds}s)")
            return True

        except Exception as e:
            logger.error(f"Error setting cached data for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete cached data by key"""
        if not self.redis_client:
            return False

        try:
            cache_key = self._make_cache_key(key)
            result = await self.redis_client.delete(cache_key)

            if result:
                logger.debug(f"Cache DELETE for key: {key}")
                return True
            else:
                logger.debug(f"Cache DELETE failed - key not found: {key}")
                return False

        except Exception as e:
            logger.error(f"Error deleting cached data for key {key}: {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Clear multiple cache keys matching pattern"""
        if not self.redis_client:
            return 0

        try:
            search_pattern = f"{self.cache_prefix}{pattern}"
            keys = await self.redis_client.keys(search_pattern)

            if keys:
                deleted_count = await self.redis_client.delete(*keys)
                logger.info(
                    f"Cache CLEAR: {deleted_count} keys deleted for pattern: {pattern}"
                )
                return deleted_count
            else:
                logger.debug(f"Cache CLEAR: No keys found for pattern: {pattern}")
                return 0

        except Exception as e:
            logger.error(f"Error clearing cache for pattern {pattern}: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.redis_client:
            return {"status": "disabled", "total_keys": 0}

        try:
            cache_keys = await self.redis_client.keys(f"{self.cache_prefix}*")
            total_keys = len(cache_keys)

            # Get memory usage info if available
            try:
                info = await self.redis_client.info("memory")
                memory_usage = info.get("used_memory_human", "N/A")
            except:
                memory_usage = "N/A"

            return {
                "status": "enabled",
                "total_keys": total_keys,
                "memory_usage": memory_usage,
                "default_ttl": self.default_ttl,
            }

        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"status": "error", "error": str(e)}


# Create global cache manager instance
cache_manager = CacheManager()


# Decorator for caching API responses
def cache_response(cache_key: str = None, ttl: int = 300):
    """
    Decorator to cache API endpoint responses

    Args:
        cache_key: Custom cache key (optional, defaults to endpoint path)
        ttl: Time to live in seconds (default: 5 minutes)
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract request object if available
            request = None
            for arg in args:
                if hasattr(arg, "url"):
                    request = arg
                    break

            # Generate cache key
            if cache_key:
                key = cache_key
            elif request:
                key = f"endpoint:{request.url.path}:{hash(str(kwargs))}"
            else:
                key = f"func:{func.__name__}:{hash(str(kwargs))}"

            # Try to get from cache first
            cached_result = await cache_manager.get(key)
            if cached_result is not None:
                return cached_result

            # Execute function and cache result
            result = await func(*args, **kwargs)

            # Only cache successful responses (dict with no error status)
            if isinstance(result, dict) and not result.get("error"):
                await cache_manager.set(key, result, ttl)

            return result

        return wrapper

    return decorator
