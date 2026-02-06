# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Metrics Recorder

Metrics for task execution tracking.
Extracted from PrometheusMetricsManager as part of Issue #394.
"""

from typing import Optional

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class TaskMetricsRecorder(BaseMetricsRecorder):
    """Recorder for task execution metrics."""

    def _init_metrics(self) -> None:
        """Initialize task metrics."""
        self.tasks_executed_total = Counter(
            "autobot_tasks_executed_total",
            "Total tasks executed",
            ["task_type", "agent_type", "status"],
            registry=self.registry,
        )

        self.task_duration = Histogram(
            "autobot_task_duration_seconds",
            "Task execution duration in seconds",
            ["task_type", "agent_type"],
            buckets=[1.0, 5.0, 15.0, 30.0, 60.0, 180.0, 300.0, 600.0],
            registry=self.registry,
        )

        self.active_tasks = Gauge(
            "autobot_active_tasks",
            "Number of currently active tasks",
            ["task_type", "agent_type"],
            registry=self.registry,
        )

        self.task_queue_size = Gauge(
            "autobot_task_queue_size",
            "Number of tasks in queue",
            ["priority"],
            registry=self.registry,
        )

        self.task_retries = Counter(
            "autobot_task_retries_total",
            "Total task retry attempts",
            ["task_type", "reason"],
            registry=self.registry,
        )

    def record_execution(
        self,
        task_type: str,
        agent_type: str,
        status: str,
        duration: Optional[float] = None,
    ) -> None:
        """Record a task execution."""
        self.tasks_executed_total.labels(
            task_type=task_type, agent_type=agent_type, status=status
        ).inc()
        if duration is not None:
            self.task_duration.labels(
                task_type=task_type, agent_type=agent_type
            ).observe(duration)

    def update_active_count(self, task_type: str, agent_type: str, count: int) -> None:
        """Update active tasks count."""
        self.active_tasks.labels(task_type=task_type, agent_type=agent_type).set(count)

    def update_queue_size(self, priority: str, size: int) -> None:
        """Update task queue size."""
        self.task_queue_size.labels(priority=priority).set(size)

    def record_retry(self, task_type: str, reason: str) -> None:
        """Record a task retry attempt."""
        self.task_retries.labels(task_type=task_type, reason=reason).inc()


__all__ = ["TaskMetricsRecorder"]
