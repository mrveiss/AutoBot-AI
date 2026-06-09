# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for MeshPruner — weekly entropy control and decay (#1994, #2118)."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from services.mesh_brain.mesh_pruner import MeshPruner, PruningReport

# =============================================================================
# Helpers
# =============================================================================

_DECAY_DAYS = 30
_DECAY_FACTOR = 0.8
_MIN_WEIGHT = 0.1
_ORPHAN_DAYS = 60
_MAX_AVG_EDGES = 20


def _make_db_mock(density: float = 5.0) -> AsyncMock:
    """Return a MeshDB mock with sensible non-zero defaults."""
    db = AsyncMock()
    db.decay_edges = AsyncMock(return_value=10)
    db.delete_edges = AsyncMock(return_value=3)
    db.archive_orphan_nodes = AsyncMock(return_value=2)
    db.merge_duplicate_edges = AsyncMock(return_value=1)
    db.get_graph_density = AsyncMock(return_value=density)
    return db


def _make_pruner(db: AsyncMock, edge_sync=None) -> MeshPruner:
    return MeshPruner(
        db=db,
        edge_sync=edge_sync,
        decay_days=_DECAY_DAYS,
        decay_factor=_DECAY_FACTOR,
        min_weight=_MIN_WEIGHT,
        orphan_days=_ORPHAN_DAYS,
        max_avg_edges=_MAX_AVG_EDGES,
    )


# =============================================================================
# Tests
# =============================================================================


class TestMeshPrunerAllSteps:
    """Verify that prune() calls every db method exactly once."""

    @pytest.mark.asyncio
    async def test_prune_runs_all_steps(self) -> None:
        """All five db methods are awaited during a single prune() call."""
        db = _make_db_mock()
        pruner = _make_pruner(db)

        await pruner.prune()

        db.decay_edges.assert_awaited_once()
        db.delete_edges.assert_awaited_once()
        db.archive_orphan_nodes.assert_awaited_once()
        db.merge_duplicate_edges.assert_awaited_once()
        db.get_graph_density.assert_awaited_once()


class TestDecayExcludesSeeder:
    """Seeder edges must not appear in the origins list passed to decay_edges."""

    @pytest.mark.asyncio
    async def test_decay_excludes_seeder_edges(self) -> None:
        """decay_edges is called with origins=['learner','discoverer'], never 'seeder'."""
        db = _make_db_mock()
        pruner = _make_pruner(db)

        await pruner.prune()

        call_kwargs = db.decay_edges.call_args
        origins = call_kwargs.kwargs.get("origins") or call_kwargs.args[0]
        assert "seeder" not in origins
        assert set(origins) == {"learner", "discoverer"}


class TestDeleteWeakEdges:
    """delete_edges must receive min_weight as max_weight."""

    @pytest.mark.asyncio
    async def test_delete_weak_edges_uses_min_weight(self) -> None:
        """delete_edges is called with max_weight equal to min_weight config."""
        db = _make_db_mock()
        pruner = _make_pruner(db)

        await pruner.prune()

        db.delete_edges.assert_awaited_once_with(max_weight=_MIN_WEIGHT)


class TestArchiveOrphans:
    """archive_orphan_nodes must use a cutoff derived from orphan_days."""

    @pytest.mark.asyncio
    async def test_archive_orphans_uses_orphan_days(self) -> None:
        """archive_orphan_nodes receives a datetime roughly orphan_days ago."""
        db = _make_db_mock()
        pruner = _make_pruner(db)

        await pruner.prune()

        call_kwargs = db.archive_orphan_nodes.call_args
        cutoff = call_kwargs.kwargs.get("no_access_since") or call_kwargs.args[0]

        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        expected_cutoff = now - timedelta(days=_ORPHAN_DAYS)
        # Allow a 5-second window for test execution time
        assert abs((cutoff - expected_cutoff).total_seconds()) < 5


class TestDensityWarning:
    """density_warning reflects whether avg edges/node exceeds max_avg_edges."""

    @pytest.mark.asyncio
    async def test_density_warning_set_when_exceeded(self) -> None:
        """density > max_avg_edges → PruningReport.density_warning is True."""
        db = _make_db_mock(density=25.0)
        pruner = _make_pruner(db)

        report = await pruner.prune()

        assert report.density_warning is True

    @pytest.mark.asyncio
    async def test_density_warning_false_when_normal(self) -> None:
        """density < max_avg_edges → PruningReport.density_warning is False."""
        db = _make_db_mock(density=10.0)
        pruner = _make_pruner(db)

        report = await pruner.prune()

        assert report.density_warning is False


class TestEdgeSyncBehaviour:
    """edge_sync.sync() is called after pruning only when a sync object is provided."""

    @pytest.mark.asyncio
    async def test_edge_sync_called_after_prune(self) -> None:
        """edge_sync.sync() is awaited once at the end of prune()."""
        db = _make_db_mock()
        edge_sync = AsyncMock()
        edge_sync.sync = AsyncMock()
        pruner = _make_pruner(db, edge_sync=edge_sync)

        await pruner.prune()

        edge_sync.sync.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_edge_sync_skipped_when_none(self) -> None:
        """prune() completes without error when edge_sync is None."""
        db = _make_db_mock()
        pruner = _make_pruner(db, edge_sync=None)

        # Should not raise
        report = await pruner.prune()

        assert isinstance(report, PruningReport)


class TestPruningReportCounts:
    """PruningReport is populated with return values from every db method."""

    @pytest.mark.asyncio
    async def test_report_contains_all_counts(self) -> None:
        """PruningReport fields mirror the int values returned by each db method."""
        db = _make_db_mock(density=5.0)
        db.decay_edges = AsyncMock(return_value=7)
        db.delete_edges = AsyncMock(return_value=4)
        db.archive_orphan_nodes = AsyncMock(return_value=2)
        db.merge_duplicate_edges = AsyncMock(return_value=1)

        pruner = _make_pruner(db)
        report = await pruner.prune()

        assert report.edges_decayed == 7
        assert report.edges_deleted == 4
        assert report.nodes_archived == 2
        assert report.edges_merged == 1
        assert report.density_warning is False
