# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Metrics Recorder

Metrics for workflow execution tracking.
Extracted from PrometheusMetricsManager as part of Issue #394.
"""

from typing import Optional

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class WorkflowMetricsRecorder(BaseMetricsRecorder):
    """Recorder for workflow execution metrics."""

    def _init_metrics(self) -> None:
        """Initialize workflow metrics."""
        self.workflow_executions_total = Counter(
            "autobot_workflow_executions_total",
            "Total workflow executions",
            ["workflow_type", "status"],
            registry=self.registry,
        )

        self.workflow_duration = Histogram(
            "autobot_workflow_duration_seconds",
            "Workflow execution duration in seconds",
            ["workflow_type"],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
            registry=self.registry,
        )

        self.workflow_steps_executed = Counter(
            "autobot_workflow_steps_executed_total",
            "Total workflow steps executed",
            ["workflow_type", "step_type", "status"],
            registry=self.registry,
        )

        self.active_workflows = Gauge(
            "autobot_active_workflows",
            "Number of currently active workflows",
            ["workflow_type"],
            registry=self.registry,
        )

        self.workflow_approvals = Counter(
            "autobot_workflow_approvals_total",
            "Total workflow approval requests",
            ["workflow_type", "decision"],
            registry=self.registry,
        )

    def record_execution(
        self, workflow_type: str, status: str, duration: Optional[float] = None
    ) -> None:
        """Record a workflow execution."""
        self.workflow_executions_total.labels(
            workflow_type=workflow_type, status=status
        ).inc()
        if duration is not None:
            self.workflow_duration.labels(workflow_type=workflow_type).observe(duration)

    def record_step(self, workflow_type: str, step_type: str, status: str) -> None:
        """Record a workflow step execution."""
        self.workflow_steps_executed.labels(
            workflow_type=workflow_type, step_type=step_type, status=status
        ).inc()

    def update_active_count(self, workflow_type: str, count: int) -> None:
        """Update active workflows count."""
        self.active_workflows.labels(workflow_type=workflow_type).set(count)

    def record_approval(self, workflow_type: str, decision: str) -> None:
        """Record a workflow approval decision."""
        self.workflow_approvals.labels(
            workflow_type=workflow_type, decision=decision
        ).inc()


__all__ = ["WorkflowMetricsRecorder"]
