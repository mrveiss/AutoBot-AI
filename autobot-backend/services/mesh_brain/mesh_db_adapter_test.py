# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for MeshDBAdapter — concrete MeshGraph/MeshDB adapter (#2548)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

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
    async def test_returns_dict_when_found(self):
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
    async def test_returns_none_when_absent(self):
        adapter, mock_db = _make_adapter(get_edge=None)

        result = await adapter.get_edge(_NODE_A, _NODE_B)

        assert result is None
        mock_db.get_edge.assert_awaited_once_with(_NODE_A, _NODE_B)


class TestUpdateEdge:
    """MeshDBAdapter.update_edge forwards all keyword arguments to MeshDB."""

    @pytest.mark.asyncio
    async def test_forwards_kwargs(self):
        adapter, mock_db = _make_adapter(update_edge=None)

        await adapter.update_edge(_EDGE_ID, weight=0.75, co_access_count=5)

        mock_db.update_edge.assert_awaited_once_with(
            _EDGE_ID, weight=0.75, co_access_count=5
        )


class TestCreateEdge:
    """MeshDBAdapter.create_edge forwards positional and keyword arguments to MeshDB."""

    @pytest.mark.asyncio
    async def test_forwards_all_args(self):
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
    async def test_returns_count(self):
        adapter, mock_db = _make_adapter(get_co_access_count=7)

        result = await adapter.get_co_access_count(_NODE_A, _NODE_B)

        assert result == 7
        mock_db.get_co_access_count.assert_awaited_once_with(_NODE_A, _NODE_B)

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_edge(self):
        adapter, mock_db = _make_adapter(get_co_access_count=0)

        result = await adapter.get_co_access_count(_NODE_A, _NODE_B)

        assert result == 0


class TestUpdateAccessCount:
    """MeshDBAdapter.update_access_count delegates the node_ids list to MeshDB."""

    @pytest.mark.asyncio
    async def test_forwards_node_ids(self):
        adapter, mock_db = _make_adapter(update_access_count=None)

        await adapter.update_access_count([_NODE_A, _NODE_B])

        mock_db.update_access_count.assert_awaited_once_with([_NODE_A, _NODE_B])

    @pytest.mark.asyncio
    async def test_empty_list_is_forwarded(self):
        adapter, mock_db = _make_adapter(update_access_count=None)

        await adapter.update_access_count([])

        mock_db.update_access_count.assert_awaited_once_with([])


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
    async def test_projects_dicts_to_tuples(self):
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
    async def test_empty_neighbors_returns_empty_list(self):
        adapter, mock_db = _make_adapter(get_neighbors=[])

        result = await adapter.get_neighbors(_NODE_A)

        assert result == []

    @pytest.mark.asyncio
    async def test_weight_is_cast_to_float(self):
        """Weights stored as strings in the DB (e.g. from Redis) are coerced to float."""
        db_rows = [{"neighbor_id": _NODE_B, "weight": "0.75", "edge_type": "semantic"}]
        adapter, mock_db = _make_adapter(get_neighbors=db_rows)

        result = await adapter.get_neighbors(_NODE_A)

        assert result == [(_NODE_B, 0.75)]
        assert isinstance(result[0][1], float)

    @pytest.mark.asyncio
    async def test_single_neighbor(self):
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

    def test_has_all_mesh_db_protocol_methods(self):
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

    def test_has_all_mesh_graph_protocol_methods(self):
        """All methods required by StalenessPropagor's MeshGraph Protocol are present."""
        adapter = MeshDBAdapter(MagicMock())
        assert callable(getattr(adapter, "get_neighbors", None))


# =============================================================================
# Factory function
# =============================================================================


class TestCreateMeshDbAdapter:
    """create_mesh_db_adapter returns a ready MeshDBAdapter."""

    def test_returns_mesh_db_adapter_instance(self):
        mock_engine = MagicMock()
        adapter = create_mesh_db_adapter(mock_engine)

        assert isinstance(adapter, MeshDBAdapter)

    def test_inner_db_receives_engine(self):
        """The wrapped MeshDB instance is constructed with the supplied engine."""
        mock_engine = MagicMock()
        adapter = create_mesh_db_adapter(mock_engine)

        # The inner MeshDB must have been given the engine
        assert adapter._db.engine is mock_engine
