# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Entity Mapping Data Models for AutoBot RAG Optimization

Defines data structures for entity resolution and relationship management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class EntityType(Enum):
    """Classification of entity types."""

    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    TECHNOLOGY = "TECHNOLOGY"
    CONCEPT = "CONCEPT"
    LOCATION = "LOCATION"
    PRODUCT = "PRODUCT"
    VERSION = "VERSION"
    CONFIGURATION = "CONFIGURATION"
    UNKNOWN = "UNKNOWN"


class SimilarityMethod(Enum):
    """Methods used for entity similarity calculation."""

    EXACT_MATCH = "exact_match"
    SEMANTIC_EMBEDDING = "semantic_embedding"
    FUZZY_STRING = "fuzzy_string"
    PATTERN_BASED = "pattern_based"
    HYBRID = "hybrid"


@dataclass
class EntityMapping:
    """
    Represents a mapping between different entity mentions to a canonical entity.
    """

    # Core identification
    canonical_id: str  # Unique identifier for the canonical entity
    canonical_name: str  # Primary/preferred name for the entity
    entity_type: EntityType  # Classification of the entity

    # Alternative names and mentions
    aliases: Set[str] = field(default_factory=set)  # All alternative names
    mentions: List[str] = field(default_factory=list)  # All mentions found

    # Confidence and validation
    confidence_score: float = 1.0  # Overall confidence in this mapping
    validation_status: str = "pending"  # pending, validated, rejected

    # Relationships
    related_entities: Set[str] = field(default_factory=set)  # Related entity IDs
    parent_entity: Optional[str] = None  # Hierarchical parent entity
    child_entities: Set[str] = field(default_factory=set)  # Child entities

    # Context and sources
    sources: Set[str] = field(default_factory=set)  # Sources where entity appears
    contexts: List[str] = field(default_factory=list)  # Context descriptions

    # Metadata
    creation_timestamp: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    created_by: str = "entity_resolution_system"

    # Statistics
    mention_count: int = 0  # Total number of mentions across sources
    fact_count: int = 0  # Number of facts involving this entity

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Post-initialization processing."""
        # Ensure canonical name is in aliases
        if self.canonical_name not in self.aliases:
            self.aliases.add(self.canonical_name)

        # Update mention count
        self.mention_count = len(self.mentions)

        # Ensure confidence is within bounds
        self.confidence_score = max(0.0, min(1.0, self.confidence_score))

    def add_alias(self, alias: str, confidence: float = 0.8):
        """
        Add an alias to this entity mapping.

        Args:
            alias: Alternative name for the entity
            confidence: Confidence in this alias mapping
        """
        if alias and alias.strip():
            self.aliases.add(alias.strip())
            self.mentions.append(alias.strip())
            self.mention_count += 1
            self.last_updated = datetime.now()

            # Adjust overall confidence based on new alias confidence
            self.confidence_score = (self.confidence_score + confidence) / 2

    def merge_with(self, other_mapping: "EntityMapping") -> "EntityMapping":
        """
        Merge this mapping with another mapping.

        Args:
            other_mapping: Another EntityMapping to merge

        Returns:
            New merged EntityMapping
        """
        # Use the mapping with higher confidence as base
        if other_mapping.confidence_score > self.confidence_score:
            primary = other_mapping
            secondary = self
        else:
            primary = self
            secondary = other_mapping

        merged = EntityMapping(
            canonical_id=primary.canonical_id,
            canonical_name=primary.canonical_name,
            entity_type=primary.entity_type,
            aliases=primary.aliases.union(secondary.aliases),
            mentions=primary.mentions + secondary.mentions,
            confidence_score=(primary.confidence_score + secondary.confidence_score)
            / 2,
            validation_status="pending",  # Reset validation status
            related_entities=primary.related_entities.union(secondary.related_entities),
            parent_entity=primary.parent_entity or secondary.parent_entity,
            child_entities=primary.child_entities.union(secondary.child_entities),
            sources=primary.sources.union(secondary.sources),
            contexts=primary.contexts + secondary.contexts,
            creation_timestamp=min(
                primary.creation_timestamp, secondary.creation_timestamp
            ),
            last_updated=datetime.now(),
            created_by="entity_resolution_merge",
            mention_count=primary.mention_count + secondary.mention_count,
            fact_count=primary.fact_count + secondary.fact_count,
            metadata={**primary.metadata, **secondary.metadata},
        )

        return merged

    def is_similar_to(self, other_name: str, threshold: float = 0.8) -> bool:
        """
        Check if another name is similar to this entity.

        Args:
            other_name: Name to compare
            threshold: Similarity threshold

        Returns:
            True if names are similar above threshold
        """
        other_name_lower = other_name.lower().strip()

        # Check exact matches in aliases
        for alias in self.aliases:
            if alias.lower().strip() == other_name_lower:
                return True

        # Check partial matches for compound names
        for alias in self.aliases:
            alias_lower = alias.lower().strip()
            # Check if one is contained in the other (for abbreviations)
            if len(other_name_lower) >= 3 and len(alias_lower) >= 3:
                if other_name_lower in alias_lower or alias_lower in other_name_lower:
                    return True

        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity mapping to dictionary."""
        return {
            "canonical_id": self.canonical_id,
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type.value,
            "aliases": list(self.aliases),
            "mentions": self.mentions,
            "confidence_score": self.confidence_score,
            "validation_status": self.validation_status,
            "related_entities": list(self.related_entities),
            "parent_entity": self.parent_entity,
            "child_entities": list(self.child_entities),
            "sources": list(self.sources),
            "contexts": self.contexts,
            "creation_timestamp": self.creation_timestamp.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "created_by": self.created_by,
            "mention_count": self.mention_count,
            "fact_count": self.fact_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntityMapping":
        """Create EntityMapping from dictionary."""
        return cls(
            canonical_id=data["canonical_id"],
            canonical_name=data["canonical_name"],
            entity_type=EntityType(data["entity_type"]),
            aliases=set(data.get("aliases", [])),
            mentions=data.get("mentions", []),
            confidence_score=data.get("confidence_score", 1.0),
            validation_status=data.get("validation_status", "pending"),
            related_entities=set(data.get("related_entities", [])),
            parent_entity=data.get("parent_entity"),
            child_entities=set(data.get("child_entities", [])),
            sources=set(data.get("sources", [])),
            contexts=data.get("contexts", []),
            creation_timestamp=datetime.fromisoformat(data["creation_timestamp"]),
            last_updated=datetime.fromisoformat(data["last_updated"]),
            created_by=data.get("created_by", "system"),
            mention_count=data.get("mention_count", 0),
            fact_count=data.get("fact_count", 0),
            metadata=data.get("metadata", {}),
        )

    def __str__(self) -> str:
        """String representation of the entity mapping."""
        return f"{self.canonical_name} ({self.entity_type.value}, {len(self.aliases)} aliases)"

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"EntityMapping(id={self.canonical_id[:8]}..., "
            f"name='{self.canonical_name}', type={self.entity_type.value}, "
            f"aliases={len(self.aliases)}, confidence={self.confidence_score:.3f})"
        )


@dataclass
class EntityResolutionResult:
    """Result of entity resolution operation."""

    original_entities: List[str]  # Original entity mentions
    resolved_mappings: Dict[str, str]  # Original -> Canonical mapping
    canonical_entities: List[EntityMapping]  # Resolved entity mappings

    # Statistics
    total_original: int = 0
    total_canonical: int = 0
    resolution_rate: float = 0.0  # Percentage of entities resolved

    # Metadata
    processing_time: float = 0.0
    similarity_method: SimilarityMethod = SimilarityMethod.HYBRID
    confidence_threshold: float = 0.8

    # Quality metrics
    high_confidence_resolutions: int = 0
    low_confidence_resolutions: int = 0
    exact_matches: int = 0
    semantic_matches: int = 0

    def __post_init__(self):
        """Calculate statistics after initialization."""
        self.total_original = len(self.original_entities)
        self.total_canonical = len(self.canonical_entities)

        if self.total_original > 0:
            self.resolution_rate = (
                (self.total_original - self.total_canonical) / self.total_original * 100
            )

        # Calculate confidence distribution
        for mapping in self.canonical_entities:
            if mapping.confidence_score >= 0.9:
                self.high_confidence_resolutions += 1
            elif mapping.confidence_score < 0.6:
                self.low_confidence_resolutions += 1

    def get_canonical_name(self, original_name: str) -> str:
        """Get canonical name for an original entity mention."""
        return self.resolved_mappings.get(original_name, original_name)

    def get_resolution_summary(self) -> Dict[str, Any]:
        """Get summary of resolution results."""
        return {
            "total_original_entities": self.total_original,
            "total_canonical_entities": self.total_canonical,
            "entities_merged": self.total_original - self.total_canonical,
            "resolution_rate": round(self.resolution_rate, 1),
            "processing_time": round(self.processing_time, 3),
            "similarity_method": self.similarity_method.value,
            "confidence_threshold": self.confidence_threshold,
            "quality_metrics": {
                "high_confidence": self.high_confidence_resolutions,
                "low_confidence": self.low_confidence_resolutions,
                "exact_matches": self.exact_matches,
                "semantic_matches": self.semantic_matches,
            },
        }


@dataclass
class EntityRelationship:
    """Represents a relationship between two entities."""

    source_entity_id: str
    target_entity_id: str
    relationship_type: str  # "parent_of", "similar_to", "related_to", etc.
    confidence: float
    evidence: List[str] = field(default_factory=list)  # Supporting evidence
    metadata: Dict[str, Any] = field(default_factory=dict)

    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "relationship_type": self.relationship_type,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }
