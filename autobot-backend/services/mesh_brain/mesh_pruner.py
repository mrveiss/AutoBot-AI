# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Weekly entropy control and decay for Neural Mesh RAG (#1994, #2118)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_LEARNER_ORIGINS = ["learner", "discoverer"]


@dataclass
class PruningReport:
    """Summary counts from a single MeshPruner.prune() run."""

    edges_decayed: int = 0
    edges_deleted: int = 0
    nodes_archived: int = 0
    edges_merged: int = 0
    density_warning: bool = False


class MeshDB(Protocol):
    """Protocol for mesh database operations required by MeshPruner."""

    async def decay_edges(self, origins: list[str], not_reinforced_since: datetime, decay_factor: float) -> int: ...

    async def delete_edges(self, max_weight: float) -> int: ...

    async def archive_orphan_nodes(self, no_access_since: datetime) -> int: ...

    async def merge_duplicate_edges(self) -> int: ...

    async def get_graph_density(self) -> float: ...


class MeshPruner:
    """AutoBot manages its own graph health. Runs weekly.

    Rules:
    1. Decay unreinforced learner/discoverer edges (decay_days, decay_factor).
    2. Delete edges whose weight falls below min_weight.
    3. Archive orphaned nodes (no edges, no access for orphan_days).
    4. Merge near-duplicate edges.
    5. Graph density check — emit warning when avg edges/node > max_avg_edges.

    Seeder edges (origin='seeder') are NEVER decayed.
    Orphaned nodes are archived (not deleted) and remain recoverable.
    """

    def __init__(
        self,
        db: MeshDB,
        edge_sync=None,
        decay_days: int = 30,
        decay_factor: float = 0.8,
        min_weight: float = 0.1,
        orphan_days: int = 60,
        max_avg_edges: int = 20,
    ) -> None:
        self.db = db
        self.edge_sync = edge_sync
        self.decay_days = decay_days
        self.decay_factor = decay_factor
        self.min_weight = min_weight
        self.orphan_days = orphan_days
        self.max_avg_edges = max_avg_edges

    async def prune(self) -> PruningReport:
        """Run all five pruning steps and return a consolidated report."""
        report = PruningReport()

        report.edges_decayed = await self._decay_stale_edges()
        report.edges_deleted = await self._delete_weak_edges()
        report.nodes_archived = await self._archive_orphans()
        report.edges_merged = await self._merge_duplicates()
        report.density_warning = await self._check_density()

        if self.edge_sync is not None:
            await self.edge_sync.sync()

        await self._log_report(report)
        return report

    async def _decay_stale_edges(self) -> int:
        """Decay learner/discoverer edges not reinforced within decay_days."""
        cutoff = _utc_ago(days=self.decay_days)
        return await self.db.decay_edges(
            origins=_LEARNER_ORIGINS,
            not_reinforced_since=cutoff,
            decay_factor=self.decay_factor,
        )

    async def _delete_weak_edges(self) -> int:
        """Delete edges whose weight is at or below min_weight."""
        return await self.db.delete_edges(max_weight=self.min_weight)

    async def _archive_orphans(self) -> int:
        """Archive nodes with no edges and no access within orphan_days."""
        cutoff = _utc_ago(days=self.orphan_days)
        return await self.db.archive_orphan_nodes(no_access_since=cutoff)

    async def _merge_duplicates(self) -> int:
        """Merge near-duplicate edges and return the count merged."""
        return await self.db.merge_duplicate_edges()

    async def _check_density(self) -> bool:
        """Return True if avg edges/node exceeds max_avg_edges threshold."""
        density = await self.db.get_graph_density()
        exceeded = density > self.max_avg_edges
        if exceeded:
            logger.warning(
                "MeshPruner: graph density %.2f exceeds threshold %d",
                density,
                self.max_avg_edges,
            )
        return exceeded

    async def _log_report(self, report: PruningReport) -> None:
        """Emit a structured log line summarising the pruning run."""
        logger.info(
            "MeshPruner complete: decayed=%d deleted=%d archived=%d merged=%d density_warning=%s",
            report.edges_decayed,
            report.edges_deleted,
            report.nodes_archived,
            report.edges_merged,
            report.density_warning,
        )


def _utc_ago(*, days: int) -> datetime:
    """Return a UTC datetime exactly ``days`` days in the past."""
    return datetime.now(tz=timezone.utc) - timedelta(days=days)
