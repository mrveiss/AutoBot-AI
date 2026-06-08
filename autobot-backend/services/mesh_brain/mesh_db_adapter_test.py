# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for MeshDBAdapter — concrete MeshGraph/MeshDB adapter (#2548)."""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.mesh_brain.community_clusterer import CommunityClusterer
from services.mesh_brain.mesh_db_adapter import MeshDBAdapter, create_mesh_db_adapter

# ---------------------------------------------------------------------------
# Shared test UUIDs
# ---------------------------------------------------------------------------

_NODE_A = "aaaaaaaa-0000-0000-0000-000000000001"
_NODE_B = "bbbbbbbb-0000-0000-0000-000000000002"
_EDGE_ID = "cccccccc-0000-0000-0000-000000000003"


# ---------------------------------------------------------------------------
# Helper: build a MeshDBAdapter with a fully-mocked inner MeshDB
# ---------------------------------------------------------------------------


def _make_adapter(**method_returns) -> tuple["MeshDBAdapter", MagicMock]:
    """Return ``(adapter, mock_db)`` with each key in ``method_returns`` patched.

    The ``mock_db`` is a ``MagicMock`` whose async methods are ``AsyncMock``
    instances pre-configured with the supplied return values.
    """
    mock_db = MagicMock()
    for method, return_value in method_returns.items():
        setattr(mock_db, method, AsyncMock(return_value=return_value))
    return MeshDBAdapter(mock_db), mock_db


# =============================================================================
# MeshDB protocol surface
# =============================================================================


class TestGetEdge:
    """MeshDBAdapter.get_edge delegates to inner MeshDB and forwards the result."""

    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self) -> None:
        edge_row = {
            "id": _EDGE_ID,
            "from_node": _NODE_A,
            "to_node": _NODE_B,
            "weight": 0.9,
            "co_access_count": 2,
        }
        adapter, mock_db = _make_adapter(get_edge=edge_row)

        result = await adapter.get_edge(_NODE_A, _NODE_B)

        assert result == edge_row
        mock_db.get_edge.assert_awaited_once_with(_NODE_A, _NODE_B)

    @pytest.mark.asyncio
    async def test_returns_none_when_absent(self) -> None:
        adapter, mock_db = _make_adapter(get_edge=None)

        result = await adapter.get_edge(_NODE_A, _NODE_B)

        assert result is None
        mock_db.get_edge.assert_awaited_once_with(_NODE_A, _NODE_B)


class TestUpdateEdge:
    """MeshDBAdapter.update_edge forwards all keyword arguments to MeshDB."""

    @pytest.mark.asyncio
    async def test_forwards_kwargs(self) -> None:
        adapter, mock_db = _make_adapter(update_edge=None)

        await adapter.update_edge(_EDGE_ID, weight=0.75, co_access_count=5)

        mock_db.update_edge.assert_awaited_once_with(_EDGE_ID, weight=0.75, co_access_count=5)


class TestCreateEdge:
    """MeshDBAdapter.create_edge forwards positional and keyword arguments to MeshDB."""

    @pytest.mark.asyncio
    async def test_forwards_all_args(self) -> None:
        adapter, mock_db = _make_adapter(create_edge=_EDGE_ID)

        await adapter.create_edge(
            _NODE_A,
            _NODE_B,
            edge_type="CO_RETRIEVED",
            weight=0.3,
            origin="learner",
        )

        mock_db.create_edge.assert_awaited_once_with(
            _NODE_A,
            _NODE_B,
            edge_type="CO_RETRIEVED",
            weight=0.3,
            origin="learner",
        )


class TestGetCoAccessCount:
    """MeshDBAdapter.get_co_access_count delegates to MeshDB and returns int."""

    @pytest.mark.asyncio
    async def test_returns_count(self) -> None:
        adapter, mock_db = _make_adapter(get_co_access_count=7)

        result = await adapter.get_co_access_count(_NODE_A, _NODE_B)

        assert result == 7
        mock_db.get_co_access_count.assert_awaited_once_with(_NODE_A, _NODE_B)

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_edge(self) -> None:
        adapter, mock_db = _make_adapter(get_co_access_count=0)

        result = await adapter.get_co_access_count(_NODE_A, _NODE_B)

        assert result == 0


class TestUpdateAccessCount:
    """MeshDBAdapter.update_access_count delegates the node_ids list to MeshDB."""

    @pytest.mark.asyncio
    async def test_forwards_node_ids(self) -> None:
        adapter, mock_db = _make_adapter(update_access_count=None)

        await adapter.update_access_count([_NODE_A, _NODE_B])

        mock_db.update_access_count.assert_awaited_once_with([_NODE_A, _NODE_B])

    @pytest.mark.asyncio
    async def test_empty_list_is_forwarded(self) -> None:
        adapter, mock_db = _make_adapter(update_access_count=None)

        await adapter.update_access_count([])

        mock_db.update_access_count.assert_awaited_once_with([])


# =============================================================================
# CommunityClusterer protocol surface — fetch_edges + promote_to_anchor
# =============================================================================


class TestFetchEdges:
    """MeshDBAdapter.fetch_edges delegates to inner MeshDB and returns list[dict]."""

    @pytest.mark.asyncio
    async def test_forwards_min_weight_and_returns_rows(self) -> None:
        edge_rows = [
            {"id": _EDGE_ID, "from_node": _NODE_A, "to_node": _NODE_B, "weight": 0.8},
        ]
        adapter, mock_db = _make_adapter(fetch_edges=edge_rows)

        result = await adapter.fetch_edges(min_weight=0.7)

        assert result == edge_rows
        mock_db.fetch_edges.assert_awaited_once_with(min_weight=0.7)

    @pytest.mark.asyncio
    async def test_default_min_weight_is_forwarded(self) -> None:
        adapter, mock_db = _make_adapter(fetch_edges=[])

        await adapter.fetch_edges()

        mock_db.fetch_edges.assert_awaited_once_with(min_weight=0.5)


class TestPromoteToAnchor:
    """MeshDBAdapter.promote_to_anchor delegates to inner MeshDB."""

    @pytest.mark.asyncio
    async def test_forwards_node_id(self) -> None:
        adapter, mock_db = _make_adapter(promote_to_anchor=None)

        await adapter.promote_to_anchor(_NODE_A)

        mock_db.promote_to_anchor.assert_awaited_once_with(_NODE_A)


# =============================================================================
# MeshGraph protocol surface
# =============================================================================


class TestGetNeighborsMeshGraph:
    """MeshDBAdapter.get_neighbors satisfies the MeshGraph Protocol.

    MeshDB.get_neighbors returns list[dict] with ``neighbor_id`` and ``weight``
    keys.  The adapter must project these to list[tuple[str, float]] as required
    by ``propagate_staleness()``.
    """

    @pytest.mark.asyncio
    async def test_projects_dicts_to_tuples(self) -> None:
        db_rows = [
            {"neighbor_id": _NODE_B, "weight": 0.85, "edge_type": "semantic"},
            {"neighbor_id": _EDGE_ID, "weight": 0.60, "edge_type": "coref"},
        ]
        adapter, mock_db = _make_adapter(get_neighbors=db_rows)

        result = await adapter.get_neighbors(_NODE_A)

        assert result == [(_NODE_B, 0.85), (_EDGE_ID, 0.60)]
        # Adapter must pass min_weight=0.0 so no edges are discarded
        mock_db.get_neighbors.assert_awaited_once_with(_NODE_A, min_weight=0.0)

    @pytest.mark.asyncio
    async def test_empty_neighbors_returns_empty_list(self) -> None:
        adapter, mock_db = _make_adapter(get_neighbors=[])

        result = await adapter.get_neighbors(_NODE_A)

        assert result == []

    @pytest.mark.asyncio
    async def test_weight_is_cast_to_float(self) -> None:
        """Weights stored as strings in the DB (e.g. from Redis) are coerced to float."""
        db_rows = [{"neighbor_id": _NODE_B, "weight": "0.75", "edge_type": "semantic"}]
        adapter, mock_db = _make_adapter(get_neighbors=db_rows)

        result = await adapter.get_neighbors(_NODE_A)

        assert result == [(_NODE_B, 0.75)]
        assert isinstance(result[0][1], float)

    @pytest.mark.asyncio
    async def test_single_neighbor(self) -> None:
        db_rows = [{"neighbor_id": _NODE_B, "weight": 1.0, "edge_type": "strong"}]
        adapter, mock_db = _make_adapter(get_neighbors=db_rows)

        result = await adapter.get_neighbors(_NODE_A)

        assert len(result) == 1
        neighbor_id, weight = result[0]
        assert neighbor_id == _NODE_B
        assert weight == 1.0


# =============================================================================
# Protocol conformance — structural duck-typing
# =============================================================================


class TestProtocolConformance:
    """Verify MeshDBAdapter exposes the full method surface of both protocols."""

    def test_has_all_mesh_db_protocol_methods(self) -> None:
        """All methods required by EdgeLearner's MeshDB Protocol are present."""
        adapter = MeshDBAdapter(MagicMock())
        for method in (
            "get_edge",
            "update_edge",
            "create_edge",
            "get_co_access_count",
            "update_access_count",
        ):
            assert callable(getattr(adapter, method, None)), f"Missing method: {method}"

    def test_has_all_mesh_graph_protocol_methods(self) -> None:
        """All methods required by StalenessPropagor's MeshGraph Protocol are present."""
        adapter = MeshDBAdapter(MagicMock())
        assert callable(getattr(adapter, "get_neighbors", None))


# =============================================================================
# Factory function
# =============================================================================


class TestCreateMeshDbAdapter:
    """create_mesh_db_adapter returns a ready MeshDBAdapter."""

    def test_returns_mesh_db_adapter_instance(self) -> None:
        mock_engine = MagicMock()
        adapter = create_mesh_db_adapter(mock_engine)

        assert isinstance(adapter, MeshDBAdapter)

    def test_inner_db_receives_engine(self) -> None:
        """The wrapped MeshDB instance is constructed with the supplied engine."""
        mock_engine = MagicMock()
        adapter = create_mesh_db_adapter(mock_engine)

        # The inner MeshDB must have been given the engine
        assert adapter._db.engine is mock_engine


# =============================================================================
# CommunityClusterer integration — MeshDBAdapter satisfies fetch_edges /
# promote_to_anchor protocol without AttributeError (#4864)
# =============================================================================


def _ensure_graspologic_stub() -> None:
    """Install a minimal graspologic stub if not present so tests run without the package."""
    if "graspologic" not in sys.modules:

        def _leiden(G, trials=3):
            import networkx as nx  # networkx is a declared dep

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


class TestCommunityClustererWithAdapter:
    """CommunityClusterer.run() works end-to-end through a real MeshDBAdapter (#4864).

    Verifies that the adapter exposes both ``fetch_edges`` and ``promote_to_anchor``
    so that CommunityClusterer never raises AttributeError when given an adapter
    rather than a raw MeshDB.
    """

    @pytest.mark.asyncio
    async def test_run_completes_without_attribute_error(self) -> None:
        """run() on a MeshDBAdapter-backed clusterer promotes centroids without error."""
        _ensure_graspologic_stub()
        edge_rows = [
            {"id": "e1", "from_node": _NODE_A, "to_node": _NODE_B, "weight": 0.9},
        ]
        adapter, mock_db = _make_adapter(
            fetch_edges=edge_rows,
            promote_to_anchor=None,
        )

        clusterer = CommunityClusterer(db=adapter)
        promoted = await clusterer.run(min_weight=0.3)

        assert isinstance(promoted, list)
        assert len(promoted) == 1
        assert promoted[0] in (_NODE_A, _NODE_B)

    @pytest.mark.asyncio
    async def test_run_empty_edges_promotes_nothing(self) -> None:
        """run() with no edges above min_weight returns [] and never calls promote_to_anchor."""
        _ensure_graspologic_stub()
        adapter, mock_db = _make_adapter(
            fetch_edges=[],
            promote_to_anchor=None,
        )

        clusterer = CommunityClusterer(db=adapter)
        promoted = await clusterer.run()

        assert promoted == []
        mock_db.promote_to_anchor.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_edges_called_with_min_weight(self) -> None:
        """run() forwards min_weight to adapter.fetch_edges."""
        _ensure_graspologic_stub()
        adapter, mock_db = _make_adapter(
            fetch_edges=[],
            promote_to_anchor=None,
        )

        clusterer = CommunityClusterer(db=adapter)
        await clusterer.run(min_weight=0.7)

        mock_db.fetch_edges.assert_awaited_once_with(min_weight=0.7)
