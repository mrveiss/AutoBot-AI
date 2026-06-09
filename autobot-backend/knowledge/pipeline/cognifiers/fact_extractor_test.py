# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fact Extractor Tests - Unit tests for fact extraction cognifier.

Issue #3395: RAG optimization — semantic chunking, fact extraction, entity resolution.
"""

from uuid import uuid4

import pytest

from knowledge.pipeline.base import PipelineContext
from knowledge.pipeline.cognifiers.fact_extractor import FactExtractor
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.models.fact import AtomicFact


@pytest.fixture
def fact_extractor():
    """Create a fact extractor instance for testing."""
    return FactExtractor(mode="nlp", use_patterns=True)


@pytest.fixture
def sample_chunks():
    """Create sample chunks for testing."""
    doc_id = uuid4()
    return [
        ProcessedChunk(
            content="AutoBot is an AI-powered automation platform. It uses ChromaDB for knowledge indexing.",
            document_id=doc_id,
            chunk_index=0,
        ),
        ProcessedChunk(
            content="Entity resolution enables improved retrieval accuracy. The system contains multiple components.",
            document_id=doc_id,
            chunk_index=1,
        ),
    ]


@pytest.fixture
def pipeline_context(sample_chunks):
    """Create a pipeline context with sample chunks."""
    doc_id = sample_chunks[0].document_id
    context = PipelineContext()
    context.document_id = doc_id
    context.chunks = sample_chunks
    return context


class TestFactExtractorNLP:
    """Tests for NLP-based fact extraction."""

    def test_nlp_extract_simple_facts(self, fact_extractor, sample_chunks):
        """Test extraction of simple facts using NLP patterns."""
        facts = fact_extractor._nlp_extract(sample_chunks, sample_chunks[0].document_id)

        assert len(facts) > 0
        assert all(isinstance(f, AtomicFact) for f in facts)
        assert all(f.subject and f.predicate and f.object_ for f in facts)

    def test_nlp_extract_confidence_scores(self, fact_extractor, sample_chunks):
        """Test that NLP-extracted facts have confidence scores."""
        facts = fact_extractor._nlp_extract(sample_chunks, sample_chunks[0].document_id)

        for fact in facts:
            assert 0.0 <= fact.confidence <= 1.0

    def test_fact_deduplication(self, fact_extractor):
        """Test that identical facts are deduplicated."""
        facts = [
            AtomicFact(
                subject="AutoBot",
                predicate="is",
                object="platform",
                source_document_id=uuid4(),
                confidence=0.9,
            ),
            AtomicFact(
                subject="AutoBot",
                predicate="is",
                object="platform",
                source_document_id=uuid4(),
                confidence=0.8,
            ),
        ]

        dedup = fact_extractor._deduplicate_facts(facts)
        assert len(dedup) == 1
        assert dedup[0].supported_by_count == 2

    def test_normalize_triple(self, fact_extractor):
        """Test triple normalization for deduplication."""
        triple1 = fact_extractor._normalize_triple("AutoBot", "IS", "Platform")
        triple2 = fact_extractor._normalize_triple("autobot", "is", "platform")

        assert triple1 == triple2

    def test_sentence_splitting(self, fact_extractor):
        """Test sentence splitting for pattern matching."""
        text = "AutoBot is a system. It enables automation. The system is comprehensive."
        sentences = fact_extractor._split_sentences(text)

        assert len(sentences) == 3
        assert all(isinstance(s, str) for s in sentences)
        assert all(s for s in sentences)  # No empty strings


class TestFactExtractorAsync:
    """Tests for async operations."""

    @pytest.mark.asyncio
    async def test_process_with_nlp_mode(self, fact_extractor, pipeline_context):
        """Test async fact extraction with NLP mode."""
        result = await fact_extractor.process(pipeline_context)

        assert result.facts is not None
        assert isinstance(result.facts, list)
        assert all(isinstance(f, AtomicFact) for f in result.facts)

    @pytest.mark.asyncio
    async def test_process_empty_chunks(self):
        """Test processing with no chunks."""
        extractor = FactExtractor(mode="nlp")
        context = PipelineContext()
        context.document_id = uuid4()
        context.chunks = []

        result = await extractor.process(context)
        assert result.facts == []

    @pytest.mark.asyncio
    async def test_mode_selection(self, pipeline_context):
        """Test automatic mode selection based on chunk count."""
        # Small number of chunks should select LLM mode
        extractor_auto = FactExtractor(mode="auto", nlp_threshold=100)
        mode = extractor_auto._select_mode(pipeline_context.chunks)
        assert mode == "llm"

        # Large number of chunks should select NLP mode
        pipeline_context.chunks = [
            ProcessedChunk(
                content=f"Fact {i}",
                document_id=pipeline_context.document_id,
                chunk_index=i,
            )
            for i in range(600)
        ]
        mode = extractor_auto._select_mode(pipeline_context.chunks)
        assert mode == "nlp"


class TestFactTypes:
    """Tests for fact type classification."""

    def test_fact_type_statement(self):
        """Test statement fact type."""
        fact = AtomicFact(
            subject="AutoBot",
            predicate="is",
            object="platform",
            fact_type="statement",
            source_document_id=uuid4(),
        )
        assert fact.fact_type == "statement"

    def test_fact_type_relationship(self):
        """Test relationship fact type."""
        fact = AtomicFact(
            subject="AutoBot",
            predicate="uses",
            object="ChromaDB",
            fact_type="relationship",
            source_document_id=uuid4(),
        )
        assert fact.fact_type == "relationship"

    def test_fact_as_triple(self):
        """Test fact triple representation."""
        fact = AtomicFact(
            subject="Entity A",
            predicate="relates_to",
            object="Entity B",
            source_document_id=uuid4(),
        )
        triple = fact.as_triple()
        assert triple == ("Entity A", "relates_to", "Entity B")
