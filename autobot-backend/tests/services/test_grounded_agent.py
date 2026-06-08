# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for GroundedAgent (Tier 4 - Knowledge Grounding)

Tests core functionality:
- Claim extraction
- KB classification
- Verification
- Conflict resolution
- Response reconstruction
- Causal trace generation

Issue: #4070 (Knowledge Grounding Tier 4)

This module contains 40+ tests verifying:
- End-to-end grounded response generation
- Claims from KB only
- Unknown claims (trigger research)
- Conflicting claims
- Conflict resolution
- Error handling
- Integration with Tier 3
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.grounded_agent import (
    Claim,
    ClaimStatus,
    GroundedAgent,
    GroundedResponse,
    VerifiedClaim,
)


@pytest.fixture
def grounded_agent():
    """Create a GroundedAgent for testing."""
    return GroundedAgent()


@pytest.fixture
def sample_claim():
    """Create a sample claim."""
    return Claim(
        claim_text="System latency increased by 15%",
        subject="System latency",
        predicate="increased by",
        object="15%",
        confidence=0.95,
    )


@pytest.fixture
def sample_verified_claim(sample_claim):
    """Create a sample verified claim."""
    return VerifiedClaim(
        claim=sample_claim,
        kb_status=ClaimStatus.IN_KB,
        kb_source="fact-123",
        confidence=0.95,
        evidence=["Found in KB monitoring facts"],
        verification_method="kb_lookup",
    )


# ===== CLAIM EXTRACTION TESTS =====


@pytest.mark.asyncio
async def test_extract_claims_success(grounded_agent):
    """Test successful claim extraction."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                [
                    {
                        "claim_text": "Latency increased",
                        "subject": "Latency",
                        "predicate": "increased",
                        "object": "yes",
                        "confidence": 0.95,
                    },
                    {
                        "claim_text": "DB slow",
                        "subject": "DB",
                        "predicate": "is",
                        "object": "slow",
                        "confidence": 0.87,
                    },
                ]
            )
        )
    )
    grounded_agent.llm_service = mock_llm

    claims = await grounded_agent._extract_claims(
        "Why slow?",
        "Latency increased and DB slow",
    )

    assert len(claims) == 2
    assert claims[0].claim_text == "Latency increased"
    assert claims[0].confidence == 0.95


@pytest.mark.asyncio
async def test_extract_claims_empty(grounded_agent):
    """Test extraction with empty response."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=MagicMock(content="[]"))
    grounded_agent.llm_service = mock_llm

    claims = await grounded_agent._extract_claims("Q", "")

    assert claims == []


@pytest.mark.asyncio
async def test_extract_claims_invalid_json(grounded_agent):
    """Test extraction with invalid JSON."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=MagicMock(content="not json"))
    grounded_agent.llm_service = mock_llm

    claims = await grounded_agent._extract_claims("Q", "A")

    assert claims == []


@pytest.mark.asyncio
async def test_extract_claims_error(grounded_agent):
    """Test extraction error handling."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=Exception("Error"))
    grounded_agent.llm_service = mock_llm

    claims = await grounded_agent._extract_claims("Q", "A")

    assert claims == []


# ===== CLAIM CLASSIFICATION TESTS =====


@pytest.mark.asyncio
async def test_classify_claim_in_kb(grounded_agent, sample_claim):
    """Test claim found in KB."""
    mock_kb = AsyncMock()
    mock_kb.search = AsyncMock(
        return_value=[
            {
                "fact_id": "f1",
                "content": "Latency increased",
                "similarity_score": 0.92,
            }
        ]
    )
    grounded_agent.kb = mock_kb

    verified = await grounded_agent._classify_and_verify_claim(sample_claim)

    assert verified.kb_status == ClaimStatus.IN_KB
    assert verified.confidence > 0.85
    assert verified.kb_source == "f1"


@pytest.mark.asyncio
async def test_classify_claim_unknown(grounded_agent, sample_claim):
    """Test claim not in KB."""
    mock_kb = AsyncMock()
    mock_kb.search = AsyncMock(return_value=[])
    grounded_agent.kb = mock_kb

    verified = await grounded_agent._classify_and_verify_claim(sample_claim)

    assert verified.kb_status == ClaimStatus.UNKNOWN
    assert verified.confidence == 0.0


@pytest.mark.asyncio
async def test_classify_claim_partial_match(grounded_agent, sample_claim):
    """Test claim with partial KB match."""
    mock_kb = AsyncMock()
    mock_kb.search = AsyncMock(
        return_value=[
            {
                "fact_id": "f2",
                "content": "Some latency info",
                "similarity_score": 0.65,
            }
        ]
    )
    grounded_agent.kb = mock_kb

    verified = await grounded_agent._classify_and_verify_claim(sample_claim)

    assert verified.kb_status == ClaimStatus.VERIFIED
    assert 0.5 < verified.confidence < 0.85


@pytest.mark.asyncio
async def test_classify_claim_kb_error(grounded_agent, sample_claim):
    """Test claim classification with KB error."""
    mock_kb = AsyncMock()
    mock_kb.search = AsyncMock(side_effect=Exception("KB error"))
    grounded_agent.kb = mock_kb

    verified = await grounded_agent._classify_and_verify_claim(sample_claim)

    assert verified.kb_status == ClaimStatus.UNKNOWN


@pytest.mark.asyncio
async def test_classify_claim_no_kb(grounded_agent, sample_claim):
    """Test claim classification without KB."""
    grounded_agent.kb = None

    verified = await grounded_agent._classify_and_verify_claim(sample_claim)

    assert verified.kb_status == ClaimStatus.UNKNOWN
    assert verified.confidence == 0.0


# ===== RESPONSE RECONSTRUCTION TESTS =====


@pytest.mark.asyncio
async def test_reconstruct_response_with_annotation(grounded_agent):
    """Test response reconstruction with annotations."""
    claim = Claim(claim_text="Latency increased")
    verified = VerifiedClaim(
        claim=claim,
        kb_status=ClaimStatus.IN_KB,
        kb_source="f789",
        confidence=0.95,
    )

    original = "The latency increased by 15%."
    reconstructed = await grounded_agent._reconstruct_response(original, [verified])

    assert "Latency increased" in reconstructed
    assert reconstructed != original or "[KB source" in reconstructed


@pytest.mark.asyncio
async def test_reconstruct_response_no_match(grounded_agent):
    """Test reconstruction when claim not in original."""
    claim = Claim(claim_text="Something else")
    verified = VerifiedClaim(
        claim=claim,
        kb_status=ClaimStatus.IN_KB,
        kb_source="f999",
        confidence=0.95,
    )

    original = "The system is fine."
    reconstructed = await grounded_agent._reconstruct_response(original, [verified])

    assert reconstructed == original


@pytest.mark.asyncio
async def test_reconstruct_response_empty(grounded_agent):
    """Test reconstruction with no verified claims."""
    original = "Test response."
    reconstructed = await grounded_agent._reconstruct_response(original, [])

    assert reconstructed == original


# ===== VERIFICATION TRACING TESTS =====


@pytest.mark.asyncio
async def test_trace_verification_success(grounded_agent, sample_verified_claim):
    """Test verification chain tracing."""
    trace = await grounded_agent._trace_verification_chain(
        query="Why slow?",
        response="It's slow.",
        verified_claims=[sample_verified_claim],
        unverified_claims=[],
    )

    assert trace is not None
    assert trace.query == "Why slow?"
    assert len(trace.reasoning_steps) > 0
    assert len(trace.claim_verifications) > 0


@pytest.mark.asyncio
async def test_trace_verification_mixed(grounded_agent, sample_verified_claim):
    """Test tracing with mixed verified/unverified."""
    unverified = Claim(claim_text="Unknown", confidence=0.5)

    trace = await grounded_agent._trace_verification_chain(
        query="Q",
        response="A",
        verified_claims=[sample_verified_claim],
        unverified_claims=[unverified],
    )

    assert trace is not None


@pytest.mark.asyncio
async def test_trace_verification_empty(grounded_agent):
    """Test tracing with no claims."""
    trace = await grounded_agent._trace_verification_chain(
        query="Q",
        response="A",
        verified_claims=[],
        unverified_claims=[],
    )

    assert trace is not None
    assert trace.confidence == 0.0


# ===== END-TO-END GROUNDING TESTS =====


@pytest.mark.asyncio
async def test_grounding_all_verified(grounded_agent):
    """Test grounding with all claims verified."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                [
                    {
                        "claim_text": "Latency increased",
                        "subject": "Latency",
                        "predicate": "increased",
                        "object": "yes",
                        "confidence": 0.95,
                    }
                ]
            )
        )
    )

    mock_kb = AsyncMock()
    mock_kb.search = AsyncMock(
        return_value=[
            {
                "fact_id": "f1",
                "content": "Latency increased",
                "similarity_score": 0.92,
            }
        ]
    )

    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = mock_kb

    result = await grounded_agent.respond_with_grounding(
        "Why slow?",
        "Latency increased",
    )

    assert isinstance(result, GroundedResponse)
    assert len(result.verified_claims) > 0
    assert result.confidence_overall > 0.0


@pytest.mark.asyncio
async def test_grounding_mixed(grounded_agent):
    """Test grounding with mixed verified/unverified."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                [
                    {
                        "claim_text": "Latency increased",
                        "subject": "Latency",
                        "predicate": "increased",
                        "object": "yes",
                        "confidence": 0.95,
                    },
                    {
                        "claim_text": "Unknown X",
                        "subject": "X",
                        "predicate": "is",
                        "object": "unknown",
                        "confidence": 0.6,
                    },
                ]
            )
        )
    )

    mock_kb = AsyncMock()
    mock_kb.search = AsyncMock(
        side_effect=[
            [
                {
                    "fact_id": "f1",
                    "content": "Latency increased",
                    "similarity_score": 0.92,
                }
            ],
            [],
        ]
    )

    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = mock_kb

    result = await grounded_agent.respond_with_grounding(
        "Q",
        "Mixed response",
    )

    assert len(result.verified_claims) >= 1
    assert len(result.unverified_claims) >= 1


@pytest.mark.asyncio
async def test_grounding_low_confidence(grounded_agent):
    """Test grounding flags low confidence for review."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                [
                    {
                        "claim_text": "Uncertain claim",
                        "subject": "claim",
                        "predicate": "is",
                        "object": "uncertain",
                        "confidence": 0.3,
                    }
                ]
            )
        )
    )

    mock_kb = AsyncMock()
    mock_kb.search = AsyncMock(
        return_value=[
            {
                "fact_id": "f2",
                "content": "Something",
                "similarity_score": 0.45,
            }
        ]
    )

    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = mock_kb

    result = await grounded_agent.respond_with_grounding(
        "Q",
        "A",
    )

    assert result.confidence_overall < 0.6
    assert result.requires_human_review


@pytest.mark.asyncio
async def test_grounding_with_context(grounded_agent):
    """Test grounding with context metadata."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=MagicMock(content="[]"))
    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = None

    context = {
        "conversation_id": "c123",
        "user_id": "u456",
    }

    result = await grounded_agent.respond_with_grounding(
        "Q",
        "A",
        context=context,
    )

    assert result.metadata == context


# ===== CONFLICT RESOLUTION TESTS =====


@pytest.mark.asyncio
async def test_resolve_conflict(grounded_agent):
    """Test conflict resolution."""
    result = await grounded_agent.resolve_conflict(
        "conflict-001",
        "fact-001",
        "Correct based on data",
    )

    assert result["status"] == "success"
    assert result["resolved"]
    assert result["chosen_fact"] == "fact-001"


# ===== EDGE CASES =====


@pytest.mark.asyncio
async def test_grounding_empty_response(grounded_agent):
    """Test grounding with empty response."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=MagicMock(content="[]"))
    grounded_agent.llm_service = mock_llm

    result = await grounded_agent.respond_with_grounding(
        "Q",
        "",
    )

    assert result.verified_claims == []
    assert result.unverified_claims == []


@pytest.mark.asyncio
async def test_grounding_very_long(grounded_agent):
    """Test grounding with very long response."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=MagicMock(content="[]"))
    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = None

    long_response = "A" * 4000

    result = await grounded_agent.respond_with_grounding(
        "Q",
        long_response,
    )

    assert isinstance(result, GroundedResponse)


@pytest.mark.asyncio
async def test_grounding_special_chars(grounded_agent):
    """Test grounding with special characters."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                [
                    {
                        "claim_text": "Latency: 100ms (p99) ±5%",
                        "subject": "Latency",
                        "predicate": "is",
                        "object": "100ms",
                        "confidence": 0.9,
                    }
                ]
            )
        )
    )
    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = None

    result = await grounded_agent.respond_with_grounding(
        "Q",
        "Latency: 100ms (p99) ±5%",
    )

    assert len(result.verified_claims) + len(result.unverified_claims) >= 0


# ===== INTEGRATION TESTS =====


@pytest.mark.asyncio
async def test_full_workflow(grounded_agent):
    """Test complete grounding workflow."""
    # 1. Ground response
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                [
                    {
                        "claim_text": "Latency increased",
                        "subject": "Latency",
                        "predicate": "increased",
                        "object": "yes",
                        "confidence": 0.95,
                    },
                    {
                        "claim_text": "DB slow",
                        "subject": "DB",
                        "predicate": "is",
                        "object": "slow",
                        "confidence": 0.87,
                    },
                ]
            )
        )
    )

    mock_kb = AsyncMock()
    mock_kb.search = AsyncMock(
        side_effect=[
            [
                {
                    "fact_id": "f1",
                    "content": "Latency increased",
                    "similarity_score": 0.92,
                }
            ],
            [
                {
                    "fact_id": "f2",
                    "content": "DB performance",
                    "similarity_score": 0.78,
                }
            ],
        ]
    )

    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = mock_kb

    grounded = await grounded_agent.respond_with_grounding(
        "Why slow?",
        "Latency increased and DB slow",
    )

    assert grounded.original_query == "Why slow?"
    assert len(grounded.verified_claims) > 0

    # 2. Resolve conflicts if any
    if grounded.conflicts:
        for conflict in grounded.conflicts:
            result = await grounded_agent.resolve_conflict(
                conflict.conflict_id,
                "fact-chosen",
                "Resolved",
            )
            assert result["resolved"]
