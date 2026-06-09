# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for ClaimClassifier - Tier 4 Knowledge Grounding

Tests claim extraction, classification, batch processing, and caching behavior.

Issue: Knowledge Grounding Tier 4 implementation
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.claim_classifier import ClaimClassifier
from services.knowledge_grounding_models import (
    Claim,
    ClaimType,
    KBSource,
    KBStatus,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_knowledge_base():
    """Create a mock knowledge base."""
    kb = MagicMock()
    kb.search = MagicMock(return_value=[])
    return kb


@pytest.fixture
def mock_redis_client():
    """Create a mock async Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    return redis


@pytest.fixture
def claim_classifier(mock_knowledge_base):
    """Create a ClaimClassifier instance with mock KB."""
    classifier = ClaimClassifier(mock_knowledge_base)
    classifier._initialized = True
    classifier._semaphore = asyncio.Semaphore(5)
    return classifier


# =============================================================================
# Tests: Claim Extraction
# =============================================================================


class TestClaimExtraction:
    """Tests for claim extraction from LLM responses."""

    @pytest.mark.asyncio
    async def test_extract_empty_response(self, claim_classifier):
        """Extract from empty response returns no claims."""
        result = await claim_classifier.extract_claims("")
        assert result.claims == []
        assert result.extraction_confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_none_response(self, claim_classifier):
        """Extract from None response returns no claims."""
        result = await claim_classifier.extract_claims(None)
        assert result.claims == []
        assert result.extraction_confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_whitespace_response(self, claim_classifier):
        """Extract from whitespace-only response returns no claims."""
        result = await claim_classifier.extract_claims("   \n\t  ")
        assert result.claims == []
        assert result.extraction_confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_causal_claim(self, claim_classifier):
        """Extract causal relationship claims."""
        response = "High CPU usage causes system slowdown. The impact is severe."
        result = await claim_classifier.extract_claims(response)
        assert len(result.claims) > 0
        assert any("causes" in claim.lower() for claim in result.claims)

    @pytest.mark.asyncio
    async def test_extract_state_claims(self, claim_classifier):
        """Extract state assertion claims."""
        response = "The service is running. Port 8080 is open. Status is healthy."
        result = await claim_classifier.extract_claims(response)
        assert len(result.claims) > 0
        assert any("is" in claim.lower() for claim in result.claims)

    @pytest.mark.asyncio
    async def test_extract_quantity_claims(self, claim_classifier):
        """Extract quantitative metric claims."""
        response = "Latency is 500ms. Memory usage is 2GB. Response time is 200ms."
        result = await claim_classifier.extract_claims(response)
        assert len(result.claims) > 0
        assert any(any(unit in claim.lower() for unit in ["ms", "gb", "mb"]) for claim in result.claims)

    @pytest.mark.asyncio
    async def test_extract_procedural_claims(self, claim_classifier):
        """Extract procedural/should claims."""
        response = "We should cache this data. Must validate input. Need to add logging."
        result = await claim_classifier.extract_claims(response)
        assert len(result.claims) > 0
        assert any(any(word in claim.lower() for word in ["should", "must", "need"]) for claim in result.claims)

    @pytest.mark.asyncio
    async def test_extract_predictive_claims(self, claim_classifier):
        """Extract predictive/outcome claims."""
        response = "Adding memory will improve performance. This will help with latency."
        result = await claim_classifier.extract_claims(response)
        assert len(result.claims) > 0
        assert any("will" in claim.lower() for claim in result.claims)

    @pytest.mark.asyncio
    async def test_extract_multiple_claims(self, claim_classifier):
        """Extract multiple different claim types from single response."""
        response = """
        The API is slow. Latency is 5 seconds. This causes timeouts.
        We should cache results. Adding Redis will help. Must validate input.
        """
        result = await claim_classifier.extract_claims(response)
        assert len(result.claims) >= 3
        assert result.extraction_confidence > 0.0
        assert result.method == "hybrid_pattern_nlp"

    @pytest.mark.asyncio
    async def test_extract_filters_short_claims(self, claim_classifier):
        """Filter out very short extracted claims."""
        response = "X is Y. A causes B. The system is running."
        result = await claim_classifier.extract_claims(response)
        # Short claims should be filtered
        assert all(len(claim) > 5 for claim in result.claims)

    @pytest.mark.asyncio
    async def test_extract_removes_duplicates(self, claim_classifier):
        """Remove duplicate claims from extraction."""
        response = "The service is running. The service is running. The service is running."
        result = await claim_classifier.extract_claims(response)
        # Should have only one unique claim
        assert len(result.claims) == 1

    @pytest.mark.asyncio
    async def test_extract_confidence_scales_with_claims(self, claim_classifier):
        """Extraction confidence scales with number of claims."""
        # Single sentence with single claim
        result1 = await claim_classifier.extract_claims("The system is slow.")
        conf1 = result1.extraction_confidence

        # Multiple sentences with multiple claims
        result2 = await claim_classifier.extract_claims(
            "The system is slow. The API is down. Memory is high. CPU is high."
        )
        conf2 = result2.extraction_confidence

        # More claims should have higher/equal confidence
        assert conf2 >= conf1

    @pytest.mark.asyncio
    async def test_extract_tracks_processing_time(self, claim_classifier):
        """Extraction result includes processing time."""
        response = "The service is running. It is healthy. Performance is good."
        result = await claim_classifier.extract_claims(response)
        assert result.processing_time_ms >= 0.0
        assert isinstance(result.processing_time_ms, float)


# =============================================================================
# Tests: Claim Type Classification
# =============================================================================


class TestClaimTypeClassification:
    """Tests for claim type detection."""

    def test_classify_factual_claim(self, claim_classifier):
        """Classify factual/state claims."""
        claim = "The service is running"
        claim_type = claim_classifier._classify_claim_type(claim)
        assert claim_type == ClaimType.FACTUAL

    def test_classify_procedural_claim(self, claim_classifier):
        """Classify procedural/should claims."""
        claim = "We should cache the results"
        claim_type = claim_classifier._classify_claim_type(claim)
        assert claim_type == ClaimType.PROCEDURAL

    def test_classify_predictive_claim(self, claim_classifier):
        """Classify predictive/outcome claims."""
        claim = "Adding memory will improve performance"
        claim_type = claim_classifier._classify_claim_type(claim)
        assert claim_type == ClaimType.PREDICTIVE

    def test_classify_opinion_claim(self, claim_classifier):
        """Classify opinion claims."""
        claim = "This approach is inefficient"
        claim_type = claim_classifier._classify_claim_type(claim)
        assert claim_type == ClaimType.OPINION

    def test_classify_must_claim_as_procedural(self, claim_classifier):
        """'Must' keyword indicates procedural claim."""
        claim = "Must validate input before processing"
        claim_type = claim_classifier._classify_claim_type(claim)
        assert claim_type == ClaimType.PROCEDURAL

    def test_classify_could_claim_as_predictive(self, claim_classifier):
        """'Could' keyword indicates predictive claim."""
        claim = "This could reduce latency significantly"
        claim_type = claim_classifier._classify_claim_type(claim)
        assert claim_type == ClaimType.PREDICTIVE


# =============================================================================
# Tests: Knowledge Base Status Classification
# =============================================================================


class TestKBStatusClassification:
    """Tests for KB status determination from search results."""

    def test_evaluate_no_results_returns_unknown(self, claim_classifier):
        """No KB results returns UNKNOWN status."""
        status, conf, sources, fact = claim_classifier._evaluate_kb_results([])
        assert status == KBStatus.UNKNOWN
        assert conf == 0.0
        assert sources == []

    def test_evaluate_single_high_confidence_returns_in_kb(self, claim_classifier):
        """Single high-confidence result returns IN_KB."""
        results = [
            {
                "id": "fact1",
                "type": "document",
                "text": "The service is running",
                "score": 0.85,
                "age_days": 1.0,
            }
        ]
        status, conf, sources, fact = claim_classifier._evaluate_kb_results(results)
        assert status == KBStatus.IN_KB
        assert conf >= 0.7
        assert len(sources) == 1

    def test_evaluate_multiple_high_confidence_returns_in_kb(self, claim_classifier):
        """Multiple high-confidence results return IN_KB."""
        results = [
            {
                "id": "fact1",
                "type": "document",
                "text": "Result 1",
                "score": 0.8,
                "age_days": 1.0,
            },
            {
                "id": "fact2",
                "type": "document",
                "text": "Result 2",
                "score": 0.75,
                "age_days": 2.0,
            },
        ]
        status, conf, sources, fact = claim_classifier._evaluate_kb_results(results)
        assert status == KBStatus.IN_KB
        assert conf >= 0.7
        assert len(sources) == 2

    def test_evaluate_multiple_low_confidence_returns_ambiguous(self, claim_classifier):
        """Multiple low-confidence results return AMBIGUOUS."""
        results = [
            {
                "id": "fact1",
                "type": "document",
                "text": "Result 1",
                "score": 0.3,
                "age_days": 1.0,
            },
            {
                "id": "fact2",
                "type": "document",
                "text": "Result 2",
                "score": 0.4,
                "age_days": 2.0,
            },
        ]
        status, conf, sources, fact = claim_classifier._evaluate_kb_results(results)
        assert status == KBStatus.AMBIGUOUS
        assert len(sources) == 2

    def test_evaluate_single_low_confidence_returns_unknown(self, claim_classifier):
        """Single low-confidence result returns UNKNOWN."""
        results = [
            {
                "id": "fact1",
                "type": "document",
                "text": "Result",
                "score": 0.3,
                "age_days": 1.0,
            }
        ]
        status, conf, sources, fact = claim_classifier._evaluate_kb_results(results)
        assert status == KBStatus.UNKNOWN
        assert len(sources) == 1


# =============================================================================
# Tests: Individual Claim Classification
# =============================================================================


class TestIndividualClassification:
    """Tests for single claim classification."""

    @pytest.mark.asyncio
    async def test_classify_claim_basic(self, claim_classifier):
        """Classify a basic claim."""
        claim_classifier._redis_client = None
        claim = "The service is running"
        result = await claim_classifier.classify(claim)

        assert isinstance(result, Claim)
        assert result.claim_text == claim
        assert isinstance(result.claim_type, ClaimType)
        assert isinstance(result.kb_status, KBStatus)
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_classify_sets_metadata(self, claim_classifier):
        """Classification includes metadata."""
        claim_classifier._redis_client = None
        claim = "The service is running"
        result = await claim_classifier.classify(claim)

        assert result.metadata is not None
        assert "search_result_count" in result.metadata
        assert "extraction_method" in result.metadata

    @pytest.mark.asyncio
    async def test_classify_with_kb_results(self, claim_classifier):
        """Classification includes KB sources when found."""
        claim_classifier._redis_client = None
        claim_classifier.kb.search_async = AsyncMock(
            return_value=[
                {
                    "id": "fact1",
                    "type": "document",
                    "text": "The service is running",
                    "score": 0.9,
                    "age_days": 1.0,
                    "url": "http://example.com",
                }
            ]
        )

        claim = "The service is running"
        result = await claim_classifier.classify(claim)
        assert result.kb_status == KBStatus.IN_KB
        assert len(result.sources) == 1
        assert result.sources[0].source_id == "fact1"

    @pytest.mark.asyncio
    async def test_classify_caches_result(self, claim_classifier):
        """Classification results are cached in Redis."""
        # Create a proper mock Redis client
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()
        claim_classifier._redis_client = mock_redis

        # Mock KB search to return empty (no KB results)
        claim_classifier.kb.search = MagicMock(return_value=[])

        claim = "The service is running"
        await claim_classifier.classify(claim)

        # Should attempt to cache
        assert mock_redis.setex.called

    @pytest.mark.asyncio
    async def test_classify_returns_cached_result(self, claim_classifier):
        """Classification returns cached results."""
        cached_claim = Claim(
            claim_text="The service is running",
            claim_type=ClaimType.FACTUAL,
            kb_status=KBStatus.IN_KB,
            confidence=0.95,
        )

        mock_redis = AsyncMock()
        # Return cached JSON on first get call (cache hit)
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_claim.to_dict()))
        mock_redis.setex = AsyncMock()
        claim_classifier._redis_client = mock_redis

        cached_result = await claim_classifier.classify("The service is running")

        assert cached_result.claim_text == cached_claim.claim_text
        assert cached_result.kb_status == cached_claim.kb_status
        assert cached_result.confidence == cached_claim.confidence
        # Should return from cache without calling KB search
        claim_classifier.kb.search.assert_not_called()


# =============================================================================
# Tests: Batch Classification
# =============================================================================


class TestBatchClassification:
    """Tests for batch claim classification."""

    @pytest.mark.asyncio
    async def test_batch_classify_empty_list(self, claim_classifier):
        """Batch classify empty list returns empty list."""
        result = await claim_classifier.batch_classify([])
        assert result == []

    @pytest.mark.asyncio
    async def test_batch_classify_single_claim(self, claim_classifier):
        """Batch classify single claim."""
        claim_classifier._redis_client = None
        result = await claim_classifier.batch_classify(["The service is running"])

        assert len(result) == 1
        assert isinstance(result[0], Claim)

    @pytest.mark.asyncio
    async def test_batch_classify_multiple_claims(self, claim_classifier):
        """Batch classify multiple claims preserves order."""
        claim_classifier._redis_client = None
        claims = [
            "The service is running",
            "Latency is 500ms",
            "We should cache this",
        ]

        results = await claim_classifier.batch_classify(claims)

        assert len(results) == 3
        assert results[0].claim_text == claims[0]
        assert results[1].claim_text == claims[1]
        assert results[2].claim_text == claims[2]

    @pytest.mark.asyncio
    async def test_batch_classify_respects_semaphore(self, claim_classifier):
        """Batch classification respects concurrency limit."""
        claim_classifier._redis_client = None
        claim_classifier.batch_semaphore_limit = 2
        # Reset semaphore with new limit
        claim_classifier._semaphore = asyncio.Semaphore(2)

        # Create a mock to track concurrent access
        concurrent_count = 0
        max_concurrent = 0

        async def slow_classify(claim: str) -> Claim:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1
            return Claim(
                claim_text=claim,
                claim_type=ClaimType.FACTUAL,
                kb_status=KBStatus.UNKNOWN,
                confidence=0.5,
            )

        # Patch classify method
        original_classify = claim_classifier.classify
        claim_classifier.classify = slow_classify

        claims = [f"Claim {i}" for i in range(5)]
        results = await claim_classifier.batch_classify(claims)

        # Restore original
        claim_classifier.classify = original_classify

        assert len(results) == 5
        assert max_concurrent <= claim_classifier.batch_semaphore_limit

    @pytest.mark.asyncio
    async def test_batch_classify_handles_errors(self, claim_classifier):
        """Batch classify handles classification errors gracefully."""
        claim_classifier._redis_client = None

        # Make classify raise an error for one claim
        call_count = 0

        async def failing_classify(claim: str) -> Claim:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Simulated KB error")
            return Claim(
                claim_text=claim,
                claim_type=ClaimType.FACTUAL,
                kb_status=KBStatus.UNKNOWN,
                confidence=0.5,
            )

        original_classify = claim_classifier.classify
        claim_classifier.classify = failing_classify

        claims = ["Claim 1", "Claim 2", "Claim 3"]
        results = await claim_classifier.batch_classify(claims)

        claim_classifier.classify = original_classify

        # All three results returned despite error
        assert len(results) == 3
        assert results[0].claim_text == "Claim 1"
        assert results[1].claim_text == "Claim 2"  # Has error metadata
        assert results[2].claim_text == "Claim 3"


# =============================================================================
# Tests: Caching
# =============================================================================


class TestCaching:
    """Tests for classification result caching."""

    def test_cache_key_generation(self, claim_classifier):
        """Cache key generation is consistent."""
        claim = "The service is running"
        key1 = claim_classifier._make_cache_key(claim)
        key2 = claim_classifier._make_cache_key(claim)

        assert key1 == key2
        assert key1.startswith("claim:classification:")

    def test_cache_key_unique_for_different_claims(self, claim_classifier):
        """Different claims produce different cache keys."""
        key1 = claim_classifier._make_cache_key("Claim 1")
        key2 = claim_classifier._make_cache_key("Claim 2")

        assert key1 != key2

    @pytest.mark.asyncio
    async def test_cache_get_with_no_client(self, claim_classifier):
        """Cache get returns None if no Redis client."""
        claim_classifier._redis_client = None
        result = await claim_classifier._get_from_cache("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_save_with_no_client(self, claim_classifier):
        """Cache save doesn't error if no Redis client."""
        claim_classifier._redis_client = None
        claim = Claim(
            claim_text="Test",
            claim_type=ClaimType.FACTUAL,
            kb_status=KBStatus.UNKNOWN,
            confidence=0.5,
        )
        # Should not raise
        await claim_classifier._save_to_cache("test_key", claim)


# =============================================================================
# Tests: Data Models
# =============================================================================


class TestClaimDataModel:
    """Tests for Claim data model."""

    def test_claim_to_dict(self):
        """Claim converts to dictionary."""
        claim = Claim(
            claim_text="Test claim",
            claim_type=ClaimType.FACTUAL,
            kb_status=KBStatus.IN_KB,
            confidence=0.85,
        )

        data = claim.to_dict()
        assert data["claim_text"] == "Test claim"
        assert data["claim_type"] == "factual"
        assert data["kb_status"] == "in_kb"
        assert data["confidence"] == 0.85

    def test_claim_from_dict(self):
        """Claim reconstructs from dictionary."""
        data = {
            "claim_text": "Test claim",
            "claim_type": "factual",
            "kb_status": "in_kb",
            "confidence": 0.85,
            "sources": [],
        }

        claim = Claim.from_dict(data)
        assert claim.claim_text == "Test claim"
        assert claim.claim_type == ClaimType.FACTUAL
        assert claim.kb_status == KBStatus.IN_KB
        assert claim.confidence == 0.85

    def test_claim_with_sources(self):
        """Claim with sources serializes correctly."""
        source = KBSource(
            source_id="fact1",
            source_type="document",
            text="Source text",
            confidence=0.9,
            age_days=1.0,
            url="http://example.com",
        )

        claim = Claim(
            claim_text="Test claim",
            claim_type=ClaimType.FACTUAL,
            kb_status=KBStatus.IN_KB,
            confidence=0.85,
            sources=[source],
        )

        data = claim.to_dict()
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source_id"] == "fact1"

        # Round-trip
        claim2 = Claim.from_dict(data)
        assert len(claim2.sources) == 1
        assert claim2.sources[0].source_id == "fact1"


# =============================================================================
# Tests: Integration
# =============================================================================


class TestIntegration:
    """Integration tests combining extraction and classification."""

    @pytest.mark.asyncio
    async def test_end_to_end_extraction_and_classification(self, claim_classifier):
        """Extract claims from response and classify them."""
        claim_classifier._redis_client = None
        response = "The API is slow. Latency is 5 seconds. " "We should cache results. This will improve performance."

        # Extract claims
        extraction_result = await claim_classifier.extract_claims(response)
        assert len(extraction_result.claims) > 0

        # Classify extracted claims
        classifications = await claim_classifier.batch_classify(extraction_result.claims)
        assert len(classifications) == len(extraction_result.claims)

        # All claims should be classified
        for classification in classifications:
            assert classification.claim_type is not None
            assert classification.kb_status is not None

    @pytest.mark.asyncio
    async def test_claim_extraction_result_processing_time(self, claim_classifier):
        """Verify processing time is tracked accurately."""
        response = "Test claim that should be processed."
        result = await claim_classifier.extract_claims(response)

        assert result.processing_time_ms > 0
        assert isinstance(result.processing_time_ms, float)
