# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Robust task queue system for AutoBot with Redis backend.

This module provides a comprehensive task queue implementation with
priority handling, retry logic, and distributed task execution.
"""

import asyncio
import json
import logging
import time
import traceback
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

try:
    from redis.exceptions import RedisError

    from autobot_shared.redis_client import get_redis_client
except ImportError:
    RedisError = Exception  # Fallback if redis not available
    get_redis_client = None

from backend.constants.threshold_constants import RetryConfig, TimingConstants

# Temporary implementations until proper modules are created
# try:
#     from utils.error_handler import error_handler, ErrorCategory
# except ImportError:
error_handler = None
ErrorCategory = None


# try:
#     from utils.logging_config import log_performance_metric
# except ImportError:
def log_performance_metric(*args, **kwargs):
    """Log performance metric placeholder until logging_config module is created."""


class TaskStatus(Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY = "retry"


class TaskPriority(Enum):
    """Task priority levels."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class TaskResult:
    """Task execution result."""

    task_id: str
    status: TaskStatus
    result: Any = None
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time: Optional[float] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["status"] = self.status.value
        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        """Create from dictionary."""
        if "status" in data:
            data["status"] = TaskStatus(data["status"])
        if "started_at" in data and data["started_at"]:
            data["started_at"] = datetime.fromisoformat(data["started_at"])
        if "completed_at" in data and data["completed_at"]:
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])
        return cls(**data)


@dataclass
class Task:
    """Task definition for queue execution."""

    id: str
    function_name: str
    args: tuple = ()
    kwargs: Optional[Dict[str, Any]] = None
    priority: TaskPriority = TaskPriority.NORMAL
    max_retries: int = RetryConfig.DEFAULT_RETRIES
    retry_delay: float = 1.0  # seconds
    timeout: Optional[float] = None
    created_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize default values for kwargs, created_at, and metadata."""
        if self.kwargs is None:
            self.kwargs = {}
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["priority"] = self.priority.value
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.scheduled_at:
            data["scheduled_at"] = self.scheduled_at.isoformat()
        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create from dictionary."""
        if "priority" in data:
            data["priority"] = TaskPriority(data["priority"])
        if "created_at" in data:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "scheduled_at" in data and data["scheduled_at"]:
            data["scheduled_at"] = datetime.fromisoformat(data["scheduled_at"])
        if "expires_at" in data and data["expires_at"]:
            data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return cls(**data)


class TaskQueue:
    """Redis-based task queue with priority and retry support."""

    def __init__(
        self,
        queue_name: str = "autobot_tasks",
        redis_client=None,
        max_workers: int = 5,
        enable_scheduler: bool = True,
    ):
        """
        Initialize task queue.

        Args:
            queue_name: Base name for Redis keys
            redis_client: Redis client instance
            max_workers: Maximum concurrent workers
            enable_scheduler: Whether to enable scheduled task processing
        """
        self.queue_name = queue_name
        self.redis = redis_client or (get_redis_client() if get_redis_client else None)
        self.max_workers = max_workers
        self.enable_scheduler = enable_scheduler

        # Redis key patterns
        self.pending_key = f"{queue_name}:pending"
        self.running_key = f"{queue_name}:running"
        self.completed_key = f"{queue_name}:completed"
        self.failed_key = f"{queue_name}:failed"
        self.scheduled_key = f"{queue_name}:scheduled"
        self.results_key = f"{queue_name}:results"

        # Task registry for function execution
        self.task_registry: Dict[str, Callable] = {}

        # Worker management
        self.workers: List[asyncio.Task] = []
        self.is_running = False
        self.logger = logging.getLogger(__name__)

        # Lock for thread-safe stats access
        self._stats_lock = asyncio.Lock()

        # Statistics
        self.stats = {
            "tasks_processed": 0,
            "tasks_failed": 0,
            "total_execution_time": 0.0,
            "started_at": None,
        }

    def register_task(self, name: str, func: Callable) -> None:
        """
        Register a task function.

        Args:
            name: Task name identifier
            func: Function to execute for this task
        """
        self.task_registry[name] = func
        self.logger.info("Registered task: %s", name)

    def task(self, name: str = None):
        """
        Decorator to register task functions.

        Args:
            name: Optional task name (defaults to function name)
        """

        def decorator(func: Callable):
            """Register function with task name and return it unchanged."""
            task_name = name or func.__name__
            self.register_task(task_name, func)
            return func

        return decorator

    def _calculate_task_timing(
        self, delay: Optional[float], expires_in: Optional[float]
    ) -> tuple:
        """
        Calculate scheduled_at and expires_at timestamps for a task.

        Args:
            delay: Delay before execution (seconds)
            expires_in: Task expiration time (seconds)

        Returns:
            Tuple of (scheduled_at, expires_at) datetime objects or None

        Issue #620.
        """
        scheduled_at = None
        if delay:
            scheduled_at = datetime.utcnow() + timedelta(seconds=delay)

        expires_at = None
        if expires_in:
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        return scheduled_at, expires_at

    async def _add_task_to_queue(
        self, task_id: str, scheduled_at: Optional[datetime], priority: TaskPriority
    ) -> None:
        """
        Add task to appropriate queue (scheduled or pending).

        Args:
            task_id: The task identifier
            scheduled_at: When to execute (None for immediate)
            priority: Task priority level

        Raises:
            RuntimeError: If Redis operation fails

        Issue #620.
        """
        try:
            if scheduled_at and scheduled_at > datetime.utcnow():
                score = scheduled_at.timestamp()
                await self.redis.zadd(self.scheduled_key, {task_id: score})
            else:
                priority_score = priority.value * 1000000 + int(time.time())
                await self.redis.zadd(self.pending_key, {task_id: priority_score})
        except RedisError as e:
            self.logger.error("Failed to enqueue task %s: %s", task_id, e)
            raise RuntimeError(f"Failed to enqueue task: {e}")

    async def enqueue(
        self,
        function_name: str,
        *args,
        priority: TaskPriority = TaskPriority.NORMAL,
        delay: Optional[float] = None,
        timeout: Optional[float] = None,
        max_retries: int = RetryConfig.DEFAULT_RETRIES,
        expires_in: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """
        Enqueue a task for execution.

        Args:
            function_name: Name of registered function to execute
            *args: Function arguments
            priority: Task priority
            delay: Delay before execution (seconds)
            timeout: Task timeout (seconds)
            max_retries: Maximum retry attempts
            expires_in: Task expiration time (seconds)
            metadata: Additional task metadata
            **kwargs: Function keyword arguments

        Returns:
            Task ID
        """
        if not self.redis:
            raise RuntimeError("Redis client not available")

        task_id = str(uuid.uuid4())
        scheduled_at, expires_at = self._calculate_task_timing(delay, expires_in)

        task = Task(
            id=task_id,
            function_name=function_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            max_retries=max_retries,
            timeout=timeout,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        await self._store_task(task)
        await self._add_task_to_queue(task_id, scheduled_at, priority)

        self.logger.info("Enqueued task %s: %s", task_id, function_name)
        return task_id

    async def _store_task(self, task: Task) -> None:
        """Store task data in Redis."""
        if not self.redis:
            return
        try:
            task_data = json.dumps(task.to_dict())
            await self.redis.hset(f"{self.queue_name}:tasks", task.id, task_data)
        except RedisError as e:
            self.logger.error("Failed to store task %s: %s", task.id, e)
            raise RuntimeError(f"Failed to store task: {e}")

    async def _get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve task data from Redis."""
        if not self.redis:
            return None
        try:
            task_data = await self.redis.hget(f"{self.queue_name}:tasks", task_id)
            if task_data:
                return Task.from_dict(json.loads(task_data))
            return None
        except RedisError as e:
            self.logger.error("Failed to get task %s: %s", task_id, e)
            raise RuntimeError(f"Failed to get task: {e}")

    async def start_workers(self) -> None:
        """Start worker processes (thread-safe)."""
        if self.is_running:
            return

        self.is_running = True
        async with self._stats_lock:
            self.stats["started_at"] = datetime.utcnow()

        # Start task workers
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self.workers.append(worker)

        # Start scheduler if enabled
        if self.enable_scheduler:
            scheduler = asyncio.create_task(self._scheduler_loop())
            self.workers.append(scheduler)

        self.logger.info("Started %s workers", len(self.workers))

    async def stop_workers(self) -> None:
        """Stop all workers."""
        self.is_running = False

        # Cancel all workers
        for worker in self.workers:
            worker.cancel()

        # Wait for workers to finish
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)

        self.workers.clear()
        self.logger.info("Stopped all workers")

    async def _worker_loop(self, worker_name: str) -> None:
        """Main worker loop."""
        self.logger.info("Worker %s started", worker_name)

        while self.is_running:
            try:
                # Get next task
                task_id = await self._get_next_task()
                if not task_id:
                    await asyncio.sleep(TimingConstants.STANDARD_DELAY)
                    continue

                # Process task
                await self._process_task(task_id, worker_name)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Worker %s error: %s", worker_name, e)
                await asyncio.sleep(TimingConstants.STANDARD_DELAY)

        self.logger.info("Worker %s stopped", worker_name)

    async def _scheduler_loop(self) -> None:
        """Scheduler loop for delayed tasks."""
        self.logger.info("Scheduler started")

        while self.is_running:
            try:
                if not self.redis:
                    await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)
                    continue

                current_time = time.time()

                # Get scheduled tasks that are due
                due_tasks = await self.redis.zrangebyscore(
                    self.scheduled_key, 0, current_time, withscores=True
                )

                for task_id, score in due_tasks:
                    # Move to pending queue
                    task = await self._get_task(task_id)
                    if task:
                        priority_score = task.priority.value * 1000000 + int(
                            time.time()
                        )
                        await self.redis.zadd(
                            self.pending_key, {task_id: priority_score}
                        )
                        await self.redis.zrem(self.scheduled_key, task_id)

                        self.logger.debug(
                            "Moved scheduled task to pending: %s", task_id
                        )

                await asyncio.sleep(
                    TimingConstants.ERROR_RECOVERY_DELAY
                )  # Check every 5 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Scheduler error: %s", e)
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)

        self.logger.info("Scheduler stopped")

    async def _get_next_task(self) -> Optional[str]:
        """Get next task from pending queue."""
        if not self.redis:
            return None

        try:
            # Get highest priority task
            tasks = await self.redis.zrevrange(self.pending_key, 0, 0)
            if not tasks:
                return None

            task_id = tasks[0]

            # Move to running queue
            await self.redis.zrem(self.pending_key, task_id)
            await self.redis.zadd(self.running_key, {task_id: time.time()})

            return task_id
        except RedisError as e:
            self.logger.error("Failed to get next task from queue: %s", e)
            return None  # Return None to allow worker to continue

    async def _record_task_success(
        self, result: TaskResult, task_result: Any, start_time: float
    ) -> None:
        """
        Record successful task execution.

        (Issue #398: extracted helper)
        """
        result.status = TaskStatus.COMPLETED
        result.result = task_result
        result.completed_at = datetime.utcnow()
        result.execution_time = time.time() - start_time

        async with self._stats_lock:
            self.stats["tasks_processed"] += 1
            self.stats["total_execution_time"] += result.execution_time

        self.logger.info(
            "Task %s completed successfully in %.2fs",
            result.task_id,
            result.execution_time,
        )

    def _record_task_failure(
        self,
        result: TaskResult,
        error: str,
        start_time: float,
        error_traceback: Optional[str] = None,
    ) -> None:
        """
        Record task failure.

        (Issue #398: extracted helper)
        """
        result.status = TaskStatus.FAILED
        result.error = error
        if error_traceback:
            result.error_traceback = error_traceback
        result.completed_at = datetime.utcnow()
        result.execution_time = time.time() - start_time

    def _check_task_expired(self, task: Task) -> bool:
        """
        Check if a task has expired based on its expiration time.

        Args:
            task: The task to check

        Returns:
            True if the task has expired, False otherwise

        Issue #620.
        """
        return task.expires_at is not None and datetime.utcnow() > task.expires_at

    async def _execute_task_with_timeout(
        self, task: Task, result: TaskResult, start_time: float
    ) -> None:
        """
        Execute a task with optional timeout handling.

        Args:
            task: The task to execute
            result: The TaskResult object to update
            start_time: When task processing started

        Issue #620.
        """
        if task.function_name not in self.task_registry:
            raise ValueError(f"Task function '{task.function_name}' not registered")

        func = self.task_registry[task.function_name]
        kwargs = task.kwargs or {}

        if task.timeout:
            task_result = await asyncio.wait_for(
                self._execute_function(func, task.args, kwargs),
                timeout=task.timeout,
            )
        else:
            task_result = await self._execute_function(func, task.args, kwargs)

        await self._record_task_success(result, task_result, start_time)

    async def _process_task(self, task_id: str, worker_name: str) -> None:
        """
        Process a single task.

        (Issue #398: refactored to use extracted helpers)
        (Issue #620: further extraction of helpers)
        """
        start_time = time.time()
        task = await self._get_task(task_id)

        if not task:
            self.logger.error("Task %s not found", task_id)
            return

        if self._check_task_expired(task):
            await self._handle_task_completion(
                task,
                TaskResult(
                    task_id=task_id, status=TaskStatus.CANCELLED, error="Task expired"
                ),
            )
            return

        self.logger.info(
            "Worker %s processing task %s: %s", worker_name, task_id, task.function_name
        )

        result = TaskResult(
            task_id=task_id, status=TaskStatus.RUNNING, started_at=datetime.utcnow()
        )

        try:
            await self._execute_task_with_timeout(task, result, start_time)

        except asyncio.TimeoutError:
            self._record_task_failure(
                result, f"Task timed out after {task.timeout}s", start_time
            )
            self.logger.error("Task %s timed out", task_id)

        except Exception as e:
            self._record_task_failure(
                result, str(e), start_time, traceback.format_exc()
            )
            self.logger.error("Task %s failed: %s", task_id, e)

        await self._handle_task_completion(task, result)

    async def _execute_function(
        self, func: Callable, args: tuple, kwargs: Dict[str, Any]
    ) -> Any:
        """Execute task function (sync or async)."""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            # Run sync function in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def _handle_task_completion(self, task: Task, result: TaskResult) -> None:
        """Handle task completion (success or failure)."""
        if not self.redis:
            return

        # Remove from running queue
        await self.redis.zrem(self.running_key, task.id)

        if result.status == TaskStatus.FAILED and result.retry_count < task.max_retries:
            await self._schedule_task_retry(task, result)
        else:
            await self._finalize_task_completion(task, result)

        await self._store_task_result(task, result)
        self._log_task_performance(task, result)

    async def _schedule_task_retry(self, task: Task, result: TaskResult) -> None:
        """Schedule a failed task for retry with exponential backoff. Issue #620."""
        result.retry_count += 1
        result.status = TaskStatus.RETRY

        retry_delay = task.retry_delay * (2**result.retry_count)
        retry_time = datetime.utcnow() + timedelta(seconds=retry_delay)

        if task.metadata:
            task.metadata["retry_count"] = result.retry_count
            task.metadata["last_error"] = result.error
        await self._store_task(task)

        await self.redis.zadd(self.scheduled_key, {task.id: retry_time.timestamp()})

        self.logger.info(
            f"Scheduling retry {result.retry_count}/{task.max_retries} "
            f"for task {task.id} in {retry_delay}s"
        )

    async def _finalize_task_completion(self, task: Task, result: TaskResult) -> None:
        """Move task to completed or failed queue. Issue #620."""
        if result.status == TaskStatus.COMPLETED:
            await self.redis.zadd(self.completed_key, {task.id: time.time()})
        else:
            await self.redis.zadd(self.failed_key, {task.id: time.time()})
            async with self._stats_lock:
                self.stats["tasks_failed"] += 1

    async def _store_task_result(self, task: Task, result: TaskResult) -> None:
        """Store task result in Redis. Issue #620."""
        result_data = json.dumps(result.to_dict())
        # Issue #361 - avoid blocking
        await asyncio.to_thread(self.redis.hset, self.results_key, task.id, result_data)

    def _log_task_performance(self, task: Task, result: TaskResult) -> None:
        """Log task execution performance metrics. Issue #620."""
        if result.execution_time:
            log_performance_metric(
                "task_execution_time",
                result.execution_time,
                "seconds",
                task_id=task.id,
                function_name=task.function_name,
                status=result.status.value,
                retry_count=result.retry_count,
            )

    async def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """Get task execution result."""
        if not self.redis:
            return None
        # Issue #361 - avoid blocking
        result_data = await asyncio.to_thread(
            self.redis.hget, self.results_key, task_id
        )
        if result_data:
            return TaskResult.from_dict(json.loads(result_data))
        return None

    def _check_task_in_queue(self, task_id: str, queue_key: str) -> bool:
        """Check if task exists in specified queue (Issue #315 - extracted helper)."""
        try:
            return self.redis.zscore(queue_key, task_id) is not None
        except RedisError:
            return False

    async def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get current task status (Issue #315 - uses dispatch table pattern)."""
        if not self.redis:
            return None

        # Dispatch table: (queue_key, status_if_found)
        queue_status_map = [
            (self.pending_key, TaskStatus.PENDING),
            (self.scheduled_key, TaskStatus.PENDING),
            (self.running_key, TaskStatus.RUNNING),
            (self.completed_key, TaskStatus.COMPLETED),
            (self.failed_key, TaskStatus.FAILED),
        ]

        for queue_key, status in queue_status_map:
            if self._check_task_in_queue(task_id, queue_key):
                return status

        return None

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task."""
        if not self.redis:
            return False

        # Remove from pending or scheduled queues
        removed_pending = await self.redis.zrem(self.pending_key, task_id)
        removed_scheduled = await self.redis.zrem(self.scheduled_key, task_id)

        if removed_pending or removed_scheduled:
            # Create cancelled result
            result = TaskResult(
                task_id=task_id,
                status=TaskStatus.CANCELLED,
                completed_at=datetime.utcnow(),
            )

            result_data = json.dumps(result.to_dict())
            # Issue #361 - avoid blocking
            await asyncio.to_thread(
                self.redis.hset, self.results_key, task_id, result_data
            )

            self.logger.info("Cancelled task %s", task_id)
            return True

        return False

    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics (thread-safe)."""
        if not self.redis:
            return {
                "queue_name": self.queue_name,
                "redis_available": False,
                "error": "Redis client not available",
            }

        pending_count = self.redis.zcard(self.pending_key)
        running_count = self.redis.zcard(self.running_key)
        completed_count = self.redis.zcard(self.completed_key)
        failed_count = self.redis.zcard(self.failed_key)
        scheduled_count = self.redis.zcard(self.scheduled_key)

        # Copy stats under lock
        async with self._stats_lock:
            stats_copy = dict(self.stats)
            started_at = self.stats["started_at"]

        stats = {
            "queue_name": self.queue_name,
            "pending_tasks": pending_count,
            "running_tasks": running_count,
            "completed_tasks": completed_count,
            "failed_tasks": failed_count,
            "scheduled_tasks": scheduled_count,
            "total_tasks": (
                pending_count + running_count + completed_count + failed_count
            ),
            "workers": len(self.workers),
            "is_running": self.is_running,
            "registered_functions": list(self.task_registry.keys()),
            "performance": stats_copy,
            "redis_available": True,
        }

        if started_at:
            uptime = datetime.utcnow() - started_at
            stats["uptime_seconds"] = uptime.total_seconds()

        return stats

    async def cleanup_completed_tasks(self, older_than_hours: int = 24) -> int:
        """Clean up old completed and failed tasks."""
        if not self.redis:
            return 0

        cutoff_time = time.time() - (older_than_hours * 3600)

        # Issue #361 - avoid blocking - run all Redis ops in helper
        def _cleanup_old_tasks():
            # Get old tasks
            old_completed = self.redis.zrangebyscore(self.completed_key, 0, cutoff_time)
            old_failed = self.redis.zrangebyscore(self.failed_key, 0, cutoff_time)

            all_old_tasks = list(old_completed) + list(old_failed)

            if all_old_tasks:
                # Remove from queues
                if old_completed:
                    self.redis.zremrangebyscore(self.completed_key, 0, cutoff_time)
                if old_failed:
                    self.redis.zremrangebyscore(self.failed_key, 0, cutoff_time)

                # Remove task data and results
                self.redis.hdel(f"{self.queue_name}:tasks", *all_old_tasks)
                self.redis.hdel(self.results_key, *all_old_tasks)

            return len(all_old_tasks)

        cleaned_count = await asyncio.to_thread(_cleanup_old_tasks)
        if cleaned_count > 0:
            self.logger.info("Cleaned up %s old tasks", cleaned_count)

        return cleaned_count


# Global task queue instance (thread-safe)
import threading

_task_queue: Optional[TaskQueue] = None
_task_queue_lock = threading.Lock()


def get_task_queue() -> TaskQueue:
    """Get the global task queue instance (thread-safe)."""
    global _task_queue

    if _task_queue is None:
        with _task_queue_lock:
            # Double-check after acquiring lock
            if _task_queue is None:
                _task_queue = TaskQueue()

    return _task_queue


def initialize_task_queue(**kwargs) -> TaskQueue:
    """Initialize the global task queue."""
    global _task_queue

    _task_queue = TaskQueue(**kwargs)
    return _task_queue


# Convenience decorators
def task(name: Optional[str] = None, **task_kwargs):
    """
    Decorator to register and configure task functions.

    Args:
        name: Task name (defaults to function name)
        **task_kwargs: Default task configuration
    """

    def decorator(func: Callable):
        """Register function as task and add enqueue method."""
        task_queue = get_task_queue()
        task_name = name or func.__name__
        task_queue.register_task(task_name, func)

        # Add enqueue method to function
        async def enqueue_task(*args, **kwargs):
            """Enqueue task with merged default and call-time config."""
            # Merge default task config with call-time config
            enqueue_kwargs = task_kwargs.copy()
            enqueue_kwargs.update(kwargs)

            return await task_queue.enqueue(task_name, *args, **enqueue_kwargs)

        # Store as attributes with type hints to avoid linter warnings
        func.__dict__["enqueue"] = enqueue_task
        func.__dict__["task_name"] = task_name

        return func

    return decorator


async def enqueue_task(function_name: str, *args, **kwargs) -> str:
    """
    Convenience function to enqueue a task.

    Args:
        function_name: Name of registered function
        *args: Function arguments
        **kwargs: Task configuration and function keyword arguments

    Returns:
        Task ID
    """
    task_queue = get_task_queue()
    return await task_queue.enqueue(function_name, *args, **kwargs)
