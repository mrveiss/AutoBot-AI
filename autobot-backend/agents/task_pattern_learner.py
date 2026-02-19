# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Pattern Learner (Issue #930)

Analyzes recent task outcomes to extract the best strategy for each task type.
Persists learned patterns to Redis for orchestrator routing decisions.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REDIS_PATTERNS_KEY = "task:patterns:{task_type}"
REDIS_PATTERNS_TTL = 60 * 60 * 24 * 7  # 7 days

# Minimum outcomes required before learning is triggered
MIN_OUTCOMES_TO_LEARN = 3
# Maximum outcomes considered per analysis window
ANALYSIS_WINDOW = 20


@dataclass
class LearnedStrategy:
    """Best strategy learned from analyzing task outcome history."""

    task_type: str
    best_approach: str
    best_prompt_template: str
    avg_score: float
    sample_size: int
    confidence: float
    failure_patterns: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class TaskPatternLearner:
    """Analyzes task outcome history to extract optimal strategies per task type."""

    def __init__(self, llm_interface=None):
        """Initialize with optional LLM interface."""
        self._llm = llm_interface
        self._redis = None

    async def _get_redis(self):
        """Lazily initialize Redis client."""
        if self._redis is None:
            from autobot_shared.redis_client import get_redis_client

            self._redis = await get_redis_client(async_client=True, database="main")
        return self._redis

    async def _get_llm(self):
        """Lazily initialize LLM interface."""
        if self._llm is None:
            from llm_interface import LLMInterface

            self._llm = LLMInterface()
        return self._llm

    async def learn_from_outcomes(
        self, task_type: str, outcomes: List[Dict]
    ) -> Optional[LearnedStrategy]:
        """Analyze recent outcomes and extract the best strategy.

        Args:
            task_type: Task category to analyze
            outcomes: List of outcome dicts with score, strategy_used, rationale

        Returns:
            LearnedStrategy if enough data, else None
        """
        if len(outcomes) < MIN_OUTCOMES_TO_LEARN:
            logger.debug("Not enough outcomes to learn from for %s", task_type)
            return None
        recent = outcomes[:ANALYSIS_WINDOW]
        best_outcome = max(recent, key=lambda o: o.get("score", 0.0))
        strategy = await self._synthesize_strategy(task_type, recent, best_outcome)
        if strategy:
            await self._persist_strategy(task_type, strategy)
        return strategy

    async def _synthesize_strategy(
        self,
        task_type: str,
        outcomes: List[Dict],
        best_outcome: Dict,
    ) -> Optional[LearnedStrategy]:
        """Use LLM to synthesize a strategy from outcome history."""
        try:
            llm = await self._get_llm()
            prompt = self._build_synthesis_prompt(task_type, outcomes, best_outcome)
            response = await llm.chat_completion_async(
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            return self._parse_strategy_response(response, task_type, outcomes)
        except Exception as exc:
            logger.warning("Error synthesizing strategy for %s: %s", task_type, exc)
            return self._fallback_strategy(task_type, outcomes, best_outcome)

    def _build_synthesis_prompt(
        self, task_type: str, outcomes: List[Dict], best_outcome: Dict
    ) -> str:
        """Build synthesis prompt from outcome data."""
        summary = json.dumps(
            [
                {
                    "score": o.get("score"),
                    "strategy": o.get("strategy_used"),
                    "rationale": o.get("rationale", "")[:100],
                }
                for o in outcomes
            ],
            indent=2,
        )
        return (
            f"Analyze these {len(outcomes)} task outcomes for task type '{task_type}'.\n\n"
            f"OUTCOMES:\n{summary}\n\n"
            f"BEST OUTCOME: strategy='{best_outcome.get('strategy_used')}', "
            f"score={best_outcome.get('score', 0):.2f}\n\n"
            f"Extract the best strategy. Return JSON with:\n"
            f"- best_approach: description of the optimal approach\n"
            f"- best_prompt_template: a reusable prompt template\n"
            f"- failure_patterns: list of patterns that lead to failure\n"
            f"- confidence: float 0.0-1.0\n"
        )

    def _system_prompt(self) -> str:
        """System prompt for strategy synthesis."""
        return (
            "You are a learning systems analyst. Examine task execution histories "
            "and identify the most effective patterns and strategies. "
            "Return structured JSON only."
        )

    def _parse_strategy_response(
        self, response: Any, task_type: str, outcomes: List[Dict]
    ) -> Optional[LearnedStrategy]:
        """Parse LLM response into a LearnedStrategy."""
        try:
            content = (
                response
                if isinstance(response, (str, dict))
                else response.get("content", "{}")
            )
            data = content if isinstance(content, dict) else json.loads(content)
            avg_score = sum(o.get("score", 0.0) for o in outcomes) / len(outcomes)
            return LearnedStrategy(
                task_type=task_type,
                best_approach=data.get("best_approach", ""),
                best_prompt_template=data.get("best_prompt_template", ""),
                avg_score=avg_score,
                sample_size=len(outcomes),
                confidence=float(data.get("confidence", 0.5)),
                failure_patterns=data.get("failure_patterns", []),
            )
        except Exception as exc:
            logger.warning("Failed to parse strategy response: %s", exc)
            return None

    def _fallback_strategy(
        self, task_type: str, outcomes: List[Dict], best_outcome: Dict
    ) -> LearnedStrategy:
        """Build a basic strategy when LLM synthesis is unavailable."""
        avg_score = sum(o.get("score", 0.0) for o in outcomes) / len(outcomes)
        return LearnedStrategy(
            task_type=task_type,
            best_approach=best_outcome.get("strategy_used", "default"),
            best_prompt_template=f"Complete this {task_type} task: {{goal}}",
            avg_score=avg_score,
            sample_size=len(outcomes),
            confidence=0.3,
        )

    async def _persist_strategy(
        self, task_type: str, strategy: LearnedStrategy
    ) -> None:
        """Persist learned strategy to Redis."""
        try:
            redis = await self._get_redis()
            key = REDIS_PATTERNS_KEY.format(task_type=task_type)
            await redis.set(key, json.dumps(strategy.__dict__), ex=REDIS_PATTERNS_TTL)
        except Exception as exc:
            logger.warning("Failed to persist learned strategy: %s", exc)

    async def get_learned_strategy(self, task_type: str) -> Optional[LearnedStrategy]:
        """Retrieve persisted learned strategy for a task type."""
        try:
            redis = await self._get_redis()
            key = REDIS_PATTERNS_KEY.format(task_type=task_type)
            raw = await redis.get(key)
            if raw:
                return LearnedStrategy(**json.loads(raw))
        except Exception as exc:
            logger.warning("Failed to retrieve learned strategy: %s", exc)
        return None

    async def clear_strategy(self, task_type: str) -> None:
        """Clear the learned strategy for a task type."""
        try:
            redis = await self._get_redis()
            key = REDIS_PATTERNS_KEY.format(task_type=task_type)
            await redis.delete(key)
        except Exception as exc:
            logger.warning("Failed to clear learned strategy: %s", exc)

    async def get_all_task_types(self) -> List[str]:
        """List all task types that have stored outcomes in Redis."""
        try:
            redis = await self._get_redis()
            pattern = "task:outcomes:*"
            cursor = 0
            types: List[str] = []
            while True:
                cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                for k in keys:
                    task_type = k.decode() if isinstance(k, bytes) else k
                    types.append(task_type.replace("task:outcomes:", ""))
                if cursor == 0:
                    break
            return types
        except Exception as exc:
            logger.warning("Failed to list task types: %s", exc)
            return []
