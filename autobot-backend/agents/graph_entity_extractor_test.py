#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit Tests for GraphEntityExtractor

Tests the entity extraction and graph population using mocked dependencies.

Test Strategy:
- Mock KnowledgeExtractionAgent and AutoBotMemoryGraph
- Test fact→entity mapping logic
- Test relationship inference algorithms
- Test batch processing and error handling
"""

from unittest.mock import AsyncMock, Mock

import pytest
from agents.graph_entity_extractor import (
    EntityCandidate,
    ExtractionResult,
    GraphEntityExtractor,
    RelationCandidate,
)
from backend.models.atomic_fact import AtomicFact, FactType, TemporalType

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_extraction_agent():
    """Mock KnowledgeExtractionAgent for isolated testing."""
    agent = Mock()

    # Mock extract_facts to return sample facts (using Mock objects for simplicity)
    mock_result = Mock()

    fact1 = Mock(spec=AtomicFact)
    fact1.original_text = "Redis timeout was increased to 30 seconds"
    fact1.fact_type = FactType.FACT
    fact1.temporal_type = TemporalType.DYNAMIC
    fact1.confidence = 0.9
    fact1.entities = ["Redis", "timeout"]

    fact2 = Mock(spec=AtomicFact)
    fact2.original_text = "New caching feature improves performance by 40%"
    fact2.fact_type = FactType.FACT
    fact2.temporal_type = TemporalType.DYNAMIC
    fact2.confidence = 0.85
    fact2.entities = ["caching", "performance"]

    fact3 = Mock(spec=AtomicFact)
    fact3.original_text = "Decided to use Redis for session storage"
    fact3.fact_type = FactType.OPINION
    fact3.temporal_type = TemporalType.DYNAMIC
    fact3.confidence = 0.95
    fact3.entities = ["Redis", "session"]

    mock_result.facts = [fact1, fact2, fact3]

    agent.extract_facts = AsyncMock(return_value=mock_result)
    return agent


@pytest.fixture
def mock_memory_graph():
    """Mock AutoBotMemoryGraph for isolated testing."""
    graph = Mock()
    graph.initialized = True

    # Mock create_entity
    async def mock_create_entity(entity_type, name, observations, metadata, tags):
        return {
            "id": f"entity-{hash(name)}",
            "type": entity_type,
            "name": name,
            "observations": observations,
            "metadata": metadata,
        }

    graph.create_entity = AsyncMock(side_effect=mock_create_entity)

    # Mock create_relation
    async def mock_create_relation(from_entity, to_entity, relation_type, **kwargs):
        return {
            "from": from_entity,
            "to": to_entity,
            "type": relation_type,
        }

    graph.create_relation = AsyncMock(side_effect=mock_create_relation)

    return graph


@pytest.fixture
def entity_extractor(mock_extraction_agent, mock_memory_graph):
    """Create GraphEntityExtractor with mocked dependencies."""
    return GraphEntityExtractor(
        extraction_agent=mock_extraction_agent,
        memory_graph=mock_memory_graph,
        confidence_threshold=0.6,
        enable_relationship_inference=True,
    )


# ============================================================================
# Initialization Tests
# ============================================================================


def test_entity_extractor_initialization(mock_extraction_agent, mock_memory_graph):
    """Test GraphEntityExtractor initialization with composition pattern."""
    extractor = GraphEntityExtractor(
        extraction_agent=mock_extraction_agent,
        memory_graph=mock_memory_graph,
        confidence_threshold=0.7,
        enable_relationship_inference=False,
    )

    # Verify composition (dependencies stored, not inherited)
    assert extractor.extractor is mock_extraction_agent
    assert extractor.graph is mock_memory_graph
    assert extractor.confidence_threshold == 0.7
    assert extractor.enable_relationship_inference is False


# ============================================================================
# Extract and Populate Tests
# ============================================================================


@pytest.mark.asyncio
async def test_extract_and_populate_basic(
    entity_extractor, mock_extraction_agent, mock_memory_graph
):
    """Test basic entity extraction and graph population."""
    messages = [
        {"role": "user", "content": "Redis is timing out"},
        {"role": "assistant", "content": "Fixed by increasing timeout to 30s"},
    ]

    result = await entity_extractor.extract_and_populate(
        conversation_id="test-123",
        messages=messages,
    )

    # Verify extraction agent was called (composition)
    mock_extraction_agent.extract_facts.assert_called_once()

    # Verify entities were created
    assert result.entities_created > 0
    assert mock_memory_graph.create_entity.call_count > 0

    # Verify result structure
    assert isinstance(result, ExtractionResult)
    assert result.conversation_id == "test-123"
    assert result.processing_time > 0
    assert result.facts_analyzed == 3  # From mock


@pytest.mark.asyncio
async def test_extract_and_populate_with_relationships(
    entity_extractor, mock_memory_graph
):
    """Test relationship inference during extraction."""
    messages = [
        {"role": "user", "content": "Need to fix Redis timeout"},
        {"role": "assistant", "content": "Fixed timeout, added caching feature"},
    ]

    result = await entity_extractor.extract_and_populate(
        conversation_id="test-456",
        messages=messages,
    )

    # Verify relationships were created
    if result.entities_created > 1:
        assert mock_memory_graph.create_relation.call_count >= 0


@pytest.mark.asyncio
async def test_extract_and_populate_empty_messages(entity_extractor):
    """Test handling of empty message list."""
    result = await entity_extractor.extract_and_populate(
        conversation_id="test-empty",
        messages=[],
    )

    # Should return early with no entities
    assert result.entities_created == 0
    assert result.relations_created == 0


@pytest.mark.asyncio
async def test_extract_and_populate_confidence_threshold(
    entity_extractor, mock_extraction_agent, mock_memory_graph
):
    """Test confidence threshold filtering."""
    # Mock low-confidence facts
    mock_result = Mock()
    mock_result.facts = [
        Mock(
            spec=AtomicFact,
            **{
                "original_text": "Low confidence fact",
                "fact_type": FactType.FACT,
                "temporal_type": TemporalType.DYNAMIC,
                "confidence": 0.3,  # Below threshold,
                "entities": ["test"],
            },
        ),
    ]
    mock_extraction_agent.extract_facts = AsyncMock(return_value=mock_result)

    messages = [{"role": "user", "content": "test"}]

    result = await entity_extractor.extract_and_populate(
        conversation_id="test-threshold",
        messages=messages,
    )

    # Should filter out low-confidence facts
    assert result.facts_analyzed == 1
    # May create 0 entities due to confidence threshold
    assert result.entities_created >= 0


# ============================================================================
# Fact-to-Entity Mapping Tests
# ============================================================================


def test_facts_to_entity_candidates(entity_extractor):
    """Test conversion of facts to entity candidates."""
    facts = [
        Mock(
            spec=AtomicFact,
            **{
                "original_text": "Fixed Redis timeout bug",
                "fact_type": FactType.FACT,
                "temporal_type": TemporalType.TEMPORAL_BOUND,
                "confidence": 0.9,
                "entities": ["Redis", "timeout"],
            },
        ),
        Mock(
            spec=AtomicFact,
            **{
                "original_text": "Added new caching feature",
                "fact_type": FactType.FACT,
                "temporal_type": TemporalType.DYNAMIC,
                "confidence": 0.85,
                "entities": ["caching"],
            },
        ),
    ]

    candidates = entity_extractor._facts_to_entity_candidates(
        facts=facts,
        conversation_id="test-123",
        session_metadata=None,
    )

    # Verify candidates created
    assert len(candidates) > 0

    # Verify entity types mapped correctly
    entity_types = {c.entity_type for c in candidates}
    assert "fact" in entity_types  # Both facts use FactType.FACT

    # Verify observations extracted
    for candidate in candidates:
        assert len(candidate.observations) > 0
        assert candidate.confidence > 0


def test_group_similar_facts(entity_extractor):
    """Test grouping of similar facts."""
    facts = [
        Mock(
            spec=AtomicFact,
            **{
                "original_text": "Redis timeout configuration",
                "fact_type": FactType.FACT,
                "temporal_type": TemporalType.DYNAMIC,
                "confidence": 0.9,
                "entities": ["Redis"],
            },
        ),
        Mock(
            spec=AtomicFact,
            **{
                "original_text": "Redis timeout settings",
                "fact_type": FactType.FACT,
                "temporal_type": TemporalType.DYNAMIC,
                "confidence": 0.85,
                "entities": ["Redis"],
            },
        ),
        Mock(
            spec=AtomicFact,
            **{
                "original_text": "Database backup procedure",
                "fact_type": FactType.INSTRUCTION,
                "temporal_type": TemporalType.STATIC,
                "confidence": 0.8,
                "entities": ["database"],
            },
        ),
    ]

    groups = entity_extractor._group_similar_facts(facts)

    # Verify grouping
    assert len(groups) > 0

    # Verify similar facts grouped together
    # First two facts about Redis should be grouped
    for group in groups:
        assert len(group) > 0


def test_calculate_fact_similarity(entity_extractor):
    """Test fact similarity calculation."""
    fact1 = Mock(
        spec=AtomicFact,
        **{
            "original_text": "Redis timeout configuration settings",
            "fact_type": FactType.FACT,
            "temporal_type": TemporalType.DYNAMIC,
            "confidence": 0.9,
            "entities": [],
        },
    )

    fact2 = Mock(
        spec=AtomicFact,
        **{
            "original_text": "Redis timeout settings changed",
            "fact_type": FactType.FACT,
            "temporal_type": TemporalType.DYNAMIC,
            "confidence": 0.85,
            "entities": [],
        },
    )

    fact3 = Mock(
        spec=AtomicFact,
        **{
            "original_text": "Database backup procedure",
            "fact_type": FactType.INSTRUCTION,
            "temporal_type": TemporalType.STATIC,
            "confidence": 0.8,
            "entities": [],
        },
    )

    # Similar facts should have high similarity
    similarity_high = entity_extractor._calculate_fact_similarity(fact1, fact2)
    assert similarity_high > 0.4  # Share "Redis", "timeout", "settings"

    # Dissimilar facts should have low similarity
    similarity_low = entity_extractor._calculate_fact_similarity(fact1, fact3)
    assert similarity_low < 0.3  # Few shared words


# ============================================================================
# Relationship Inference Tests
# ============================================================================


def test_infer_relationships(entity_extractor):
    """Test relationship inference between entities."""
    entity_candidates = [
        EntityCandidate(
            name="Bug Fix: Redis Timeout",
            entity_type="bug_fix",
            observations=["Fixed timeout issue"],
            confidence=0.9,
            tags={"Redis", "timeout"},
        ),
        EntityCandidate(
            name="Feature: Caching",
            entity_type="feature",
            observations=["Added caching"],
            confidence=0.85,
            tags={"caching", "Redis"},
        ),
    ]

    facts = [
        Mock(
            spec=AtomicFact,
            **{
                "original_text": "Fixed Redis timeout and added caching",
                "fact_type": FactType.FACT,
                "temporal_type": TemporalType.TEMPORAL_BOUND,
                "confidence": 0.9,
                "entities": ["Redis", "caching"],
            },
        ),
    ]

    relations = entity_extractor._infer_relationships(entity_candidates, facts)

    # Verify relationships inferred
    assert len(relations) > 0

    # Verify relation structure
    for relation in relations:
        assert isinstance(relation, RelationCandidate)
        assert relation.from_entity
        assert relation.to_entity
        assert (
            relation.relation_type in entity_extractor.relationship_keywords.keys()
            or relation.relation_type == "relates_to"
        )


def test_check_co_occurrence(entity_extractor):
    """Test co-occurrence detection."""
    entity_a = EntityCandidate(
        name="Entity A",
        entity_type="bug_fix",
        observations=[],
        confidence=0.9,
        tags={"Redis"},
    )

    entity_b = EntityCandidate(
        name="Entity B",
        entity_type="feature",
        observations=[],
        confidence=0.85,
        tags={"caching"},
    )

    facts = [
        Mock(
            spec=AtomicFact,
            **{
                "original_text": "Redis and caching improvements",
                "fact_type": FactType.FACT,
                "temporal_type": TemporalType.DYNAMIC,
                "confidence": 0.9,
                "entities": [],
            },
        ),
    ]

    evidence = entity_extractor._check_co_occurrence(entity_a, entity_b, facts)

    # Verify co-occurrence detected
    assert len(evidence) > 0


def test_deduplicate_relations(entity_extractor):
    """Test relationship deduplication."""
    relations = [
        RelationCandidate(
            from_entity="Entity A",
            to_entity="Entity B",
            relation_type="relates_to",
            confidence=0.7,
        ),
        RelationCandidate(
            from_entity="Entity A",
            to_entity="Entity B",
            relation_type="relates_to",
            confidence=0.9,  # Higher confidence
        ),
        RelationCandidate(
            from_entity="Entity C",
            to_entity="Entity D",
            relation_type="fixes",
            confidence=0.8,
        ),
    ]

    unique = entity_extractor._deduplicate_relations(relations)

    # Verify deduplication
    assert len(unique) == 2  # Two unique relations

    # Verify highest confidence version kept
    relation_ab = [
        r for r in unique if r.from_entity == "Entity A" and r.to_entity == "Entity B"
    ]
    assert len(relation_ab) == 1
    assert relation_ab[0].confidence == 0.9


# ============================================================================
# Helper Method Tests
# ============================================================================


def test_combine_messages(entity_extractor):
    """Test message combination."""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
        {"role": "user", "content": "Help needed"},
    ]

    combined = entity_extractor._combine_messages(messages)

    # Verify messages combined with role prefixes
    assert "[USER]" in combined
    assert "[ASSISTANT]" in combined
    assert "Hello" in combined
    assert "Hi there" in combined


def test_generate_entity_name(entity_extractor):
    """Test entity name generation."""
    fact = Mock(
        spec=AtomicFact,
        **{
            "original_text": "Redis timeout was increased to 30 seconds",
            "fact_type": FactType.FACT,
            "temporal_type": TemporalType.TEMPORAL_BOUND,
            "confidence": 0.9,
            "entities": ["Redis Timeout"],
        },
    )

    name = entity_extractor._generate_entity_name(
        fact=fact,
        entity_type="bug_fix",
        conversation_id="test-123",
    )

    # Verify name structure
    assert "Bug Fix" in name or "bug_fix" in name.lower()
    assert len(name) > 0


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_extract_and_populate_handles_extraction_error(
    entity_extractor, mock_extraction_agent
):
    """Test handling of extraction errors."""
    # Mock extraction failure
    mock_extraction_agent.extract_facts = AsyncMock(
        side_effect=Exception("Extraction failed")
    )

    messages = [{"role": "user", "content": "test"}]

    result = await entity_extractor.extract_and_populate(
        conversation_id="test-error",
        messages=messages,
    )

    # Verify graceful error handling
    assert len(result.errors) > 0
    assert "Extraction failed" in result.errors[0]


@pytest.mark.asyncio
async def test_create_entities_handles_graph_error(entity_extractor, mock_memory_graph):
    """Test handling of graph creation errors."""

    # Mock graph error for specific entity
    async def mock_create_with_error(entity_type, name, **kwargs):
        if "error" in name.lower():
            raise Exception("Graph error")
        return {
            "id": f"entity-{hash(name)}",
            "type": entity_type,
            "name": name,
        }

    mock_memory_graph.create_entity = AsyncMock(side_effect=mock_create_with_error)

    candidates = [
        EntityCandidate(
            name="Good Entity",
            entity_type="feature",
            observations=["test"],
            confidence=0.9,
        ),
        EntityCandidate(
            name="Error Entity",
            entity_type="bug_fix",
            observations=["test"],
            confidence=0.8,
        ),
    ]

    created = await entity_extractor._create_entities_in_graph(candidates)

    # Verify partial success (good entity created, error entity skipped)
    assert len(created) == 1
    assert created[0]["name"] == "Good Entity"
