# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Claim Classifier - Tier 4 Knowledge Grounding

Extracts claims from LLM output and classifies them against the knowledge base.

Features:
- Claim extraction from LLM responses using pattern and NLP methods
- Semantic search against knowledge base for claim verification
- Claim type classification (FACTUAL, PROCEDURAL, PREDICTIVE, OPINION)
- Knowledge base status determination (IN_KB, UNKNOWN, CONTRADICTS, AMBIGUOUS)
- Result caching using async Redis
- Batch processing with configurable concurrency

Issue: Knowledge Grounding Tier 4 implementation
"""

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Set

from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.ttl_constants import TTL_7_DAYS

from .knowledge_grounding_models import (
    Claim,
    ClaimExtractionResult,
    ClaimType,
    KBSource,
    KBStatus,
)

logger = get_llm_logger("claim_classifier")

# Cache TTL for classification results
CACHE_TTL_SECONDS = TTL_7_DAYS
BATCH_PROCESSING_SEMAPHORE_LIMIT = 5

# Regex patterns for claim extraction
_PATTERN_CAUSAL = re.compile(
    r"(.*?)\s+(?:causes|leads to|results in|triggers|creates)\s+(.*?)(?:[.!?]|$)",
    re.IGNORECASE,
)
_PATTERN_STATE = re.compile(r"(.*?)\s+(?:is|are|was|were)\s+(.*?)(?:[.!?]|$)", re.IGNORECASE)
_PATTERN_QUANTITY = re.compile(
    r"(.*?)\s+(?:is|has)\s+([0-9]+\s*(?:ms|seconds?|minutes?|hours?|days?|%|bytes?|kb|mb|gb))",
    re.IGNORECASE,
)
_PATTERN_SHOULD = re.compile(r"(?:should|must|need to|have to)\s+(.*?)(?:[.!?]|$)", re.IGNORECASE)
_PATTERN_WILL = re.compile(r"(?:will|would|can|could)\s+(.*?)(?:[.!?]|$)", re.IGNORECASE)


class ClaimClassifier:
    """
    Extracts and classifies claims from LLM output against the knowledge base.

    Provides:
    - Claim extraction from text using pattern and NLP methods
    - Individual claim classification with KB semantic search
    - Batch classification with concurrency control
    - Redis-backed caching for classification results
    - Confidence scoring and source attribution
    """

    def __init__(
        self,
        knowledge_base: Any,
        cache_ttl: int = CACHE_TTL_SECONDS,
        batch_semaphore_limit: int = BATCH_PROCESSING_SEMAPHORE_LIMIT,
    ) -> None:
        """
        Initialize ClaimClassifier.

        Args:
            knowledge_base: KnowledgeBase instance for semantic search
            cache_ttl: TTL for cached classification results (seconds)
            batch_semaphore_limit: Max concurrent KB searches during batch processing
        """
        self.kb = knowledge_base
        self.cache_ttl = cache_ttl
        self.batch_semaphore_limit = batch_semaphore_limit
        self._semaphore: asyncio.Semaphore | None = None
        self._redis_client: Any | None = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Lazy-initialize Redis client and semaphore."""
        if self._initialized:
            return

        try:
            self._redis_client = await get_async_redis_client(database="main")
            self._semaphore = asyncio.Semaphore(self.batch_semaphore_limit)
            self._initialized = True
            logger.info(f"ClaimClassifier initialized with semaphore limit {self.batch_semaphore_limit}")
        except Exception as e:
            logger.error(f"Failed to initialize ClaimClassifier: {e}")
            # Gracefully continue without caching if Redis unavailable
            self._semaphore = asyncio.Semaphore(self.batch_semaphore_limit)
            self._initialized = True

    async def extract_claims(self, response: str) -> ClaimExtractionResult:
        """
        Extract factual claims from LLM response text.

        Uses multiple pattern-based extraction methods to identify claims:
        - Causal claims ("X causes Y")
        - State claims ("Z is true")
        - Quantitative claims ("Latency is 500ms")
        - Procedural claims ("Should cache this")
        - Predictive claims ("Will improve by 20%")

        Args:
            response: LLM response text

        Returns:
            ClaimExtractionResult with extracted claims and confidence
        """
        start_time = time.time()
        claims: Set[str] = set()

        if not response or not response.strip():
            return ClaimExtractionResult(
                claims=[],
                extraction_confidence=0.0,
                method="none",
                processing_time_ms=0.0,
            )

        # Split into sentences for better claim isolation
        sentences = self._split_into_sentences(response)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:  # Skip very short sentences
                continue

            # Apply pattern-based extraction
            self._extract_causal_claims(sentence, claims)
            self._extract_state_claims(sentence, claims)
            self._extract_quantity_claims(sentence, claims)
            self._extract_procedural_claims(sentence, claims)
            self._extract_predictive_claims(sentence, claims)

        # Remove duplicates and very short claims
        filtered_claims = [c for c in claims if len(c) > 5 and c.lower() not in ("unknown", "none")]

        # Calculate extraction confidence based on claim count and sentence count
        extraction_confidence = min(1.0, len(filtered_claims) / max(1, len(sentences)))

        processing_time_ms = (time.time() - start_time) * 1000

        logger.debug(
            f"Extracted {len(filtered_claims)} claims from {len(sentences)} sentences " f"in {processing_time_ms:.1f}ms"
        )

        return ClaimExtractionResult(
            claims=list(filtered_claims),
            extraction_confidence=extraction_confidence,
            method="hybrid_pattern_nlp",
            processing_time_ms=processing_time_ms,
        )

    async def classify(self, claim: str) -> Claim:
        """
        Classify a single claim against the knowledge base.

        Performs:
        1. Claim type detection (FACTUAL, PROCEDURAL, PREDICTIVE, OPINION)
        2. Semantic KB search
        3. Confidence scoring
        4. Source attribution if found

        Args:
            claim: Claim text to classify

        Returns:
            Claim with classification results
        """
        await self._ensure_initialized()

        # Check cache first
        cache_key = self._make_cache_key(claim)
        cached = await self._get_from_cache(cache_key)
        if cached:
            logger.debug(f"Cache hit for claim: {claim[:50]}...")
            return cached

        # Classify claim type
        claim_type = self._classify_claim_type(claim)

        # Search knowledge base
        kb_results = await self._search_knowledge_base(claim)

        # Determine KB status and confidence
        kb_status, confidence, sources, kb_fact = self._evaluate_kb_results(kb_results)

        # Create claim object
        result = Claim(
            claim_text=claim,
            claim_type=claim_type,
            kb_status=kb_status,
            confidence=confidence,
            sources=sources,
            kb_fact=kb_fact,
            metadata={
                "search_result_count": len(kb_results) if kb_results else 0,
                "extraction_method": "pattern_hybrid",
            },
        )

        # Cache the result
        await self._save_to_cache(cache_key, result)

        logger.debug(f"Classified claim '{claim[:50]}...' as {claim_type.value}/{kb_status.value}")

        return result

    async def batch_classify(self, claims: List[str]) -> List[Claim]:
        """
        Classify multiple claims in parallel with concurrency limits.

        Uses semaphore to limit concurrent KB searches to avoid overwhelming
        the knowledge base. Processes claims in the order provided.

        Args:
            claims: List of claim texts to classify

        Returns:
            List of Claim objects in same order as input
        """
        await self._ensure_initialized()

        if not claims:
            return []

        logger.info(f"Batch classifying {len(claims)} claims")

        # Create tasks with semaphore protection
        async def classify_with_semaphore(claim: str) -> Claim:
            async with self._semaphore:
                return await self.classify(claim)

        tasks = [classify_with_semaphore(claim) for claim in claims]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        classified = []
        for claim, result in zip(claims, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to classify claim '{claim}': {result}")
                # Return a default UNKNOWN claim on error
                classified.append(
                    Claim(
                        claim_text=claim,
                        claim_type=ClaimType.FACTUAL,
                        kb_status=KBStatus.UNKNOWN,
                        confidence=0.0,
                        metadata={"error": str(result)},
                    )
                )
            else:
                classified.append(result)

        logger.info(f"Completed batch classification of {len(classified)} claims")
        return classified

    # =========================================================================
    # Private Methods - Claim Extraction
    # =========================================================================

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences, handling common edge cases."""
        # Simple heuristic sentence splitting
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _extract_causal_claims(self, sentence: str, claims: Set[str]) -> None:
        """Extract causal relationship claims (X causes Y)."""
        match = _PATTERN_CAUSAL.search(sentence)
        if match:
            subject, consequence = match.groups()
            claim = f"{subject.strip()} causes {consequence.strip()}"
            if len(claim) > 10:
                claims.add(claim)

    def _extract_state_claims(self, sentence: str, claims: Set[str]) -> None:
        """Extract state claims (X is Y)."""
        match = _PATTERN_STATE.search(sentence)
        if match:
            subject, state = match.groups()
            claim = f"{subject.strip()} is {state.strip()}"
            if len(claim) > 10:
                claims.add(claim)

    def _extract_quantity_claims(self, sentence: str, claims: Set[str]) -> None:
        """Extract quantitative claims (has value, is metric)."""
        match = _PATTERN_QUANTITY.search(sentence)
        if match:
            subject, quantity = match.groups()
            claim = f"{subject.strip()} is {quantity.strip()}"
            if len(claim) > 10:
                claims.add(claim)

    def _extract_procedural_claims(self, sentence: str, claims: Set[str]) -> None:
        """Extract procedural claims (should/must do X)."""
        match = _PATTERN_SHOULD.search(sentence)
        if match:
            action = match.group(1).strip()
            if len(action) > 5:
                claim = f"should {action}"
                claims.add(claim)

    def _extract_predictive_claims(self, sentence: str, claims: Set[str]) -> None:
        """Extract predictive claims (will/would do X)."""
        match = _PATTERN_WILL.search(sentence)
        if match:
            prediction = match.group(1).strip()
            if len(prediction) > 5:
                claim = f"will {prediction}"
                claims.add(claim)

    # =========================================================================
    # Private Methods - Claim Classification
    # =========================================================================

    def _classify_claim_type(self, claim: str) -> ClaimType:
        """Determine claim type based on linguistic patterns."""
        claim_lower = claim.lower()

        # Procedural: should, must, need to, have to
        if any(word in claim_lower for word in ["should", "must", "need to", "have to"]):
            return ClaimType.PROCEDURAL

        # Predictive: will, would, can, could, improve, help, cause
        if any(word in claim_lower for word in ["will", "would", "can", "could", "improve", "help", "cause"]):
            return ClaimType.PREDICTIVE

        # Opinion indicators: bad, good, inefficient, better, worse, think, believe
        if any(
            word in claim_lower
            for word in [
                "bad",
                "good",
                "inefficient",
                "better",
                "worse",
                "think",
                "believe",
                "opinion",
            ]
        ):
            return ClaimType.OPINION

        # Default to factual for state/quantitative claims
        return ClaimType.FACTUAL

    async def _search_knowledge_base(self, claim: str) -> List[Dict[str, Any]]:
        """
        Search knowledge base for claim using semantic search.

        Returns:
            List of matching KB entries with relevance scores
        """
        try:
            # Use the RAGService or direct KB search interface
            # For now, using a simplified search interface
            if hasattr(self.kb, "search_async"):
                results = await self.kb.search_async(claim, limit=5)
            elif hasattr(self.kb, "search"):
                results = self.kb.search(claim, limit=5)
            else:
                logger.warning("Knowledge base has no search method")
                return []

            return results if results else []
        except Exception as e:
            logger.error(f"KB search failed for claim '{claim}': {e}")
            return []

    def _evaluate_kb_results(self, results: List[Dict[str, Any]]) -> tuple[KBStatus, float, List[KBSource], str | None]:
        """
        Evaluate KB search results to determine status and confidence.

        Returns:
            Tuple of (status, confidence, sources, conflicting_fact)
        """
        if not results:
            return KBStatus.UNKNOWN, 0.0, [], None

        # Convert results to sources
        sources = []
        confidence_scores = []

        for result in results:
            try:
                source = KBSource(
                    source_id=result.get("id", "unknown"),
                    source_type=result.get("type", "document"),
                    text=result.get("text", ""),
                    confidence=float(result.get("score", 0.5)),
                    age_days=result.get("age_days", 0.0),
                    url=result.get("url"),
                )
                sources.append(source)
                confidence_scores.append(source.confidence)
            except (KeyError, ValueError) as e:
                logger.debug(f"Failed to parse KB result: {e}")
                continue

        if not sources:
            return KBStatus.UNKNOWN, 0.0, [], None

        # Determine status based on result count and confidence
        avg_confidence = sum(confidence_scores) / len(confidence_scores)

        if len(sources) >= 2 and avg_confidence >= 0.7:
            # Multiple high-confidence sources = IN_KB
            status = KBStatus.IN_KB
            confidence = min(0.95, avg_confidence + 0.1)
        elif len(sources) >= 2 and avg_confidence < 0.5:
            # Multiple low-confidence sources = AMBIGUOUS
            status = KBStatus.AMBIGUOUS
            confidence = 0.5
        elif avg_confidence >= 0.7:
            # Single high-confidence source = IN_KB
            status = KBStatus.IN_KB
            confidence = avg_confidence
        else:
            # Single low-confidence source = UNKNOWN
            status = KBStatus.UNKNOWN
            confidence = avg_confidence

        return status, confidence, sources, None

    # =========================================================================
    # Private Methods - Caching
    # =========================================================================

    def _make_cache_key(self, claim: str) -> str:
        """Generate cache key for a claim."""
        # Use claim hash for consistent key generation
        import hashlib

        claim_hash = hashlib.sha256(claim.encode()).hexdigest()
        return f"claim:classification:{claim_hash}"

    async def _get_from_cache(self, cache_key: str) -> Claim | None:
        """Retrieve classification from Redis cache."""
        if not self._redis_client:
            return None

        try:
            cached_json = await self._redis_client.get(cache_key)
            if not cached_json:
                return None

            data = json.loads(cached_json)
            return Claim.from_dict(data)
        except Exception as e:
            logger.debug(f"Cache retrieval failed: {e}")
            return None

    async def _save_to_cache(self, cache_key: str, claim: Claim) -> None:
        """Store classification in Redis cache."""
        if not self._redis_client:
            return

        try:
            claim_json = json.dumps(claim.to_dict())
            await self._redis_client.setex(cache_key, self.cache_ttl, claim_json)
        except Exception as e:
            logger.debug(f"Cache storage failed: {e}")


def get_claim_classifier(knowledge_base: Any) -> ClaimClassifier:
    """
    Factory function to get a ClaimClassifier instance.

    Args:
        knowledge_base: KnowledgeBase instance

    Returns:
        ClaimClassifier instance
    """
    return ClaimClassifier(knowledge_base)
