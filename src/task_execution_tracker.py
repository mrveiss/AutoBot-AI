# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Execution History Tracker for AutoBot Phase 7
Integrates with orchestrator and agents to provide comprehensive execution tracking
"""

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from src.enhanced_memory_manager_async import (
    Priority,  # Import Priority for backward compatibility
)
from src.enhanced_memory_manager_async import (
    AsyncEnhancedMemoryManager,
    ExecutionRecord,
    TaskPriority,
    TaskStatus,
    get_async_enhanced_memory_manager,
)

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Task type classification for tracking purposes"""

    USER_REQUEST = "user_request"
    AGENT_TASK = "agent_task"
    SYSTEM_TASK = "system_task"
    BACKGROUND_TASK = "background_task"
    WORKFLOW_STEP = "workflow_step"


class TaskExecutionTracker:
    """
    Comprehensive task execution tracker that integrates with the enhanced memory manager
    to provide automatic task logging, performance monitoring, and execution analytics
    """

    def __init__(self, memory_manager: Optional[AsyncEnhancedMemoryManager] = None):
        """Initialize task tracker with memory manager and callback registry."""
        self.memory_manager = memory_manager or get_async_enhanced_memory_manager()
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.task_callbacks: Dict[str, List[Callable]] = {}

        logger.info("Task Execution Tracker initialized")

    def _create_and_start_task(
        self,
        task_name: str,
        description: str,
        priority: TaskPriority,
        agent_type: Optional[str],
        inputs: Optional[Dict[str, Any]],
        parent_task_id: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> str:
        """Create task record and mark as started.

        Args:
            task_name: Name of the task
            description: Task description
            priority: Task priority level
            agent_type: Type of agent executing task
            inputs: Task input parameters
            parent_task_id: Parent task ID if subtask
            metadata: Additional metadata

        Returns:
            Created task ID. Issue #620.
        """
        task_id = self.memory_manager.create_task_record(
            task_name=task_name,
            description=description,
            priority=priority,
            agent_type=agent_type,
            inputs=inputs,
            parent_task_id=parent_task_id,
            metadata=metadata,
        )
        self.memory_manager.start_task(task_id)
        return task_id

    def _register_active_task(
        self,
        task_id: str,
        task_name: str,
        agent_type: Optional[str],
        inputs: Optional[Dict[str, Any]],
    ) -> None:
        """Register task in active tasks tracking dictionary.

        Args:
            task_id: Task identifier
            task_name: Name of the task
            agent_type: Type of agent executing task
            inputs: Task input parameters. Issue #620.
        """
        self.active_tasks[task_id] = {
            "task_name": task_name,
            "agent_type": agent_type,
            "started_at": datetime.now(),
            "inputs": inputs,
        }

    async def _finalize_task(
        self, task_id: str, task_context: "TaskExecutionContext"
    ) -> None:
        """Complete task and execute callbacks.

        Args:
            task_id: Task identifier
            task_context: Execution context with outputs. Issue #620.
        """
        if task_id in self.active_tasks:
            self.memory_manager.complete_task(task_id, outputs=task_context.outputs)
        self.active_tasks.pop(task_id, None)
        await self._execute_task_callbacks(task_id, "completed")

    @asynccontextmanager
    async def track_task(
        self,
        task_name: str,
        description: str,
        agent_type: Optional[str] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        inputs: Optional[Dict[str, Any]] = None,
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Context manager for automatic task tracking with proper cleanup.

        Issue #620: Refactored to use extracted helpers for task creation,
        registration, and finalization.

        Usage:
            async with tracker.track_task("Agent Communication", "Chat with user") as task_id:
                result = await some_agent_operation()
                return result
        """
        # Create and start task (Issue #620: uses helper)
        task_id = self._create_and_start_task(
            task_name,
            description,
            priority,
            agent_type,
            inputs,
            parent_task_id,
            metadata,
        )
        self._register_active_task(task_id, task_name, agent_type, inputs)
        task_context = TaskExecutionContext(self, task_id)

        try:
            yield task_context
            # Complete task if still active (Issue #620: uses helper)
            await self._finalize_task(task_id, task_context)

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.memory_manager.fail_task(task_id, error_msg)
            logger.error("Task %s failed: %s", task_id, error_msg)
            self.active_tasks.pop(task_id, None)
            await self._execute_task_callbacks(task_id, "completed")
            raise

    def create_subtask(
        self,
        parent_task_id: str,
        task_name: str,
        description: str,
        agent_type: Optional[str] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        inputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a subtask linked to a parent task"""
        return self.memory_manager.create_task_record(
            task_name=task_name,
            description=description,
            priority=priority,
            agent_type=agent_type,
            inputs=inputs,
            parent_task_id=parent_task_id,
            metadata=metadata,
        )

    def add_task_callback(
        self, task_id: str, callback: Callable, event_type: str = "completed"
    ):
        """Add callback to be executed when task reaches specific state"""
        if task_id not in self.task_callbacks:
            self.task_callbacks[task_id] = []

        self.task_callbacks[task_id].append(
            {"callback": callback, "event_type": event_type}
        )

    async def _execute_task_callbacks(self, task_id: str, event_type: str):
        """Execute registered callbacks for task events"""
        if task_id not in self.task_callbacks:
            return

        callbacks = [
            cb for cb in self.task_callbacks[task_id] if cb["event_type"] == event_type
        ]

        # Issue #370: Execute callbacks in parallel instead of sequentially
        async def run_callback(callback_info):
            """Execute a single callback and handle errors."""
            try:
                callback = callback_info["callback"]
                if asyncio.iscoroutinefunction(callback):
                    await callback(task_id)
                else:
                    await asyncio.to_thread(callback, task_id)
            except Exception as e:
                logger.error("Task callback error for %s: %s", task_id, e)

        await asyncio.gather(
            *[run_callback(cb_info) for cb_info in callbacks],
            return_exceptions=True,
        )

        # Clean up callbacks after execution
        self.task_callbacks.pop(task_id, None)

    def get_active_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get currently active tasks"""
        return self.active_tasks.copy()

    def get_task_history(
        self,
        agent_type: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        days_back: int = 30,
    ) -> List[ExecutionRecord]:
        """Get task execution history"""
        return self.memory_manager.get_task_history(
            agent_type=agent_type, status=status, limit=limit, days_back=days_back
        )

    def get_performance_metrics(self, days_back: int = 30) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        stats = self.memory_manager.get_task_statistics(days_back)

        # Add active task information
        stats["active_tasks"] = {
            "count": len(self.active_tasks),
            "by_agent_type": self._group_active_tasks_by_agent(),
        }

        return stats

    def _group_active_tasks_by_agent(self) -> Dict[str, int]:
        """Group active tasks by agent type"""
        agent_counts = {}
        for task_info in self.active_tasks.values():
            agent_type = task_info.get("agent_type", "unknown")
            agent_counts[agent_type] = agent_counts.get(agent_type, 0) + 1
        return agent_counts

    def add_markdown_reference(
        self, task_id: str, markdown_file: str, ref_type: str = "documentation"
    ):
        """Add markdown reference to a task"""
        return self.memory_manager.add_markdown_reference(
            task_id, markdown_file, ref_type
        )

    def store_task_embedding(
        self,
        task_id: str,
        content: str,
        embedding_model: str,
        embedding_vector: List[float],
    ):
        """Store embedding for task-related content"""
        return self.memory_manager.store_embedding(
            content=content,
            content_type=f"task_{task_id}",
            embedding_model=embedding_model,
            embedding_vector=embedding_vector,
        )

    async def analyze_task_patterns(self, days_back: int = 30) -> Dict[str, Any]:
        """Analyze task execution patterns and provide insights"""
        history = self.get_task_history(days_back=days_back, limit=1000)

        if not history:
            return {"message": "No task history available for analysis"}

        # Issue #317: Single-pass aggregation using defaultdict (O(2n) → O(n))
        agent_stats = defaultdict(
            lambda: {"total": 0, "successful": 0, "durations": [], "retries": []}
        )

        for task in history:
            agent = task.agent_type or "unknown"
            stats = agent_stats[agent]

            stats["total"] += 1
            if task.status == TaskStatus.COMPLETED:
                stats["successful"] += 1

            if task.duration_seconds:
                stats["durations"].append(task.duration_seconds)

            if task.retry_count > 0:
                stats["retries"].append(task.retry_count)

        # Calculate insights directly from aggregated data
        insights = {
            "analysis_period_days": days_back,
            "total_tasks_analyzed": len(history),
            "agent_performance": {
                agent: {
                    "success_rate_percent": round(
                        (data["successful"] / data["total"]) * 100, 2
                    ),
                    "total_tasks": data["total"],
                    "avg_duration_seconds": (
                        round(sum(data["durations"]) / len(data["durations"]), 2)
                        if data["durations"]
                        else None
                    ),
                    "avg_retry_count": (
                        round(sum(data["retries"]) / len(data["retries"]), 2)
                        if data["retries"]
                        else 0
                    ),
                }
                for agent, data in agent_stats.items()
            },
        }

        return insights

    # ========================================================================
    # Backward Compatibility Methods for orchestrator.py
    # ========================================================================

    def start_task(
        self,
        task_id: str,
        task_type: TaskType,
        description: str,
        priority: Priority,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Start a task with the given parameters (backward compatibility wrapper).

        Note: This is a simplified interface for backward compatibility.
        For full functionality, use the async track_task() context manager.
        """
        # Create task record in memory manager
        actual_task_id = self.memory_manager.create_task_record(
            task_name=task_type.value,
            description=description,
            priority=(
                priority if isinstance(priority, TaskPriority) else TaskPriority.MEDIUM
            ),
            agent_type=None,
            inputs=context,
            metadata={"task_id": task_id, "task_type": task_type.value},
        )

        # Start the task
        self.memory_manager.start_task(actual_task_id)

        # Track the mapping from user task_id to actual task_id
        if not hasattr(self, "_task_id_mapping"):
            self._task_id_mapping = {}
        self._task_id_mapping[task_id] = actual_task_id

        logger.info(
            f"Started task: {task_id} (type: {task_type.value}, priority: {priority})"
        )

    def complete_task(self, task_id: str, result: Any):
        """
        Complete a task (backward compatibility wrapper).

        Note: This is a simplified interface for backward compatibility.
        For full functionality, use the async track_task() context manager.
        """
        # Get actual task ID from mapping
        if hasattr(self, "_task_id_mapping") and task_id in self._task_id_mapping:
            actual_task_id = self._task_id_mapping[task_id]

            # Complete the task
            outputs = {"result": result} if result else None
            self.memory_manager.complete_task(actual_task_id, outputs=outputs)

            # Clean up mapping
            del self._task_id_mapping[task_id]

            logger.info("Completed task: %s", task_id)
        else:
            logger.warning("Task %s not found in mapping for completion", task_id)

    def fail_task(self, task_id: str, error_message: str):
        """
        Mark a task as failed (backward compatibility wrapper).

        Note: This is a simplified interface for backward compatibility.
        For full functionality, use the async track_task() context manager.
        """
        # Get actual task ID from mapping
        if hasattr(self, "_task_id_mapping") and task_id in self._task_id_mapping:
            actual_task_id = self._task_id_mapping[task_id]

            # Fail the task
            self.memory_manager.fail_task(actual_task_id, error_message)

            # Clean up mapping
            del self._task_id_mapping[task_id]

            logger.error("Failed task: %s - %s", task_id, error_message)
        else:
            logger.warning("Task %s not found in mapping for failure", task_id)


class TaskExecutionContext:
    """Context object provided during task execution for additional operations"""

    def __init__(self, tracker: TaskExecutionTracker, task_id: str):
        """Initialize execution context with tracker reference and task ID."""
        self.tracker = tracker
        self.task_id = task_id
        self.outputs: Optional[Dict[str, Any]] = None
        self.metadata: Dict[str, Any] = {}

    def set_outputs(self, outputs: Dict[str, Any]):
        """Set task outputs that will be stored in memory"""
        self.outputs = outputs

    def add_metadata(self, key: str, value: Any):
        """Add metadata to the task execution"""
        self.metadata[key] = value

    def create_subtask(
        self,
        task_name: str,
        description: str,
        agent_type: Optional[str] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a subtask of the current task"""
        return self.tracker.create_subtask(
            parent_task_id=self.task_id,
            task_name=task_name,
            description=description,
            agent_type=agent_type,
            priority=priority,
            inputs=inputs,
            metadata=self.metadata.copy(),
        )

    def add_markdown_reference(
        self, markdown_file: str, ref_type: str = "documentation"
    ):
        """Add markdown file reference to current task"""
        return self.tracker.add_markdown_reference(
            self.task_id, markdown_file, ref_type
        )

    def store_embedding(
        self, content: str, embedding_model: str, embedding_vector: List[float]
    ):
        """Store embedding related to current task"""
        return self.tracker.store_task_embedding(
            self.task_id, content, embedding_model, embedding_vector
        )


# Global instance for easy access across the application
task_tracker = TaskExecutionTracker()
