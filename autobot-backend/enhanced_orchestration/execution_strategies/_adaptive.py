# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Adaptive execution strategy (GH #6830)."""

import asyncio
from typing import Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.workflow import ExecutionStrategy

from ..types import WorkflowPlan
from ._base import BaseExecutionStrategy

logger = get_logger(__name__)


class AdaptiveStrategy(BaseExecutionStrategy):
    """Execute with adaptive strategy switching mid-flight (Issue #315)."""

    def __init__(
        self,
        sequential_strategy: "SequentialStrategy",  # noqa: F821
        parallel_strategy: "ParallelStrategy",  # noqa: F821
    ) -> None:
        # Share the same dependencies as the delegated strategies
        super().__init__(
            sequential_strategy._execute_single_task,
            sequential_strategy.max_parallel_tasks,
            sequential_strategy.resource_semaphore,
        )
        self._sequential = sequential_strategy
        self._parallel = parallel_strategy

    async def execute(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute with adaptive strategy (Issue #315 - refactored)."""
        results = {}
        current_strategy = plan.strategy
        completed_tasks, failed_tasks = 0, 0
        pending_tasks = list(plan.tasks)

        while pending_tasks:
            progress_ratio = completed_tasks / len(plan.tasks)
            failure_ratio = failed_tasks / max(completed_tasks, 1)
            current_strategy = self._adapt_strategy(progress_ratio, failure_ratio, current_strategy)

            if current_strategy == ExecutionStrategy.PARALLEL:
                c, f = await self._execute_parallel_batch(pending_tasks, results)
            else:
                c, f = await self._execute_sequential_step(pending_tasks, results)

            if c == 0 and f == 0 and pending_tasks:
                # No progress made — dependency deadlock (#6429)
                logger.error(
                    "Dependency deadlock in adaptive: %d tasks unresolvable, failing them",
                    len(pending_tasks),
                )
                for task in pending_tasks:
                    results[task.task_id] = task.to_failed_result("Dependency deadlock")
                break

            completed_tasks += c
            failed_tasks += f

        return results

    def _adapt_strategy(
        self, progress_ratio: float, failure_ratio: float, current: ExecutionStrategy
    ) -> ExecutionStrategy:
        """Adapt execution strategy based on progress metrics."""
        if failure_ratio > 0.3:
            logger.info("Adapting to SEQUENTIAL due to high failure rate")
            return ExecutionStrategy.SEQUENTIAL

        if progress_ratio > 0.7 and failure_ratio < 0.1:
            logger.info("Adapting to PARALLEL due to good progress")
            return ExecutionStrategy.PARALLEL

        return current

    async def _execute_parallel_batch(self, pending_tasks: list, results: Dict[str, Any]) -> Tuple[int, int]:
        """Execute tasks in parallel batch."""
        batch_size = min(self.max_parallel_tasks, len(pending_tasks))
        batch_tasks = pending_tasks[:batch_size]
        ready_tasks = [t for t in batch_tasks if self._parallel._dependencies_met(t, results)]

        batch_results = await asyncio.gather(*[self._safe_execute(task, results) for task in ready_tasks])

        completed, failed = 0, 0
        for task, result in zip(ready_tasks, batch_results):
            results[task.task_id] = result
            pending_tasks.remove(task)
            if result.get("status") == "completed":
                completed += 1
            else:
                failed += 1

        return completed, failed

    async def _execute_sequential_step(self, pending_tasks: list, results: Dict[str, Any]) -> Tuple[int, int]:
        """Execute one sequential task step."""
        for task in pending_tasks[:]:
            if not self._sequential._dependencies_met(task, results):
                continue

            result = await self._safe_execute(task, results)
            results[task.task_id] = result
            pending_tasks.remove(task)

            if result.get("status") == "completed":
                return 1, 0
            return 0, 1

        return 0, 0
