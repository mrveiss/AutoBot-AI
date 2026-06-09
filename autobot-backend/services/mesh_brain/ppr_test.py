# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for PersonalizedPageRank — mesh graph expansion (#1994, #2057)."""

from unittest.mock import AsyncMock

import pytest

from services.mesh_brain.ppr import PersonalizedPageRank

# =============================================================================
# Helpers
# =============================================================================


def _make_db_mock(neighbor_map: dict[str, list[dict]]) -> AsyncMock:
    """Return a MeshDB mock whose get_neighbors returns from neighbor_map.

    neighbor_map keys are node_id strings; values are lists of
    {"to_node": str, "weight": float} dicts.  Unknown nodes return [].
    """
    db = AsyncMock()
    db.get_neighbors = AsyncMock(side_effect=lambda node_id, min_weight=0.0: neighbor_map.get(node_id, []))
    return db


def _ppr(neighbor_map: dict) -> PersonalizedPageRank:
    """Construct a PersonalizedPageRank with the given neighbor map."""
    return PersonalizedPageRank(db=_make_db_mock(neighbor_map))


# =============================================================================
# Tests
# =============================================================================


class TestPersonalizedPageRank:
    """Tests for PersonalizedPageRank.rank() and its helpers."""

    @pytest.mark.asyncio
    async def test_single_seed_node_gets_highest_score(self) -> None:
        """The seed node must receive the highest PPR score in any connected graph."""
        neighbor_map = {
            "A": [{"to_node": "B", "weight": 0.8}],
            "B": [],
        }
        ppr = _ppr(neighbor_map)

        results = await ppr.rank(seed_node_ids=["A"], alpha=0.15, top_k=10)

        assert results, "Expected non-empty results"
        top_node, top_score = results[0]
        assert top_node == "A", f"Expected seed 'A' as top node, got {top_node!r}"
        assert top_score > 0.0

    @pytest.mark.asyncio
    async def test_connected_neighbor_gets_score(self) -> None:
        """A directly connected neighbor with high weight receives a meaningful score."""
        neighbor_map = {
            "seed": [{"to_node": "neighbor", "weight": 0.9}],
            "neighbor": [],
        }
        ppr = _ppr(neighbor_map)

        results = await ppr.rank(seed_node_ids=["seed"], alpha=0.15, top_k=10)

        node_ids = [nid for nid, _ in results]
        assert "neighbor" in node_ids, "Neighbor should appear in PPR results"

        scores = dict(results)
        assert scores["neighbor"] > 0.0, "Neighbor score should be positive"

    @pytest.mark.asyncio
    async def test_disconnected_node_gets_zero(self) -> None:
        """A node not reachable from seeds must not appear in results."""
        neighbor_map = {
            "seed": [],
            "isolated": [{"to_node": "seed", "weight": 0.9}],
        }
        ppr = _ppr(neighbor_map)

        # BFS from "seed" will not visit "isolated" (no outgoing edge from seed to it)
        results = await ppr.rank(seed_node_ids=["seed"], alpha=0.15, top_k=20)

        node_ids = {nid for nid, _ in results}
        assert "isolated" not in node_ids, "'isolated' is unreachable and must not appear"

    @pytest.mark.asyncio
    async def test_alpha_controls_teleport(self) -> None:
        """High alpha concentrates scores on seeds; low alpha spreads to neighbors."""
        neighbor_map = {
            "seed": [{"to_node": "far", "weight": 0.9}],
            "far": [],
        }

        high_alpha_ppr = _ppr(neighbor_map)
        low_alpha_ppr = _ppr(neighbor_map)

        high_results = dict(await high_alpha_ppr.rank(["seed"], alpha=0.9, top_k=10))
        low_results = dict(await low_alpha_ppr.rank(["seed"], alpha=0.05, top_k=10))

        # With high alpha, seed dominates far more strongly
        seed_dominance_high = high_results.get("seed", 0.0) - high_results.get("far", 0.0)
        seed_dominance_low = low_results.get("seed", 0.0) - low_results.get("far", 0.0)
        assert (
            seed_dominance_high > seed_dominance_low
        ), "High alpha should produce greater seed dominance than low alpha"

    @pytest.mark.asyncio
    async def test_edge_weight_influences_propagation(self) -> None:
        """A higher-weight edge propagates more PPR score than a lower-weight edge."""
        high_weight_map = {
            "seed": [{"to_node": "target", "weight": 0.95}],
            "target": [],
        }
        low_weight_map = {
            "seed": [{"to_node": "target", "weight": 0.1}],
            "target": [],
        }

        high_results = dict(await _ppr(high_weight_map).rank(["seed"], alpha=0.15, top_k=10))
        low_results = dict(await _ppr(low_weight_map).rank(["seed"], alpha=0.15, top_k=10))

        assert high_results.get("target", 0.0) > low_results.get(
            "target", 0.0
        ), "Higher edge weight must propagate more score to the target"

    def test_convergence_check_identical_dicts(self) -> None:
        """_converged returns True when old and new score vectors are identical."""
        scores = {"A": 0.5, "B": 0.3, "C": 0.2}
        ppr = PersonalizedPageRank(db=AsyncMock())
        assert ppr._converged(scores, scores.copy()) is True

    def test_convergence_check_different_dicts(self) -> None:
        """_converged returns False when score vectors differ beyond tolerance."""
        old = {"A": 0.5, "B": 0.5}
        new = {"A": 0.9, "B": 0.1}
        ppr = PersonalizedPageRank(db=AsyncMock())
        assert ppr._converged(old, new) is False

    @pytest.mark.asyncio
    async def test_empty_subgraph_returns_seed_scores(self) -> None:
        """When no neighbors exist, seeds receive uniform 1/n scores."""
        neighbor_map: dict = {}  # get_neighbors returns [] for all nodes
        ppr = _ppr(neighbor_map)

        results = await ppr.rank(seed_node_ids=["X", "Y"], alpha=0.15, top_k=10)

        assert len(results) == 2
        scores = dict(results)
        # Both seeds should get equal scores (no edges to break symmetry)
        assert abs(scores["X"] - scores["Y"]) < 1e-9, "Seeds should get equal scores"
        assert scores["X"] > 0, "Seed scores should be positive"

    @pytest.mark.asyncio
    async def test_top_k_limits_results(self) -> None:
        """rank() returns at most top_k results regardless of subgraph size."""
        # Build a star graph: seed → n0..n9
        neighbor_map: dict = {
            "seed": [{"to_node": f"n{i}", "weight": 0.8} for i in range(10)],
        }
        for i in range(10):
            neighbor_map[f"n{i}"] = []

        ppr = _ppr(neighbor_map)
        results = await ppr.rank(seed_node_ids=["seed"], alpha=0.15, top_k=5)

        assert len(results) == 5, f"Expected 5 results, got {len(results)}"

    @pytest.mark.asyncio
    async def test_results_sorted_descending(self) -> None:
        """rank() results are sorted by score in descending order."""
        neighbor_map = {
            "seed": [{"to_node": "B", "weight": 0.8}],
            "B": [],
        }
        ppr = _ppr(neighbor_map)

        results = await ppr.rank(seed_node_ids=["seed"], alpha=0.15, top_k=10)

        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True), "Results must be sorted descending"
