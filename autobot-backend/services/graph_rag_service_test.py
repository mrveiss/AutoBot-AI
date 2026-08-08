#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit Tests for GraphRAGService

Tests the graph-RAG integration using mocked dependencies to verify:
- Composition pattern (no duplication)
- Proper delegation to RAGService and AutoBotMemoryGraph
- Hybrid scoring algorithm
- Entity extraction logic
- Graph expansion strategy
- Deduplication and ranking

Test Strategy:
- Mock all external dependencies (RAGService, AutoBotMemoryGraph)
- Test each method in isolation
- Verify correct delegation to composed services
- Test edge cases and error handling
"""

from unittest.mock import AsyncMock, Mock

import pytest

from advanced_rag_optimizer import RAGMetrics, SearchResult
from services.graph_rag_service import EntityMatch, GraphRAGMetrics, GraphRAGService

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_rag_service():
    """Mock RAGService for isolated testing."""
    rag = Mock()
    rag.advanced_search = AsyncMock(
        return_value=(
            [
                SearchResult(
                    content="Redis timeout configuration guide",
                    metadata={"session_id": "abc123", "entities": ["Redis Config"]},
                    semantic_score=0.95,
                    keyword_score=0.85,
                    hybrid_score=0.90,
                    relevance_rank=1,
                    source_path="docs/redis.md",
                    chunk_index=0,
                ),
                SearchResult(
                    content="Redis connection pooling best practices",
                    metadata={"session_id": "def456"},
                    semantic_score=0.88,
                    keyword_score=0.75,
                    hybrid_score=0.82,
                    relevance_rank=2,
                    source_path="docs/redis-pool.md",
                    chunk_index=0,
                ),
            ],
            RAGMetrics(
                query_processing_time=0.05,
                retrieval_time=0.15,
                reranking_time=0.10,
                total_time=0.30,
                documents_considered=20,
                final_results_count=2,
            ),
        )
    )
    # get_metrics is awaited by GraphRAGService.get_metrics(); must be AsyncMock
    rag.get_metrics = AsyncMock(return_value={"searches": 0})
    return rag


@pytest.fixture
def mock_memory_graph():
    """Mock AutoBotMemoryGraph for isolated testing."""
    graph = Mock()
    graph.initialized = True

    # Mock get_entity
    graph.get_entity = AsyncMock(
        return_value={
            "id": "entity-123",
            "type": "decision",
            "name": "Redis Config",
            "created_at": 1700000000000,
            "updated_at": 1700000000000,
            "observations": [
                "Configured Redis timeout to 30s",
                "Set max connections to 100",
            ],
            "metadata": {"priority": "high"},
        }
    )

    # Mock get_related_entities
    graph.get_related_entities = AsyncMock(
        return_value=[
            {
                "entity": {
                    "id": "related-456",
                    "type": "bug_fix",
                    "name": "Redis Timeout Bug",
                    "observations": [
                        "Fixed timeout issue in connection pool",
                        "Added retry logic",
                    ],
                    "metadata": {},
                },
                "relation": {"type": "fixes", "metadata": {"strength": 0.9}},
                "direction": "outgoing",
            }
        ]
    )

    return graph


@pytest.fixture
def graph_rag_service(mock_rag_service, mock_memory_graph):
    """Create GraphRAGService with mocked dependencies."""
    return GraphRAGService(
        rag_service=mock_rag_service,
        memory_graph=mock_memory_graph,
        graph_weight=0.3,
        enable_entity_extraction=True,
    )


# ============================================================================
# Initialization Tests
# ============================================================================


def test_graph_rag_service_initialization(mock_rag_service, mock_memory_graph) -> None:
    """Test GraphRAGService initialization with composition pattern."""
    service = GraphRAGService(
        rag_service=mock_rag_service,
        memory_graph=mock_memory_graph,
        graph_weight=0.4,
        enable_entity_extraction=False,
    )

    # Verify composition (dependencies stored, not inherited)
    assert service.rag is mock_rag_service
    assert service.graph is mock_memory_graph
    assert service.graph_weight == 0.4
    assert service.enable_entity_extraction is False


# ============================================================================
# Graph-Aware Search Tests
# ============================================================================


@pytest.mark.asyncio
async def test_graph_aware_search_basic(graph_rag_service, mock_rag_service) -> None:
    """Test basic graph-aware search delegates to RAGService."""
    results, metrics = await graph_rag_service.graph_aware_search(
        query="Redis configuration",
        max_results=5,
    )

    # Verify RAGService was called (composition, not duplication)
    mock_rag_service.advanced_search.assert_called_once_with(
        query="Redis configuration",
        max_results=10,  # 2x for filtering
        enable_reranking=True,
        timeout=None,
    )

    # Verify results returned
    assert len(results) > 0
    assert isinstance(results[0], SearchResult)

    # Verify metrics structure
    assert isinstance(metrics, GraphRAGMetrics)
    assert metrics.total_time > 0
    assert metrics.retrieval_time > 0  # Copied from RAG metrics


@pytest.mark.asyncio
async def test_graph_aware_search_with_entity_expansion(graph_rag_service, mock_rag_service, mock_memory_graph) -> None:
    """Test graph expansion adds related entity content."""
    results, metrics = await graph_rag_service.graph_aware_search(
        query="Redis issues",
        start_entity="Redis Config",
        max_depth=2,
        max_results=5,
    )

    # Issue #12389: start_entity="Redis Config" and every extracted entity
    # match also resolves to "Redis Config" (fixture returns a fixed entity),
    # so after starting-point dedup, get_related_entities is called exactly
    # once for the single distinct entity name.
    mock_memory_graph.get_related_entities.assert_called_once()
    assert mock_memory_graph.get_related_entities.call_args.kwargs["entity_name"] == "Redis Config"

    # Verify graph metrics
    assert metrics.graph_expansion_enabled is True
    assert metrics.graph_traversal_time > 0
    assert metrics.entities_explored >= 0


@pytest.mark.asyncio
async def test_graph_starting_points_dedup_by_entity_name(graph_rag_service, mock_memory_graph) -> None:
    """Issue #12389: duplicate entity names collapse to a single starting point.

    When start_entity coincides with an extracted entity, or the same entity
    is extracted from multiple result chunks, get_related_entities must be
    invoked at most once per distinct entity name.
    """
    entity_matches = [
        EntityMatch(
            entity={"name": "Redis Config", "id": "e1"},
            relevance_score=0.9,
            graph_distance=0,
            relationship_path=[],
        ),
        EntityMatch(
            entity={"name": "Redis Config", "id": "e1"},
            relevance_score=0.8,
            graph_distance=0,
            relationship_path=[],
        ),
        EntityMatch(
            entity={"name": "Other Entity", "id": "e2"},
            relevance_score=0.7,
            graph_distance=0,
            relationship_path=[],
        ),
    ]

    start_points = graph_rag_service._get_graph_starting_points(
        start_entity="Redis Config",
        entity_matches=entity_matches,
    )

    # "Redis Config" appears as start_entity + twice in entity_matches, but
    # must collapse to a single starting point (first occurrence wins).
    assert start_points == [("Redis Config", 1.0), ("Other Entity", 0.7)]

    await graph_rag_service._fetch_related_entities_parallel(start_points, max_depth=2)

    assert mock_memory_graph.get_related_entities.call_count == 2
    called_names = {call.kwargs["entity_name"] for call in mock_memory_graph.get_related_entities.call_args_list}
    assert called_names == {"Redis Config", "Other Entity"}


@pytest.mark.asyncio
async def test_graph_starting_points_dedup_is_case_insensitive(graph_rag_service) -> None:
    """Issue #12389: dedup keys on the case-folded name to match the downstream
    case-insensitive node resolution, so 'Redis Config' and 'redis config'
    collapse to a single starting point (no redundant traversal)."""
    entity_matches = [
        EntityMatch(
            entity={"name": "redis config", "id": "e1"},
            relevance_score=0.9,
            graph_distance=0,
            relationship_path=[],
        ),
        EntityMatch(
            entity={"name": "Other Entity", "id": "e2"},
            relevance_score=0.7,
            graph_distance=0,
            relationship_path=[],
        ),
    ]

    start_points = graph_rag_service._get_graph_starting_points(
        start_entity="Redis Config",
        entity_matches=entity_matches,
    )

    # "Redis Config" (start) and "redis config" (match) differ only in case →
    # collapse to one; the original-cased start_entity is kept.
    assert start_points == [("Redis Config", 1.0), ("Other Entity", 0.7)]


@pytest.mark.asyncio
async def test_graph_aware_search_no_expansion_without_entities(
    graph_rag_service, mock_rag_service, mock_memory_graph
) -> None:
    """Test search without entity expansion when no entities found."""
    # Mock empty entity extraction
    graph_rag_service.enable_entity_extraction = False

    results, metrics = await graph_rag_service.graph_aware_search(
        query="Redis issues",
        start_entity=None,  # No start entity
        max_depth=2,
        max_results=5,
    )

    # Verify graph traversal NOT called
    mock_memory_graph.get_related_entities.assert_not_called()

    # Verify no graph expansion
    assert metrics.graph_expansion_enabled is False
    assert metrics.graph_results_added == 0


@pytest.mark.asyncio
async def test_graph_aware_search_timeout_handling(graph_rag_service, mock_rag_service) -> None:
    """Test timeout handling delegates to RAGService."""
    # Mock timeout in RAG service
    import asyncio

    mock_rag_service.advanced_search.side_effect = asyncio.TimeoutError()

    results, metrics = await graph_rag_service.graph_aware_search(
        query="Redis issues",
        timeout=1.0,
    )

    # Verify graceful handling
    assert results == []
    assert metrics.total_time > 0


# ============================================================================
# Entity Extraction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_extract_entities_from_results(graph_rag_service, mock_memory_graph) -> None:
    """Test entity extraction from search results."""
    rag_results = [
        SearchResult(
            content="Redis config",
            metadata={"entities": ["Redis Config"], "session_id": "abc123"},
            semantic_score=0.9,
            keyword_score=0.8,
            hybrid_score=0.85,
            relevance_rank=1,
            source_path="test",
            chunk_index=0,
        )
    ]

    entity_matches = await graph_rag_service._extract_entities_from_results(rag_results)

    # Verify graph was queried
    assert mock_memory_graph.get_entity.call_count >= 1

    # Verify entity matches structure
    assert len(entity_matches) > 0
    assert isinstance(entity_matches[0], EntityMatch)
    assert entity_matches[0].relevance_score >= 0.5  # High relevance for first result


@pytest.mark.asyncio
async def test_extract_entities_handles_missing_entities(graph_rag_service, mock_memory_graph) -> None:
    """Test entity extraction handles missing entities gracefully."""
    # Mock entity not found
    mock_memory_graph.get_entity = AsyncMock(return_value=None)

    rag_results = [
        SearchResult(
            content="Test",
            metadata={"entities": ["Nonexistent Entity"]},
            semantic_score=0.9,
            keyword_score=0.8,
            hybrid_score=0.85,
            relevance_rank=1,
            source_path="test",
            chunk_index=0,
        )
    ]

    entity_matches = await graph_rag_service._extract_entities_from_results(rag_results)

    # Verify no matches for missing entity
    assert len(entity_matches) == 0


# ============================================================================
# Graph Expansion Tests
# ============================================================================


@pytest.mark.asyncio
async def test_expand_via_graph(graph_rag_service, mock_memory_graph) -> None:
    """Test graph expansion creates SearchResult objects from entities."""
    entity_matches = [
        EntityMatch(
            entity={
                "id": "test-123",
                "name": "Test Entity",
                "observations": ["Observation 1"],
            },
            relevance_score=0.9,
            graph_distance=1,
        )
    ]

    expanded = await graph_rag_service._expand_via_graph(
        query="test",
        start_entity=None,
        entity_matches=entity_matches,
        max_depth=2,
        max_results=5,
    )

    # Verify graph traversal called
    mock_memory_graph.get_related_entities.assert_called_once()

    # Verify SearchResult creation
    assert len(expanded) > 0
    assert isinstance(expanded[0], SearchResult)
    assert expanded[0].metadata["source"] == "graph_expansion"
    assert expanded[0].hybrid_score > 0  # Graph proximity score applied


@pytest.mark.asyncio
async def test_expand_via_graph_multiple_starting_points(graph_rag_service, mock_memory_graph) -> None:
    """Test graph expansion from multiple entity matches."""
    entity_matches = [
        EntityMatch(
            entity={"id": "e1", "name": "Entity 1", "observations": ["Obs 1"]},
            relevance_score=0.9,
            graph_distance=0,
        ),
        EntityMatch(
            entity={"id": "e2", "name": "Entity 2", "observations": ["Obs 2"]},
            relevance_score=0.8,
            graph_distance=0,
        ),
    ]

    _expanded = await graph_rag_service._expand_via_graph(
        query="test",
        start_entity=None,
        entity_matches=entity_matches,
        max_depth=2,
        max_results=10,
    )

    # Verify multiple traversals (one per entity, limited to top 3)
    assert mock_memory_graph.get_related_entities.call_count == 2


# ============================================================================
# Deduplication Tests
# ============================================================================


@pytest.mark.asyncio
async def test_deduplicate_and_rank(graph_rag_service) -> None:
    """Test deduplication removes duplicate content and ranks by score."""
    results = [
        SearchResult(
            content="Duplicate content here",
            metadata={},
            semantic_score=0.9,
            keyword_score=0.8,
            hybrid_score=0.85,
            relevance_rank=0,
            source_path="source1",
            chunk_index=0,
        ),
        SearchResult(
            content="Duplicate content here",  # Same content
            metadata={},
            semantic_score=0.7,
            keyword_score=0.6,
            hybrid_score=0.65,  # Lower score
            relevance_rank=0,
            source_path="source2",
            chunk_index=0,
        ),
        SearchResult(
            content="Unique content here",
            metadata={},
            semantic_score=0.95,
            keyword_score=0.9,
            hybrid_score=0.92,  # Highest score
            relevance_rank=0,
            source_path="source3",
            chunk_index=0,
        ),
    ]

    deduplicated = await graph_rag_service._deduplicate_and_rank(results, max_results=10)

    # Verify deduplication (3 → 2)
    assert len(deduplicated) == 2

    # Verify highest-scored version kept
    assert deduplicated[0].content == "Unique content here"  # Highest score first
    assert deduplicated[0].relevance_rank == 1

    # Verify duplicate with higher score kept
    duplicate_kept = [r for r in deduplicated if r.content.startswith("Duplicate")]
    assert len(duplicate_kept) == 1
    assert duplicate_kept[0].hybrid_score == 0.85  # Higher score version


@pytest.mark.asyncio
async def test_deduplicate_and_rank_respects_max_results(graph_rag_service) -> None:
    """Test deduplication respects max_results limit."""
    results = [
        SearchResult(
            content=f"Content {i}",
            metadata={},
            semantic_score=0.9 - i * 0.1,
            keyword_score=0.8,
            hybrid_score=0.85 - i * 0.1,
            relevance_rank=0,
            source_path=f"source{i}",
            chunk_index=0,
        )
        for i in range(10)
    ]

    deduplicated = await graph_rag_service._deduplicate_and_rank(results, max_results=3)

    # Verify max_results respected
    assert len(deduplicated) == 3

    # Verify top-scored results kept
    assert all(r.relevance_rank > 0 for r in deduplicated)
    assert deduplicated[0].relevance_rank == 1
    assert deduplicated[1].relevance_rank == 2
    assert deduplicated[2].relevance_rank == 3


# ============================================================================
# Integration Tests (With Real Behavior)
# ============================================================================


@pytest.mark.asyncio
async def test_end_to_end_composition(graph_rag_service, mock_rag_service, mock_memory_graph) -> None:
    """Test end-to-end flow verifies proper composition."""
    # Execute full search
    results, metrics = await graph_rag_service.graph_aware_search(
        query="Redis configuration",
        start_entity="Redis Config",
        max_depth=2,
        max_results=5,
    )

    # Verify RAGService called (composition)
    assert mock_rag_service.advanced_search.called

    # Verify AutoBotMemoryGraph called (composition)
    assert mock_memory_graph.get_entity.called or mock_memory_graph.get_related_entities.called

    # Verify results structure
    assert isinstance(results, list)
    assert isinstance(metrics, GraphRAGMetrics)
    assert metrics.total_time > 0


# ============================================================================
# Metrics Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_metrics(graph_rag_service) -> None:
    """Test service metrics reporting."""
    metrics = await graph_rag_service.get_metrics()

    # Verify metrics structure
    assert metrics["service"] == "GraphRAGService"
    assert "graph_weight" in metrics
    assert "entity_extraction_enabled" in metrics
    assert "graph_initialized" in metrics


# ============================================================================
# Source Provenance Tests
# ============================================================================


def test_create_search_result_includes_source_extracted() -> None:
    """source='extracted' propagates into metadata when relation has origin='extracted'."""
    rag = AsyncMock()
    graph = AsyncMock()
    graph.initialized = True
    svc = GraphRAGService(rag, graph)

    entity = {"id": "e1", "type": "module", "name": "auth", "observations": ["handles login"]}
    relation = {"type": "imports", "metadata": {"strength": 0.9, "origin": "extracted"}}

    result = svc._create_search_result_from_entity(entity, relation, "outgoing", 1.0, 2)

    assert result is not None
    assert result.metadata["source_provenance"] == "extracted"


def test_create_search_result_includes_source_inferred() -> None:
    """source='inferred' propagates when origin is absent (defaults to inferred)."""
    rag = AsyncMock()
    graph = AsyncMock()
    graph.initialized = True
    svc = GraphRAGService(rag, graph)

    entity = {"id": "e2", "type": "function", "name": "login", "observations": ["validates token"]}
    relation = {"type": "calls", "metadata": {"strength": 0.5}}

    result = svc._create_search_result_from_entity(entity, relation, "incoming", 0.8, 2)

    assert result is not None
    assert result.metadata["source_provenance"] == "inferred"


def test_create_search_result_includes_source_ambiguous() -> None:
    """source='ambiguous' passes through when origin='ambiguous'."""
    rag = AsyncMock()
    graph = AsyncMock()
    graph.initialized = True
    svc = GraphRAGService(rag, graph)

    entity = {"id": "e3", "type": "module", "name": "utils", "observations": ["helpers"]}
    relation = {"type": "related", "metadata": {"strength": 0.4, "origin": "ambiguous"}}

    result = svc._create_search_result_from_entity(entity, relation, "outgoing", 0.6, 2)

    assert result is not None
    assert result.metadata["source_provenance"] == "ambiguous"


def test_create_search_result_unknown_origin_defaults_to_inferred() -> None:
    """Unknown origin value falls back to 'inferred' via whitelist guard."""
    rag = AsyncMock()
    graph = AsyncMock()
    graph.initialized = True
    svc = GraphRAGService(rag, graph)

    entity = {"id": "e4", "type": "class", "name": "Config", "observations": ["settings"]}
    relation = {"type": "uses", "metadata": {"strength": 0.7, "origin": "garbage_value"}}

    result = svc._create_search_result_from_entity(entity, relation, "incoming", 0.9, 2)

    assert result is not None
    assert result.metadata["source_provenance"] == "inferred"


# ============================================================================
# Provenance Adjustment in _deduplicate_and_rank Tests (#4914)
# ============================================================================


@pytest.mark.asyncio
async def test_deduplicate_and_rank_applies_provenance_boost(graph_rag_service) -> None:
    """extracted > inferred after deduplication when base hybrid_score is equal."""
    base_score = 0.5
    extracted = SearchResult(
        content="Graph entity A",
        metadata={"source_provenance": "extracted"},
        semantic_score=0.0,
        keyword_score=0.0,
        hybrid_score=base_score,
        relevance_rank=0,
        source_path="graph:A",
        chunk_index=0,
    )
    inferred = SearchResult(
        content="Graph entity B",
        metadata={"source_provenance": "inferred"},
        semantic_score=0.0,
        keyword_score=0.0,
        hybrid_score=base_score,
        relevance_rank=0,
        source_path="graph:B",
        chunk_index=0,
    )

    ranked = await graph_rag_service._deduplicate_and_rank([extracted, inferred], max_results=10)

    # extracted receives +0.05 boost; inferred receives 0.0 adjustment
    assert ranked[0] is extracted
    assert ranked[0].hybrid_score > ranked[1].hybrid_score


@pytest.mark.asyncio
async def test_deduplicate_and_rank_applies_provenance_penalty(graph_rag_service) -> None:
    """inferred > ambiguous after deduplication when base hybrid_score is equal."""
    base_score = 0.5
    inferred = SearchResult(
        content="Graph entity C",
        metadata={"source_provenance": "inferred"},
        semantic_score=0.0,
        keyword_score=0.0,
        hybrid_score=base_score,
        relevance_rank=0,
        source_path="graph:C",
        chunk_index=0,
    )
    ambiguous = SearchResult(
        content="Graph entity D",
        metadata={"source_provenance": "ambiguous"},
        semantic_score=0.0,
        keyword_score=0.0,
        hybrid_score=base_score,
        relevance_rank=0,
        source_path="graph:D",
        chunk_index=0,
    )

    ranked = await graph_rag_service._deduplicate_and_rank([ambiguous, inferred], max_results=10)

    # inferred receives 0.0; ambiguous receives -0.05 penalty
    assert ranked[0] is inferred
    assert ranked[0].hybrid_score > ranked[1].hybrid_score


@pytest.mark.asyncio
async def test_deduplicate_and_rank_no_provenance_unchanged(graph_rag_service) -> None:
    """Results without source_provenance are not adjusted (0.0 delta, no mutation)."""
    result = SearchResult(
        content="Graph entity E",
        metadata={},
        semantic_score=0.0,
        keyword_score=0.0,
        hybrid_score=0.7,
        relevance_rank=0,
        source_path="graph:E",
        chunk_index=0,
    )

    ranked = await graph_rag_service._deduplicate_and_rank([result], max_results=10)

    assert len(ranked) == 1
    # No adjustment for missing provenance (0.0 delta skipped)
    assert ranked[0].hybrid_score == 0.7


@pytest.mark.asyncio
async def test_metadata_none_does_not_raise(graph_rag_service) -> None:
    """Result with metadata=None passes through _deduplicate_and_rank without AttributeError (#4939)."""
    result = SearchResult(
        content="Graph entity F",
        metadata=None,
        semantic_score=0.0,
        keyword_score=0.0,
        hybrid_score=0.5,
        relevance_rank=0,
        source_path="graph:F",
        chunk_index=0,
    )

    # Must not raise AttributeError
    ranked = await graph_rag_service._deduplicate_and_rank([result], max_results=10)

    assert len(ranked) == 1
    # No provenance adjustment applied when metadata is None
    assert ranked[0].hybrid_score == 0.5


@pytest.mark.asyncio
async def test_hybrid_score_clamped_at_1_0(graph_rag_service) -> None:
    """hybrid_score + provenance boost is clamped at 1.0 (#4943)."""
    result = SearchResult(
        content="Graph entity G",
        metadata={"source_provenance": "extracted"},
        semantic_score=0.0,
        keyword_score=0.0,
        hybrid_score=0.98,
        relevance_rank=0,
        source_path="graph:G",
        chunk_index=0,
    )

    ranked = await graph_rag_service._deduplicate_and_rank([result], max_results=10)

    assert len(ranked) == 1
    assert ranked[0].hybrid_score <= 1.0


@pytest.mark.asyncio
async def test_hybrid_score_clamped_at_0_0(graph_rag_service) -> None:
    """hybrid_score + provenance penalty is clamped at 0.0 (#4943)."""
    result = SearchResult(
        content="Graph entity H",
        metadata={"source_provenance": "ambiguous"},
        semantic_score=0.0,
        keyword_score=0.0,
        hybrid_score=0.02,
        relevance_rank=0,
        source_path="graph:H",
        chunk_index=0,
    )

    ranked = await graph_rag_service._deduplicate_and_rank([result], max_results=10)

    assert len(ranked) == 1
    assert ranked[0].hybrid_score >= 0.0


# ============================================================================
# find_connection_path — #13474 wiring of the shortest-path traversal
# ============================================================================


@pytest.mark.asyncio
async def test_find_connection_path_delegates_to_memory_graph(graph_rag_service, mock_memory_graph) -> None:
    """The service must not reimplement traversal — it forwards to find_path (#13474)."""
    mock_memory_graph.find_path = AsyncMock(
        return_value={
            "found": True,
            "reason": None,
            "missing_entities": [],
            "from_entity": {"id": "e1", "name": "Redis Config", "type": "decision"},
            "to_entity": {"id": "e2", "name": "Incident 7", "type": "incident"},
            "hops": 1,
            "path": [{"relation": "CAUSED", "direction": "outgoing"}],
            "query": {},
        }
    )

    result = await graph_rag_service.find_connection_path(
        from_entity="Redis Config",
        to_entity="Incident 7",
        relation="CAUSED",
        max_depth=4,
        direction="outgoing",
    )

    mock_memory_graph.find_path.assert_awaited_once_with(
        from_entity="Redis Config",
        to_entity="Incident 7",
        relation="CAUSED",
        max_depth=4,
        direction="outgoing",
    )
    assert result["found"] is True
    assert result["hops"] == 1


@pytest.mark.asyncio
async def test_find_connection_path_records_traversal_time(graph_rag_service, mock_memory_graph) -> None:
    mock_memory_graph.find_path = AsyncMock(
        return_value={"found": False, "reason": "no_path", "hops": 0, "path": [], "missing_entities": []}
    )

    result = await graph_rag_service.find_connection_path("A", "B")

    assert result["traversal_time"] >= 0.0
    assert result["found"] is False


@pytest.mark.asyncio
async def test_find_connection_path_defaults_to_undirected(graph_rag_service, mock_memory_graph) -> None:
    """ "How are these connected" is undirected by default (#13474)."""
    mock_memory_graph.find_path = AsyncMock(return_value={"found": True, "hops": 0, "path": []})

    await graph_rag_service.find_connection_path("A", "B")

    assert mock_memory_graph.find_path.await_args.kwargs["direction"] == "both"
    assert mock_memory_graph.find_path.await_args.kwargs["max_depth"] == 6


@pytest.mark.asyncio
async def test_find_connection_path_does_not_swallow_failures(graph_rag_service, mock_memory_graph) -> None:
    """A failed traversal must surface as an error, never as "no path" (#13474)."""
    mock_memory_graph.find_path = AsyncMock(side_effect=ConnectionError("redis down"))

    with pytest.raises(ConnectionError):
        await graph_rag_service.find_connection_path("A", "B")
