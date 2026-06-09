# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for staleness propagation wiring (#2547).

Covers:
- RedisGraphAdapter.get_neighbors() reading from Redis sorted sets
- enqueue_for_reembedding() pushing to mesh:reembed_queue
- Full propagate → store → enqueue pipeline
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.mesh_brain.staleness_propagator import (
    RedisGraphAdapter,
    enqueue_for_reembedding,
    propagate_staleness,
    store_staleness_scores,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_async_redis(zrangebyscore_result=None, rpush_result=None):
    """Build an async Redis mock wired for staleness tests."""
    redis = AsyncMock()
    redis.zrangebyscore = AsyncMock(return_value=zrangebyscore_result or [])
    redis.rpush = AsyncMock(return_value=rpush_result or 0)
    pipe = MagicMock()
    redis.pipeline = lambda: pipe
    pipe.set = MagicMock()
    pipe.execute = AsyncMock(return_value=[])
    return redis


# =============================================================================
# RedisGraphAdapter
# =============================================================================


class TestRedisGraphAdapter:
    """Unit tests for the Redis-backed MeshGraph adapter."""

    @pytest.mark.asyncio
    async def test_get_neighbors_decodes_bytes(self) -> None:
        """Members returned as bytes are decoded to strings."""
        redis = _make_async_redis(zrangebyscore_result=[(b"node-B", 0.9), (b"node-C", 0.5)])
        adapter = RedisGraphAdapter(redis)

        neighbors = await adapter.get_neighbors("node-A")

        assert neighbors == [("node-B", 0.9), ("node-C", 0.5)]
        redis.zrangebyscore.assert_awaited_once_with("mesh:edges:node-A", min=0.0, max="+inf", withscores=True)

    @pytest.mark.asyncio
    async def test_get_neighbors_handles_string_members(self) -> None:
        """Members already returned as strings are passed through unchanged."""
        redis = _make_async_redis(zrangebyscore_result=[("node-B", 0.7)])
        adapter = RedisGraphAdapter(redis)

        neighbors = await adapter.get_neighbors("node-A")

        assert neighbors == [("node-B", 0.7)]

    @pytest.mark.asyncio
    async def test_get_neighbors_empty_when_no_edges(self) -> None:
        """An isolated node returns an empty neighbor list."""
        redis = _make_async_redis(zrangebyscore_result=[])
        adapter = RedisGraphAdapter(redis)

        neighbors = await adapter.get_neighbors("isolated")

        assert neighbors == []

    @pytest.mark.asyncio
    async def test_key_format_matches_edge_sync(self) -> None:
        """Key used is mesh:edges:{node_id}, matching MeshEdgeSync layout."""
        redis = _make_async_redis()
        adapter = RedisGraphAdapter(redis)

        await adapter.get_neighbors("doc/readme.md")

        call_args = redis.zrangebyscore.call_args
        assert call_args[0][0] == "mesh:edges:doc/readme.md"


# =============================================================================
# enqueue_for_reembedding
# =============================================================================


class TestEnqueueForReembedding:
    """Tests for the re-embedding work queue."""

    @pytest.mark.asyncio
    async def test_enqueues_all_node_ids(self) -> None:
        """All provided node IDs are pushed onto mesh:reembed_queue."""
        redis = _make_async_redis()
        node_ids = ["doc/a.md", "doc/b.md", "doc/c.md"]

        count = await enqueue_for_reembedding(redis, node_ids)

        assert count == 3
        redis.rpush.assert_awaited_once_with("mesh:reembed_queue", *node_ids)

    @pytest.mark.asyncio
    async def test_empty_list_is_noop(self) -> None:
        """An empty node list makes no Redis calls and returns 0."""
        redis = _make_async_redis()

        count = await enqueue_for_reembedding(redis, [])

        assert count == 0
        redis.rpush.assert_not_awaited()


# =============================================================================
# Full pipeline: propagate → store → enqueue
# =============================================================================


class TestFullStalenessIntegrationPipeline:
    """End-to-end test of the propagate → store → enqueue pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_propagates_stores_and_enqueues(self) -> None:
        """BFS runs over the Redis graph, scores are stored, and stale nodes queued."""
        # Graph: source -> neighbor-B (weight 1.0)
        # decay=0.7 → neighbor-B gets score 0.7 (above default 0.3 threshold)
        redis = AsyncMock()
        redis.zrangebyscore = AsyncMock(side_effect=lambda key, **_: ([("neighbor-B", 1.0)] if "source" in key else []))
        redis.rpush = AsyncMock(return_value=1)
        pipe = MagicMock()
        redis.pipeline = lambda: pipe
        pipe.set = MagicMock()
        pipe.execute = AsyncMock(return_value=[])

        graph = RedisGraphAdapter(redis)
        result = await propagate_staleness(graph, "source", max_depth=3, decay=0.7)

        assert "source" in result.scores
        assert "neighbor-B" in result.scores
        assert result.scores["neighbor-B"] == pytest.approx(0.7)

        stored = await store_staleness_scores(redis, result.scores)
        assert stored == len(result.scores)

        flagged = result.flagged_for_reembedding()
        assert "neighbor-B" in flagged
        assert "source" not in flagged

        enqueued = await enqueue_for_reembedding(redis, flagged)
        assert enqueued == len(flagged)
        redis.rpush.assert_awaited_once_with("mesh:reembed_queue", *flagged)
