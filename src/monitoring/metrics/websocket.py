# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
WebSocket Metrics Recorder

Metrics for WebSocket connection management and messaging.
Created as part of Issue #470 - Add missing Prometheus metrics.

Covers:
- Active connection tracking
- Message counts and sizes
- Connection lifecycle (connect, disconnect, error)
- Latency and throughput
- Room/channel metrics
"""

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class WebSocketMetricsRecorder(BaseMetricsRecorder):
    """Recorder for WebSocket metrics."""

    def _init_metrics(self) -> None:
        """Initialize WebSocket metrics.

        Delegates to helper methods for each metric category.
        Issue #665: Refactored from 149-line monolithic function.
        """
        self._init_connection_metrics()
        self._init_message_metrics()
        self._init_error_metrics()
        self._init_latency_metrics()
        self._init_room_metrics()
        self._init_throughput_metrics()

    def _init_connection_metrics(self) -> None:
        """Initialize connection tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.connections_active = Gauge(
            "autobot_websocket_connections_active",
            "Current number of active WebSocket connections",
            ["namespace"],  # namespace for different WS endpoints
            registry=self.registry,
        )

        self.connections_total = Counter(
            "autobot_websocket_connections_total",
            "Total WebSocket connections established",
            ["namespace"],
            registry=self.registry,
        )

        self.disconnections_total = Counter(
            "autobot_websocket_disconnections_total",
            "Total WebSocket disconnections",
            ["namespace", "reason"],  # reason: normal, error, timeout, server_shutdown
            registry=self.registry,
        )

        self.connection_duration = Histogram(
            "autobot_websocket_connection_duration_seconds",
            "WebSocket connection duration in seconds",
            ["namespace"],
            buckets=[1, 10, 60, 300, 900, 1800, 3600, 7200, 14400],
            registry=self.registry,
        )

    def _init_message_metrics(self) -> None:
        """Initialize message tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.messages_sent = Counter(
            "autobot_websocket_messages_sent_total",
            "Total messages sent to clients",
            ["namespace", "message_type"],
            registry=self.registry,
        )

        self.messages_received = Counter(
            "autobot_websocket_messages_received_total",
            "Total messages received from clients",
            ["namespace", "message_type"],
            registry=self.registry,
        )

        self.message_size_bytes = Histogram(
            "autobot_websocket_message_size_bytes",
            "Message size in bytes",
            ["namespace", "direction"],  # direction: sent, received
            buckets=[64, 256, 1024, 4096, 16384, 65536, 262144, 1048576],
            registry=self.registry,
        )

        self.messages_dropped = Counter(
            "autobot_websocket_messages_dropped_total",
            "Total messages dropped (queue full, client disconnected, etc.)",
            ["namespace", "reason"],
            registry=self.registry,
        )

    def _init_error_metrics(self) -> None:
        """Initialize error tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.errors_total = Counter(
            "autobot_websocket_errors_total",
            "Total WebSocket errors",
            ["namespace", "error_type"],  # error_type: connection, message, protocol
            registry=self.registry,
        )

        self.reconnection_attempts = Counter(
            "autobot_websocket_reconnection_attempts_total",
            "Total client reconnection attempts",
            ["namespace"],
            registry=self.registry,
        )

    def _init_latency_metrics(self) -> None:
        """Initialize latency tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.message_latency = Histogram(
            "autobot_websocket_message_latency_seconds",
            "Message processing latency in seconds",
            ["namespace", "message_type"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
            registry=self.registry,
        )

        self.ping_latency = Histogram(
            "autobot_websocket_ping_latency_seconds",
            "Ping/pong round-trip latency",
            ["namespace"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
            registry=self.registry,
        )

    def _init_room_metrics(self) -> None:
        """Initialize room/channel tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.rooms_active = Gauge(
            "autobot_websocket_rooms_active",
            "Current number of active rooms/channels",
            ["namespace"],
            registry=self.registry,
        )

        self.room_subscribers = Gauge(
            "autobot_websocket_room_subscribers",
            "Number of subscribers per room",
            ["namespace", "room"],
            registry=self.registry,
        )

        self.room_messages = Counter(
            "autobot_websocket_room_messages_total",
            "Total messages broadcast to rooms",
            ["namespace", "room"],
            registry=self.registry,
        )

    def _init_throughput_metrics(self) -> None:
        """Initialize throughput tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.bytes_sent = Counter(
            "autobot_websocket_bytes_sent_total",
            "Total bytes sent",
            ["namespace"],
            registry=self.registry,
        )

        self.bytes_received = Counter(
            "autobot_websocket_bytes_received_total",
            "Total bytes received",
            ["namespace"],
            registry=self.registry,
        )

        self.messages_per_second = Gauge(
            "autobot_websocket_messages_per_second",
            "Current message throughput (messages/second)",
            ["namespace", "direction"],
            registry=self.registry,
        )

    # =========================================================================
    # Connection Methods
    # =========================================================================

    def record_connection(self, namespace: str) -> None:
        """Record a new WebSocket connection."""
        self.connections_active.labels(namespace=namespace).inc()
        self.connections_total.labels(namespace=namespace).inc()

    def record_disconnection(
        self, namespace: str, reason: str, duration_seconds: float
    ) -> None:
        """Record a WebSocket disconnection."""
        self.connections_active.labels(namespace=namespace).dec()
        self.disconnections_total.labels(namespace=namespace, reason=reason).inc()
        self.connection_duration.labels(namespace=namespace).observe(duration_seconds)

    def set_active_connections(self, namespace: str, count: int) -> None:
        """Set the current number of active connections."""
        self.connections_active.labels(namespace=namespace).set(count)

    # =========================================================================
    # Message Methods
    # =========================================================================

    def record_message_sent(
        self, namespace: str, message_type: str, size_bytes: int
    ) -> None:
        """Record a message sent to client."""
        self.messages_sent.labels(namespace=namespace, message_type=message_type).inc()
        self.message_size_bytes.labels(namespace=namespace, direction="sent").observe(
            size_bytes
        )
        self.bytes_sent.labels(namespace=namespace).inc(size_bytes)

    def record_message_received(
        self, namespace: str, message_type: str, size_bytes: int
    ) -> None:
        """Record a message received from client."""
        self.messages_received.labels(
            namespace=namespace, message_type=message_type
        ).inc()
        self.message_size_bytes.labels(
            namespace=namespace, direction="received"
        ).observe(size_bytes)
        self.bytes_received.labels(namespace=namespace).inc(size_bytes)

    def record_message_dropped(self, namespace: str, reason: str) -> None:
        """Record a dropped message."""
        self.messages_dropped.labels(namespace=namespace, reason=reason).inc()

    # =========================================================================
    # Error Methods
    # =========================================================================

    def record_error(self, namespace: str, error_type: str) -> None:
        """Record a WebSocket error."""
        self.errors_total.labels(namespace=namespace, error_type=error_type).inc()

    def record_reconnection_attempt(self, namespace: str) -> None:
        """Record a client reconnection attempt."""
        self.reconnection_attempts.labels(namespace=namespace).inc()

    # =========================================================================
    # Latency Methods
    # =========================================================================

    def record_message_latency(
        self, namespace: str, message_type: str, latency_seconds: float
    ) -> None:
        """Record message processing latency."""
        self.message_latency.labels(
            namespace=namespace, message_type=message_type
        ).observe(latency_seconds)

    def record_ping_latency(self, namespace: str, latency_seconds: float) -> None:
        """Record ping/pong latency."""
        self.ping_latency.labels(namespace=namespace).observe(latency_seconds)

    # =========================================================================
    # Room Methods
    # =========================================================================

    def set_active_rooms(self, namespace: str, count: int) -> None:
        """Set the number of active rooms."""
        self.rooms_active.labels(namespace=namespace).set(count)

    def set_room_subscribers(self, namespace: str, room: str, count: int) -> None:
        """Set the number of subscribers in a room."""
        self.room_subscribers.labels(namespace=namespace, room=room).set(count)

    def record_room_message(self, namespace: str, room: str) -> None:
        """Record a message broadcast to a room."""
        self.room_messages.labels(namespace=namespace, room=room).inc()

    # =========================================================================
    # Throughput Methods
    # =========================================================================

    def set_message_throughput(
        self, namespace: str, direction: str, messages_per_second: float
    ) -> None:
        """Set current message throughput."""
        self.messages_per_second.labels(namespace=namespace, direction=direction).set(
            messages_per_second
        )


__all__ = ["WebSocketMetricsRecorder"]
