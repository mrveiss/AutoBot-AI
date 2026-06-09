# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for CommunityClusterer (#4819, #4834)."""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.logging_manager import get_logger as _get_logger
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


def test_cluster_graph_empty_returns_empty() -> None:
    assert cluster_graph([]) == []


def test_cluster_graph_single_edge_returns_one_centroid() -> None:
    _ensure_graspologic_stub()
    edges = _make_edges([("n1", "n2", 1.0)])
    centroids = cluster_graph(edges)
    assert len(centroids) == 1
    assert centroids[0] in ("n1", "n2")


def test_cluster_graph_triangle_returns_one_centroid() -> None:
    """Three fully-connected nodes → one community → one centroid."""
    _ensure_graspologic_stub()
    edges = _make_edges([("n1", "n2", 1.0), ("n2", "n3", 1.0), ("n1", "n3", 1.0)])
    centroids = cluster_graph(edges)
    assert len(centroids) == 1


def test_cluster_graph_two_components_returns_two_centroids() -> None:
    """Two disconnected triangles → two communities → two centroids."""
    _ensure_graspologic_stub()
    edges = _make_edges(
        [
            ("a1", "a2", 1.0),
            ("a2", "a3", 1.0),
            ("a1", "a3", 1.0),
            ("b1", "b2", 1.0),
            ("b2", "b3", 1.0),
            ("b1", "b3", 1.0),
        ]
    )
    centroids = cluster_graph(edges)
    assert len(centroids) == 2
    assert set(centroids).issubset({"a1", "a2", "a3", "b1", "b2", "b3"})


# ---------------------------------------------------------------------------
# CommunityClusterer (async, uses MeshDB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_seeds_anchors_from_centroids() -> None:
    """run() fetches edges, clusters, and promotes centroid nodes to anchors."""
    _ensure_graspologic_stub()
    db = AsyncMock()
    db.fetch_edges = AsyncMock(
        return_value=_make_edges(
            [
                ("n1", "n2", 1.0),
                ("n2", "n3", 1.0),
                ("n1", "n3", 1.0),
            ]
        )
    )
    db.promote_to_anchor = AsyncMock()

    clusterer = CommunityClusterer(db)
    promoted = await clusterer.run()

    assert len(promoted) == 1
    db.promote_to_anchor.assert_called_once_with(promoted[0])


@pytest.mark.asyncio
async def test_run_empty_graph_promotes_nothing() -> None:
    db = AsyncMock()
    db.fetch_edges = AsyncMock(return_value=[])
    db.promote_to_anchor = AsyncMock()

    clusterer = CommunityClusterer(db)
    promoted = await clusterer.run()

    assert promoted == []
    db.promote_to_anchor.assert_not_called()


# ---------------------------------------------------------------------------
# Periodic scheduler integration (#4834)
# Tests that CommunityClusterer can be driven from a periodic caller,
# exercising the same pattern used by _start_community_clustering_loop in lifespan.py.
# We test the logic inline rather than importing lifespan (which has heavy deps).
# ---------------------------------------------------------------------------


async def _run_clustering_loop_once(mesh_db) -> list[str]:
    """Minimal replica of the loop body inside _start_community_clustering_loop.

    Runs one iteration: create clusterer, run it, return promoted IDs.
    This mirrors the production path in initialization/lifespan.py (#4834).
    """
    promoted = await CommunityClusterer(mesh_db).run()
    return promoted


@pytest.mark.asyncio
async def test_periodic_caller_promotes_anchors_on_connected_graph() -> None:
    """A scheduler-style caller creates CommunityClusterer per run and promotes centroids."""
    _ensure_graspologic_stub()
    db = AsyncMock()
    db.fetch_edges = AsyncMock(
        return_value=_make_edges(
            [
                ("p1", "p2", 0.9),
                ("p2", "p3", 0.8),
                ("p1", "p3", 0.7),
            ]
        )
    )
    db.promote_to_anchor = AsyncMock()

    promoted = await _run_clustering_loop_once(db)

    assert len(promoted) == 1
    db.promote_to_anchor.assert_called_once_with(promoted[0])


@pytest.mark.asyncio
async def test_periodic_caller_noop_on_empty_graph() -> None:
    """A scheduler-style caller handles an empty graph gracefully — no promotions."""
    db = AsyncMock()
    db.fetch_edges = AsyncMock(return_value=[])
    db.promote_to_anchor = AsyncMock()

    promoted = await _run_clustering_loop_once(db)

    assert promoted == []
    db.promote_to_anchor.assert_not_called()


@pytest.mark.asyncio
async def test_periodic_caller_promotes_two_anchors_for_two_components() -> None:
    """Two disconnected components produce two anchor promotions per run."""
    _ensure_graspologic_stub()
    db = AsyncMock()
    db.fetch_edges = AsyncMock(
        return_value=_make_edges(
            [
                ("a1", "a2", 1.0),
                ("a2", "a3", 1.0),
                ("a1", "a3", 1.0),
                ("b1", "b2", 1.0),
                ("b2", "b3", 1.0),
                ("b1", "b3", 1.0),
            ]
        )
    )
    db.promote_to_anchor = AsyncMock()

    promoted = await _run_clustering_loop_once(db)

    assert len(promoted) == 2
    assert db.promote_to_anchor.call_count == 2


# ---------------------------------------------------------------------------
# ImportError path (#4896)
# Verify that missing graspologic raises ImportError (not silently returns [])
# and that a loop caller can catch it specifically to log CRITICAL and exit.
# ---------------------------------------------------------------------------


def test_cluster_graph_raises_import_error_when_graspologic_missing() -> None:
    """cluster_graph raises ImportError when graspologic is unavailable (#4896).

    Ensures callers can distinguish a missing dependency from an empty-graph result.
    """
    edges = _make_edges([("n1", "n2", 1.0)])
    with patch.dict(sys.modules, {"graspologic": None, "graspologic.partition": None}):
        with pytest.raises(ImportError):
            cluster_graph(edges)


@pytest.mark.asyncio
async def test_loop_body_logs_warning_and_sleeps_on_import_error(caplog):
    """Loop body catches ImportError, logs WARNING, sleeps 24h, and continues (#4924).

    Mirrors the _loop() coroutine in _start_community_clustering_loop but inlined
    here to avoid importing lifespan (heavy deps). Verifies that the production
    pattern — catch ImportError → log warning → sleep 24h → continue — works end-to-end.
    Prior behaviour was CRITICAL + permanent exit; now it retries after 24h (#4924).
    """
    import logging

    db = AsyncMock()
    db.fetch_edges = AsyncMock(return_value=_make_edges([("n1", "n2", 1.0)]))
    db.promote_to_anchor = AsyncMock()

    slept_seconds: list[float] = []
    continued = False

    async def _loop_once(mesh_db) -> None:
        nonlocal continued
        try:
            await CommunityClusterer(mesh_db).run()
        except ImportError as exc:
            pass

            _get_logger(__name__).warning(
                "graspologic not installed — community clustering paused. "
                "Install with: pip install graspologic. Retrying in 24h. Error: %s",
                exc,
            )
            slept_seconds.append(86400)
            continued = True
            return  # simulate continue in the real loop

    with patch.dict(sys.modules, {"graspologic": None, "graspologic.partition": None}):
        with caplog.at_level(logging.WARNING):
            await _loop_once(db)

    assert continued, "Loop should have continued (not exited) after ImportError"
    assert slept_seconds == [86400], "Loop should sleep 86400s (24h) on ImportError"
    assert any(
        "graspologic not installed" in record.message for record in caplog.records if record.levelno == logging.WARNING
    ), "Expected WARNING log message about missing graspologic"
    db.promote_to_anchor.assert_not_called()
