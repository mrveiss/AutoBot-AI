# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Execution strategies package (GH #6830 refactor).

Decomposed from single 317-LOC god class into per-strategy files:
- _base: BaseExecutionStrategy ABC + shared helpers
- _sequential: SequentialStrategy
- _parallel: ParallelStrategy
- _pipeline: PipelineStrategy
- _collaborative: CollaborativeStrategy
- _adaptive: AdaptiveStrategy

ExecutionStrategyHandler is the thin dispatcher that selects and instantiates
the appropriate strategy based on the workflow plan.
"""

import asyncio
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.workflow import ExecutionStrategy

from ..types import WorkflowDependencies, WorkflowPlan
from ._adaptive import AdaptiveStrategy
from ._collaborative import CollaborativeStrategy
from ._parallel import ParallelStrategy
from ._pipeline import PipelineStrategy
from ._sequential import SequentialStrategy

logger = get_logger(__name__)


class ExecutionStrategyHandler:
    """Thin dispatcher for execution strategies (GH #6830 refactor).

    Selects and instantiates the appropriate strategy based on the workflow
    plan's strategy field. All dependencies are injected at construction.
    """

    def __init__(
        self,
        max_parallel_tasks: int,
        resource_semaphore: asyncio.Semaphore,
        deps: WorkflowDependencies,
    ) -> None:
        """Initialize with shared deps; lazily construct strategy instances."""
        self.max_parallel_tasks = max_parallel_tasks
        self.resource_semaphore = resource_semaphore
        shared_args = (deps.execute_single_task, max_parallel_tasks, resource_semaphore)

        # Construct per-strategy instances with their specific dependencies
        seq = SequentialStrategy(*shared_args, deps.topological_sort_tasks, deps.dependencies_met)
        par = ParallelStrategy(*shared_args, deps.dependencies_met)
        pip = PipelineStrategy(*shared_args, deps.group_pipeline_stages)
        col = CollaborativeStrategy(*shared_args, deps.enhance_task_for_collaboration, deps.coordinate_collaboration)
        adp = AdaptiveStrategy(seq, par)

        self._strategies = {
            ExecutionStrategy.SEQUENTIAL: seq,
            ExecutionStrategy.PARALLEL: par,
            ExecutionStrategy.PIPELINE: pip,
            ExecutionStrategy.COLLABORATIVE: col,
            ExecutionStrategy.ADAPTIVE: adp,
        }

    async def execute_by_strategy(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute workflow based on its strategy (Issue #315: extracted)."""
        handler = self._strategies.get(plan.strategy, self._strategies[ExecutionStrategy.ADAPTIVE])
        return await handler.execute(plan)


__all__ = ["ExecutionStrategyHandler"]
