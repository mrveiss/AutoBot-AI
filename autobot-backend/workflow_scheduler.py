# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Scheduler and Queue Management

This module provides workflow scheduling capabilities, allowing workflows
to be scheduled for future execution, queued for orderly processing,
and managed with priority-based execution.
"""

from __future__ import annotations

import asyncio
import threading

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)
import heapq
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List
from uuid import uuid4

from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.time_utils import parse_utc_iso
from autobot_types import TaskComplexity
from constants.threshold_constants import RetryConfig, WorkflowConfig


class WorkflowPriority(Enum):
    """Workflow execution priority levels"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    CRITICAL = 5


from autobot_shared.status_enums import WorkflowStatus  # #6973 consolidation


@dataclass
class ScheduledWorkflow:
    """Represents a scheduled workflow"""

    id: str
    name: str
    template_id: str | None
    user_message: str
    scheduled_time: datetime
    priority: WorkflowPriority
    status: WorkflowStatus
    created_at: datetime
    complexity: TaskComplexity = TaskComplexity.SIMPLE
    user_id: str | None = None
    variables: Dict[str, Any] = None
    auto_approve: bool = False
    max_retries: int = RetryConfig.DEFAULT_RETRIES  # Issue #376
    retry_count: int = 0
    tags: List[str] = None
    dependencies: List[str] = None  # Other workflow IDs this depends on
    estimated_duration_minutes: int = WorkflowConfig.DEFAULT_ESTIMATED_DURATION_MIN
    timeout_minutes: int = WorkflowConfig.DEFAULT_TIMEOUT_MIN
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        """Initialize default values for optional fields."""
        if self.variables is None:
            self.variables = {}
        if self.tags is None:
            self.tags = []
        if self.dependencies is None:
            self.dependencies = []
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        # Convert datetime objects to ISO format
        data["scheduled_time"] = self.scheduled_time.isoformat()
        data["created_at"] = self.created_at.isoformat()
        data["priority"] = self.priority.value
        data["status"] = self.status.value
        return data

    # === Issue #372: Feature Envy Reduction Methods ===

    def to_summary_response(self) -> Dict[str, Any]:
        """Convert to summary dict for schedule response (Issue #372)."""
        return {
            "id": self.id,
            "name": self.name,
            "user_message": self.user_message,
            "scheduled_time": self.scheduled_time.isoformat(),
            "priority": self.priority.name,
            "status": self.status.name,
            "complexity": self.complexity.value,
            "template_id": self.template_id,
            "estimated_duration_minutes": self.estimated_duration_minutes,
        }

    def to_list_response(self) -> Dict[str, Any]:
        """Convert to list item dict for listing workflows (Issue #372)."""
        return {
            "id": self.id,
            "name": self.name,
            "user_message": self.user_message,
            "scheduled_time": self.scheduled_time.isoformat(),
            "priority": self.priority.name,
            "status": self.status.name,
            "complexity": self.complexity.value,
            "created_at": self.created_at.isoformat(),
            "template_id": self.template_id,
            "user_id": self.user_id,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }

    def to_detail_response(self) -> Dict[str, Any]:
        """Convert to detailed dict for single workflow response (Issue #372)."""
        return {
            "id": self.id,
            "name": self.name,
            "user_message": self.user_message,
            "scheduled_time": self.scheduled_time.isoformat(),
            "priority": self.priority.name,
            "status": self.status.name,
            "complexity": self.complexity.value,
            "created_at": self.created_at.isoformat(),
            "template_id": self.template_id,
            "variables": self.variables,
            "user_id": self.user_id,
            "auto_approve": self.auto_approve,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "timeout_minutes": self.timeout_minutes,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledWorkflow":
        """Create from dictionary"""
        # Convert datetime strings back to datetime objects
        data["scheduled_time"] = parse_utc_iso(data["scheduled_time"])
        data["created_at"] = parse_utc_iso(data["created_at"])
        data["priority"] = WorkflowPriority(data["priority"])
        data["status"] = WorkflowStatus(data["status"])
        return cls(**data)


@dataclass
class QueuedWorkflow:
    """Represents a workflow in the execution queue"""

    workflow: ScheduledWorkflow
    priority_score: float  # Combined priority + urgency score
    queued_at: datetime

    def __lt__(self, other):
        """Compare workflows by priority score for heap operations."""
        # For heapq - higher priority scores should be processed first
        return self.priority_score > other.priority_score


@dataclass
class WorkflowScheduleRequest:
    """
    Request parameters for scheduling a workflow.

    Issue #319: Reduces long parameter list in schedule_workflow().
    Groups all scheduling parameters into a single request object.
    """

    user_message: str
    scheduled_time: datetime | str
    priority: WorkflowPriority | str = WorkflowPriority.NORMAL
    complexity: TaskComplexity | str = TaskComplexity.SIMPLE
    template_id: str | None = None
    variables: Dict[str, Any] | None = None
    auto_approve: bool = False
    tags: List[str] | None = None
    dependencies: List[str] | None = None
    user_id: str | None = None
    estimated_duration_minutes: int = WorkflowConfig.DEFAULT_ESTIMATED_DURATION_MIN
    timeout_minutes: int = WorkflowConfig.DEFAULT_TIMEOUT_MIN
    max_retries: int = RetryConfig.DEFAULT_RETRIES


class WorkflowQueue:
    """Priority-based workflow execution queue"""

    def __init__(
        self,
        completed_workflows: Dict[str, "ScheduledWorkflow"] | None = None,
    ):
        """Initialize workflow queue with empty queues and default settings.

        Args:
            completed_workflows: Reference to the scheduler's completed_workflows dict.
                Passed by reference so the queue always sees the current state (#2180).
        """
        self._queue: List[QueuedWorkflow] = []
        self._running: Dict[str, ScheduledWorkflow] = {}
        self._max_concurrent = WorkflowConfig.DEFAULT_MAX_CONCURRENT  # Issue #376
        self._paused = False
        self._completed_workflows: Dict[str, ScheduledWorkflow] = (
            completed_workflows if completed_workflows is not None else {}
        )

    def add(self, workflow: ScheduledWorkflow) -> None:
        """Add workflow to queue with priority scoring"""
        priority_score = self._calculate_priority_score(workflow)
        queued_workflow = QueuedWorkflow(
            workflow=workflow, priority_score=priority_score, queued_at=datetime.now(tz=timezone.utc)
        )

        heapq.heappush(self._queue, queued_workflow)
        workflow.status = WorkflowStatus.QUEUED

    def get_next(self) -> ScheduledWorkflow | None:
        """Get the next workflow to execute"""
        if self._paused or len(self._running) >= self._max_concurrent:
            return None

        if not self._queue:
            return None

        queued_workflow = heapq.heappop(self._queue)
        workflow = queued_workflow.workflow

        # Check dependencies
        if not self._dependencies_satisfied(workflow):
            # Re-queue with lower priority if dependencies not met (Issue #376)
            workflow.status = WorkflowStatus.QUEUED
            queued_workflow.priority_score *= WorkflowConfig.DEPENDENCY_PENALTY
            heapq.heappush(self._queue, queued_workflow)
            return None

        workflow.status = WorkflowStatus.RUNNING
        self._running[workflow.id] = workflow

        return workflow

    def complete_workflow(self, workflow_id: str, status: WorkflowStatus) -> None:
        """Mark workflow as completed"""
        if workflow_id in self._running:
            workflow = self._running.pop(workflow_id)
            workflow.status = status

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a queued or running workflow"""
        # Check running workflows
        if workflow_id in self._running:
            workflow = self._running.pop(workflow_id)
            workflow.status = WorkflowStatus.CANCELLED
            return True

        # Check queued workflows
        for i, queued_workflow in enumerate(self._queue):
            if queued_workflow.workflow.id == workflow_id:
                queued_workflow.workflow.status = WorkflowStatus.CANCELLED
                del self._queue[i]
                heapq.heapify(self._queue)
                return True

        return False

    def pause_queue(self) -> None:
        """Pause workflow processing"""
        self._paused = True

    def resume_queue(self) -> None:
        """Resume workflow processing"""
        self._paused = False

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        return {
            "queued_workflows": len(self._queue),
            "running_workflows": len(self._running),
            "max_concurrent": self._max_concurrent,
            "paused": self._paused,
            "next_priority": self._queue[0].priority_score if self._queue else None,
        }

    def list_queued(self) -> List[ScheduledWorkflow]:
        """List all queued workflows"""
        return [qw.workflow for qw in sorted(self._queue, key=lambda x: x.priority_score, reverse=True)]

    def list_running(self) -> List[ScheduledWorkflow]:
        """List all running workflows"""
        return list(self._running.values())

    def _calculate_priority_score(self, workflow: ScheduledWorkflow) -> float:
        """Calculate priority score for workflow (Issue #376 - use named constants)"""
        base_score = workflow.priority.value * WorkflowConfig.PRIORITY_BASE_MULTIPLIER

        # Add urgency based on scheduled time
        now = datetime.now(tz=timezone.utc)
        if workflow.scheduled_time <= now:
            # Overdue workflows get bonus
            overdue_minutes = (now - workflow.scheduled_time).total_seconds() / 60
            urgency_bonus = min(
                overdue_minutes * WorkflowConfig.OVERDUE_BONUS_RATE,
                WorkflowConfig.MAX_OVERDUE_BONUS,
            )
            base_score += urgency_bonus

        # Complexity adjustment (Issue #376 - use named constants)
        complexity_multiplier = {
            TaskComplexity.SIMPLE: WorkflowConfig.COMPLEXITY_SIMPLE,
            TaskComplexity.RESEARCH: WorkflowConfig.COMPLEXITY_RESEARCH,
            TaskComplexity.INSTALL: WorkflowConfig.COMPLEXITY_INSTALL,
            TaskComplexity.COMPLEX: WorkflowConfig.COMPLEXITY_COMPLEX,
            TaskComplexity.SECURITY_SCAN: WorkflowConfig.COMPLEXITY_SECURITY_SCAN,
        }

        complexity_factor = complexity_multiplier.get(workflow.complexity, 1.0)

        # Add estimated duration factor (shorter workflows get slight priority)
        duration_factor = max(
            WorkflowConfig.MIN_DURATION_FACTOR,
            1.0 - (workflow.estimated_duration_minutes / WorkflowConfig.DEFAULT_TIMEOUT_MIN),
        )

        return base_score * complexity_factor * duration_factor

    def _dependencies_satisfied(self, workflow: ScheduledWorkflow) -> bool:
        """Check if all dependency workflows completed successfully (#2180).

        A dependency is satisfied when its workflow ID is present in
        completed_workflows with status COMPLETED. Any other terminal
        status (FAILED, CANCELLED) or absence leaves the dependency
        unsatisfied so the dependent workflow stays queued.

        Circular dependencies are detected via a visited set and logged
        as a warning; the affected workflow is treated as unsatisfied.
        """
        if not workflow.dependencies:
            return True

        return self._check_deps_recursive(workflow.id, workflow.dependencies, set())

    def _check_deps_recursive(
        self,
        origin_id: str,
        dep_ids: List[str],
        visited: set,
    ) -> bool:
        """Recursively verify all deps are satisfied, guarding against cycles.

        Args:
            origin_id: ID of the workflow we are checking (for cycle detection).
            dep_ids: Dependency IDs to check at this level.
            visited: Set of workflow IDs already visited in this traversal.

        Returns:
            True if every listed dependency completed successfully.
        """
        for dep_id in dep_ids:
            if dep_id == origin_id or dep_id in visited:
                logger.warning(
                    "Circular dependency detected for workflow %s (dep %s) — treating as" " unsatisfied",
                    origin_id,
                    dep_id,
                )
                return False

            dep_workflow = self._completed_workflows.get(dep_id)
            if dep_workflow is None:
                logger.debug(
                    "Workflow %s waiting — dependency %s not yet completed",
                    origin_id,
                    dep_id,
                )
                return False

            if dep_workflow.status != WorkflowStatus.COMPLETED:
                logger.debug(
                    "Workflow %s waiting — dependency %s has status %s",
                    origin_id,
                    dep_id,
                    dep_workflow.status.value,
                )
                return False

            visited.add(dep_id)

        return True

    def set_max_concurrent(self, max_concurrent: int) -> None:
        """Set maximum concurrent workflows"""
        self._max_concurrent = max(1, max_concurrent)


class WorkflowScheduler:
    """Main workflow scheduler with persistent storage (thread-safe)"""

    def __init__(self, storage_path: str = "data/scheduled_workflows.json"):
        """Initialize workflow scheduler with persistent storage and queue management."""
        self.storage_path = storage_path
        self.scheduled_workflows: Dict[str, ScheduledWorkflow] = {}
        self.completed_workflows: Dict[str, ScheduledWorkflow] = {}
        # Pass completed_workflows by reference so the queue always sees live state (#2180)
        self.queue = WorkflowQueue(completed_workflows=self.completed_workflows)
        self._scheduler_task: asyncio.Task | None = None
        self._running = False
        self._workflow_executor: Callable | None = None
        self._file_lock = threading.Lock()  # Lock for file operations

        # Load existing workflows
        self._load_workflows()

    def set_workflow_executor(self, executor: Callable) -> None:
        """Set the workflow execution function"""
        self._workflow_executor = executor

    async def start(self) -> None:
        """Start the scheduler"""
        if self._running:
            return

        if not self._workflow_executor:
            self._workflow_executor = _default_template_executor

        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        """Stop the scheduler"""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                logger.debug("Scheduler task cancelled during shutdown")

        # Issue #8165: run blocking file I/O off the event loop.
        await asyncio.to_thread(self._save_workflows)

    def _parse_schedule_params(
        self,
        scheduled_time: datetime | str,
        priority: WorkflowPriority | str,
        complexity: TaskComplexity | str,
    ) -> tuple:
        """Parse and normalize schedule parameters (Issue #398: extracted).

        Args:
            scheduled_time: Time as datetime or string
            priority: Priority as enum or string
            complexity: Complexity as enum or string

        Returns:
            Tuple of (parsed_time, parsed_priority, parsed_complexity)
        """
        # Parse scheduled time
        if isinstance(scheduled_time, str):
            try:
                scheduled_time = parse_utc_iso(scheduled_time)
            except ValueError:
                scheduled_time = self._parse_time_string(scheduled_time)

        # Parse priority and complexity
        if isinstance(priority, str):
            priority = WorkflowPriority[priority.upper()]
        if isinstance(complexity, str):
            complexity = TaskComplexity(complexity.lower())

        return scheduled_time, priority, complexity

    def _extract_request_params(self, request: WorkflowScheduleRequest, kwargs: Dict[str, Any]) -> tuple:
        """
        Extract parameters from WorkflowScheduleRequest object. Issue #620.

        Args:
            request: WorkflowScheduleRequest object
            kwargs: Additional keyword arguments dict to update

        Returns:
            Tuple of extracted parameters
        """
        kwargs.setdefault("estimated_duration_minutes", request.estimated_duration_minutes)
        kwargs.setdefault("timeout_minutes", request.timeout_minutes)
        kwargs.setdefault("max_retries", request.max_retries)
        return (
            request.user_message,
            request.scheduled_time,
            request.priority,
            request.complexity,
            request.template_id,
            request.variables,
            request.auto_approve,
            request.tags,
            request.dependencies,
            request.user_id,
        )

    def _resolve_workflow_params(
        self,
        request: "WorkflowScheduleRequest" | None,
        user_message: str | None,
        scheduled_time: datetime | str | None,
        priority: WorkflowPriority | str,
        complexity: TaskComplexity | str,
        template_id: str | None,
        variables: Dict[str, Any] | None,
        auto_approve: bool,
        tags: List[str] | None,
        dependencies: List[str] | None,
        user_id: str | None,
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolve and validate workflow parameters from request or kwargs. Issue #620.
        """
        if request is not None:
            (
                user_message,
                scheduled_time,
                priority,
                complexity,
                template_id,
                variables,
                auto_approve,
                tags,
                dependencies,
                user_id,
            ) = self._extract_request_params(request, kwargs)
        elif user_message is None or scheduled_time is None:
            raise ValueError("Either 'request' or 'user_message'/'scheduled_time' required")

        scheduled_time, priority, complexity = self._parse_schedule_params(scheduled_time, priority, complexity)

        return self._build_workflow_params_dict(
            user_message,
            scheduled_time,
            priority,
            complexity,
            template_id,
            variables,
            auto_approve,
            tags,
            dependencies,
            user_id,
        )

    def _build_workflow_params_dict(
        self,
        user_message: str,
        scheduled_time: datetime,
        priority: WorkflowPriority,
        complexity: TaskComplexity,
        template_id: str | None,
        variables: Dict[str, Any] | None,
        auto_approve: bool,
        tags: List[str] | None,
        dependencies: List[str] | None,
        user_id: str | None,
    ) -> Dict[str, Any]:
        """
        Build workflow parameters dictionary from resolved values. Issue #620.
        """
        return {
            "user_message": user_message,
            "scheduled_time": scheduled_time,
            "priority": priority,
            "complexity": complexity,
            "template_id": template_id,
            "variables": variables,
            "auto_approve": auto_approve,
            "tags": tags,
            "dependencies": dependencies,
            "user_id": user_id,
        }

    def _create_scheduled_workflow(
        self,
        workflow_id: str,
        params: Dict[str, Any],
        **kwargs,
    ) -> ScheduledWorkflow:
        """
        Create a ScheduledWorkflow instance from params dict. Issue #620.

        Args:
            workflow_id: Unique workflow identifier
            params: Dict with workflow parameters from _resolve_workflow_params

        Returns:
            ScheduledWorkflow instance
        """
        return ScheduledWorkflow(
            id=workflow_id,
            name=f"Workflow {workflow_id[:8]}",
            template_id=params["template_id"],
            user_message=params["user_message"],
            scheduled_time=params["scheduled_time"],
            priority=params["priority"],
            status=WorkflowStatus.SCHEDULED,
            created_at=datetime.now(tz=timezone.utc),
            complexity=params["complexity"],
            user_id=params["user_id"],
            variables=params["variables"] or {},
            auto_approve=params["auto_approve"],
            tags=params["tags"] or [],
            dependencies=params["dependencies"] or [],
            **kwargs,
        )

    def schedule_workflow(
        self,
        request: WorkflowScheduleRequest | None = None,
        *,  # Force keyword-only args for backwards compatibility
        user_message: str | None = None,
        scheduled_time: datetime | str | None = None,
        priority: WorkflowPriority | str = WorkflowPriority.NORMAL,
        complexity: TaskComplexity | str = TaskComplexity.SIMPLE,
        template_id: str | None = None,
        variables: Dict[str, Any] | None = None,
        auto_approve: bool = False,
        tags: List[str] | None = None,
        dependencies: List[str] | None = None,
        user_id: str | None = None,
        **kwargs,
    ) -> str:
        """Schedule a workflow for future execution. Issue #620: Refactored.

        Issue #319: Supports both request object and individual parameters.

        Returns:
            Workflow ID string
        """
        params = self._resolve_workflow_params(
            request,
            user_message,
            scheduled_time,
            priority,
            complexity,
            template_id,
            variables,
            auto_approve,
            tags,
            dependencies,
            user_id,
            kwargs,
        )

        workflow_id = str(uuid4())
        workflow = self._create_scheduled_workflow(workflow_id, params, **kwargs)

        self.scheduled_workflows[workflow_id] = workflow
        self._save_workflows()
        return workflow_id

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a scheduled or queued workflow"""
        # Try cancelling from queue first
        if self.queue.cancel_workflow(workflow_id):
            return True

        # Cancel scheduled workflow
        if workflow_id in self.scheduled_workflows:
            workflow = self.scheduled_workflows[workflow_id]
            if workflow.status == WorkflowStatus.SCHEDULED:
                workflow.status = WorkflowStatus.CANCELLED
                self._save_workflows()
                return True

        return False

    def reschedule_workflow(
        self,
        workflow_id: str,
        new_time: datetime | str,
        new_priority: WorkflowPriority | str | None = None,
    ) -> bool:
        """Reschedule an existing workflow"""
        if workflow_id not in self.scheduled_workflows:
            return False

        workflow = self.scheduled_workflows[workflow_id]

        # Only reschedule if not already running
        if workflow.status in (
            WorkflowStatus.RUNNING,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
        ):
            return False

        # Parse new time
        if isinstance(new_time, str):
            new_time = self._parse_time_string(new_time)

        workflow.scheduled_time = new_time

        if new_priority:
            if isinstance(new_priority, str):
                new_priority = WorkflowPriority[new_priority.upper()]
            workflow.priority = new_priority

        # Reset status to scheduled
        workflow.status = WorkflowStatus.SCHEDULED

        self._save_workflows()
        return True

    def get_workflow(self, workflow_id: str) -> ScheduledWorkflow | None:
        """Get a workflow by ID"""
        return self.scheduled_workflows.get(workflow_id)

    def list_scheduled_workflows(
        self,
        status: WorkflowStatus | None = None,
        user_id: str | None = None,
        tags: List[str] | None = None,
    ) -> List[ScheduledWorkflow]:
        """List scheduled workflows with optional filtering"""
        workflows = list(self.scheduled_workflows.values())

        if status:
            workflows = [w for w in workflows if w.status == status]

        if user_id:
            workflows = [w for w in workflows if w.user_id == user_id]

        if tags:
            workflows = [w for w in workflows if any(tag in w.tags for tag in tags)]

        return sorted(workflows, key=lambda w: w.scheduled_time)

    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get current scheduler status"""
        now = datetime.now(tz=timezone.utc)

        status_counts = {}
        overdue_count = 0

        for workflow in self.scheduled_workflows.values():
            status_key = workflow.status.value
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

            if workflow.status == WorkflowStatus.SCHEDULED and workflow.scheduled_time <= now:
                overdue_count += 1

        return {
            "running": self._running,
            "queue_status": self.queue.get_queue_status(),
            "total_scheduled": len(self.scheduled_workflows),
            "status_breakdown": status_counts,
            "overdue_workflows": overdue_count,
            "completed_workflows": len(self.completed_workflows),
        }

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop (Issue #376 - use named constants)"""
        while self._running:
            try:
                await self._process_scheduled_workflows()
                await self._execute_queued_workflows()
                await asyncio.sleep(WorkflowConfig.SCHEDULER_CHECK_INTERVAL_S)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler loop error: %s", e)
                await asyncio.sleep(WorkflowConfig.SCHEDULER_ERROR_BACKOFF_S)

    async def _process_scheduled_workflows(self) -> None:
        """Move due scheduled workflows to queue"""
        now = datetime.now(tz=timezone.utc)

        for workflow in list(self.scheduled_workflows.values()):
            if workflow.status == WorkflowStatus.SCHEDULED and workflow.scheduled_time <= now:
                # Move to queue
                self.queue.add(workflow)
                logger.info("Queued workflow %s: %s", workflow.id, workflow.name)

    async def _execute_queued_workflows(self) -> None:
        """Execute workflows from queue"""
        if not self._workflow_executor:
            return

        while True:
            workflow = self.queue.get_next()
            if not workflow:
                break

            logger.info("Executing workflow %s: %s", workflow.id, workflow.name)

            # Execute workflow in background
            asyncio.create_task(self._execute_workflow(workflow))

    async def _execute_workflow(self, workflow: ScheduledWorkflow) -> None:
        """Execute a single workflow"""
        try:
            if self._workflow_executor:
                result = await self._workflow_executor(workflow)

                if result and result.get("success"):
                    self.queue.complete_workflow(workflow.id, WorkflowStatus.COMPLETED)
                    await self._move_to_completed(workflow)
                    logger.info("Workflow %s completed successfully", workflow.id)
                else:
                    # Handle failure with retry logic
                    await self._handle_workflow_failure(workflow)

        except Exception as e:
            logger.error("Workflow execution error: %s", e)
            await self._handle_workflow_failure(workflow)

    async def _handle_workflow_failure(self, workflow: ScheduledWorkflow) -> None:
        """Handle workflow execution failure"""
        workflow.retry_count += 1

        if workflow.retry_count < workflow.max_retries:
            # Reschedule for retry
            retry_delay = min(300 * (2**workflow.retry_count), 3600)  # Exponential backoff, max 1 hour
            workflow.scheduled_time = datetime.now(tz=timezone.utc) + timedelta(seconds=retry_delay)
            workflow.status = WorkflowStatus.SCHEDULED
            logger.info(f"Rescheduling workflow {workflow.id} for retry {workflow.retry_count}")
        else:
            # Mark as failed
            self.queue.complete_workflow(workflow.id, WorkflowStatus.FAILED)
            await self._move_to_completed(workflow)
            logger.warning("Workflow %s failed after %s retries", workflow.id, workflow.retry_count)

    async def _move_to_completed(self, workflow: ScheduledWorkflow) -> None:
        """Move workflow to completed storage.

        Issue #8165: async so the blocking file write runs via asyncio.to_thread.
        """
        self.completed_workflows[workflow.id] = workflow
        if workflow.id in self.scheduled_workflows:
            del self.scheduled_workflows[workflow.id]
        await asyncio.to_thread(self._save_workflows)

    def _parse_time_string(self, time_str: str) -> datetime:
        """Parse various time string formats"""
        now = datetime.now(tz=timezone.utc)
        time_str = time_str.lower().strip()

        # Handle relative times
        if "in" in time_str:
            if "minute" in time_str:
                minutes = int("".join(filter(str.isdigit, time_str)))
                return now + timedelta(minutes=minutes)
            elif "hour" in time_str:
                hours = int("".join(filter(str.isdigit, time_str)))
                return now + timedelta(hours=hours)
            elif "day" in time_str:
                days = int("".join(filter(str.isdigit, time_str)))
                return now + timedelta(days=days)

        # Handle specific times
        if time_str == "now":
            return now
        elif time_str == "tomorrow":
            return now + timedelta(days=1)

        # Default: try parsing as ISO format
        try:
            return parse_utc_iso(time_str)
        except ValueError:
            # Fall back to current time + 5 minutes
            return now + timedelta(minutes=5)

    def _save_workflows(self) -> None:
        """Save workflows to persistent storage (thread-safe)"""
        with self._file_lock:
            try:
                import os

                os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)

                data = {
                    "scheduled": {wf_id: wf.to_dict() for wf_id, wf in self.scheduled_workflows.items()},
                    "completed": {wf_id: wf.to_dict() for wf_id, wf in self.completed_workflows.items()},
                }

                with open(self.storage_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, default=str, ensure_ascii=False)

            except Exception as e:
                logger.error("Failed to save workflows: %s", e)

    def _load_workflow_dict(self, data: Dict[str, Any], key: str, target: Dict[str, ScheduledWorkflow]) -> None:
        """Load workflows from data dict into target (Issue #315 - extracted helper)."""
        for wf_id, wf_data in data.get(key, {}).items():
            try:
                workflow = ScheduledWorkflow.from_dict(wf_data)
                target[wf_id] = workflow
            except Exception as e:
                logger.warning("Failed to load %s workflow %s: %s", key, wf_id, e)

    def _load_workflows(self) -> None:
        """Load workflows from persistent storage (Issue #315 - refactored depth 5 to 3)."""
        with self._file_lock:
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self._load_workflow_dict(data, "scheduled", self.scheduled_workflows)
                self._load_workflow_dict(data, "completed", self.completed_workflows)

            except FileNotFoundError:
                pass  # No existing data, start fresh
            except Exception as e:
                logger.error("Failed to load workflows: %s", e)


async def _default_template_executor(
    workflow: ScheduledWorkflow,
) -> Dict[str, Any]:
    """Execute a scheduled workflow via template execution (#1614).

    Adapts ScheduledWorkflow to the template execution interface.
    Requires template_id to be set on the workflow.
    """
    if not workflow.template_id:
        logger.warning(
            "Scheduled workflow %s has no template_id, skipping",
            workflow.id,
        )
        return {"success": False, "error": "No template_id"}

    from api.templates import TemplateExecutionRequest, execute_template_workflow

    request = TemplateExecutionRequest(
        template_id=workflow.template_id,
        variables=workflow.variables or {},
        auto_approve=workflow.auto_approve,
    )
    result = await execute_template_workflow(workflow.template_id, request)
    return result


get_workflow_scheduler = lazy_singleton(WorkflowScheduler)


# ---------------------------------------------------------------------------
# Autonomous improvement loop integration (Issue #4680)
# ---------------------------------------------------------------------------

_autonomous_loop_task: asyncio.Task | None = None


async def _autonomous_loop_runner(llm_service: Any) -> None:
    """Background task that polls the autonomous_loop_cron schedule and fires runs.

    Uses a simple asyncio loop with 60-second resolution rather than a full cron
    library to avoid adding a new dependency.  Checks ``autonomous_loop_enabled``
    on every tick so the feature can be toggled at runtime without restart.
    """

    from services.knowledge.autonomous_loop import run_scheduled_loop
    from services.rag_config import get_rag_config

    def _cron_matches_now(cron_expr: str) -> bool:
        """Return True when the current UTC time matches *cron_expr*.

        Evaluates all 5 standard cron fields: minute hour day-of-month month day-of-week.
        Day-of-week uses standard cron convention: 0=Sunday, 1=Monday, …, 6=Saturday.
        Conversion to Python weekday(): ``(cron_dow - 1) % 7``
          cron 0 (Sun) → Python 6, cron 1 (Mon) → Python 0, …, cron 6 (Sat) → Python 5.
        """
        try:
            parts = cron_expr.split()
            if len(parts) < 5:
                return False
            now = datetime.now(tz=timezone.utc)
            minute_match = parts[0] == "*" or int(parts[0]) == now.minute
            hour_match = parts[1] == "*" or int(parts[1]) == now.hour
            dom_match = parts[2] == "*" or int(parts[2]) == now.day
            month_match = parts[3] == "*" or int(parts[3]) == now.month
            dow_match = parts[4] == "*" or (int(parts[4]) - 1) % 7 == now.weekday()
            return minute_match and hour_match and dom_match and month_match and dow_match
        except Exception:
            return False

    logger.info("AutonomousLoopRunner: background task started")
    _last_fired_minute: int | None = None

    while True:
        try:
            cfg = get_rag_config()
            if cfg.autonomous_loop_enabled:
                now = datetime.now(tz=timezone.utc)
                current_minute = now.hour * 60 + now.minute
                if _cron_matches_now(cfg.autonomous_loop_cron) and current_minute != _last_fired_minute:
                    _last_fired_minute = current_minute
                    logger.info("AutonomousLoopRunner: cron matched — firing loop run")
                    asyncio.create_task(run_scheduled_loop(llm_service))
        except Exception:
            logger.exception("AutonomousLoopRunner: tick error (non-fatal)")

        await asyncio.sleep(30)  # 30-second tick resolution


def start_autonomous_loop(llm_service: Any) -> None:
    """Schedule the autonomous improvement loop background task.

    Call this from the application lifespan startup after the event loop is running.
    Safe to call multiple times — only starts once.

    Issue #4680.
    """
    global _autonomous_loop_task
    if _autonomous_loop_task is not None and not _autonomous_loop_task.done():
        logger.debug("AutonomousLoopRunner: already running — skipping duplicate start")
        return

    _autonomous_loop_task = asyncio.create_task(
        _autonomous_loop_runner(llm_service),
        name="autonomous_loop_runner",
    )
    logger.info("AutonomousLoopRunner: task created")
