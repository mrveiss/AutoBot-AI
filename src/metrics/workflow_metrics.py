# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Performance Metrics and Monitoring System
Provides comprehensive tracking and analysis of workflow execution performance

DEPRECATED (Phase 2, Issue #345): This module is redundant with PrometheusMetricsManager.
All workflow metrics are now tracked in src/monitoring/prometheus_metrics.py.
This module will be REMOVED in Phase 5.

Use PrometheusMetricsManager instead:
    from src.monitoring.prometheus_metrics import get_metrics_manager
    metrics = get_metrics_manager()
    metrics.record_workflow_execution(workflow_type, status, duration)
    metrics.record_workflow_step(workflow_type, step_type, status)
    metrics.update_active_workflows(workflow_type, count)
"""

import warnings

warnings.warn(
    "workflow_metrics module is deprecated and will be removed in Phase 5. "
    "Use PrometheusMetricsManager at src/monitoring/prometheus_metrics.py instead.",
    DeprecationWarning,
    stacklevel=2,
)

import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for numeric type checks
_NUMERIC_TYPES = (int, float)


class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class WorkflowMetric:
    """Individual workflow metric data point"""

    workflow_id: str
    metric_type: str
    metric_name: str
    value: float
    timestamp: datetime
    labels: Dict[str, str]
    metadata: Dict[str, Any]


@dataclass
class WorkflowExecutionStats:
    """Complete workflow execution statistics"""

    workflow_id: str
    user_message: str
    complexity: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    agents_involved: List[str]
    start_time: datetime
    end_time: Optional[datetime]
    total_duration_ms: Optional[float]
    avg_step_duration_ms: float
    step_timings: Dict[str, float]
    approval_wait_time_ms: float
    error_count: int
    success_rate: float
    resource_usage: Dict[str, Any]
    status: str


class WorkflowMetricsCollector:
    """Collects and aggregates workflow performance metrics"""

    def __init__(self, max_history: int = 10000):
        """Initialize workflow metrics collector with history buffer and aggregation."""
        self.max_history = max_history
        self.metrics_history: deque = deque(maxlen=max_history)
        self.active_workflows: Dict[str, Dict[str, Any]] = {}
        self.step_timers: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.aggregated_stats = {
            "total_workflows": 0,
            "successful_workflows": 0,
            "failed_workflows": 0,
            "avg_duration_ms": 0.0,
            "complexity_distribution": defaultdict(int),
            "agent_usage_count": defaultdict(int),
            "error_types": defaultdict(int),
            "performance_trends": [],
        }

    def start_workflow_tracking(self, workflow_id: str, workflow_data: Dict[str, Any]):
        """Begin tracking a new workflow"""
        try:
            self.active_workflows[workflow_id] = {
                "workflow_id": workflow_id,
                "user_message": workflow_data.get("user_message", ""),
                "complexity": workflow_data.get("complexity", "unknown"),
                "total_steps": workflow_data.get("total_steps", 0),
                "agents_involved": workflow_data.get("agents_involved", []),
                "start_time": datetime.now(),
                "completed_steps": 0,
                "failed_steps": 0,
                "step_timings": {},
                "approval_wait_times": [],
                "errors": [],
                "resource_snapshots": [],
                "status": "running",
            }

            # Record workflow start metric
            self._record_metric(
                workflow_id=workflow_id,
                metric_type=MetricType.COUNTER.value,
                metric_name="workflow_started",
                value=1,
                labels={
                    "complexity": workflow_data.get("complexity", "unknown"),
                    "agent_count": str(len(workflow_data.get("agents_involved", []))),
                    "step_count": str(workflow_data.get("total_steps", 0)),
                },
            )

            logger.info("Started tracking workflow %s", workflow_id)

        except Exception as e:
            logger.error("Failed to start workflow tracking: %s", e)

    def start_step_timing(self, workflow_id: str, step_id: str, agent_type: str):
        """Start timing a workflow step"""
        try:
            if workflow_id not in self.step_timers:
                self.step_timers[workflow_id] = {}

            self.step_timers[workflow_id][step_id] = {
                "start_time": time.time(),
                "agent_type": agent_type,
            }

        except Exception as e:
            logger.error("Failed to start step timing: %s", e)

    def _update_workflow_step_tracking(
        self,
        workflow_id: str,
        step_id: str,
        duration_ms: float,
        success: bool,
        error: str,
    ) -> None:
        """Update workflow tracking with step completion data. Issue #620."""
        if workflow_id not in self.active_workflows:
            return
        workflow = self.active_workflows[workflow_id]
        workflow["step_timings"][step_id] = duration_ms
        if success:
            workflow["completed_steps"] += 1
        else:
            workflow["failed_steps"] += 1
            if error:
                workflow["errors"].append(
                    {
                        "step_id": step_id,
                        "error": error,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

    def end_step_timing(
        self, workflow_id: str, step_id: str, success: bool = True, error: str = None
    ):
        """End timing a workflow step and record metrics. Issue #620."""
        try:
            if (
                workflow_id not in self.step_timers
                or step_id not in self.step_timers[workflow_id]
            ):
                logger.warning(
                    f"No timer found for step {step_id} in workflow {workflow_id}"
                )
                return

            step_data = self.step_timers[workflow_id][step_id]
            duration_ms = (time.time() - step_data["start_time"]) * 1000

            self._update_workflow_step_tracking(
                workflow_id, step_id, duration_ms, success, error
            )
            self._record_metric(
                workflow_id=workflow_id,
                metric_type=MetricType.TIMER.value,
                metric_name="step_duration_ms",
                value=duration_ms,
                labels={
                    "step_id": step_id,
                    "agent_type": step_data["agent_type"],
                    "success": str(success),
                },
            )
            del self.step_timers[workflow_id][step_id]

        except Exception as e:
            logger.error("Failed to end step timing: %s", e)

    def record_approval_wait_time(self, workflow_id: str, wait_time_ms: float):
        """Record time spent waiting for user approval"""
        try:
            if workflow_id in self.active_workflows:
                self.active_workflows[workflow_id]["approval_wait_times"].append(
                    wait_time_ms
                )

            self._record_metric(
                workflow_id=workflow_id,
                metric_type=MetricType.TIMER.value,
                metric_name="approval_wait_time_ms",
                value=wait_time_ms,
                labels={"workflow_id": workflow_id},
            )

        except Exception as e:
            logger.error("Failed to record approval wait time: %s", e)

    def record_resource_usage(self, workflow_id: str, resource_data: Dict[str, Any]):
        """Record resource usage snapshot during workflow execution"""
        try:
            if workflow_id in self.active_workflows:
                resource_snapshot = {
                    "timestamp": datetime.now().isoformat(),
                    "cpu_percent": resource_data.get("cpu_percent", 0),
                    "memory_mb": resource_data.get("memory_mb", 0),
                    "disk_io": resource_data.get("disk_io", {}),
                    "network_io": resource_data.get("network_io", {}),
                }
                self.active_workflows[workflow_id]["resource_snapshots"].append(
                    resource_snapshot
                )

            # Record resource metrics
            for metric_name, value in resource_data.items():
                if isinstance(value, _NUMERIC_TYPES):  # Issue #380
                    self._record_metric(
                        workflow_id=workflow_id,
                        metric_type=MetricType.GAUGE.value,
                        metric_name=f"resource_{metric_name}",
                        value=float(value),
                        labels={"workflow_id": workflow_id},
                    )

        except Exception as e:
            logger.error("Failed to record resource usage: %s", e)

    def _build_workflow_stats(
        self,
        workflow_id: str,
        workflow: Dict[str, Any],
        end_time: datetime,
        final_status: str,
    ) -> WorkflowExecutionStats:
        """Build workflow execution stats (Issue #665: extracted helper).

        Args:
            workflow_id: Workflow identifier
            workflow: Workflow data dict
            end_time: Workflow end timestamp
            final_status: Final status string

        Returns:
            WorkflowExecutionStats instance
        """
        total_duration_ms = (end_time - workflow["start_time"]).total_seconds() * 1000
        step_durations = list(workflow["step_timings"].values())
        avg_step_duration = (
            sum(step_durations) / len(step_durations) if step_durations else 0
        )
        total_approval_wait = (
            sum(workflow["approval_wait_times"])
            if workflow["approval_wait_times"]
            else 0
        )
        success_rate = (
            workflow["completed_steps"]
            / max(workflow["completed_steps"] + workflow["failed_steps"], 1)
        ) * 100

        return WorkflowExecutionStats(
            workflow_id=workflow_id,
            user_message=workflow["user_message"],
            complexity=workflow["complexity"],
            total_steps=workflow["total_steps"],
            completed_steps=workflow["completed_steps"],
            failed_steps=workflow["failed_steps"],
            agents_involved=workflow["agents_involved"],
            start_time=workflow["start_time"],
            end_time=end_time,
            total_duration_ms=total_duration_ms,
            avg_step_duration_ms=avg_step_duration,
            step_timings=workflow["step_timings"],
            approval_wait_time_ms=total_approval_wait,
            error_count=len(workflow["errors"]),
            success_rate=success_rate,
            resource_usage=self._aggregate_resource_usage(
                workflow["resource_snapshots"]
            ),
            status=final_status,
        )

    def end_workflow_tracking(self, workflow_id: str, final_status: str):
        """Complete workflow tracking and generate final statistics.

        Issue #665: Refactored to use _build_workflow_stats helper.
        """
        try:
            if workflow_id not in self.active_workflows:
                logger.warning("No active workflow found: %s", workflow_id)
                return None

            workflow = self.active_workflows[workflow_id]
            end_time = datetime.now()

            # Build stats using helper
            stats = self._build_workflow_stats(
                workflow_id, workflow, end_time, final_status
            )

            # Record final metrics
            self._record_metric(
                workflow_id=workflow_id,
                metric_type=MetricType.TIMER.value,
                metric_name="workflow_total_duration_ms",
                value=stats.total_duration_ms,
                labels={
                    "complexity": workflow["complexity"],
                    "status": final_status,
                    "step_count": str(workflow["total_steps"]),
                },
            )
            self._record_metric(
                workflow_id=workflow_id,
                metric_type=MetricType.GAUGE.value,
                metric_name="workflow_success_rate",
                value=stats.success_rate,
                labels={
                    "complexity": workflow["complexity"],
                    "workflow_id": workflow_id,
                },
            )

            self._update_aggregated_stats(stats)
            del self.active_workflows[workflow_id]

            logger.info("Completed tracking workflow %s: %s", workflow_id, final_status)
            return stats

        except Exception as e:
            logger.error("Failed to end workflow tracking: %s", e)
            return None

    def _record_metric(
        self,
        workflow_id: str,
        metric_type: str,
        metric_name: str,
        value: float,
        labels: Dict[str, str] = None,
        metadata: Dict[str, Any] = None,
    ):
        """Record a single metric data point"""
        try:
            metric = WorkflowMetric(
                workflow_id=workflow_id,
                metric_type=metric_type,
                metric_name=metric_name,
                value=value,
                timestamp=datetime.now(),
                labels=labels or {},
                metadata=metadata or {},
            )

            self.metrics_history.append(metric)

        except Exception as e:
            logger.error("Failed to record metric: %s", e)

    def _aggregate_resource_usage(
        self, snapshots: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Aggregate resource usage from snapshots"""
        if not snapshots:
            return {}

        try:
            cpu_values = [s.get("cpu_percent", 0) for s in snapshots]
            memory_values = [s.get("memory_mb", 0) for s in snapshots]

            return {
                "avg_cpu_percent": (
                    sum(cpu_values) / len(cpu_values) if cpu_values else 0
                ),
                "max_cpu_percent": max(cpu_values) if cpu_values else 0,
                "avg_memory_mb": (
                    sum(memory_values) / len(memory_values) if memory_values else 0
                ),
                "max_memory_mb": max(memory_values) if memory_values else 0,
                "snapshot_count": len(snapshots),
            }
        except Exception as e:
            logger.error("Failed to aggregate resource usage: %s", e)
            return {}

    def _update_aggregated_stats(self, stats: WorkflowExecutionStats):
        """Update aggregated performance statistics"""
        try:
            self.aggregated_stats["total_workflows"] += 1

            if stats.status == "completed":
                self.aggregated_stats["successful_workflows"] += 1
            else:
                self.aggregated_stats["failed_workflows"] += 1

            # Update average duration
            total_duration = (
                self.aggregated_stats["avg_duration_ms"]
                * (self.aggregated_stats["total_workflows"] - 1)
                + stats.total_duration_ms
            )
            self.aggregated_stats["avg_duration_ms"] = (
                total_duration / self.aggregated_stats["total_workflows"]
            )

            # Update complexity distribution
            self.aggregated_stats["complexity_distribution"][stats.complexity] += 1

            # Update agent usage
            for agent in stats.agents_involved:
                self.aggregated_stats["agent_usage_count"][agent] += 1

            # Track performance trends (last 100 workflows)
            trend_data = {
                "timestamp": stats.end_time.isoformat() if stats.end_time else None,
                "duration_ms": stats.total_duration_ms,
                "success_rate": stats.success_rate,
                "complexity": stats.complexity,
            }

            self.aggregated_stats["performance_trends"].append(trend_data)
            if len(self.aggregated_stats["performance_trends"]) > 100:
                self.aggregated_stats["performance_trends"].pop(0)

        except Exception as e:
            logger.error("Failed to update aggregated stats: %s", e)

    def get_workflow_stats(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific workflow"""
        try:
            # Check if workflow is still active
            if workflow_id in self.active_workflows:
                workflow = self.active_workflows[workflow_id]
                current_duration = (
                    datetime.now() - workflow["start_time"]
                ).total_seconds() * 1000

                return {
                    "workflow_id": workflow_id,
                    "status": "running",
                    "current_duration_ms": current_duration,
                    "completed_steps": workflow["completed_steps"],
                    "total_steps": workflow["total_steps"],
                    "progress_percent": (
                        (workflow["completed_steps"] / max(workflow["total_steps"], 1))
                        * 100
                    ),
                    "current_step_timings": workflow["step_timings"],
                }

            # Search completed workflows in history
            workflow_metrics = [
                m for m in self.metrics_history if m.workflow_id == workflow_id
            ]
            if workflow_metrics:
                duration_metrics = [
                    m
                    for m in workflow_metrics
                    if m.metric_name == "workflow_total_duration_ms"
                ]
                if duration_metrics:
                    return {
                        "workflow_id": workflow_id,
                        "status": "completed",
                        "total_duration_ms": duration_metrics[0].value,
                        "labels": duration_metrics[0].labels,
                    }

            return None

        except Exception as e:
            logger.error("Failed to get workflow stats: %s", e)
            return None

    def get_performance_summary(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """Get overall performance summary for specified time window"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=time_window_hours)
            recent_metrics = [
                m for m in self.metrics_history if m.timestamp >= cutoff_time
            ]

            # Calculate summary statistics
            workflow_completions = [
                m
                for m in recent_metrics
                if m.metric_name == "workflow_total_duration_ms"
            ]

            if not workflow_completions:
                return {
                    "message": "No completed workflows in time window",
                    "time_window_hours": time_window_hours,
                }

            durations = [m.value for m in workflow_completions]
            success_rates = [
                m.value
                for m in recent_metrics
                if m.metric_name == "workflow_success_rate"
            ]

            complexity_counts = defaultdict(int)
            for metric in workflow_completions:
                complexity_counts[metric.labels.get("complexity", "unknown")] += 1

            return {
                "time_window_hours": time_window_hours,
                "total_workflows": len(workflow_completions),
                "avg_duration_ms": sum(durations) / len(durations),
                "min_duration_ms": min(durations),
                "max_duration_ms": max(durations),
                "avg_success_rate": (
                    sum(success_rates) / len(success_rates) if success_rates else 0
                ),
                "complexity_distribution": dict(complexity_counts),
                "metrics_collected": len(recent_metrics),
                "active_workflows": len(self.active_workflows),
            }

        except Exception as e:
            logger.error("Failed to get performance summary: %s", e)
            return {"error": str(e)}

    def export_metrics(self, format: str = "json") -> str:
        """Export metrics in specified format"""
        try:
            if format.lower() == "json":
                export_data = {
                    "aggregated_stats": dict(self.aggregated_stats),
                    "active_workflows": len(self.active_workflows),
                    "total_metrics": len(self.metrics_history),
                    "export_timestamp": datetime.now().isoformat(),
                }
                return json.dumps(export_data, indent=2, default=str)
            else:
                return f"Unsupported export format: {format}"

        except Exception as e:
            logger.error("Failed to export metrics: %s", e)
            return f"Export failed: {str(e)}"


# Global metrics collector instance
workflow_metrics = WorkflowMetricsCollector()
