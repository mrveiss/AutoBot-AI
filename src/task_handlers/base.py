# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base TaskHandler Abstract Class

Defines the interface that all task handlers must implement.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from src.worker_node import WorkerNode


class TaskHandler(ABC):
    """
    Abstract base class for task handlers.

    Each handler is responsible for executing a specific task type,
    including all validation, execution, and audit logging.
    """

    @abstractmethod
    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """
        Execute a specific task type.

        Args:
            worker: The WorkerNode instance providing access to modules
            task_payload: The task data including all parameters
            user_role: The user role for audit logging
            task_id: The unique task identifier

        Returns:
            Dict with status, message, and any result data
        """
        raise NotImplementedError
