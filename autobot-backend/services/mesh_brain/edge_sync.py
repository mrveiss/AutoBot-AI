# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""PostgreSQL to Redis edge sync for Neural Mesh retrieval (#1994, #2029)."""
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class MeshDB(Protocol):
    """Protocol for mesh database operations."""

    async def fetch_edges(self, min_weight: float) -> list[dict]:
        ...


class MeshEdgeSync:
    """Syncs high-weight edges from PostgreSQL to Redis sorted sets."""

    def __init__(self, db: MeshDB, redis, min_weight: float = 0.5):
        self.db = db
        self.redis = redis
        self.min_weight = min_weight

    async def sync(self) -> int:
        """Sync edges above min_weight to Redis. Returns count synced."""
        edges = await self.db.fetch_edges(min_weight=self.min_weight)
        if not edges:
            logger.info("No edges above weight %.2f to sync", self.min_weight)
            return 0

        synced = 0
        pipe = self.redis.pipeline()
        nodes_touched = set()

        for edge in edges:
            from_node = str(edge["from_node"])
            to_node = str(edge["to_node"])
            weight = float(edge["weight"])

            key = f"mesh:edges:{from_node}"
            pipe.zadd(key, {to_node: weight})
            nodes_touched.add(from_node)

            rev_key = f"mesh:edges:{to_node}"
            pipe.zadd(rev_key, {from_node: weight})
            nodes_touched.add(to_node)
            synced += 1

        await pipe.execute()
        logger.info(
            "Synced %d edges across %d nodes",
            synced,
            len(nodes_touched),
        )
        return synced

    async def get_neighbors(
        self,
        node_id: str,
        min_weight: float = 0.0,
        limit: int = 20,
    ):
        """Get neighbors from Redis sorted set (fast path)."""
        key = f"mesh:edges:{node_id}"
        return await self.redis.zrangebyscore(
            key,
            min=min_weight,
            max="+inf",
            start=0,
            num=limit,
            withscores=True,
        )
