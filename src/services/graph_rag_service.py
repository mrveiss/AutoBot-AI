#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Graph-RAG Service - Reusable service combining graph traversal with RAG retrieval.

This service implements graph-aware retrieval by composing existing RAGService
and AutoBotMemoryGraph components. It enhances standard RAG search with
relationship-based context expansion.

Architecture:
- Composes RAGService (reuses all RAG logic)
- Composes AutoBotMemoryGraph (reuses all graph logic)
- Adds graph-aware retrieval strategy
- Zero code duplication - pure composition pattern

Key Features:
- Graph relationship traversal for context expansion
- Entity-aware retrieval using graph structure
- Relationship strength weighting
- Hybrid scoring (RAG relevance + graph proximity)
- Result deduplication and ranking
- Performance metrics tracking

Usage:
    from backend.services.rag_service import RAGService
    from src.autobot_memory_graph import AutoBotMemoryGraph
    from src.services.graph_rag_service import GraphRAGService

    # Initialize dependencies
    rag_service = RAGService(knowledge_base)
    await rag_service.initialize()

    memory_graph = AutoBotMemoryGraph()
    await memory_graph.initialize()

    # Create graph-RAG service via composition
    graph_rag = GraphRAGService(rag_service, memory_graph)

    # Use graph-aware search
    results, metrics = await graph_rag.graph_aware_search(
        query="Redis configuration issues",
        start_entity="Conversation ABC123",
        max_depth=2,
        max_results=5
    )
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.services.rag_service import RAGService
from src.advanced_rag_optimizer import RAGMetrics, SearchResult
from src.autobot_memory_graph import AutoBotMemoryGraph
from src.utils.error_boundaries import error_boundary
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("graph_rag_service")


@dataclass
class GraphRAGMetrics(RAGMetrics):
    """
    Extended metrics for graph-RAG operations.

    Inherits all standard RAG metrics and adds graph-specific tracking.
    """

    graph_traversal_time: float = 0.0
    entities_explored: int = 0
    relationships_traversed: int = 0
    graph_expansion_enabled: bool = False
    graph_results_added: int = 0

    # === Issue #372: Feature Envy Reduction Methods ===

    def copy_from_rag_metrics(self, rag_metrics: "RAGMetrics") -> None:
        """Copy base metrics from RAG search (Issue #372 - reduces feature envy)."""
        self.query_processing_time = rag_metrics.query_processing_time
        self.retrieval_time = rag_metrics.retrieval_time
        self.reranking_time = rag_metrics.reranking_time
        self.documents_considered = rag_metrics.documents_considered
        self.hybrid_search_enabled = rag_metrics.hybrid_search_enabled

    def record_graph_results(
        self, graph_traversal_time: float, results_added: int
    ) -> None:
        """Record graph expansion results (Issue #372 - reduces feature envy)."""
        self.graph_expansion_enabled = True
        self.graph_traversal_time = graph_traversal_time
        self.graph_results_added = results_added

    def finalize(self, final_count: int, total_time: float) -> None:
        """Finalize metrics with final counts (Issue #372 - reduces feature envy)."""
        self.final_results_count = final_count
        self.total_time = total_time

    def get_timing_summary(self) -> str:
        """Get timing summary string (Issue #372 - reduces feature envy)."""
        return (
            f"{self.total_time:.3f}s total "
            f"(RAG: {self.retrieval_time:.3f}s, "
            f"Graph: {self.graph_traversal_time:.3f}s)"
        )

    def to_response_dict(self) -> Dict[str, Any]:
        """Convert metrics to API response dictionary (Issue #372 - reduces feature envy)."""
        return {
            "query_processing_time": self.query_processing_time,
            "retrieval_time": self.retrieval_time,
            "reranking_time": self.reranking_time,
            "graph_traversal_time": self.graph_traversal_time,
            "total_time": self.total_time,
            "documents_considered": self.documents_considered,
            "final_results_count": self.final_results_count,
            "entities_explored": self.entities_explored,
            "graph_expansion_enabled": self.graph_expansion_enabled,
            "graph_results_added": self.graph_results_added,
        }


@dataclass
class EntityMatch:
    """
    Represents an entity matched during graph traversal.

    Attributes:
        entity: Entity data from memory graph
        relevance_score: Score from initial RAG search (0.0-1.0)
        graph_distance: Distance from start entity (hops)
        relationship_path: List of relationships traversed to reach this entity
    """

    entity: Dict[str, Any]
    relevance_score: float
    graph_distance: int
    relationship_path: List[Dict[str, Any]] = field(default_factory=list)


class GraphRAGService:
    """
    Reusable service for graph-aware RAG retrieval.

    This service enhances standard RAG search by incorporating graph relationships.
    It follows the composition pattern, reusing existing RAGService and
    AutoBotMemoryGraph components without duplication.

    Graph-Aware Retrieval Strategy:
    1. Initial RAG search: Use RAGService for semantic retrieval (REUSE)
    2. Entity extraction: Identify entities mentioned in top results
    3. Graph expansion: Use memory_graph to find related entities (REUSE)
    4. Context gathering: Retrieve observations from related entities
    5. Result combination: Merge and deduplicate results
    6. Hybrid ranking: Score by RAG relevance + graph proximity
    7. Reranking: Apply cross-encoder reranking (REUSE from RAGService)
    """

    def __init__(
        self,
        rag_service: RAGService,
        memory_graph: AutoBotMemoryGraph,
        graph_weight: float = 0.3,
        enable_entity_extraction: bool = True,
    ):
        """
        Initialize Graph-RAG service via composition.

        Args:
            rag_service: Existing RAG service instance (dependency injection)
            memory_graph: Existing memory graph instance (dependency injection)
            graph_weight: Weight for graph proximity in hybrid scoring (0.0-1.0)
            enable_entity_extraction: Whether to extract entities from results

        Design Notes:
        - No inheritance - uses composition for maximum flexibility
        - Dependencies injected - easy to test with mocks
        - Configuration external - no hardcoded values
        """
        self.rag = rag_service
        self.graph = memory_graph
        self.graph_weight = graph_weight
        self.enable_entity_extraction = enable_entity_extraction

        # Result deduplication cache
        self._seen_content: Set[str] = set()

        logger.info(
            "GraphRAGService initialized (graph_weight=%s, entity_extraction=%s)",
            graph_weight,
            enable_entity_extraction,
        )

    @error_boundary(
        component="graph_rag_service",
        function="graph_aware_search",
    )
    async def graph_aware_search(
        self,
        query: str,
        start_entity: Optional[str] = None,
        max_depth: int = 2,
        max_results: int = 5,
        enable_reranking: bool = True,
        timeout: Optional[float] = None,
    ) -> Tuple[List[SearchResult], GraphRAGMetrics]:
        """
        Perform graph-aware RAG search with relationship-based expansion.

        Issue #281: Refactored to use extracted helpers.

        Args:
            query: Search query string
            start_entity: Optional starting entity name for graph traversal
            max_depth: Maximum graph traversal depth (1-3)
            max_results: Maximum number of results to return
            enable_reranking: Whether to apply cross-encoder reranking
            timeout: Optional timeout in seconds

        Returns:
            Tuple of (search_results, metrics)
        """
        start_time = time.perf_counter()
        metrics = GraphRAGMetrics()

        try:
            self._seen_content.clear()

            # Step 1: Initial RAG search
            rag_results = await self._perform_initial_rag_search(
                query, max_results, enable_reranking, timeout, metrics
            )

            # Step 2-3: Extract entities and expand via graph
            all_results = await self._extract_and_expand_graph(
                query, rag_results, start_entity, max_depth, max_results, metrics
            )

            # Step 4: Deduplicate and rank
            final_results = await self._deduplicate_and_rank(all_results, max_results)
            metrics.finalize(len(final_results), time.perf_counter() - start_time)

            logger.info(
                "Graph-RAG search complete: %s results, %s",
                len(final_results),
                metrics.get_timing_summary(),
            )
            return final_results, metrics

        except asyncio.TimeoutError:
            logger.warning("Graph-RAG search timed out after %ss", timeout)
            metrics.total_time = time.perf_counter() - start_time
            return [], metrics

        except Exception as e:
            logger.error("Graph-RAG search failed: %s", e, exc_info=True)
            metrics.total_time = time.perf_counter() - start_time
            return [], metrics

    async def _extract_entities_from_results(
        self, results: List[SearchResult]
    ) -> List[EntityMatch]:
        """
        Extract entity references from search results.

        Issue #281: Refactored to use extracted helpers.

        Args:
            results: Search results from RAG search

        Returns:
            List of EntityMatch objects with entity data and relevance scores
        """
        entity_matches = []

        for idx, result in enumerate(results):
            relevance = 1.0 - (idx / len(results) * 0.5)  # 1.0 → 0.5
            entity_refs = self._collect_entity_refs_from_result(result)

            if entity_refs:
                matches = await self._query_and_build_matches(entity_refs, relevance)
                entity_matches.extend(matches)

        return entity_matches

    async def _expand_via_graph(
        self,
        query: str,
        start_entity: Optional[str],
        entity_matches: List[EntityMatch],
        max_depth: int,
        max_results: int,
    ) -> List[SearchResult]:
        """
        Expand context using graph relationships.

        Issue #281: Refactored to use extracted helpers.

        Args:
            query: Original search query (for relevance filtering)
            start_entity: Optional starting entity name
            entity_matches: Entities extracted from RAG results
            max_depth: Maximum traversal depth
            max_results: Maximum results to return

        Returns:
            List of SearchResult objects from graph expansion
        """
        start_points = self._get_graph_starting_points(start_entity, entity_matches)

        logger.info(
            "Graph expansion from %s starting points (max_depth=%s)",
            len(start_points),
            max_depth,
        )

        all_related_results = await self._fetch_related_entities_parallel(
            start_points, max_depth
        )

        expanded_results = self._process_graph_traversal_results(
            start_points, all_related_results, max_depth
        )

        logger.info("Graph expansion yielded %s results", len(expanded_results))
        return expanded_results[:max_results]

    async def _fetch_related_entities_parallel(
        self,
        start_points: List[Tuple[str, float]],
        max_depth: int,
    ) -> List[Any]:
        """
        Fetch related entities from graph in parallel.

        Args:
            start_points: List of (entity_name, base_score) tuples.
            max_depth: Maximum traversal depth.

        Returns:
            List of results or exceptions from parallel traversal.

        Issue #620.
        """
        return await asyncio.gather(
            *[
                self.graph.get_related_entities(
                    entity_name=entity_name,
                    relation_type=None,
                    direction="both",
                    max_depth=max_depth,
                )
                for entity_name, _ in start_points
            ],
            return_exceptions=True,
        )

    def _process_graph_traversal_results(
        self,
        start_points: List[Tuple[str, float]],
        all_related_results: List[Any],
        max_depth: int,
    ) -> List[SearchResult]:
        """
        Process graph traversal results into SearchResult objects.

        Args:
            start_points: List of (entity_name, base_score) tuples.
            all_related_results: Results from parallel graph traversal.
            max_depth: Maximum traversal depth for scoring.

        Returns:
            List of SearchResult objects from expanded entities.

        Issue #620.
        """
        expanded_results = []

        for (entity_name, base_score), related in zip(
            start_points, all_related_results
        ):
            if isinstance(related, Exception):
                logger.warning(
                    "Graph traversal failed for '%s': %s", entity_name, related
                )
                continue

            logger.debug(
                "Found %s related entities for '%s'", len(related), entity_name
            )

            for item in related:
                result = self._create_search_result_from_entity(
                    item["entity"],
                    item["relation"],
                    item["direction"],
                    base_score,
                    max_depth,
                )
                if result:
                    expanded_results.append(result)

        return expanded_results

    async def _deduplicate_and_rank(
        self, results: List[SearchResult], max_results: int
    ) -> List[SearchResult]:
        """
        Deduplicate results and rank by hybrid score.

        This method removes duplicate content and ranks results by their
        combined RAG relevance + graph proximity scores.

        Args:
            results: Combined results from RAG + graph expansion
            max_results: Maximum results to return

        Returns:
            Deduplicated and ranked results

        Strategy:
            1. Hash content for deduplication
            2. Keep highest-scored version of duplicates
            3. Sort by hybrid_score descending
            4. Assign relevance_rank
            5. Return top N results
        """
        deduplicated = []
        content_hashes: Dict[str, SearchResult] = {}

        for result in results:
            # Create content hash for deduplication
            content_hash = hash(result.content[:500])  # First 500 chars

            if content_hash in content_hashes:
                # Keep higher-scored version
                existing = content_hashes[content_hash]
                if result.hybrid_score > existing.hybrid_score:
                    content_hashes[content_hash] = result
            else:
                content_hashes[content_hash] = result

        # Convert to list and sort by hybrid score
        deduplicated = list(content_hashes.values())
        deduplicated.sort(key=lambda x: x.hybrid_score, reverse=True)

        # Assign relevance ranks
        for idx, result in enumerate(deduplicated[:max_results]):
            result.relevance_rank = idx + 1

        logger.info(
            "Deduplication: %s → %s → %s results",
            len(results),
            len(deduplicated),
            min(len(deduplicated), max_results),
        )

        return deduplicated[:max_results]

    # === Issue #281: Extracted Helper Methods ===

    async def _perform_initial_rag_search(
        self,
        query: str,
        max_results: int,
        enable_reranking: bool,
        timeout: Optional[float],
        metrics: GraphRAGMetrics,
    ) -> List[SearchResult]:
        """
        Perform initial RAG search and update metrics.

        Issue #281: Extracted from graph_aware_search.
        """
        logger.info("Graph-RAG search: '%s...'", query[:50])

        rag_results, rag_metrics = await self.rag.advanced_search(
            query=query,
            max_results=max_results * 2,  # Get more for filtering
            enable_reranking=enable_reranking,
            timeout=timeout,
        )

        metrics.copy_from_rag_metrics(rag_metrics)
        logger.info(
            "Initial RAG search: %s results in %.3fs",
            len(rag_results),
            rag_metrics.total_time,
        )
        return rag_results

    async def _extract_and_expand_graph(
        self,
        query: str,
        rag_results: List[SearchResult],
        start_entity: Optional[str],
        max_depth: int,
        max_results: int,
        metrics: GraphRAGMetrics,
    ) -> List[SearchResult]:
        """
        Extract entities and expand via graph traversal.

        Issue #281: Extracted from graph_aware_search.
        Returns combined RAG + graph results.
        """
        graph_start = time.perf_counter()
        entity_matches: List[EntityMatch] = []

        if self.enable_entity_extraction:
            entity_matches = await self._extract_entities_from_results(
                rag_results[:5]  # Only top 5 for entity extraction
            )
            logger.info("Extracted %s entity matches", len(entity_matches))

        if start_entity or entity_matches:
            expanded_results = await self._expand_via_graph(
                query=query,
                start_entity=start_entity,
                entity_matches=entity_matches,
                max_depth=max_depth,
                max_results=max_results,
            )

            graph_traversal_time = time.perf_counter() - graph_start
            metrics.record_graph_results(graph_traversal_time, len(expanded_results))
            logger.info("Graph expansion added %s results", len(expanded_results))

            return rag_results + expanded_results

        metrics.graph_traversal_time = time.perf_counter() - graph_start
        logger.info("No graph expansion (no start entity or matches)")
        return rag_results

    def _collect_entity_refs_from_result(self, result: SearchResult) -> List[str]:
        """
        Collect entity references from a single search result.

        Issue #281: Extracted from _extract_entities_from_results.
        """
        metadata = result.metadata or {}
        entity_refs = list(metadata.get("entities", []))

        if "session_id" in metadata:
            entity_refs.append(f"Conversation {metadata['session_id'][:8]}")

        return entity_refs

    async def _query_and_build_matches(
        self,
        entity_refs: List[str],
        relevance: float,
    ) -> List[EntityMatch]:
        """
        Query graph for entities and build EntityMatch objects.

        Issue #281: Extracted from _extract_entities_from_results.
        """
        matches = []

        entities = await asyncio.gather(
            *[
                self.graph.get_entity(entity_name=entity_ref, include_relations=False)
                for entity_ref in entity_refs
            ],
            return_exceptions=True,
        )

        for entity_ref, entity in zip(entity_refs, entities):
            if isinstance(entity, Exception):
                logger.warning("Failed to query entity '%s': %s", entity_ref, entity)
                continue

            if entity:
                matches.append(
                    EntityMatch(
                        entity=entity,
                        relevance_score=relevance,
                        graph_distance=0,
                        relationship_path=[],
                    )
                )
                logger.debug(
                    "Matched entity: %s (relevance=%.2f)", entity_ref, relevance
                )

        return matches

    def _get_graph_starting_points(
        self,
        start_entity: Optional[str],
        entity_matches: List[EntityMatch],
    ) -> List[Tuple[str, float]]:
        """
        Determine starting points for graph traversal.

        Issue #281: Extracted from _expand_via_graph.
        """
        start_points = []
        if start_entity:
            start_points.append((start_entity, 1.0))

        for match in entity_matches[:3]:  # Limit to top 3
            entity_name = match.entity.get("name")
            if entity_name:
                start_points.append((entity_name, match.relevance_score))

        return start_points

    def _create_search_result_from_entity(
        self,
        related_entity: Dict[str, Any],
        relation: Dict[str, Any],
        direction: str,
        base_score: float,
        max_depth: int,
    ) -> Optional[SearchResult]:
        """
        Create SearchResult from a related graph entity.

        Issue #281: Extracted from _expand_via_graph.
        """
        observations = related_entity.get("observations", [])
        if not observations:
            return None

        content = "\n".join(observations)

        relationship_strength = relation.get("metadata", {}).get("strength", 1.0)
        proximity_score = base_score * relationship_strength

        hybrid_score = (
            1.0 - self.graph_weight
        ) * base_score + self.graph_weight * proximity_score

        return SearchResult(
            content=content,
            metadata={
                "entity_id": related_entity.get("id"),
                "entity_type": related_entity.get("type"),
                "entity_name": related_entity.get("name"),
                "source": "graph_expansion",
                "relation_type": relation.get("type"),
                "direction": direction,
                "graph_distance": max_depth,
            },
            semantic_score=0.0,
            keyword_score=0.0,
            hybrid_score=hybrid_score,
            relevance_rank=0,
            source_path=f"graph:{related_entity.get('name', 'unknown')}",
            chunk_index=0,
        )

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Get service health and performance metrics.

        Returns:
            Dictionary with service metrics including RAG and graph statistics
        """
        rag_stats = (
            await self.rag.get_metrics() if hasattr(self.rag, "get_metrics") else {}
        )

        return {
            "service": "GraphRAGService",
            "graph_weight": self.graph_weight,
            "entity_extraction_enabled": self.enable_entity_extraction,
            "rag_service": rag_stats,
            "graph_initialized": self.graph.initialized,
        }
