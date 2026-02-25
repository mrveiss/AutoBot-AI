# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Execution Strategies Module

Issue #381: Extracted from enhanced_multi_agent_orchestrator.py god class refactoring.
Contains execution strategy implementations for workflow orchestration.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Tuple

from constants.threshold_constants import TimingConstants

from .types import AgentTask, ExecutionStrategy, WorkflowPlan

logger = logging.getLogger(__name__)


class ExecutionStrategyHandler:
    """Handles different execution strategies for workflow plans."""

    def __init__(
        self,
        max_parallel_tasks: int,
        resource_semaphore: asyncio.Semaphore,
        execute_single_task: Callable,
        topological_sort_tasks: Callable,
        dependencies_met: Callable,
        group_pipeline_stages: Callable,
        enhance_task_for_collaboration: Callable,
        coordinate_collaboration: Callable,
    ):
        """
        Initialize strategy handler with required dependencies.

        Args:
            max_parallel_tasks: Maximum concurrent tasks
            resource_semaphore: Semaphore for resource management
            execute_single_task: Function to execute a single task
            topological_sort_tasks: Function to sort tasks by dependencies
            dependencies_met: Function to check if dependencies are satisfied
            group_pipeline_stages: Function to group tasks into pipeline stages
            enhance_task_for_collaboration: Function to enhance tasks for collaboration
            coordinate_collaboration: Coroutine for coordination
        """
        self.max_parallel_tasks = max_parallel_tasks
        self.resource_semaphore = resource_semaphore
        self._execute_single_task = execute_single_task
        self._topological_sort_tasks = topological_sort_tasks
        self._dependencies_met = dependencies_met
        self._group_pipeline_stages = group_pipeline_stages
        self._enhance_task_for_collaboration = enhance_task_for_collaboration
        self._coordinate_collaboration = coordinate_collaboration
        self.coordination_prefix = "autobot:orchestrator:coord:"

    async def execute_by_strategy(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute workflow based on its strategy (Issue #315: extracted)."""
        strategy_handlers = {
            ExecutionStrategy.SEQUENTIAL: self.execute_sequential,
            ExecutionStrategy.PARALLEL: self.execute_parallel,
            ExecutionStrategy.PIPELINE: self.execute_pipeline,
            ExecutionStrategy.COLLABORATIVE: self.execute_collaborative,
        }
        handler = strategy_handlers.get(plan.strategy, self.execute_adaptive)
        return await handler(plan)

    async def execute_sequential(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute tasks sequentially"""
        results = {}

        # Sort tasks by dependencies and priority
        sorted_tasks = self._topological_sort_tasks(plan.tasks, plan.dependencies_graph)

        for task in sorted_tasks:
            logger.info("Executing task %s (%s)", task.task_id, task.agent_type)

            # Wait for dependencies
            await self._wait_for_dependencies(task, results)

            # Execute task
            result = await self._execute_single_task(task, results)
            results[task.task_id] = result

            # Check if we should continue
            if result.get("status") == "failed" and not task.metadata.get(
                "optional", False
            ):
                logger.error("Required task %s failed, stopping workflow", task.task_id)
                break

        return results

    async def execute_parallel(self, plan: WorkflowPlan) -> Dict[str, Any]:
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
                    task_future = asyncio.create_task(
                        self._execute_single_task(task, results)
                    )
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
            else:
                # No tasks running, wait a bit
                await asyncio.sleep(TimingConstants.MICRO_DELAY)

        return results

    async def execute_pipeline(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute tasks in pipeline mode where outputs feed into next inputs"""
        results = {}

        # Group tasks into pipeline stages
        stages = self._group_pipeline_stages(plan.tasks, plan.dependencies_graph)

        pipeline_data = {}
        for stage_num, stage_tasks in enumerate(stages):
            logger.info("Executing pipeline stage %d/%d", stage_num + 1, len(stages))

            # Execute stage tasks in parallel
            stage_results = await asyncio.gather(
                *[
                    self._execute_single_task(task, {**results, **pipeline_data})
                    for task in stage_tasks
                ]
            )

            # Collect results and prepare pipeline data for next stage
            for task, result in zip(stage_tasks, stage_results):
                results[task.task_id] = result

                # Extract outputs for pipeline
                if result.get("status") == "completed" and "output" in result:
                    pipeline_data.update(result["output"])

        return results

    async def execute_collaborative(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute tasks collaboratively with inter-agent communication"""
        results = {}

        # Create collaboration channels
        collab_channel = f"{self.coordination_prefix}collab:{plan.plan_id}"

        # Start collaboration coordinator
        coordinator_task = asyncio.create_task(
            self._coordinate_collaboration(plan, collab_channel)
        )

        # Execute tasks with collaboration
        task_futures = []
        for task in plan.tasks:
            enhanced_task = self._enhance_task_for_collaboration(task, collab_channel)
            future = asyncio.create_task(
                self._execute_single_task(enhanced_task, results)
            )
            task_futures.append((task, future))

        # Wait for all tasks
        for task, future in task_futures:
            result = await future
            results[task.task_id] = result

        # Stop coordinator
        coordinator_task.cancel()

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

    async def _execute_parallel_batch(
        self, pending_tasks: list, results: Dict[str, Any]
    ) -> Tuple[int, int]:
        """Execute tasks in parallel batch."""
        batch_size = min(self.max_parallel_tasks, len(pending_tasks))
        batch_tasks = pending_tasks[:batch_size]

        batch_results = await asyncio.gather(
            *[
                self._execute_single_task(task, results)
                for task in batch_tasks
                if self._dependencies_met(task, results)
            ]
        )

        completed, failed = 0, 0
        for task, result in zip(batch_tasks, batch_results):
            results[task.task_id] = result
            pending_tasks.remove(task)
            if result.get("status") == "completed":
                completed += 1
            else:
                failed += 1

        return completed, failed

    async def _execute_sequential_step(
        self, pending_tasks: list, results: Dict[str, Any]
    ) -> Tuple[int, int]:
        """Execute one sequential task step."""
        for task in pending_tasks[:]:
            if not self._dependencies_met(task, results):
                continue

            result = await self._execute_single_task(task, results)
            results[task.task_id] = result
            pending_tasks.remove(task)

            if result.get("status") == "completed":
                return 1, 0
            return 0, 1

        return 0, 0

    async def execute_adaptive(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute with adaptive strategy (Issue #315 - refactored)."""
        results = {}
        current_strategy = plan.strategy
        completed_tasks, failed_tasks = 0, 0
        pending_tasks = list(plan.tasks)

        while pending_tasks:
            progress_ratio = completed_tasks / len(plan.tasks)
            failure_ratio = failed_tasks / max(completed_tasks, 1)
            current_strategy = self._adapt_strategy(
                progress_ratio, failure_ratio, current_strategy
            )

            if current_strategy == ExecutionStrategy.PARALLEL:
                c, f = await self._execute_parallel_batch(pending_tasks, results)
            else:
                c, f = await self._execute_sequential_step(pending_tasks, results)

            completed_tasks += c
            failed_tasks += f

        return results

    async def _wait_for_dependencies(
        self, task: AgentTask, results: Dict[str, Any]
    ) -> None:
        """Wait for task dependencies to complete."""
        while not self._dependencies_met(task, results):
            await asyncio.sleep(TimingConstants.SHORT_DELAY)
