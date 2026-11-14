# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Grounding Data Models - Tier 4 Knowledge Grounding

This module defines the data structures for claim extraction and classification.

Issue: Knowledge Grounding Tier 4 implementation
- Claim: Extracted factual assertion from LLM output
- ClaimType: Categorization of claim types (FACTUAL, PROCEDURAL, PREDICTIVE, OPINION)
- KBStatus: Classification result (IN_KB, UNKNOWN, CONTRADICTS, AMBIGUOUS)
- KBSource: Source reference from knowledge base
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List
from uuid import uuid4


class ClaimType(str, Enum):
    """
    Categorization of claim types based on content characteristics.

    - FACTUAL: Observable, verifiable assertions ("Latency is 500ms", "Port 8080 is open")
    - PROCEDURAL: Process-oriented claims ("Should cache this", "Use config from file")
    - PREDICTIVE: Causal/outcome claims ("Adding memory will improve performance")
    - OPINION: Subjective statements ("This is inefficient", "Better approach")
    """

    FACTUAL = "factual"
    PROCEDURAL = "procedural"
    PREDICTIVE = "predictive"
    OPINION = "opinion"


class KBStatus(str, Enum):
    """
    Knowledge base matching status for a claim.

    - IN_KB: Found corroborating information in knowledge base
    - UNKNOWN: Not found in knowledge base
    - CONTRADICTS: Knowledge base contains conflicting information
    - AMBIGUOUS: Multiple conflicting sources in knowledge base
    """

    IN_KB = "in_kb"
    UNKNOWN = "unknown"
    CONTRADICTS = "contradicts"
    AMBIGUOUS = "ambiguous"


class VerificationMethod(str, Enum):
    """
    How an extracted CLAIM was verified (#15005) — ``VerifiedClaim.verification_method``
    in ``services/grounded_agent_models.py``, not the FACT-provenance field of the same name
    (see the boundary note below; do not add that vocabulary here).

    Lives here rather than beside ``VerificationStatus`` in
    ``services/claim_verifier.py`` because that file is grandfathered at its
    current line count in ``python_file_size_known_large.py`` and may not
    grow; this module is already a shared import for that domain.

    Two members are produced today — read the call site, not the #15005
    issue body, which named a different three and missed one of these:

    - KB_LOOKUP: matched directly against the knowledge base
      (``services/grounded_agent.py::GroundedAgent._classify_claim`` and its
      unverified fallback).
    - CLAIM_VERIFIER_RAG: escalated to ``ClaimVerifier.kb_rag_search`` when KB
      match confidence was too low
      (``GroundedAgent._escalate_to_claim_verifier``).

    Two members are reserved, not yet produced by anything: EXTERNAL_RESEARCH
    and CAUSAL_INFERENCE name the research-agent and
    ``CausalInferenceEngine`` escalation tiers documented in
    ``VerifiedClaim.verification_method``'s original comment and in
    ``api/knowledge_grounding.py``'s fabricated ``claim_sources`` breakdown
    (#14981 — a separate bug: that endpoint currently returns hardcoded
    ratios, not real counts). Kept as members so #14981's fix has a rung to
    key its per-method counts on rather than inventing the spelling again;
    do not treat their presence as evidence either tier is wired up.

    Boundary, found while ground-truthing #15005 — do NOT fold this in: a
    SECOND, unrelated ``verification_method`` field exists on facts
    (``knowledge/facts.py``'s ``_PROVENANCE_DEFAULTS``,
    ``api/knowledge_verification.py``, ``api/schemas_knowledge.py:3146``),
    describing how a *fact's provenance* was verified
    (``auto_quality``/``user_approved``/``connector_trusted``), not how a
    *claim* was. The one real value it produces, ``"user_approved"``,
    coincides with a spelling a human could also use for a claim, but the
    two vocabularies do not otherwise overlap — a fact is never
    ``kb_lookup``-verified and a claim is never ``connector_trusted``.
    Merging them would be the wrong-enum mistake #14988 found in
    ``command_patterns.py``, not a consolidation.
    """

    KB_LOOKUP = "kb_lookup"
    CLAIM_VERIFIER_RAG = "claim_verifier_rag"
    EXTERNAL_RESEARCH = "external_research"
    CAUSAL_INFERENCE = "causal_inference"


@dataclass
class KBSource:
    """
    Reference to a source in the knowledge base that matched a claim.

    Attributes:
        source_id: Unique identifier in knowledge base
        source_type: Category of source ("document", "log", "metric", "code", "procedure")
        text: Relevant text excerpt from source
        confidence: Match confidence (0.0-1.0)
        age_days: Days since source was created/updated
        url: Optional URL or reference link
    """

    source_id: str
    source_type: str
    text: str
    confidence: float
    age_days: float
    url: str | None = None


@dataclass
class Claim:
    """
    The one Claim model for the knowledge-grounding tiers (#18086).

    Replaces three same-named dataclasses: the classifier's (claim_type/kb_status/
    sources/kb_fact), GroundedAgent's (claim_id/subject/predicate/object) and the
    conflict resolver's (source). A claim is classified, extracted or asserted by
    an agent; every field a given producer does not know keeps its neutral default.

    Attributes:
        claim_text: The claim as text
        claim_type: Classifier output (FACTUAL, PROCEDURAL, ...); None until classified
        kb_status: KB matching status; None until matched
        confidence: Confidence in [0.0, 1.0]; 0.5 means "unknown"
        sources: Matching KB sources
        kb_fact: If CONTRADICTS, the conflicting fact from the KB
        timestamp: Unix time of creation (filled in when omitted)
        metadata: Additional context (original_context, reasoning, ...)
        claim_id: Stable id, referenced by Conflict.claim_1_id
        source: Who made the claim (agent name, ...)
        subject, predicate, object: Extracted triple, empty when not extracted
    """

    claim_text: str
    claim_type: ClaimType | None = None
    kb_status: KBStatus | None = None
    confidence: float = 0.5
    sources: List[KBSource] = field(default_factory=list)
    kb_fact: str | None = None
    timestamp: float | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    claim_id: str = field(default_factory=lambda: str(uuid4()))
    source: str = ""
    subject: str = ""
    predicate: str = ""
    object: str = ""

    def __post_init__(self):
        """Validate confidence and stamp the creation time."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert claim to dictionary for serialization."""
        return {
            "claim_text": self.claim_text,
            "claim_type": self.claim_type.value if self.claim_type else None,
            "kb_status": self.kb_status.value if self.kb_status else None,
            "confidence": self.confidence,
            "sources": [
                {
                    "source_id": s.source_id,
                    "source_type": s.source_type,
                    "text": s.text,
                    "confidence": s.confidence,
                    "age_days": s.age_days,
                    "url": s.url,
                }
                for s in self.sources
            ],
            "kb_fact": self.kb_fact,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "claim_id": self.claim_id,
            "source": self.source,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Claim":
        """Reconstruct claim from dictionary (tolerates pre-merge cached payloads)."""
        sources = [
            KBSource(
                source_id=s["source_id"],
                source_type=s["source_type"],
                text=s["text"],
                confidence=s["confidence"],
                age_days=s["age_days"],
                url=s.get("url"),
            )
            for s in data.get("sources", [])
        ]
        claim_type = data.get("claim_type")
        kb_status = data.get("kb_status")
        extra = {k: data[k] for k in ("claim_id", "source", "subject", "predicate", "object") if k in data}
        return cls(
            claim_text=data["claim_text"],
            claim_type=ClaimType(claim_type) if claim_type else None,
            kb_status=KBStatus(kb_status) if kb_status else None,
            confidence=data["confidence"],
            sources=sources,
            kb_fact=data.get("kb_fact"),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
            **extra,
        )


class ClaimStatus(str, Enum):
    """Status of a claim in the grounding process (GroundedAgent's vocabulary)."""

    IN_KB = "in_kb"  # Claim verified in knowledge base
    UNKNOWN = "unknown"  # Claim not found in KB, needs research
    CONTRADICTS = "contradicts"  # Claim contradicts KB knowledge
    VERIFIED = "verified"  # Claim verified through external source
    UNVERIFIABLE = "unverifiable"  # Claim cannot be verified
    CONFLICTED = "conflicted"  # Claim conflicts with other verified claims


class VerificationStatus(str, Enum):
    """Outcome of ClaimVerifier's verification (the verifier's vocabulary)."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class VerifiedClaim:
    """
    The one verified-claim model (#18086), replacing GroundedAgent's and ClaimVerifier's.

    GroundedAgent fills ``kb_status`` (a ClaimStatus), ``kb_source`` (KB fact id),
    ``evidence`` and ``verification_method``; ClaimVerifier fills ``verified_as`` (a
    VerificationStatus), ``source`` (channel: knowledge_base, kb_rag, research_agent),
    ``source_text``/``source_url`` and ``requires_human_review``. Each producer leaves the
    other's fields at their neutral default.
    """

    claim: Claim
    kb_status: ClaimStatus | None = None
    verified_as: VerificationStatus | None = None
    kb_source: str | None = None
    source: str = ""
    source_text: str | None = None
    source_url: str | None = None
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)
    verification_method: str = ""  # a VerificationMethod value; see #15005
    timestamp: float = field(default_factory=time.time)
    requires_human_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for the verifier's Redis cache (key names are the cached wire shape)."""
        return {
            "original_claim": self.claim.to_dict(),
            "verified_as": self.verified_as.value if self.verified_as else None,
            "kb_status": self.kb_status.value if self.kb_status else None,
            "source": self.source,
            "source_text": self.source_text,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "requires_human_review": self.requires_human_review,
            "kb_source": self.kb_source,
            "evidence": self.evidence,
            "verification_method": self.verification_method,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerifiedClaim":
        """Rebuild from :meth:`to_dict` output; tolerates pre-merge cached payloads."""
        verified_as = data.get("verified_as", "unverified")
        kb_status = data.get("kb_status")
        return cls(
            claim=Claim.from_dict(data.get("original_claim", {})),
            verified_as=VerificationStatus(verified_as) if verified_as else None,
            kb_status=ClaimStatus(kb_status) if kb_status else None,
            source=data.get("source", "unknown"),
            source_text=data.get("source_text"),
            source_url=data.get("source_url"),
            confidence=data.get("confidence", 0.0),
            timestamp=data.get("timestamp", time.time()),
            requires_human_review=data.get("requires_human_review", False),
            kb_source=data.get("kb_source"),
            evidence=data.get("evidence", []),
            verification_method=data.get("verification_method", ""),
        )


@dataclass
class ClaimExtractionResult:
    """
    Result of claim extraction from LLM response.

    Attributes:
        claims: List of extracted claims
        extraction_confidence: Overall extraction confidence (0.0-1.0)
        method: Extraction method used (pattern, nlp, hybrid)
        processing_time_ms: Time taken to extract claims
    """

    claims: List[str]
    extraction_confidence: float
    method: str
    processing_time_ms: float = 0.0
