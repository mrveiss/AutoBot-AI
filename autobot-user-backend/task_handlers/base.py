# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base TaskHandler Abstract Class

Defines the interface that all task handlers must implement.

Issue #322: Updated to use TaskExecutionContext to eliminate data clump pattern.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from backend.models.task_context import TaskExecutionContext


class TaskHandler(ABC):
    """
    Abstract base class for task handlers.

    Each handler is responsible for executing a specific task type,
    including all validation, execution, and audit logging.

    Issue #322: Updated to use TaskExecutionContext instead of individual parameters.
    """

    @abstractmethod
    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """
        Execute a specific task type.

        Issue #322: Refactored to use TaskExecutionContext instead of 4 separate parameters.

        Args:
            ctx: TaskExecutionContext containing:
                - worker: The WorkerNode instance providing access to modules
                - task_payload: The task data including all parameters
                - user_role: The user role for audit logging
                - task_id: The unique task identifier

        Returns:
            Dict with status, message, and any result data
        """
        raise NotImplementedError
