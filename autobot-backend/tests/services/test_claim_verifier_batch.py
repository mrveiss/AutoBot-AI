#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Batch verification tests of the ClaimVerifier service (split from test_claim_verifier.py, #16665).
"""

import time
from unittest.mock import AsyncMock

import pytest

from knowledge.ownership import KnowledgeOwnership
from services.claim_verifier import (
    ClaimVerifier,
    ResearchStatus,
)
from services.knowledge_grounding_models import (
    Claim,
    ClaimType,
    KBSource,
    KBStatus,
    VerificationStatus,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_knowledge_base():
    """Create a mock knowledge base."""
    kb = AsyncMock()
    kb.search = AsyncMock()
    kb.ownership_manager = KnowledgeOwnership(None)  # #16665: the real visibility decision
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

        results = await claim_verifier.batch_verify(claims, "alice")

        assert len(results) == 3
        assert results[0].verified_as == VerificationStatus.VERIFIED  # IN_KB
        assert results[2].verified_as == VerificationStatus.CONFLICTING  # CONTRADICTS

    @pytest.mark.asyncio
    async def test_batch_verify_preserves_order(self, claim_verifier, mock_knowledge_base, mock_research_agent):
        """Batch verify should return results in same order as input."""
        claims = [Claim(f"Claim {i}", ClaimType.FACTUAL, KBStatus.IN_KB, 0.9) for i in range(5)]

        mock_knowledge_base.search.return_value = []

        results = await claim_verifier.batch_verify(claims, "alice")

        assert len(results) == len(claims)
        for i, result in enumerate(results):
            assert result.claim.claim_text == f"Claim {i}"

    @pytest.mark.asyncio
    async def test_batch_verify_parallelizes(self, claim_verifier, mock_knowledge_base, mock_research_agent):
        """Batch verify should parallelize verification."""
        claims = [Claim(f"Claim {i}", ClaimType.FACTUAL, KBStatus.IN_KB, 0.9) for i in range(10)]

        mock_knowledge_base.search.return_value = []

        start_time = time.time()
        await claim_verifier.batch_verify(claims, "alice")
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

        results = await claim_verifier.batch_verify(claims, "alice")

        # Both should be verified, order preserved
        assert len(results) == 2
        assert results[0].claim.claim_text == "IN KB claim"
        assert results[1].claim.claim_text == "Unknown claim"

    @pytest.mark.asyncio
    async def test_batch_verify_error_handling(self, claim_verifier, mock_knowledge_base, mock_research_agent):
        """Batch verify should handle errors gracefully."""
        claims = [
            Claim("Claim 1", ClaimType.FACTUAL, KBStatus.IN_KB, 0.9),
            Claim("Claim 2", ClaimType.FACTUAL, KBStatus.UNKNOWN, 0.5),
        ]

        # Simulate error in KB
        mock_knowledge_base.search.side_effect = Exception("KB error")

        results = await claim_verifier.batch_verify(claims, "alice")

        assert len(results) == 2
        # Should have results but marked as ERROR
        assert any(r.verified_as == VerificationStatus.ERROR for r in results)
