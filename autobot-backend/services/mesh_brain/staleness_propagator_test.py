# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for BFS staleness propagation (#2111)."""

from unittest.mock import AsyncMock

import pytest

from services.mesh_brain.staleness_propagator import (
    StalenessResult,
    get_staleness_score,
    propagate_staleness,
    store_staleness_scores,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_graph(adjacency: dict[str, list[tuple[str, float]]]) -> AsyncMock:
    """Return a MeshGraph mock from an adjacency dict.

    adjacency: {node_id: [(neighbor_id, edge_weight), ...]}
    """
    graph = AsyncMock()

    async def _get_neighbors(node_id: str) -> list[tuple[str, float]]:
        return adjacency.get(node_id, [])

    graph.get_neighbors = _get_neighbors
    return graph


def _make_redis_mock() -> AsyncMock:
    """Return a Redis mock with pipeline support."""
    redis = AsyncMock()
    pipe = AsyncMock()
    # pipeline() is synchronous — returns pipe directly, not a coroutine.
    redis.pipeline = lambda: pipe
    pipe.execute = AsyncMock(return_value=[])
    return redis


# =============================================================================
# Tests — propagate_staleness
# =============================================================================


class TestPropagateStaleness:
    """Tests for the BFS staleness propagation algorithm."""

    @pytest.mark.asyncio
    async def test_single_hop_decay(self) -> None:
        """Direct neighbor gets decay^1 * edge_weight."""
        graph = _make_graph({"A": [("B", 0.8)]})
        result = await propagate_staleness(graph, "A", max_depth=3, decay=0.7)

        assert result.scores["A"] == 1.0
        assert result.scores["B"] == pytest.approx(0.7 * 0.8)

    @pytest.mark.asyncio
    async def test_multi_hop_decay(self) -> None:
        """Depth-2 neighbor gets decay^2 * edge_weight."""
        graph = _make_graph({"A": [("B", 1.0)], "B": [("C", 1.0)]})
        result = await propagate_staleness(graph, "A", max_depth=3, decay=0.7)

        assert result.scores["B"] == pytest.approx(0.7)
        assert result.scores["C"] == pytest.approx(0.49)

    @pytest.mark.asyncio
    async def test_max_depth_respected(self) -> None:
        """Nodes beyond max_depth are not visited."""
        graph = _make_graph({"A": [("B", 1.0)], "B": [("C", 1.0)], "C": [("D", 1.0)]})
        result = await propagate_staleness(graph, "A", max_depth=2, decay=0.7)

        assert "B" in result.scores
        assert "C" in result.scores
        assert "D" not in result.scores

    @pytest.mark.asyncio
    async def test_best_score_wins(self) -> None:
        """When multiple paths reach the same node, the highest score is kept."""
        # A->B (weight 1.0) and A->C->B (weights 1.0, 1.0)
        # Direct: 0.7 * 1.0 = 0.7
        # Via C:  0.49 * 1.0 = 0.49
        # B should keep the higher score: 0.7
        graph = _make_graph(
            {
                "A": [("B", 1.0), ("C", 1.0)],
                "C": [("B", 1.0)],
            }
        )
        result = await propagate_staleness(graph, "A", max_depth=3, decay=0.7)

        assert result.scores["B"] == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_edge_weight_scales_score(self) -> None:
        """Edge weight multiplies the decay factor."""
        graph = _make_graph({"A": [("B", 0.5)]})
        result = await propagate_staleness(graph, "A", max_depth=3, decay=0.7)

        assert result.scores["B"] == pytest.approx(0.7 * 0.5)

    @pytest.mark.asyncio
    async def test_isolated_node(self) -> None:
        """A node with no neighbors returns only the source."""
        graph = _make_graph({})
        result = await propagate_staleness(graph, "A", max_depth=3, decay=0.7)

        assert result.scores == {"A": 1.0}

    @pytest.mark.asyncio
    async def test_source_always_has_score_one(self) -> None:
        """The changed document always has staleness 1.0."""
        graph = _make_graph({"X": [("Y", 1.0)]})
        result = await propagate_staleness(graph, "X", max_depth=1, decay=0.5)

        assert result.scores["X"] == 1.0


# =============================================================================
# Tests — StalenessResult
# =============================================================================


class TestStalenessResult:
    """Tests for StalenessResult helper methods."""

    def test_above_threshold_filters(self) -> None:
        """Only nodes at or above threshold are returned."""
        result = StalenessResult(
            scores={"A": 1.0, "B": 0.5, "C": 0.2, "D": 0.3},
            source_node="A",
            max_depth=3,
            decay=0.7,
        )
        above = result.above_threshold(0.3)

        assert set(above.keys()) == {"A", "B", "D"}
        assert "C" not in above

    def test_flagged_for_reembedding_excludes_source(self) -> None:
        """Source node is excluded from reembedding candidates."""
        result = StalenessResult(
            scores={"A": 1.0, "B": 0.7, "C": 0.1},
            source_node="A",
            max_depth=3,
            decay=0.7,
        )
        flagged = result.flagged_for_reembedding(0.3)

        assert "B" in flagged
        assert "A" not in flagged
        assert "C" not in flagged


# =============================================================================
# Tests — Redis store/retrieve
# =============================================================================


class TestStalenessRedis:
    """Tests for Redis storage and retrieval of staleness scores."""

    @pytest.mark.asyncio
    async def test_store_staleness_scores(self) -> None:
        """store_staleness_scores writes all scores via pipeline."""
        from unittest.mock import MagicMock

        redis = AsyncMock()
        pipe = MagicMock()
        redis.pipeline = lambda: pipe
        pipe.execute = AsyncMock(return_value=[])

        count = await store_staleness_scores(redis, {"A": 1.0, "B": 0.5}, ttl=600)

        assert count == 2
        pipe.set.assert_any_call("mesh:staleness:A", "1.0", ex=600)
        pipe.set.assert_any_call("mesh:staleness:B", "0.5", ex=600)
        pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_staleness_score_returns_value(self) -> None:
        """get_staleness_score returns the stored float value."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value="0.7")

        score = await get_staleness_score(redis, "doc-1")

        assert score == pytest.approx(0.7)
        redis.get.assert_awaited_once_with("mesh:staleness:doc-1")

    @pytest.mark.asyncio
    async def test_get_staleness_score_returns_zero_for_missing(self) -> None:
        """get_staleness_score returns 0.0 when no score exists."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        score = await get_staleness_score(redis, "fresh-doc")

        assert score == 0.0
