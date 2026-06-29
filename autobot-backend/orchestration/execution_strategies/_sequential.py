# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sequential execution strategy (GH #6830).

Moved from enhanced_orchestration.execution_strategies._sequential to
orchestration.execution_strategies._sequential (issue #10666 B3).
"""

import asyncio
from typing import Any, Callable, Dict

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import TimingConstants

from ..types import AgentTask, WorkflowPlan
from ._base import BaseExecutionStrategy

logger = get_logger(__name__)


class SequentialStrategy(BaseExecutionStrategy):
    """Execute tasks sequentially, respecting dependencies."""

    def __init__(
        self,
        execute_single_task: Callable,
        max_parallel_tasks: int,
        resource_semaphore: asyncio.Semaphore,
        topological_sort_tasks: Callable,
        dependencies_met: Callable,
    ) -> None:
        super().__init__(execute_single_task, max_parallel_tasks, resource_semaphore)
        self._topological_sort_tasks = topological_sort_tasks
        self._dependencies_met = dependencies_met

    async def execute(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute tasks sequentially"""
        results = {}

        # Sort tasks by dependencies and priority
        sorted_tasks = self._topological_sort_tasks(plan.tasks, plan.dependencies_graph)

        for task in sorted_tasks:
            logger.info("Executing task %s (%s)", task.task_id, task.agent_type)

            try:
                await self._wait_for_dependencies(task, results)
            except RuntimeError as exc:
                result = task.to_failed_result(str(exc))
                results[task.task_id] = result
                if self._is_required_failure(task, result):
                    logger.error("Required task %s blocked by failed dep, stopping", task.task_id)
                    break
                continue

            result = await self._safe_execute(task, results)
            results[task.task_id] = result

            if self._is_required_failure(task, result):
                logger.error("Required task %s failed, stopping workflow", task.task_id)
                break

        return results

    async def _wait_for_dependencies(self, task: AgentTask, results: Dict[str, Any]) -> None:
        """Wait for task dependencies to complete, or raise if a dep is in any terminal non-completed state."""
        while not self._dependencies_met(task, results):
            terminal_deps = [
                dep for dep in task.dependencies if dep in results and results[dep].get("status") != "completed"
            ]
            if terminal_deps:
                status = results[terminal_deps[0]].get("status")
                raise RuntimeError(
                    f"Task {task.task_id} cannot run: dependency {terminal_deps[0]}" f" is terminal (status={status})"
                )
            await asyncio.sleep(TimingConstants.SHORT_DELAY)
