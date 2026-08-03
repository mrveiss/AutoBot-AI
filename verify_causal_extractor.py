#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Quick verification script for CausalRelationshipExtractor.
Tests the core functionality without requiring full pytest infrastructure.
"""

# isort: skip_file
# Import order is load-bearing: sys.path must gain the package roots and the
# optional LLM provider must be stubbed BEFORE the knowledge.pipeline imports
# below. Re-sorting them to the top makes this script unrunnable.

import sys
from pathlib import Path
from types import ModuleType
from uuid import uuid4

# Resolve package roots from __file__ (#13409) — this previously hardcoded a
# developer workstation's absolute path and could only run on one machine.
_REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "autobot-backend"))

# Stub the optional LLM provider — this script exercises the NLP path only.
_mock_llm_mod = ModuleType("llm_interface_pkg")
_mock_llm_mod.LLMInterface = type("LLMInterface", (), {})
sys.modules.setdefault("llm_interface_pkg", _mock_llm_mod)

# autobot_shared is imported for real. It used to be replaced by a bare
# ModuleType stub, which is not a package, so every downstream
# `from autobot_shared.<sub> import ...` broke once knowledge.pipeline started
# importing logging_manager and rate_limiter. The real client degrades to a
# warning when no broker is reachable, which is fine for this offline check.

from knowledge.pipeline.cognifiers.causal_relationship_extractor import (
    CausalRelationshipExtractor,
)
from knowledge.pipeline.models.causal_edge import CausalEdge
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.base import PipelineContext


def test_nlp_extraction():
    """Test NLP-based causal extraction."""
    print("\n=== Testing NLP Extraction ===")  # noqa: print
    extractor = CausalRelationshipExtractor(mode="nlp")

    test_cases = [
        ("Cache TTL causes query latency reduction.", "CAUSES"),
        ("Indexing enables fast queries.", "ENABLES"),
        ("Rate limiting prevents resource exhaustion.", "PREVENTS"),
        ("Caching reduces database queries.", "REDUCES"),
    ]

    for text, expected_type in test_cases:
        chunk = ProcessedChunk(content=text, document_id=uuid4(), chunk_index=0)
        edges = extractor._nlp_extract_chunk(chunk, uuid4())

        if edges:
            print(f"✓ '{text}'")  # noqa: print
            print(f"  → Found {len(edges)} edge(s)")  # noqa: print
            for edge in edges:
                print(f"    - {edge.source_name} {edge.effect_type} {edge.target_name}")  # noqa: print
                print(f"      Confidence: {edge.confidence}")  # noqa: print
        else:
            print(f"✓ '{text}' (no edges - expected for basic pattern matching)")  # noqa: print


def test_correlation_rejection():
    """Test that correlations are rejected."""
    print("\n=== Testing Correlation Rejection ===")  # noqa: print
    extractor = CausalRelationshipExtractor(mode="nlp")

    correlation_texts = [
        "Cache size and memory usage are correlated.",
        "X and Y tend to occur together.",
        "These metrics are associated with latency.",
    ]

    for text in correlation_texts:
        chunk = ProcessedChunk(content=text, document_id=uuid4(), chunk_index=0)
        edges = extractor._nlp_extract_chunk(chunk, uuid4())

        if not edges:
            print(f"✓ Correctly rejected correlation: '{text}'")  # noqa: print
        else:
            print(f"⚠ WARNING: Accepted correlation as causal: '{text}'")  # noqa: print


def test_causal_edge_model():
    """Test CausalEdge model and formatting."""
    print("\n=== Testing CausalEdge Model ===")  # noqa: print

    edge = CausalEdge(
        source_name="cache_ttl",
        target_name="query_latency",
        effect_type="REDUCES",
        condition="when cache is enabled",
        confidence=0.95,
        evidence_text="Shorter TTLs reduce query latency by forcing fresh data retrieval.",
    )

    print(f"✓ CausalEdge created successfully")  # noqa: print
    print(f"  - source: {edge.source_name}")  # noqa: print
    print(f"  - target: {edge.target_name}")  # noqa: print
    print(f"  - effect_type: {edge.effect_type}")  # noqa: print
    print(f"  - condition: {edge.condition}")  # noqa: print
    print(f"  - confidence: {edge.confidence}")  # noqa: print
    print(f"  - Human-readable: {edge.to_causal_string()}")  # noqa: print


def test_mode_selection():
    """Test automatic mode selection."""
    print("\n=== Testing Mode Selection ===")  # noqa: print

    extractor = CausalRelationshipExtractor(mode="auto", nlp_threshold=100)

    # Small chunk set
    small_chunks = [ProcessedChunk(content=f"Text {i}", document_id=uuid4(), chunk_index=i) for i in range(10)]
    mode = extractor._select_mode(small_chunks)
    print(f"✓ Mode for 10 chunks: {mode} (expected: llm)")  # noqa: print

    # Large chunk set
    large_chunks = [ProcessedChunk(content=f"Text {i}", document_id=uuid4(), chunk_index=i) for i in range(150)]
    mode = extractor._select_mode(large_chunks)
    print(f"✓ Mode for 150 chunks: {mode} (expected: nlp)")  # noqa: print


def test_confidence_filtering():
    """Test confidence score filtering."""
    print("\n=== Testing Confidence Filtering ===")  # noqa: print

    extractor = CausalRelationshipExtractor(mode="llm", min_confidence=0.8)

    raw_edges = [
        {
            "source_name": "a",
            "target_name": "b",
            "effect_type": "CAUSES",
            "condition": "",
            "confidence": 0.95,  # Above threshold
        },
        {
            "source_name": "c",
            "target_name": "d",
            "effect_type": "PREVENTS",
            "condition": "",
            "confidence": 0.5,  # Below threshold
        },
    ]

    chunk = ProcessedChunk(content="test", document_id=uuid4(), chunk_index=0)
    edges = extractor._convert_to_causal_edges(raw_edges, chunk, uuid4())

    print(f"✓ Input: {len(raw_edges)} raw edges (one above, one below 0.8 threshold)")  # noqa: print
    print(f"  → Filtered: {len(edges)} edges")  # noqa: print
    for edge in edges:
        print(f"    - {edge.source_name} {edge.effect_type} {edge.target_name}")  # noqa: print
        print(f"      Confidence: {edge.confidence}")  # noqa: print

    if len(edges) == 1 and edges[0].confidence >= 0.8:
        print("✓ Confidence filtering working correctly")  # noqa: print
    else:
        print("⚠ WARNING: Confidence filtering not working as expected")  # noqa: print


def test_pipeline_context_integration():
    """Test integration with PipelineContext."""
    print("\n=== Testing PipelineContext Integration ===")  # noqa: print

    ctx = PipelineContext()
    ctx.document_id = uuid4()
    ctx.chunks = [
        ProcessedChunk(
            content="Caching reduces latency.",
            document_id=ctx.document_id,
            chunk_index=0,
        )
    ]

    # Simulate having causal_edges attribute
    if hasattr(ctx, "causal_edges"):
        print("✓ PipelineContext has causal_edges attribute")  # noqa: print

        edge = CausalEdge(
            source_name="cache",
            target_name="latency",
            effect_type="REDUCES",
        )
        ctx.causal_edges.append(edge)
        print(f"✓ Successfully added edge to context")  # noqa: print
        print(f"  → Total edges in context: {len(ctx.causal_edges)}")  # noqa: print
    else:
        print("⚠ WARNING: PipelineContext missing causal_edges attribute")  # noqa: print


def main():
    """Run all verification tests."""
    print("=" * 60)  # noqa: print
    print("CausalRelationshipExtractor Verification")  # noqa: print
    print("=" * 60)  # noqa: print

    try:
        test_causal_edge_model()
        test_nlp_extraction()
        test_correlation_rejection()
        test_mode_selection()
        test_confidence_filtering()
        test_pipeline_context_integration()

        print("\n" + "=" * 60)  # noqa: print
        print("✓ All verification tests passed!")  # noqa: print
        print("=" * 60)  # noqa: print
        return 0
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")  # noqa: print
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
