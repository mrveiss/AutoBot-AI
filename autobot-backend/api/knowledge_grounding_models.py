# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Grounding Data Models - Tier 4 Conflict Resolution.

Defines data structures for KB facts, agent claims, research results,
conflict detection, and resolution tracking. Used by ConflictResolver
service to determine ground truth between competing information sources.

Issue #4070: Tier 4 (Knowledge Grounding) — handle KB vs agent claim
conflicts with confidence scoring, age decay, and human review escalation.

Models:
- KBFact: Knowledge base fact with confidence and timestamp
- Claim: Agent assertion with source and confidence
- ResearchResult: Extended research finding with validation
- ResolvedClaim: Final resolved truth with source and reasoning
- Conflict: Conflict record for analysis and escalation
- ReviewTicket: Human review request with metadata
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List
from uuid import uuid4


class SourceType(str, Enum):
    """Types of information sources for facts."""

    DOCUMENT = "document"  # From KB documents
    LOG = "log"  # From system logs
    CODE = "code"  # From codebase analysis
    MEASUREMENT = "measurement"  # From direct measurement/monitoring
    RESEARCH = "research"  # From web research
    AGENT = "agent"  # From agent assertion


class ConflictResolution(str, Enum):
    """Possible outcomes of conflict resolution."""

    KB_WINS = "kb_wins"  # Knowledge base fact was most confident
    RESEARCH_WINS = "research_wins"  # Research result was most confident
    AGENT_WINS = "agent_wins"  # Agent claim was most confident
    HUMAN_REVIEW = "human_review"  # Escalated for human decision
    UNRESOLVED = "unresolved"  # Could not resolve with confidence


class ReviewTicketStatus(str, Enum):
    """Status of human review ticket."""

    PENDING = "pending"  # Waiting for review
    REVIEWING = "reviewing"  # Currently being reviewed
    RESOLVED = "resolved"  # Resolved by human
    DISMISSED = "dismissed"  # Rejected as false conflict


class ReviewTicketPriority(str, Enum):
    """Priority level for human review."""

    LOW = "low"  # Confidence difference 0.05-0.1
    MEDIUM = "medium"  # Confidence difference 0.0-0.05
    HIGH = "high"  # Critical facts with low confidence


# ===== DATA MODELS =====


@dataclass
class KBFact:
    """Knowledge base fact with confidence and age tracking.

    Attributes:
        fact_text: The actual fact/claim
        source_id: Unique identifier of the source (document ID, etc.)
        confidence: Base confidence score [0.0-1.0]
        timestamp: Unix timestamp of when this was recorded
        source_type: Type of source (document, log, code, etc.)
        metadata: Optional additional metadata (tags, categories, etc.)
    """

    fact_text: str
    source_id: str
    confidence: float
    timestamp: float
    source_type: str = "document"
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        """Validate confidence is in valid range."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.confidence}")

    def age_days(self) -> float:
        """Get fact age in days.

        Returns:
            Float: Number of days since the fact was recorded
        """
        return (time.time() - self.timestamp) / 86400

    def effective_confidence(self) -> float:
        """Calculate confidence adjusted for age (age decay).

        Age decay strategy:
        - < 7 days: 100% of confidence (fresh data)
        - 7-30 days: 80% of confidence (relatively fresh)
        - 30-90 days: 60% of confidence (aging)
        - > 90 days: 40% of confidence (stale)

        Returns:
            Float: Effective confidence [0.0-1.0] after age adjustment
        """
        age = self.age_days()
        if age < 7:
            return self.confidence
        elif age < 30:
            return self.confidence * 0.8
        elif age < 90:
            return self.confidence * 0.6
        else:
            return self.confidence * 0.4

    def is_stale(self) -> bool:
        """Check if fact is considered stale (>30 days old).

        Returns:
            Bool: True if age > 30 days
        """
        return self.age_days() > 30


@dataclass
class Claim:
    """Agent claim/assertion to compare against KB facts.

    Attributes:
        claim_text: The actual claim being made
        source: Where the claim came from (agent name, etc.)
        confidence: Confidence level [0.0-1.0], defaults to 0.5 for unknown
        timestamp: Unix timestamp of when claim was made
        metadata: Additional metadata (reasoning, sources, etc.)
    """

    claim_text: str
    source: str
    confidence: float = 0.5
    timestamp: float | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        """Validate and normalize claim."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class ResearchResult:
    """Result from web research validation.

    Attributes:
        fact_text: What the research found
        source: URL or source description
        confidence: Confidence in the finding [0.0-1.0]
        timestamp: When this research was performed
        source_type: Type of source (documentation, tutorial, etc.)
        evidence: List of supporting evidence snippets
    """

    fact_text: str
    source: str
    confidence: float
    timestamp: float | None = None
    source_type: str = "research"
    evidence: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate research result."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class ResolvedClaim:
    """Final resolved truth after conflict resolution.

    Attributes:
        claim: The resolved claim text
        source: Source of the winning claim
        confidence: Final confidence in the resolution [0.0-1.0]
        kb_fact: Original KB fact if present
        research_result: Research result if used
        agent_claim: Agent claim if used
        update_kb: Whether KB should be updated with this claim
        requires_human_review: Whether human review was needed
        reasoning: Explanation of why this resolution was chosen
        resolution_type: How conflict was resolved
    """

    claim: str
    source: str
    confidence: float
    kb_fact: KBFact | None = None
    research_result: ResearchResult | None = None
    agent_claim: Claim | None = None
    update_kb: bool = False
    requires_human_review: bool = False
    reasoning: str = ""
    resolution_type: ConflictResolution = ConflictResolution.KB_WINS

    def __post_init__(self):
        """Validate resolved claim."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.confidence}")


@dataclass
class Conflict:
    """Record of a conflict between KB and agent claim.

    Tracks all three sources (KB, agent, research) and their confidence
    levels for analysis and escalation to human review if needed.

    Attributes:
        kb_says: The KB fact involved
        agent_says: The agent claim involved
        research_says: Research validation result if available
        kb_confidence: Effective confidence of KB fact
        agent_confidence: Confidence of agent claim
        research_confidence: Confidence of research result
        created_at: Unix timestamp when conflict was detected
        conflict_id: Unique identifier for this conflict
    """

    kb_says: KBFact
    agent_says: Claim
    kb_confidence: float
    agent_confidence: float
    research_says: ResearchResult | None = None
    research_confidence: float = 0.0
    created_at: float = field(default_factory=time.time)
    conflict_id: str = field(default_factory=lambda: str(uuid4()))

    def max_confidence(self) -> float:
        """Get highest confidence across all sources.

        Returns:
            Float: Maximum confidence value
        """
        return max(self.kb_confidence, self.agent_confidence, self.research_confidence)

    def confidence_gap(self) -> float:
        """Calculate gap between highest and second-highest confidence.

        Returns:
            Float: Difference between max and second-max confidence
        """
        confidences = sorted(
            [self.kb_confidence, self.agent_confidence, self.research_confidence],
            reverse=True,
        )
        return confidences[0] - confidences[1]


@dataclass
class ReviewTicket:
    """Human review ticket for conflicts that need human decision.

    Tracks a conflict escalated for human review with metadata about
    the sources and their confidence scores.

    Attributes:
        ticket_id: Unique identifier for this ticket
        conflict: The underlying conflict
        priority: Priority level (high/medium/low)
        status: Current status (pending/reviewing/resolved/dismissed)
        resolution: Final resolution if ticket was resolved
        resolved_by: User who resolved it (if resolved)
        resolved_at: Timestamp when resolved
        notes: Human notes or explanation of decision
    """

    ticket_id: str
    conflict: Conflict
    priority: ReviewTicketPriority
    status: ReviewTicketStatus = ReviewTicketStatus.PENDING
    resolution: ResolvedClaim | None = None
    resolved_by: str | None = None
    resolved_at: float | None = None
    notes: str = ""
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create_from_conflict(cls, conflict: Conflict, priority: ReviewTicketPriority) -> "ReviewTicket":
        """Factory method to create a ticket from a conflict.

        Args:
            conflict: The conflict to escalate
            priority: Priority level

        Returns:
            ReviewTicket: New ticket ready for human review
        """
        return cls(
            ticket_id=str(uuid4()),
            conflict=conflict,
            priority=priority,
        )

    def resolve(self, resolution: ResolvedClaim, resolved_by: str, notes: str = "") -> None:
        """Mark this ticket as resolved.

        Args:
            resolution: The final resolved claim
            resolved_by: Who made the decision
            notes: Optional explanation
        """
        self.resolution = resolution
        self.resolved_by = resolved_by
        self.resolved_at = time.time()
        self.status = ReviewTicketStatus.RESOLVED
        self.notes = notes

    def dismiss(self, resolved_by: str, notes: str = "") -> None:
        """Mark this ticket as dismissed (false conflict).

        Args:
            resolved_by: Who made the decision
            notes: Why it was dismissed
        """
        self.resolved_by = resolved_by
        self.resolved_at = time.time()
        self.status = ReviewTicketStatus.DISMISSED
        self.notes = notes
