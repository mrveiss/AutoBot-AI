# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
DEPRECATED: This module is deprecated as of 2025-11-11 (Phase 4 Cache Consolidation)
Use src.utils.advanced_cache_manager instead.

Migration:
    OLD: from backend.utils.cache_manager import cache_manager, cache_response
    NEW: from src.utils.advanced_cache_manager import cache_manager, cache_response

All functionality preserved in unified AdvancedCacheManager.
Archived: archives/2025-11-11_cache_consolidation/cache_manager.py

---

Redis-based caching manager for performance optimization
Implements TTL-based caching for frequently requested API endpoints
"""

import functools
import json
import logging
from typing import Any, Optional

from fastapi import Request

# Import centralized Redis client utility
from utils.redis_client import get_redis_client

from backend.type_defs.common import Metadata

logger = logging.getLogger(__name__)


class CacheManager:
    """Redis-based cache manager with TTL support"""

    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        """Initialize cache manager with default TTL and Redis client state."""
        self.default_ttl = default_ttl
        self.cache_prefix = "cache:"
        self._redis_client = None
        self._redis_initialized = False

    async def _ensure_redis_client(self):
        """Ensure Redis client is initialized (async)"""
        if self._redis_initialized:
            return

        try:
            # Get async Redis client
            client = get_redis_client(async_client=True)

            # If it's a coroutine, await it
            if hasattr(client, "__await__"):
                self._redis_client = await client
            else:
                self._redis_client = client

            if self._redis_client:
                logger.info("CacheManager Redis client initialized successfully")
            else:
                logger.warning("CacheManager Redis client is None - caching disabled")

            self._redis_initialized = True

        except Exception as e:
            logger.error("Failed to initialize Redis client: %s", e)
            self._redis_client = None
            self._redis_initialized = True

    def _make_cache_key(self, key: str) -> str:
        """Generate cache key with prefix"""
        return f"{self.cache_prefix}{key}"

    async def get(self, key: str) -> Optional[Metadata]:
        """Get cached data by key"""
        await self._ensure_redis_client()

        if not self._redis_client:
            return None

        try:
            cache_key = self._make_cache_key(key)
            cached_data = await self._redis_client.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)
                logger.debug("Cache HIT for key: %s", key)
                return data
            else:
                logger.debug("Cache MISS for key: %s", key)
                return None

        except Exception as e:
            logger.error("Error getting cached data for key %s: %s", key, e)
            return None

    async def set(self, key: str, data: Metadata, ttl: Optional[int] = None) -> bool:
        """Set cached data with TTL"""
        await self._ensure_redis_client()

        if not self._redis_client:
            return False

        try:
            cache_key = self._make_cache_key(key)
            ttl_seconds = ttl or self.default_ttl

            serialized_data = json.dumps(data, default=str)
            await self._redis_client.setex(cache_key, ttl_seconds, serialized_data)

            logger.debug("Cache SET for key: %s (TTL: %ss)", key, ttl_seconds)
            return True

        except Exception as e:
            logger.error("Error setting cached data for key %s: %s", key, e)
            return False

    async def delete(self, key: str) -> bool:
        """Delete cached data by key"""
        await self._ensure_redis_client()

        if not self._redis_client:
            return False

        try:
            cache_key = self._make_cache_key(key)
            result = await self._redis_client.delete(cache_key)

            if result:
                logger.debug("Cache DELETE for key: %s", key)
                return True
            else:
                logger.debug("Cache DELETE failed - key not found: %s", key)
                return False

        except Exception as e:
            logger.error("Error deleting cached data for key %s: %s", key, e)
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Clear multiple cache keys matching pattern"""
        await self._ensure_redis_client()

        if not self._redis_client:
            return 0

        try:
            search_pattern = f"{self.cache_prefix}{pattern}"
            keys = await self._redis_client.keys(search_pattern)

            if keys:
                deleted_count = await self._redis_client.delete(*keys)
                logger.info(
                    f"Cache CLEAR: {deleted_count} keys deleted for pattern: {pattern}"
                )
                return deleted_count
            else:
                logger.debug("Cache CLEAR: No keys found for pattern: %s", pattern)
                return 0

        except Exception as e:
            logger.error("Error clearing cache for pattern %s: %s", pattern, e)
            return 0

    async def get_stats(self) -> Metadata:
        """Get cache statistics"""
        await self._ensure_redis_client()

        if not self._redis_client:
            return {"status": "disabled", "total_keys": 0}

        try:
            cache_keys = await self._redis_client.keys(f"{self.cache_prefix}*")
            total_keys = len(cache_keys)

            # Get memory usage info if available
            try:
                info = await self._redis_client.info("memory")
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


# Create global cache manager instance
cache_manager = CacheManager()


# FastAPI 0.115.9 compatible decorator for caching API responses
def cache_response(cache_key: str = None, ttl: int = 300):
    """
    FastAPI 0.115.9 compatible decorator to cache API endpoint responses

    Args:
        cache_key: Custom cache key (optional, defaults to endpoint path)
        ttl: Time to live in seconds (default: 5 minutes)
    """

    def decorator(func):
        """Create async wrapper with cache lookup and storage for FastAPI endpoints."""

        @functools.wraps(func)  # Preserve function signature for FastAPI
        async def wrapper(*args, **kwargs):
            """Async wrapper with cache lookup before execution and cache storage after."""
            # Extract request object from FastAPI dependency injection
            request = None

            # Check for Request object in kwargs (FastAPI dependency injection)
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
                cached_result = await cache_manager.get(key)
                if cached_result is not None:
                    logger.debug("Cache HIT: %s - serving from cache", key)
                    return cached_result
            except Exception as e:
                logger.error("Cache retrieval error for key %s: %s", key, e)

            # Execute function and cache result
            logger.debug("Cache MISS: %s - executing function", key)
            result = await func(*args, **kwargs)

            # Cache successful responses
            if _is_cacheable_response(result):
                try:
                    await cache_manager.set(key, result, ttl)
                    logger.debug("Cache SET: %s - cached for %ss", key, ttl)
                except Exception as e:
                    logger.error("Cache storage error for key %s: %s", key, e)

            return result

        return wrapper

    return decorator


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


# Simple cache decorator for non-HTTP functions
def cache_function(cache_key: str = None, ttl: int = 300):
    """
    Simple cache decorator for non-FastAPI functions

    Args:
        cache_key: Custom cache key (optional, defaults to function name + args hash)
        ttl: Time to live in seconds (default: 5 minutes)
    """

    def decorator(func):
        """Create async wrapper with cache lookup and storage for non-HTTP functions."""

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            """Async wrapper with cache lookup and storage for non-HTTP functions."""
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

            if _is_cacheable_response(result):
                try:
                    await cache_manager.set(key, result, ttl)
                except Exception as e:
                    logger.error("Cache storage error for key %s: %s", key, e)

            return result

        return wrapper

    return decorator
