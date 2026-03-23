# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unified mesh-aware retriever for Neural Mesh RAG Phase 3 (#1994, #2058).

Routes queries by complexity:
  SIMPLE     -> semantic search only (~50 ms fast path)
  MODERATE   -> hybrid search + 1-hop PPR expansion
  COMPLEX    -> full pipeline: hybrid + anchor lookup + PPR + rerank
  MULTI_HOP  -> same as COMPLEX
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Protocol

logger = logging.getLogger(__name__)


# =============================================================================
# Protocols — duck-typed for testability
# =============================================================================


class _AnchorDB(Protocol):
    """Minimal protocol for anchor-node lookups used by _find_anchors."""

    async def get_anchor_neighbors(self, seed_ids: list[str]) -> list[str]:
        """Return node IDs of anchor nodes adjacent to any of seed_ids."""
        ...


# =============================================================================
# Result type
# =============================================================================


@dataclass
class MeshRetrievalResult:
    """Output of NeuralMeshRetriever.retrieve().

    Attributes:
        chunks:         Ranked result dicts / SearchResult objects.
        expanded:       True when PPR expansion was applied.
        complexity:     String value of the QueryComplexity tier used.
        anchor_used:    True when at least one anchor node was injected.
        nodes_explored: Approximate count of graph nodes visited.
    """

    chunks: list
    expanded: bool
    complexity: str
    anchor_used: bool = False
    nodes_explored: int = 0


# =============================================================================
# Retriever
# =============================================================================


class NeuralMeshRetriever:
    """Self-evolving retrieval: vector seed -> mesh expansion -> rerank -> learn.

    All dependencies are injected as callables or Protocol instances so the
    class can be fully unit-tested with AsyncMock / MagicMock without a
    running database, Redis, or model server.

    Issue #2058: Phase 3 integration point for Neural Mesh RAG.
    """

    def __init__(
        self,
        chroma_search: Callable[..., Coroutine[Any, Any, list]],
        hybrid_search: Callable[..., Coroutine[Any, Any, list]],
        ppr: Any,
        edge_learner: Any,
        reranker: Any,
        classifier: Any,
        mesh_db: Any,
    ) -> None:
        """Inject all dependencies.

        Args:
            chroma_search:  async callable(query, k) -> list of results.
            hybrid_search:  async callable(query, top_k) -> list of results.
            ppr:            PersonalizedPageRank instance.
            edge_learner:   EdgeLearner instance.
            reranker:       ResultReranker instance.
            classifier:     QueryClassifier instance.
            mesh_db:        Object satisfying _AnchorDB protocol.
        """
        self.chroma_search = chroma_search
        self.hybrid_search = hybrid_search
        self.ppr = ppr
        self.edge_learner = edge_learner
        self.reranker = reranker
        self.classifier = classifier
        self.mesh_db = mesh_db

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def retrieve(self, query: str, top_k: int = 5) -> MeshRetrievalResult:
        """Main entry point. Routes by query complexity.

        Args:
            query: Raw user query string.
            top_k: Maximum number of chunks to return.

        Returns:
            MeshRetrievalResult with ranked chunks and metadata.
        """
        complexity = self.classifier.classify(query)
        value = complexity.value

        logger.debug("NeuralMeshRetriever: query complexity=%s top_k=%d", value, top_k)

        if value == "simple":
            return await self._simple_retrieve(query, top_k)
        if value == "moderate":
            return await self._moderate_retrieve(query, top_k)
        # complex or multi_hop both use the full pipeline
        return await self._full_retrieve(query, top_k)

    # ------------------------------------------------------------------
    # Retrieval paths
    # ------------------------------------------------------------------

    async def _simple_retrieve(self, query: str, top_k: int) -> MeshRetrievalResult:
        """Semantic search only — fast path (~50 ms). Issue #2058."""
        results = await self.chroma_search(query, top_k)
        self._fire_learner(query, results)
        return MeshRetrievalResult(chunks=results, expanded=False, complexity="simple")

    async def _moderate_retrieve(self, query: str, top_k: int) -> MeshRetrievalResult:
        """Hybrid search + 1-hop PPR expansion. Issue #2058."""
        seeds = await self.hybrid_search(query, top_k * 2)
        seed_ids = [self._chunk_id(r) for r in seeds[:5]]

        expanded_scores = await self.ppr.rank(
            seed_ids, top_k=top_k * 3, max_iterations=5
        )
        merged = self._merge_with_expansion(seeds, expanded_scores)

        ranked = await self.reranker.rerank(query, merged, top_k=top_k)
        self._fire_learner(query, ranked)
        return MeshRetrievalResult(
            chunks=ranked,
            expanded=True,
            complexity="moderate",
            nodes_explored=len(expanded_scores),
        )

    async def _full_retrieve(self, query: str, top_k: int) -> MeshRetrievalResult:
        """Full pipeline: hybrid + anchor check + PPR + rerank. Issue #2058."""
        seeds = await self.hybrid_search(query, top_k * 2)
        seed_ids = [self._chunk_id(r) for r in seeds[:5]]

        anchors = await self._find_anchors(seed_ids)
        anchor_used = bool(anchors)
        if anchor_used:
            seed_ids = list(set(seed_ids + anchors))

        expanded_scores = await self.ppr.rank(seed_ids, top_k=top_k * 4)
        merged = self._merge_with_expansion(seeds, expanded_scores)

        ranked = await self.reranker.rerank(query, merged, top_k=top_k)
        self._fire_learner(query, ranked)
        return MeshRetrievalResult(
            chunks=ranked,
            expanded=True,
            complexity="complex",
            anchor_used=anchor_used,
            nodes_explored=len(expanded_scores),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _find_anchors(self, seed_ids: list[str]) -> list[str]:
        """Look up anchor nodes adjacent to seed IDs via mesh_db.

        Delegates to mesh_db.get_anchor_neighbors() so the Protocol
        implementation decides what constitutes an anchor node.

        Args:
            seed_ids: List of chunk/node IDs to search around.

        Returns:
            List of anchor node IDs (may be empty).
        """
        try:
            return await self.mesh_db.get_anchor_neighbors(seed_ids)
        except Exception:
            logger.exception("_find_anchors failed; proceeding without anchors")
            return []

    def _merge_with_expansion(
        self,
        seeds: list,
        expanded_scores: list[tuple[str, float]],
    ) -> list:
        """Merge seed results with PPR-expanded node score map.

        Seed results already present are score-boosted by their PPR rank.
        Expanded nodes not in seeds are appended as synthetic result dicts
        so that the reranker can consider them.

        Args:
            seeds:           Original search results (dicts or SearchResult).
            expanded_scores: [(node_id, ppr_score), ...] from ppr.rank().

        Returns:
            Combined list of result dicts for the reranker.
        """
        score_map = dict(expanded_scores)
        merged: list = []
        seen_ids: set[str] = set()

        for r in seeds:
            cid = self._chunk_id(r)
            seen_ids.add(cid)
            merged.append(self._as_dict(r, ppr_boost=score_map.get(cid, 0.0)))

        for node_id, ppr_score in expanded_scores:
            if node_id not in seen_ids:
                merged.append({"chunk_id": node_id, "score": ppr_score, "content": ""})

        return merged

    def _fire_learner(self, query: str, results: list) -> None:
        """Schedule EdgeLearner.on_retrieval as a background asyncio task.

        Non-blocking: failures are logged but do not affect the caller.

        Args:
            query:   Original query text for feedback attribution.
            results: Ranked result list (top-5 IDs are recorded).
        """
        event = {
            "query_text": query,
            "final_ranked_ids": [self._chunk_id(r) for r in results[:5]],
            "timestamp": str(time.time()),
        }
        asyncio.create_task(self._run_learner(event))

    async def _run_learner(self, event: dict) -> None:
        """Await EdgeLearner.on_retrieval and swallow exceptions. Issue #2058."""
        try:
            await self.edge_learner.on_retrieval(event)
        except Exception:
            logger.exception("EdgeLearner.on_retrieval raised an exception")

    def _chunk_id(self, result: Any) -> str:
        """Extract chunk ID from a result dict or SearchResult-like object.

        Priority for dicts:   metadata.chunk_id -> chunk_id -> source_path -> ""
        Priority for objects: metadata.chunk_id -> source_path -> ""

        Args:
            result: A dict or object with metadata/source_path attributes.

        Returns:
            Chunk ID string, empty string on failure.
        """
        if isinstance(result, dict):
            return (
                result.get("metadata", {}).get("chunk_id")
                or result.get("chunk_id")
                or result.get("source_path", "")
            )
        meta = getattr(result, "metadata", {}) or {}
        return meta.get("chunk_id") or getattr(result, "source_path", "")

    @staticmethod
    def _as_dict(result: Any, ppr_boost: float = 0.0) -> dict:
        """Normalise a result to a dict, optionally applying a PPR score boost.

        Args:
            result:    A dict or SearchResult-like object.
            ppr_boost: PPR score from expansion; added to the base score.

        Returns:
            A dict suitable for the reranker.
        """
        if isinstance(result, dict):
            out = dict(result)
            out["score"] = out.get("score", 0.0) + ppr_boost
            return out
        base_score = getattr(result, "score", 0.0) or 0.0
        return {
            "chunk_id": getattr(result, "source_path", ""),
            "content": getattr(result, "content", ""),
            "score": base_score + ppr_boost,
            "metadata": getattr(result, "metadata", {}),
            "source_path": getattr(result, "source_path", ""),
        }
