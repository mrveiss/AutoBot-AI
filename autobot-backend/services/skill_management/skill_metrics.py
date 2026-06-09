# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skill Metrics Tracking (Issue #4339)

Tracks skill performance metrics including invocation counts, success rates,
error patterns, and duration. Provides insights for skill refinement and
auto-deprecation of underperforming skills.
"""

import json
from datetime import timedelta
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.ssot_constants import TTL_90_DAYS
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

# Redis key prefixes
REDIS_SKILL_METRICS_PREFIX = "skill_metrics:"
REDIS_SKILL_INVOCATION_PREFIX = "skill_invocation:"
REDIS_SKILL_ERROR_PREFIX = "skill_error:"
REDIS_SKILL_HEALTH_PREFIX = "skill_health:"


class SkillMetrics(AsyncRedisClientMixin):
    """Tracks and stores skill invocation metrics in Redis."""

    _redis_database = "analytics"

    async def log_invocation(
        self,
        skill_id: str,
        action: str,
        success: bool,
        duration_ms: float,
        error_type: str | None = None,
        user_feedback: str | None = None,
    ) -> None:
        """Log a skill invocation with outcome.

        Args:
            skill_id: Unique skill identifier
            action: Action/tool name invoked
            success: Whether the invocation succeeded
            duration_ms: Execution duration in milliseconds
            error_type: Category of error (if any)
            user_feedback: User feedback on skill performance
        """
        redis = await self._get_redis()
        if not redis:
            logger.warning("Redis unavailable, skipping metrics logging")
            return

        now = now_utc()
        date_key = now.strftime("%Y-%m-%d")
        day_prefix = f"{REDIS_SKILL_METRICS_PREFIX}{skill_id}:{date_key}"

        try:
            # Increment invocation counter
            await redis.incr(f"{day_prefix}:total")

            if success:
                await redis.incr(f"{day_prefix}:success")
            else:
                await redis.incr(f"{day_prefix}:failures")

            # Track error type
            if error_type:
                await redis.incr(f"{day_prefix}:error:{error_type}")

            # Record duration (for percentile calculations)
            await redis.lpush(f"{day_prefix}:durations", str(duration_ms))

            # Store feedback if provided
            if user_feedback:
                feedback_entry = {
                    "timestamp": now.isoformat(),
                    "action": action,
                    "success": success,
                    "feedback": user_feedback,
                }
                await redis.lpush(
                    f"{day_prefix}:feedback",
                    json.dumps(feedback_entry, default=str),
                )

            # Trim old data (keep last 100 feedbacks per day)
            await redis.ltrim(f"{day_prefix}:feedback", 0, 99)
            await redis.ltrim(f"{day_prefix}:durations", 0, 999)

            # Set key expiry (keep 90 days of metrics)
            await redis.expire(f"{day_prefix}:total", TTL_90_DAYS)
            await redis.expire(f"{day_prefix}:success", TTL_90_DAYS)
            await redis.expire(f"{day_prefix}:failures", TTL_90_DAYS)
            await redis.expire(f"{day_prefix}:feedback", TTL_90_DAYS)
            await redis.expire(f"{day_prefix}:durations", TTL_90_DAYS)

        except Exception as e:
            logger.error("Failed to log skill metrics: %s", e)

    async def get_metrics(self, skill_id: str, days: int = 30) -> Dict[str, Any]:
        """Get aggregated metrics for a skill over past N days.

        Args:
            skill_id: Unique skill identifier
            days: Number of days to include (default 30)

        Returns:
            Dictionary with aggregated metrics
        """
        redis = await self._get_redis()
        if not redis:
            return {
                "skill_id": skill_id,
                "invocations": 0,
                "success_rate": 0.0,
                "error_patterns": {},
                "avg_duration_ms": 0.0,
            }

        total_invocations = 0
        total_successes = 0
        error_patterns: Dict[str, int] = {}
        all_durations: List[float] = []

        try:
            # Iterate over past N days
            now = now_utc()
            for i in range(days):
                date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
                day_prefix = f"{REDIS_SKILL_METRICS_PREFIX}{skill_id}:{date}"

                # Get counts for this day
                invocations = int(await redis.get(f"{day_prefix}:total") or 0)
                successes = int(await redis.get(f"{day_prefix}:success") or 0)
                total_invocations += invocations
                total_successes += successes

                # Aggregate error patterns
                error_keys = await redis.keys(f"{day_prefix}:error:*")
                for key in error_keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    error_type = key_str.split(":")[-1]
                    count = int(await redis.get(key) or 0)
                    error_patterns[error_type] = error_patterns.get(error_type, 0) + count

                # Collect durations
                durations_raw = await redis.lrange(f"{day_prefix}:durations", 0, -1)
                for d in durations_raw:
                    try:
                        duration_str = d.decode() if isinstance(d, bytes) else d
                        all_durations.append(float(duration_str))
                    except (ValueError, AttributeError):
                        continue

            # Calculate aggregated metrics
            success_rate = (total_successes / total_invocations * 100) if total_invocations > 0 else 0.0
            avg_duration = (sum(all_durations) / len(all_durations)) if all_durations else 0.0

            return {
                "skill_id": skill_id,
                "invocations": total_invocations,
                "successes": total_successes,
                "failures": total_invocations - total_successes,
                "success_rate": round(success_rate, 2),
                "error_patterns": error_patterns,
                "avg_duration_ms": round(avg_duration, 2),
                "period_days": days,
            }

        except Exception as e:
            logger.error("Failed to retrieve metrics for %s: %s", skill_id, e)
            return {
                "skill_id": skill_id,
                "invocations": 0,
                "success_rate": 0.0,
                "error_patterns": {},
                "avg_duration_ms": 0.0,
            }

    async def get_health_score(self, skill_id: str, days: int = 30) -> float:
        """Calculate health score for a skill (0.0 - 1.0).

        Health score = success_rate * performance_factor
        Performance factor penalizes slow skills or those with high error variety.

        Args:
            skill_id: Unique skill identifier
            days: Number of days to consider

        Returns:
            Health score between 0.0 and 1.0
        """
        metrics = await self.get_metrics(skill_id, days)

        if metrics["invocations"] == 0:
            return 0.5  # Default for untested skills

        # Base health on success rate
        success_rate = metrics["success_rate"] / 100.0

        # Penalize slow skills (>5s average)
        duration_factor = 1.0
        if metrics["avg_duration_ms"] > 5000:
            duration_factor = 0.8
        elif metrics["avg_duration_ms"] > 10000:
            duration_factor = 0.6

        # Penalize high error variety (>2 error types)
        error_variety = len(metrics["error_patterns"])
        error_factor = 1.0
        if error_variety > 2:
            error_factor = 0.8
        elif error_variety > 4:
            error_factor = 0.6

        # Calculate final health score
        health_score = success_rate * duration_factor * error_factor
        return round(max(0.0, min(1.0, health_score)), 2)

    async def mark_stale(self, skill_id: str) -> None:
        """Mark a skill as stale if unused for 30+ days.

        Args:
            skill_id: Unique skill identifier
        """
        redis = await self._get_redis()
        if not redis:
            return

        try:
            # Check if skill has any invocations in past 30 days
            now = now_utc()
            recent_invocations = 0

            for i in range(30):
                date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
                day_prefix = f"{REDIS_SKILL_METRICS_PREFIX}{skill_id}:{date}"
                count = int(await redis.get(f"{day_prefix}:total") or 0)
                recent_invocations += count

            if recent_invocations == 0:
                # Mark as stale
                await redis.set(
                    f"{REDIS_SKILL_HEALTH_PREFIX}{skill_id}:stale",
                    "true",
                    ex=TTL_90_DAYS,
                )
                logger.info(
                    "Marked skill %s as stale (no invocations in 30 days)",
                    skill_id,
                )

        except Exception as e:
            logger.error("Failed to mark skill as stale: %s", e)

    async def get_stale_skills(self) -> List[str]:
        """Get list of skills marked as stale.

        Returns:
            List of skill IDs marked as stale
        """
        redis = await self._get_redis()
        if not redis:
            return []

        try:
            stale_keys = await redis.keys(f"{REDIS_SKILL_HEALTH_PREFIX}*:stale")
            return [
                key.decode().replace(f"{REDIS_SKILL_HEALTH_PREFIX}", "").replace(":stale", "") for key in stale_keys
            ]
        except Exception as e:
            logger.error("Failed to retrieve stale skills: %s", e)
            return []
