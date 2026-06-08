# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Subagent Spawner (#4348)

Autonomous spawning and coordination of parallel subagents for independent tasks.

Core functionality:
- Spawn N subagents for independent tasks (max 5 per parent, max depth 2)
- Subagent receives goal, context, constraints, timeout
- Independent execution with isolated failure handling
- Results aggregation and conflict resolution
"""

import asyncio
from typing import Any, Coroutine, Dict, List

from autobot_shared.logging_manager import get_logger
from constants.ttl_constants import TTL_1_HOUR

from .subagent_task import (
    ConflictResolution,
    SubagentTask,
    TaskPriority,
    TaskResult,
    TaskStatus,
)

logger = get_logger(__name__)

# Constants
MAX_SUBAGENTS_PER_PARENT = 5
MAX_SUBAGENT_DEPTH = 2
DEFAULT_TIMEOUT_SECONDS = 300


class SubagentSpawner:
    """Spawns and coordinates parallel subagents for independent tasks."""

    def __init__(self, redis_client=None) -> None:
        """Initialize spawner with optional Redis client for state persistence."""
        self.redis = redis_client
        self.pending_tasks: Dict[str, List[SubagentTask]] = {}
        self.active_subagents: Dict[str, List[str]] = {}

    async def spawn_subagents(
        self,
        parent_task_id: str,
        tasks: List[Dict[str, Any]],
        parent_depth: int = 0,
        wait_for_all: bool = True,
        timeout_seconds: int | None = None,
    ) -> Dict[str, Any]:
        """
        Spawn subagents for independent tasks and optionally wait for completion.

        Args:
            parent_task_id: ID of the parent task
            tasks: List of task dicts with goal, context, constraints, timeout_seconds
            parent_depth: Current recursion depth
            wait_for_all: If True, wait for all subagents; if False, return immediately
            timeout_seconds: Overall timeout for all subagents (per-task timeout overrides)

        Returns:
            Dict with subagent_ids, results (if wait_for_all), status

        Raises:
            ValueError: If constraints violated (max subagents, max depth)
        """
        # Validate constraints
        if len(tasks) > MAX_SUBAGENTS_PER_PARENT:
            raise ValueError(f"Cannot spawn {len(tasks)} subagents: max {MAX_SUBAGENTS_PER_PARENT}")
        if parent_depth >= MAX_SUBAGENT_DEPTH:
            raise ValueError(f"Cannot spawn subagents at depth {parent_depth}: max {MAX_SUBAGENT_DEPTH}")

        logger.info(
            "Spawning %d subagents for parent task %s (depth %d)",
            len(tasks),
            parent_task_id,
            parent_depth,
        )

        # Create task objects
        subagent_tasks = []
        for task_dict in tasks:
            task = SubagentTask(
                goal=task_dict.get("goal", ""),
                context=task_dict.get("context", {}),
                constraints=task_dict.get("constraints", {}),
                timeout_seconds=task_dict.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
                priority=TaskPriority(task_dict.get("priority", TaskPriority.NORMAL.value)),
                parent_task_id=parent_task_id,
                depth=parent_depth + 1,
                metadata=task_dict.get("metadata", {}),
            )
            subagent_tasks.append(task)

        # Store pending tasks
        self.pending_tasks[parent_task_id] = subagent_tasks
        self.active_subagents[parent_task_id] = [t.task_id for t in subagent_tasks]

        # Persist to Redis if available
        if self.redis:
            await self._persist_tasks(parent_task_id, subagent_tasks)

        task_ids = [t.task_id for t in subagent_tasks]

        if not wait_for_all:
            # Return immediately with task IDs
            return {
                "parent_task_id": parent_task_id,
                "subagent_ids": task_ids,
                "status": "spawned",
                "count": len(task_ids),
            }

        # Wait for all subagents to complete
        overall_timeout = timeout_seconds or (max(t.timeout_seconds for t in subagent_tasks) + 30)
        try:
            results = await self._wait_for_completion(parent_task_id, subagent_tasks, overall_timeout)
            return {
                "parent_task_id": parent_task_id,
                "subagent_ids": task_ids,
                "status": "completed",
                "count": len(task_ids),
                "results": results,
            }
        except asyncio.TimeoutError:
            logger.error("Subagent spawning timed out for parent task %s", parent_task_id)
            return {
                "parent_task_id": parent_task_id,
                "subagent_ids": task_ids,
                "status": "timeout",
                "count": len(task_ids),
                "error": "Overall timeout exceeded",
            }

    async def get_subagent_status(self, task_id: str) -> Dict[str, Any]:
        """Get current status of a subagent task."""
        if self.redis:
            status_data = await self.redis.get(f"subagent:status:{task_id}")
            if status_data:
                return status_data

        return {"task_id": task_id, "status": "unknown"}

    async def cancel_subagent(self, task_id: str) -> bool:
        """Cancel a running subagent task."""
        logger.info("Cancelling subagent task %s", task_id)
        if self.redis:
            await self.redis.set(f"subagent:cancelled:{task_id}", "true", ex=TTL_1_HOUR)
        return True

    async def _wait_for_completion(
        self,
        parent_task_id: str,
        tasks: List[SubagentTask],
        timeout_seconds: int,
    ) -> List[TaskResult]:
        """Wait for all subagent tasks to complete with timeout."""
        task_coroutines: List[Coroutine] = []
        for task in tasks:
            coro = self._wait_for_task(task.task_id, task.timeout_seconds)
            task_coroutines.append(coro)

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*task_coroutines, return_exceptions=True),
                timeout=timeout_seconds,
            )
            return results
        except asyncio.TimeoutError:
            # Cancel pending tasks
            for task in tasks:
                await self.cancel_subagent(task.task_id)
            raise

    async def _wait_for_task(self, task_id: str, timeout_seconds: int) -> TaskResult:
        """Wait for a single task to complete."""
        start_time = asyncio.get_running_loop().time()
        poll_interval = 0.5  # Check every 500ms

        while True:
            elapsed = asyncio.get_running_loop().time() - start_time
            if elapsed > timeout_seconds:
                logger.warning("Task %s timed out after %.1f seconds", task_id, elapsed)
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.TIMEOUT,
                    error=f"Timeout after {timeout_seconds} seconds",
                    duration_seconds=elapsed,
                )

            # Check if task is cancelled
            if self.redis:
                cancelled = await self.redis.get(f"subagent:cancelled:{task_id}")
                if cancelled:
                    return TaskResult(
                        task_id=task_id,
                        status=TaskStatus.CANCELLED,
                        duration_seconds=elapsed,
                    )

                # Try to get result
                result_data = await self.redis.get(f"subagent:result:{task_id}")
                if result_data:
                    result = TaskResult.from_dict(result_data)
                    result.duration_seconds = elapsed
                    return result

            await asyncio.sleep(poll_interval)

    async def _persist_tasks(self, parent_task_id: str, tasks: List[SubagentTask]) -> None:
        """Persist tasks to Redis for durability."""
        if not self.redis:
            return

        for task in tasks:
            key = f"subagent:task:{task.task_id}"
            await self.redis.set(
                key,
                task.to_dict(),
                ex=TTL_1_HOUR,
            )
            # Track parent-child relationship
            await self.redis.lpush(f"subagent:children:{parent_task_id}", task.task_id)

    async def aggregate_results(
        self,
        results: List[TaskResult],
        strategy: str = "consensus",
    ) -> Dict[str, Any]:
        """
        Aggregate results from multiple subagents.

        Strategies:
        - consensus: All results must match
        - majority: Use result with most agreement
        - priority: Use highest priority result
        - all: Return all results
        """
        if not results:
            return {"status": "no_results", "results": []}

        successful_results = [r for r in results if r.status == TaskStatus.COMPLETED]
        failed_results = [r for r in results if r.status == TaskStatus.FAILED]

        aggregation = {
            "total_tasks": len(results),
            "successful": len(successful_results),
            "failed": len(failed_results),
            "strategy": strategy,
            "results": [r.to_dict() for r in results],
        }

        if strategy == "all":
            return aggregation

        if not successful_results:
            aggregation["status"] = "all_failed"
            return aggregation

        if strategy == "consensus":
            outputs = [r.output for r in successful_results]
            if len(set(str(o) for o in outputs)) == 1:
                aggregation["status"] = "consensus_reached"
                aggregation["consensus_output"] = outputs[0]
            else:
                aggregation["status"] = "no_consensus"
                aggregation["outputs"] = outputs

        elif strategy == "majority":
            outputs = [r.output for r in successful_results]
            output_counts = {}
            for o in outputs:
                key = str(o)
                output_counts[key] = output_counts.get(key, 0) + 1
            majority_output = max(output_counts.items(), key=lambda x: x[1])
            aggregation["status"] = "majority_selected"
            aggregation["majority_output"] = majority_output[0]
            aggregation["confidence"] = majority_output[1] / len(successful_results)

        elif strategy == "priority":
            # Sort by priority and return highest
            sorted_results = sorted(
                successful_results,
                key=lambda r: self._priority_value(r.metadata.get("priority", "normal")),
                reverse=True,
            )
            aggregation["status"] = "priority_selected"
            aggregation["priority_output"] = sorted_results[0].output

        return aggregation

    @staticmethod
    def _priority_value(priority: str) -> int:
        """Convert priority string to numeric value."""
        mapping = {"low": 1, "normal": 2, "high": 3, "urgent": 4}
        return mapping.get(priority, 2)

    async def resolve_conflicts(
        self,
        results: List[TaskResult],
        strategy: str = "consensus",
    ) -> ConflictResolution | None:
        """
        Detect and resolve conflicts between subagent outputs.

        Returns ConflictResolution if conflicts detected, None otherwise.
        """
        if len(results) < 2:
            return None

        successful_results = [r for r in results if r.status == TaskStatus.COMPLETED]
        if len(successful_results) < 2:
            return None

        # Check for output conflicts
        outputs = [r.output for r in successful_results]
        output_str_set = set(str(o) for o in outputs)

        if len(output_str_set) <= 1:
            # No conflict
            return None

        # Conflict detected
        logger.warning("Output conflict detected between %d subagents", len(results))
        conflict = ConflictResolution(
            task_ids=[r.task_id for r in successful_results],
            resolution_strategy=strategy,
            metadata={"outputs": outputs},
        )

        # Apply resolution strategy
        if strategy == "consensus":
            # Try to reach consensus
            majority_output = max(output_str_set, key=lambda o: sum(1 for x in outputs if str(x) == o))
            conflict.resolved_output = majority_output
            conflict.confidence = sum(1 for o in outputs if str(o) == majority_output) / len(outputs)

        return conflict
