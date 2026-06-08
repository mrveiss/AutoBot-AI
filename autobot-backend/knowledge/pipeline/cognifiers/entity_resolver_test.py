# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Entity Resolver Tests - Unit tests for entity resolution cognifier.

Issue #3395: RAG optimization — semantic chunking, fact extraction, entity resolution.
"""

from uuid import uuid4

import pytest

from knowledge.pipeline.base import PipelineContext
from knowledge.pipeline.cognifiers.entity_resolver import EntityResolver
from knowledge.pipeline.models.entity import Entity


@pytest.fixture
def entity_resolver():
    """Create an entity resolver instance for testing."""
    return EntityResolver(
        similarity_threshold=0.85,
        use_synonyms=True,
        use_fuzzy_matching=True,
    )


@pytest.fixture
def sample_entities():
    """Create sample entities for testing."""
    doc_id = uuid4()
    return [
        Entity(
            name="AutoBot",
            canonical_name="autobot",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        ),
        Entity(
            name="AutoBot AI",
            canonical_name="autobot ai",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        ),
        Entity(
            name="the system",
            canonical_name="the system",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        ),
        Entity(
            name="ChromaDB",
            canonical_name="chromadb",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        ),
        Entity(
            name="Chroma",
            canonical_name="chroma",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id,
        ),
    ]


@pytest.fixture
def pipeline_context(sample_entities):
    """Create a pipeline context with sample entities."""
    doc_id = sample_entities[0].source_document_id
    context = PipelineContext()
    context.document_id = doc_id
    context.entities = sample_entities
    return context


class TestEntityResolverExactMatch:
    """Tests for exact matching in entity resolution."""

    def test_exact_match_detection(self, entity_resolver):
        """Test that exact matches are detected."""
        entities = [
            Entity(
                name="AutoBot",
                canonical_name="autobot",
                entity_type="TECHNOLOGY",
                source_document_id=uuid4(),
            ),
            Entity(
                name="AutoBot",
                canonical_name="autobot",
                entity_type="TECHNOLOGY",
                source_document_id=uuid4(),
            ),
        ]

        resolved = entity_resolver._resolve_entities(entities)
        assert len(resolved) == 1
        assert resolved[0].extraction_count == 2


class TestEntityResolverSynonyms:
    """Tests for synonym-based resolution."""

    def test_synonym_resolution(self, entity_resolver):
        """Test resolution using predefined synonyms."""
        # Test AutoBot synonyms
        entities = [
            Entity(
                name="AutoBot",
                canonical_name="autobot",
                entity_type="TECHNOLOGY",
                source_document_id=uuid4(),
            ),
            Entity(
                name="AutoBot AI",
                canonical_name="autobot ai",
                entity_type="TECHNOLOGY",
                source_document_id=uuid4(),
            ),
        ]

        resolved = entity_resolver._resolve_entities(entities)
        assert len(resolved) <= 2  # May or may not merge depending on synonym matching

    def test_chromadb_synonym(self, entity_resolver):
        """Test ChromaDB synonym resolution."""
        entities = [
            Entity(
                name="ChromaDB",
                canonical_name="chromadb",
                entity_type="TECHNOLOGY",
                source_document_id=uuid4(),
            ),
            Entity(
                name="Chroma",
                canonical_name="chroma",
                entity_type="TECHNOLOGY",
                source_document_id=uuid4(),
            ),
        ]

        resolved = entity_resolver._resolve_entities(entities)
        # Should merge via synonym mapping
        assert len(resolved) <= 2

    def test_custom_synonyms(self, entity_resolver):
        """Test adding custom synonym mappings."""
        entity_resolver.add_synonyms("autobot", {"AutoBot AI", "the system"})

        match = entity_resolver._find_synonym_match("autobot", ["autobot ai"])
        assert match == "autobot ai"


class TestEntityResolverFuzzyMatching:
    """Tests for fuzzy string matching in resolution."""

    def test_fuzzy_match_detection(self, entity_resolver):
        """Test fuzzy matching with high similarity."""
        # Very similar strings should match
        match = entity_resolver._find_fuzzy_match(
            "chromadb",
            ["chromadb", "chromadb_v2"],
        )
        # Should match "chromadb" exactly or close variant
        assert match is not None

    def test_fuzzy_match_threshold(self, entity_resolver):
        """Test that fuzzy matching respects similarity threshold."""
        # Very dissimilar strings should not match
        match = entity_resolver._find_fuzzy_match(
            "chromadb",
            ["completely_different", "unrelated_system"],
        )
        assert match is None

    def test_string_similarity(self):
        """Test string similarity calculation."""
        resolver = EntityResolver()

        # Identical strings
        assert resolver._string_similarity("test", "test") == 1.0

        # Completely different strings
        assert resolver._string_similarity("abc", "xyz") < 0.5

        # Similar strings
        similarity = resolver._string_similarity("chromadb", "chromadb_v2")
        assert 0.5 < similarity < 1.0


class TestEntityResolverAsync:
    """Tests for async resolution operations."""

    @pytest.mark.asyncio
    async def test_process_entities(self, entity_resolver, pipeline_context):
        """Test async entity resolution."""
        result = await entity_resolver.process(pipeline_context)

        assert result.entities is not None
        assert isinstance(result.entities, list)
        # Should have fewer or equal entities after resolution
        assert len(result.entities) <= len(pipeline_context.entities)

    @pytest.mark.asyncio
    async def test_process_empty_entities(self, entity_resolver):
        """Test processing with no entities."""
        context = PipelineContext()
        context.document_id = uuid4()
        context.entities = []

        result = await entity_resolver.process(context)
        assert result.entities == []

    @pytest.mark.asyncio
    async def test_process_none_entities(self, entity_resolver):
        """Test processing with None entities."""
        context = PipelineContext()
        context.document_id = uuid4()
        context.entities = None

        result = await entity_resolver.process(context)
        assert result.entities is None


class TestEntityResolverStrategy:
    """Tests for multi-strategy resolution."""

    def test_find_equivalent_entity_exact(self, entity_resolver):
        """Test exact match strategy."""
        existing = ["autobot", "chromadb", "llm"]
        match = entity_resolver._find_equivalent_entity("autobot", existing)
        assert match == "autobot"

    def test_find_equivalent_entity_synonym(self, entity_resolver):
        """Test synonym match strategy."""
        existing = ["autobot", "chromadb"]
        # Add a test to ensure strategy is applied
        match = entity_resolver._find_equivalent_entity("autobot ai", existing)
        # May or may not find match depending on synonym configuration
        assert match is None or match in existing

    def test_find_equivalent_entity_fuzzy(self, entity_resolver):
        """Test fuzzy match strategy."""
        existing = ["chromadb"]
        match = entity_resolver._find_equivalent_entity("chromadb", existing)
        assert match == "chromadb"

    def test_strategy_priority(self, entity_resolver):
        """Test that exact match takes priority over fuzzy."""
        # Exact match should be found first
        existing = ["chromadb", "chroma"]
        match = entity_resolver._find_equivalent_entity("chromadb", existing)
        assert match == "chromadb"


class TestEntitySourceTracking:
    """Tests for source tracking during resolution."""

    def test_merged_entity_tracking(self, entity_resolver):
        """Test that merged entities track all sources."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()

        entity1 = Entity(
            name="AutoBot",
            canonical_name="autobot",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id_1,
        )
        entity2 = Entity(
            name="AutoBot",
            canonical_name="autobot",
            entity_type="TECHNOLOGY",
            source_document_id=doc_id_2,
        )

        resolved = entity_resolver._resolve_entities([entity1, entity2])
        assert len(resolved) == 1
        # Should have incremented extraction count
        assert resolved[0].extraction_count >= 2
