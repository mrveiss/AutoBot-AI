# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis Memory Provider (Issue #4344)"""

import json
from typing import Any, Dict, List

from autobot_memory_graph.owner_scope import (
    OWNER_ORG_FIELD,
    OWNER_USER_FIELD,
    entity_visible,
    owner_fields,
    owner_from_source,
)
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.redis_management.types import DATABASE_MAPPING
from autobot_shared.ssot_constants import TTL_24_HOURS

logger = get_logger(__name__)


class RedisMemoryProvider:
    """Redis-backed memory provider for fast memory retrieval.

    Every cached document records its owner (#18825) and every read re-checks it against the caller's
    scope. A caller with no scope -- or a document with no recorded owner -- reads nothing: the cache is
    keyed by conversation / query, never by user, so the key alone is not an authorisation.
    """

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
        owner = owner_from_source(context)
        if owner is None:
            logger.warning("Redis prefetch refused: context carries no user scope (fail closed, #18825)")
            return {}
        try:
            conversation_id = context.get("conversation_id")
            cache_key = f"{self.prefix}:cache:{conversation_id}"
            cached = await self.redis.get(cache_key)
            data = json.loads(cached) if cached else None
            if not entity_visible(data, owner):
                return {}
            return {k: v for k, v in data.items() if k not in (OWNER_USER_FIELD, OWNER_ORG_FIELD)}
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
            owner = owner_from_source(turn)
            if owner is None:
                logger.warning("Redis sync skipped: turn carries no user scope (fail closed, #18825)")
                return
            cache_key = f"{self.prefix}:cache:{conversation_id}"
            cache_data = {
                **owner_fields(owner),
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
        owner = owner_from_source(filters)
        if owner is None:
            logger.warning("Redis search refused: filters carry no user scope (fail closed, #18825)")
            return []
        try:
            query_hash = hash(query) % (10**8)
            cache_key = f"{self.prefix}:search:{query_hash}"
            cached = await self.redis.get(cache_key)
            if cached:
                visible = [r for r in json.loads(cached) if entity_visible(r, owner)]
                return visible[:limit]
            return []
        except Exception as e:
            logger.error(f"Error searching Redis cache: {e}")
            return []

    async def get_entity(self, entity_id: str, *, owner: Any = None) -> Dict[str, Any] | None:
        if owner is None:
            logger.warning("Redis entity read refused: no caller scope supplied (fail closed, #18825)")
            return None
        entity = await self._load_entity(entity_id)
        return entity if entity_visible(entity, owner) else None

    async def _load_entity(self, entity_id: str) -> Dict[str, Any] | None:
        """The cached document, whoever owns it. For by-id mutations only (not owner-scoped, #18876)."""
        if not self.redis:
            return None
        try:
            cached = await self.redis.get(f"{self.prefix}:entity:{entity_id}")
            return json.loads(cached) if cached else None
        except Exception as e:
            logger.error(f"Error getting entity from Redis: {e}")
            return None

    async def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> None:
        if not self.redis:
            logger.warning("Redis not initialized for update")
            return
        try:
            cache_key = f"{self.prefix}:entity:{entity_id}"
            entity = await self._load_entity(entity_id)
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
