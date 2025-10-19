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
        self.registry = registry or CollectorRegistry()

        # Initialize all metrics
        self._init_timeout_metrics()
        self._init_latency_metrics()
        self._init_connection_metrics()
        self._init_circuit_breaker_metrics()
        self._init_request_metrics()

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

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format"""
        return generate_latest(self.registry)


# Global metrics instance
_metrics_instance: Optional[PrometheusMetricsManager] = None


def get_metrics_manager() -> PrometheusMetricsManager:
    """Get or create global metrics manager"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = PrometheusMetricsManager()
    return _metrics_instance
