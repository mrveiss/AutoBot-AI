# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Outcome Judge (Issue #930)

LLM-based evaluator that scores task outputs for correctness, completeness,
and efficiency. Stores outcomes in Redis for pattern learning.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from judges import BaseLLMJudge, JudgmentDimension, JudgmentResult

logger = logging.getLogger(__name__)

# Redis key pattern for task outcomes
REDIS_OUTCOMES_KEY = "task:outcomes:{task_type}"
REDIS_OUTCOMES_TTL = 60 * 60 * 24 * 30  # 30 days
MAX_OUTCOMES_PER_TYPE = 100


@dataclass
class TaskOutcomeRecord:
    """Record of a single task outcome evaluation."""

    task_type: str
    goal: str
    output_summary: str
    strategy_used: str
    score: float
    rationale: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class TaskOutcomeJudge(BaseLLMJudge):
    """
    Scores task outputs using LLM evaluation on accuracy, completeness,
    and efficiency. Persists results to Redis for pattern learning.
    """

    def __init__(self, llm_interface=None):
        """Initialize with task_outcome judge type."""
        super().__init__("task_outcome", llm_interface)
        self._redis_client = None

    async def _get_redis(self):
        """Lazily initialize Redis client."""
        if self._redis_client is None:
            from autobot_shared.redis_client import get_redis_client

            self._redis_client = await get_redis_client(
                async_client=True, database="main"
            )
        return self._redis_client

    async def evaluate_task_outcome(
        self,
        task_type: str,
        goal: str,
        output: str,
        strategy_used: str = "default",
    ) -> JudgmentResult:
        """Evaluate quality of a task output and persist to Redis.

        Args:
            task_type: Category/type of the task (e.g. "code_generation")
            goal: The original task goal/objective
            output: The task's actual output
            strategy_used: Description of the strategy/approach used

        Returns:
            JudgmentResult with quality assessment
        """
        criteria = [
            JudgmentDimension.ACCURACY,
            JudgmentDimension.COMPLETENESS,
            JudgmentDimension.EFFICIENCY,
        ]
        context = {
            "task_type": task_type,
            "goal": goal,
            "strategy_used": strategy_used,
        }
        result = await self.make_judgment(
            subject={"goal": goal, "output": output},
            criteria=criteria,
            context=context,
        )
        await self._persist_outcome(task_type, goal, output, strategy_used, result)
        return result

    async def _persist_outcome(
        self,
        task_type: str,
        goal: str,
        output: str,
        strategy_used: str,
        result: JudgmentResult,
    ) -> None:
        """Store outcome in Redis list, keeping only the last MAX_OUTCOMES_PER_TYPE."""
        try:
            redis = await self._get_redis()
            key = REDIS_OUTCOMES_KEY.format(task_type=task_type)
            record = TaskOutcomeRecord(
                task_type=task_type,
                goal=goal[:200],
                output_summary=output[:500],
                strategy_used=strategy_used,
                score=result.overall_score,
                rationale=result.reasoning[:300],
            )
            await redis.lpush(key, json.dumps(record.__dict__))
            await redis.ltrim(key, 0, MAX_OUTCOMES_PER_TYPE - 1)
            await redis.expire(key, REDIS_OUTCOMES_TTL)
        except Exception as exc:
            logger.warning("Failed to persist task outcome: %s", exc)

    async def get_outcomes(
        self, task_type: str, limit: int = 20
    ) -> List[TaskOutcomeRecord]:
        """Retrieve recent outcomes for a task type from Redis.

        Args:
            task_type: Task category to retrieve outcomes for
            limit: Maximum number of outcomes to return

        Returns:
            List of TaskOutcomeRecord sorted newest-first
        """
        try:
            redis = await self._get_redis()
            key = REDIS_OUTCOMES_KEY.format(task_type=task_type)
            raw = await redis.lrange(key, 0, limit - 1)
            return [TaskOutcomeRecord(**json.loads(r)) for r in raw]
        except Exception as exc:
            logger.warning("Failed to retrieve task outcomes: %s", exc)
            return []

    async def clear_outcomes(self, task_type: str) -> None:
        """Clear all stored outcomes for a task type."""
        try:
            redis = await self._get_redis()
            key = REDIS_OUTCOMES_KEY.format(task_type=task_type)
            await redis.delete(key)
        except Exception as exc:
            logger.warning("Failed to clear task outcomes: %s", exc)

    async def _prepare_judgment_prompt(
        self,
        subject: Any,
        criteria: List[JudgmentDimension],
        context: Dict[str, Any],
        alternatives=None,
        **kwargs,
    ) -> str:
        """Build evaluation prompt for task outcome assessment."""
        goal = context.get("goal", "")
        task_type = context.get("task_type", "unknown")
        strategy = context.get("strategy_used", "default")
        output = (
            subject.get("output", "") if isinstance(subject, dict) else str(subject)
        )
        return (
            f"Evaluate the quality of this task output.\n\n"
            f"TASK TYPE: {task_type}\n"
            f"GOAL: {goal}\n"
            f"STRATEGY USED: {strategy}\n\n"
            f"TASK OUTPUT:\n{output}\n\n"
            f"Evaluate on three dimensions (score 0.0-1.0 each):\n"
            f"1. ACCURACY: Did the output correctly address the goal?\n"
            f"2. COMPLETENESS: Was the output thorough and complete?\n"
            f"3. EFFICIENCY: Was the approach direct and not over-engineered?\n\n"
            f"Return JSON with: overall_score, recommendation "
            f"(APPROVE/REJECT/CONDITIONAL/REVISE), confidence, reasoning, "
            f"criterion_scores, improvement_suggestions."
        )

    def _get_system_prompt(self) -> str:
        """System prompt specialized for task outcome evaluation."""
        return (
            "You are an expert AI judge that evaluates task outputs for quality. "
            "Score each task on accuracy (did it meet the goal?), "
            "completeness (was it thorough?), and efficiency (lean and direct?). "
            "Be concise and objective. Return structured JSON with all required fields."
        )
