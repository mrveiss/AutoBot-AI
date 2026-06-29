# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pipeline execution strategy (GH #6830).

Moved from enhanced_orchestration.execution_strategies._pipeline to
orchestration.execution_strategies._pipeline (issue #10666 B3).
"""

import asyncio
from typing import Any, Callable, Dict

from autobot_shared.logging_manager import get_logger

from ..types import WorkflowPlan
from ._base import BaseExecutionStrategy

logger = get_logger(__name__)


class PipelineStrategy(BaseExecutionStrategy):
    """Execute tasks in pipeline mode where outputs feed into next inputs."""

    def __init__(
        self,
        execute_single_task: Callable,
        max_parallel_tasks: int,
        resource_semaphore: asyncio.Semaphore,
        group_pipeline_stages: Callable,
    ) -> None:
        super().__init__(execute_single_task, max_parallel_tasks, resource_semaphore)
        self._group_pipeline_stages = group_pipeline_stages

    async def execute(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute tasks in pipeline mode where outputs feed into next inputs"""
        results = {}

        # Group tasks into pipeline stages
        stages = self._group_pipeline_stages(plan.tasks, plan.dependencies_graph)

        pipeline_data = {}
        for stage_num, stage_tasks in enumerate(stages):
            logger.info("Executing pipeline stage %d/%d", stage_num + 1, len(stages))

            stage_results = await asyncio.gather(
                *[self._safe_execute(task, {**results, **pipeline_data}) for task in stage_tasks]
            )

            stage_failed = False
            for task, result in zip(stage_tasks, stage_results):
                results[task.task_id] = result
                if result.get("status") == "completed" and "output" in result:
                    pipeline_data.update(result["output"])
                if self._is_required_failure(task, result):
                    stage_failed = True

            if stage_failed:
                logger.error("Pipeline stage %d has required failures, stopping", stage_num + 1)
                break

        return results
