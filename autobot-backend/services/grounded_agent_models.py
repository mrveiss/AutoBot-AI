# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
GroundedAgent data models - Tier 4 (Knowledge Grounding).

The claim, verification, conflict and response types that GroundedAgent
(services/grounded_agent.py) produces and the knowledge-grounding API returns.
Split out of the agent module so the orchestration and the data it passes
around can each be read, and sized, on their own (#14981).

Not the same types as the claim classifier's Claim/KBStatus in
services/knowledge_grounding_models.py, or the conflict resolver's
Claim/Conflict/ConflictResolution in api/knowledge_grounding_models.py: the same
domain, but different shapes, each with its own callers.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List
from uuid import uuid4


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
    verification_method: str = ""  # a VerificationMethod value; see #15005
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
