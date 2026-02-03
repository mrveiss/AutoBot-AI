# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Parallel Tool Executor

Executes tool calls with automatic parallelization based on dependency analysis.
Implements Cursor's "DEFAULT TO PARALLEL" pattern for 3-5x faster execution.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from src.constants.status_enums import TaskStatus
from src.constants.threshold_constants import BatchConfig, RetryConfig
from src.events.types import create_action_event, create_observation_event
from src.tools.parallel.analyzer import DependencyAnalyzer
from src.tools.parallel.types import ExecutionMetrics, ToolCall

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class ParallelExecutorConfig:
    """Parallel executor configuration.

    Issue #670: Uses centralized constants from threshold_constants.py
    """

    max_parallel_calls: int = BatchConfig.DEFAULT_CONCURRENCY  # 10
    per_call_timeout_ms: int = 30000  # Tool-specific timeout, kept as-is
    group_timeout_ms: int = 60000  # Group-specific timeout, kept as-is
    retry_failed: bool = True
    max_retries: int = RetryConfig.MIN_RETRIES  # 2
    collect_metrics: bool = True


# =============================================================================
# Execution Graph
# =============================================================================


@dataclass
class ExecutionGraph:
    """Dependency graph for parallel execution"""

    calls: dict[str, ToolCall] = field(default_factory=dict)
    dependencies: dict[str, list[str]] = field(default_factory=dict)

    def add_call(self, call: ToolCall) -> None:
        """Add a tool call to the graph"""
        self.calls[call.call_id] = call
        self.dependencies[call.call_id] = call.depends_on.copy()

    def get_ready_calls(self) -> list[ToolCall]:
        """Get calls that are ready to execute (all dependencies satisfied).

        Issue #670: Uses TaskStatus enum for status comparisons.
        """
        completed = {
            call_id
            for call_id, call in self.calls.items()
            if call.status == TaskStatus.COMPLETED.value
        }

        ready = []
        for call_id, call in self.calls.items():
            if call.status != TaskStatus.PENDING.value:
                continue

            deps = self.dependencies.get(call_id, [])
            if all(dep_id in completed for dep_id in deps):
                ready.append(call)

        return ready

    def mark_completed(self, call_id: str, result: Any) -> None:
        """Mark a call as completed"""
        if call_id in self.calls:
            self.calls[call_id].status = TaskStatus.COMPLETED.value
            self.calls[call_id].result = result

    def mark_failed(self, call_id: str, error: str) -> None:
        """Mark a call as failed"""
        if call_id in self.calls:
            self.calls[call_id].status = TaskStatus.FAILED.value
            self.calls[call_id].error = error

    def get_failed_calls(self) -> list[ToolCall]:
        """Get all failed calls"""
        return [c for c in self.calls.values() if c.status == TaskStatus.FAILED.value]

    def get_completed_calls(self) -> list[ToolCall]:
        """Get all completed calls"""
        return [
            c for c in self.calls.values() if c.status == TaskStatus.COMPLETED.value
        ]


# =============================================================================
# Parallel Executor
# =============================================================================


class ParallelToolExecutor:
    """Executes tool calls with automatic parallelization"""

    def __init__(
        self,
        tool_dispatcher: Callable[[str, dict], Awaitable[Any]],
        event_stream: Optional[Any] = None,
        config: Optional[ParallelExecutorConfig] = None,
    ):
        """
        Initialize the parallel executor.

        Args:
            tool_dispatcher: Async function that executes a tool by name and args
            event_stream: Optional event stream for publishing events
            config: Executor configuration
        """
        self.dispatch = tool_dispatcher
        self.event_stream = event_stream
        self.config = config or ParallelExecutorConfig()
        self.analyzer = DependencyAnalyzer()

    async def _execute_group(
        self,
        group: list[ToolCall],
        group_idx: int,
        task_id: Optional[str],
        results: dict[str, Any],
        metrics: ExecutionMetrics,
    ) -> None:
        """Execute a single group of parallel tool calls."""
        group_id = f"group-{group_idx}"

        logger.debug(
            "Executing group %d with %d calls: %s",
            group_idx + 1,
            len(group),
            [c.tool_name for c in group],
        )

        for call in group:
            call.parallel_group_id = group_id

        if len(group) == 1:
            metrics.sequential_calls += 1

        semaphore = asyncio.Semaphore(self.config.max_parallel_calls)
        tasks = [
            self._execute_with_semaphore(call, task_id, semaphore) for call in group
        ]

        try:
            group_results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.config.group_timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            logger.error("Group %d timed out", group_idx)
            for call in group:
                if call.status == TaskStatus.RUNNING.value:
                    call.status = TaskStatus.FAILED.value
                    call.error = "Timeout"
                    results[call.call_id] = {"error": "Timeout"}
            return

        await self._process_group_results(group, group_results, task_id, results)

    async def _process_group_results(
        self,
        group: list[ToolCall],
        group_results: list[Any],
        task_id: Optional[str],
        results: dict[str, Any],
    ) -> None:
        """Process results from a group execution."""
        for call, result in zip(group, group_results):
            if isinstance(result, Exception):
                call.status = TaskStatus.FAILED.value
                call.error = str(result)
                results[call.call_id] = {"error": str(result)}

                if self.config.retry_failed:
                    retry_result = await self._retry_call(call, task_id)
                    if retry_result is not None:
                        results[call.call_id] = retry_result
            else:
                call.status = TaskStatus.COMPLETED.value
                call.result = result
                results[call.call_id] = result

    def _log_execution_metrics(
        self, metrics: ExecutionMetrics, tool_calls: list[ToolCall], start_time: float
    ) -> None:
        """Calculate and log execution metrics."""
        total_time = (time.monotonic() - start_time) * 1000
        metrics.parallel_time_ms = total_time
        metrics.sequential_time_ms = sum(c.execution_time_ms for c in tool_calls)
        metrics.total_time_ms = total_time
        metrics.calculate_speedup()

        if self.config.collect_metrics:
            logger.info(
                "Parallel execution complete: %.1fms (sequential would be %.1fms, "
                "speedup: %.2fx)",
                metrics.parallel_time_ms,
                metrics.sequential_time_ms,
                metrics.speedup_factor,
            )

    async def execute_batch(
        self,
        tool_calls: list[ToolCall],
        task_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute a batch of tool calls with automatic parallelization.

        Args:
            tool_calls: List of tool calls to execute
            task_id: Optional task ID for event tracking

        Returns:
            Dict mapping call_id to result
        """
        if not tool_calls:
            return {}

        start_time = time.monotonic()
        metrics = ExecutionMetrics(total_calls=len(tool_calls))

        self.analyzer.analyze_dependencies(tool_calls)
        groups = self.analyzer.get_parallel_groups(tool_calls)
        metrics.parallel_groups = len(groups)

        logger.info(
            "Executing %d tool calls in %d groups (max parallel: %d)",
            len(tool_calls),
            len(groups),
            self.config.max_parallel_calls,
        )

        results: dict[str, Any] = {}

        for group_idx, group in enumerate(groups):
            await self._execute_group(group, group_idx, task_id, results, metrics)

        self._log_execution_metrics(metrics, tool_calls, start_time)

        return results

    async def execute_single(
        self,
        call: ToolCall,
        task_id: Optional[str] = None,
    ) -> Any:
        """Execute a single tool call"""
        return await self._execute_single(call, task_id)

    async def _execute_with_semaphore(
        self,
        call: ToolCall,
        task_id: Optional[str],
        semaphore: asyncio.Semaphore,
    ) -> Any:
        """Execute a single tool call with semaphore limiting"""
        async with semaphore:
            return await self._execute_single(call, task_id)

    async def _execute_single(
        self,
        call: ToolCall,
        task_id: Optional[str],
    ) -> Any:
        """Execute a single tool call with event tracking"""
        call.status = TaskStatus.RUNNING.value

        # Publish ACTION event
        action_event = None
        if self.event_stream:
            action_event = create_action_event(
                tool_name=call.tool_name,
                arguments=call.arguments,
                task_id=task_id,
                is_parallel=call.parallel_group_id is not None,
                parallel_group_id=call.parallel_group_id,
                depends_on=call.depends_on,
            )
            # Override tool_id to match call_id
            action_event.content["tool_id"] = call.call_id
            await self.event_stream.publish(action_event)

        # Execute with timeout
        start_time = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.dispatch(call.tool_name, call.arguments),
                timeout=self.config.per_call_timeout_ms / 1000,
            )
            success = True
            error = None
        except asyncio.TimeoutError:
            result = None
            success = False
            error = f"Tool {call.tool_name} timed out after {self.config.per_call_timeout_ms}ms"
            logger.warning(error)
        except Exception as e:
            result = None
            success = False
            error = str(e)
            logger.error("Tool %s failed: %s", call.tool_name, e)

        execution_time = (time.monotonic() - start_time) * 1000
        call.execution_time_ms = execution_time

        # Publish OBSERVATION event
        if self.event_stream and action_event:
            observation_event = create_observation_event(
                action_id=action_event.event_id,
                tool_name=call.tool_name,
                success=success,
                result=result if success else None,
                error=error,
                execution_time_ms=execution_time,
                task_id=task_id,
            )
            await self.event_stream.publish(observation_event)

        if not success:
            raise RuntimeError(error)

        return result

    async def _retry_call(
        self,
        call: ToolCall,
        task_id: Optional[str],
        retry_count: int = 0,
    ) -> Optional[Any]:
        """Retry a failed call"""
        if retry_count >= self.config.max_retries:
            logger.warning(
                "Max retries (%d) reached for %s",
                self.config.max_retries,
                call.tool_name,
            )
            return None

        logger.info(
            "Retrying %s (attempt %d/%d)",
            call.tool_name,
            retry_count + 1,
            self.config.max_retries,
        )

        # Reset call status
        call.status = TaskStatus.PENDING.value
        call.error = None

        try:
            result = await self._execute_single(call, task_id)
            call.status = TaskStatus.COMPLETED.value
            call.result = result
            return result
        except Exception:
            return await self._retry_call(call, task_id, retry_count + 1)


# =============================================================================
# Utility Functions
# =============================================================================


def create_tool_calls(
    tool_specs: list[dict],
) -> list[ToolCall]:
    """
    Create ToolCall objects from simple specifications.

    Args:
        tool_specs: List of {"tool_name": str, "arguments": dict} dicts

    Returns:
        List of ToolCall objects
    """
    return [
        ToolCall(
            tool_name=spec["tool_name"],
            arguments=spec.get("arguments", {}),
        )
        for spec in tool_specs
    ]


async def execute_tools_parallel(
    tool_specs: list[dict],
    dispatcher: Callable[[str, dict], Awaitable[Any]],
    task_id: Optional[str] = None,
    event_stream: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Convenience function to execute tools in parallel.

    Args:
        tool_specs: List of {"tool_name": str, "arguments": dict} dicts
        dispatcher: Tool dispatch function
        task_id: Optional task ID
        event_stream: Optional event stream

    Returns:
        Dict mapping call IDs to results
    """
    calls = create_tool_calls(tool_specs)
    executor = ParallelToolExecutor(dispatcher, event_stream)
    return await executor.execute_batch(calls, task_id)
