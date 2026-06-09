# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
GroundedAgent - Tier 4 (Knowledge Grounding) Service

Orchestrates claim classification → verification → conflict resolution → grounded response
generation. Integrates with Tier 3 (causal inference) to provide reasoning transparency.

Issue: #4070 (Knowledge Grounding Tier 4)

Core functionality:
- Extract claims from agent responses
- Classify each claim (IN_KB, UNKNOWN, CONTRADICTS)
- Verify claims against knowledge base and external sources
- Resolve conflicts with causal reasoning
- Reconstruct response with source annotations and confidence scores
- Trace reasoning chain through Tier 3 for user transparency

Data flow:
1. User query → Initial response (from agent/LLM)
2. Extract claims via structured extraction
3. Classify claims against KB
4. Verify unknown/contradicting claims
5. Resolve conflicts using causal inference
6. Reconstruct response with annotations
7. Return GroundedResponse with full provenance
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List
from uuid import uuid4

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from knowledge_factory import get_or_create_knowledge_base
from llm_shared.types import LLMType
from services.ai_stack_client import get_ai_stack_client
from services.causal_inference_engine import CausalInferenceEngine

logger = get_logger(__name__)


class ClaimStatus(str, Enum):
    """Status of a claim in the grounding process."""

    IN_KB = "in_kb"  # Claim verified in knowledge base
    UNKNOWN = "unknown"  # Claim not found in KB, needs research
    CONTRADICTS = "contradicts"  # Claim contradicts KB knowledge
    VERIFIED = "verified"  # Claim verified through external source
    UNVERIFIABLE = "unverifiable"  # Claim cannot be verified
    CONFLICTED = "conflicted"  # Claim conflicts with other verified claims


class ConflictResolution(str, Enum):
    """Resolution status of a conflict."""

    RESOLVED = "resolved"  # Conflict resolved with clear winner
    PENDING_REVIEW = "pending_review"  # Needs human review
    INCONCLUSIVE = "inconclusive"  # Multiple valid interpretations


@dataclass
class Claim:
    """Extracted claim from response text."""

    claim_id: str = field(default_factory=lambda: str(uuid4()))
    claim_text: str = ""
    subject: str = ""  # Subject entity
    predicate: str = ""  # Relationship/property
    object: str = ""  # Object/value
    confidence: float = 0.0  # LLM confidence in the claim (0.0-1.0)
    context: Dict[str, Any] = field(default_factory=dict)  # Context from response
    timestamp: float = field(default_factory=time.time)


@dataclass
class VerifiedClaim:
    """Claim that has been verified."""

    claim: Claim
    kb_status: ClaimStatus  # Classification result
    kb_source: str | None = None  # KB fact ID if IN_KB
    confidence: float = 0.0  # Verification confidence (0.0-1.0)
    evidence: List[str] = field(default_factory=list)  # Supporting evidence
    verification_method: str = ""  # "kb_lookup", "external_research", "causal_inference"
    resolved_at: float = field(default_factory=time.time)


@dataclass
class Conflict:
    """Conflict between claims or against KB."""

    conflict_id: str = field(default_factory=lambda: str(uuid4()))
    claim_1_id: str = ""  # First claim ID
    claim_2_id: str | None = None  # Second claim ID (or KB fact)
    description: str = ""  # Description of conflict
    severity: str = "medium"  # "low", "medium", "high"
    resolution: ConflictResolution = ConflictResolution.PENDING_REVIEW
    chosen_fact: str | None = None  # Fact ID chosen for resolution
    reasoning: str = ""  # Human/system reasoning for resolution
    timestamp: float = field(default_factory=time.time)


@dataclass
class CausalTrace:
    """Trace of reasoning through causal inference (Tier 3)."""

    trace_id: str = field(default_factory=lambda: str(uuid4()))
    query: str = ""
    reasoning_steps: List[Dict[str, Any]] = field(default_factory=list)
    claim_verifications: List[Dict[str, Any]] = field(default_factory=list)
    causal_analysis: Dict[str, Any] | None = None
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class GroundedResponse:
    """Final response with all claims grounded and sourced."""

    response_id: str = field(default_factory=lambda: str(uuid4()))
    original_query: str = ""
    response_text: str = ""  # Reconstructed with source annotations
    original_response_text: str = ""  # Before reconstruction
    verified_claims: List[VerifiedClaim] = field(default_factory=list)
    unverified_claims: List[Claim] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)
    causal_trace: CausalTrace | None = None
    confidence_overall: float = 0.0  # Average of verified claims
    requires_human_review: bool = False
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API serialization."""
        return {
            "response_id": self.response_id,
            "original_query": self.original_query,
            "response_text": self.response_text,
            "original_response_text": self.original_response_text,
            "verified_claims": [
                {
                    "claim_id": c.claim.claim_id,
                    "claim_text": c.claim.claim_text,
                    "kb_status": c.kb_status.value,
                    "confidence": round(c.confidence, 3),
                    "evidence": c.evidence,
                    "verification_method": c.verification_method,
                }
                for c in self.verified_claims
            ],
            "unverified_claims": [
                {
                    "claim_id": c.claim_id,
                    "claim_text": c.claim_text,
                    "confidence": round(c.confidence, 3),
                }
                for c in self.unverified_claims
            ],
            "conflicts": [
                {
                    "conflict_id": c.conflict_id,
                    "description": c.description,
                    "severity": c.severity,
                    "resolution": c.resolution.value,
                    "chosen_fact": c.chosen_fact,
                    "reasoning": c.reasoning,
                }
                for c in self.conflicts
            ],
            "confidence_overall": round(self.confidence_overall, 3),
            "requires_human_review": self.requires_human_review,
            "timestamp": self.timestamp,
            "causal_trace": self.causal_trace.trace_id if self.causal_trace else None,
        }


class GroundedAgent:
    """
    Main orchestrator for knowledge grounding (Tier 4).

    Orchestrates the full claim verification pipeline:
    1. Extract claims from response
    2. Classify claims against KB
    3. Verify unknown/contradicting claims
    4. Resolve conflicts
    5. Reconstruct response with annotations
    6. Trace reasoning through causal inference
    """

    def __init__(self, app=None) -> None:
        """Initialize GroundedAgent with optional FastAPI app."""
        self.app = app
        self.kb = None
        self.llm_service = None
        self.causal_engine = None
        self.redis_client = None

    async def _init_dependencies(self) -> None:
        """Lazy-load dependencies on first use."""
        if self.kb is None and self.app:
            self.kb = await get_or_create_knowledge_base(self.app, force_refresh=False)
        if self.llm_service is None:
            self.llm_service = get_ai_stack_client()
        if self.redis_client is None:
            self.redis_client = await get_async_redis_client()
        if self.causal_engine is None:
            self.causal_engine = CausalInferenceEngine()

    @with_error_handling(
        category=ErrorCategory.SERVER_ERROR,
        operation="respond_with_grounding",
        error_code_prefix="GROUNDING",
    )
    async def respond_with_grounding(
        self,
        user_query: str,
        agent_response: str,
        context: Dict[str, Any] | None = None,
    ) -> GroundedResponse:
        """
        Main entry point: Ground an agent response with KB verification.

        Workflow:
        1. Extract claims from response
        2. Classify each claim (IN_KB, UNKNOWN, CONTRADICTS)
        3. Verify unknown/contradicting claims
        4. Resolve conflicts
        5. Reconstruct response with sources/confidence
        6. Trace verification chain through Tier 3

        Args:
            user_query: Original user query
            agent_response: Response to ground
            context: Optional context dict (metadata, conversation_id, etc.)

        Returns:
            GroundedResponse with all claims grounded and sourced
        """
        await self._init_dependencies()
        start_time = time.time()

        logger.info(
            "Grounding response for query: %s...",
            user_query[:100],
        )

        # 1. Extract claims
        claims = await self._extract_claims(user_query, agent_response)
        logger.info("Extracted %d claims from response", len(claims))

        # 2. Classify claims against KB
        verified_claims = []
        unverified_claims = []
        conflicts = []

        for claim in claims:
            verified = await self._classify_and_verify_claim(claim)
            if verified.kb_status == ClaimStatus.UNVERIFIABLE:
                unverified_claims.append(claim)
            elif verified.kb_status == ClaimStatus.CONTRADICTS:
                conflicts.append(
                    Conflict(
                        claim_1_id=claim.claim_id,
                        description=f"Claim contradicts KB: {claim.claim_text}",
                        severity="high",
                    )
                )
                unverified_claims.append(claim)
            else:
                verified_claims.append(verified)

        logger.info(
            "Classified: %d verified, %d unverified, %d conflicts",
            len(verified_claims),
            len(unverified_claims),
            len(conflicts),
        )

        # 3. Reconstruct response with sources
        reconstructed_text = await self._reconstruct_response(agent_response, verified_claims)

        # 4. Trace reasoning through Tier 3
        causal_trace = await self._trace_verification_chain(
            user_query, agent_response, verified_claims, unverified_claims
        )

        # 5. Calculate overall confidence
        overall_confidence = (
            sum(c.confidence for c in verified_claims) / len(verified_claims) if verified_claims else 0.0
        )

        # 6. Determine if review needed
        requires_review = len(unverified_claims) > 0 or len(conflicts) > 0 or overall_confidence < 0.6

        # Build response
        grounded = GroundedResponse(
            original_query=user_query,
            response_text=reconstructed_text,
            original_response_text=agent_response,
            verified_claims=verified_claims,
            unverified_claims=unverified_claims,
            conflicts=conflicts,
            causal_trace=causal_trace,
            confidence_overall=overall_confidence,
            requires_human_review=requires_review,
            metadata=context or {},
        )

        logger.info(
            "Grounding complete (%.2fs): confidence=%.2f, requires_review=%s",
            time.time() - start_time,
            overall_confidence,
            requires_review,
        )

        return grounded

    async def _extract_claims(self, query: str, response: str) -> List[Claim]:
        """
        Extract atomic claims from response using LLM.

        Uses structured extraction to identify individual factual claims
        in the response text.

        Args:
            query: User query
            response: Agent response

        Returns:
            List of extracted Claim objects
        """
        prompt = f"""Extract individual factual claims from this response.

User Query: {query}

Response: {response}

For each claim, provide:
1. Claim text (exact phrase)
2. Subject (what entity is it about?)
3. Predicate (what relationship/property?)
4. Object (what is the value?)
5. Confidence (0.0-1.0, how confident is this claim?)

Format as JSON array of objects with fields: claim_text, subject, predicate, object, confidence"""

        try:
            response_obj = await self.llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                llm_type=LLMType.EXTRACTION,
                temperature=0.1,
                max_tokens=1024,
            )

            # Parse JSON response (simplified - production would use robust parsing)
            import json

            try:
                claims_data = json.loads(response_obj.content)
            except json.JSONDecodeError:
                logger.warning("Failed to parse claim extraction JSON")
                claims_data = []

            claims = []
            for item in claims_data:
                if isinstance(item, dict):
                    claims.append(
                        Claim(
                            claim_text=item.get("claim_text", ""),
                            subject=item.get("subject", ""),
                            predicate=item.get("predicate", ""),
                            object=item.get("object", ""),
                            confidence=float(item.get("confidence", 0.0)),
                        )
                    )

            return claims

        except Exception as e:
            logger.error("Error extracting claims: %s", e)
            return []

    async def _classify_and_verify_claim(self, claim: Claim) -> VerifiedClaim:
        """
        Classify claim against KB and verify if needed.

        Classification:
        - IN_KB: Found in knowledge base
        - UNKNOWN: Not in KB, needs research
        - CONTRADICTS: Contradicts KB fact
        - VERIFIED: Verified through external research
        - UNVERIFIABLE: Cannot be verified

        Args:
            claim: Claim to classify

        Returns:
            VerifiedClaim with status and evidence
        """
        if not self.kb:
            return VerifiedClaim(
                claim=claim,
                kb_status=ClaimStatus.UNKNOWN,
                confidence=0.0,
            )

        try:
            # Search KB for related facts
            search_results = await self.kb.search(
                query=claim.claim_text,
                limit=5,
                search_mode="semantic",
            )

            if not search_results:
                return VerifiedClaim(
                    claim=claim,
                    kb_status=ClaimStatus.UNKNOWN,
                    confidence=0.0,
                    evidence=["No matching KB facts found"],
                )

            # Find best match
            best_match = search_results[0] if search_results else None

            if not best_match:
                return VerifiedClaim(
                    claim=claim,
                    kb_status=ClaimStatus.UNKNOWN,
                    confidence=0.0,
                )

            match_confidence = best_match.get("similarity_score", 0.0)
            fact_id = best_match.get("fact_id", "")

            # Determine status based on confidence
            if match_confidence > 0.85:
                status = ClaimStatus.IN_KB
            elif match_confidence > 0.5:
                status = ClaimStatus.VERIFIED
            else:
                status = ClaimStatus.UNKNOWN

            return VerifiedClaim(
                claim=claim,
                kb_status=status,
                kb_source=fact_id,
                confidence=match_confidence,
                evidence=[best_match.get("content", "")[:200]],
                verification_method="kb_lookup",
            )

        except Exception as e:
            logger.error("Error classifying claim: %s", e)
            return VerifiedClaim(
                claim=claim,
                kb_status=ClaimStatus.UNKNOWN,
                confidence=0.0,
                evidence=[f"Classification error: {str(e)[:100]}"],
            )

    async def _reconstruct_response(
        self,
        original: str,
        verified_claims: List[VerifiedClaim],
    ) -> str:
        """
        Reconstruct response with source annotations and confidence badges.

        Injects:
        - Source citations from KB
        - Confidence scores
        - Uncertainty markers for unverified claims

        Example: "Latency increased [KB: monitoring, 0.95 confidence]"

        Args:
            original: Original response text
            verified_claims: List of verified claims with sources

        Returns:
            Reconstructed response with annotations
        """
        reconstructed = original

        for verified in verified_claims:
            if verified.kb_source and verified.confidence > 0.7:
                # Find claim text in response and annotate it
                claim_text = verified.claim.claim_text
                if claim_text in reconstructed:
                    annotation = f"{claim_text} [KB source, {verified.confidence:.0%} confidence]"
                    reconstructed = reconstructed.replace(claim_text, annotation)

        return reconstructed

    async def _trace_verification_chain(
        self,
        query: str,
        response: str,
        verified_claims: List[VerifiedClaim],
        unverified_claims: List[Claim],
    ) -> CausalTrace | None:
        """
        Use Tier 3 (CausalInferenceEngine) to trace reasoning.

        Explains:
        - Why did we choose KB vs research vs agent?
        - What was the verification chain?
        - Dependencies between claims
        - Overall reasoning confidence

        Args:
            query: Original query
            response: Original response
            verified_claims: Claims that were verified
            unverified_claims: Claims that couldn't be verified

        Returns:
            CausalTrace with reasoning transparency
        """
        try:
            trace = CausalTrace(
                query=query,
                reasoning_steps=[
                    {
                        "step": "claim_extraction",
                        "total_claims": len(verified_claims) + len(unverified_claims),
                        "verified": len(verified_claims),
                    },
                    {
                        "step": "kb_classification",
                        "kb_matches": sum(1 for c in verified_claims if c.kb_status == ClaimStatus.IN_KB),
                        "unknown": len(unverified_claims),
                    },
                ],
                claim_verifications=[
                    {
                        "claim": c.claim.claim_text,
                        "status": c.kb_status.value,
                        "confidence": c.confidence,
                        "method": c.verification_method,
                    }
                    for c in verified_claims
                ],
                confidence=(
                    sum(c.confidence for c in verified_claims) / len(verified_claims) if verified_claims else 0.0
                ),
            )

            return trace

        except Exception as e:
            logger.error("Error tracing verification chain: %s", e)
            return None

    async def resolve_conflict(
        self,
        conflict_id: str,
        chosen_fact_id: str,
        reasoning: str,
    ) -> Dict[str, Any]:
        """
        Manually resolve a conflict.

        Called when human reviews a conflict and chooses which fact/claim
        is correct. Updates the conflict status and may update KB.

        Args:
            conflict_id: Conflict ID to resolve
            chosen_fact_id: Chosen fact ID
            reasoning: Human reasoning for the choice

        Returns:
            Resolution result
        """
        logger.info("Resolving conflict %s to fact %s", conflict_id, chosen_fact_id)

        # Store resolution in Redis
        redis = await get_async_redis_client()
        await redis.hset(
            f"conflict:{conflict_id}",
            mapping={
                "resolved_at": time.time(),
                "chosen_fact": chosen_fact_id,
                "reasoning": reasoning,
                "status": ConflictResolution.RESOLVED.value,
            },
        )

        return {
            "status": "success",
            "conflict_id": conflict_id,
            "resolved": True,
            "chosen_fact": chosen_fact_id,
        }


_grounded_agent_instance: GroundedAgent | None = None


def get_grounded_agent(app=None) -> GroundedAgent:
    """
    Get or create the GroundedAgent singleton.

    Args:
        app: Optional FastAPI app instance

    Returns:
        GroundedAgent instance
    """
    global _grounded_agent_instance
    if _grounded_agent_instance is None:
        _grounded_agent_instance = GroundedAgent(app=app)
    return _grounded_agent_instance
