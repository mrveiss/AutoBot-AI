# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Feedback Analysis (Issue #4339)

Analyzes skill feedback to identify failure patterns and
provide refinement recommendations.
"""

import json
from collections import Counter
from datetime import timedelta
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.ssot_constants import TTL_90_DAYS
from autobot_shared.time_utils import now_utc

from .skill_metrics import SkillMetrics

logger = get_logger(__name__)


class SkillFeedbackAnalyzer(AsyncRedisClientMixin):
    """Analyzes skill feedback to identify patterns and recommend improvements."""

    _redis_database = "analytics"

    def __init__(self) -> None:
        self._metrics = SkillMetrics()

    async def log_user_feedback(
        self,
        skill_id: str,
        action: str,
        rating: int,
        feedback_text: str | None = None,
    ) -> None:
        """Log user feedback for a skill invocation.

        Args:
            skill_id: Unique skill identifier
            action: Action/tool that was invoked
            rating: User rating (1-5, where 5 is best)
            feedback_text: Optional free-text feedback
        """
        redis = await self._get_redis()
        if not redis:
            return

        try:
            now = now_utc()
            feedback_entry = {
                "timestamp": now.isoformat(),
                "skill_id": skill_id,
                "action": action,
                "rating": rating,
                "feedback": feedback_text or "",
            }

            key = f"skill_feedback:{skill_id}:{now.strftime('%Y-%m-%d')}"
            await redis.lpush(key, json.dumps(feedback_entry, default=str))
            await redis.expire(key, TTL_90_DAYS)  # Keep 90 days

            logger.debug("Logged feedback for %s: rating=%d", skill_id, rating)

        except Exception as e:
            logger.error("Failed to log user feedback: %s", e)

    async def get_feedback_summary(self, skill_id: str, days: int = 30) -> Dict[str, Any]:
        """Get summary of user feedback for a skill.

        Args:
            skill_id: Unique skill identifier
            days: Number of days to analyze

        Returns:
            Summary of feedback patterns
        """
        redis = await self._get_redis()
        if not redis:
            return {
                "skill_id": skill_id,
                "avg_rating": 0.0,
                "total_feedback": 0,
                "failure_patterns": [],
            }

        try:
            ratings = []
            failure_patterns: List[str] = []

            # Collect feedback from past N days
            now = now_utc()
            for i in range(days):
                date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
                key = f"skill_feedback:{skill_id}:{date}"
                feedback_entries = await redis.lrange(key, 0, -1)

                for entry_raw in feedback_entries:
                    try:
                        entry = json.loads(entry_raw.decode())
                        rating = entry.get("rating", 0)
                        feedback = entry.get("feedback", "")

                        ratings.append(rating)

                        # Track failure patterns (ratings 1-2)
                        if rating <= 2 and feedback:
                            failure_patterns.append(feedback)

                    except json.JSONDecodeError:
                        continue

            # Calculate statistics
            avg_rating = (sum(ratings) / len(ratings)) if ratings else 0.0

            # Find most common failure patterns
            pattern_counter = Counter(failure_patterns)
            top_patterns = [{"pattern": p, "count": c} for p, c in pattern_counter.most_common(5)]

            return {
                "skill_id": skill_id,
                "total_feedback": len(ratings),
                "avg_rating": round(avg_rating, 2),
                "rating_distribution": {
                    "5_star": ratings.count(5),
                    "4_star": ratings.count(4),
                    "3_star": ratings.count(3),
                    "2_star": ratings.count(2),
                    "1_star": ratings.count(1),
                },
                "failure_patterns": top_patterns,
                "period_days": days,
                "needs_refinement": len(top_patterns) >= 2 and len(ratings) > 5,
            }

        except Exception as e:
            logger.error("Failed to get feedback summary: %s", e)
            return {
                "skill_id": skill_id,
                "avg_rating": 0.0,
                "total_feedback": 0,
                "failure_patterns": [],
            }

    async def get_refinement_suggestions(self, skill_id: str) -> Dict[str, Any]:
        """Suggest improvements for a skill based on feedback patterns.

        Args:
            skill_id: Unique skill identifier

        Returns:
            Dictionary with refinement suggestions
        """
        try:
            metrics = await self._metrics.get_metrics(skill_id)
            feedback = await self.get_feedback_summary(skill_id)

            suggestions = []

            # Suggest refinement if >2 failure patterns
            if feedback.get("needs_refinement"):
                patterns = feedback.get("failure_patterns", [])
                pattern_text = ", ".join([p["pattern"] for p in patterns[:2]])
                suggestions.append(
                    {
                        "type": "refinement",
                        "priority": "high",
                        "message": f"Consider editing skill to address failure patterns: {pattern_text}",
                        "confidence": 0.9,
                    }
                )

            # Suggest performance optimization if avg duration > 5s
            if metrics["avg_duration_ms"] > 5000:
                suggestions.append(
                    {
                        "type": "performance",
                        "priority": "medium",
                        "message": f"Skill is slow (avg {metrics['avg_duration_ms']:.0f}ms). Consider optimization.",
                        "confidence": 0.8,
                    }
                )

            # Suggest deprecation if low usage
            if metrics["invocations"] < 5 and metrics["invocations"] > 0:
                suggestions.append(
                    {
                        "type": "deprecation",
                        "priority": "low",
                        "message": "Skill has low usage. Consider deprecation if not essential.",
                        "confidence": 0.6,
                    }
                )

            # Suggest error handling improvements if error variety high
            error_types = len(metrics.get("error_patterns", {}))
            if error_types > 4:
                suggestions.append(
                    {
                        "type": "error_handling",
                        "priority": "medium",
                        "message": f"Skill produces many error types ({error_types}). Improve error handling.",
                        "confidence": 0.75,
                    }
                )

            return {
                "skill_id": skill_id,
                "suggestions": suggestions,
                "total_suggestions": len(suggestions),
            }

        except Exception as e:
            logger.error("Failed to generate refinement suggestions: %s", e)
            return {
                "skill_id": skill_id,
                "suggestions": [],
                "error": str(e),
            }
