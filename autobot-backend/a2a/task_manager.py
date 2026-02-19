# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Task Manager

Issue #961: In-memory task lifecycle manager for A2A tasks.
Manages task state transitions per the A2A spec §4.2.

State machine:
  SUBMITTED → WORKING → COMPLETED
                      → FAILED
  SUBMITTED → CANCELLED
  WORKING   → INPUT_REQUIRED → WORKING
  WORKING   → CANCELLED
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .types import Task, TaskArtifact, TaskState, TaskStatus

logger = logging.getLogger(__name__)

# Terminal states — no further transitions allowed
_TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskManager:
    """Thread-safe (asyncio-safe) in-memory A2A task store."""

    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}

    def create_task(
        self,
        input_text: str,
        context: Optional[Dict] = None,
    ) -> Task:
        """Create and register a new task in SUBMITTED state."""
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            status=TaskStatus(state=TaskState.SUBMITTED),
            input=input_text,
            context=context,
        )
        self._tasks[task_id] = task
        logger.info("A2A task created: %s", task_id)
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve a task by ID, or None if not found."""
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[Task]:
        """Return all tasks."""
        return list(self._tasks.values())

    def update_state(
        self,
        task_id: str,
        state: TaskState,
        message: Optional[str] = None,
    ) -> Optional[Task]:
        """
        Transition a task to a new state.

        Returns the updated task, or None if task not found or already terminal.
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.warning("update_state: task %s not found", task_id)
            return None

        if task.status.state in _TERMINAL_STATES:
            logger.warning(
                "update_state: task %s already in terminal state %s",
                task_id,
                task.status.state.value,
            )
            return task

        task.status = TaskStatus(state=state, message=message)
        task.updated_at = _utcnow()
        logger.debug("A2A task %s → %s", task_id, state.value)
        return task

    def add_artifact(self, task_id: str, artifact: TaskArtifact) -> bool:
        """Append an artifact to a task. Returns False if task not found."""
        task = self._tasks.get(task_id)
        if not task:
            logger.warning("add_artifact: task %s not found", task_id)
            return False
        task.artifacts.append(artifact)
        task.updated_at = _utcnow()
        return True

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task if it is not already in a terminal state.

        Returns True on success, False if not found or already terminal.
        """
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status.state in _TERMINAL_STATES:
            return False
        task.status = TaskStatus(state=TaskState.CANCELLED)
        task.updated_at = _utcnow()
        logger.info("A2A task cancelled: %s", task_id)
        return True

    def stats(self) -> Dict[str, int]:
        """Return task counts per state."""
        counts: Dict[str, int] = {}
        for task in self._tasks.values():
            key = task.status.state.value
            counts[key] = counts.get(key, 0) + 1
        return counts


# Module-level singleton — one manager per backend process
_task_manager = TaskManager()


def get_task_manager() -> TaskManager:
    """Return the module-level TaskManager singleton."""
    return _task_manager
