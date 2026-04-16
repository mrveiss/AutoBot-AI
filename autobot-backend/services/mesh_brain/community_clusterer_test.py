# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for CommunityClusterer (#4819)."""

import sys
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

from services.mesh_brain.community_clusterer import CommunityClusterer, cluster_graph


def _make_edges(pairs: list[tuple[str, str, float]]) -> list[dict]:
    return [
        {
            "from_node": a,
            "to_node": b,
            "weight": w,
            "id": f"{a}-{b}",
            "edge_type": "co_access",
            "origin": "extracted",
        }
        for a, b, w in pairs
    ]


def _ensure_graspologic_stub() -> None:
    """Install a minimal graspologic stub if not present, so tests run without the package."""
    if "graspologic" not in sys.modules:
        def _leiden(G, trials=3):
            # Assign each connected component its own community ID
            import networkx as nx
            partition = {}
            for comm_id, component in enumerate(nx.connected_components(G)):
                for node in component:
                    partition[node] = comm_id
            return partition

        graspologic_mod = ModuleType("graspologic")
        partition_mod = ModuleType("graspologic.partition")
        partition_mod.leiden = _leiden
        graspologic_mod.partition = partition_mod
        sys.modules["graspologic"] = graspologic_mod
        sys.modules["graspologic.partition"] = partition_mod


# ---------------------------------------------------------------------------
# cluster_graph (pure function)
# ---------------------------------------------------------------------------


def test_cluster_graph_empty_returns_empty():
    assert cluster_graph([]) == []


def test_cluster_graph_single_edge_returns_one_centroid():
    _ensure_graspologic_stub()
    edges = _make_edges([("n1", "n2", 1.0)])
    centroids = cluster_graph(edges)
    assert len(centroids) == 1
    assert centroids[0] in ("n1", "n2")


def test_cluster_graph_triangle_returns_one_centroid():
    """Three fully-connected nodes → one community → one centroid."""
    _ensure_graspologic_stub()
    edges = _make_edges([("n1", "n2", 1.0), ("n2", "n3", 1.0), ("n1", "n3", 1.0)])
    centroids = cluster_graph(edges)
    assert len(centroids) == 1


def test_cluster_graph_two_components_returns_two_centroids():
    """Two disconnected triangles → two communities → two centroids."""
    _ensure_graspologic_stub()
    edges = _make_edges([
        ("a1", "a2", 1.0), ("a2", "a3", 1.0), ("a1", "a3", 1.0),
        ("b1", "b2", 1.0), ("b2", "b3", 1.0), ("b1", "b3", 1.0),
    ])
    centroids = cluster_graph(edges)
    assert len(centroids) == 2
    assert set(centroids).issubset({"a1", "a2", "a3", "b1", "b2", "b3"})


# ---------------------------------------------------------------------------
# CommunityClusterer (async, uses MeshDB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_seeds_anchors_from_centroids():
    """run() fetches edges, clusters, and promotes centroid nodes to anchors."""
    _ensure_graspologic_stub()
    db = AsyncMock()
    db.fetch_edges = AsyncMock(
        return_value=_make_edges([
            ("n1", "n2", 1.0),
            ("n2", "n3", 1.0),
            ("n1", "n3", 1.0),
        ])
    )
    db.promote_to_anchor = AsyncMock()

    clusterer = CommunityClusterer(db)
    promoted = await clusterer.run()

    assert len(promoted) == 1
    db.promote_to_anchor.assert_called_once_with(promoted[0])


@pytest.mark.asyncio
async def test_run_empty_graph_promotes_nothing():
    db = AsyncMock()
    db.fetch_edges = AsyncMock(return_value=[])
    db.promote_to_anchor = AsyncMock()

    clusterer = CommunityClusterer(db)
    promoted = await clusterer.run()

    assert promoted == []
    db.promote_to_anchor.assert_not_called()
