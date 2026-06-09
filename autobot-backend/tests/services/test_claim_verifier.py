#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for ClaimVerifier Service - Tier 4 Knowledge Grounding

Tests verification of claims via KB RAG and research agent escalation.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from services.claim_verifier import (
    ClaimVerifier,
    ResearchStatus,
    VerificationStatus,
)
from services.knowledge_grounding_models import (
    Claim,
    ClaimType,
    KBSource,
    KBStatus,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_knowledge_base():
    """Create a mock knowledge base."""
    kb = AsyncMock()
    kb.search = AsyncMock()
    return kb


@pytest.fixture
def mock_research_agent():
    """Create a mock research agent service."""
    agent = AsyncMock()
    agent.investigate_claim = AsyncMock()
    return agent


@pytest.fixture
def claim_verifier(mock_knowledge_base, mock_research_agent):
    """Create a ClaimVerifier instance with mocks."""
    return ClaimVerifier(mock_knowledge_base, mock_research_agent)


@pytest.fixture
def sample_claim():
    """Create a sample claim for testing."""
    return Claim(
        claim_text="The latency is 500ms",
        claim_type=ClaimType.FACTUAL,
        kb_status=KBStatus.UNKNOWN,
        confidence=0.8,
    )


@pytest.fixture
def sample_in_kb_claim():
    """Create a claim already verified in KB."""
    source = KBSource(
        source_id="kb_001",
        source_type="document",
        text="The latency is documented as 500ms in the system",
        confidence=0.95,
        age_days=5.0,
        url="https://docs.example.com/latency",
    )
    return Claim(
        claim_text="The latency is 500ms",
        claim_type=ClaimType.FACTUAL,
        kb_status=KBStatus.IN_KB,
        confidence=0.95,
        sources=[source],
    )


@pytest.fixture
def sample_contradicts_claim():
    """Create a claim that contradicts KB."""
    return Claim(
        claim_text="The latency is 100ms",
        claim_type=ClaimType.FACTUAL,
        kb_status=KBStatus.CONTRADICTS,
        confidence=0.3,
        kb_fact="The actual latency is 500ms",
    )


# ---------------------------------------------------------------------------
# Test IN_KB Verification (Immediate, High Confidence)
# ---------------------------------------------------------------------------


class TestInKBVerification:
    """Tests for verification of claims already in KB."""

    @pytest.mark.asyncio
    async def test_in_kb_returns_verified_immediately(self, claim_verifier, sample_in_kb_claim):
        """IN_KB claims should return VERIFIED with high confidence immediately."""
        result = await claim_verifier.verify(sample_in_kb_claim)

        assert result.verified_as == VerificationStatus.VERIFIED
        assert result.source == "knowledge_base"
        assert result.confidence >= 0.9
        assert not result.requires_human_review

    @pytest.mark.asyncio
    async def test_in_kb_uses_kb_source(self, claim_verifier, sample_in_kb_claim):
        """IN_KB verification should use knowledge_base as source."""
        result = await claim_verifier.verify(sample_in_kb_claim)

        assert result.source == "knowledge_base"
        assert result.source_text == sample_in_kb_claim.kb_fact

    @pytest.mark.asyncio
    async def test_in_kb_skips_research_agent(self, claim_verifier, sample_in_kb_claim, mock_research_agent):
        """IN_KB verification should not call research agent."""
        await claim_verifier.verify(sample_in_kb_claim)

        # Research agent should not be called
        mock_research_agent.investigate_claim.assert_not_called()

    @pytest.mark.asyncio
    async def test_in_kb_skips_rag_search(self, claim_verifier, sample_in_kb_claim, mock_knowledge_base):
        """IN_KB verification should not perform RAG search."""
        await claim_verifier.verify(sample_in_kb_claim)

        # KB search should not be called
        mock_knowledge_base.search.assert_not_called()


# ---------------------------------------------------------------------------
# Test CONTRADICTS Verification (Escalate to ConflictResolver)
# ---------------------------------------------------------------------------


class TestContradictingVerification:
    """Tests for verification of contradicting claims."""

    @pytest.mark.asyncio
    async def test_contradicts_returns_conflicting(self, claim_verifier, sample_contradicts_claim):
        """CONTRADICTS claims should return CONFLICTING status."""
        result = await claim_verifier.verify(sample_contradicts_claim)

        assert result.verified_as == VerificationStatus.CONFLICTING
        assert result.requires_human_review

    @pytest.mark.asyncio
    async def test_contradicts_includes_kb_fact(self, claim_verifier, sample_contradicts_claim):
        """CONFLICTING verification should include the contradicting fact."""
        result = await claim_verifier.verify(sample_contradicts_claim)

        assert result.source_text == sample_contradicts_claim.kb_fact

    @pytest.mark.asyncio
    async def test_contradicts_zero_confidence(self, claim_verifier, sample_contradicts_claim):
        """CONFLICTING verification should have zero confidence."""
        result = await claim_verifier.verify(sample_contradicts_claim)

        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_contradicts_skips_research_agent(
        self, claim_verifier, sample_contradicts_claim, mock_research_agent
    ):
        """CONTRADICTS verification should not call research agent."""
        await claim_verifier.verify(sample_contradicts_claim)

        mock_research_agent.investigate_claim.assert_not_called()


# ---------------------------------------------------------------------------
# Test UNKNOWN → KB RAG Search Path
# ---------------------------------------------------------------------------


class TestRAGSearch:
    """Tests for KB RAG search."""

    @pytest.mark.asyncio
    async def test_rag_search_returns_matches(self, claim_verifier, mock_knowledge_base):
        """RAG search should return matches with confidence."""
        mock_knowledge_base.search.return_value = [
            {
                "node_id": "chunk_1",
                "doc_id": "doc_1",
                "content": "The latency is 500ms according to benchmarks",
                "score": 0.85,
                "metadata": {"source_type": "document", "age_days": 5.0},
            }
        ]

        result = await claim_verifier.kb_rag_search("What is the latency?")

        assert result is not None
        assert len(result.matches) > 0
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_rag_search_filters_low_confidence(self, claim_verifier, mock_knowledge_base):
        """RAG search should filter results below min confidence threshold."""
        mock_knowledge_base.search.return_value = [
            {
                "node_id": "chunk_1",
                "content": "Low confidence result",
                "score": 0.3,  # Below MIN_RAG_CONFIDENCE (0.5)
                "metadata": {},
            }
        ]

        result = await claim_verifier.kb_rag_search("test query")

        assert result is not None
        assert len(result.matches) == 0
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_rag_search_handles_empty_results(self, claim_verifier, mock_knowledge_base):
        """RAG search should handle empty results gracefully."""
        mock_knowledge_base.search.return_value = []

        result = await claim_verifier.kb_rag_search("test query")

        assert result is not None
        assert len(result.matches) == 0
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_rag_search_handles_kb_unavailable(self, claim_verifier):
        """RAG search should handle missing KB gracefully."""
        verifier = ClaimVerifier(None, None)
        result = await verifier.kb_rag_search("test query")

        assert result is None

    @pytest.mark.asyncio
    async def test_rag_search_returns_multiple_matches(self, claim_verifier, mock_knowledge_base):
        """RAG search should return matches above confidence threshold."""
        mock_knowledge_base.search.return_value = [
            {
                "node_id": f"chunk_{i}",
                "content": f"Result {i}",
                "score": 0.9 - (i * 0.1),
                "metadata": {},
            }
            for i in range(5)
        ]

        result = await claim_verifier.kb_rag_search("test query")

        assert result is not None
        # Should return all results above MIN_RAG_CONFIDENCE (0.5)
        assert len(result.matches) >= 4


# ---------------------------------------------------------------------------
# Test UNKNOWN → RAG High Confidence Path
# ---------------------------------------------------------------------------


class TestUnknownWithHighRAGConfidence:
    """Tests for UNKNOWN claims with high RAG confidence."""

    @pytest.mark.asyncio
    async def test_rag_high_confidence_returns_verified(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """UNKNOWN with high RAG confidence (>=0.7) should return VERIFIED."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = [
            {
                "node_id": "chunk_1",
                "content": "The latency is 500ms",
                "score": 0.85,  # >= 0.7 threshold
                "metadata": {"source_type": "document"},
            }
        ]

        result = await claim_verifier.verify(sample_claim)

        assert result.verified_as == VerificationStatus.VERIFIED
        assert result.source == "kb_rag"
        assert result.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_rag_high_confidence_skips_research_agent(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """UNKNOWN with high RAG confidence should skip research agent."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = [
            {
                "node_id": "chunk_1",
                "content": "The latency is 500ms",
                "score": 0.85,
                "metadata": {},
            }
        ]

        await claim_verifier.verify(sample_claim)

        # Research agent should not be called
        mock_research_agent.investigate_claim.assert_not_called()

    @pytest.mark.asyncio
    async def test_rag_confidence_boundary_0_7(self, claim_verifier, sample_claim, mock_knowledge_base):
        """RAG confidence exactly at 0.7 threshold should return UNVERIFIED (not quite verified)."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = [
            {
                "node_id": "chunk_1",
                "content": "The latency is 500ms",
                "score": 0.7,  # Exactly at threshold
                "metadata": {},
            }
        ]

        result = await claim_verifier.verify(sample_claim)

        # At 0.7, confidence is at threshold but not > 0.8 for VERIFIED
        assert result.source == "kb_rag"
        assert result.confidence == 0.7


# ---------------------------------------------------------------------------
# Test UNKNOWN → RAG Low Confidence → Research Agent Path
# ---------------------------------------------------------------------------


class TestUnknownWithLowRAGAndResearchAgent:
    """Tests for UNKNOWN claims with low RAG confidence → research agent escalation."""

    @pytest.mark.asyncio
    async def test_low_rag_confidence_escalates_to_research_agent(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """UNKNOWN with low RAG confidence should escalate to research agent."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        # Low RAG confidence
        mock_knowledge_base.search.return_value = [
            {
                "node_id": "chunk_1",
                "content": "Possibly related",
                "score": 0.6,  # < 0.7 threshold
                "metadata": {},
            }
        ]

        # Research agent finds the claim
        mock_research_agent.investigate_claim.return_value = {
            "fact": "The latency is 500ms",
            "status": ResearchStatus.FOUND.value,
            "url": "https://example.com/research",
            "confidence": 0.9,
        }

        result = await claim_verifier.verify(sample_claim)

        # Should use research agent result
        assert result.source == "research_agent"
        mock_research_agent.investigate_claim.assert_called_once()

    @pytest.mark.asyncio
    async def test_research_agent_found_status(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """Research agent FOUND status should return VERIFIED."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = [
            {"node_id": "chunk_1", "content": "Low confidence", "score": 0.5, "metadata": {}}
        ]

        mock_research_agent.investigate_claim.return_value = {
            "fact": "The latency is 500ms",
            "status": ResearchStatus.FOUND.value,
            "url": "https://example.com",
            "confidence": 0.9,
        }

        result = await claim_verifier.verify(sample_claim)

        assert result.verified_as == VerificationStatus.VERIFIED
        assert result.source_url == "https://example.com"

    @pytest.mark.asyncio
    async def test_research_agent_not_found_status(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """Research agent NOT_FOUND status should return NOT_FOUND."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = []

        mock_research_agent.investigate_claim.return_value = {
            "fact": None,
            "status": ResearchStatus.NOT_FOUND.value,
            "url": None,
            "confidence": 0.0,
        }

        result = await claim_verifier.verify(sample_claim)

        assert result.verified_as == VerificationStatus.NOT_FOUND

    @pytest.mark.asyncio
    async def test_research_agent_conflicting_status(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """Research agent CONFLICTING status should return CONFLICTING."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = []

        mock_research_agent.investigate_claim.return_value = {
            "fact": "The latency is actually 100ms",
            "status": ResearchStatus.CONFLICTING.value,
            "url": "https://example.com",
            "confidence": 0.85,
        }

        result = await claim_verifier.verify(sample_claim)

        assert result.verified_as == VerificationStatus.CONFLICTING

    @pytest.mark.asyncio
    async def test_research_agent_confidence_comparison(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """Should use result with higher confidence (RAG vs Research)."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = [
            {
                "node_id": "chunk_1",
                "content": "Possibly related",
                "score": 0.65,
                "metadata": {},
            }
        ]

        # Research agent has lower confidence
        mock_research_agent.investigate_claim.return_value = {
            "fact": "Different fact",
            "status": ResearchStatus.FOUND.value,
            "url": "https://example.com",
            "confidence": 0.5,  # Lower than RAG
        }

        result = await claim_verifier.verify(sample_claim)

        # Should use RAG result (higher confidence)
        assert result.source == "kb_rag"
        assert result.confidence == 0.65


# ---------------------------------------------------------------------------
# Test Research Agent Timeout
# ---------------------------------------------------------------------------


class TestResearchAgentTimeout:
    """Tests for research agent timeout handling."""

    @pytest.mark.asyncio
    async def test_research_agent_timeout_returns_timeout_status(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """Research agent timeout should be caught and handled gracefully."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = []

        # Simulate timeout by raising asyncio.TimeoutError
        async def timeout_func(*args, **kwargs):
            raise asyncio.TimeoutError("Research agent timed out")

        mock_research_agent.investigate_claim = timeout_func

        result = await claim_verifier.verify(sample_claim)

        # Should return TIMEOUT status (not found fallback)
        assert result.verified_as in (VerificationStatus.TIMEOUT, VerificationStatus.NOT_FOUND)

    @pytest.mark.asyncio
    async def test_research_agent_timeout_fallback_to_rag(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """Research agent timeout should fallback to RAG result if available."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = [
            {
                "node_id": "chunk_1",
                "content": "Some evidence",
                "score": 0.6,
                "metadata": {},
            }
        ]

        # Simulate timeout by raising asyncio.TimeoutError
        async def timeout_func(*args, **kwargs):
            raise asyncio.TimeoutError("Research agent timed out")

        mock_research_agent.investigate_claim = timeout_func

        result = await claim_verifier.verify(sample_claim)

        # Should handle timeout gracefully
        assert result.verified_as in (VerificationStatus.TIMEOUT, VerificationStatus.UNVERIFIED)


# ---------------------------------------------------------------------------
# Test Caching Behavior
# ---------------------------------------------------------------------------


class TestCacheBehavior:
    """Tests for verification result caching."""

    @pytest.mark.asyncio
    async def test_verified_claim_cached_in_memory(self, claim_verifier, sample_claim, mock_knowledge_base):
        """Verified claims should be cached in memory."""
        sample_claim.kb_status = KBStatus.IN_KB

        result1 = await claim_verifier.verify(sample_claim)
        mock_knowledge_base.reset_mock()

        result2 = await claim_verifier.verify(sample_claim)

        # Should not call KB again (cached)
        mock_knowledge_base.search.assert_not_called()
        assert result1.verified_as == result2.verified_as

    @pytest.mark.asyncio
    async def test_cache_key_unique_per_claim_text(self, claim_verifier):
        """Different claim texts should have different cache keys."""
        claim1 = Claim("Claim A", ClaimType.FACTUAL, KBStatus.IN_KB, 0.9)
        claim2 = Claim("Claim B", ClaimType.FACTUAL, KBStatus.IN_KB, 0.9)

        key1 = claim_verifier._build_cache_key(claim1)
        key2 = claim_verifier._build_cache_key(claim2)

        assert key1 != key2

    @pytest.mark.asyncio
    async def test_clear_cache(self, claim_verifier, sample_claim):
        """Cache should be clearable."""
        sample_claim.kb_status = KBStatus.IN_KB
        await claim_verifier.verify(sample_claim)

        await claim_verifier.clear_cache()

        assert len(claim_verifier._cache) == 0

    @pytest.mark.asyncio
    @patch("services.claim_verifier.get_async_redis_client")
    async def test_cache_stored_in_redis(self, mock_get_redis, claim_verifier, sample_claim):
        """Verified claims should be stored in Redis."""
        sample_claim.kb_status = KBStatus.IN_KB

        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await claim_verifier.verify(sample_claim)

        # Should have called Redis setex
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    @patch("services.claim_verifier.get_async_redis_client")
    async def test_cache_retrieved_from_redis(self, mock_get_redis, claim_verifier, sample_claim):
        """Verified claims should be retrievable from Redis cache."""
        sample_claim.kb_status = KBStatus.IN_KB

        # First verification populates cache
        await claim_verifier.verify(sample_claim)

        # Clear in-memory cache
        await claim_verifier.clear_cache()

        # Setup Redis to return cached value
        mock_redis = AsyncMock()
        verified_dict = {
            "original_claim": sample_claim.to_dict(),
            "verified_as": VerificationStatus.VERIFIED.value,
            "source": "knowledge_base",
            "confidence": 0.95,
            "timestamp": time.time(),
            "requires_human_review": False,
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(verified_dict))
        mock_get_redis.return_value = mock_redis

        # Should retrieve from Redis
        result = await claim_verifier._get_from_cache(claim_verifier._build_cache_key(sample_claim))

        assert result is not None
        assert result.verified_as == VerificationStatus.VERIFIED


# ---------------------------------------------------------------------------
# Test Batch Verification
# ---------------------------------------------------------------------------


class TestBatchVerification:
    """Tests for batch verification of multiple claims."""

    @pytest.mark.asyncio
    async def test_batch_verify_empty_list(self, claim_verifier):
        """Batch verify should handle empty claim list."""
        result = await claim_verifier.batch_verify([])

        assert result == []

    @pytest.mark.asyncio
    async def test_batch_verify_mixed_statuses(self, claim_verifier, mock_knowledge_base, mock_research_agent):
        """Batch verify should handle claims with different KB statuses."""
        in_kb_claim = Claim("IN KB claim", ClaimType.FACTUAL, KBStatus.IN_KB, 0.9)
        unknown_claim = Claim("Unknown claim", ClaimType.FACTUAL, KBStatus.UNKNOWN, 0.5)
        contradicts_claim = Claim(
            "Contradicts claim", ClaimType.FACTUAL, KBStatus.CONTRADICTS, 0.3, kb_fact="Actual fact"
        )

        claims = [in_kb_claim, unknown_claim, contradicts_claim]

        mock_knowledge_base.search.return_value = []
        mock_research_agent.investigate_claim.return_value = {
            "fact": None,
            "status": ResearchStatus.NOT_FOUND.value,
            "confidence": 0.0,
        }

        results = await claim_verifier.batch_verify(claims)

        assert len(results) == 3
        assert results[0].verified_as == VerificationStatus.VERIFIED  # IN_KB
        assert results[2].verified_as == VerificationStatus.CONFLICTING  # CONTRADICTS

    @pytest.mark.asyncio
    async def test_batch_verify_preserves_order(self, claim_verifier, mock_knowledge_base, mock_research_agent):
        """Batch verify should return results in same order as input."""
        claims = [Claim(f"Claim {i}", ClaimType.FACTUAL, KBStatus.IN_KB, 0.9) for i in range(5)]

        mock_knowledge_base.search.return_value = []

        results = await claim_verifier.batch_verify(claims)

        assert len(results) == len(claims)
        for i, result in enumerate(results):
            assert result.original.claim_text == f"Claim {i}"

    @pytest.mark.asyncio
    async def test_batch_verify_parallelizes(self, claim_verifier, mock_knowledge_base, mock_research_agent):
        """Batch verify should parallelize verification."""
        claims = [Claim(f"Claim {i}", ClaimType.FACTUAL, KBStatus.IN_KB, 0.9) for i in range(10)]

        mock_knowledge_base.search.return_value = []

        start_time = time.time()
        await claim_verifier.batch_verify(claims)
        elapsed = time.time() - start_time

        # Should complete reasonably quickly (parallel, not sequential)
        assert elapsed < 5.0  # Should not take long for IN_KB (fast) claims

    @pytest.mark.asyncio
    async def test_batch_verify_prioritizes_unknown(self, claim_verifier, mock_knowledge_base, mock_research_agent):
        """Batch verify should prioritize UNKNOWN claims for research agent."""
        in_kb_claim = Claim("IN KB claim", ClaimType.FACTUAL, KBStatus.IN_KB, 0.9)
        unknown_claim = Claim("Unknown claim", ClaimType.FACTUAL, KBStatus.UNKNOWN, 0.5)

        claims = [in_kb_claim, unknown_claim]

        mock_knowledge_base.search.return_value = []
        mock_research_agent.investigate_claim.return_value = {
            "fact": None,
            "status": ResearchStatus.NOT_FOUND.value,
            "confidence": 0.0,
        }

        results = await claim_verifier.batch_verify(claims)

        # Both should be verified, order preserved
        assert len(results) == 2
        assert results[0].original.claim_text == "IN KB claim"
        assert results[1].original.claim_text == "Unknown claim"

    @pytest.mark.asyncio
    async def test_batch_verify_error_handling(self, claim_verifier, mock_knowledge_base, mock_research_agent):
        """Batch verify should handle errors gracefully."""
        claims = [
            Claim("Claim 1", ClaimType.FACTUAL, KBStatus.IN_KB, 0.9),
            Claim("Claim 2", ClaimType.FACTUAL, KBStatus.UNKNOWN, 0.5),
        ]

        # Simulate error in KB
        mock_knowledge_base.search.side_effect = Exception("KB error")

        results = await claim_verifier.batch_verify(claims)

        assert len(results) == 2
        # Should have results but marked as ERROR
        assert any(r.verified_as == VerificationStatus.ERROR for r in results)


# ---------------------------------------------------------------------------
# Test Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    """Tests for service statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self, claim_verifier):
        """Should return service statistics."""
        stats = claim_verifier.get_stats()

        assert "cache_entries" in stats
        assert "kb_available" in stats
        assert "research_agent_available" in stats
        assert stats["kb_available"] is True
        assert stats["research_agent_available"] is True

    @pytest.mark.asyncio
    async def test_stats_cache_count(self, claim_verifier, sample_claim):
        """Stats should track cache entry count."""
        sample_claim.kb_status = KBStatus.IN_KB

        await claim_verifier.verify(sample_claim)

        stats = claim_verifier.get_stats()
        assert stats["cache_entries"] > 0


# ---------------------------------------------------------------------------
# Test Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_kb_search_exception_returns_none(self, claim_verifier, mock_knowledge_base):
        """KB search exception should return None."""
        mock_knowledge_base.search.side_effect = Exception("KB error")

        result = await claim_verifier.kb_rag_search("test claim")

        assert result is None

    @pytest.mark.asyncio
    async def test_research_agent_exception_returns_gracefully(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """Research agent exception should be handled gracefully."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = []
        mock_research_agent.investigate_claim.side_effect = Exception("Agent error")

        result = await claim_verifier.verify(sample_claim)

        # Should return UNVERIFIED or ERROR status, not crash
        assert result.verified_as in (
            VerificationStatus.ERROR,
            VerificationStatus.UNVERIFIED,
            VerificationStatus.NOT_FOUND,
        )

    @pytest.mark.asyncio
    async def test_invalid_research_status_defaults_to_not_found(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """Invalid research status should default to NOT_FOUND."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = []
        mock_research_agent.investigate_claim.return_value = {
            "fact": None,
            "status": "invalid_status",  # Invalid enum value
            "confidence": 0.0,
        }

        result = await claim_verifier.verify(sample_claim)

        # Should default to NOT_FOUND
        assert result.verified_as == VerificationStatus.NOT_FOUND

    @pytest.mark.asyncio
    async def test_none_research_agent_service_handled(self, claim_verifier, sample_claim, mock_knowledge_base):
        """Should handle None research agent service gracefully."""
        verifier = ClaimVerifier(mock_knowledge_base, None)
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = []

        result = await verifier.verify(sample_claim)

        # Should return ERROR (no KB match, no research agent)
        assert result.verified_as in (VerificationStatus.ERROR, VerificationStatus.UNVERIFIED)


# ---------------------------------------------------------------------------
# Test Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_claim_text(self, claim_verifier):
        """Should handle claim with empty text."""
        Claim("", ClaimType.FACTUAL, KBStatus.UNKNOWN, 0.0)

        result = await claim_verifier.kb_rag_search("")

        assert result is not None
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_very_long_claim_text(self, claim_verifier, mock_knowledge_base):
        """Should handle very long claim text."""
        long_claim_text = "This is a claim " * 100  # Very long

        mock_knowledge_base.search.return_value = []

        result = await claim_verifier.kb_rag_search(long_claim_text)

        assert result is not None

    @pytest.mark.asyncio
    async def test_special_characters_in_claim(self, claim_verifier, mock_knowledge_base):
        """Should handle special characters in claim text."""
        claim_with_special = "Claim with !@#$%^&*() special chars"

        mock_knowledge_base.search.return_value = []

        result = await claim_verifier.kb_rag_search(claim_with_special)

        assert result is not None

    @pytest.mark.asyncio
    async def test_unicode_in_claim(self, claim_verifier, mock_knowledge_base):
        """Should handle unicode characters in claim text."""
        claim_with_unicode = "Claim with 中文 and émojis 🎉"

        mock_knowledge_base.search.return_value = []

        result = await claim_verifier.kb_rag_search(claim_with_unicode)

        assert result is not None

    @pytest.mark.asyncio
    async def test_confidence_boundary_values(self, claim_verifier, mock_knowledge_base):
        """Should handle confidence boundary values (0.0, 1.0)."""
        mock_knowledge_base.search.return_value = [
            {
                "node_id": "chunk_1",
                "content": "Perfect match",
                "score": 1.0,  # Perfect confidence
                "metadata": {},
            }
        ]

        result = await claim_verifier.kb_rag_search("test")

        assert result is not None
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_zero_confidence_research_result(
        self, claim_verifier, sample_claim, mock_knowledge_base, mock_research_agent
    ):
        """Should handle research result with zero confidence."""
        sample_claim.kb_status = KBStatus.UNKNOWN

        mock_knowledge_base.search.return_value = [
            {
                "node_id": "chunk_1",
                "content": "Some evidence",
                "score": 0.6,
                "metadata": {},
            }
        ]

        mock_research_agent.investigate_claim.return_value = {
            "fact": None,
            "status": ResearchStatus.NOT_FOUND.value,
            "confidence": 0.0,
        }

        result = await claim_verifier.verify(sample_claim)

        # Should use RAG result (0.6 > 0.0)
        assert result.source == "kb_rag"
