# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Autonomous subagent spawning for parallel workstreams."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from autobot_shared.logging_manager import get_logger
from orchestration.primitives import bounded_gather

logger = get_logger(__name__)


def _get_llm_service() -> Any:
    """Lazy import of get_llm_service to avoid circular imports at module load.

    Exposed as a module-level name so tests can patch it.
    """
    from services.llm_service import get_llm_service  # noqa: PLC0415

    return get_llm_service()


_REFLECTION_PROMPT = """\
You are a critical reviewer evaluating whether a subagent result fully addresses its original task.

Original task:
{task_description}

Result:
{result}

Respond with a JSON object and nothing else:
{{
  "score": <float 0.0-1.0>,
  "gaps": ["<gap 1>", "<gap 2>"]
}}

A score of 1.0 means the result completely addresses the task with no gaps.
"""

_REVISION_PROMPT = """\
You are a subagent completing a task that was partially addressed. Improve the result to fill all identified gaps.

Original task:
{task_description}

Previous result:
{result}

Gaps identified:
{gaps}

Provide an improved, complete result that addresses all gaps.
"""


@dataclass
class SubagentTask:
    """Definition of a task for subagent execution."""

    task_id: str
    func: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    timeout: int = 300
    enable_reflection: bool = False
    reflection_threshold: float = 0.7
    task_description: str = ""

    def __post_init__(self) -> None:
        if self.kwargs is None:
            self.kwargs = {}


class SubagentDispatcher:
    """Dispatches autonomous subagents for parallel workstreams."""

    def __init__(self, max_parallel: int = 10) -> None:
        self.max_parallel = max_parallel
        self.active_subagents: Dict[str, asyncio.Task] = {}

    async def spawn_parallel_tasks(self, tasks: List[SubagentTask]) -> Dict[str, Any]:
        """Spawn multiple subagents for parallel execution.

        Args:
            tasks: List of SubagentTask objects.

        Returns:
            Dictionary with results keyed by task_id.
        """
        results: Dict[str, Any] = {}
        pending: List[tuple[str, Any]] = []

        for task in tasks:
            try:
                coro = asyncio.wait_for(
                    self._execute_task(task),
                    timeout=task.timeout_seconds,
                )
                pending.append((task.task_id, coro))
            except Exception as exc:
                logger.error("Error creating task %s: %s", task.task_id, exc)
                results[task.task_id] = {"error": str(exc)}

        if pending:
            task_ids, coros = zip(*pending)
            task_results = await bounded_gather(list(coros), self.max_parallel)
            for task_id, result in zip(task_ids, task_results):
                results[task_id] = result

        return results

    async def _execute_task(self, task: SubagentTask) -> Any:
        """Execute a single subagent task, optionally with a reflection pass."""
        try:
            if asyncio.iscoroutinefunction(task.func):
                result = await task.func(*task.args, **task.kwargs)
            else:
                result = task.func(*task.args, **task.kwargs)
        except Exception as exc:
            logger.error("Task %s failed: %s", task.task_id, exc)
            raise

        if task.enable_reflection:
            result = await self._reflection_pass(task, result)

        return result

    async def _reflection_pass(self, task: SubagentTask, result: Any) -> Any:
        """Run an optional score-and-revise reflection pass.

        Scores the result against the task description. If the score is below
        ``task.reflection_threshold``, sends the result and gap list back for
        one revision pass and returns the revised result. Otherwise returns the
        original result unchanged.
        """
        try:
            llm = _get_llm_service()
        except Exception as exc:
            logger.warning(
                "Reflection skipped for task %s — LLM service unavailable: %s",
                task.task_id,
                exc,
            )
            return result

        task_description = task.task_description or str(task.task_id)
        result_text = result if isinstance(result, str) else json.dumps(result, default=str)

        score, gaps = await self._score_result(llm, task_description, result_text)
        logger.debug(
            "Reflection score for task %s: %.2f (threshold=%.2f, gaps=%s)",
            task.task_id,
            score,
            task.reflection_threshold,
            gaps,
        )

        if score >= task.reflection_threshold or not gaps:
            return result

        revised = await self._revise_result(llm, task_description, result_text, gaps)
        logger.info(
            "Task %s revised after reflection (score=%.2f < threshold=%.2f)",
            task.task_id,
            score,
            task.reflection_threshold,
        )
        return revised

    async def _score_result(
        self,
        llm: Any,
        task_description: str,
        result_text: str,
    ) -> tuple[float, List[str]]:
        """Ask the LLM to score the result and list gaps. Returns (score, gaps)."""
        prompt = _REFLECTION_PROMPT.format(
            task_description=task_description,
            result=result_text,
        )
        try:
            response = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                llm_type="analysis",
                temperature=0.1,
                max_tokens=256,
            )
            payload = json.loads(response.content.strip())
            score = float(payload.get("score", 0.0))
            gaps = [str(g) for g in payload.get("gaps", [])]
            return max(0.0, min(1.0, score)), gaps
        except Exception as exc:
            logger.warning("Reflection scoring failed: %s", exc)
            return 1.0, []  # assume good to avoid spurious revisions on LLM error

    async def _revise_result(
        self,
        llm: Any,
        task_description: str,
        result_text: str,
        gaps: List[str],
    ) -> Any:
        """Ask the LLM to produce a revised result that fills the listed gaps."""
        gaps_text = "\n".join(f"- {g}" for g in gaps)
        prompt = _REVISION_PROMPT.format(
            task_description=task_description,
            result=result_text,
            gaps=gaps_text,
        )
        try:
            response = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                llm_type="analysis",
                temperature=0.3,
                max_tokens=1024,
            )
            return response.content.strip()
        except Exception as exc:
            logger.warning("Revision LLM call failed: %s — returning original result", exc)
            return result_text


_orchestrator_instance: SubagentDispatcher | None = None


def get_subagent_dispatcher(max_parallel: int = 10) -> SubagentDispatcher:
    """Get or create global dispatcher instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = SubagentDispatcher(max_parallel=max_parallel)
    return _orchestrator_instance
