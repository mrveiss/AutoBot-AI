# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Retry Strategy (Issue #930)

Given a failed or low-score task, generates an alternative approach
using LLM to adapt strategy on retry.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List

logger = logging.getLogger(__name__)

# Score threshold below which a task is considered low-quality
LOW_SCORE_THRESHOLD = 0.6


@dataclass
class RetryApproach:
    """Alternative approach for a failed/low-score task."""

    task_type: str
    goal: str
    original_strategy: str
    failure_reason: str
    suggested_prompt: str
    suggested_approach: str
    tool_sequence: List[str] = field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.5
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class TaskRetryStrategy:
    """Generates alternative strategies for failed or low-score tasks."""

    def __init__(self, llm_interface=None):
        """Initialize with optional LLM interface."""
        self._llm = llm_interface

    async def _get_llm(self):
        """Lazily initialize LLM interface."""
        if self._llm is None:
            from llm_interface import LLMInterface

            self._llm = LLMInterface()
        return self._llm

    async def generate_retry(
        self,
        task_type: str,
        goal: str,
        original_strategy: str,
        failure_reason: str,
        previous_score: float = 0.0,
    ) -> RetryApproach:
        """Generate an alternative retry approach for a failed/low-score task.

        Args:
            task_type: Category of the task
            goal: The original task goal
            original_strategy: Description of what was tried before
            failure_reason: Why the previous attempt failed or scored low
            previous_score: Quality score of previous attempt (0.0-1.0)

        Returns:
            RetryApproach with alternative strategy suggestions
        """
        try:
            llm = await self._get_llm()
            prompt = self._build_retry_prompt(
                task_type, goal, original_strategy, failure_reason, previous_score
            )
            response = await llm.chat_completion_async(
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            return self._parse_retry_response(
                response, task_type, goal, original_strategy, failure_reason
            )
        except Exception as exc:
            logger.warning("Error generating retry strategy: %s", exc)
            return self._fallback_retry(
                task_type, goal, original_strategy, failure_reason
            )

    def _build_retry_prompt(
        self,
        task_type: str,
        goal: str,
        original_strategy: str,
        failure_reason: str,
        previous_score: float,
    ) -> str:
        """Build the retry strategy generation prompt."""
        return (
            f"A task of type '{task_type}' failed or scored poorly "
            f"(score: {previous_score:.2f}).\n\n"
            f"GOAL: {goal}\n"
            f"ORIGINAL STRATEGY: {original_strategy}\n"
            f"FAILURE REASON: {failure_reason}\n\n"
            f"Suggest an alternative approach. Respond with JSON containing:\n"
            f"- suggested_prompt: improved prompt for the LLM\n"
            f"- suggested_approach: high-level description of alternative approach\n"
            f"- tool_sequence: list of tools to use in order\n"
            f"- rationale: why this approach is better\n"
            f"- confidence: float 0.0-1.0 confidence in this retry\n"
        )

    def _system_prompt(self) -> str:
        """System prompt for retry strategy generation."""
        return (
            "You are a task optimization expert. Given a failed task, "
            "analyze the failure and suggest a concrete alternative approach. "
            "Return structured JSON only."
        )

    def _parse_retry_response(
        self,
        response: Any,
        task_type: str,
        goal: str,
        original_strategy: str,
        failure_reason: str,
    ) -> RetryApproach:
        """Parse LLM response into a RetryApproach."""
        try:
            content = (
                response
                if isinstance(response, (str, dict))
                else response.get("content", "{}")
            )
            data = content if isinstance(content, dict) else json.loads(content)
            return RetryApproach(
                task_type=task_type,
                goal=goal,
                original_strategy=original_strategy,
                failure_reason=failure_reason,
                suggested_prompt=data.get("suggested_prompt", ""),
                suggested_approach=data.get("suggested_approach", ""),
                tool_sequence=data.get("tool_sequence", []),
                rationale=data.get("rationale", ""),
                confidence=float(data.get("confidence", 0.5)),
            )
        except Exception as exc:
            logger.warning("Failed to parse retry response: %s", exc)
            return self._fallback_retry(
                task_type, goal, original_strategy, failure_reason
            )

    def _fallback_retry(
        self,
        task_type: str,
        goal: str,
        original_strategy: str,
        failure_reason: str,
    ) -> RetryApproach:
        """Provide a basic fallback when LLM is unavailable."""
        return RetryApproach(
            task_type=task_type,
            goal=goal,
            original_strategy=original_strategy,
            failure_reason=failure_reason,
            suggested_prompt=(
                f"Retry: {goal}. Previous approach failed. Try a different angle."
            ),
            suggested_approach="Use a step-by-step decomposition approach",
            rationale="Fallback strategy due to LLM unavailability",
            confidence=0.3,
        )
