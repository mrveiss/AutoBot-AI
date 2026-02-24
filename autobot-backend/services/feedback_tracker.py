# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Feedback Tracker Service (Issue #905)

Tracks completion feedback and updates pattern statistics.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from models.code_pattern import CodePattern
from models.completion_feedback import CompletionFeedback
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)


class FeedbackTracker:
    """
    Tracks code completion feedback and updates pattern statistics.

    Implements learning loop by recording user acceptance/rejection
    and adjusting pattern frequencies accordingly.
    """

    def __init__(self):
        # Database setup
        DATABASE_URL = (
            f"postgresql://{config.database.user}:{config.database.password}"
            f"@{config.database.host}:{config.database.port}/"
            f"{config.database.name}"
        )
        engine = create_engine(DATABASE_URL)
        self.SessionLocal = sessionmaker(bind=engine)

        # Redis for time-series caching
        self.redis_client = get_redis_client(async_client=False, database="main")

        # Retraining thresholds
        self.retrain_threshold = 1000  # Retrain after N feedback events
        self.last_retrain_key = "completion:last_retrain"

    def record_feedback(
        self,
        context: str,
        suggestion: str,
        action: str,
        user_id: Optional[str] = None,
        language: Optional[str] = None,
        file_path: Optional[str] = None,
        pattern_id: Optional[int] = None,
        confidence_score: Optional[float] = None,
        completion_rank: Optional[int] = None,
    ) -> CompletionFeedback:
        """Record completion feedback event. Ref: #1088."""
        db = self.SessionLocal()
        try:
            # Create feedback record
            feedback = CompletionFeedback(
                timestamp=datetime.utcnow(),
                user_id=user_id,
                context=context,
                suggestion=suggestion,
                language=language,
                file_path=file_path,
                action=action,
                pattern_id=pattern_id,
                confidence_score=str(confidence_score) if confidence_score else None,
                completion_rank=completion_rank,
            )
            db.add(feedback)

            # Update pattern statistics if pattern_id provided
            if pattern_id:
                self._update_pattern_statistics(db, pattern_id, action)

            db.commit()

            # Cache in Redis for fast metrics
            self._cache_feedback_event(feedback)

            # Check if retraining threshold reached
            self._check_retrain_threshold()

            logger.info(
                f"Recorded {action} feedback for pattern_id={pattern_id}, "
                f"language={language}"
            )

            return feedback

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to record feedback: {e}", exc_info=True)
            raise
        finally:
            db.close()

    def _update_pattern_statistics(self, db, pattern_id: int, action: str):
        """Update pattern usage statistics."""
        pattern = db.query(CodePattern).filter(CodePattern.id == pattern_id).first()

        if not pattern:
            logger.warning(f"Pattern {pattern_id} not found for statistics update")
            return

        # Increment counters
        pattern.times_suggested += 1
        if action == "accepted":
            pattern.times_accepted += 1

        # Recalculate acceptance rate
        if pattern.times_suggested > 0:
            pattern.acceptance_rate = pattern.times_accepted / pattern.times_suggested

        # Update last_seen timestamp
        pattern.last_seen = datetime.utcnow()

        logger.debug(
            f"Updated pattern {pattern_id}: "
            f"{pattern.times_accepted}/{pattern.times_suggested} "
            f"= {pattern.acceptance_rate:.2%}"
        )

    def _cache_feedback_event(self, feedback: CompletionFeedback):
        """Cache feedback event in Redis for fast metrics."""
        # Store in time-series sorted set
        redis_key = f"feedback:events:{feedback.language or 'all'}"
        event_data = {
            "id": feedback.id,
            "action": feedback.action,
            "pattern_id": feedback.pattern_id,
            "timestamp": feedback.timestamp.isoformat(),
        }

        # Use timestamp as score for time-based queries
        score = feedback.timestamp.timestamp()
        self.redis_client.zadd(redis_key, {json.dumps(event_data): score})

        # Keep only last 30 days
        cutoff = (datetime.utcnow() - timedelta(days=30)).timestamp()
        self.redis_client.zremrangebyscore(redis_key, 0, cutoff)

    def _check_retrain_threshold(self):
        """Check if retraining threshold reached."""
        db = self.SessionLocal()
        try:
            # Get feedback count since last retrain
            last_retrain_str = self.redis_client.get(self.last_retrain_key)
            if last_retrain_str:
                last_retrain = datetime.fromisoformat(last_retrain_str.decode())
            else:
                last_retrain = datetime.utcnow() - timedelta(days=30)

            feedback_count = (
                db.query(func.count(CompletionFeedback.id))
                .filter(CompletionFeedback.timestamp > last_retrain)
                .scalar()
            )

            if feedback_count >= self.retrain_threshold:
                logger.info(
                    f"Retraining threshold reached: {feedback_count} "
                    f"feedback events since {last_retrain}"
                )
                # Note: Actual retraining triggered via API endpoint

        finally:
            db.close()

    def _get_language_breakdown(self, db, since: datetime) -> Dict:
        """
        Get per-language acceptance breakdown.

        Helper for get_acceptance_metrics (Issue #905).
        """
        language_breakdown = {}
        for lang, count in (
            db.query(CompletionFeedback.language, func.count(CompletionFeedback.id))
            .filter(CompletionFeedback.timestamp > since)
            .group_by(CompletionFeedback.language)
            .all()
        ):
            accepted = (
                db.query(func.count(CompletionFeedback.id))
                .filter(
                    CompletionFeedback.timestamp > since,
                    CompletionFeedback.language == lang,
                    CompletionFeedback.action == "accepted",
                )
                .scalar()
            )
            language_breakdown[lang or "unknown"] = {
                "total": count,
                "accepted": accepted,
                "acceptance_rate": accepted / count if count > 0 else 0.0,
            }
        return language_breakdown

    def _get_top_patterns(self, db) -> List[Dict]:
        """
        Get top performing patterns.

        Helper for get_acceptance_metrics (Issue #905).
        """
        top_patterns = (
            db.query(CodePattern)
            .filter(CodePattern.times_suggested > 10)
            .order_by(CodePattern.acceptance_rate.desc())
            .limit(10)
            .all()
        )
        return [
            {
                "id": p.id,
                "signature": p.signature[:50] + "...",
                "language": p.language,
                "acceptance_rate": p.acceptance_rate,
                "times_suggested": p.times_suggested,
            }
            for p in top_patterns
        ]

    def get_acceptance_metrics(
        self,
        language: Optional[str] = None,
        pattern_type: Optional[str] = None,
        time_window_days: int = 7,
    ) -> Dict:
        """
        Get acceptance rate metrics.

        Args:
            language: Filter by language
            pattern_type: Filter by pattern type
            time_window_days: Time window for metrics

        Returns:
            Dictionary with acceptance metrics
        """
        db = self.SessionLocal()
        try:
            # Time window
            since = datetime.utcnow() - timedelta(days=time_window_days)

            # Base query
            query = db.query(CompletionFeedback).filter(
                CompletionFeedback.timestamp > since
            )

            if language:
                query = query.filter(CompletionFeedback.language == language)

            # Total feedback
            total_feedback = query.count()
            accepted_feedback = query.filter(
                CompletionFeedback.action == "accepted"
            ).count()

            # Acceptance rate
            acceptance_rate = (
                accepted_feedback / total_feedback if total_feedback > 0 else 0.0
            )

            return {
                "time_window_days": time_window_days,
                "total_feedback": total_feedback,
                "accepted": accepted_feedback,
                "rejected": total_feedback - accepted_feedback,
                "acceptance_rate": acceptance_rate,
                "language_breakdown": self._get_language_breakdown(db, since),
                "top_patterns": self._get_top_patterns(db),
            }

        finally:
            db.close()

    def get_recent_feedback(
        self, limit: int = 50, action: Optional[str] = None
    ) -> List[Dict]:
        """
        Get recent feedback events.

        Args:
            limit: Maximum number of events to return
            action: Filter by action ('accepted' or 'rejected')

        Returns:
            List of recent feedback events
        """
        db = self.SessionLocal()
        try:
            query = db.query(CompletionFeedback).order_by(
                CompletionFeedback.timestamp.desc()
            )

            if action:
                query = query.filter(CompletionFeedback.action == action)

            feedback_events = query.limit(limit).all()

            return [fb.to_dict() for fb in feedback_events]

        finally:
            db.close()

    def mark_retrain_completed(self):
        """Mark that retraining has completed."""
        self.redis_client.set(
            self.last_retrain_key, datetime.utcnow().isoformat().encode()
        )
        logger.info("Marked retraining as completed")
