# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skill Health Scheduler (Issue #4339)

Periodic job that computes skill health metrics and auto-disables
skills with unhealthy scores. Runs every 5 minutes.
"""

import asyncio
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import RedisDatabase, get_redis_client
from skills.registry import get_skill_registry

from .skill_metrics import SkillMetrics

logger = get_logger(__name__)

HEALTH_CHECK_INTERVAL = 5 * 60  # 5 minutes in seconds
HEALTH_THRESHOLD = 0.5  # Skills below this score are auto-disabled
STALE_THRESHOLD_DAYS = 30  # Skills unused for this many days are marked stale


class SkillHealthScheduler:
    """Periodic health check job for skills.

    Computes health scores and auto-disables unhealthy skills.
    """

    def __init__(self) -> None:
        self._metrics = SkillMetrics()
        self._running = False

    async def start(self) -> None:
        """Start the health check loop (5-minute intervals)."""
        if self._running:
            logger.warning("Health scheduler already running")
            return

        self._running = True
        logger.info("Starting skill health scheduler (interval: %ds)", HEALTH_CHECK_INTERVAL)

        while self._running:
            try:
                await self.check_all_skills()
            except Exception as e:
                logger.error("Health check failed: %s", e)

            # Sleep before next check
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def stop(self) -> None:
        """Stop the health check loop."""
        self._running = False
        logger.info("Stopping skill health scheduler")

    async def check_all_skills(self) -> Dict[str, Any]:
        """Check health of all registered skills.

        Returns:
            Dictionary with health check results
        """
        registry = get_skill_registry()
        skills = registry.list_skills()

        results = {
            "checked": 0,
            "healthy": 0,
            "unhealthy": 0,
            "disabled": 0,
            "stale": 0,
            "details": [],
        }

        for skill_info in skills:
            skill_id = skill_info.get("name")
            if not skill_id:
                continue

            try:
                health_score = await self._metrics.get_health_score(skill_id)
                metrics = await self._metrics.get_metrics(skill_id)

                result = {
                    "skill_id": skill_id,
                    "health_score": health_score,
                    "invocations": metrics["invocations"],
                    "success_rate": metrics["success_rate"],
                }

                results["checked"] += 1

                # Check if skill should be auto-disabled
                if health_score < HEALTH_THRESHOLD and metrics["invocations"] > 0:
                    await self._disable_skill(skill_id)
                    result["action"] = "disabled"
                    result["reason"] = f"health_score={health_score} < {HEALTH_THRESHOLD}"
                    results["disabled"] += 1
                    logger.warning(
                        "Auto-disabled skill %s (health=%.2f)",
                        skill_id,
                        health_score,
                    )
                elif health_score >= HEALTH_THRESHOLD:
                    result["action"] = "healthy"
                    results["healthy"] += 1
                else:
                    result["action"] = "untested"

                # Check for stale skills
                await self._metrics.mark_stale(skill_id)
                stale_list = await self._metrics.get_stale_skills()
                if skill_id in stale_list:
                    result["stale"] = True
                    results["stale"] += 1

                results["details"].append(result)

            except Exception as e:
                logger.error("Failed to check health for skill %s: %s", skill_id, e)

        if results["checked"] > 0:
            logger.info(
                "Health check complete: %d skills, %d healthy, %d disabled",
                results["checked"],
                results["healthy"],
                results["disabled"],
            )

        return results

    async def _disable_skill(self, skill_id: str) -> bool:
        """Disable a skill in the registry.

        Args:
            skill_id: Unique skill identifier

        Returns:
            True if disabled successfully
        """
        try:
            registry = get_skill_registry()
            result = registry.disable_skill(skill_id)
            if result.get("success"):
                # Persist to Redis
                redis = get_redis_client(RedisDatabase.MAIN)
                redis.set(f"skills:enabled:{skill_id}", "false", ex=90 * 86400)
                return True
            return False
        except Exception as e:
            logger.error("Failed to disable skill %s: %s", skill_id, e)
            return False

    async def get_health_status(self, skill_id: str) -> Dict[str, Any]:
        """Get current health status for a skill.

        Args:
            skill_id: Unique skill identifier

        Returns:
            Health status dictionary
        """
        try:
            health_score = await self._metrics.get_health_score(skill_id)
            metrics = await self._metrics.get_metrics(skill_id)
            stale_list = await self._metrics.get_stale_skills()

            return {
                "skill_id": skill_id,
                "health_score": health_score,
                "status": self._status_from_score(health_score),
                "invocations": metrics["invocations"],
                "successes": metrics.get("successes", 0),
                "failures": metrics.get("failures", 0),
                "success_rate": metrics["success_rate"],
                "error_patterns": metrics.get("error_patterns", {}),
                "avg_duration_ms": metrics["avg_duration_ms"],
                "stale": skill_id in stale_list,
                "threshold": HEALTH_THRESHOLD,
            }
        except Exception as e:
            logger.error("Failed to get health status for %s: %s", skill_id, e)
            return {
                "skill_id": skill_id,
                "error": str(e),
            }

    @staticmethod
    def _status_from_score(score: float) -> str:
        """Map health score to status label.

        Args:
            score: Health score (0.0 - 1.0)

        Returns:
            Status label
        """
        if score >= 0.8:
            return "excellent"
        elif score >= HEALTH_THRESHOLD:
            return "healthy"
        elif score > 0.2:
            return "degraded"
        else:
            return "critical"


# Singleton instance
_scheduler_instance: SkillHealthScheduler | None = None


def get_skill_health_scheduler() -> SkillHealthScheduler:
    """Get or create the skill health scheduler singleton."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SkillHealthScheduler()
    return _scheduler_instance
