# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Feedback and per-pattern statistics records for the pattern-learning engine (Issue #235).

Split out of ``api/analytics_pattern_learning.py`` (#16375) so that router stays
under its size ceiling; the engine imports both records back from here.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from api.schemas_analytics import FeedbackType

MIN_FEEDBACK_FOR_CONFIDENCE = 3  # Minimum feedback count for reliable scoring


@dataclass
class FeedbackRecord:
    """Internal representation of feedback."""

    feedback_id: str
    pattern_id: str
    feedback_type: FeedbackType
    file_path: str
    line_number: int
    code_snippet: str | None
    developer_comment: str | None
    suggested_fix: str | None
    timestamp: datetime
    weight: float = 1.0

    # === Issue #372: Feature Envy Reduction Methods ===

    def get_age_weeks(self, now: datetime) -> float:
        """Get age of this feedback in weeks (Issue #372 - reduces feature envy)."""
        return (now - self.timestamp).days / 7.0

    def get_normalized_weight(self) -> float:
        """Get weight normalized to 0-1 range (Issue #372 - reduces feature envy)."""
        return (self.weight + 1.0) / 2.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response (Issue #372 - reduces feature envy)."""
        return {
            "feedback_id": self.feedback_id,
            "feedback_type": self.feedback_type.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
            "developer_comment": self.developer_comment,
            "timestamp": self.timestamp.isoformat(),
            "weight": self.weight,
        }


@dataclass
class PatternStats:
    """Statistics for a pattern."""

    pattern_id: str
    feedback_history: List[FeedbackRecord] = field(default_factory=list)
    correct_count: int = 0
    incorrect_count: int = 0
    missed_count: int = 0
    partial_count: int = 0
    irrelevant_count: int = 0
    raw_score: float = 0.5  # Start at neutral
    confidence_score: float = 0.5
    last_updated: datetime = field(default_factory=datetime.now)
    version: int = 1

    # === Issue #372: Feature Envy Reduction Methods ===

    @property
    def total_feedback_count(self) -> int:
        """Get total feedback count (Issue #372 - reduces feature envy)."""
        return (
            self.correct_count + self.incorrect_count + self.missed_count + self.partial_count + self.irrelevant_count
        )

    @property
    def feedback_count(self) -> int:
        """Get count of feedback history entries (Issue #372 - reduces feature envy)."""
        return len(self.feedback_history)

    @property
    def has_sufficient_feedback(self) -> bool:
        """Check if has minimum feedback for confidence (Issue #372)."""
        return self.feedback_count >= MIN_FEEDBACK_FOR_CONFIDENCE

    @property
    def has_conflicting_feedback(self) -> bool:
        """Check if feedback is conflicting (Issue #372 - reduces feature envy)."""
        return self.correct_count > 0 and self.incorrect_count > 0

    @property
    def conflict_ratio(self) -> float:
        """Get conflict ratio between correct and incorrect (Issue #372)."""
        total = self.correct_count + self.incorrect_count
        return min(self.correct_count, self.incorrect_count) / max(total, 1)

    def get_active_learning_priority(self) -> float:
        """Calculate priority score for active learning (Issue #372)."""
        priority = 0.0
        # Low confidence = high priority
        if self.confidence_score < 0.4:
            priority += 0.5
        # Conflicting feedback = high priority
        priority += self.conflict_ratio * 0.3
        # Little feedback = moderate priority
        if not self.has_sufficient_feedback:
            priority += 0.2
        return priority

    def get_most_recent_snippet(self) -> str:
        """Get most recent code snippet from feedback (Issue #372)."""
        if not self.feedback_history:
            return ""
        sorted_feedback = sorted(self.feedback_history, key=lambda x: x.timestamp, reverse=True)
        return sorted_feedback[0].code_snippet or "" if sorted_feedback else ""
