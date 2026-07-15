# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for ClaimVerifier wiring into GroundedAgent (#10602).

Verifies that:
- CLAIM_VERIFICATION_ENABLED=false (default): _escalate_to_claim_verifier returns UNKNOWN
  without touching ClaimVerifier.
- CLAIM_VERIFICATION_ENABLED=true: ClaimVerifier.kb_rag_search is called for low-confidence
  claims and the result is mapped back into GroundedAgent's VerifiedClaim type.
- Errors in ClaimVerifier are swallowed; UNKNOWN VerifiedClaim is returned.
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest

from services.grounded_agent import Claim, ClaimStatus, GroundedAgent


def _make_claim(text: str = "test claim") -> Claim:
    return Claim(claim_text=text, confidence=0.3)


def _make_rag_result(confidence: float, match_text: str = "kb evidence") -> types.SimpleNamespace:
    match = types.SimpleNamespace(text=match_text, url=None)
    return types.SimpleNamespace(
        confidence=confidence,
        matches=[match] if confidence > 0.0 else [],
    )


class TestEscalateToClaimVerifier:
    @pytest.mark.asyncio
    async def test_flag_off_returns_unknown_without_claim_verifier(self, monkeypatch):
        """When CLAIM_VERIFICATION_ENABLED=false, ClaimVerifier is never imported."""
        monkeypatch.setattr("services.grounded_agent.CLAIM_VERIFICATION_ENABLED", False)
        agent = GroundedAgent()
        claim = _make_claim()

        # ClaimVerifier should not be called at all
        with patch("services.claim_verifier.ClaimVerifier") as mock_cv:
            result = await agent._escalate_to_claim_verifier(claim, "no evidence")

        mock_cv.assert_not_called()
        assert result.kb_status == ClaimStatus.UNKNOWN
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_flag_on_calls_claim_verifier_rag(self, monkeypatch):
        """When CLAIM_VERIFICATION_ENABLED=true, ClaimVerifier.kb_rag_search is called."""
        monkeypatch.setattr("services.grounded_agent.CLAIM_VERIFICATION_ENABLED", True)
        agent = GroundedAgent()
        agent.kb = object()  # non-None KB so verifier is constructed
        claim = _make_claim("Redis latency is 500ms")

        mock_verifier = AsyncMock()
        mock_verifier.kb_rag_search = AsyncMock(return_value=_make_rag_result(0.85))

        # _make_claim_verifier is a module-level helper; patch it directly.
        with patch("services.grounded_agent._make_claim_verifier", return_value=mock_verifier):
            result = await agent._escalate_to_claim_verifier(claim, "")

        mock_verifier.kb_rag_search.assert_called_once_with(claim.claim_text)
        # confidence >= 0.8 → VERIFIED
        assert result.kb_status == ClaimStatus.VERIFIED
        assert result.confidence == pytest.approx(0.85)
        assert result.verification_method == "claim_verifier_rag"

    @pytest.mark.asyncio
    async def test_flag_on_medium_confidence_returns_unknown(self, monkeypatch):
        """Confidence 0.7-0.8 → UNKNOWN (below VERIFIED threshold)."""
        monkeypatch.setattr("services.grounded_agent.CLAIM_VERIFICATION_ENABLED", True)
        agent = GroundedAgent()
        agent.kb = object()
        claim = _make_claim("some fact")

        mock_verifier = AsyncMock()
        mock_verifier.kb_rag_search = AsyncMock(return_value=_make_rag_result(0.75))

        with patch("services.grounded_agent._make_claim_verifier", return_value=mock_verifier):
            result = await agent._escalate_to_claim_verifier(claim, "")

        # confidence 0.7-0.8 → status is UNKNOWN (threshold for VERIFIED is 0.8)
        assert result.kb_status == ClaimStatus.UNKNOWN
        assert result.confidence == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_flag_on_below_threshold_returns_unknown(self, monkeypatch):
        """ClaimVerifier RAG confidence < 0.7 → UNKNOWN returned."""
        monkeypatch.setattr("services.grounded_agent.CLAIM_VERIFICATION_ENABLED", True)
        agent = GroundedAgent()
        agent.kb = object()
        claim = _make_claim("obscure fact")

        mock_verifier = AsyncMock()
        mock_verifier.kb_rag_search = AsyncMock(return_value=_make_rag_result(0.4))

        with patch("services.grounded_agent._make_claim_verifier", return_value=mock_verifier):
            result = await agent._escalate_to_claim_verifier(claim, "")

        # Below 0.7 threshold → falls through to UNKNOWN
        assert result.kb_status == ClaimStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_claim_verifier_error_swallowed_returns_unknown(self, monkeypatch):
        """ClaimVerifier raising must not propagate; UNKNOWN is returned."""
        monkeypatch.setattr("services.grounded_agent.CLAIM_VERIFICATION_ENABLED", True)
        agent = GroundedAgent()
        agent.kb = object()
        claim = _make_claim()

        with patch(
            "services.grounded_agent._make_claim_verifier",
            side_effect=RuntimeError("redis down"),
        ):
            result = await agent._escalate_to_claim_verifier(claim, "evidence")

        assert result.kb_status == ClaimStatus.UNKNOWN


class TestClassifyAndVerifyClaimDelegation:
    @pytest.mark.asyncio
    async def test_no_kb_returns_unknown(self):
        """When kb is None, _classify_and_verify_claim returns UNKNOWN immediately."""
        agent = GroundedAgent()
        agent.kb = None
        claim = _make_claim()
        result = await agent._classify_and_verify_claim(claim)
        assert result.kb_status == ClaimStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_low_confidence_delegates_to_escalate(self, monkeypatch):
        """A <0.5 similarity_score delegates to _escalate_to_claim_verifier."""
        monkeypatch.setattr("services.grounded_agent.CLAIM_VERIFICATION_ENABLED", False)
        agent = GroundedAgent()
        agent.kb = AsyncMock()
        agent.kb.search = AsyncMock(return_value=[{"similarity_score": 0.3, "fact_id": "f1", "content": "x"}])
        claim = _make_claim()

        result = await agent._classify_and_verify_claim(claim)
        # With flag off, escalation returns UNKNOWN
        assert result.kb_status == ClaimStatus.UNKNOWN
