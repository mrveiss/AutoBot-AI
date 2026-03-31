# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Metrics Recorder

Metrics for Redis operations including command execution,
connection pool management, and pub/sub.
Created as part of Issue #470 - Add missing Prometheus metrics.

Covers:
- Operation counts and latency
- Connection pool stats
- Memory usage
- Pub/Sub metrics
- Key space metrics
"""

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class RedisMetricsRecorder(BaseMetricsRecorder):
    """Recorder for Redis metrics."""

    def _init_metrics(self) -> None:
        """Initialize Redis metrics by delegating to category-specific helpers."""
        self._init_operation_metrics()
        self._init_connection_pool_metrics()
        self._init_memory_metrics()
        self._init_key_space_metrics()
        self._init_pubsub_metrics()
        self._init_stream_metrics()
        self._init_health_metrics()

    def _init_operation_metrics(self) -> None:
        """
        Initialize operation-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.operations_total = Counter(
            "autobot_redis_operations_total",
            "Total Redis operations",
            ["database", "operation", "status"],  # status: success, error
            registry=self.registry,
        )

        self.operation_latency = Histogram(
            "autobot_redis_operation_latency_seconds",
            "Redis operation latency in seconds",
            ["database", "operation"],
            buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
            registry=self.registry,
        )

        self.pipeline_operations = Counter(
            "autobot_redis_pipeline_operations_total",
            "Total Redis pipeline operations",
            ["database"],
            registry=self.registry,
        )

        self.pipeline_size = Histogram(
            "autobot_redis_pipeline_size",
            "Number of commands per pipeline",
            ["database"],
            buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
            registry=self.registry,
        )

    def _init_connection_pool_metrics(self) -> None:
        """
        Initialize connection pool-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.connections_active = Gauge(
            "autobot_redis_connections_active",
            "Current number of active connections",
            ["database"],
            registry=self.registry,
        )

        self.connections_available = Gauge(
            "autobot_redis_connections_available",
            "Number of available connections in pool",
            ["database"],
            registry=self.registry,
        )

        self.connections_max = Gauge(
            "autobot_redis_connections_max",
            "Maximum connection pool size",
            ["database"],
            registry=self.registry,
        )

        self.connection_errors = Counter(
            "autobot_redis_connection_errors_total",
            "Total connection errors",
            ["database", "error_type"],  # error_type: timeout, refused, reset
            registry=self.registry,
        )

        self.connection_wait_time = Histogram(
            "autobot_redis_connection_wait_seconds",
            "Time spent waiting for a connection from pool",
            ["database"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
            registry=self.registry,
        )

    def _init_memory_metrics(self) -> None:
        """
        Initialize memory-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.memory_used_bytes = Gauge(
            "autobot_redis_memory_used_bytes",
            "Redis memory usage in bytes",
            ["database"],
            registry=self.registry,
        )

        self.memory_peak_bytes = Gauge(
            "autobot_redis_memory_peak_bytes",
            "Redis peak memory usage in bytes",
            ["database"],
            registry=self.registry,
        )

        self.memory_fragmentation_ratio = Gauge(
            "autobot_redis_memory_fragmentation_ratio",
            "Memory fragmentation ratio",
            ["database"],
            registry=self.registry,
        )

    def _init_key_space_metrics(self) -> None:
        """
        Initialize key space-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.keys_total = Gauge(
            "autobot_redis_keys_total",
            "Total number of keys",
            ["database"],
            registry=self.registry,
        )

        self.keys_expired = Counter(
            "autobot_redis_keys_expired_total",
            "Total expired keys",
            ["database"],
            registry=self.registry,
        )

        self.keys_evicted = Counter(
            "autobot_redis_keys_evicted_total",
            "Total evicted keys (due to maxmemory)",
            ["database"],
            registry=self.registry,
        )

        self.key_hits = Counter(
            "autobot_redis_key_hits_total",
            "Total key hits (key exists)",
            ["database"],
            registry=self.registry,
        )

        self.key_misses = Counter(
            "autobot_redis_key_misses_total",
            "Total key misses (key doesn't exist)",
            ["database"],
            registry=self.registry,
        )

    def _init_pubsub_metrics(self) -> None:
        """
        Initialize pub/sub-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.pubsub_channels = Gauge(
            "autobot_redis_pubsub_channels_active",
            "Number of active pub/sub channels",
            ["database"],
            registry=self.registry,
        )

        self.pubsub_subscribers = Gauge(
            "autobot_redis_pubsub_subscribers",
            "Number of pub/sub subscribers",
            ["database", "channel"],
            registry=self.registry,
        )

        self.pubsub_messages_published = Counter(
            "autobot_redis_pubsub_messages_published_total",
            "Total messages published",
            ["database", "channel"],
            registry=self.registry,
        )

        self.pubsub_messages_received = Counter(
            "autobot_redis_pubsub_messages_received_total",
            "Total messages received by subscribers",
            ["database", "channel"],
            registry=self.registry,
        )

    def _init_stream_metrics(self) -> None:
        """
        Initialize Redis Streams-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.stream_entries = Gauge(
            "autobot_redis_stream_entries",
            "Number of entries in stream",
            ["database", "stream"],
            registry=self.registry,
        )

        self.stream_consumer_groups = Gauge(
            "autobot_redis_stream_consumer_groups",
            "Number of consumer groups for stream",
            ["database", "stream"],
            registry=self.registry,
        )

        self.stream_pending_entries = Gauge(
            "autobot_redis_stream_pending_entries",
            "Number of pending entries (not ACKed)",
            ["database", "stream", "group"],
            registry=self.registry,
        )

    def _init_health_metrics(self) -> None:
        """
        Initialize health-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.server_available = Gauge(
            "autobot_redis_server_available",
            "Redis server availability (1=available, 0=unavailable)",
            ["database"],
            registry=self.registry,
        )

        self.replication_lag_seconds = Gauge(
            "autobot_redis_replication_lag_seconds",
            "Replication lag in seconds (for replicas)",
            ["database"],
            registry=self.registry,
        )

    # =========================================================================
    # Operation Methods
    # =========================================================================

    def record_operation(
        self,
        database: str,
        operation: str,
        latency_seconds: float,
        success: bool = True,
    ) -> None:
        """Record a Redis operation."""
        status = "success" if success else "error"
        self.operations_total.labels(
            database=database, operation=operation, status=status
        ).inc()
        if success:
            self.operation_latency.labels(
                database=database, operation=operation
            ).observe(latency_seconds)

    def record_pipeline(
        self, database: str, command_count: int, latency_seconds: float
    ) -> None:
        """Record a Redis pipeline execution."""
        self.pipeline_operations.labels(database=database).inc()
        self.pipeline_size.labels(database=database).observe(command_count)
        self.operation_latency.labels(database=database, operation="pipeline").observe(
            latency_seconds
        )

    # =========================================================================
    # Connection Pool Methods
    # =========================================================================

    def update_pool_stats(
        self,
        database: str,
        active: int,
        available: int,
        max_connections: int,
    ) -> None:
        """Update connection pool statistics."""
        self.connections_active.labels(database=database).set(active)
        self.connections_available.labels(database=database).set(available)
        self.connections_max.labels(database=database).set(max_connections)

    def record_connection_error(self, database: str, error_type: str) -> None:
        """Record a connection error."""
        self.connection_errors.labels(database=database, error_type=error_type).inc()

    def record_connection_wait(self, database: str, wait_seconds: float) -> None:
        """Record time spent waiting for a connection."""
        self.connection_wait_time.labels(database=database).observe(wait_seconds)

    # =========================================================================
    # Memory Methods
    # =========================================================================

    def update_memory_stats(
        self,
        database: str,
        used_bytes: int,
        peak_bytes: int,
        fragmentation_ratio: float,
    ) -> None:
        """Update memory statistics."""
        self.memory_used_bytes.labels(database=database).set(used_bytes)
        self.memory_peak_bytes.labels(database=database).set(peak_bytes)
        self.memory_fragmentation_ratio.labels(database=database).set(
            fragmentation_ratio
        )

    # =========================================================================
    # Key Space Methods
    # =========================================================================

    def set_key_count(self, database: str, count: int) -> None:
        """Set total key count."""
        self.keys_total.labels(database=database).set(count)

    def record_key_expired(self, database: str) -> None:
        """Record a key expiration."""
        self.keys_expired.labels(database=database).inc()

    def record_key_evicted(self, database: str) -> None:
        """Record a key eviction."""
        self.keys_evicted.labels(database=database).inc()

    def record_key_hit(self, database: str) -> None:
        """Record a key hit."""
        self.key_hits.labels(database=database).inc()

    def record_key_miss(self, database: str) -> None:
        """Record a key miss."""
        self.key_misses.labels(database=database).inc()

    # =========================================================================
    # Pub/Sub Methods
    # =========================================================================

    def set_pubsub_channels(self, database: str, count: int) -> None:
        """Set number of active pub/sub channels."""
        self.pubsub_channels.labels(database=database).set(count)

    def set_pubsub_subscribers(self, database: str, channel: str, count: int) -> None:
        """Set number of subscribers for a channel."""
        self.pubsub_subscribers.labels(database=database, channel=channel).set(count)

    def record_pubsub_publish(self, database: str, channel: str) -> None:
        """Record a message published."""
        self.pubsub_messages_published.labels(database=database, channel=channel).inc()

    def record_pubsub_receive(self, database: str, channel: str) -> None:
        """Record a message received."""
        self.pubsub_messages_received.labels(database=database, channel=channel).inc()

    # =========================================================================
    # Stream Methods
    # =========================================================================

    def update_stream_stats(
        self,
        database: str,
        stream: str,
        entries: int,
        consumer_groups: int,
    ) -> None:
        """Update stream statistics."""
        self.stream_entries.labels(database=database, stream=stream).set(entries)
        self.stream_consumer_groups.labels(database=database, stream=stream).set(
            consumer_groups
        )

    def set_stream_pending(
        self, database: str, stream: str, group: str, pending: int
    ) -> None:
        """Set pending entry count for a consumer group."""
        self.stream_pending_entries.labels(
            database=database, stream=stream, group=group
        ).set(pending)

    # =========================================================================
    # Health Methods
    # =========================================================================

    def set_server_available(self, database: str, available: bool) -> None:
        """Set server availability status."""
        self.server_available.labels(database=database).set(1 if available else 0)

    def set_replication_lag(self, database: str, lag_seconds: float) -> None:
        """Set replication lag."""
        self.replication_lag_seconds.labels(database=database).set(lag_seconds)


__all__ = ["RedisMetricsRecorder"]
