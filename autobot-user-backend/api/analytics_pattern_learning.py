# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Self-Improving Pattern Recognition System (Issue #235)

Implements feedback collection, pattern confidence scoring, and active learning
to continuously improve code pattern detection accuracy.

Key Features:
- Developer feedback collection for pattern matches
- Redis-based feedback persistence
- Confidence scoring with decay over time
- Active learning pipeline for pattern refinement
- Learning metrics and performance tracking
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Enums and Constants
# =============================================================================


class FeedbackType(str, Enum):
    """Types of feedback developers can provide."""

    CORRECT = "correct"  # Pattern match is accurate
    INCORRECT = "incorrect"  # False positive
    MISSED = "missed"  # False negative - pattern should have matched
    PARTIAL = "partial"  # Partially correct
    IRRELEVANT = "irrelevant"  # Not useful pattern


class PatternCategory(str, Enum):
    """Categories of patterns for organization."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    CODE_QUALITY = "code_quality"
    ARCHITECTURE = "architecture"
    ERROR_HANDLING = "error_handling"
    CONCURRENCY = "concurrency"
    DATA_FLOW = "data_flow"
    CONTROL_FLOW = "control_flow"
    STYLE = "style"
    DOCUMENTATION = "documentation"


class LearningPhase(str, Enum):
    """Phases of the active learning pipeline."""

    COLLECTING = "collecting"  # Gathering feedback
    ANALYZING = "analyzing"  # Analyzing patterns
    TRAINING = "training"  # Updating models
    VALIDATING = "validating"  # Validating changes
    DEPLOYED = "deployed"  # Changes active


class ConfidenceLevel(str, Enum):
    """Human-readable confidence levels."""

    VERY_LOW = "very_low"  # < 0.2
    LOW = "low"  # 0.2 - 0.4
    MEDIUM = "medium"  # 0.4 - 0.6
    HIGH = "high"  # 0.6 - 0.8
    VERY_HIGH = "very_high"  # > 0.8


# Confidence thresholds
CONFIDENCE_THRESHOLDS = {
    ConfidenceLevel.VERY_LOW: 0.0,
    ConfidenceLevel.LOW: 0.2,
    ConfidenceLevel.MEDIUM: 0.4,
    ConfidenceLevel.HIGH: 0.6,
    ConfidenceLevel.VERY_HIGH: 0.8,
}

# Feedback weight factors
FEEDBACK_WEIGHTS = {
    FeedbackType.CORRECT: 1.0,
    FeedbackType.INCORRECT: -1.0,
    FeedbackType.MISSED: -0.5,
    FeedbackType.PARTIAL: 0.3,
    FeedbackType.IRRELEVANT: -0.2,
}

# Time decay factor (confidence decays over time without new feedback)
CONFIDENCE_DECAY_RATE = 0.95  # Per week
MIN_FEEDBACK_FOR_CONFIDENCE = 3  # Minimum feedback count for reliable scoring


# =============================================================================
# Data Models
# =============================================================================


class PatternFeedback(BaseModel):
    """Feedback for a specific pattern match."""

    pattern_id: str = Field(..., description="Unique identifier for the pattern")
    feedback_type: FeedbackType = Field(..., description="Type of feedback")
    file_path: str = Field(..., description="File where pattern was detected")
    line_number: int = Field(..., description="Line number of pattern match")
    code_snippet: Optional[str] = Field(None, description="Code snippet context")
    developer_comment: Optional[str] = Field(None, description="Developer notes")
    suggested_fix: Optional[str] = Field(None, description="Suggested improvement")
    timestamp: Optional[datetime] = Field(None, description="Feedback timestamp")


class PatternDefinition(BaseModel):
    """Definition of a learnable pattern."""

    pattern_id: str = Field(..., description="Unique pattern identifier")
    name: str = Field(..., description="Human-readable pattern name")
    description: str = Field(..., description="Pattern description")
    category: PatternCategory = Field(..., description="Pattern category")
    regex_patterns: List[str] = Field(
        default_factory=list, description="Regex patterns"
    )
    ast_patterns: List[str] = Field(
        default_factory=list, description="AST pattern descriptions"
    )
    examples: List[str] = Field(default_factory=list, description="Example matches")
    counter_examples: List[str] = Field(
        default_factory=list, description="Non-matching examples"
    )
    severity: str = Field(default="medium", description="Pattern severity")
    enabled: bool = Field(default=True, description="Whether pattern is active")


class ConfidenceScore(BaseModel):
    """Confidence score for a pattern."""

    pattern_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    level: ConfidenceLevel
    total_feedback: int
    correct_count: int
    incorrect_count: int
    last_updated: datetime
    trend: str  # "improving", "stable", "declining"


class LearningMetrics(BaseModel):
    """Metrics for the learning pipeline."""

    total_patterns: int
    total_feedback: int
    average_confidence: float
    high_confidence_patterns: int
    low_confidence_patterns: int
    patterns_improved: int
    patterns_degraded: int
    feedback_by_type: Dict[str, int]
    feedback_by_category: Dict[str, int]
    learning_rate: float
    last_training_run: Optional[datetime]


class ActiveLearningQuery(BaseModel):
    """Query for active learning suggestions."""

    pattern_id: str
    code_snippet: str
    predicted_match: bool
    confidence: float
    question: str  # Question to ask developer


class PatternUpdate(BaseModel):
    """Update to a pattern based on learning."""

    pattern_id: str
    update_type: str  # "regex_added", "regex_removed", "threshold_adjusted", etc.
    old_value: Optional[Any]
    new_value: Optional[Any]
    reason: str
    applied_at: datetime


# =============================================================================
# Pattern Learning Engine
# =============================================================================


@dataclass
class FeedbackRecord:
    """Internal representation of feedback."""

    feedback_id: str
    pattern_id: str
    feedback_type: FeedbackType
    file_path: str
    line_number: int
    code_snippet: Optional[str]
    developer_comment: Optional[str]
    suggested_fix: Optional[str]
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
            self.correct_count
            + self.incorrect_count
            + self.missed_count
            + self.partial_count
            + self.irrelevant_count
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
        sorted_feedback = sorted(
            self.feedback_history, key=lambda x: x.timestamp, reverse=True
        )
        return sorted_feedback[0].code_snippet or "" if sorted_feedback else ""


class PatternLearningEngine:
    """
    Core engine for self-improving pattern recognition.

    Manages feedback collection, confidence scoring, and active learning.
    """

    def __init__(self):
        """Initialize pattern learning engine with empty patterns and stats."""
        self.patterns: Dict[str, PatternDefinition] = {}
        self.pattern_stats: Dict[str, PatternStats] = {}
        self.feedback_queue: List[FeedbackRecord] = []
        self.learning_phase = LearningPhase.COLLECTING
        self.redis_client = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> bool:
        """Initialize the learning engine with Redis connection."""
        if self._initialized:
            return True

        async with self._lock:
            if self._initialized:
                return True

            try:
                from src.utils.redis_client import get_redis_client

                self.redis_client = await get_redis_client(
                    async_client=True, database="analytics"
                )
                # Issue #379: Parallelize independent Redis loading operations
                await asyncio.gather(
                    self._load_patterns_from_redis(),
                    self._load_feedback_from_redis(),
                )
                self._initialized = True
                logger.info("Pattern Learning Engine initialized successfully")
                return True
            except Exception as e:
                logger.error("Failed to initialize Pattern Learning Engine: %s", e)
                # Continue with in-memory storage
                self._initialized = True
                return True

    async def _load_patterns_from_redis(self):
        """Load pattern definitions from Redis."""
        if not self.redis_client:
            return

        try:
            pattern_keys = []
            cursor = 0
            while True:
                cursor, keys = await self.redis_client.scan(
                    cursor, match="pattern:definition:*", count=100
                )
                pattern_keys.extend(keys)
                if cursor == 0:
                    break

            # Batch fetch all patterns using mget - eliminates N+1
            if pattern_keys:
                all_data = await self.redis_client.mget(pattern_keys)
                for data in all_data:
                    if data:
                        pattern_data = json.loads(data)
                        pattern = PatternDefinition(**pattern_data)
                        self.patterns[pattern.pattern_id] = pattern

            logger.info("Loaded %s patterns from Redis", len(self.patterns))
        except Exception as e:
            logger.warning("Failed to load patterns from Redis: %s", e)

    def _parse_pattern_stats(self, stats_data: dict) -> PatternStats:
        """Parse stats data into PatternStats object."""
        return PatternStats(
            pattern_id=stats_data["pattern_id"],
            correct_count=stats_data.get("correct_count", 0),
            incorrect_count=stats_data.get("incorrect_count", 0),
            missed_count=stats_data.get("missed_count", 0),
            partial_count=stats_data.get("partial_count", 0),
            irrelevant_count=stats_data.get("irrelevant_count", 0),
            raw_score=stats_data.get("raw_score", 0.5),
            confidence_score=stats_data.get("confidence_score", 0.5),
            last_updated=datetime.fromisoformat(
                stats_data.get("last_updated", datetime.now().isoformat())
            ),
            version=stats_data.get("version", 1),
        )

    async def _load_feedback_from_redis(self):
        """Load feedback history and stats from Redis."""
        if not self.redis_client:
            return

        try:
            stats_keys = []
            cursor = 0
            while True:
                cursor, keys = await self.redis_client.scan(
                    cursor, match="pattern:stats:*", count=100
                )
                stats_keys.extend(keys)
                if cursor == 0:
                    break

            if not stats_keys:
                logger.info("No pattern stats found in Redis")
                return

            # Batch fetch all stats using mget - eliminates N+1
            all_data = await self.redis_client.mget(stats_keys)

            for data in all_data:
                if not data:
                    continue
                stats_data = json.loads(data)
                pattern_id = stats_data.get("pattern_id")
                if not pattern_id:
                    continue
                self.pattern_stats[pattern_id] = self._parse_pattern_stats(stats_data)

            logger.info("Loaded stats for %s patterns", len(self.pattern_stats))
        except Exception as e:
            logger.warning("Failed to load stats from Redis: %s", e)

    async def submit_feedback(self, feedback: PatternFeedback) -> Dict[str, Any]:
        """
        Submit developer feedback for a pattern match.

        Args:
            feedback: Pattern feedback from developer

        Returns:
            Feedback processing result
        """
        await self.initialize()

        # Generate feedback ID
        feedback_id = hashlib.sha256(
            f"{feedback.pattern_id}:{feedback.file_path}:{feedback.line_number}:"
            f"{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        # Create feedback record
        record = FeedbackRecord(
            feedback_id=feedback_id,
            pattern_id=feedback.pattern_id,
            feedback_type=feedback.feedback_type,
            file_path=feedback.file_path,
            line_number=feedback.line_number,
            code_snippet=feedback.code_snippet,
            developer_comment=feedback.developer_comment,
            suggested_fix=feedback.suggested_fix,
            timestamp=feedback.timestamp or datetime.now(),
            weight=FEEDBACK_WEIGHTS.get(feedback.feedback_type, 0.0),
        )

        # Update pattern stats
        await self._update_pattern_stats(record)

        # Store in Redis
        await self._store_feedback(record)

        # Check if we should trigger learning
        should_learn = await self._check_learning_trigger()

        return {
            "feedback_id": feedback_id,
            "pattern_id": feedback.pattern_id,
            "feedback_type": feedback.feedback_type.value,
            "processed": True,
            "new_confidence": self._get_pattern_confidence(feedback.pattern_id),
            "learning_triggered": should_learn,
        }

    # Feedback type to counter attribute mapping (Issue #315)
    _FEEDBACK_COUNTERS = {
        FeedbackType.CORRECT: "correct_count",
        FeedbackType.INCORRECT: "incorrect_count",
        FeedbackType.MISSED: "missed_count",
        FeedbackType.PARTIAL: "partial_count",
        FeedbackType.IRRELEVANT: "irrelevant_count",
    }

    async def _update_pattern_stats(self, record: FeedbackRecord):
        """Update pattern statistics with new feedback."""
        pattern_id = record.pattern_id

        if pattern_id not in self.pattern_stats:
            self.pattern_stats[pattern_id] = PatternStats(pattern_id=pattern_id)

        stats = self.pattern_stats[pattern_id]
        stats.feedback_history.append(record)

        # Update counts using dispatch table (Issue #315 - reduced depth)
        counter_attr = self._FEEDBACK_COUNTERS.get(record.feedback_type)
        if counter_attr:
            setattr(stats, counter_attr, getattr(stats, counter_attr) + 1)

        # Recalculate confidence
        stats.raw_score = self._calculate_raw_score(stats)
        stats.confidence_score = self._calculate_confidence_score(stats)
        stats.last_updated = datetime.now()
        stats.version += 1

        # Persist to Redis
        await self._persist_pattern_stats(stats)

    def _calculate_raw_score(self, stats: PatternStats) -> float:
        """Calculate raw accuracy score from feedback counts."""
        # Issue #372: Use stats property instead of accessing attributes directly
        if stats.total_feedback_count == 0:
            return 0.5  # Neutral

        # Weighted score calculation
        positive = stats.correct_count + (stats.partial_count * 0.5)
        negative = (
            stats.incorrect_count
            + (stats.missed_count * 0.5)
            + (stats.irrelevant_count * 0.3)
        )

        score = positive / (positive + negative) if (positive + negative) > 0 else 0.5
        return max(0.0, min(1.0, score))

    def _calculate_confidence_score(self, stats: PatternStats) -> float:
        """
        Calculate confidence score with time decay and feedback volume.

        Confidence is based on:
        1. Raw accuracy score
        2. Volume of feedback (more feedback = higher confidence in score)
        3. Time decay (older feedback matters less)
        4. Recency weighting (recent trends matter more)
        """
        if not stats.feedback_history:
            return 0.5

        # Issue #372: Use stats property instead of accessing len() directly
        # Volume factor: confidence in score increases with more feedback
        volume_factor = min(
            1.0, stats.feedback_count / 20
        )  # Max out at 20 feedback items

        # Time-weighted score
        now = datetime.now()
        weighted_sum = 0.0
        weight_sum = 0.0

        for record in stats.feedback_history:
            # Issue #372: Use FeedbackRecord methods to reduce feature envy
            age_weeks = record.get_age_weeks(now)
            time_weight = CONFIDENCE_DECAY_RATE**age_weeks
            normalized_weight = record.get_normalized_weight()

            weighted_sum += normalized_weight * time_weight
            weight_sum += time_weight

        time_weighted_score = weighted_sum / weight_sum if weight_sum > 0 else 0.5

        # Combine raw score with time-weighted score
        combined_score = (stats.raw_score * 0.4) + (time_weighted_score * 0.6)

        # Apply volume factor (low feedback = score closer to 0.5)
        confidence = 0.5 + (combined_score - 0.5) * volume_factor

        return max(0.0, min(1.0, confidence))

    def _get_pattern_confidence(self, pattern_id: str) -> float:
        """Get current confidence score for a pattern."""
        if pattern_id in self.pattern_stats:
            return self.pattern_stats[pattern_id].confidence_score
        return 0.5

    async def _store_feedback(self, record: FeedbackRecord):
        """Store feedback record in Redis."""
        if not self.redis_client:
            return

        try:
            key = f"pattern:feedback:{record.pattern_id}:{record.feedback_id}"
            data = {
                "feedback_id": record.feedback_id,
                "pattern_id": record.pattern_id,
                "feedback_type": record.feedback_type.value,
                "file_path": record.file_path,
                "line_number": record.line_number,
                "code_snippet": record.code_snippet,
                "developer_comment": record.developer_comment,
                "suggested_fix": record.suggested_fix,
                "timestamp": record.timestamp.isoformat(),
                "weight": record.weight,
            }
            await self.redis_client.set(
                key, json.dumps(data), ex=60 * 60 * 24 * 90
            )  # 90 day TTL
        except Exception as e:
            logger.warning("Failed to store feedback in Redis: %s", e)

    async def _persist_pattern_stats(self, stats: PatternStats):
        """Persist pattern stats to Redis."""
        if not self.redis_client:
            return

        try:
            key = f"pattern:stats:{stats.pattern_id}"
            data = {
                "pattern_id": stats.pattern_id,
                "correct_count": stats.correct_count,
                "incorrect_count": stats.incorrect_count,
                "missed_count": stats.missed_count,
                "partial_count": stats.partial_count,
                "irrelevant_count": stats.irrelevant_count,
                "raw_score": stats.raw_score,
                "confidence_score": stats.confidence_score,
                "last_updated": stats.last_updated.isoformat(),
                "version": stats.version,
            }
            await self.redis_client.set(key, json.dumps(data))
        except Exception as e:
            logger.warning("Failed to persist pattern stats: %s", e)

    async def _check_learning_trigger(self) -> bool:
        """Check if we should trigger active learning."""
        # Trigger learning if we have enough new feedback
        new_feedback_count = sum(
            1
            for stats in self.pattern_stats.values()
            if (datetime.now() - stats.last_updated).seconds < 3600
        )

        return new_feedback_count >= 10

    async def get_confidence_scores(
        self, pattern_ids: Optional[List[str]] = None
    ) -> List[ConfidenceScore]:
        """Get confidence scores for patterns."""
        await self.initialize()

        scores = []
        target_patterns = pattern_ids or list(self.pattern_stats.keys())

        for pattern_id in target_patterns:
            if pattern_id not in self.pattern_stats:
                continue

            stats = self.pattern_stats[pattern_id]
            score = stats.confidence_score

            # Determine confidence level
            level = ConfidenceLevel.VERY_LOW
            for lvl, threshold in sorted(
                CONFIDENCE_THRESHOLDS.items(), key=lambda x: x[1], reverse=True
            ):
                if score >= threshold:
                    level = lvl
                    break

            # Determine trend
            trend = self._calculate_trend(stats)

            scores.append(
                ConfidenceScore(
                    pattern_id=pattern_id,
                    score=round(score, 4),
                    level=level,
                    total_feedback=len(stats.feedback_history),
                    correct_count=stats.correct_count,
                    incorrect_count=stats.incorrect_count,
                    last_updated=stats.last_updated,
                    trend=trend,
                )
            )

        return sorted(scores, key=lambda x: x.score, reverse=True)

    def _calculate_trend(self, stats: PatternStats) -> str:
        """Calculate trend based on recent vs older feedback."""
        if len(stats.feedback_history) < 5:
            return "stable"

        now = datetime.now()
        recent_cutoff = now - timedelta(days=7)

        recent_scores = []
        older_scores = []

        for record in stats.feedback_history:
            weight = FEEDBACK_WEIGHTS.get(record.feedback_type, 0.0)
            if record.timestamp >= recent_cutoff:
                recent_scores.append(weight)
            else:
                older_scores.append(weight)

        if not recent_scores or not older_scores:
            return "stable"

        recent_avg = sum(recent_scores) / len(recent_scores)
        older_avg = sum(older_scores) / len(older_scores)

        diff = recent_avg - older_avg
        if diff > 0.2:
            return "improving"
        elif diff < -0.2:
            return "declining"
        return "stable"

    async def get_learning_metrics(self) -> LearningMetrics:
        """Get comprehensive learning metrics."""
        await self.initialize()

        total_patterns = len(self.pattern_stats)
        total_feedback = sum(
            len(s.feedback_history) for s in self.pattern_stats.values()
        )

        scores = [s.confidence_score for s in self.pattern_stats.values()]
        avg_confidence = sum(scores) / len(scores) if scores else 0.5

        high_conf = sum(1 for s in scores if s >= 0.7)
        low_conf = sum(1 for s in scores if s <= 0.3)

        # Count patterns with improving/degrading trends
        improving = 0
        degrading = 0
        for stats in self.pattern_stats.values():
            trend = self._calculate_trend(stats)
            if trend == "improving":
                improving += 1
            elif trend == "declining":
                degrading += 1

        # Feedback by type
        feedback_by_type: Dict[str, int] = defaultdict(int)
        feedback_by_category: Dict[str, int] = defaultdict(int)

        for stats in self.pattern_stats.values():
            for record in stats.feedback_history:
                feedback_by_type[record.feedback_type.value] += 1
                if stats.pattern_id in self.patterns:
                    cat = self.patterns[stats.pattern_id].category.value
                    feedback_by_category[cat] += 1

        return LearningMetrics(
            total_patterns=total_patterns,
            total_feedback=total_feedback,
            average_confidence=round(avg_confidence, 4),
            high_confidence_patterns=high_conf,
            low_confidence_patterns=low_conf,
            patterns_improved=improving,
            patterns_degraded=degrading,
            feedback_by_type=dict(feedback_by_type),
            feedback_by_category=dict(feedback_by_category),
            learning_rate=self._calculate_learning_rate(),
            last_training_run=None,  # Will be set when training runs
        )

    def _calculate_learning_rate(self) -> float:
        """Calculate the rate of learning improvement."""
        if not self.pattern_stats:
            return 0.0

        # Calculate average improvement over time
        improvements = []
        for stats in self.pattern_stats.values():
            if len(stats.feedback_history) >= 5:
                trend = self._calculate_trend(stats)
                if trend == "improving":
                    improvements.append(1.0)
                elif trend == "declining":
                    improvements.append(-1.0)
                else:
                    improvements.append(0.0)

        return sum(improvements) / len(improvements) if improvements else 0.0

    async def get_active_learning_queries(
        self, limit: int = 10
    ) -> List[ActiveLearningQuery]:
        """
        Generate active learning queries for patterns that need more feedback.

        Prioritizes:
        1. Low confidence patterns
        2. Patterns with conflicting feedback
        3. New patterns with little feedback
        """
        await self.initialize()

        queries = []
        candidates = []

        for pattern_id, stats in self.pattern_stats.items():
            # Issue #372: Use PatternStats method to reduce feature envy
            priority = stats.get_active_learning_priority()

            if priority > 0.2:
                candidates.append((pattern_id, stats, priority))

        # Sort by priority
        candidates.sort(key=lambda x: x[2], reverse=True)

        for pattern_id, stats, priority in candidates[:limit]:
            # Issue #372: Use PatternStats method to get snippet
            code_snippet = stats.get_most_recent_snippet()

            queries.append(
                ActiveLearningQuery(
                    pattern_id=pattern_id,
                    code_snippet=code_snippet,
                    predicted_match=True,
                    confidence=stats.confidence_score,
                    question=self._generate_learning_question(pattern_id, stats),
                )
            )

        return queries

    def _generate_learning_question(self, pattern_id: str, stats: PatternStats) -> str:
        """Generate a question for active learning."""
        if stats.confidence_score < 0.3:
            return (
                f"Pattern '{pattern_id}' has low confidence ({stats.confidence_score:.2%}). "
                f"Should this pattern be flagged? Please provide feedback."
            )

        # Issue #372: Use PatternStats property to reduce feature envy
        if stats.has_conflicting_feedback:
            ratio = stats.correct_count / (stats.correct_count + stats.incorrect_count)
            return (
                f"Pattern '{pattern_id}' has mixed feedback "
                f"({ratio:.1%} positive). Is this match accurate?"
            )

        # Issue #372: Use PatternStats properties
        if not stats.has_sufficient_feedback:
            return (
                f"Pattern '{pattern_id}' needs more feedback "
                f"({stats.feedback_count} samples). Is this detection correct?"
            )

        return f"Please validate pattern '{pattern_id}' match."

    async def register_pattern(self, pattern: PatternDefinition) -> Dict[str, Any]:
        """Register a new pattern for learning."""
        await self.initialize()

        self.patterns[pattern.pattern_id] = pattern

        # Initialize stats if not exists
        if pattern.pattern_id not in self.pattern_stats:
            self.pattern_stats[pattern.pattern_id] = PatternStats(
                pattern_id=pattern.pattern_id
            )

        # Persist to Redis
        if self.redis_client:
            try:
                key = f"pattern:definition:{pattern.pattern_id}"
                await self.redis_client.set(key, pattern.model_dump_json())
            except Exception as e:
                logger.warning("Failed to persist pattern definition: %s", e)

        return {
            "pattern_id": pattern.pattern_id,
            "registered": True,
            "initial_confidence": 0.5,
        }

    async def get_pattern_history(
        self, pattern_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get feedback history for a pattern."""
        await self.initialize()

        if pattern_id not in self.pattern_stats:
            return []

        stats = self.pattern_stats[pattern_id]
        history = sorted(
            stats.feedback_history, key=lambda x: x.timestamp, reverse=True
        )[:limit]

        # Issue #372: Use FeedbackRecord.to_dict() to reduce feature envy
        return [r.to_dict() for r in history]

    async def run_learning_cycle(self) -> Dict[str, Any]:
        """
        Run a complete learning cycle.

        This analyzes feedback, identifies pattern improvements,
        and updates pattern configurations.
        """
        await self.initialize()

        self.learning_phase = LearningPhase.ANALYZING
        start_time = time.time()

        updates: List[PatternUpdate] = []
        patterns_analyzed = 0
        patterns_updated = 0

        try:
            for pattern_id, stats in self.pattern_stats.items():
                patterns_analyzed += 1

                # Analyze feedback for this pattern
                analysis = self._analyze_pattern_feedback(pattern_id, stats)

                if analysis.get("needs_update"):
                    update = await self._apply_pattern_update(pattern_id, analysis)
                    if update:
                        updates.append(update)
                        patterns_updated += 1

            self.learning_phase = LearningPhase.DEPLOYED
            duration = time.time() - start_time

            return {
                "success": True,
                "patterns_analyzed": patterns_analyzed,
                "patterns_updated": patterns_updated,
                "updates": [
                    {
                        "pattern_id": u.pattern_id,
                        "update_type": u.update_type,
                        "reason": u.reason,
                    }
                    for u in updates
                ],
                "duration_seconds": round(duration, 2),
                "phase": self.learning_phase.value,
            }

        except Exception as e:
            logger.error("Learning cycle failed: %s", e)
            self.learning_phase = LearningPhase.COLLECTING
            return {
                "success": False,
                "error": str(e),
                "patterns_analyzed": patterns_analyzed,
            }

    def _analyze_pattern_feedback(
        self, pattern_id: str, stats: PatternStats
    ) -> Dict[str, Any]:
        """Analyze feedback to determine if pattern needs updates."""
        analysis = {
            "pattern_id": pattern_id,
            "needs_update": False,
            "update_type": None,
            "reason": None,
        }

        # Check for consistently poor performance
        if (
            stats.confidence_score < 0.3
            and len(stats.feedback_history) >= MIN_FEEDBACK_FOR_CONFIDENCE
        ):
            analysis["needs_update"] = True
            analysis["update_type"] = "disable_pattern"
            analysis["reason"] = "Consistently low confidence, pattern may be too broad"
            return analysis

        # Check for improving patterns that could be enhanced
        if stats.confidence_score > 0.8 and stats.correct_count >= 10:
            # Look for common characteristics in correct matches
            analysis["needs_update"] = False  # Could analyze for refinements
            analysis["reason"] = "High confidence pattern, no changes needed"
            return analysis

        # Check for patterns with many "missed" feedback
        if stats.missed_count > stats.correct_count and stats.missed_count >= 5:
            analysis["needs_update"] = True
            analysis["update_type"] = "expand_pattern"
            analysis["reason"] = "Many false negatives reported"
            return analysis

        return analysis

    async def _apply_pattern_update(
        self, pattern_id: str, analysis: Dict[str, Any]
    ) -> Optional[PatternUpdate]:
        """Apply an update to a pattern based on learning analysis."""
        if not analysis.get("needs_update"):
            return None

        update_type = analysis.get("update_type", "unknown")

        if pattern_id in self.patterns:
            pattern = self.patterns[pattern_id]

            if update_type == "disable_pattern":
                old_value = pattern.enabled
                pattern.enabled = False

                update = PatternUpdate(
                    pattern_id=pattern_id,
                    update_type=update_type,
                    old_value=old_value,
                    new_value=False,
                    reason=analysis.get("reason", "Learning-based update"),
                    applied_at=datetime.now(),
                )

                # Persist update
                if self.redis_client:
                    key = f"pattern:definition:{pattern_id}"
                    await self.redis_client.set(key, pattern.model_dump_json())

                return update

        return None


# =============================================================================
# Global Instance
# =============================================================================

_learning_engine: Optional[PatternLearningEngine] = None
_learning_engine_lock = asyncio.Lock()


async def get_learning_engine() -> PatternLearningEngine:
    """Get or create the global pattern learning engine."""
    global _learning_engine

    if _learning_engine is None:
        async with _learning_engine_lock:
            if _learning_engine is None:
                _learning_engine = PatternLearningEngine()
                await _learning_engine.initialize()

    return _learning_engine


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/feedback", summary="Submit pattern feedback")
async def submit_pattern_feedback(feedback: PatternFeedback) -> Dict[str, Any]:
    """
    Submit developer feedback for a pattern match.

    This feedback is used to improve pattern accuracy over time.
    """
    engine = await get_learning_engine()
    return await engine.submit_feedback(feedback)


@router.get("/confidence", summary="Get pattern confidence scores")
async def get_pattern_confidence(
    pattern_ids: Optional[str] = Query(None, description="Comma-separated pattern IDs"),
) -> Dict[str, Any]:
    """Get confidence scores for patterns."""
    engine = await get_learning_engine()

    ids = pattern_ids.split(",") if pattern_ids else None
    scores = await engine.get_confidence_scores(ids)

    return {
        "scores": [s.model_dump() for s in scores],
        "total": len(scores),
    }


@router.get("/metrics", summary="Get learning metrics")
async def get_learning_metrics() -> LearningMetrics:
    """Get comprehensive metrics about the learning system."""
    engine = await get_learning_engine()
    return await engine.get_learning_metrics()


@router.get("/active-learning", summary="Get active learning queries")
async def get_active_learning_queries(
    limit: int = Query(10, ge=1, le=50, description="Maximum queries to return"),
) -> Dict[str, Any]:
    """
    Get patterns that need more feedback for active learning.

    These are patterns where additional developer input would
    most improve the system's accuracy.
    """
    engine = await get_learning_engine()
    queries = await engine.get_active_learning_queries(limit)

    return {
        "queries": [q.model_dump() for q in queries],
        "total": len(queries),
    }


@router.post("/patterns", summary="Register a new pattern")
async def register_pattern(pattern: PatternDefinition) -> Dict[str, Any]:
    """Register a new pattern for learning."""
    engine = await get_learning_engine()
    return await engine.register_pattern(pattern)


@router.get("/patterns/{pattern_id}/history", summary="Get pattern feedback history")
async def get_pattern_history(
    pattern_id: str,
    limit: int = Query(50, ge=1, le=200, description="Maximum records to return"),
) -> Dict[str, Any]:
    """Get the feedback history for a specific pattern."""
    engine = await get_learning_engine()
    history = await engine.get_pattern_history(pattern_id, limit)

    if not history:
        raise HTTPException(status_code=404, detail="Pattern not found or no history")

    return {
        "pattern_id": pattern_id,
        "history": history,
        "total": len(history),
    }


@router.post("/learn", summary="Run learning cycle")
async def run_learning_cycle() -> Dict[str, Any]:
    """
    Trigger a learning cycle to analyze feedback and update patterns.

    This will:
    1. Analyze all pattern feedback
    2. Identify patterns needing updates
    3. Apply learned improvements
    """
    engine = await get_learning_engine()
    return await engine.run_learning_cycle()


@router.get("/health", summary="Health check")
async def health_check() -> Dict[str, Any]:
    """Check the health of the pattern learning system."""
    try:
        engine = await get_learning_engine()
        metrics = await engine.get_learning_metrics()

        return {
            "status": "healthy",
            "initialized": engine._initialized,
            "learning_phase": engine.learning_phase.value,
            "total_patterns": metrics.total_patterns,
            "total_feedback": metrics.total_feedback,
            "redis_connected": engine.redis_client is not None,
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
        }
