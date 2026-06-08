# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""PostgreSQL to Redis edge sync for Neural Mesh retrieval (#1994, #2029)."""

from typing import Protocol

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class MeshDB(Protocol):
    """Protocol for mesh database operations."""

    async def fetch_edges(self, min_weight: float) -> list[dict]: ...


class MeshEdgeSync:
    """Syncs high-weight edges from PostgreSQL to Redis sorted sets."""

    def __init__(self, db: MeshDB, redis, min_weight: float = 0.5) -> None:
        self.db = db
        self.redis = redis
        self.min_weight = min_weight

    @staticmethod
    def _collect_nodes(edges: list[dict]) -> set[str]:
        """Return the set of all node IDs touched by the given edge list (#2053)."""
        nodes: set[str] = set()
        for edge in edges:
            nodes.add(str(edge["from_node"]))
            nodes.add(str(edge["to_node"]))
        return nodes

    async def sync(self) -> int:
        """Sync edges above min_weight to Redis. Returns count synced.

        Stale entries are removed by deleting each touched node's sorted-set
        key before writing fresh ZADD entries (#2053).
        """
        edges = await self.db.fetch_edges(min_weight=self.min_weight)
        if not edges:
            logger.info("No edges above weight %.2f to sync", self.min_weight)
            return 0

        nodes_touched = self._collect_nodes(edges)
        pipe = self.redis.pipeline()
        self._clear_stale_keys(pipe, nodes_touched)
        synced = self._enqueue_zadd(pipe, edges)
        await pipe.execute()
        logger.info("Synced %d edges across %d nodes", synced, len(nodes_touched))
        return synced

    @staticmethod
    def _clear_stale_keys(pipe, nodes: set[str]) -> None:
        """Delete sorted-set keys for all nodes before re-writing (#2053)."""
        for node_id in nodes:
            pipe.delete(f"mesh:edges:{node_id}")

    @staticmethod
    def _enqueue_zadd(pipe, edges: list[dict]) -> int:
        """Queue ZADD commands for every edge (bidirectional). Returns edge count."""
        for edge in edges:
            from_node = str(edge["from_node"])
            to_node = str(edge["to_node"])
            weight = float(edge["weight"])
            pipe.zadd(f"mesh:edges:{from_node}", {to_node: weight})
            pipe.zadd(f"mesh:edges:{to_node}", {from_node: weight})
        return len(edges)

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
