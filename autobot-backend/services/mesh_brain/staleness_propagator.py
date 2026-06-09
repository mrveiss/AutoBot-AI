# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""BFS staleness propagation for Neural Mesh knowledge graph (#1994, #2111)."""

from collections import deque
from typing import Protocol

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class MeshGraph(Protocol):
    """Protocol for graph traversal operations needed by staleness propagation."""

    async def get_neighbors(self, node_id: str) -> list[tuple[str, float]]:
        """Return list of (neighbor_id, edge_weight) for the given node."""
        ...


class StalenessResult:
    """Container for BFS staleness propagation results."""

    def __init__(self, scores: dict[str, float], source_node: str, max_depth: int, decay: float) -> None:
        self.scores = scores
        self.source_node = source_node
        self.max_depth = max_depth
        self.decay = decay

    def above_threshold(self, threshold: float = 0.3) -> dict[str, float]:
        """Return nodes with staleness score at or above the threshold."""
        return {nid: score for nid, score in self.scores.items() if score >= threshold}

    def flagged_for_reembedding(self, threshold: float = 0.3) -> list[str]:
        """Return node IDs that should be queued for re-embedding.

        Excludes the source node (it was just updated, not stale).
        """
        return [nid for nid, score in self.scores.items() if score >= threshold and nid != self.source_node]


async def propagate_staleness(
    graph: MeshGraph,
    changed_doc_id: str,
    max_depth: int = 3,
    decay: float = 0.7,
) -> StalenessResult:
    """BFS propagation: staleness_score = decay^depth * edge_weight for each neighbor.

    When multiple paths reach the same node, the highest score is kept so that
    strongly-connected neighbours always reflect the worst-case staleness.

    Args:
        graph: Graph interface providing neighbor lookups.
        changed_doc_id: The document that was updated.
        max_depth: Maximum BFS depth (default 3).
        decay: Decay factor per hop (default 0.7).

    Returns:
        StalenessResult with per-node staleness scores.
    """
    staleness: dict[str, float] = {changed_doc_id: 1.0}
    queue: deque[tuple[str, int]] = deque([(changed_doc_id, 0)])

    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        neighbors = await graph.get_neighbors(node)
        for neighbor_id, edge_weight in neighbors:
            score = (decay ** (depth + 1)) * edge_weight
            if neighbor_id not in staleness or score > staleness[neighbor_id]:
                staleness[neighbor_id] = score
                queue.append((neighbor_id, depth + 1))

    logger.info(
        "Staleness propagation from %s: %d nodes affected (depth=%d, decay=%.2f)",
        changed_doc_id,
        len(staleness) - 1,
        max_depth,
        decay,
    )
    return StalenessResult(staleness, changed_doc_id, max_depth, decay)


async def store_staleness_scores(redis, scores: dict[str, float], ttl: int = 3600) -> int:
    """Store staleness scores in Redis for hot-path retrieval.

    Args:
        redis: Async Redis client.
        scores: {doc_id: staleness_score} mapping.
        ttl: Time-to-live in seconds (default 1 hour).

    Returns:
        Number of scores stored.
    """
    pipe = redis.pipeline()
    for doc_id, score in scores.items():
        key = f"mesh:staleness:{doc_id}"
        pipe.set(key, str(score), ex=ttl)
    await pipe.execute()
    return len(scores)


async def get_staleness_score(redis, doc_id: str) -> float:
    """Retrieve staleness score for a document from Redis.

    Returns:
        Staleness score (0-1), or 0.0 if the document is fresh / has no score.
    """
    value = await redis.get(f"mesh:staleness:{doc_id}")
    return float(value) if value else 0.0


# ---------------------------------------------------------------------------
# Redis-backed MeshGraph adapter
# ---------------------------------------------------------------------------

_REEMBED_QUEUE_KEY = "mesh:reembed_queue"


class RedisGraphAdapter:
    """MeshGraph adapter that reads edges from the Redis sorted sets written by MeshEdgeSync.

    Issue #2547: Wires propagate_staleness() to the live mesh edge data so that
    staleness BFS uses the same graph that PPR and retrieval see.

    The Redis key layout mirrors MeshEdgeSync: ``mesh:edges:{node_id}`` is a
    sorted set where members are neighbour node-IDs and scores are edge weights.
    """

    def __init__(self, redis) -> None:
        self._redis = redis

    async def get_neighbors(self, node_id: str) -> list[tuple[str, float]]:
        """Return [(neighbor_id, edge_weight)] from the Redis sorted set.

        Uses ``zrangebyscore`` with the full weight range and returns results
        in the same format expected by ``propagate_staleness()``.
        """
        key = f"mesh:edges:{node_id}"
        raw: list[tuple[bytes, float]] = await self._redis.zrangebyscore(key, min=0.0, max="+inf", withscores=True)
        return [(member.decode() if isinstance(member, bytes) else member, score) for member, score in raw]


async def enqueue_for_reembedding(redis, node_ids: list[str]) -> int:
    """Push node IDs flagged for re-embedding onto the Redis work queue.

    Issue #2547: Background scheduler picks up ``mesh:reembed_queue`` to
    trigger fresh embeddings for stale nodes.

    Args:
        redis: Async Redis client.
        node_ids: Node IDs returned by ``StalenessResult.flagged_for_reembedding()``.

    Returns:
        Number of IDs enqueued.
    """
    if not node_ids:
        return 0
    await redis.rpush(_REEMBED_QUEUE_KEY, *node_ids)
    logger.info("Enqueued %d nodes for re-embedding (key=%s)", len(node_ids), _REEMBED_QUEUE_KEY)
    return len(node_ids)
