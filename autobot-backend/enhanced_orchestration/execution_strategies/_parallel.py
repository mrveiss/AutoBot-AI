# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Parallel execution strategy (GH #6830)."""

import asyncio
from typing import Any, Callable, Dict

from autobot_shared.logging_manager import get_logger

from ..types import WorkflowPlan
from ._base import BaseExecutionStrategy

logger = get_logger(__name__)


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
        """Execute independent tasks in parallel"""
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
            for task in ready_tasks:
                if len(running_tasks) < self.max_parallel_tasks:
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
