#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Claim Verifier Service - Tier 4 Knowledge Grounding

This module verifies unknown claims by searching the knowledge base via RAG
and delegating to a research agent when KB evidence is insufficient.

Issue: Knowledge Grounding Tier 4 implementation

Features:
- Fast KB RAG search (semantic similarity, confidence-based)
- Research agent escalation for unverified claims
- Parallel batch verification with intelligent prioritization
- Redis caching for verified claims with TTL
- Comprehensive logging for analytics
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.ttl_constants import TTL_7_DAYS
from services.knowledge_grounding_models import (
    Claim,
    KBSource,
    KBStatus,
)

logger = get_llm_logger("claim_verifier")

# Cache configuration
_CACHE_TTL_SECONDS = TTL_7_DAYS
_CACHE_KEY_PREFIX = "verified_claim"

# Research agent configuration
_RESEARCH_AGENT_TIMEOUT = 30.0  # seconds
_RAG_CONFIDENCE_THRESHOLD = 0.7
_MIN_RAG_CONFIDENCE = 0.5


class VerificationStatus(str, Enum):
    """Verification status of a claim."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    ERROR = "error"


class ResearchStatus(str, Enum):
    """Status from research agent investigation."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    CONFLICTING = "conflicting"
    TIMEOUT = "timeout"


@dataclass
class RAGResult:
    """Result from KB RAG search."""

    fact: str
    matches: List[KBSource]
    confidence: float
    search_time_ms: float


@dataclass
class ResearchResult:
    """Result from research agent investigation."""

    claim: str
    fact: str | None
    status: ResearchStatus
    url: str | None = None
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    research_time_ms: float = 0.0


@dataclass
class VerifiedClaim:
    """Claim verification result with sources and confidence."""

    original: Claim
    verified_as: VerificationStatus
    source: str  # "knowledge_base", "kb_rag", "research_agent"
    source_text: str | None = None
    source_url: str | None = None
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    requires_human_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "original_claim": self.original.to_dict(),
            "verified_as": self.verified_as.value,
            "source": self.source,
            "source_text": self.source_text,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "requires_human_review": self.requires_human_review,
        }


class ClaimVerifier:
    """
    Verifies claims using KB RAG search and research agent escalation.

    Architecture:
    1. IN_KB claims return VERIFIED immediately (high confidence)
    2. UNKNOWN claims:
       a) Try fast KB RAG search
       b) If confidence >= 0.7, return result
       c) Otherwise, escalate to research agent
       d) Return whichever source has higher confidence
    3. CONTRADICTS claims return to ConflictResolver (not handled here)
    """

    def __init__(self, knowledge_base: Any, research_agent_service: Any | None = None) -> None:
        """
        Initialize claim verifier.

        Args:
            knowledge_base: KnowledgeBase instance for RAG searches
            research_agent_service: Optional research agent service for escalation
        """
        self.kb = knowledge_base
        self.research_agent_service = research_agent_service
        self._cache: Dict[str, Tuple[VerifiedClaim, float]] = {}
        self._cache_lock = asyncio.Lock()
        logger.info("ClaimVerifier initialized")

    def _build_cache_key(self, claim: Claim) -> str:
        """Build cache key for a claim (based on claim text hash)."""
        claim_hash = hashlib.sha256(claim.claim_text.encode("utf-8")).hexdigest()
        return f"{_CACHE_KEY_PREFIX}:{claim_hash}"

    async def _get_from_cache(self, cache_key: str) -> VerifiedClaim | None:
        """Get verified claim from cache if not expired."""
        async with self._cache_lock:
            if cache_key in self._cache:
                cached_claim, timestamp = self._cache[cache_key]
                if time.time() - timestamp < _CACHE_TTL_SECONDS:
                    logger.debug("Cache hit for claim: %s", cache_key)
                    return cached_claim
                else:
                    del self._cache[cache_key]

        # Check Redis cache as fallback
        try:
            redis = await get_async_redis_client(database="main")
            if redis:
                cached_json = await redis.get(cache_key)
                if cached_json:
                    logger.debug("Redis cache hit for claim: %s", cache_key)
                    data = json.loads(cached_json)
                    return self._deserialize_verified_claim(data)
        except Exception as e:
            logger.warning("Redis cache lookup failed: %s", e)

        return None

    async def _set_to_cache(self, cache_key: str, verified: VerifiedClaim) -> None:
        """Store verified claim in cache (both in-memory and Redis)."""
        async with self._cache_lock:
            self._cache[cache_key] = (verified, time.time())

            # Simple LRU cleanup: if cache > 1000 items, remove oldest 10%
            if len(self._cache) > 1000:
                sorted_cache = sorted(self._cache.items(), key=lambda x: x[1][1])
                for key, _ in sorted_cache[:100]:
                    del self._cache[key]

        # Store in Redis with TTL
        try:
            redis = await get_async_redis_client(database="main")
            if redis:
                cache_json = json.dumps(verified.to_dict(), default=str)
                await redis.setex(cache_key, _CACHE_TTL_SECONDS, cache_json)
                logger.debug("Cached verified claim in Redis: %s", cache_key)
        except Exception as e:
            logger.warning("Redis cache store failed: %s", e)

    def _deserialize_verified_claim(self, data: Dict[str, Any]) -> VerifiedClaim:
        """Reconstruct VerifiedClaim from dictionary."""
        original = Claim.from_dict(data.get("original_claim", {}))
        return VerifiedClaim(
            original=original,
            verified_as=VerificationStatus(data.get("verified_as", "unverified")),
            source=data.get("source", "unknown"),
            source_text=data.get("source_text"),
            source_url=data.get("source_url"),
            confidence=data.get("confidence", 0.0),
            timestamp=data.get("timestamp", time.time()),
            requires_human_review=data.get("requires_human_review", False),
        )

    async def kb_rag_search(self, claim: str) -> RAGResult | None:
        """
        Search knowledge base via RAG for evidence.

        Performs semantic search against KB and returns top 3 matches
        with confidence > 0.5. Includes source documents and text snippets.

        Args:
            claim: Claim text to search

        Returns:
            RAGResult with matches and confidence, or None on error
        """
        if not self.kb:
            logger.warning("Knowledge base not available for RAG search")
            return None

        try:
            start_time = time.time()
            logger.debug("Starting KB RAG search for claim: %s...", claim[:80])

            # Search KB (attempt to use advanced search if available)
            search_results = await self.kb.search(query=claim, top_k=3)

            if not search_results:
                logger.info("KB RAG search returned no results for claim: %s...", claim[:80])
                return RAGResult(
                    fact=claim,
                    matches=[],
                    confidence=0.0,
                    search_time_ms=(time.time() - start_time) * 1000,
                )

            # Convert search results to KBSource objects (confidence = score)
            matches = []
            for i, result in enumerate(search_results):
                if isinstance(result, dict) and result.get("score", 0.0) > _MIN_RAG_CONFIDENCE:
                    matches.append(
                        KBSource(
                            source_id=result.get("node_id", result.get("doc_id", f"chunk_{i}")),
                            source_type=result.get("metadata", {}).get("source_type", "document"),
                            text=result.get("content", ""),
                            confidence=result.get("score", 0.0),
                            age_days=result.get("metadata", {}).get("age_days", 0.0),
                            url=result.get("metadata", {}).get("url"),
                        )
                    )

            if not matches:
                logger.info("KB RAG search: no matches above confidence threshold")
                return RAGResult(
                    fact=claim,
                    matches=[],
                    confidence=0.0,
                    search_time_ms=(time.time() - start_time) * 1000,
                )

            # Calculate overall confidence as mean of match confidences
            overall_confidence = sum(m.confidence for m in matches) / len(matches)

            logger.info(
                "KB RAG search: found %d matches with confidence %.2f for claim: %s...",
                len(matches),
                overall_confidence,
                claim[:80],
            )

            return RAGResult(
                fact=claim,
                matches=matches,
                confidence=overall_confidence,
                search_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error("KB RAG search failed: %s", e)
            return None

    async def research_agent_lookup(self, claim: str) -> ResearchResult | None:
        """
        Delegate claim investigation to research agent.

        Calls research agent service to investigate the claim with timeout protection.
        Returns fact, status (FOUND/NOT_FOUND/CONFLICTING), URL, and confidence.

        Args:
            claim: Claim text to investigate

        Returns:
            ResearchResult with investigation outcome, or None on error/timeout
        """
        if not self.research_agent_service:
            logger.debug("Research agent service not available")
            return None

        try:
            start_time = time.time()
            logger.debug("Starting research agent lookup for claim: %s...", claim[:80])

            # Call research agent with timeout protection
            result = await asyncio.wait_for(
                self.research_agent_service.investigate_claim(claim),
                timeout=_RESEARCH_AGENT_TIMEOUT,
            )

            research_time_ms = (time.time() - start_time) * 1000

            # Parse result (assume research agent returns dict-like object)
            verified_fact = result.get("fact") if isinstance(result, dict) else getattr(result, "fact", None)
            status_str = result.get("status") if isinstance(result, dict) else getattr(result, "status", "not_found")
            url = result.get("url") if isinstance(result, dict) else getattr(result, "url", None)
            confidence = (
                result.get("confidence", 0.6) if isinstance(result, dict) else getattr(result, "confidence", 0.6)
            )

            # Validate status enum
            try:
                status = ResearchStatus(status_str) if isinstance(status_str, str) else status_str
            except ValueError:
                logger.warning("Invalid research status: %s, defaulting to NOT_FOUND", status_str)
                status = ResearchStatus.NOT_FOUND

            logger.info(
                "Research agent result: status=%s, confidence=%.2f, url=%s",
                status.value,
                confidence,
                url,
            )

            return ResearchResult(
                claim=claim,
                fact=verified_fact,
                status=status,
                url=url,
                confidence=confidence,
                research_time_ms=research_time_ms,
            )

        except asyncio.TimeoutError:
            logger.warning("Research agent lookup timed out after %.1fs", _RESEARCH_AGENT_TIMEOUT)
            return ResearchResult(
                claim=claim,
                fact=None,
                status=ResearchStatus.TIMEOUT,
                confidence=0.0,
                research_time_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            logger.error("Research agent lookup failed: %s", e)
            return None

    async def verify(self, claim: Claim) -> VerifiedClaim:
        """
        Verify a single claim using KB RAG and research agent.

        Strategy:
        1. IN_KB: Return VERIFIED with high confidence
        2. UNKNOWN:
           a) Try KB RAG search (fast, cheap)
           b) If confidence >= 0.7, return
           c) Escalate to research agent
           d) Return whichever has higher confidence
        3. CONTRADICTS: Return to ConflictResolver (mark requires_human_review)

        Args:
            claim: Claim to verify

        Returns:
            VerifiedClaim with verification status and sources
        """
        cache_key = self._build_cache_key(claim)

        # Check cache first
        cached = await self._get_from_cache(cache_key)
        if cached:
            return cached

        start_time = time.time()

        try:
            # Handle IN_KB status: immediate verification
            if claim.kb_status == KBStatus.IN_KB:
                logger.info("Claim already in KB, marking as VERIFIED")
                verified = VerifiedClaim(
                    original=claim,
                    verified_as=VerificationStatus.VERIFIED,
                    source="knowledge_base",
                    source_text=claim.kb_fact,
                    confidence=0.95,  # High confidence for KB matches
                )
                await self._set_to_cache(cache_key, verified)
                return verified

            # Handle CONTRADICTS status: escalate to ConflictResolver
            if claim.kb_status == KBStatus.CONTRADICTS:
                logger.warning("Claim contradicts KB, marking for human review")
                verified = VerifiedClaim(
                    original=claim,
                    verified_as=VerificationStatus.CONFLICTING,
                    source="knowledge_base",
                    source_text=claim.kb_fact,
                    confidence=0.0,
                    requires_human_review=True,
                )
                await self._set_to_cache(cache_key, verified)
                return verified

            # Handle UNKNOWN status: RAG search + optional research agent
            if claim.kb_status == KBStatus.UNKNOWN:
                rag_result = await self.kb_rag_search(claim.claim_text)
                rag_confidence = rag_result.confidence if rag_result else 0.0

                # If RAG confidence is high enough, return RAG result
                if rag_result and rag_confidence >= _RAG_CONFIDENCE_THRESHOLD:
                    logger.info("RAG search confidence %.2f >= threshold, returning result", rag_confidence)
                    verified = VerifiedClaim(
                        original=claim,
                        verified_as=(
                            VerificationStatus.VERIFIED if rag_confidence > 0.8 else VerificationStatus.UNVERIFIED
                        ),
                        source="kb_rag",
                        source_text=rag_result.matches[0].text if rag_result.matches else None,
                        source_url=rag_result.matches[0].url if rag_result.matches else None,
                        confidence=rag_confidence,
                    )
                    await self._set_to_cache(cache_key, verified)
                    return verified

                # RAG confidence too low, escalate to research agent
                research_result = await self.research_agent_lookup(claim.claim_text)

                if not research_result:
                    # Research agent unavailable or error
                    if rag_result:
                        # Fallback to RAG result
                        logger.warning("Research agent failed, falling back to RAG result")
                        verified = VerifiedClaim(
                            original=claim,
                            verified_as=VerificationStatus.UNVERIFIED,
                            source="kb_rag",
                            source_text=rag_result.matches[0].text if rag_result.matches else None,
                            confidence=rag_confidence,
                        )
                    else:
                        # No evidence found
                        verified = VerifiedClaim(
                            original=claim,
                            verified_as=VerificationStatus.ERROR,
                            source="unknown",
                            confidence=0.0,
                        )
                    await self._set_to_cache(cache_key, verified)
                    return verified

                # Compare RAG and research results, return best
                if research_result.confidence >= rag_confidence:
                    logger.info(
                        "Research agent confidence %.2f >= RAG %.2f, using research result",
                        research_result.confidence,
                        rag_confidence,
                    )
                    status_mapping = {
                        ResearchStatus.FOUND: VerificationStatus.VERIFIED,
                        ResearchStatus.NOT_FOUND: VerificationStatus.NOT_FOUND,
                        ResearchStatus.CONFLICTING: VerificationStatus.CONFLICTING,
                        ResearchStatus.TIMEOUT: VerificationStatus.TIMEOUT,
                    }
                    verified = VerifiedClaim(
                        original=claim,
                        verified_as=status_mapping.get(research_result.status, VerificationStatus.UNVERIFIED),
                        source="research_agent",
                        source_text=research_result.fact,
                        source_url=research_result.url,
                        confidence=research_result.confidence,
                    )
                else:
                    logger.info(
                        "RAG confidence %.2f > research agent %.2f, using RAG result",
                        rag_confidence,
                        research_result.confidence,
                    )
                    verified = VerifiedClaim(
                        original=claim,
                        verified_as=VerificationStatus.UNVERIFIED,
                        source="kb_rag",
                        source_text=rag_result.matches[0].text if rag_result and rag_result.matches else None,
                        confidence=rag_confidence,
                    )

                await self._set_to_cache(cache_key, verified)
                return verified

            # Fallback for AMBIGUOUS or unknown KB statuses
            logger.warning("Unknown KB status: %s, marking as unverified", claim.kb_status)
            verified = VerifiedClaim(
                original=claim,
                verified_as=VerificationStatus.UNVERIFIED,
                source="unknown",
                confidence=0.0,
            )
            await self._set_to_cache(cache_key, verified)
            return verified

        except Exception as e:
            logger.error("Claim verification failed: %s", e)
            verified = VerifiedClaim(
                original=claim,
                verified_as=VerificationStatus.ERROR,
                source="unknown",
                confidence=0.0,
            )
            return verified
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.debug("Claim verification completed in %.1fms", elapsed_ms)

    async def batch_verify(self, claims: List[Claim]) -> List[VerifiedClaim]:
        """
        Verify multiple claims in parallel with intelligent prioritization.

        Strategy:
        - UNKNOWN claims prioritized for research agent escalation
        - Parallel processing with bounded concurrency
        - Results cached for reuse

        Args:
            claims: List of claims to verify

        Returns:
            List of verified claims in same order as input
        """
        if not claims:
            return []

        logger.info("Starting batch verification for %d claims", len(claims))

        # Separate claims by status for smart prioritization
        in_kb_claims = [c for c in claims if c.kb_status == KBStatus.IN_KB]
        unknown_claims = [c for c in claims if c.kb_status == KBStatus.UNKNOWN]
        contradicts_claims = [c for c in claims if c.kb_status == KBStatus.CONTRADICTS]
        other_claims = [
            c for c in claims if c.kb_status not in (KBStatus.IN_KB, KBStatus.UNKNOWN, KBStatus.CONTRADICTS)
        ]

        # Create priority queue: IN_KB (fast) first, then UNKNOWN (slow), then others
        priority_queue = in_kb_claims + unknown_claims + contradicts_claims + other_claims

        # Verify with bounded concurrency (max 5 concurrent verifications)
        results_dict = {}
        semaphore = asyncio.Semaphore(5)

        async def verify_with_semaphore(claim: Claim) -> Tuple[str, VerifiedClaim]:
            """Verify claim with concurrency limit."""
            async with semaphore:
                result = await self.verify(claim)
                return (claim.claim_text, result)

        try:
            tasks = [verify_with_semaphore(claim) for claim in priority_queue]
            verification_results = await asyncio.gather(*tasks, return_exceptions=False)

            # Build results dict
            for claim_text, verified in verification_results:
                results_dict[claim_text] = verified

            # Return results in original order
            results = [results_dict.get(c.claim_text) for c in claims]

            logger.info("Batch verification completed: %d claims verified", len(results))
            return results

        except Exception as e:
            logger.error("Batch verification failed: %s", e)
            # Return unverified results as fallback
            return [
                VerifiedClaim(
                    original=c,
                    verified_as=VerificationStatus.ERROR,
                    source="unknown",
                    confidence=0.0,
                )
                for c in claims
            ]

    async def clear_cache(self) -> None:
        """Clear verification cache."""
        async with self._cache_lock:
            self._cache.clear()
        logger.info("Verification cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "cache_entries": len(self._cache),
            "kb_available": self.kb is not None,
            "research_agent_available": self.research_agent_service is not None,
        }
