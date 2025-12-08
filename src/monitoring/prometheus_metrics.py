# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prometheus Metrics Manager for AutoBot
Provides centralized metrics collection and exposure.
"""

from typing import Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


class PrometheusMetricsManager:
    """Centralized Prometheus metrics manager"""

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """Initialize Prometheus metrics manager with optional registry."""
        self.registry = registry or CollectorRegistry()

        # Initialize all metrics
        self._init_timeout_metrics()
        self._init_latency_metrics()
        self._init_connection_metrics()
        self._init_circuit_breaker_metrics()
        self._init_request_metrics()
        self._init_workflow_metrics()
        self._init_github_metrics()
        self._init_task_metrics()
        # Phase 1: New metrics (Issue #344)
        self._init_system_metrics()
        self._init_error_metrics()
        self._init_claude_api_metrics()
        self._init_service_health_metrics()

    def _init_timeout_metrics(self):
        """Initialize timeout-related metrics"""
        self.timeout_total = Counter(
            "autobot_timeout_total",
            "Total number of timeout events",
            ["operation_type", "database", "status"],
            registry=self.registry,
        )

    def _init_latency_metrics(self):
        """Initialize latency histogram metrics"""
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

    def _init_connection_metrics(self):
        """Initialize Redis connection pool metrics"""
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

    def _init_circuit_breaker_metrics(self):
        """Initialize circuit breaker metrics"""
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

    def _init_request_metrics(self):
        """Initialize request success/failure metrics"""
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

    def _init_workflow_metrics(self):
        """Initialize workflow execution metrics"""
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

    def _init_github_metrics(self):
        """Initialize GitHub operation metrics"""
        self.github_operations_total = Counter(
            "autobot_github_operations_total",
            "Total GitHub API operations",
            ["operation", "status"],
            registry=self.registry,
        )

        self.github_api_duration = Histogram(
            "autobot_github_api_duration_seconds",
            "GitHub API call duration in seconds",
            ["operation"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=self.registry,
        )

        self.github_rate_limit_remaining = Gauge(
            "autobot_github_rate_limit_remaining",
            "GitHub API rate limit remaining",
            ["resource_type"],
            registry=self.registry,
        )

        self.github_commits = Counter(
            "autobot_github_commits_total",
            "Total GitHub commits created",
            ["repository", "status"],
            registry=self.registry,
        )

        self.github_pull_requests = Counter(
            "autobot_github_pull_requests_total",
            "Total GitHub pull requests",
            ["repository", "action", "status"],
            registry=self.registry,
        )

        self.github_issues = Counter(
            "autobot_github_issues_total",
            "Total GitHub issues",
            ["repository", "action", "status"],
            registry=self.registry,
        )

    def _init_task_metrics(self):
        """Initialize task execution metrics"""
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

    # Metric recording methods

    def record_timeout(self, operation_type: str, database: str, timed_out: bool):
        """Record a timeout event"""
        status = "timeout" if timed_out else "success"
        self.timeout_total.labels(
            operation_type=operation_type, database=database, status=status
        ).inc()

    def record_operation_duration(
        self, operation_type: str, database: str, duration: float
    ):
        """Record operation duration"""
        self.operation_duration.labels(
            operation_type=operation_type, database=database
        ).observe(duration)

    def record_circuit_breaker_event(self, database: str, event: str, reason: str):
        """Record circuit breaker state change"""
        self.circuit_breaker_events.labels(
            database=database, event=event, reason=reason
        ).inc()

    def update_circuit_breaker_state(
        self, database: str, state: str, failure_count: int
    ):
        """Update circuit breaker state gauge"""
        state_value = {"closed": 0, "open": 1, "half_open": 2}.get(state, 0)
        self.circuit_breaker_state.labels(database=database).set(state_value)
        self.circuit_breaker_failures.labels(database=database).set(failure_count)

    def update_connection_pool(
        self, database: str, active: int, idle: int, max_connections: int
    ):
        """Update connection pool metrics"""
        self.pool_connections.labels(database=database, state="active").set(active)
        self.pool_connections.labels(database=database, state="idle").set(idle)
        self.pool_connections.labels(database=database, state="total").set(
            max_connections
        )

        # Calculate saturation ratio
        saturation = active / max_connections if max_connections > 0 else 0
        self.pool_saturation.labels(database=database).set(saturation)

    def record_request(self, database: str, operation: str, success: bool):
        """Record a request success or failure"""
        status = "success" if success else "failure"
        self.requests_total.labels(
            database=database, operation=operation, status=status
        ).inc()

    # Workflow metric recording methods

    def record_workflow_execution(
        self, workflow_type: str, status: str, duration: float = None
    ):
        """Record a workflow execution"""
        self.workflow_executions_total.labels(
            workflow_type=workflow_type, status=status
        ).inc()
        if duration is not None:
            self.workflow_duration.labels(workflow_type=workflow_type).observe(duration)

    def record_workflow_step(self, workflow_type: str, step_type: str, status: str):
        """Record a workflow step execution"""
        self.workflow_steps_executed.labels(
            workflow_type=workflow_type, step_type=step_type, status=status
        ).inc()

    def update_active_workflows(self, workflow_type: str, count: int):
        """Update active workflows count"""
        self.active_workflows.labels(workflow_type=workflow_type).set(count)

    def record_workflow_approval(self, workflow_type: str, decision: str):
        """Record a workflow approval decision"""
        self.workflow_approvals.labels(
            workflow_type=workflow_type, decision=decision
        ).inc()

    # GitHub metric recording methods

    def record_github_operation(
        self, operation: str, status: str, duration: float = None
    ):
        """Record a GitHub API operation"""
        self.github_operations_total.labels(operation=operation, status=status).inc()
        if duration is not None:
            self.github_api_duration.labels(operation=operation).observe(duration)

    def update_github_rate_limit(self, resource_type: str, remaining: int):
        """Update GitHub rate limit remaining"""
        self.github_rate_limit_remaining.labels(resource_type=resource_type).set(
            remaining
        )

    def record_github_commit(self, repository: str, status: str):
        """Record a GitHub commit"""
        self.github_commits.labels(repository=repository, status=status).inc()

    def record_github_pull_request(self, repository: str, action: str, status: str):
        """Record a GitHub pull request operation"""
        self.github_pull_requests.labels(
            repository=repository, action=action, status=status
        ).inc()

    def record_github_issue(self, repository: str, action: str, status: str):
        """Record a GitHub issue operation"""
        self.github_issues.labels(
            repository=repository, action=action, status=status
        ).inc()

    # Task metric recording methods

    def record_task_execution(
        self,
        task_type: str,
        agent_type: str,
        status: str,
        duration: float = None,
    ):
        """Record a task execution"""
        self.tasks_executed_total.labels(
            task_type=task_type, agent_type=agent_type, status=status
        ).inc()
        if duration is not None:
            self.task_duration.labels(
                task_type=task_type, agent_type=agent_type
            ).observe(duration)

    def update_active_tasks(self, task_type: str, agent_type: str, count: int):
        """Update active tasks count"""
        self.active_tasks.labels(task_type=task_type, agent_type=agent_type).set(count)

    def update_task_queue_size(self, priority: str, size: int):
        """Update task queue size"""
        self.task_queue_size.labels(priority=priority).set(size)

    def record_task_retry(self, task_type: str, reason: str):
        """Record a task retry attempt"""
        self.task_retries.labels(task_type=task_type, reason=reason).inc()

    # Phase 1: System Metrics (Issue #344)

    def _init_system_metrics(self):
        """Initialize system-level metrics"""
        self.system_cpu_usage = Gauge(
            "autobot_cpu_usage_percent",
            "CPU usage percentage",
            registry=self.registry,
        )

        self.system_memory_usage = Gauge(
            "autobot_memory_usage_percent",
            "Memory usage percentage",
            registry=self.registry,
        )

        self.system_disk_usage = Gauge(
            "autobot_disk_usage_percent",
            "Disk usage percentage by mount point",
            ["mount_point"],
            registry=self.registry,
        )

        self.system_network_bytes = Counter(
            "autobot_network_bytes_total",
            "Total network bytes transferred",
            ["direction"],  # sent or received
            registry=self.registry,
        )

    def _init_error_metrics(self):
        """Initialize error tracking metrics"""
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

    def _init_claude_api_metrics(self):
        """Initialize Claude API metrics"""
        self.claude_api_requests_total = Counter(
            "autobot_claude_api_requests_total",
            "Total Claude API requests",
            ["tool_name", "success"],
            registry=self.registry,
        )

        self.claude_api_payload_bytes = Histogram(
            "autobot_claude_api_payload_bytes",
            "Claude API payload size distribution",
            buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000],
            registry=self.registry,
        )

        self.claude_api_response_time = Histogram(
            "autobot_claude_api_response_time_seconds",
            "Claude API response time in seconds",
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry,
        )

        self.claude_api_rate_limit_remaining = Gauge(
            "autobot_claude_api_rate_limit_remaining",
            "Claude API rate limit remaining",
            registry=self.registry,
        )

    def _init_service_health_metrics(self):
        """Initialize service health metrics"""
        self.service_health_score = Gauge(
            "autobot_service_health_score",
            "Service health score (0-100)",
            ["service_name"],
            registry=self.registry,
        )

        self.service_response_time = Histogram(
            "autobot_service_response_time_seconds",
            "Service response time in seconds",
            ["service_name"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=self.registry,
        )

        self.service_status = Gauge(
            "autobot_service_status",
            "Service status (0=offline, 1=online, 2=degraded)",
            ["service_name", "status"],
            registry=self.registry,
        )

    # System metric recording methods

    def update_system_cpu(self, cpu_percent: float):
        """Update CPU usage metric"""
        self.system_cpu_usage.set(cpu_percent)

    def update_system_memory(self, memory_percent: float):
        """Update memory usage metric"""
        self.system_memory_usage.set(memory_percent)

    def update_system_disk(self, mount_point: str, disk_percent: float):
        """Update disk usage metric"""
        self.system_disk_usage.labels(mount_point=mount_point).set(disk_percent)

    def record_network_bytes(self, direction: str, bytes_count: int):
        """Record network bytes transferred"""
        self.system_network_bytes.labels(direction=direction).inc(bytes_count)

    # Error metric recording methods

    def record_error(
        self, category: str, component: str, error_code: str = "unknown"
    ):
        """Record an error occurrence"""
        self.errors_total.labels(
            category=category, component=component, error_code=error_code
        ).inc()

    def update_error_rate(self, component: str, time_window: str, rate: float):
        """Update error rate for a component"""
        self.error_rate.labels(component=component, time_window=time_window).set(rate)

    # Claude API metric recording methods

    def record_claude_api_request(self, tool_name: str, success: bool):
        """Record a Claude API request"""
        self.claude_api_requests_total.labels(
            tool_name=tool_name, success=str(success).lower()
        ).inc()

    def record_claude_api_payload(self, payload_bytes: int):
        """Record Claude API payload size"""
        self.claude_api_payload_bytes.observe(payload_bytes)

    def record_claude_api_response_time(self, response_time_seconds: float):
        """Record Claude API response time"""
        self.claude_api_response_time.observe(response_time_seconds)

    def update_claude_api_rate_limit(self, remaining: int):
        """Update Claude API rate limit remaining"""
        self.claude_api_rate_limit_remaining.set(remaining)

    # Service health metric recording methods

    def update_service_health(self, service_name: str, health_score: float):
        """Update service health score"""
        self.service_health_score.labels(service_name=service_name).set(health_score)

    def record_service_response_time(self, service_name: str, response_time: float):
        """Record service response time"""
        self.service_response_time.labels(service_name=service_name).observe(
            response_time
        )

    def update_service_status(self, service_name: str, status: str):
        """Update service status"""
        status_value = {"offline": 0, "online": 1, "degraded": 2}.get(
            status.lower(), 0
        )
        self.service_status.labels(service_name=service_name, status=status).set(
            status_value
        )

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format"""
        return generate_latest(self.registry)


# Global metrics instance (thread-safe)
import threading

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
