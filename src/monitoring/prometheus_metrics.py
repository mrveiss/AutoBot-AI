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
# Issue #469: Added PerformanceMetricsRecorder for GPU/NPU metrics
# Issue #470: Added KnowledgeBase, LLMProvider, WebSocket, Redis recorders
# Issue #476: Added FrontendMetricsRecorder for RUM metrics
from .metrics import (
    WorkflowMetricsRecorder,
    GitHubMetricsRecorder,
    TaskMetricsRecorder,
    SystemMetricsRecorder,
    ClaudeAPIMetricsRecorder,
    ServiceHealthMetricsRecorder,
    PerformanceMetricsRecorder,
    KnowledgeBaseMetricsRecorder,
    LLMProviderMetricsRecorder,
    WebSocketMetricsRecorder,
    RedisMetricsRecorder,
    FrontendMetricsRecorder,
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
    - PerformanceMetricsRecorder: GPU/NPU/Performance metrics (Issue #469)
    - KnowledgeBaseMetricsRecorder: Knowledge base/vector store metrics (Issue #470)
    - LLMProviderMetricsRecorder: LLM provider metrics (Issue #470)
    - WebSocketMetricsRecorder: WebSocket connection metrics (Issue #470)
    - RedisMetricsRecorder: Redis operation metrics (Issue #470)
    - FrontendMetricsRecorder: Frontend RUM metrics (Issue #476)
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
        # Issue #469: Initialize performance recorder for GPU/NPU metrics
        self._performance = PerformanceMetricsRecorder(self.registry)
        # Issue #470: Initialize new domain-specific recorders
        self._knowledge_base = KnowledgeBaseMetricsRecorder(self.registry)
        self._llm_provider = LLMProviderMetricsRecorder(self.registry)
        self._websocket = WebSocketMetricsRecorder(self.registry)
        self._redis = RedisMetricsRecorder(self.registry)
        # Issue #476: Initialize frontend RUM metrics recorder
        self._frontend = FrontendMetricsRecorder(self.registry)

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
        self, workflow_type: str, status: str, duration: Optional[float] = None
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
        self, operation: str, status: str, duration: Optional[float] = None
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
        duration: Optional[float] = None,
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
    # Performance Metrics (Issue #469: Delegates to PerformanceMetricsRecorder)
    # =========================================================================

    def update_gpu_metrics(
        self,
        gpu_id: str,
        gpu_name: str,
        utilization: float,
        memory_utilization: float,
        temperature: float,
        power_watts: float,
    ) -> None:
        """Update GPU metrics."""
        self._performance.update_gpu_metrics(
            gpu_id, gpu_name, utilization, memory_utilization, temperature, power_watts
        )

    def set_gpu_available(self, available: bool) -> None:
        """Set GPU availability status."""
        self._performance.set_gpu_available(available)

    def record_gpu_throttling(self, gpu_id: str, throttle_type: str) -> None:
        """Record a GPU throttling event."""
        self._performance.record_gpu_throttling(gpu_id, throttle_type)

    def update_npu_metrics(self, utilization: float, acceleration_ratio: float) -> None:
        """Update NPU utilization and acceleration metrics."""
        self._performance.update_npu_metrics(utilization, acceleration_ratio)

    def set_npu_available(self, available: bool) -> None:
        """Set NPU availability status."""
        self._performance.set_npu_available(available)

    def set_npu_wsl_limitation(self, limited: bool) -> None:
        """Set NPU WSL limitation status."""
        self._performance.set_npu_wsl_limitation(limited)

    def record_npu_inference(self, model_type: str) -> None:
        """Record an NPU inference operation."""
        self._performance.record_npu_inference(model_type)

    def update_performance_score(self, score: float) -> None:
        """Update overall performance score (0-100)."""
        self._performance.update_performance_score(score)

    def update_health_score(self, score: float) -> None:
        """Update system health score (0-100)."""
        self._performance.update_health_score(score)

    def set_bottleneck(self, category: str, detected: bool) -> None:
        """Set bottleneck detection status for a category."""
        self._performance.set_bottleneck(category, detected)

    def record_optimization_recommendation(
        self, category: str, priority: str
    ) -> None:
        """Record an optimization recommendation."""
        self._performance.record_optimization_recommendation(category, priority)

    def record_performance_alert(self, category: str, severity: str) -> None:
        """Record a performance alert."""
        self._performance.record_performance_alert(category, severity)

    def update_active_alerts(self, severity: str, count: int) -> None:
        """Update active alert count for a severity level."""
        self._performance.update_active_alerts(severity, count)

    def record_multimodal_processing(
        self, modality: str, duration_seconds: float, success: bool
    ) -> None:
        """Record a multi-modal processing operation."""
        self._performance.record_multimodal_processing(modality, duration_seconds, success)

    # =========================================================================
    # Knowledge Base Metrics (Issue #470: Delegates to KnowledgeBaseMetricsRecorder)
    # =========================================================================

    def set_document_count(
        self, count: int, collection: str, document_type: str = "default"
    ) -> None:
        """Set total document count for a collection."""
        self._knowledge_base.set_document_count(count, collection, document_type)

    def record_document_operation(
        self, operation: str, collection: str, size_bytes: int = 0
    ) -> None:
        """Record a document operation."""
        self._knowledge_base.record_document_operation(operation, collection, size_bytes)

    def set_vector_count(self, count: int, collection: str) -> None:
        """Set total vector count for a collection."""
        self._knowledge_base.set_vector_count(count, collection)

    def record_embedding_operation(
        self, operation: str, model: str, latency_seconds: float = 0
    ) -> None:
        """Record an embedding operation."""
        self._knowledge_base.record_embedding_operation(operation, model, latency_seconds)

    def record_knowledge_search(
        self,
        search_type: str,
        collection: str,
        latency_seconds: float,
        results_count: int,
    ) -> None:
        """Record a knowledge base search operation."""
        self._knowledge_base.record_search(
            search_type, collection, latency_seconds, results_count
        )

    def record_knowledge_cache_hit(self, cache_type: str) -> None:
        """Record a knowledge base cache hit."""
        self._knowledge_base.record_cache_hit(cache_type)

    def record_knowledge_cache_miss(self, cache_type: str) -> None:
        """Record a knowledge base cache miss."""
        self._knowledge_base.record_cache_miss(cache_type)

    # =========================================================================
    # LLM Provider Metrics (Issue #470: Delegates to LLMProviderMetricsRecorder)
    # =========================================================================

    def record_llm_request_start(self, provider: str) -> None:
        """Record start of an LLM request."""
        self._llm_provider.record_request_start(provider)

    def record_llm_request_complete(
        self,
        provider: str,
        model: str,
        request_type: str,
        latency_seconds: float,
        time_to_first_token_seconds: float = 0,
    ) -> None:
        """Record completion of an LLM request."""
        self._llm_provider.record_request_complete(
            provider, model, request_type, latency_seconds, time_to_first_token_seconds
        )

    def record_llm_tokens(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record token usage for an LLM request."""
        self._llm_provider.record_tokens(provider, model, input_tokens, output_tokens)

    def record_llm_cost(
        self,
        provider: str,
        model: str,
        input_cost: float,
        output_cost: float,
    ) -> None:
        """Record cost for an LLM request."""
        self._llm_provider.record_cost(provider, model, input_cost, output_cost)

    def record_llm_error(self, provider: str, model: str, error_type: str) -> None:
        """Record an LLM error."""
        self._llm_provider.record_error(provider, model, error_type)

    def set_llm_provider_available(self, provider: str, available: bool) -> None:
        """Set LLM provider availability status."""
        self._llm_provider.set_provider_available(provider, available)

    def update_llm_rate_limits(
        self,
        provider: str,
        requests_remaining: int,
        tokens_remaining: int,
        reset_seconds: float,
    ) -> None:
        """Update LLM rate limit metrics."""
        self._llm_provider.update_rate_limits(
            provider, requests_remaining, tokens_remaining, reset_seconds
        )

    # =========================================================================
    # WebSocket Metrics (Issue #470: Delegates to WebSocketMetricsRecorder)
    # =========================================================================

    def record_websocket_connection(self, namespace: str) -> None:
        """Record a new WebSocket connection."""
        self._websocket.record_connection(namespace)

    def record_websocket_disconnection(
        self, namespace: str, reason: str, duration_seconds: float
    ) -> None:
        """Record a WebSocket disconnection."""
        self._websocket.record_disconnection(namespace, reason, duration_seconds)

    def record_websocket_message_sent(
        self, namespace: str, message_type: str, size_bytes: int
    ) -> None:
        """Record a message sent to WebSocket client."""
        self._websocket.record_message_sent(namespace, message_type, size_bytes)

    def record_websocket_message_received(
        self, namespace: str, message_type: str, size_bytes: int
    ) -> None:
        """Record a message received from WebSocket client."""
        self._websocket.record_message_received(namespace, message_type, size_bytes)

    def record_websocket_error(self, namespace: str, error_type: str) -> None:
        """Record a WebSocket error."""
        self._websocket.record_error(namespace, error_type)

    def set_websocket_active_connections(self, namespace: str, count: int) -> None:
        """Set the number of active WebSocket connections."""
        self._websocket.set_active_connections(namespace, count)

    # =========================================================================
    # Redis Metrics (Issue #470: Delegates to RedisMetricsRecorder)
    # =========================================================================

    def record_redis_operation(
        self,
        database: str,
        operation: str,
        latency_seconds: float,
        success: bool = True,
    ) -> None:
        """Record a Redis operation."""
        self._redis.record_operation(database, operation, latency_seconds, success)

    def update_redis_pool_stats(
        self,
        database: str,
        active: int,
        available: int,
        max_connections: int,
    ) -> None:
        """Update Redis connection pool statistics."""
        self._redis.update_pool_stats(database, active, available, max_connections)

    def update_redis_memory_stats(
        self,
        database: str,
        used_bytes: int,
        peak_bytes: int,
        fragmentation_ratio: float,
    ) -> None:
        """Update Redis memory statistics."""
        self._redis.update_memory_stats(
            database, used_bytes, peak_bytes, fragmentation_ratio
        )

    def set_redis_key_count(self, database: str, count: int) -> None:
        """Set Redis total key count."""
        self._redis.set_key_count(database, count)

    def set_redis_server_available(self, database: str, available: bool) -> None:
        """Set Redis server availability status."""
        self._redis.set_server_available(database, available)

    def record_redis_pubsub_publish(self, database: str, channel: str) -> None:
        """Record a Redis pub/sub publish."""
        self._redis.record_pubsub_publish(database, channel)

    # =========================================================================
    # Frontend RUM Metrics (Issue #476: Delegates to FrontendMetricsRecorder)
    # =========================================================================

    def record_frontend_page_load(self, page: str, load_time_seconds: float) -> None:
        """Record frontend page load time."""
        self._frontend.record_page_load(page, load_time_seconds)

    def record_frontend_fcp(self, page: str, fcp_seconds: float) -> None:
        """Record First Contentful Paint time."""
        self._frontend.record_first_contentful_paint(page, fcp_seconds)

    def record_frontend_lcp(self, page: str, lcp_seconds: float) -> None:
        """Record Largest Contentful Paint time."""
        self._frontend.record_largest_contentful_paint(page, lcp_seconds)

    def record_frontend_tti(self, page: str, tti_seconds: float) -> None:
        """Record Time to Interactive."""
        self._frontend.record_time_to_interactive(page, tti_seconds)

    def record_frontend_dom_loaded(self, page: str, dcl_seconds: float) -> None:
        """Record DOM Content Loaded time."""
        self._frontend.record_dom_content_loaded(page, dcl_seconds)

    def record_frontend_api_request(
        self,
        endpoint: str,
        method: str,
        status: str,
        latency_seconds: float,
        is_slow: bool = False,
        is_timeout: bool = False,
    ) -> None:
        """Record a frontend API request."""
        self._frontend.record_api_request(
            endpoint, method, status, latency_seconds, is_slow, is_timeout
        )

    def record_frontend_api_error(
        self, endpoint: str, method: str, error_type: str
    ) -> None:
        """Record a frontend API error."""
        self._frontend.record_api_error(endpoint, method, error_type)

    def record_frontend_js_error(self, error_type: str, page: str) -> None:
        """Record a JavaScript error from frontend."""
        self._frontend.record_js_error(error_type, page)

    def record_frontend_unhandled_rejection(self, page: str) -> None:
        """Record an unhandled Promise rejection from frontend."""
        self._frontend.record_unhandled_rejection(page)

    def record_frontend_component_error(
        self, component: str, error_type: str
    ) -> None:
        """Record a Vue component error from frontend."""
        self._frontend.record_component_error(component, error_type)

    def record_frontend_user_action(self, action_type: str, page: str) -> None:
        """Record a user action from frontend."""
        self._frontend.record_user_action(action_type, page)

    def record_frontend_form_submission(self, form_name: str, status: str) -> None:
        """Record a form submission from frontend."""
        self._frontend.record_form_submission(form_name, status)

    def record_frontend_session_duration(self, duration_seconds: float) -> None:
        """Record frontend session duration."""
        self._frontend.record_session_duration(duration_seconds)

    def set_frontend_active_sessions(self, count: int) -> None:
        """Set frontend active session count."""
        self._frontend.set_active_sessions(count)

    def record_frontend_session_start(self) -> None:
        """Record a new frontend session starting."""
        self._frontend.record_session_start()

    def record_frontend_ws_event(self, event: str) -> None:
        """Record a WebSocket connection event from frontend."""
        self._frontend.record_ws_connection_event(event)

    def record_frontend_ws_message(self, direction: str, event_type: str) -> None:
        """Record a WebSocket message from frontend."""
        self._frontend.record_ws_message(direction, event_type)

    def record_frontend_slow_resource(self, resource_type: str) -> None:
        """Record a slow resource load from frontend."""
        self._frontend.record_slow_resource(resource_type)

    def record_frontend_resource_load(
        self, resource_type: str, load_time_seconds: float
    ) -> None:
        """Record resource load time from frontend."""
        self._frontend.record_resource_load(resource_type, load_time_seconds)

    def record_frontend_critical_issue(self, issue_type: str) -> None:
        """Record a critical issue from frontend."""
        self._frontend.record_critical_issue(issue_type)

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
