# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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


# =============================================================================
# Tests — create_node
# =============================================================================


class TestCreateNode:
    """MeshDB.create_node returns the UUID string from the DB."""

    @pytest.mark.asyncio
    async def test_returns_uuid_string(self):
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
    async def test_passes_correct_params(self):
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
    async def test_returns_uuid_string(self):
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
    async def test_duplicate_raises_on_db_error(self):
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
    async def test_returns_dict_when_found(self):
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
    async def test_returns_none_when_absent(self):
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
    async def test_returns_correct_structure(self):
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
    async def test_empty_when_no_neighbors(self):
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
    async def test_passes_min_weight_param(self):
        engine, conn = _make_engine(mappings=[])
        db = MeshDB(engine)

        await db.fetch_edges(min_weight=0.7)

        params = conn.execute.call_args[0][1]
        assert params["min_weight"] == 0.7

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
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
    async def test_creates_audit_entry(self):
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
    async def test_none_entity_id_allowed(self):
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
    async def test_skips_on_empty_list(self):
        engine, conn = _make_engine()
        db = MeshDB(engine)

        await db.update_access_count([])

        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calls_execute_with_node_ids(self):
        engine, conn = _make_engine()
        db = MeshDB(engine)

        await db.update_access_count([_NODE_UUID, _OTHER_UUID])

        conn.execute.assert_awaited_once()
        params = conn.execute.call_args[0][1]
        assert _NODE_UUID in params["node_ids"]
