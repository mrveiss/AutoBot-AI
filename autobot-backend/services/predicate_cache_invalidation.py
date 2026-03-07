#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Predicate-Bounded Cache Invalidation — scoped invalidation by data partition.

Instead of invalidating all caches when data changes, this module scopes
invalidation to only the affected data partition (e.g., only invalidate
2024 caches when 2024 data changes).

Issue: #1378

Predicate types:
  - temporal: year/month/quarter ranges
  - categorical: knowledge domain, source type
  - entity: specific document or fact ID
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Predicate types
# ---------------------------------------------------------------------------


class PredicateType(str, Enum):
    """Types of cache partition predicates."""

    TEMPORAL = "temporal"
    CATEGORICAL = "categorical"
    ENTITY = "entity"


@dataclass
class CachePredicate:
    """Metadata describing a cache entry's data partition scope.

    Each cached result is tagged with one or more predicates so that
    invalidation can be scoped to just the affected partition.
    """

    predicate_type: PredicateType
    key: str  # e.g. "year", "category", "document_id"
    value: str  # e.g. "2024", "system_knowledge", "fact:abc123"

    def matches(self, other: "CachePredicate") -> bool:
        """Check if this predicate overlaps with another."""
        if self.predicate_type != other.predicate_type:
            return False
        if self.key != other.key:
            return False
        return self.value == other.value or self.value == "*"


@dataclass
class PredicateSet:
    """Collection of predicates describing a cache entry's scope."""

    predicates: List[CachePredicate] = field(default_factory=list)

    def to_dict(self) -> List[Dict[str, str]]:
        """Serialize predicates for storage in cache metadata."""
        return [
            {
                "type": p.predicate_type.value,
                "key": p.key,
                "value": p.value,
            }
            for p in self.predicates
        ]

    @classmethod
    def from_dict(cls, data: List[Dict[str, str]]) -> "PredicateSet":
        """Deserialize predicates from cache metadata."""
        predicates = []
        for item in data:
            try:
                predicates.append(
                    CachePredicate(
                        predicate_type=PredicateType(item["type"]),
                        key=item["key"],
                        value=item["value"],
                    )
                )
            except (KeyError, ValueError):
                continue
        return cls(predicates=predicates)

    def matches_any(self, invalidation_predicates: List[CachePredicate]) -> bool:
        """Check if any stored predicate matches any invalidation predicate."""
        for stored in self.predicates:
            for inv in invalidation_predicates:
                if stored.matches(inv):
                    return True
        return False

    def add_temporal(self, key: str, value: str) -> None:
        """Add a temporal predicate (year, month, quarter)."""
        self.predicates.append(
            CachePredicate(
                predicate_type=PredicateType.TEMPORAL,
                key=key,
                value=value,
            )
        )

    def add_categorical(self, key: str, value: str) -> None:
        """Add a categorical predicate (domain, source type)."""
        self.predicates.append(
            CachePredicate(
                predicate_type=PredicateType.CATEGORICAL,
                key=key,
                value=value,
            )
        )

    def add_entity(self, entity_id: str) -> None:
        """Add an entity-scoped predicate (document or fact ID)."""
        self.predicates.append(
            CachePredicate(
                predicate_type=PredicateType.ENTITY,
                key="entity_id",
                value=entity_id,
            )
        )


# ---------------------------------------------------------------------------
# Predicate extraction from content metadata
# ---------------------------------------------------------------------------

# Patterns to extract temporal predicates from metadata
_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
_MONTH_PATTERN = re.compile(r"\b(20\d{2}-(?:0[1-9]|1[0-2]))\b")


def extract_predicates_from_metadata(
    metadata: Dict[str, Any],
) -> PredicateSet:
    """Extract cache predicates from fact/document metadata. Ref: #1378.

    Inspects common metadata fields to build a predicate set:
    - timestamp/date fields → temporal predicates
    - category/source_type fields → categorical predicates
    - fact_id/document_id → entity predicates
    """
    pset = PredicateSet()

    # Temporal predicates from timestamp
    timestamp = metadata.get("timestamp", "")
    if isinstance(timestamp, str):
        year_match = _YEAR_PATTERN.search(timestamp)
        if year_match:
            pset.add_temporal("year", year_match.group(1))
        month_match = _MONTH_PATTERN.search(timestamp)
        if month_match:
            pset.add_temporal("month", month_match.group(1))

    # Categorical predicates
    for cat_key in ("category", "source_type", "knowledge_domain"):
        cat_val = metadata.get(cat_key)
        if cat_val and isinstance(cat_val, str):
            pset.add_categorical(cat_key, cat_val)

    # Entity predicates
    for id_key in ("fact_id", "document_id"):
        id_val = metadata.get(id_key)
        if id_val and isinstance(id_val, str):
            pset.add_entity(id_val)

    return pset


def build_invalidation_predicates(
    changed_metadata: Dict[str, Any],
) -> List[CachePredicate]:
    """Build invalidation predicates from changed source metadata. Ref: #1378.

    When a source document changes, this function extracts which partitions
    are affected so that only matching cache entries get invalidated.
    """
    pset = extract_predicates_from_metadata(changed_metadata)
    return pset.predicates


# ---------------------------------------------------------------------------
# Scoped invalidation
# ---------------------------------------------------------------------------


async def invalidate_by_predicates(
    predicates: List[CachePredicate],
    cache_entries: List[Dict[str, Any]],
) -> List[str]:
    """Identify cache entries matching the given predicates. Ref: #1378.

    Args:
        predicates: List of invalidation predicates to match against.
        cache_entries: Cache entries with 'key' and 'predicates' fields.

    Returns:
        List of cache keys that should be invalidated.
    """
    keys_to_invalidate: List[str] = []

    for entry in cache_entries:
        entry_predicates = entry.get("predicates", [])
        if not entry_predicates:
            continue

        pset = PredicateSet.from_dict(entry_predicates)
        if pset.matches_any(predicates):
            cache_key = entry.get("key", "")
            if cache_key:
                keys_to_invalidate.append(cache_key)

    if keys_to_invalidate:
        logger.info(
            "Predicate invalidation: %d/%d entries matched",
            len(keys_to_invalidate),
            len(cache_entries),
        )

    return keys_to_invalidate
