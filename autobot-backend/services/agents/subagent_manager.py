# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Subagent Manager (#4348)

Lifecycle management and coordination of spawned subagents.

Core functionality:
- Track spawned subagent lifecycles
- Distribute work to subagents
- Aggregate and monitor results
- Handle failures with isolation
"""

import asyncio
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from constants.ttl_constants import TTL_1_HOUR, TTL_30_DAYS

from .subagent_task import (
    SubagentTask,
    TaskResult,
    TaskStatus,
)

logger = get_logger(__name__)


class SubagentManager:
    """Manages lifecycle and coordination of spawned subagents."""

    def __init__(self, redis_client=None) -> None:
        """Initialize manager with optional Redis client."""
        self.redis = redis_client
        self.local_results: Dict[str, TaskResult] = {}

    async def register_subagent(self, task: SubagentTask) -> str:
        """Register a new subagent and return its ID."""
        logger.debug("Registering subagent task %s", task.task_id)

        # Store in Redis if available
        if self.redis:
            await self.redis.set(
                f"subagent:task:{task.task_id}",
                task.to_dict(),
                ex=TTL_1_HOUR,
            )

            # Update status to PENDING
            await self.set_task_status(task.task_id, TaskStatus.PENDING)

        return task.task_id

    async def set_task_status(self, task_id: str, status: TaskStatus, metadata: Dict[str, Any] | None = None) -> None:
        """Update task status."""
        if not self.redis:
            return

        status_data = {
            "task_id": task_id,
            "status": status.value,
            "updated_at": now_utc().isoformat(),
        }
        if metadata:
            status_data["metadata"] = metadata

        await self.redis.set(
            f"subagent:status:{task_id}",
            status_data,
            ex=TTL_1_HOUR,
        )

    async def record_task_result(self, result: TaskResult) -> None:
        """Record the result of a completed task."""
        logger.info("Recording result for task %s: %s", result.task_id, result.status.value)

        # Store result in Redis if available
        if self.redis:
            await self.redis.set(
                f"subagent:result:{result.task_id}",
                result.to_dict(),
                ex=TTL_30_DAYS,
            )

            # Update status
            await self.set_task_status(
                result.task_id,
                result.status,
                {"duration_seconds": result.duration_seconds, "error": result.error},
            )

        # Store in local cache
        self.local_results[result.task_id] = result

    async def get_task_result(self, task_id: str) -> TaskResult | None:
        """Get result of a completed task."""
        # Check local cache first
        if task_id in self.local_results:
            return self.local_results[task_id]

        # Try Redis if available
        if self.redis:
            result_data = await self.redis.get(f"subagent:result:{task_id}")
            if result_data:
                result = TaskResult.from_dict(result_data)
                self.local_results[task_id] = result
                return result

        return None

    async def get_batch_results(self, task_ids: List[str]) -> Dict[str, TaskResult | None]:
        """Get results for multiple tasks."""
        results = {}
        for task_id in task_ids:
            results[task_id] = await self.get_task_result(task_id)
        return results

    async def get_parent_task_status(self, parent_task_id: str) -> Dict[str, Any]:
        """Get overall status of a parent task and its subagents."""
        try:
            if not self.redis:
                return {"parent_task_id": parent_task_id, "status": "no_redis"}

            # Get all child task IDs
            child_ids = await self.redis.lrange(f"subagent:children:{parent_task_id}", 0, -1)

            if not child_ids:
                return {
                    "parent_task_id": parent_task_id,
                    "child_count": 0,
                    "status": "no_children",
                }

            # Get status of each child
            statuses = {
                TaskStatus.PENDING.value: 0,
                TaskStatus.RUNNING.value: 0,
                TaskStatus.COMPLETED.value: 0,
                TaskStatus.FAILED.value: 0,
                TaskStatus.CANCELLED.value: 0,
                TaskStatus.TIMEOUT.value: 0,
            }

            results = []
            for child_id in child_ids:
                result = await self.get_task_result(child_id)
                if result:
                    statuses[result.status.value] += 1
                    results.append(result.to_dict())
                else:
                    statuses[TaskStatus.PENDING.value] += 1

            # Determine overall status
            overall_status = "running"
            if statuses[TaskStatus.COMPLETED.value] == len(child_ids):
                overall_status = "completed"
            elif statuses[TaskStatus.FAILED.value] > 0:
                overall_status = "partially_failed"
            elif statuses[TaskStatus.TIMEOUT.value] > 0:
                overall_status = "partially_timeout"

            return {
                "parent_task_id": parent_task_id,
                "child_count": len(child_ids),
                "overall_status": overall_status,
                "status_breakdown": statuses,
                "results": results,
            }
        except Exception as e:
            logger.error("Failed to get parent task status: %s", str(e))
            return {"parent_task_id": parent_task_id, "error": str(e)}

    async def cleanup_parent_tasks(self, parent_task_id: str) -> bool:
        """Clean up Redis entries for a parent task."""
        try:
            if not self.redis:
                return False

            # Get child IDs before deleting
            child_ids = await self.redis.lrange(f"subagent:children:{parent_task_id}", 0, -1)

            # Delete each child's data
            for child_id in child_ids:
                await self.redis.delete(f"subagent:task:{child_id}")
                await self.redis.delete(f"subagent:status:{child_id}")
                await self.redis.delete(f"subagent:result:{child_id}")
                await self.redis.delete(f"subagent:cancelled:{child_id}")
                self.local_results.pop(child_id, None)

            # Delete parent's children list
            await self.redis.delete(f"subagent:children:{parent_task_id}")

            logger.info("Cleaned up subagent data for parent task %s", parent_task_id)
            return True
        except Exception as e:
            logger.error("Failed to cleanup parent task %s: %s", parent_task_id, e)
            return False

    async def distribute_work(
        self,
        task: SubagentTask,
        executor_func,
    ) -> TaskResult:
        """
        Distribute a task to an executor (agent) for processing.

        Args:
            task: The SubagentTask to execute
            executor_func: Async function(task) -> output that executes the task

        Returns:
            TaskResult with execution outcome
        """
        task_id = task.task_id
        logger.info("Distributing task %s to executor", task_id)
        start_time = asyncio.get_running_loop().time()

        try:
            # Update status to RUNNING
            await self.set_task_status(task_id, TaskStatus.RUNNING)

            # Execute task with timeout
            try:
                output = await asyncio.wait_for(
                    executor_func(task),
                    timeout=task.timeout_seconds,
                )
                duration = asyncio.get_running_loop().time() - start_time

                # Record success
                result = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    output=output,
                    duration_seconds=duration,
                )
                await self.record_task_result(result)
                return result

            except asyncio.TimeoutError:
                duration = asyncio.get_running_loop().time() - start_time
                logger.warning("Task %s timed out after %.1f seconds", task_id, duration)
                result = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.TIMEOUT,
                    error=f"Task timed out after {task.timeout_seconds} seconds",
                    duration_seconds=duration,
                )
                await self.record_task_result(result)
                return result

        except Exception as e:
            duration = asyncio.get_running_loop().time() - start_time
            logger.error("Task %s failed with error: %s", task_id, str(e))
            result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                duration_seconds=duration,
            )
            await self.record_task_result(result)
            return result

    async def wait_for_results(
        self,
        task_ids: List[str],
        timeout_seconds: int,
        check_interval: float = 0.5,
    ) -> Dict[str, TaskResult | None]:
        """
        Wait for results from multiple tasks.

        Returns dict mapping task_id to TaskResult or None if not completed.
        """
        start_time = asyncio.get_running_loop().time()

        while True:
            results = {}
            all_complete = True

            for task_id in task_ids:
                result = await self.get_task_result(task_id)
                results[task_id] = result
                if result is None or result.status == TaskStatus.RUNNING:
                    all_complete = False

            if all_complete:
                return results

            elapsed = asyncio.get_running_loop().time() - start_time
            if elapsed > timeout_seconds:
                logger.warning("Timed out waiting for results after %.1f seconds", elapsed)
                return results

            await asyncio.sleep(check_interval)
