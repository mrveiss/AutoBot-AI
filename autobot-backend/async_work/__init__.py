# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified async-work facade for AutoBot.

Issue #6495: Unify 10 parallel async systems (3 task queues, 3 progress trackers,
4 schedulers) onto a single interface backed by Celery.

## Layer summary

  TaskQueue       — enqueue/retrieve tasks (Celery as canonical broker)
  ProgressTracker — report/query task progress (Redis-backed)
  PeriodicScheduler — register/cancel recurring jobs (Celery Beat as canonical)

## Migration status

  Phase 1 — Task queues   : facade defined; callers still use legacy directly
  Phase 2 — Progress      : facade defined; callers still use legacy directly
  Phase 3 — Schedulers    : facade defined; callers still use legacy directly

Full migration plan: docs/architecture/async-work.md

## Quick-start (new code)

    from async_work import get_task_queue, get_progress_tracker, get_periodic_scheduler

    # Enqueue a Celery task
    handle = await get_task_queue().enqueue("knowledge_tasks.rebuild_index", priority=5)

    # Report progress inside a task
    await get_progress_tracker().report(task_id, percent=50, current_step="Embedding")

    # Schedule a periodic job
    get_periodic_scheduler().schedule("nightly_cleanup", "0 2 * * *", cleanup_callback)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class TaskHandle:
    """Opaque reference to an enqueued task."""

    task_id: str
    queue_name: str
    priority: int = 5


@dataclass
class TaskRecord:
    """Snapshot of a task's current state."""

    task_id: str
    status: str  # pending | running | success | failure | revoked
    result: Any = None
    error: str | None = None
    progress_percent: float = 0.0
    current_step: str | None = None


@dataclass
class Progress:
    """Progress snapshot for a long-running task."""

    task_id: str
    percent: float
    current_step: str | None = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# TaskQueue facade
# ---------------------------------------------------------------------------


class TaskQueue:
    """
    Single entry point for enqueuing and retrieving tasks.

    Backed by Celery (Redis broker DB 1, result backend DB 2).
    Direct Redis-Streams usage (utils/task_queue.py) is a carve-out for
    atomic-claim patterns per issue #6468 — document new carve-outs here.
    """

    async def enqueue(
        self,
        task_name: str,
        args: tuple = (),
        kwargs: dict | None = None,
        *,
        priority: int = 5,
        countdown: float = 0,
    ) -> TaskHandle:
        """Enqueue a Celery task by dotted name.

        Args:
            task_name: Celery task name, e.g. ``knowledge_tasks.rebuild_index``
            args: Positional args passed to the task
            kwargs: Keyword args passed to the task
            priority: 0 (highest) – 9 (lowest); default 5
            countdown: Delay in seconds before execution

        Returns:
            TaskHandle with the Celery task id
        """
        from celery_app import celery_app

        result = celery_app.send_task(
            task_name,
            args=args,
            kwargs=kwargs or {},
            priority=priority,
            countdown=countdown,
        )
        return TaskHandle(task_id=result.id, queue_name="celery", priority=priority)

    async def get(self, task_id: str) -> TaskRecord:
        """Retrieve current state of a previously enqueued task."""
        from celery.result import AsyncResult

        result = AsyncResult(task_id)
        status = result.state.lower()  # PENDING/STARTED/SUCCESS/FAILURE/REVOKED
        return TaskRecord(
            task_id=task_id,
            status=status,
            result=result.result if result.successful() else None,
            error=str(result.result) if result.failed() else None,
        )


# ---------------------------------------------------------------------------
# ProgressTracker facade
# ---------------------------------------------------------------------------


class ProgressTracker:
    """
    Single progress-reporting path for long-running operations.

    Backed by Redis (main DB).  Canonical callers: task_execution_tracker.py.
    Legacy: utils/long_running_operations/progress_tracker.py (in-memory only)
    and enhanced_memory_manager_async.py ExecutionRecord (Redis + DB).
    """

    def __init__(self) -> None:
        """Initialize progress tracker."""
        self._prefix = "async_work:progress:"

    async def report(
        self,
        task_id: str,
        percent: float,
        current_step: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Write progress for a task_id to Redis."""
        import json

        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("ProgressTracker: Redis unavailable, progress not stored")
            return

        payload = {
            "task_id": task_id,
            "percent": percent,
            "current_step": current_step,
            "metadata": metadata or {},
        }
        await redis.setex(
            f"{self._prefix}{task_id}",
            3600,
            json.dumps(payload),
        )

    async def get(self, task_id: str) -> Progress | None:
        """Read last progress snapshot for a task_id from Redis."""
        import json

        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client()
        if redis is None:
            return None

        raw = await redis.get(f"{self._prefix}{task_id}")
        if not raw:
            return None

        data = json.loads(raw)
        return Progress(
            task_id=task_id,
            percent=data.get("percent", 0.0),
            current_step=data.get("current_step"),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# PeriodicScheduler facade
# ---------------------------------------------------------------------------


class PeriodicScheduler:
    """
    Single interface for registering recurring jobs.

    Celery Beat is the authoritative cron source.  Legacy schedulers that
    still run: services/scheduling/cron_scheduler.py (basic 5-field cron)
    and knowledge/connectors/scheduler.py (asyncio interval).
    Migration plan: add registrations here → delete legacy files.

    Note: ``services/heartbeat_scheduler.py`` is NOT a cron scheduler —
    it handles event-driven wakeups and should NOT be migrated here.
    """

    def schedule(
        self,
        name: str,
        cron_expr_or_interval: str,
        callback: Callable,
    ) -> None:
        """
        Register a periodic job with Celery Beat at runtime.

        For static schedules, prefer adding entries to
        ``celery_app.conf.beat_schedule`` in ``celery_app.py``.

        Args:
            name: Unique job name (used as Celery Beat entry key)
            cron_expr_or_interval: Cron expression (``"0 2 * * *"``) or
                interval string (``"@hourly"``, ``"*/15"``)
            callback: Zero-arg callable; will be wrapped as a Celery task
        """

        from celery_app import celery_app

        schedule = self._parse_schedule(cron_expr_or_interval)
        celery_app.conf.beat_schedule[name] = {
            "task": f"async_work.dynamic.{name}",
            "schedule": schedule,
        }
        logger.info("PeriodicScheduler: registered %s (%s)", name, cron_expr_or_interval)

    def cancel(self, name: str) -> None:
        """Remove a previously registered periodic job."""
        from celery_app import celery_app

        celery_app.conf.beat_schedule.pop(name, None)
        logger.info("PeriodicScheduler: cancelled %s", name)

    def _parse_schedule(self, expr: str):
        """Convert cron expression or interval shorthand to Celery schedule object."""
        from celery.schedules import crontab

        aliases = {
            "@hourly": "0 * * * *",
            "@daily": "0 0 * * *",
            "@weekly": "0 0 * * 0",
        }
        expr = aliases.get(expr, expr)

        parts = expr.split()
        if len(parts) == 5:
            minute, hour, day_of_month, month, day_of_week = parts
            return crontab(
                minute=minute,
                hour=hour,
                day_of_month=day_of_month,
                month_of_year=month,
                day_of_week=day_of_week,
            )
        # Assume interval in minutes for "*/N" patterns
        if expr.startswith("*/"):
            from celery.schedules import timedelta

            return timedelta(minutes=int(expr[2:]))
        raise ValueError(f"Unrecognised schedule expression: {expr!r}")


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

get_task_queue: Callable[[], TaskQueue] = lazy_singleton(TaskQueue)
get_progress_tracker: Callable[[], ProgressTracker] = lazy_singleton(ProgressTracker)
get_periodic_scheduler: Callable[[], PeriodicScheduler] = lazy_singleton(PeriodicScheduler)

__all__ = [
    "TaskHandle",
    "TaskRecord",
    "Progress",
    "TaskQueue",
    "ProgressTracker",
    "PeriodicScheduler",
    "get_task_queue",
    "get_progress_tracker",
    "get_periodic_scheduler",
]
