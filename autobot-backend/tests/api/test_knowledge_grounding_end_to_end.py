# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""End-to-end grounding tests of the GroundedAgent (split from test_knowledge_grounding.py, #16665)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.ownership import KnowledgeOwnership
from services.grounded_agent import GroundedAgent
from services.grounded_agent_models import GroundedResponse
from services.knowledge_grounding_models import Claim, ClaimStatus, VerificationMethod, VerifiedClaim


@pytest.fixture
def mock_app():
    """Mock FastAPI app."""
    app = MagicMock()
    app.app = app
    return app


@pytest.fixture
def grounded_agent():
    """Create a GroundedAgent instance for testing."""
    return GroundedAgent()


@pytest.fixture
def sample_claim():
    """Create a sample claim for testing."""
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


# ===== END-TO-END GROUNDING TESTS =====


@pytest.mark.asyncio
async def test_respond_with_grounding_all_verified(grounded_agent, mock_app):
    """Test end-to-end grounding with all claims verified."""
    grounded_agent.app = mock_app

    # Mock dependencies
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
                "fact_id": "fact-001",
                "content": "Latency increased by 15%",
                "similarity_score": 0.92,
                "metadata": {"owner_id": "alice", "visibility": "private"},
            }
        ]
    )

    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = mock_kb
    mock_kb.ownership_manager = KnowledgeOwnership(None)  # #16665: the real visibility decision

    result = await grounded_agent.respond_with_grounding(
        user_query="What happened to latency?",
        agent_response="Latency increased by 15%",
        user_id="alice",
    )

    assert isinstance(result, GroundedResponse)
    assert result.original_query == "What happened to latency?"
    assert len(result.verified_claims) > 0
    assert result.confidence_overall > 0.0
    assert not result.requires_human_review


@pytest.mark.asyncio
async def test_respond_with_grounding_mixed_claims(grounded_agent, mock_app):
    """Test grounding with mix of verified and unverified claims."""
    grounded_agent.app = mock_app

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
                        "claim_text": "Unknown fact about X",
                        "subject": "X",
                        "predicate": "unknown",
                        "object": "value",
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
                    "metadata": {"owner_id": "alice", "visibility": "private"},
                }
            ],
            [],  # No match for second claim
        ]
    )

    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = mock_kb
    mock_kb.ownership_manager = KnowledgeOwnership(None)  # #16665: the real visibility decision

    result = await grounded_agent.respond_with_grounding(
        user_query="Question",
        agent_response="Two statements here",
        user_id="alice",
    )

    assert len(result.verified_claims) >= 1
    assert len(result.unverified_claims) >= 1
    assert result.requires_human_review


@pytest.mark.asyncio
async def test_respond_with_grounding_low_confidence(grounded_agent, mock_app):
    """Test grounding flags for review when confidence is low."""
    grounded_agent.app = mock_app

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                [
                    {
                        "claim_text": "Claim with low confidence",
                        "subject": "claim",
                        "predicate": "has",
                        "object": "low confidence",
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
                "metadata": {"owner_id": "alice", "visibility": "private"},
            }
        ]
    )

    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = mock_kb
    mock_kb.ownership_manager = KnowledgeOwnership(None)  # #16665: the real visibility decision

    result = await grounded_agent.respond_with_grounding(
        user_query="Question",
        agent_response="Answer",
        user_id="alice",
    )

    assert result.confidence_overall < 0.6
    assert result.requires_human_review


@pytest.mark.asyncio
async def test_respond_with_grounding_with_conflicts(grounded_agent, mock_app):
    """Test grounding detects and flags conflicts."""
    grounded_agent.app = mock_app

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                [
                    {
                        "claim_text": "Claim A",
                        "subject": "A",
                        "predicate": "is",
                        "object": "true",
                        "confidence": 0.9,
                    }
                ]
            )
        )
    )

    grounded_agent.llm_service = mock_llm
    grounded_agent.kb = None  # No KB, so claim is unverifiable

    result = await grounded_agent.respond_with_grounding(
        user_query="Q",
        agent_response="A",
        user_id="alice",
    )

    assert result.requires_human_review
