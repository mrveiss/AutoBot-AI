# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Quality-Diversity Archive for PromptOptimizer.

Issue #3222: Replaces the greedy top-K filter so all variants are retained
and parent selection uses random-weighted sampling (weight = score).
"""

from __future__ import annotations

import json
import random
from typing import List

from autobot_shared.logging_manager import get_logger

from .models import VariantArchiveEntry

logger = get_logger(__name__)


class Archive:
    """Stores all VariantArchiveEntry objects across optimization generations.

    All variants are retained regardless of score.  Parent selection is
    random-weighted so high-scoring variants are more likely to be chosen
    but low-scoring ones are never completely excluded.
    """

    def __init__(self, max_size: int | None = None) -> None:
        self._entries: List[VariantArchiveEntry] = []
        self._max_size = max_size

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add(self, entry: VariantArchiveEntry) -> None:
        """Add a new entry, optionally pruning if max_size is set."""
        self._entries.append(entry)
        if self._max_size and len(self._entries) > self._max_size:
            self._prune(self._max_size)

    def mark_invalid(self, variant_id: str) -> None:
        """Exclude *variant_id* from future parent selection."""
        for entry in self._entries:
            if entry.variant_id == variant_id:
                entry.valid_parent = False
                return

    def _prune(self, max_size: int) -> None:
        """Remove lowest-scoring entries until len <= max_size."""
        self._entries.sort(key=lambda e: e.score, reverse=True)
        self._entries = self._entries[:max_size]

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select_parent(self, strategy: str = "random_weighted") -> VariantArchiveEntry | None:
        """Return a parent entry using *strategy*.

        Supported strategies
        --------------------
        random_weighted
            Weight each valid entry by its score.  Falls back to uniform
            random when all scores are zero.
        """
        candidates = self.valid_parents
        if not candidates:
            logger.warning("Archive.select_parent: no valid parents available")
            return None

        if strategy != "random_weighted":
            logger.warning(
                "Archive.select_parent: unknown strategy %r, using random_weighted",
                strategy,
            )

        return self._weighted_random(candidates)

    def _weighted_random(self, candidates: List[VariantArchiveEntry]) -> VariantArchiveEntry:
        """Weighted-random selection; uniform fallback when all weights are 0."""
        weights = [max(e.score, 0.0) for e in candidates]
        total = sum(weights)
        if total == 0.0:
            return random.choice(candidates)
        return random.choices(candidates, weights=weights, k=1)[0]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def valid_parents(self) -> List[VariantArchiveEntry]:
        """All entries eligible for selection as a mutation parent."""
        return [e for e in self._entries if e.valid_parent]

    @property
    def best(self) -> VariantArchiveEntry | None:
        """Highest-scoring entry across the entire archive."""
        if not self._entries:
            return None
        return max(self._entries, key=lambda e: e.score)

    @property
    def size(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------------
    # Serialisation (for Redis persistence)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "max_size": self._max_size,
            "entries": [e.to_dict() for e in self._entries],
        }

    @classmethod
    def from_dict(cls, data: dict, variant_cls: type) -> "Archive":
        """Reconstruct an Archive from its serialised form.

        Args:
            data: dict produced by :meth:`to_dict`.
            variant_cls: the PromptVariant class used to reconstruct entries.
        """
        archive = cls(max_size=data.get("max_size"))
        for raw in data.get("entries", []):
            variant = variant_cls.from_dict(raw["variant"])
            entry = VariantArchiveEntry(
                variant_id=raw["variant_id"],
                variant=variant,
                score=raw["score"],
                parent_id=raw.get("parent_id"),
                generation=raw["generation"],
                valid_parent=raw.get("valid_parent", True),
                created_at=raw.get("created_at", 0.0),
            )
            archive._entries.append(entry)
        return archive

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str, variant_cls: type) -> "Archive":
        return cls.from_dict(json.loads(raw), variant_cls)
