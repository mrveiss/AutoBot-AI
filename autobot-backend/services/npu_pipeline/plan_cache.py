# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RedisShardPlanCache — stores and retrieves shard plans under ``npu:pipeline:<plan_id>``.

Each entry is a JSON-serialised list of ``ShardAssignment`` dicts.  Plans are
keyed by ``plan_id_for(model_id, active_worker_ids)`` so that a change in the
worker set automatically misses the old plan.
"""

from __future__ import annotations

import json
from typing import List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

from services.npu_pipeline.shard_planner import LayerRange, ShardAssignment

logger = get_logger(__name__)

_REDIS_DATABASE = "main"
_KEY_PREFIX = "npu:pipeline:"
_DEFAULT_TTL = 3600  # 1 hour


class RedisShardPlanCache:
    """Redis-backed shard plan store.

    Keys live at ``npu:pipeline:<plan_id>`` and expire after *ttl* seconds.
    """

    def __init__(self, ttl: int = _DEFAULT_TTL) -> None:
        self._ttl = ttl

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, plan_id: str) -> Optional[List[ShardAssignment]]:
        """Return cached plan or *None* on miss."""
        try:
            client = await get_async_redis_client(database=_REDIS_DATABASE)
            raw = await client.get(self._key(plan_id))
            if raw is None:
                return None
            data = json.loads(raw if isinstance(raw, str) else raw.decode())
            return [self._deserialise(item) for item in data]
        except Exception as exc:
            logger.warning("ShardPlanCache get error (plan_id=%s): %s", plan_id, exc)
            return None

    async def set(self, plan_id: str, assignments: List[ShardAssignment]) -> bool:
        """Persist *assignments* under *plan_id*."""
        try:
            client = await get_async_redis_client(database=_REDIS_DATABASE)
            payload = json.dumps([self._serialise(a) for a in assignments])
            await client.set(self._key(plan_id), payload, ex=self._ttl)
            return True
        except Exception as exc:
            logger.warning("ShardPlanCache set error (plan_id=%s): %s", plan_id, exc)
            return False

    async def delete(self, plan_id: str) -> bool:
        """Remove the plan entry for *plan_id*."""
        try:
            client = await get_async_redis_client(database=_REDIS_DATABASE)
            await client.delete(self._key(plan_id))
            return True
        except Exception as exc:
            logger.warning("ShardPlanCache delete error (plan_id=%s): %s", plan_id, exc)
            return False

    async def delete_by_prefix(self, prefix: str) -> int:
        """Delete all plan keys whose plan_id starts with *prefix*.

        Used by the invalidation layer when a worker is added/removed —
        caller passes ``model_id`` as prefix to drop all plans for that model.
        """
        try:
            client = await get_async_redis_client(database=_REDIS_DATABASE)
            pattern = self._key(f"{prefix}*")
            keys = await client.keys(pattern)
            if not keys:
                return 0
            count = await client.delete(*keys)
            logger.info("ShardPlanCache evicted %d plan(s) for prefix='%s'", count, prefix)
            return count
        except Exception as exc:
            logger.warning("ShardPlanCache delete_by_prefix error (prefix=%s): %s", prefix, exc)
            return 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _key(plan_id: str) -> str:
        return f"{_KEY_PREFIX}{plan_id}"

    @staticmethod
    def _serialise(assignment: ShardAssignment) -> dict:
        return {
            "worker_id": assignment.worker_id,
            "start": assignment.layer_range.start,
            "end": assignment.layer_range.end,
        }

    @staticmethod
    def _deserialise(data: dict) -> ShardAssignment:
        return ShardAssignment(
            worker_id=data["worker_id"],
            layer_range=LayerRange(start=data["start"], end=data["end"]),
        )
