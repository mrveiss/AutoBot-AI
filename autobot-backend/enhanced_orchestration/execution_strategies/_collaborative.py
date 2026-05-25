# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Collaborative execution strategy (GH #6830)."""

import asyncio
from typing import Any, Callable, Dict

from autobot_shared.logging_manager import get_logger

from ..types import WorkflowPlan
from ._base import BaseExecutionStrategy

logger = get_logger(__name__)


class CollaborativeStrategy(BaseExecutionStrategy):
    """Execute tasks collaboratively with inter-agent communication."""

    coordination_prefix = "autobot:orchestrator:coord:"

    def __init__(
        self,
        execute_single_task: Callable,
        max_parallel_tasks: int,
        resource_semaphore: asyncio.Semaphore,
        enhance_task_for_collaboration: Callable,
        coordinate_collaboration: Callable,
    ) -> None:
        super().__init__(execute_single_task, max_parallel_tasks, resource_semaphore)
        self._enhance_task_for_collaboration = enhance_task_for_collaboration
        self._coordinate_collaboration = coordinate_collaboration

    async def execute(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute tasks collaboratively with inter-agent communication"""
        results = {}

        # Create collaboration channels
        collab_channel = f"{self.coordination_prefix}collab:{plan.plan_id}"

        # Start collaboration coordinator
        coordinator_task = asyncio.create_task(self._coordinate_collaboration(collab_channel))

        # Execute tasks with collaboration
        task_futures = []
        for task in plan.tasks:
            enhanced_task = self._enhance_task_for_collaboration(task, collab_channel)
            future = asyncio.create_task(self._safe_execute(enhanced_task, results))
            task_futures.append((task, future))

        # Wait for all tasks
        for task, future in task_futures:
            result = await future
            results[task.task_id] = result

        # Stop coordinator and wait for its cleanup (finally/unsubscribe) to complete (#6431)
        coordinator_task.cancel()
        try:
            await coordinator_task
        except asyncio.CancelledError:
            pass

        return results
