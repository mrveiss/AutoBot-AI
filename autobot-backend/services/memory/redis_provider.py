# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Redis Memory Provider (Issue #4344)"""

import json
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.redis_management.types import DATABASE_MAPPING
from autobot_shared.ssot_constants import TTL_24_HOURS

logger = get_logger(__name__)


class RedisMemoryProvider:
    """Redis-backed memory provider for fast memory retrieval."""

    def __init__(self) -> None:
        self.redis = None
        self.db = DATABASE_MAPPING.get("main", 0)
        self.prefix = "autobot:memory"

    async def initialize(self) -> None:
        try:
            self.redis = await get_redis_client(db=self.db)
            logger.info("Redis memory provider initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Redis memory provider: {e}")
            raise

    async def close(self) -> None:
        if self.redis:
            try:
                await self.redis.close()
                logger.info("Redis memory provider closed")
            except Exception as e:
                logger.error(f"Error closing Redis memory provider: {e}")

    async def prefetch(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.redis:
            logger.warning("Redis not initialized for prefetch")
            return {}
        try:
            conversation_id = context.get("conversation_id")
            cache_key = f"{self.prefix}:cache:{conversation_id}"
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
            return {}
        except Exception as e:
            logger.error(f"Error prefetching from Redis: {e}")
            return {}

    async def sync(self, turn: Dict[str, Any]) -> None:
        if not self.redis:
            logger.warning("Redis not initialized for sync")
            return
        try:
            conversation_id = turn.get("conversation_id")
            if not conversation_id:
                return
            cache_key = f"{self.prefix}:cache:{conversation_id}"
            cache_data = {
                "timestamp": turn.get("timestamp"),
                "entity_updates": turn.get("entity_updates", []),
                "relation_updates": turn.get("relation_updates", []),
            }
            await self.redis.setex(cache_key, TTL_24_HOURS, json.dumps(cache_data, default=str))
            logger.debug(f"Cached turn data for {conversation_id}")
        except Exception as e:
            logger.error(f"Error syncing to Redis: {e}")

    async def search(self, query: str, limit: int = 10, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        if not self.redis:
            return []
        try:
            query_hash = hash(query) % (10**8)
            cache_key = f"{self.prefix}:search:{query_hash}"
            cached = await self.redis.get(cache_key)
            if cached:
                results = json.loads(cached)
                return results[:limit]
            return []
        except Exception as e:
            logger.error(f"Error searching Redis cache: {e}")
            return []

    async def get_entity(self, entity_id: str) -> Dict[str, Any] | None:
        if not self.redis:
            return None
        try:
            cache_key = f"{self.prefix}:entity:{entity_id}"
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            logger.error(f"Error getting entity from Redis: {e}")
            return None

    async def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> None:
        if not self.redis:
            logger.warning("Redis not initialized for update")
            return
        try:
            cache_key = f"{self.prefix}:entity:{entity_id}"
            entity = await self.get_entity(entity_id)
            if entity:
                entity.update(updates)
                await self.redis.setex(cache_key, TTL_24_HOURS, json.dumps(entity, default=str))
        except Exception as e:
            logger.error(f"Error updating entity in Redis: {e}")

    async def delete_entity(self, entity_id: str) -> None:
        if not self.redis:
            return
        try:
            cache_key = f"{self.prefix}:entity:{entity_id}"
            await self.redis.delete(cache_key)
        except Exception as e:
            logger.error(f"Error deleting entity from Redis: {e}")

    async def health_check(self) -> bool:
        if not self.redis:
            return False
        try:
            await self.redis.ping()
            return True
        except Exception as e:
            logger.error(f"Redis memory provider health check failed: {e}")
            return False
