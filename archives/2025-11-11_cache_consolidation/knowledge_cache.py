"""
Knowledge Base Query Caching System
Implements Redis-based caching for knowledge base search results to improve performance.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from src.config_helper import cfg
from src.constants.network_constants import NetworkConstants
from src.utils.redis_client import get_redis_client


class KnowledgeCache:
    """Redis-based caching system for knowledge base queries."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._redis_client = None
        self._cache_db = cfg.get("redis.databases.cache.db", 2)  # Use cache database
        self._cache_ttl = cfg.get("knowledge_base.cache.ttl", 300)  # 5 minutes default
        self._cache_prefix = cfg.get("knowledge_base.cache.prefix", "kb_cache:")
        self._max_cache_size = cfg.get("knowledge_base.cache.max_size", 1000)

    async def _get_redis_client(self):
        """Get or initialize the Redis client for caching."""
        if self._redis_client is None:
            try:
                self._redis_client = get_redis_client(
                    async_client=True, db=self._cache_db
                )
                if asyncio.iscoroutine(self._redis_client):
                    self._redis_client = await self._redis_client
                self.logger.debug(
                    f"Knowledge cache Redis client initialized for DB {self._cache_db}"
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to initialize knowledge cache Redis client: {e}"
                )
                self._redis_client = None
        return self._redis_client

    def _generate_cache_key(
        self, query: str, top_k: int, filters: Optional[Dict] = None
    ) -> str:
        """Generate a cache key for the query parameters."""
        # Create a consistent hash of the query parameters
        cache_data = {
            "query": query.lower().strip(),
            "top_k": top_k,
            "filters": filters or {},
        }
        cache_string = json.dumps(cache_data, sort_keys=True)
        cache_hash = hashlib.sha256(cache_string.encode()).hexdigest()[:16]
        return f"{self._cache_prefix}query:{cache_hash}"

    async def get_cached_results(
        self, query: str, top_k: int, filters: Optional[Dict] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Retrieve cached search results if available."""
        try:
            redis_client = await self._get_redis_client()
            if not redis_client:
                return None

            cache_key = self._generate_cache_key(query, top_k, filters)

            # Get cached data with pipeline for efficiency
            async with redis_client.pipeline() as pipe:
                pipe.hgetall(cache_key)
                pipe.expire(cache_key, self._cache_ttl)  # Refresh TTL on access
                result = await pipe.execute()

            cached_data = result[0]
            if not cached_data:
                return None

            # Parse cached results
            results_json = cached_data.get(b"results") or cached_data.get("results")
            if results_json:
                results = json.loads(results_json)
                cache_time = float(
                    cached_data.get(b"timestamp") or cached_data.get("timestamp", 0)
                )

                # Check if cache is still valid
                if time.time() - cache_time < self._cache_ttl:
                    self.logger.debug(f"Cache HIT for query: '{query}' (top_k={top_k})")
                    return results
                else:
                    # Cache expired, delete it
                    await redis_client.delete(cache_key)
                    self.logger.debug(f"Cache EXPIRED for query: '{query}'")

            return None

        except Exception as e:
            self.logger.error(f"Error retrieving cached results: {e}")
            return None

    async def cache_results(
        self,
        query: str,
        top_k: int,
        results: List[Dict[str, Any]],
        filters: Optional[Dict] = None,
    ) -> bool:
        """Cache search results for future use."""
        try:
            redis_client = await self._get_redis_client()
            if not redis_client:
                return False

            cache_key = self._generate_cache_key(query, top_k, filters)

            # Prepare cache data
            cache_data = {
                "results": json.dumps(results),
                "timestamp": str(time.time()),
                "query": query[:200],  # Store truncated query for debugging
                "top_k": str(top_k),
                "result_count": str(len(results)),
            }

            # Store with TTL
            await redis_client.hset(cache_key, mapping=cache_data)
            await redis_client.expire(cache_key, self._cache_ttl)

            # Implement cache size management
            await self._manage_cache_size(redis_client)

            self.logger.debug(
                f"Cached {len(results)} results for query: '{query}' (top_k={top_k})"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error caching results: {e}")
            return False

    async def _manage_cache_size(self, redis_client):
        """Manage cache size by removing oldest entries if needed."""
        try:
            # Count current cache entries
            cache_count = 0
            oldest_keys = []

            async for key in redis_client.scan_iter(match=f"{self._cache_prefix}*"):
                cache_count += 1
                if cache_count > self._max_cache_size:
                    # Get timestamp for LRU eviction
                    timestamp_data = await redis_client.hget(key, "timestamp")
                    if timestamp_data:
                        timestamp = float(timestamp_data)
                        oldest_keys.append((timestamp, key))

            # Remove oldest entries if cache is too large
            if oldest_keys:
                oldest_keys.sort()  # Sort by timestamp
                keys_to_remove = oldest_keys[
                    : len(oldest_keys) - self._max_cache_size + 100
                ]  # Remove extra for buffer

                if keys_to_remove:
                    keys_only = [key for _, key in keys_to_remove]
                    await redis_client.delete(*keys_only)
                    self.logger.info(
                        f"Removed {len(keys_only)} old cache entries to manage cache size"
                    )

        except Exception as e:
            self.logger.error(f"Error managing cache size: {e}")

    async def clear_cache(self, pattern: Optional[str] = None) -> int:
        """Clear cached results. If pattern provided, only clear matching keys."""
        try:
            redis_client = await self._get_redis_client()
            if not redis_client:
                return 0

            search_pattern = pattern or f"{self._cache_prefix}*"
            deleted_count = 0

            # Use SCAN to find and delete keys in batches
            batch_size = 100
            keys_to_delete = []

            async for key in redis_client.scan_iter(
                match=search_pattern, count=batch_size
            ):
                keys_to_delete.append(key)

                if len(keys_to_delete) >= batch_size:
                    deleted_count += await redis_client.delete(*keys_to_delete)
                    keys_to_delete = []

            # Delete remaining keys
            if keys_to_delete:
                deleted_count += await redis_client.delete(*keys_to_delete)

            self.logger.info(
                f"Cleared {deleted_count} cache entries with pattern: {search_pattern}"
            )
            return deleted_count

        except Exception as e:
            self.logger.error(f"Error clearing cache: {e}")
            return 0

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            redis_client = await self._get_redis_client()
            if not redis_client:
                return {"error": "Redis client not available"}

            # Count cache entries
            cache_count = 0
            total_size = 0
            oldest_timestamp = None
            newest_timestamp = None

            async for key in redis_client.scan_iter(match=f"{self._cache_prefix}*"):
                cache_count += 1

                # Get memory usage and timestamp
                try:
                    key_info = await redis_client.hgetall(key)
                    if key_info:
                        timestamp_data = key_info.get(b"timestamp") or key_info.get(
                            "timestamp"
                        )
                        if timestamp_data:
                            timestamp = float(timestamp_data)
                            if oldest_timestamp is None or timestamp < oldest_timestamp:
                                oldest_timestamp = timestamp
                            if newest_timestamp is None or timestamp > newest_timestamp:
                                newest_timestamp = timestamp

                        # Estimate size
                        total_size += len(str(key_info))

                except Exception:
                    continue

            stats = {
                "cache_entries": cache_count,
                "estimated_size_bytes": total_size,
                "max_cache_size": self._max_cache_size,
                "cache_ttl_seconds": self._cache_ttl,
                "cache_utilization": (
                    f"{cache_count / self._max_cache_size * 100:.1f}%"
                    if self._max_cache_size > 0
                    else "N/A"
                ),
            }

            if oldest_timestamp and newest_timestamp:
                stats["cache_age_range_seconds"] = newest_timestamp - oldest_timestamp

            return stats

        except Exception as e:
            self.logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}


# Global cache instance
_knowledge_cache = None


def get_knowledge_cache() -> KnowledgeCache:
    """Get the global knowledge cache instance."""
    global _knowledge_cache
    if _knowledge_cache is None:
        _knowledge_cache = KnowledgeCache()
    return _knowledge_cache
