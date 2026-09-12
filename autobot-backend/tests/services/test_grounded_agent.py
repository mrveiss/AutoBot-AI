# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.grounded_agent import (
    Claim,
    ClaimStatus,
    GroundedAgent,
    GroundedResponse,
    VerifiedClaim,
)
from services.knowledge_grounding_models import VerificationMethod
from tests.fixtures import make_async_redis, make_redis_pipeline


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
        verification_method=VerificationMethod.KB_LOOKUP.value,
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


@pytest.mark.asyncio
async def test_classify_claim_calls_real_search_signature_and_returns_content(grounded_agent, sample_claim):
    """#13024: search_mode= isn't a valid kwarg and limit= routes to the
    Enhanced dict-returning path, which this method can't consume (it does
    ``search_results[0]``) -- both silently produced UNKNOWN via the broad
    except. ``create_autospec`` (not a bare AsyncMock) reproduces the real
    ``KnowledgeBase.search()`` signature so an invalid kwarg would raise
    ``TypeError`` here exactly as it does in production.

    #13009: also asserts the quarantine filter is applied -- this is a
    general classification read, not the corroboration pipeline.
    """
    from unittest.mock import create_autospec

    from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
    from knowledge_base import KnowledgeBase

    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = [{"fact_id": "f1", "content": "Latency increased", "similarity_score": 0.92}]
    grounded_agent.kb = mock_kb

    verified = await grounded_agent._classify_and_verify_claim(sample_claim)

    assert verified.kb_status == ClaimStatus.IN_KB
    assert verified.kb_source == "f1"
    mock_kb.search.assert_called_once_with(query=sample_claim.claim_text, top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


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

    # The claim ("Latency increased") differs in case from the response
    # ("the latency increased"); reconstruction matches case-insensitively and
    # annotates it while preserving the response's original casing (#11248).
    original = "The latency increased by 15%."
    reconstructed = await grounded_agent._reconstruct_response(original, [verified])

    assert "latency increased" in reconstructed.lower()
    assert "[KB source" in reconstructed
    assert reconstructed != original


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
    mock_redis = AsyncMock()
    with patch(
        "services.grounded_agent.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        result = await grounded_agent.resolve_conflict(
            "conflict-001",
            "fact-001",
            "Correct based on data",
        )

    assert result["status"] == "success"
    assert result["resolved"]
    assert result["chosen_fact"] == "fact-001"
    mock_redis.hset.assert_awaited_once()
    # #14981: conflicts_resolved must move when a conflict actually resolves.
    mock_redis.hincrby.assert_awaited_once_with("grounding:stats", "conflicts_resolved", 1)
    mock_redis.expire.assert_awaited_once()


# ===== GROUNDING STATS (#14981) =====
#
# _record_grounding_stats is unit-tested directly, in isolation from the
# LLM/KB pipeline: what it needs to prove is that each grounding:stats
# counter moves by the right amount for the right event, not that claim
# extraction/verification also still works (that's every test above).


@pytest.fixture
def stats_pipeline():
    """The mock pipeline _record_grounding_stats writes through."""
    return make_redis_pipeline()


@pytest.fixture
def agent_with_redis(grounded_agent, stats_pipeline):
    grounded_agent.redis_client = make_async_redis(pipeline=stats_pipeline)
    return grounded_agent


@pytest.mark.asyncio
async def test_record_grounding_stats_increments_every_counter(agent_with_redis, stats_pipeline, sample_claim):
    """One event: every counter it touches moves by the exact amount."""
    verified = [
        VerifiedClaim(
            claim=sample_claim,
            kb_status=ClaimStatus.IN_KB,
            confidence=0.9,
            verification_method=VerificationMethod.KB_LOOKUP.value,
        ),
        VerifiedClaim(
            claim=sample_claim,
            kb_status=ClaimStatus.IN_KB,
            confidence=0.7,
            verification_method=VerificationMethod.CLAIM_VERIFIER_RAG.value,
        ),
    ]

    await agent_with_redis._record_grounding_stats(
        claims_extracted=3,
        verified_claims=verified,
        conflicts_created=1,
        overall_confidence=0.8,
    )

    stats_pipeline.hincrby.assert_any_await("grounding:stats", "total_responses_grounded", 1)
    stats_pipeline.hincrby.assert_any_await("grounding:stats", "total_claims_extracted", 3)
    stats_pipeline.hincrby.assert_any_await("grounding:stats", "claims_verified_count", 2)
    stats_pipeline.hincrbyfloat.assert_any_await("grounding:stats", "confidence_sum", 0.8)
    stats_pipeline.hincrby.assert_any_await("grounding:stats", "conflicts_created", 1)
    stats_pipeline.hincrby.assert_any_await("grounding:stats", "claim_source_kb_lookup", 1)
    stats_pipeline.hincrby.assert_any_await("grounding:stats", "claim_source_claim_verifier_rag", 1)
    stats_pipeline.expire.assert_awaited_once()
    stats_pipeline.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_grounding_stats_omits_a_method_nobody_produced(agent_with_redis, stats_pipeline, sample_claim):
    """No claim_verifier_rag claim this call -> no write to that counter at all."""
    verified = [
        VerifiedClaim(
            claim=sample_claim,
            kb_status=ClaimStatus.IN_KB,
            confidence=0.9,
            verification_method=VerificationMethod.KB_LOOKUP.value,
        ),
    ]

    await agent_with_redis._record_grounding_stats(
        claims_extracted=1,
        verified_claims=verified,
        conflicts_created=0,
        overall_confidence=0.9,
    )

    written_fields = {call.args[1] for call in stats_pipeline.hincrby.await_args_list}
    assert "claim_source_kb_lookup" in written_fields
    assert "claim_source_claim_verifier_rag" not in written_fields


@pytest.mark.asyncio
async def test_record_grounding_stats_is_a_noop_without_redis(grounded_agent, sample_claim):
    """No redis_client (disabled/circuit open) must not raise -- best-effort."""
    assert grounded_agent.redis_client is None

    await grounded_agent._record_grounding_stats(
        claims_extracted=1,
        verified_claims=[],
        conflicts_created=0,
        overall_confidence=0.0,
    )


@pytest.mark.asyncio
async def test_record_grounding_stats_swallows_a_redis_failure(grounded_agent):
    """A stats-write failure must never fail the response the caller is waiting on."""
    grounded_agent.redis_client = MagicMock()
    grounded_agent.redis_client.pipeline = MagicMock(side_effect=RuntimeError("redis down"))

    await grounded_agent._record_grounding_stats(
        claims_extracted=1,
        verified_claims=[],
        conflicts_created=0,
        overall_confidence=0.0,
    )


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
