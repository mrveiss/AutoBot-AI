# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLM-based relationship naming for high-weight CO_RETRIEVED edges (#2117).

Runs as a scheduled background job (nightly).  EdgeLearner creates CO_RETRIEVED
edges from usage patterns; EdgeDiscoverer promotes the strongest ones to named
relationship types by asking an LLM to classify the pair of chunks.
"""

from dataclasses import dataclass
from typing import Callable, Coroutine, Protocol

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Relationship labels offered to the LLM as constrained choices.
_KNOWN_LABELS = (
    "CALLS",
    "CONFIGURES",
    "VALIDATES",
    "EXTENDS",
    "TRIGGERS",
    "IMPLEMENTS",
    "DEPENDS_ON",
    "DOCUMENTS",
    "TESTS",
    "DEPLOYS",
    "MONITORS",
    "SIMILAR_TO",
)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class DiscovererDB(Protocol):
    """Subset of MeshDB operations required by EdgeDiscoverer (#2117)."""

    async def fetch_candidate_edges(
        self,
        edge_type: str,
        min_weight: float,
        min_co_access: int,
        origin: str,
        limit: int,
    ) -> list[dict]: ...

    async def update_edge(
        self,
        edge_id: str,
        edge_type: str | None = None,
        origin: str | None = None,
    ) -> None: ...

    async def log_evolution(
        self,
        event_type: str,
        entity_id: str | None,
        old_value: dict | None,
        new_value: dict | None,
        actor: str,
    ) -> None: ...


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryReport:
    """Summary of a single EdgeDiscoverer run."""

    edges_typed: int
    llm_calls: int


# ---------------------------------------------------------------------------
# EdgeDiscoverer
# ---------------------------------------------------------------------------

# Type alias for the async LLM callable injected by the caller.
LLMCallable = Callable[[str], Coroutine[None, None, str]]


class EdgeDiscoverer:
    """Finds and names relationship types AutoBot learns from usage.

    Runs as a scheduled background job (nightly).  Processes high-weight
    CO_RETRIEVED edges that EdgeLearner created, clusters similar pairs to
    reduce LLM calls, then upgrades edge types to descriptive labels.
    """

    def __init__(
        self,
        db: DiscovererDB,
        llm: LLMCallable,
        batch_size: int = 50,
    ) -> None:
        self.db = db
        self.llm = llm
        self.batch_size = batch_size

    async def discover(self) -> DiscoveryReport:
        """Run one discovery cycle. Returns report of edges typed (#2117)."""
        candidates = await self.db.fetch_candidate_edges(
            edge_type="CO_RETRIEVED",
            min_weight=0.7,
            min_co_access=5,
            origin="learner",
            limit=self.batch_size,
        )
        if not candidates:
            return DiscoveryReport(edges_typed=0, llm_calls=0)

        clusters = self._cluster_by_content_similarity(candidates)
        typed_count, llm_calls = await self._classify_clusters(clusters)
        logger.info(
            "EdgeDiscoverer: typed %d edges in %d LLM calls",
            typed_count,
            llm_calls,
        )
        return DiscoveryReport(edges_typed=typed_count, llm_calls=llm_calls)

    async def _classify_clusters(self, clusters: list[list[dict]]) -> tuple[int, int]:
        """Classify each cluster with one LLM call and apply label to all members."""
        typed_count = 0
        llm_calls = 0
        for cluster in clusters:
            label = await self._classify_relationship(cluster[0])
            llm_calls += 1
            for edge in cluster:
                await self._apply_label(edge, label)
                typed_count += 1
        return typed_count, llm_calls

    async def _apply_label(self, edge: dict, label: str) -> None:
        """Write the discovered label to the DB and record the evolution event."""
        await self.db.update_edge(edge["id"], edge_type=label, origin="discoverer")
        await self.db.log_evolution(
            "edge_typed",
            edge["id"],
            {"edge_type": "CO_RETRIEVED"},
            {"edge_type": label},
            "discoverer",
        )

    async def _classify_relationship(self, edge: dict) -> str:
        """Ask the LLM to name the relationship between two chunk texts (#2117)."""
        content_a = _truncate(edge.get("from_content", "") or edge.get("from_chunk_id", ""))
        content_b = _truncate(edge.get("to_content", "") or edge.get("to_chunk_id", ""))
        prompt = _build_classification_prompt(content_a, content_b)
        result = await self.llm(prompt)
        return result.strip().upper()

    def _cluster_by_content_similarity(self, edges: list[dict]) -> list[list[dict]]:
        """Group edges whose from_node is identical to share one LLM call (#2117).

        Simple heuristic: edges sharing a from_node are likely related in
        topic, so the representative chunk text is similar enough that a single
        LLM call covers the whole group.
        """
        groups: dict[str, list[dict]] = {}
        for edge in edges:
            key = edge.get("from_node", "")
            groups.setdefault(key, []).append(edge)
        return list(groups.values())


# ---------------------------------------------------------------------------
# Module-level helpers (kept under 30 lines each)
# ---------------------------------------------------------------------------


def _truncate(text: str, max_chars: int = 300) -> str:
    """Return at most max_chars characters of text."""
    return text[:max_chars]


def _build_classification_prompt(content_a: str, content_b: str) -> str:
    """Construct the LLM prompt for relationship classification (#2117)."""
    labels = ", ".join(_KNOWN_LABELS)
    return (
        "These two knowledge chunks are frequently retrieved together.\n"
        f"Chunk A: {content_a}\n"
        f"Chunk B: {content_b}\n\n"
        "What is the relationship? Respond with ONE word from:\n"
        f"{labels}\n"
        "Or suggest a new relationship word if none fit."
    )
