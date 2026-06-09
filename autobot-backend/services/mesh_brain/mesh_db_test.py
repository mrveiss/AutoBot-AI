# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for MeshDB async PostgreSQL client (#2055)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.mesh_brain.mesh_db import MeshDB

_UNSET = object()  # sentinel for "argument not supplied"

# =============================================================================
# Helpers
# =============================================================================

_NODE_UUID = "aaaaaaaa-0000-0000-0000-000000000001"
_EDGE_UUID = "bbbbbbbb-0000-0000-0000-000000000002"
_OTHER_UUID = "cccccccc-0000-0000-0000-000000000003"


def _make_engine(scalar=_UNSET, fetchone=_UNSET, mappings=_UNSET):
    """Return a mocked AsyncEngine whose begin/connect ctx mgrs behave correctly.

    Use _UNSET sentinel so callers can pass fetchone=None to mean "DB returns no row".
    AsyncMock context managers are configured via return_value.__aenter__ because
    AsyncMock intercepts dunder methods and ignores direct attribute assignment.
    """
    conn = AsyncMock()

    if scalar is not _UNSET:
        conn.execute = AsyncMock(return_value=_scalar_result(scalar))
    elif fetchone is not _UNSET:
        conn.execute = AsyncMock(return_value=_fetchone_result(fetchone))
    elif mappings is not _UNSET:
        conn.execute = AsyncMock(return_value=_mappings_result(mappings))
    else:
        conn.execute = AsyncMock(return_value=_scalar_result(None))

    engine = MagicMock()
    # begin() returns an async context manager that yields conn
    engine.begin.return_value.__aenter__ = AsyncMock(return_value=conn)
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    # connect() returns an async context manager that yields conn
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=conn)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
    return engine, conn


def _scalar_result(value):
    """Return a mock result that supports scalar_one() and scalar()."""
    r = MagicMock()
    r.scalar_one = MagicMock(return_value=value)
    r.scalar = MagicMock(return_value=value)
    return r


def _fetchone_result(row_dict):
    """Return a mock result that supports mappings().fetchone()."""
    r = MagicMock()
    mappings_mock = MagicMock()
    mappings_mock.fetchone = MagicMock(return_value=row_dict)
    r.mappings = MagicMock(return_value=mappings_mock)
    return r


def _mappings_result(rows):
    """Return a mock result that supports mappings() iteration."""
    r = MagicMock()
    r.mappings = MagicMock(return_value=iter(rows))
    return r


def _rowcount_result(count: int):
    """Return a mock result whose rowcount attribute equals count."""
    r = MagicMock()
    r.rowcount = count
    r.scalar = MagicMock(return_value=count)
    return r


# =============================================================================
# Tests — create_node
# =============================================================================


class TestCreateNode:
    """MeshDB.create_node returns the UUID string from the DB."""

    @pytest.mark.asyncio
    async def test_returns_uuid_string(self) -> None:
        engine, conn = _make_engine(scalar=_NODE_UUID)
        db = MeshDB(engine)

        result = await db.create_node(
            chunk_id="chunk-1",
            source_file="file.txt",
            node_type="doc",
            raptor_level=0,
        )

        assert result == _NODE_UUID
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_correct_params(self) -> None:
        engine, conn = _make_engine(scalar=_NODE_UUID)
        db = MeshDB(engine)

        await db.create_node("c-42", "src.md", "summary", raptor_level=2)

        _, kwargs = conn.execute.call_args
        # params dict is the second positional arg
        params = conn.execute.call_args[0][1]
        assert params["chunk_id"] == "c-42"
        assert params["node_type"] == "summary"
        assert params["raptor_level"] == 2


# =============================================================================
# Tests — create_edge
# =============================================================================


class TestCreateEdge:
    """MeshDB.create_edge returns the edge UUID string."""

    @pytest.mark.asyncio
    async def test_returns_uuid_string(self) -> None:
        engine, conn = _make_engine(scalar=_EDGE_UUID)
        db = MeshDB(engine)

        result = await db.create_edge(
            from_node=_NODE_UUID,
            to_node=_OTHER_UUID,
            edge_type="semantic",
            weight=0.8,
            origin="seeder",
        )

        assert result == _EDGE_UUID
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_raises_on_db_error(self) -> None:
        """A unique-constraint violation from the DB propagates as an exception."""
        engine, conn = _make_engine()
        conn.execute = AsyncMock(side_effect=Exception("UniqueViolation"))
        db = MeshDB(engine)

        with pytest.raises(Exception, match="UniqueViolation"):
            await db.create_edge(_NODE_UUID, _OTHER_UUID, "semantic", 0.8, "seeder")


# =============================================================================
# Tests — get_edge
# =============================================================================


class TestGetEdge:
    """MeshDB.get_edge returns dict or None."""

    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self) -> None:
        row = {
            "id": _EDGE_UUID,
            "from_node": _NODE_UUID,
            "to_node": _OTHER_UUID,
            "edge_type": "semantic",
            "weight": 0.9,
            "origin": "seeder",
            "co_access_count": 0,
            "last_reinforced": None,
        }
        engine, _ = _make_engine(fetchone=row)
        db = MeshDB(engine)

        result = await db.get_edge(_NODE_UUID, _OTHER_UUID, edge_type="semantic")

        assert result is not None
        assert result["id"] == _EDGE_UUID
        assert result["weight"] == 0.9

    @pytest.mark.asyncio
    async def test_returns_none_when_absent(self) -> None:
        engine, _ = _make_engine(fetchone=None)
        db = MeshDB(engine)

        result = await db.get_edge(_NODE_UUID, _OTHER_UUID)

        assert result is None


# =============================================================================
# Tests — get_neighbors
# =============================================================================


class TestGetNeighbors:
    """MeshDB.get_neighbors returns list of dicts."""

    @pytest.mark.asyncio
    async def test_returns_correct_structure(self) -> None:
        rows = [
            {
                "edge_id": _EDGE_UUID,
                "neighbor_id": _OTHER_UUID,
                "edge_type": "semantic",
                "weight": 0.85,
                "origin": "seeder",
            }
        ]
        engine, _ = _make_engine(mappings=rows)
        db = MeshDB(engine)

        result = await db.get_neighbors(_NODE_UUID, min_weight=0.5)

        assert len(result) == 1
        assert result[0]["neighbor_id"] == _OTHER_UUID
        assert result[0]["weight"] == 0.85

    @pytest.mark.asyncio
    async def test_empty_when_no_neighbors(self) -> None:
        engine, _ = _make_engine(mappings=[])
        db = MeshDB(engine)

        result = await db.get_neighbors(_NODE_UUID, min_weight=0.5)

        assert result == []


# =============================================================================
# Tests — fetch_edges
# =============================================================================


class TestFetchEdges:
    """MeshDB.fetch_edges filters by min_weight and satisfies MeshEdgeSync Protocol."""

    @pytest.mark.asyncio
    async def test_passes_min_weight_param(self) -> None:
        engine, conn = _make_engine(mappings=[])
        db = MeshDB(engine)

        await db.fetch_edges(min_weight=0.7)

        params = conn.execute.call_args[0][1]
        assert params["min_weight"] == 0.7

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self) -> None:
        rows = [
            {
                "id": _EDGE_UUID,
                "from_node": _NODE_UUID,
                "to_node": _OTHER_UUID,
                "edge_type": "coref",
                "weight": 0.6,
                "origin": "seeder",
            }
        ]
        engine, _ = _make_engine(mappings=rows)
        db = MeshDB(engine)

        result = await db.fetch_edges(min_weight=0.5)

        assert isinstance(result, list)
        assert result[0]["weight"] == 0.6


# =============================================================================
# Tests — log_evolution
# =============================================================================


class TestLogEvolution:
    """MeshDB.log_evolution inserts an audit entry without raising."""

    @pytest.mark.asyncio
    async def test_creates_audit_entry(self) -> None:
        engine, conn = _make_engine()
        db = MeshDB(engine)

        await db.log_evolution(
            event_type="weight_updated",
            entity_id=_EDGE_UUID,
            old_value={"weight": 0.5},
            new_value={"weight": 0.8},
            actor="EdgeLearner",
        )

        conn.execute.assert_awaited_once()
        params = conn.execute.call_args[0][1]
        assert params["event_type"] == "weight_updated"
        assert params["actor"] == "EdgeLearner"
        assert json.loads(params["new_value"]) == {"weight": 0.8}

    @pytest.mark.asyncio
    async def test_none_entity_id_allowed(self) -> None:
        """log_evolution must accept entity_id=None without raising."""
        engine, conn = _make_engine()
        db = MeshDB(engine)

        await db.log_evolution(
            event_type="node_created",
            entity_id=None,
            old_value=None,
            new_value={"chunk_id": "x"},
            actor="seeder",
        )

        conn.execute.assert_awaited_once()
        params = conn.execute.call_args[0][1]
        assert params["entity_id"] is None
        assert params["old_value"] is None


# =============================================================================
# Tests — update_access_count
# =============================================================================


class TestUpdateAccessCount:
    """MeshDB.update_access_count skips on empty list and fires SQL otherwise."""

    @pytest.mark.asyncio
    async def test_skips_on_empty_list(self) -> None:
        engine, conn = _make_engine()
        db = MeshDB(engine)

        await db.update_access_count([])

        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calls_execute_with_node_ids(self) -> None:
        engine, conn = _make_engine()
        db = MeshDB(engine)

        await db.update_access_count([_NODE_UUID, _OTHER_UUID])

        conn.execute.assert_awaited_once()
        params = conn.execute.call_args[0][1]
        assert _NODE_UUID in params["node_ids"]


# =============================================================================
# Tests — decay_edges
# =============================================================================


class TestDecayEdges:
    """MeshDB.decay_edges passes correct SQL params and returns rowcount."""

    @pytest.mark.asyncio
    async def test_decay_edges_passes_correct_params(self) -> None:
        from datetime import datetime, timezone

        engine, conn = _make_engine()
        conn.execute = AsyncMock(return_value=_rowcount_result(3))
        db = MeshDB(engine)
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)

        count = await db.decay_edges(
            origins=["seeder", "learner"],
            not_reinforced_since=cutoff,
            decay_factor=0.9,
        )

        assert count == 3
        params = conn.execute.call_args[0][1]
        assert params["factor"] == 0.9
        assert params["cutoff"] == cutoff
        assert "seeder" in params["origins"]


# =============================================================================
# Tests — delete_edges
# =============================================================================


class TestDeleteEdges:
    """MeshDB.delete_edges returns rowcount of deleted rows."""

    @pytest.mark.asyncio
    async def test_delete_edges_returns_count(self) -> None:
        engine, conn = _make_engine()
        conn.execute = AsyncMock(return_value=_rowcount_result(5))
        db = MeshDB(engine)

        count = await db.delete_edges(max_weight=0.1)

        assert count == 5
        params = conn.execute.call_args[0][1]
        assert params["max_weight"] == 0.1


# =============================================================================
# Tests — get_promotion_candidates
# =============================================================================


class TestGetPromotionCandidates:
    """MeshDB.get_promotion_candidates forwards min_access and min_edges."""

    @pytest.mark.asyncio
    async def test_get_promotion_candidates_filters_correctly(self) -> None:
        rows = [
            {
                "id": _NODE_UUID,
                "chunk_id": "c-1",
                "node_type": "doc",
                "access_count": 10,
                "edge_count": 4,
            }
        ]
        engine, conn = _make_engine(mappings=rows)
        db = MeshDB(engine)

        result = await db.get_promotion_candidates(min_access=5, min_edges=3)

        assert len(result) == 1
        assert result[0]["id"] == _NODE_UUID
        params = conn.execute.call_args[0][1]
        assert params["min_access"] == 5
        assert params["min_edges"] == 3


# =============================================================================
# Tests — promote_to_anchor
# =============================================================================


class TestPromoteToAnchor:
    """MeshDB.promote_to_anchor executes UPDATE with correct node_id."""

    @pytest.mark.asyncio
    async def test_promote_to_anchor_updates_flag(self) -> None:
        engine, conn = _make_engine()
        db = MeshDB(engine)

        await db.promote_to_anchor(_NODE_UUID)

        conn.execute.assert_awaited_once()
        params = conn.execute.call_args[0][1]
        assert params["node_id"] == _NODE_UUID


# =============================================================================
# Tests — get_graph_density
# =============================================================================


class TestGetGraphDensity:
    """MeshDB.get_graph_density returns a float value."""

    @pytest.mark.asyncio
    async def test_get_graph_density_returns_float(self) -> None:
        engine, conn = _make_engine(scalar=2.5)
        db = MeshDB(engine)

        density = await db.get_graph_density()

        assert isinstance(density, float)
        assert density == 2.5

    @pytest.mark.asyncio
    async def test_get_graph_density_returns_zero_when_empty(self) -> None:
        engine, conn = _make_engine(scalar=None)
        db = MeshDB(engine)

        density = await db.get_graph_density()

        assert density == 0.0


# =============================================================================
# Tests — get_anchor_neighbors
# =============================================================================


class TestGetAnchorNeighbors:
    """MeshDB.get_anchor_neighbors returns anchor node IDs adjacent to seeds."""

    @pytest.mark.asyncio
    async def test_get_anchor_neighbors_returns_anchor_nodes_adjacent_to_seeds(self) -> None:
        """get_anchor_neighbors returns UUIDs of anchor nodes reachable from seed_ids."""
        anchor_id = "aaaaaaaa-0000-0000-0000-000000000001"
        seed_id = "bbbbbbbb-0000-0000-0000-000000000002"

        rows = [{"id": anchor_id}]
        engine, _ = _make_engine(mappings=rows)
        db = MeshDB(engine)

        result = await db.get_anchor_neighbors([seed_id])

        assert result == [anchor_id]

    @pytest.mark.asyncio
    async def test_get_anchor_neighbors_empty_seeds_returns_empty(self) -> None:
        """get_anchor_neighbors returns [] without touching DB when seed_ids is empty."""
        engine, conn = _make_engine()
        db = MeshDB(engine)

        result = await db.get_anchor_neighbors([])

        assert result == []
        conn.execute.assert_not_awaited()
