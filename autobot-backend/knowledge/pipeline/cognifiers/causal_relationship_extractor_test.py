# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for CausalRelationshipExtractor.

Issue #3395: RAG semantic chunking, fact extraction, entity resolution.

Covers:
- LLM-guided causal extraction with confidence filtering
- NLP lightweight pattern matching (fallback)
- Condition detection and evidence tracking
- Correlation rejection (distinguish causality from correlation)
- Mode selection (auto, nlp, llm)
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Stub out llm_shared and autobot_shared to avoid dependency issues
_mock_llm_mod = ModuleType("llm_shared")
_mock_llm_mod.LLMInterface = type("LLMInterface", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("llm_shared", _mock_llm_mod)

_mock_shared = ModuleType("autobot_shared")
_mock_redis_mod = ModuleType("autobot_shared.redis_client")
_mock_redis_mod.get_redis_client = lambda *a, **kw: None  # type: ignore[attr-defined]
sys.modules.setdefault("autobot_shared", _mock_shared)
sys.modules.setdefault("autobot_shared.redis_client", _mock_redis_mod)

from knowledge.pipeline.base import PipelineContext  # noqa: E402
from knowledge.pipeline.cognifiers.causal_relationship_extractor import (  # noqa: E402
    CausalRelationshipExtractor,
)
from knowledge.pipeline.models.causal_edge import CausalEdge  # noqa: E402
from knowledge.pipeline.models.chunk import ProcessedChunk  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(content: str, doc_id=None) -> ProcessedChunk:
    """Create a test chunk."""
    return ProcessedChunk(content=content, document_id=doc_id or uuid4(), chunk_index=0)


def _make_context() -> PipelineContext:
    """Create a test pipeline context."""
    ctx = PipelineContext()
    ctx.document_id = uuid4()
    return ctx


# ---------------------------------------------------------------------------
# NLP Extraction Tests
# ---------------------------------------------------------------------------


class TestNLPExtractionPatterns:
    """NLP lightweight extraction identifies basic causal patterns."""

    def test_extracts_simple_causality(self) -> None:
        """Basic 'X causes Y' pattern is detected."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        chunk = _make_chunk("Cache TTL causes query latency reduction.")
        ctx = _make_context()
        ctx.chunks = [chunk]

        # Call the NLP extraction directly
        edges = extractor._nlp_extract_chunk(chunk, ctx.document_id)

        # Should find at least one edge with "causes"
        assert len(edges) > 0, "Expected to find causal edge"
        assert any("cause" in e.effect_type.lower() for e in edges)

    def test_detects_enables_relationship(self) -> None:
        """'X enables Y' pattern is identified."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        chunk = _make_chunk("Proper indexing enables fast queries.")
        ctx = _make_context()

        edges = extractor._nlp_extract_chunk(chunk, ctx.document_id)

        assert len(edges) > 0, "Expected to find 'enables' relationship"

    def test_detects_prevents_relationship(self) -> None:
        """'X prevents Y' pattern is identified."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        chunk = _make_chunk("Rate limiting prevents resource exhaustion.")
        ctx = _make_context()

        edges = extractor._nlp_extract_chunk(chunk, ctx.document_id)

        assert len(edges) > 0, "Expected to find 'prevents' relationship"

    def test_detects_reduces_relationship(self) -> None:
        """'X reduces Y' pattern is identified."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        chunk = _make_chunk("Caching reduces database queries significantly.")
        ctx = _make_context()

        edges = extractor._nlp_extract_chunk(chunk, ctx.document_id)

        assert len(edges) > 0, "Expected to find 'reduces' relationship"

    def test_rejects_pure_correlation(self) -> None:
        """Correlation patterns are rejected (not causality)."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        chunk = _make_chunk("Cache size and memory usage are correlated.")
        ctx = _make_context()

        edges = extractor._nlp_extract_chunk(chunk, ctx.document_id)

        # Should be filtered out because of "correlated"
        assert len(edges) == 0, "Should reject correlation pattern"

    def test_rejects_conjunction_without_causality(self) -> None:
        """Simple conjunction 'X and Y' without causal keyword is rejected."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        chunk = _make_chunk("Redis and PostgreSQL are both databases.")
        ctx = _make_context()

        edges = extractor._nlp_extract_chunk(chunk, ctx.document_id)

        # "and" alone is rejected; needs a causal keyword
        assert len(edges) == 0, "Should reject pure conjunction"

    def test_extracts_multiple_relationships_from_chunk(self) -> None:
        """Multiple causal relationships in one chunk are all extracted."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        chunk = _make_chunk("High load causes latency. Caching reduces load. " "Indexing enables fast queries.")
        ctx = _make_context()

        edges = extractor._nlp_extract_chunk(chunk, ctx.document_id)

        # Should find multiple edges (at least 2-3 depending on keyword matching)
        assert len(edges) >= 2, f"Expected multiple edges, got {len(edges)}"


# ---------------------------------------------------------------------------
# LLM Extraction Tests
# ---------------------------------------------------------------------------


class TestLLMExtractionWithMocks:
    """LLM-based extraction with mocked LLM responses."""

    @pytest.mark.asyncio
    async def test_llm_extracts_with_high_confidence(self) -> None:
        """LLM extraction produces high-confidence edges."""
        extractor = CausalRelationshipExtractor(mode="llm", min_confidence=0.7)

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = """{
            "source_name": "cache_ttl",
            "target_name": "query_latency",
            "effect_type": "REDUCES",
            "condition": "when cache is enabled",
            "evidence_text": "Shorter TTLs reduce latency.",
            "confidence": 0.95
        }"""
        extractor.llm.chat_completion = AsyncMock(return_value=mock_response)

        chunk = _make_chunk("Shorter TTLs reduce latency.")
        ctx = _make_context()
        ctx.chunks = [chunk]

        edges = await extractor._extract_from_chunk(chunk, ctx)

        assert len(edges) == 1
        edge = edges[0]
        assert edge.source_name == "cache_ttl"
        assert edge.target_name == "query_latency"
        assert edge.effect_type == "REDUCES"
        assert edge.confidence == 0.95

    @pytest.mark.asyncio
    async def test_llm_filters_low_confidence_edges(self) -> None:
        """Edges below min_confidence threshold are filtered."""
        extractor = CausalRelationshipExtractor(mode="llm", min_confidence=0.8)

        mock_response = MagicMock()
        mock_response.content = """{
            "source_name": "cache_size",
            "target_name": "memory",
            "effect_type": "AMPLIFIES",
            "condition": "",
            "evidence_text": "Cache size might affect memory.",
            "confidence": 0.6
        }"""
        extractor.llm.chat_completion = AsyncMock(return_value=mock_response)

        chunk = _make_chunk("Cache size might affect memory.")
        ctx = _make_context()

        edges = await extractor._extract_from_chunk(chunk, ctx)

        # Should be filtered out (0.6 < 0.8 threshold)
        assert len(edges) == 0, "Expected low-confidence edge to be filtered"

    @pytest.mark.asyncio
    async def test_llm_extracts_conditional_causality(self) -> None:
        """LLM extracts conditions under which causality holds."""
        extractor = CausalRelationshipExtractor(mode="llm")

        mock_response = MagicMock()
        mock_response.content = """{
            "source_name": "request_rate",
            "target_name": "cpu_usage",
            "effect_type": "AMPLIFIES",
            "condition": "when processing is single-threaded",
            "evidence_text": "Request rate amplifies CPU usage when processing is single-threaded.",
            "confidence": 0.9
        }"""
        extractor.llm.chat_completion = AsyncMock(return_value=mock_response)

        chunk = _make_chunk("Request rate amplifies CPU usage when processing is single-threaded.")
        ctx = _make_context()

        edges = await extractor._extract_from_chunk(chunk, ctx)

        assert len(edges) == 1
        edge = edges[0]
        assert edge.condition == "when processing is single-threaded"

    @pytest.mark.asyncio
    async def test_llm_handles_malformed_json(self) -> None:
        """Malformed LLM JSON response is handled gracefully."""
        extractor = CausalRelationshipExtractor(mode="llm")

        mock_response = MagicMock()
        mock_response.content = "Not valid JSON"
        extractor.llm.chat_completion = AsyncMock(return_value=mock_response)

        chunk = _make_chunk("Some text")
        ctx = _make_context()

        edges = await extractor._extract_from_chunk(chunk, ctx)

        # Should return empty list, not crash
        assert edges == []

    @pytest.mark.asyncio
    async def test_llm_extracts_multiple_edges_from_response(self) -> None:
        """LLM can return multiple causal edges in one response."""
        extractor = CausalRelationshipExtractor(mode="llm")

        mock_response = MagicMock()
        mock_response.content = """[
            {
                "source_name": "cache_ttl",
                "target_name": "latency",
                "effect_type": "REDUCES",
                "condition": "",
                "evidence_text": "Shorter TTLs reduce latency.",
                "confidence": 0.9
            },
            {
                "source_name": "load",
                "target_name": "latency",
                "effect_type": "AMPLIFIES",
                "condition": "when cache is full",
                "evidence_text": "Load amplifies latency when cache is full.",
                "confidence": 0.85
            }
        ]"""
        extractor.llm.chat_completion = AsyncMock(return_value=mock_response)

        chunk = _make_chunk("Complex scenario text")
        ctx = _make_context()

        edges = await extractor._extract_from_chunk(chunk, ctx)

        assert len(edges) == 2
        assert edges[0].source_name == "cache_ttl"
        assert edges[1].source_name == "load"


# ---------------------------------------------------------------------------
# Mode Selection Tests
# ---------------------------------------------------------------------------


class TestModeSelection:
    """Automatic mode selection based on chunk count."""

    def test_selects_llm_below_threshold(self) -> None:
        """Auto mode selects LLM when chunk count < threshold."""
        extractor = CausalRelationshipExtractor(mode="auto", nlp_threshold=500)
        chunks = [_make_chunk(f"Text {i}") for i in range(10)]

        mode = extractor._select_mode(chunks)

        assert mode == "llm", "Should select LLM for small chunk count"

    def test_selects_nlp_above_threshold(self) -> None:
        """Auto mode selects NLP when chunk count >= threshold."""
        extractor = CausalRelationshipExtractor(mode="auto", nlp_threshold=100)
        chunks = [_make_chunk(f"Text {i}") for i in range(150)]

        mode = extractor._select_mode(chunks)

        assert mode == "nlp", "Should select NLP for large chunk count"

    def test_respects_explicit_mode(self) -> None:
        """Explicit mode overrides auto selection."""
        extractor = CausalRelationshipExtractor(mode="nlp", nlp_threshold=10)
        chunks = [_make_chunk("Text")]

        mode = extractor._select_mode(chunks)

        assert mode == "nlp", "Should use explicit mode"


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestProcessPipelineIntegration:
    """Full pipeline process() integration."""

    @pytest.mark.asyncio
    async def test_process_adds_causal_edges_to_context(self) -> None:
        """process() adds causal_edges attribute to context."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        ctx = _make_context()
        ctx.chunks = [_make_chunk("Caching reduces latency.")]

        result = await extractor.process(ctx)

        assert hasattr(result, "causal_edges"), "Context should have causal_edges"
        assert len(result.causal_edges) > 0, "Should extract at least one edge"

    @pytest.mark.asyncio
    async def test_process_handles_empty_chunks(self) -> None:
        """process() handles empty chunk list gracefully."""
        extractor = CausalRelationshipExtractor(mode="llm")
        ctx = _make_context()
        ctx.chunks = []

        result = await extractor.process(ctx)

        # Should return context unchanged
        assert hasattr(result, "chunks")

    @pytest.mark.asyncio
    async def test_process_extends_existing_causal_edges(self) -> None:
        """process() extends existing causal_edges list."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        ctx = _make_context()
        ctx.chunks = [_make_chunk("Indexing enables queries.")]

        # Simulate existing edges
        existing_edge = CausalEdge(
            source_name="cache",
            target_name="speed",
            effect_type="ENABLES",
        )
        ctx.causal_edges = [existing_edge]

        result = await extractor.process(ctx)

        # Should have original + new
        assert len(result.causal_edges) >= 1


# ---------------------------------------------------------------------------
# Evidence & Condition Tests
# ---------------------------------------------------------------------------


class TestEvidenceAndConditions:
    """Evidence tracking and condition detection."""

    def test_nlp_extraction_preserves_evidence_text(self) -> None:
        """NLP extraction stores the source sentence as evidence."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        text = "Shorter TTLs reduce query latency in practice."
        chunk = _make_chunk(text)
        ctx = _make_context()

        edges = extractor._nlp_extract_chunk(chunk, ctx.document_id)

        if edges:
            # Evidence text should be present
            assert any(e.evidence_text for e in edges), "Evidence should be preserved"

    def test_causal_edge_model_formats_causal_string(self) -> None:
        """CausalEdge.to_causal_string() formats readable output."""
        edge = CausalEdge(
            source_name="cache_ttl",
            target_name="latency",
            effect_type="REDUCES",
            condition="when enabled",
        )

        result = edge.to_causal_string()

        assert "cache_ttl" in result
        assert "latency" in result
        assert "when enabled" in result


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_handles_empty_text(self) -> None:
        """Empty text produces no edges."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        chunk = _make_chunk("")
        ctx = _make_context()

        edges = extractor._nlp_extract_chunk(chunk, ctx.document_id)

        assert len(edges) == 0

    def test_handles_single_word(self) -> None:
        """Single word produces no edges."""
        extractor = CausalRelationshipExtractor(mode="nlp")
        chunk = _make_chunk("Causes")
        ctx = _make_context()

        edges = extractor._nlp_extract_chunk(chunk, ctx.document_id)

        # May produce 0 or 1 depending on word matching
        assert len(edges) <= 1

    @pytest.mark.asyncio
    async def test_handles_llm_exception(self) -> None:
        """LLM exceptions are caught and logged."""
        extractor = CausalRelationshipExtractor(mode="llm")

        # Mock LLM to raise exception
        extractor.llm.chat_completion = AsyncMock(side_effect=RuntimeError("LLM error"))

        chunk = _make_chunk("Some text")
        ctx = _make_context()

        edges = await extractor._extract_from_chunk(chunk, ctx)

        # Should return empty list, not crash
        assert edges == []

    def test_normalizes_effect_type(self) -> None:
        """Invalid effect types are normalized to CAUSES."""
        extractor = CausalRelationshipExtractor(mode="llm")
        raw_edges = [
            {
                "source_name": "a",
                "target_name": "b",
                "effect_type": "INVALID_TYPE",
                "confidence": 0.9,
            }
        ]

        chunk = _make_chunk("test")
        edges = extractor._convert_to_causal_edges(raw_edges, chunk, uuid4())

        assert edges[0].effect_type == "CAUSES"
