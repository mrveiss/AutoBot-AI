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
    in ``services/grounded_agent.py``, not the FACT-provenance field of the same name
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
    Extracted and classified claim from LLM output.

    Attributes:
        claim_text: The extracted claim as text
        claim_type: Type classification (FACTUAL, PROCEDURAL, PREDICTIVE, OPINION)
        kb_status: Knowledge base matching status
        confidence: Overall confidence score (0.0-1.0)
        sources: List of matching KB sources
        kb_fact: If CONTRADICTS, the conflicting fact from KB
        timestamp: Unix timestamp of claim classification
        metadata: Additional context (original_context, claim_position, etc.)
    """

    claim_text: str
    claim_type: ClaimType
    kb_status: KBStatus
    confidence: float
    sources: List[KBSource] = field(default_factory=list)
    kb_fact: str | None = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert claim to dictionary for serialization."""
        return {
            "claim_text": self.claim_text,
            "claim_type": self.claim_type.value,
            "kb_status": self.kb_status.value,
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
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Claim":
        """Reconstruct claim from dictionary."""
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

        return cls(
            claim_text=data["claim_text"],
            claim_type=ClaimType(data["claim_type"]),
            kb_status=KBStatus(data["kb_status"]),
            confidence=data["confidence"],
            sources=sources,
            kb_fact=data.get("kb_fact"),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
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
