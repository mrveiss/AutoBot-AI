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
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.services.rag_service import RAGService
from src.advanced_rag_optimizer import RAGMetrics, SearchResult
from src.autobot_memory_graph import AutoBotMemoryGraph
from src.utils.error_boundaries import ErrorCategory, error_boundary
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
            f"GraphRAGService initialized (graph_weight={graph_weight}, "
            f"entity_extraction={enable_entity_extraction})"
        )

    @error_boundary(
        component="graph_rag_service",
        function="graph_aware_search",
        category=ErrorCategory.SERVER_ERROR,
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

        This method combines semantic search with graph traversal to provide
        context-enhanced results. It reuses existing RAG and graph components.

        Args:
            query: Search query string
            start_entity: Optional starting entity name for graph traversal
            max_depth: Maximum graph traversal depth (1-3)
            max_results: Maximum number of results to return
            enable_reranking: Whether to apply cross-encoder reranking
            timeout: Optional timeout in seconds

        Returns:
            Tuple of (search_results, metrics)

        Strategy:
            1. RAG search: Use self.rag.advanced_search() (REUSE)
            2. Entity extraction: Parse entities from top results
            3. Graph expansion: Use self.graph.get_related_entities() (REUSE)
            4. Context gathering: Retrieve observations from graph
            5. Result merging: Combine RAG + graph results
            6. Hybrid scoring: Weight by relevance + proximity
            7. Deduplication: Remove duplicate content
            8. Final ranking: Sort by hybrid score

        Example:
            >>> results, metrics = await graph_rag.graph_aware_search(
            ...     query="Redis timeout issues",
            ...     start_entity="Bug Fix 2024-01-15",
            ...     max_depth=2,
            ...     max_results=5
            ... )
            >>> print(f"Found {len(results)} results in {metrics.total_time:.2f}s")
            Found 5 results in 0.87s
        """
        start_time = time.perf_counter()
        metrics = GraphRAGMetrics()

        try:
            # Clear deduplication cache for new search
            self._seen_content.clear()

            # Step 1: Initial RAG search (REUSE existing RAGService)
            logger.info(f"Graph-RAG search: '{query[:50]}...' (max_depth={max_depth})")

            rag_results, rag_metrics = await self.rag.advanced_search(
                query=query,
                max_results=max_results * 2,  # Get more for filtering
                enable_reranking=enable_reranking,
                timeout=timeout,
            )

            # Copy RAG metrics to extended metrics
            metrics.query_processing_time = rag_metrics.query_processing_time
            metrics.retrieval_time = rag_metrics.retrieval_time
            metrics.reranking_time = rag_metrics.reranking_time
            metrics.documents_considered = rag_metrics.documents_considered
            metrics.hybrid_search_enabled = rag_metrics.hybrid_search_enabled

            logger.info(
                f"Initial RAG search: {len(rag_results)} results in {rag_metrics.total_time:.3f}s"
            )

            # Step 2: Extract entities from top results (if enabled)
            graph_start = time.perf_counter()
            entity_matches: List[EntityMatch] = []

            if self.enable_entity_extraction:
                entity_matches = await self._extract_entities_from_results(
                    rag_results[:5]  # Only top 5 for entity extraction
                )
                logger.info(f"Extracted {len(entity_matches)} entity matches")

            # Step 3: Graph expansion from start_entity or extracted entities
            if start_entity or entity_matches:
                expanded_results = await self._expand_via_graph(
                    query=query,
                    start_entity=start_entity,
                    entity_matches=entity_matches,
                    max_depth=max_depth,
                    max_results=max_results,
                )

                metrics.graph_expansion_enabled = True
                metrics.graph_results_added = len(expanded_results)
                logger.info(f"Graph expansion added {len(expanded_results)} results")

                # Merge with RAG results
                all_results = rag_results + expanded_results
            else:
                # No graph expansion - use RAG results only
                all_results = rag_results
                logger.info("No graph expansion (no start entity or matches)")

            metrics.graph_traversal_time = time.perf_counter() - graph_start

            # Step 4: Deduplicate and rank by hybrid score
            final_results = await self._deduplicate_and_rank(
                all_results, max_results=max_results
            )

            metrics.final_results_count = len(final_results)
            metrics.total_time = time.perf_counter() - start_time

            logger.info(
                f"Graph-RAG search complete: {len(final_results)} results, "
                f"{metrics.total_time:.3f}s total "
                f"(RAG: {metrics.retrieval_time:.3f}s, "
                f"Graph: {metrics.graph_traversal_time:.3f}s)"
            )

            return final_results, metrics

        except asyncio.TimeoutError:
            logger.warning(f"Graph-RAG search timed out after {timeout}s")
            metrics.total_time = time.perf_counter() - start_time
            return [], metrics

        except Exception as e:
            logger.error(f"Graph-RAG search failed: {e}", exc_info=True)
            metrics.total_time = time.perf_counter() - start_time
            return [], metrics

    async def _extract_entities_from_results(
        self, results: List[SearchResult]
    ) -> List[EntityMatch]:
        """
        Extract entity references from search results.

        This method analyzes result metadata to identify entities referenced
        in the content. It queries the memory graph to find matching entities.

        Args:
            results: Search results from RAG search

        Returns:
            List of EntityMatch objects with entity data and relevance scores

        Strategy:
            - Parse metadata for entity references
            - Query memory graph for each entity name
            - Calculate relevance score from RAG search position
        """
        entity_matches = []

        for idx, result in enumerate(results):
            # Calculate relevance score (higher for earlier results)
            relevance = 1.0 - (idx / len(results) * 0.5)  # 1.0 → 0.5

            # Check metadata for entity references
            metadata = result.metadata or {}
            entity_refs = metadata.get("entities", [])

            # Also check for session_id (conversation entities)
            if "session_id" in metadata:
                entity_refs.append(f"Conversation {metadata['session_id'][:8]}")

            # Query graph for each entity reference
            for entity_ref in entity_refs:
                try:
                    entity = await self.graph.get_entity(
                        entity_name=entity_ref, include_relations=False
                    )

                    if entity:
                        entity_matches.append(
                            EntityMatch(
                                entity=entity,
                                relevance_score=relevance,
                                graph_distance=0,  # Direct match
                                relationship_path=[],
                            )
                        )
                        logger.debug(
                            f"Matched entity: {entity_ref} (relevance={relevance:.2f})"
                        )

                except Exception as e:
                    logger.warning(f"Failed to query entity '{entity_ref}': {e}")
                    continue

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

        This method traverses the graph from a start entity or extracted entities,
        following relationships to find related content. It uses the existing
        memory_graph.get_related_entities() method (REUSE).

        Args:
            query: Original search query (for relevance filtering)
            start_entity: Optional starting entity name
            entity_matches: Entities extracted from RAG results
            max_depth: Maximum traversal depth
            max_results: Maximum results to return

        Returns:
            List of SearchResult objects from graph expansion

        Strategy:
            1. Determine starting points (start_entity or entity_matches)
            2. Use memory_graph.get_related_entities() for traversal (REUSE)
            3. Extract observations from related entities
            4. Convert to SearchResult format
            5. Score by graph proximity + relationship strength
        """
        expanded_results = []

        # Determine starting points for traversal
        start_points = []
        if start_entity:
            start_points.append((start_entity, 1.0))  # (name, base_score)

        for match in entity_matches[:3]:  # Limit to top 3 entity matches
            entity_name = match.entity.get("name")
            if entity_name:
                start_points.append((entity_name, match.relevance_score))

        logger.info(
            f"Graph expansion from {len(start_points)} starting points (max_depth={max_depth})"
        )

        # Traverse graph from each starting point
        for entity_name, base_score in start_points:
            try:
                # Use existing graph traversal (REUSE)
                related = await self.graph.get_related_entities(
                    entity_name=entity_name,
                    relation_type=None,  # All relation types
                    direction="both",  # Bidirectional
                    max_depth=max_depth,
                )

                logger.debug(
                    f"Found {len(related)} related entities for '{entity_name}'"
                )

                # Convert related entities to SearchResult format
                for item in related:
                    related_entity = item["entity"]
                    relation = item["relation"]
                    direction = item["direction"]

                    # Calculate graph proximity score
                    # Closer entities (fewer hops) get higher scores
                    # Relationship strength also factors in
                    relationship_strength = relation.get("metadata", {}).get(
                        "strength", 1.0
                    )
                    proximity_score = base_score * relationship_strength

                    # Create SearchResult from entity observations
                    observations = related_entity.get("observations", [])
                    if observations:
                        content = "\n".join(observations)

                        # Calculate hybrid score (base relevance + graph proximity)
                        hybrid_score = (
                            (1.0 - self.graph_weight) * base_score
                            + self.graph_weight * proximity_score
                        )

                        result = SearchResult(
                            content=content,
                            metadata={
                                "entity_id": related_entity.get("id"),
                                "entity_type": related_entity.get("type"),
                                "entity_name": related_entity.get("name"),
                                "source": "graph_expansion",
                                "relation_type": relation.get("type"),
                                "direction": direction,
                                "graph_distance": max_depth,  # Approximation
                            },
                            semantic_score=0.0,  # Not from semantic search
                            keyword_score=0.0,  # Not from keyword search
                            hybrid_score=hybrid_score,
                            relevance_rank=0,  # Will be set later
                            source_path=f"graph:{related_entity.get('name', 'unknown')}",
                            chunk_index=0,
                        )

                        expanded_results.append(result)

            except Exception as e:
                logger.warning(f"Graph traversal failed for '{entity_name}': {e}")
                continue

        logger.info(f"Graph expansion yielded {len(expanded_results)} results")
        return expanded_results[:max_results]

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
            f"Deduplication: {len(results)} → {len(deduplicated)} → {min(len(deduplicated), max_results)} results"
        )

        return deduplicated[:max_results]

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Get service health and performance metrics.

        Returns:
            Dictionary with service metrics including RAG and graph statistics
        """
        rag_stats = await self.rag.get_metrics() if hasattr(self.rag, "get_metrics") else {}

        return {
            "service": "GraphRAGService",
            "graph_weight": self.graph_weight,
            "entity_extraction_enabled": self.enable_entity_extraction,
            "rag_service": rag_stats,
            "graph_initialized": self.graph.initialized,
        }
