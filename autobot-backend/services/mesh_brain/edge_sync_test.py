# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for MeshEdgeSync — PostgreSQL-to-Redis edge sync (#2029)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from services.mesh_brain.edge_sync import MeshEdgeSync

# =============================================================================
# Helpers
# =============================================================================


def _make_redis_mock():
    """Return a Redis mock with a pipeline that tracks zadd/execute calls."""
    pipe = AsyncMock()
    pipe.zadd = MagicMock()
    pipe.execute = AsyncMock(return_value=[])

    redis = AsyncMock()
    redis.pipeline = MagicMock(return_value=pipe)
    return redis, pipe


def _make_db_mock(edges: list[dict]):
    """Return a MeshDB mock that yields the given edge list."""
    db = AsyncMock()
    db.fetch_edges = AsyncMock(return_value=edges)
    return db


# =============================================================================
# Tests
# =============================================================================


class TestMeshEdgeSync:
    """Tests for MeshEdgeSync.sync() and get_neighbors()."""

    @pytest.mark.asyncio
    async def test_syncs_only_above_threshold(self):
        """Only edges at or above min_weight are returned by the DB query."""
        edges = [{"from_node": "A", "to_node": "B", "weight": 0.8}]
        db = _make_db_mock(edges)
        redis, pipe = _make_redis_mock()

        syncer = MeshEdgeSync(db=db, redis=redis, min_weight=0.5)
        count = await syncer.sync()

        assert count == 1
        db.fetch_edges.assert_awaited_once_with(min_weight=0.5)

    @pytest.mark.asyncio
    async def test_empty_edges_returns_zero(self):
        """sync() returns 0 and skips pipeline when DB has no matching edges."""
        db = _make_db_mock([])
        redis, pipe = _make_redis_mock()

        syncer = MeshEdgeSync(db=db, redis=redis, min_weight=0.5)
        count = await syncer.sync()

        assert count == 0
        pipe.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bidirectional_sync(self):
        """Each edge writes forward (A→B) AND reverse (B→A) sorted-set entries."""
        edges = [{"from_node": "X", "to_node": "Y", "weight": 0.9}]
        db = _make_db_mock(edges)
        redis, pipe = _make_redis_mock()

        syncer = MeshEdgeSync(db=db, redis=redis, min_weight=0.5)
        await syncer.sync()

        zadd_calls = pipe.zadd.call_args_list
        keys_written = {call.args[0] for call in zadd_calls}
        assert "mesh:edges:X" in keys_written
        assert "mesh:edges:Y" in keys_written

    @pytest.mark.asyncio
    async def test_get_neighbors_queries_redis(self):
        """get_neighbors() calls zrangebyscore with the correct key and args."""
        db = _make_db_mock([])
        redis, _ = _make_redis_mock()
        redis.zrangebyscore = AsyncMock(return_value=[("B", 0.9)])

        syncer = MeshEdgeSync(db=db, redis=redis, min_weight=0.5)
        result = await syncer.get_neighbors("A", min_weight=0.5, limit=10)

        redis.zrangebyscore.assert_awaited_once_with(
            "mesh:edges:A",
            min=0.5,
            max="+inf",
            start=0,
            num=10,
            withscores=True,
        )
        assert result == [("B", 0.9)]

    @pytest.mark.asyncio
    async def test_pipeline_used_for_batch(self):
        """sync() uses a single pipeline for all zadd calls, then executes once."""
        edges = [
            {"from_node": "A", "to_node": "B", "weight": 0.7},
            {"from_node": "C", "to_node": "D", "weight": 0.6},
        ]
        db = _make_db_mock(edges)
        redis, pipe = _make_redis_mock()

        syncer = MeshEdgeSync(db=db, redis=redis, min_weight=0.5)
        count = await syncer.sync()

        assert count == 2
        redis.pipeline.assert_called_once()
        pipe.execute.assert_awaited_once()
        # 2 edges × 2 directions = 4 zadd calls
        assert pipe.zadd.call_count == 4
