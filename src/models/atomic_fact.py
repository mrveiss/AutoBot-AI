# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Atomic Fact Data Models for AutoBot RAG Optimization

Defines the data structures for temporal knowledge management and atomic facts
extraction.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class FactType(Enum):
    """Classification of fact types based on their nature."""
    FACT = "FACT"  # Objective, verifiable information
    OPINION = "OPINION"  # Subjective statements or judgments
    PREDICTION = "PREDICTION"  # Future-oriented statements
    INSTRUCTION = "INSTRUCTION"  # Procedural or command information
    DEFINITION = "DEFINITION"  # Concept definitions or explanations


class TemporalType(Enum):
    """Classification of facts based on their temporal nature."""
    STATIC = "STATIC"  # Facts that don't change over time
    DYNAMIC = "DYNAMIC"  # Facts that can change or become outdated
    ATEMPORAL = "ATEMPORAL"  # Facts not bound to specific time periods
    TEMPORAL_BOUND = "TEMPORAL_BOUND"  # Facts valid only for specific time periods


class ConfidenceLevel(Enum):
    """Confidence levels for extracted facts."""
    VERY_HIGH = 0.9
    HIGH = 0.8
    MEDIUM = 0.6
    LOW = 0.4
    VERY_LOW = 0.2


# Confidence thresholds for classification (Issue #315: extracted for reduced nesting)
_CONFIDENCE_THRESHOLDS = [
    (0.9, "very_high"),
    (0.8, "high"),
    (0.6, "medium"),
    (0.4, "low"),
    (0.0, "very_low"),
]


def _classify_confidence(confidence: float) -> str:
    """Classify a confidence value into a range (Issue #315: extracted).

    Args:
        confidence: Confidence value between 0.0 and 1.0

    Returns:
        String key for the confidence range
    """
    for threshold, label in _CONFIDENCE_THRESHOLDS:
        if confidence >= threshold:
            return label
    return "very_low"


def _count_distribution(items: list, key_func) -> Dict[str, int]:
    """Count distribution of items by a key function (Issue #315: extracted).

    Args:
        items: List of items to count
        key_func: Function to extract the key from each item

    Returns:
        Dict mapping keys to counts
    """
    distribution = {}
    for item in items:
        key = key_func(item)
        distribution[key] = distribution.get(key, 0) + 1
    return distribution


@dataclass
class AtomicFact:
    """
    Represents a single atomic fact extracted from content.

    An atomic fact is the smallest unit of information that can be
    independently verified, contradicted, or invalidated.
    """

    # Core triplet structure (Subject-Predicate-Object)
    subject: str  # The entity the fact is about
    predicate: str  # The relationship or property
    object: str  # The value, entity, or description

    # Classification
    fact_type: FactType  # Type of fact (FACT, OPINION, etc.)
    temporal_type: TemporalType  # Temporal nature (STATIC, DYNAMIC, etc.)

    # Metadata
    confidence: float  # Confidence score (0.0 - 1.0)
    source: str  # Source identifier or document reference
    extraction_method: str  # Method used to extract this fact

    # Temporal information
    valid_from: datetime  # When this fact became/becomes valid
    valid_until: Optional[datetime] = None  # When this fact expires (if applicable)
    last_verified: Optional[datetime] = None  # Last verification timestamp

    # Unique identifier
    fact_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Entities and relationships
    entities: List[str] = field(default_factory=list)  # All entities mentioned
    related_facts: List[str] = field(default_factory=list)  # IDs of related facts

    # Context and provenance
    context: Optional[str] = None  # Surrounding context for this fact
    original_text: Optional[str] = None  # Original text from which fact was extracted
    chunk_id: Optional[str] = None  # ID of the chunk containing this fact

    # Invalidation tracking
    is_active: bool = True  # Whether this fact is currently considered valid
    invalidated_by: Optional[str] = None  # ID of fact that invalidated this one
    invalidation_reason: Optional[str] = None  # Reason for invalidation

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Post-initialization processing."""
        # Ensure confidence is within valid range
        self.confidence = max(0.0, min(1.0, self.confidence))

        # Set default last_verified to creation time if not provided
        if self.last_verified is None:
            self.last_verified = datetime.now()

        # Add subject and object to entities if not already included
        if self.subject not in self.entities:
            self.entities.append(self.subject)
        if self.object not in self.entities and self.object != self.subject:
            self.entities.append(self.object)

    def is_contradictory_to(self, other_fact: 'AtomicFact') -> bool:
        """
        Check if this fact contradicts another fact.

        Args:
            other_fact: Another AtomicFact to compare against

        Returns:
            True if the facts are contradictory
        """
        # Same subject and predicate but different objects might be contradictory
        if (self.subject == other_fact.subject
                and self.predicate == other_fact.predicate
                and self.object != other_fact.object):

            # Additional logic could be added here for more sophisticated
            # contradiction detection (e.g., using semantic similarity)
            return True

        return False

    def should_invalidate(self, new_fact: 'AtomicFact') -> bool:
        """
        Determine if this fact should be invalidated by a new fact.

        Args:
            new_fact: A new AtomicFact that might invalidate this one

        Returns:
            True if this fact should be invalidated
        """
        # Only dynamic facts can be invalidated by newer information
        if self.temporal_type != TemporalType.DYNAMIC:
            return False

        # Check if the new fact contradicts this one
        if new_fact.is_contradictory_to(self):
            # Only invalidate if the new fact is more recent and has
            # sufficient confidence
            return (new_fact.valid_from > self.valid_from
                    and new_fact.confidence >= 0.6)

        return False

    def invalidate(self, invalidating_fact: 'AtomicFact',
                   reason: str = "Contradicted by newer fact"):
        """
        Mark this fact as invalidated.

        Args:
            invalidating_fact: The fact that invalidates this one
            reason: Reason for invalidation
        """
        self.is_active = False
        self.valid_until = invalidating_fact.valid_from
        self.invalidated_by = invalidating_fact.fact_id
        self.invalidation_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        """Convert the atomic fact to a dictionary representation."""
        return {
            "fact_id": self.fact_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "fact_type": self.fact_type.value,
            "temporal_type": self.temporal_type.value,
            "confidence": self.confidence,
            "source": self.source,
            "extraction_method": self.extraction_method,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "last_verified": (self.last_verified.isoformat()
                              if self.last_verified else None),
            "entities": self.entities,
            "related_facts": self.related_facts,
            "context": self.context,
            "original_text": self.original_text,
            "chunk_id": self.chunk_id,
            "is_active": self.is_active,
            "invalidated_by": self.invalidated_by,
            "invalidation_reason": self.invalidation_reason,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AtomicFact':
        """Create an AtomicFact from a dictionary representation."""
        # Parse datetime fields
        valid_from = datetime.fromisoformat(data["valid_from"])
        valid_until = (datetime.fromisoformat(data["valid_until"])
                       if data.get("valid_until") else None)
        last_verified = (datetime.fromisoformat(data["last_verified"])
                         if data.get("last_verified") else None)

        return cls(
            fact_id=data["fact_id"],
            subject=data["subject"],
            predicate=data["predicate"],
            object=data["object"],
            fact_type=FactType(data["fact_type"]),
            temporal_type=TemporalType(data["temporal_type"]),
            confidence=data["confidence"],
            source=data["source"],
            extraction_method=data["extraction_method"],
            valid_from=valid_from,
            valid_until=valid_until,
            last_verified=last_verified,
            entities=data.get("entities", []),
            related_facts=data.get("related_facts", []),
            context=data.get("context"),
            original_text=data.get("original_text"),
            chunk_id=data.get("chunk_id"),
            is_active=data.get("is_active", True),
            invalidated_by=data.get("invalidated_by"),
            invalidation_reason=data.get("invalidation_reason"),
            metadata=data.get("metadata", {})
        )

    def with_resolved_entities(
        self,
        resolved_subject: str,
        resolved_object: str,
        resolved_entities: List[str],
    ) -> "AtomicFact":
        """Create a copy with resolved entity names (Issue #372 - reduces feature envy).

        Args:
            resolved_subject: The resolved canonical name for subject
            resolved_object: The resolved canonical name for object
            resolved_entities: List of resolved entity names

        Returns:
            New AtomicFact with resolved entities, preserving all other fields
        """
        return AtomicFact(
            subject=resolved_subject,
            predicate=self.predicate,
            object=resolved_object,
            fact_type=self.fact_type,
            temporal_type=self.temporal_type,
            confidence=self.confidence,
            source=self.source,
            extraction_method=self.extraction_method,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            last_verified=self.last_verified,
            fact_id=self.fact_id,
            entities=resolved_entities,
            related_facts=self.related_facts,
            context=self.context,
            original_text=self.original_text,
            chunk_id=self.chunk_id,
            is_active=self.is_active,
            invalidated_by=self.invalidated_by,
            invalidation_reason=self.invalidation_reason,
            metadata=self.metadata,
        )

    def to_redis_mapping(self, json_data: str) -> Dict[str, str]:
        """Convert to Redis hash mapping for pipeline storage (Issue #372 - reduces feature envy).

        Args:
            json_data: Pre-serialized JSON data for the 'data' field

        Returns:
            Dict with string values suitable for Redis hset mapping
        """
        return {
            "data": json_data,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "fact_type": self.fact_type.value,
            "temporal_type": self.temporal_type.value,
            "confidence": str(self.confidence),
            "source": self.source,
            "is_active": str(self.is_active),
            "valid_from": self.valid_from.isoformat(),
        }

    def get_index_keys(self) -> List[str]:
        """Get list of index keys for this fact (Issue #372 - reduces feature envy).

        Returns:
            List of index key suffixes for fact indices
        """
        return [
            f"facts_by_source:{self.source}",
            f"facts_by_type:{self.fact_type.value}",
            f"facts_by_temporal:{self.temporal_type.value}",
        ]

    def mark_invalidated(
        self, reason: Optional[Dict[str, Any]] = None, service: str = "unknown"
    ) -> None:
        """Mark this fact as invalidated with metadata (Issue #372 - reduces feature envy).

        Args:
            reason: Optional invalidation reason dict
            service: Name of the service performing invalidation
        """
        self.is_active = False
        self.valid_until = datetime.now()
        self.metadata = self.metadata or {}
        self.metadata.update({
            "invalidated_at": datetime.now().isoformat(),
            "invalidation_reason": reason or {},
            "invalidation_service": service,
        })

    def __str__(self) -> str:
        """String representation of the atomic fact."""
        status = "ACTIVE" if self.is_active else "INVALIDATED"
        return (f"{self.subject} {self.predicate} {self.object} "
                f"[{self.fact_type.value}, {status}]")

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (f"AtomicFact(id={self.fact_id[:8]}..., "
                f"subject='{self.subject}', predicate='{self.predicate}', "
                f"object='{self.object}', confidence={self.confidence}, "
                f"active={self.is_active})")


@dataclass
class FactExtractionResult:
    """Result of fact extraction operation."""

    facts: List[AtomicFact]
    extraction_metadata: Dict[str, Any] = field(default_factory=dict)
    processing_time: Optional[float] = None
    confidence_distribution: Dict[str, int] = field(default_factory=dict)
    fact_type_distribution: Dict[str, int] = field(default_factory=dict)
    temporal_type_distribution: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        """Calculate distributions after initialization.

        Issue #315: Refactored to use helper functions for reduced nesting.
        """
        if not self.facts:
            return

        # Calculate confidence distribution using helper
        self.confidence_distribution = _count_distribution(
            self.facts, lambda f: _classify_confidence(f.confidence)
        )

        # Calculate fact type distribution
        self.fact_type_distribution = _count_distribution(
            self.facts, lambda f: f.fact_type.value
        )

        # Calculate temporal type distribution
        self.temporal_type_distribution = _count_distribution(
            self.facts, lambda f: f.temporal_type.value
        )

    @property
    def total_facts(self) -> int:
        """Total number of extracted facts."""
        return len(self.facts)

    @property
    def active_facts(self) -> List[AtomicFact]:
        """List of currently active facts."""
        return [fact for fact in self.facts if fact.is_active]

    @property
    def average_confidence(self) -> float:
        """Average confidence of all facts."""
        if not self.facts:
            return 0.0
        return sum(fact.confidence for fact in self.facts) / len(self.facts)

    def facts_by_type(self, fact_type: FactType) -> List[AtomicFact]:
        """Get facts filtered by type."""
        return [fact for fact in self.facts if fact.fact_type == fact_type]

    def facts_by_temporal_type(self, temporal_type: TemporalType) -> List[AtomicFact]:
        """Get facts filtered by temporal type."""
        return [fact for fact in self.facts if fact.temporal_type == temporal_type]
