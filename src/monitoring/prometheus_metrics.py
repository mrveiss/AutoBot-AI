# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prometheus Metrics Manager for AutoBot

Provides centralized metrics collection and exposure.

Refactoring History:
- Issue #394: Extracted domain-specific metrics to separate recorder classes
  in src/monitoring/metrics/ package to reduce god class from 46 to 16 methods.
  Domain recorders: WorkflowMetricsRecorder, GitHubMetricsRecorder,
  TaskMetricsRecorder, SystemMetricsRecorder, ClaudeAPIMetricsRecorder,
  ServiceHealthMetricsRecorder
"""

import threading
from typing import Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Issue #394: Import domain-specific recorder classes
from .metrics import (
    WorkflowMetricsRecorder,
    GitHubMetricsRecorder,
    TaskMetricsRecorder,
    SystemMetricsRecorder,
    ClaudeAPIMetricsRecorder,
    ServiceHealthMetricsRecorder,
)

# Issue #380: Module-level dicts for state value mapping (avoid repeated dict creation)
_CIRCUIT_BREAKER_STATE_VALUES = {"closed": 0, "open": 1, "half_open": 2}


class PrometheusMetricsManager:
    """
    Centralized Prometheus metrics manager.

    Issue #394: Refactored from 46 methods to 16 methods (65% reduction) by
    extracting domain-specific metrics to separate recorder classes.

    This class now handles only core infrastructure metrics:
    - Timeout tracking
    - Latency histograms
    - Connection pool metrics
    - Circuit breaker metrics
    - Request success/failure
    - Error tracking

    Domain-specific metrics are delegated to:
    - WorkflowMetricsRecorder: Workflow execution metrics
    - GitHubMetricsRecorder: GitHub API operation metrics
    - TaskMetricsRecorder: Task execution metrics
    - SystemMetricsRecorder: System resource metrics
    - ClaudeAPIMetricsRecorder: Claude API metrics
    - ServiceHealthMetricsRecorder: Service health metrics
    """

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """Initialize Prometheus metrics manager with optional registry."""
        self.registry = registry or CollectorRegistry()

        # Initialize core infrastructure metrics
        self._init_timeout_metrics()
        self._init_latency_metrics()
        self._init_connection_metrics()
        self._init_circuit_breaker_metrics()
        self._init_request_metrics()
        self._init_error_metrics()

        # Issue #394: Initialize domain-specific recorders
        self._workflow = WorkflowMetricsRecorder(self.registry)
        self._github = GitHubMetricsRecorder(self.registry)
        self._task = TaskMetricsRecorder(self.registry)
        self._system = SystemMetricsRecorder(self.registry)
        self._claude_api = ClaudeAPIMetricsRecorder(self.registry)
        self._service_health = ServiceHealthMetricsRecorder(self.registry)

    # =========================================================================
    # Core Infrastructure Metrics Initialization
    # =========================================================================

    def _init_timeout_metrics(self) -> None:
        """Initialize timeout-related metrics."""
        self.timeout_total = Counter(
            "autobot_timeout_total",
            "Total number of timeout events",
            ["operation_type", "database", "status"],
            registry=self.registry,
        )

    def _init_latency_metrics(self) -> None:
        """Initialize latency histogram metrics."""
        # Custom buckets optimized for our timeout ranges
        buckets = [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]

        self.operation_duration = Histogram(
            "autobot_operation_duration_seconds",
            "Duration of operations in seconds",
            ["operation_type", "database"],
            buckets=buckets,
            registry=self.registry,
        )

        self.timeout_rate = Gauge(
            "autobot_timeout_rate",
            "Percentage of operations timing out",
            ["operation_type", "database", "time_window"],
            registry=self.registry,
        )

    def _init_connection_metrics(self) -> None:
        """Initialize Redis connection pool metrics."""
        self.pool_connections = Gauge(
            "autobot_redis_pool_connections",
            "Redis connection pool connections",
            ["database", "state"],
            registry=self.registry,
        )

        self.pool_saturation = Gauge(
            "autobot_redis_pool_saturation_ratio",
            "Redis connection pool saturation ratio",
            ["database"],
            registry=self.registry,
        )

    def _init_circuit_breaker_metrics(self) -> None:
        """Initialize circuit breaker metrics."""
        self.circuit_breaker_events = Counter(
            "autobot_circuit_breaker_events_total",
            "Total circuit breaker events",
            ["database", "event", "reason"],
            registry=self.registry,
        )

        self.circuit_breaker_state = Gauge(
            "autobot_circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=open, 2=half_open)",
            ["database"],
            registry=self.registry,
        )

        self.circuit_breaker_failures = Gauge(
            "autobot_circuit_breaker_failure_count",
            "Number of failures before circuit opens",
            ["database"],
            registry=self.registry,
        )

    def _init_request_metrics(self) -> None:
        """Initialize request success/failure metrics."""
        self.requests_total = Counter(
            "autobot_redis_requests_total",
            "Total Redis requests",
            ["database", "operation", "status"],
            registry=self.registry,
        )

        self.success_rate = Gauge(
            "autobot_redis_success_rate",
            "Redis operation success rate percentage",
            ["database", "time_window"],
            registry=self.registry,
        )

    def _init_error_metrics(self) -> None:
        """Initialize error tracking metrics."""
        self.errors_total = Counter(
            "autobot_errors_total",
            "Total errors by category, component, and error code",
            ["category", "component", "error_code"],
            registry=self.registry,
        )

        self.error_rate = Gauge(
            "autobot_error_rate",
            "Error rate per component and time window",
            ["component", "time_window"],
            registry=self.registry,
        )

    # =========================================================================
    # Core Infrastructure Metric Recording Methods
    # =========================================================================

    def record_timeout(self, operation_type: str, database: str, timed_out: bool) -> None:
        """Record a timeout event."""
        status = "timeout" if timed_out else "success"
        self.timeout_total.labels(
            operation_type=operation_type, database=database, status=status
        ).inc()

    def record_operation_duration(
        self, operation_type: str, database: str, duration: float
    ) -> None:
        """Record operation duration."""
        self.operation_duration.labels(
            operation_type=operation_type, database=database
        ).observe(duration)

    def record_circuit_breaker_event(
        self, database: str, event: str, reason: str
    ) -> None:
        """Record circuit breaker state change."""
        self.circuit_breaker_events.labels(
            database=database, event=event, reason=reason
        ).inc()

    def update_circuit_breaker_state(
        self, database: str, state: str, failure_count: int
    ) -> None:
        """Update circuit breaker state gauge."""
        state_value = _CIRCUIT_BREAKER_STATE_VALUES.get(state, 0)
        self.circuit_breaker_state.labels(database=database).set(state_value)
        self.circuit_breaker_failures.labels(database=database).set(failure_count)

    def update_connection_pool(
        self, database: str, active: int, idle: int, max_connections: int
    ) -> None:
        """Update connection pool metrics."""
        self.pool_connections.labels(database=database, state="active").set(active)
        self.pool_connections.labels(database=database, state="idle").set(idle)
        self.pool_connections.labels(database=database, state="total").set(
            max_connections
        )

        # Calculate saturation ratio
        saturation = active / max_connections if max_connections > 0 else 0
        self.pool_saturation.labels(database=database).set(saturation)

    def record_request(self, database: str, operation: str, success: bool) -> None:
        """Record a request success or failure."""
        status = "success" if success else "failure"
        self.requests_total.labels(
            database=database, operation=operation, status=status
        ).inc()

    def record_error(
        self, category: str, component: str, error_code: str = "unknown"
    ) -> None:
        """Record an error occurrence."""
        self.errors_total.labels(
            category=category, component=component, error_code=error_code
        ).inc()

    def update_error_rate(self, component: str, time_window: str, rate: float) -> None:
        """Update error rate for a component."""
        self.error_rate.labels(component=component, time_window=time_window).set(rate)

    # =========================================================================
    # Workflow Metrics (Issue #394: Delegates to WorkflowMetricsRecorder)
    # =========================================================================

    def record_workflow_execution(
        self, workflow_type: str, status: str, duration: float = None
    ) -> None:
        """Record a workflow execution."""
        self._workflow.record_execution(workflow_type, status, duration)

    def record_workflow_step(
        self, workflow_type: str, step_type: str, status: str
    ) -> None:
        """Record a workflow step execution."""
        self._workflow.record_step(workflow_type, step_type, status)

    def update_active_workflows(self, workflow_type: str, count: int) -> None:
        """Update active workflows count."""
        self._workflow.update_active_count(workflow_type, count)

    def record_workflow_approval(self, workflow_type: str, decision: str) -> None:
        """Record a workflow approval decision."""
        self._workflow.record_approval(workflow_type, decision)

    # =========================================================================
    # GitHub Metrics (Issue #394: Delegates to GitHubMetricsRecorder)
    # =========================================================================

    def record_github_operation(
        self, operation: str, status: str, duration: float = None
    ) -> None:
        """Record a GitHub API operation."""
        self._github.record_operation(operation, status, duration)

    def update_github_rate_limit(self, resource_type: str, remaining: int) -> None:
        """Update GitHub rate limit remaining."""
        self._github.update_rate_limit(resource_type, remaining)

    def record_github_commit(self, repository: str, status: str) -> None:
        """Record a GitHub commit."""
        self._github.record_commit(repository, status)

    def record_github_pull_request(
        self, repository: str, action: str, status: str
    ) -> None:
        """Record a GitHub pull request operation."""
        self._github.record_pull_request(repository, action, status)

    def record_github_issue(self, repository: str, action: str, status: str) -> None:
        """Record a GitHub issue operation."""
        self._github.record_issue(repository, action, status)

    # =========================================================================
    # Task Metrics (Issue #394: Delegates to TaskMetricsRecorder)
    # =========================================================================

    def record_task_execution(
        self,
        task_type: str,
        agent_type: str,
        status: str,
        duration: float = None,
    ) -> None:
        """Record a task execution."""
        self._task.record_execution(task_type, agent_type, status, duration)

    def update_active_tasks(self, task_type: str, agent_type: str, count: int) -> None:
        """Update active tasks count."""
        self._task.update_active_count(task_type, agent_type, count)

    def update_task_queue_size(self, priority: str, size: int) -> None:
        """Update task queue size."""
        self._task.update_queue_size(priority, size)

    def record_task_retry(self, task_type: str, reason: str) -> None:
        """Record a task retry attempt."""
        self._task.record_retry(task_type, reason)

    # =========================================================================
    # System Metrics (Issue #394: Delegates to SystemMetricsRecorder)
    # =========================================================================

    def update_system_cpu(self, cpu_percent: float) -> None:
        """Update CPU usage metric."""
        self._system.update_cpu(cpu_percent)

    def update_system_memory(self, memory_percent: float) -> None:
        """Update memory usage metric."""
        self._system.update_memory(memory_percent)

    def update_system_disk(self, mount_point: str, disk_percent: float) -> None:
        """Update disk usage metric."""
        self._system.update_disk(mount_point, disk_percent)

    def record_network_bytes(self, direction: str, bytes_count: int) -> None:
        """Record network bytes transferred."""
        self._system.record_network_bytes(direction, bytes_count)

    # =========================================================================
    # Claude API Metrics (Issue #394: Delegates to ClaudeAPIMetricsRecorder)
    # =========================================================================

    def record_claude_api_request(self, tool_name: str, success: bool) -> None:
        """Record a Claude API request."""
        self._claude_api.record_request(tool_name, success)

    def record_claude_api_payload(self, payload_bytes: int) -> None:
        """Record Claude API payload size."""
        self._claude_api.record_payload(payload_bytes)

    def record_claude_api_response_time(self, response_time_seconds: float) -> None:
        """Record Claude API response time."""
        self._claude_api.record_response_time(response_time_seconds)

    def update_claude_api_rate_limit(self, remaining: int) -> None:
        """Update Claude API rate limit remaining."""
        self._claude_api.update_rate_limit(remaining)

    # =========================================================================
    # Service Health Metrics (Issue #394: Delegates to ServiceHealthMetricsRecorder)
    # =========================================================================

    def update_service_health(self, service_name: str, health_score: float) -> None:
        """Update service health score."""
        self._service_health.update_health(service_name, health_score)

    def record_service_response_time(
        self, service_name: str, response_time: float
    ) -> None:
        """Record service response time."""
        self._service_health.record_response_time(service_name, response_time)

    def update_service_status(self, service_name: str, status: str) -> None:
        """Update service status."""
        self._service_health.update_status(service_name, status)

    # =========================================================================
    # Metrics Export
    # =========================================================================

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format."""
        return generate_latest(self.registry)


# =============================================================================
# Global Metrics Instance (Thread-safe Singleton)
# =============================================================================

_metrics_instance: Optional[PrometheusMetricsManager] = None
_metrics_instance_lock = threading.Lock()


def get_metrics_manager() -> PrometheusMetricsManager:
    """Get or create global metrics manager (thread-safe)."""
    global _metrics_instance
    if _metrics_instance is None:
        with _metrics_instance_lock:
            # Double-check after acquiring lock
            if _metrics_instance is None:
                _metrics_instance = PrometheusMetricsManager()
    return _metrics_instance


__all__ = ["PrometheusMetricsManager", "get_metrics_manager"]
