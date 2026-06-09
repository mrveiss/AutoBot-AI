# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Daily anchor emergence: promotes hot nodes to anchor status for Neural Mesh RAG (#2119)."""

from dataclasses import dataclass, field
from typing import Callable, Coroutine, Protocol

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


# =============================================================================
# Protocols
# =============================================================================


class MeshDB(Protocol):
    """Protocol for mesh database operations required by NodePromoter."""

    async def get_promotion_candidates(self, min_access: int, min_edges: int) -> list[dict]:
        """Return nodes eligible for promotion: access_count >= min_access and
        edge_count >= min_edges, not already anchors."""
        ...

    async def get_stale_anchors(self, max_access: int, inactive_days: int) -> list[dict]:
        """Return anchor nodes with access_count <= max_access inactive for >= inactive_days."""
        ...

    async def get_neighborhood(self, node_id: str, hops: int) -> list[dict]:
        """Return all nodes within *hops* of node_id, each as a dict with 'content'."""
        ...

    async def promote_to_anchor(self, node_id: str) -> None:
        """Mark node as an anchor in mesh_nodes."""
        ...

    async def demote_anchor(self, node_id: str) -> None:
        """Clear anchor flag on node in mesh_nodes."""
        ...


class ChromaCollection(Protocol):
    """Minimal ChromaDB client protocol for anchor embedding storage."""

    async def upsert(
        self,
        collection: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """Upsert documents into the named collection."""
        ...

    async def delete(self, collection: str, ids: list[str]) -> None:
        """Delete documents by ID from the named collection."""
        ...


# =============================================================================
# Result type
# =============================================================================


@dataclass
class PromotionReport:
    """Summary of a single NodePromoter.evaluate() run.

    Attributes:
        nodes_promoted: UUIDs of nodes promoted to anchor status.
        nodes_demoted:  UUIDs of nodes demoted from anchor status.
    """

    nodes_promoted: list = field(default_factory=list)
    nodes_demoted: list = field(default_factory=list)


# =============================================================================
# NodePromoter
# =============================================================================


class NodePromoter:
    """Promotes hot nodes to anchor status for faster retrieval.

    Anchor nodes: retriever checks these first before graph walk.
    When a node is promoted, its 2-hop neighborhood is summarized
    and stored as an anchor embedding in ChromaDB (#2119).
    """

    def __init__(
        self,
        db: MeshDB,
        llm: Callable[[str], Coroutine],
        chroma_client: ChromaCollection,
        promote_access_threshold: int = 50,
        promote_min_edges: int = 5,
        demote_access_threshold: int = 10,
        demote_days: int = 30,
    ) -> None:
        self.db = db
        self.llm = llm
        self.chroma = chroma_client
        self.promote_access_threshold = promote_access_threshold
        self.promote_min_edges = promote_min_edges
        self.demote_access_threshold = demote_access_threshold
        self.demote_days = demote_days

    async def evaluate(self) -> PromotionReport:
        """Run one promotion/demotion cycle and return a PromotionReport.

        Promotes all hot candidates then demotes all stale anchors.
        """
        report = PromotionReport()
        await self._promote_candidates(report)
        await self._demote_stale(report)
        logger.info(
            "NodePromoter: promoted=%d demoted=%d",
            len(report.nodes_promoted),
            len(report.nodes_demoted),
        )
        return report

    # ------------------------------------------------------------------
    # Private helpers — each under 30 lines
    # ------------------------------------------------------------------

    async def _promote_candidates(self, report: PromotionReport) -> None:
        """Fetch promotion candidates and promote each one."""
        candidates = await self.db.get_promotion_candidates(
            min_access=self.promote_access_threshold,
            min_edges=self.promote_min_edges,
        )
        for node in candidates:
            await self._promote_node(node, report)

    async def _demote_stale(self, report: PromotionReport) -> None:
        """Fetch stale anchors and demote each one."""
        stale = await self.db.get_stale_anchors(
            max_access=self.demote_access_threshold,
            inactive_days=self.demote_days,
        )
        for node in stale:
            await self._demote_node(node, report)

    async def _promote_node(self, node: dict, report: PromotionReport) -> None:
        """Summarize 2-hop neighborhood, store in ChromaDB, mark anchor in DB."""
        neighborhood = await self.db.get_neighborhood(node["id"], hops=2)
        summary = await self._summarize_neighborhood(neighborhood)
        await self.chroma.upsert(
            collection="mesh_anchors",
            ids=[f"anchor_{node['id']}"],
            documents=[summary],
            metadatas=[{"node_id": str(node["id"]), "neighborhood_size": len(neighborhood)}],
        )
        await self.db.promote_to_anchor(node["id"])
        report.nodes_promoted.append(node["id"])
        logger.info(
            "NodePromoter: promoted node %s (neighborhood=%d)",
            node["id"],
            len(neighborhood),
        )

    async def _demote_node(self, node: dict, report: PromotionReport) -> None:
        """Clear anchor flag in DB and remove embedding from ChromaDB."""
        await self.db.demote_anchor(node["id"])
        await self.chroma.delete(
            collection="mesh_anchors",
            ids=[f"anchor_{node['id']}"],
        )
        report.nodes_demoted.append(node["id"])
        logger.info("NodePromoter: demoted anchor %s", node["id"])

    async def _summarize_neighborhood(self, neighborhood: list[dict]) -> str:
        """Call LLM to produce a 2-3 sentence theme summary of the neighborhood."""
        texts = [n.get("content", "")[:200] for n in neighborhood[:10]]
        prompt = "Summarize the theme of these related knowledge chunks " "in 2-3 sentences:\n\n" + "\n---\n".join(
            texts
        )
        return await self.llm(prompt)
