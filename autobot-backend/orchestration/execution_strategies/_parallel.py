# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Parallel execution strategy (GH #6830).

Moved from enhanced_orchestration.execution_strategies._parallel to
orchestration.execution_strategies._parallel (issue #10666 B3).
"""

import asyncio
from typing import Any, Callable, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import SUBAGENT_REFLECTION_ENABLED

from ..types import WorkflowPlan
from ._base import BaseExecutionStrategy

logger = get_logger(__name__)


def _get_subagent_dispatcher(max_parallel: int):
    """Lazy import of SubagentDispatcher to avoid circular imports at module load.

    Exposed as a module-level function so tests can patch it.
    """
    from orchestration.subagent_dispatcher import SubagentTask, get_subagent_dispatcher  # noqa: PLC0415

    return SubagentTask, get_subagent_dispatcher(max_parallel=max_parallel)


class ParallelStrategy(BaseExecutionStrategy):
    """Execute independent tasks in parallel, respecting resource limits."""

    def __init__(
        self,
        execute_single_task: Callable,
        max_parallel_tasks: int,
        resource_semaphore: asyncio.Semaphore,
        dependencies_met: Callable,
    ) -> None:
        super().__init__(execute_single_task, max_parallel_tasks, resource_semaphore)
        self._dependencies_met = dependencies_met

    async def execute(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute independent tasks in parallel.

        When AUTOBOT_SUBAGENT_REFLECTION_ENABLED=true, routes the ready batch
        through SubagentDispatcher so each task gets a score-and-revise reflection
        pass after execution (#10602).  The existing asyncio.create_task path is
        used when the flag is off (default) — zero overhead.
        """
        results = {}
        pending_tasks = list(plan.tasks)
        running_tasks = []

        while pending_tasks or running_tasks:
            # Start tasks that have their dependencies met
            ready_tasks = []
            for task in pending_tasks[:]:
                if self._dependencies_met(task, results):
                    ready_tasks.append(task)
                    pending_tasks.remove(task)

            # Start ready tasks (respecting resource limits)
            startable = ready_tasks[: self.max_parallel_tasks - len(running_tasks)]
            if startable and SUBAGENT_REFLECTION_ENABLED:
                batch_results = await self._execute_batch_with_reflection(startable, results)
                results.update(batch_results)
            else:
                for task in startable:
                    logger.info("Starting parallel task %s", task.task_id)
                    task_future = asyncio.create_task(self._safe_execute(task, results))
                    running_tasks.append((task, task_future))

            # Wait for any task to complete
            if running_tasks:
                done, _ = await asyncio.wait(
                    [future for _, future in running_tasks],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Process completed tasks
                for task, future in running_tasks[:]:
                    if future in done:
                        result = await future
                        results[task.task_id] = result
                        running_tasks.remove((task, future))
                        logger.info("Completed parallel task %s", task.task_id)
            elif pending_tasks:
                # No running tasks but pending remain — dependency deadlock (#6420)
                logger.error(
                    "Dependency deadlock: %d tasks unresolvable, failing them",
                    len(pending_tasks),
                )
                for task in pending_tasks:
                    results[task.task_id] = task.to_failed_result("Dependency deadlock")
                break

        return results

    async def _execute_batch_with_reflection(self, tasks: list, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Run a batch of tasks through SubagentDispatcher with reflection (#10602).

        Wires get_subagent_dispatcher() into the parallel hot path so enable_reflection
        is actually set.  Falls back to direct _safe_execute on any dispatcher error.
        """
        try:
            SubagentTask, dispatcher = _get_subagent_dispatcher(self.max_parallel_tasks)
            subtasks = [
                SubagentTask(
                    task_id=t.task_id,
                    func=self._safe_execute,
                    args=(t, ctx),
                    timeout=getattr(t, "timeout", 300),
                    enable_reflection=True,
                    task_description=getattr(t, "description", t.task_id),
                )
                for t in tasks
            ]
            batch_results = await dispatcher.spawn_parallel_tasks(subtasks)
            logger.info("SubagentDispatcher(reflection=True) finished %d tasks", len(tasks))
            return {t.task_id: batch_results.get(t.task_id, {}) for t in tasks}
        except Exception as exc:
            logger.warning("SubagentDispatcher batch failed, falling back to direct execute: %s", exc)
            fallback: Dict[str, Any] = {}
            for t in tasks:
                fallback[t.task_id] = await self._safe_execute(t, ctx)
            return fallback
