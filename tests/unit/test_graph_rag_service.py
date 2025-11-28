#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

import pytest
from unittest.mock import AsyncMock, Mock

from src.advanced_rag_optimizer import SearchResult, RAGMetrics
from src.services.graph_rag_service import (
    GraphRAGService,
    GraphRAGMetrics,
    EntityMatch,
)


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


def test_graph_rag_service_initialization(mock_rag_service, mock_memory_graph):
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
async def test_graph_aware_search_basic(graph_rag_service, mock_rag_service):
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
async def test_graph_aware_search_with_entity_expansion(
    graph_rag_service, mock_rag_service, mock_memory_graph
):
    """Test graph expansion adds related entity content."""
    results, metrics = await graph_rag_service.graph_aware_search(
        query="Redis issues",
        start_entity="Redis Config",
        max_depth=2,
        max_results=5,
    )

    # Verify graph traversal was called
    mock_memory_graph.get_related_entities.assert_called_once()

    # Verify graph metrics
    assert metrics.graph_expansion_enabled is True
    assert metrics.graph_traversal_time > 0
    assert metrics.entities_explored >= 0


@pytest.mark.asyncio
async def test_graph_aware_search_no_expansion_without_entities(
    graph_rag_service, mock_rag_service, mock_memory_graph
):
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
async def test_graph_aware_search_timeout_handling(
    graph_rag_service, mock_rag_service
):
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
async def test_extract_entities_from_results(graph_rag_service, mock_memory_graph):
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

    entity_matches = await graph_rag_service._extract_entities_from_results(
        rag_results
    )

    # Verify graph was queried
    assert mock_memory_graph.get_entity.call_count >= 1

    # Verify entity matches structure
    assert len(entity_matches) > 0
    assert isinstance(entity_matches[0], EntityMatch)
    assert entity_matches[0].relevance_score >= 0.5  # High relevance for first result


@pytest.mark.asyncio
async def test_extract_entities_handles_missing_entities(
    graph_rag_service, mock_memory_graph
):
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

    entity_matches = await graph_rag_service._extract_entities_from_results(
        rag_results
    )

    # Verify no matches for missing entity
    assert len(entity_matches) == 0


# ============================================================================
# Graph Expansion Tests
# ============================================================================


@pytest.mark.asyncio
async def test_expand_via_graph(graph_rag_service, mock_memory_graph):
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
async def test_expand_via_graph_multiple_starting_points(
    graph_rag_service, mock_memory_graph
):
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

    expanded = await graph_rag_service._expand_via_graph(
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
async def test_deduplicate_and_rank(graph_rag_service):
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

    deduplicated = await graph_rag_service._deduplicate_and_rank(
        results, max_results=10
    )

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
async def test_deduplicate_and_rank_respects_max_results(graph_rag_service):
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

    deduplicated = await graph_rag_service._deduplicate_and_rank(
        results, max_results=3
    )

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
async def test_end_to_end_composition(graph_rag_service, mock_rag_service, mock_memory_graph):
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
async def test_get_metrics(graph_rag_service):
    """Test service metrics reporting."""
    metrics = await graph_rag_service.get_metrics()

    # Verify metrics structure
    assert metrics["service"] == "GraphRAGService"
    assert "graph_weight" in metrics
    assert "entity_extraction_enabled" in metrics
    assert "graph_initialized" in metrics
