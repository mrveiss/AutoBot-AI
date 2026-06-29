# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Base execution strategy class and shared helpers (GH #6830).

Moved from enhanced_orchestration.execution_strategies._base to
orchestration.execution_strategies._base (issue #10666 B3).
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict

from autobot_shared.logging_manager import get_logger

from ..types import AgentTask, WorkflowPlan

logger = get_logger(__name__)


class BaseExecutionStrategy(ABC):
    """Abstract base for execution strategies (GH #6830 refactor).

    Each strategy implements the execute() method to handle a specific
    execution pattern (sequential, parallel, pipeline, collaborative, adaptive).
    Shared helpers (_safe_execute, _is_required_failure) are defined here.
    """

    def __init__(
        self,
        execute_single_task: Callable,
        max_parallel_tasks: int,
        resource_semaphore: asyncio.Semaphore,
    ) -> None:
        self._execute_single_task = execute_single_task
        self.max_parallel_tasks = max_parallel_tasks
        self.resource_semaphore = resource_semaphore

    @abstractmethod
    async def execute(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute workflow plan according to this strategy."""
        ...

    async def _safe_execute(self, task: AgentTask, ctx: Dict[str, Any]) -> dict:
        """Run _execute_single_task and convert any unhandled Exception to a failed result (#6459).

        CancelledError is re-raised so cooperative cancellation still works.
        """
        try:
            return await self._execute_single_task(task, ctx)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Task %s raised during execution", task.task_id)
            return task.to_failed_result(repr(exc))

    @staticmethod
    def _is_required_failure(task: AgentTask, result: dict) -> bool:
        """Check if task failure should stop the workflow."""
        return result.get("status") == "failed" and not task.metadata.get("optional", False)
