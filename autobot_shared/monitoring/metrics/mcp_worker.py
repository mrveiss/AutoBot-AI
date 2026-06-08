# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MCP Worker Metrics Recorder

Metrics for MCP bridge worker monitoring and restart budget tracking.
Identified during #4089 review — critical for production observability.
Issue #4109: Alerts for MCP worker restart budget exhaustion.
"""

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class MCPWorkerMetricsRecorder(BaseMetricsRecorder):
    """Recorder for MCP bridge worker lifecycle and health metrics."""

    def _init_metrics(self) -> None:
        """Initialize MCP worker metrics."""
        # Restart count per bridge
        self.restart_count = Gauge(
            "autobot_mcp_worker_restart_count",
            "Total restart count per bridge worker",
            ["bridge"],
            registry=self.registry,
        )

        # Restart budget exhaustion total
        self.restart_budget_exhaustion_total = Counter(
            "autobot_mcp_worker_restart_budget_exhaustion_total",
            "Total times a bridge worker exceeded restart_max budget and entered permanent failure",
            ["bridge"],
            registry=self.registry,
        )

        # Worker crash histogram (time between crashes)
        self.mcp_worker_crash_seconds = Histogram(
            "autobot_mcp_worker_crash_seconds",
            "Time interval between consecutive worker crashes",
            ["bridge"],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 900.0],
            registry=self.registry,
        )

        # Circuit breaker activation flag
        self.circuit_breaker_activated = Gauge(
            "autobot_mcp_worker_circuit_breaker_activated",
            "Circuit breaker activated for a bridge (tool calls failing)",
            ["bridge"],
            registry=self.registry,
        )

        # Worker uptime gauge
        self.worker_uptime_seconds = Gauge(
            "autobot_mcp_worker_uptime_seconds",
            "Seconds since worker process started",
            ["bridge"],
            registry=self.registry,
        )

        # Permanent failure flag
        self.worker_permanently_failed = Gauge(
            "autobot_mcp_worker_permanently_failed",
            "Worker is in permanent failure state (restart_max exceeded)",
            ["bridge"],
            registry=self.registry,
        )

    def record_restart(self, bridge: str, restart_count: int) -> None:
        """Record a worker restart and update restart count."""
        self.restart_count.labels(bridge=bridge).set(restart_count)

    def record_restart_budget_exhaustion(self, bridge: str) -> None:
        """Record that a worker exceeded its restart budget."""
        self.restart_budget_exhaustion_total.labels(bridge=bridge).inc()

    def record_crash_interval(self, bridge: str, seconds: float) -> None:
        """Record time interval since last crash."""
        self.mcp_worker_crash_seconds.labels(bridge=bridge).observe(seconds)

    def set_circuit_breaker_activated(self, bridge: str, activated: bool) -> None:
        """Set circuit breaker activation state."""
        self.circuit_breaker_activated.labels(bridge=bridge).set(1 if activated else 0)

    def set_worker_uptime(self, bridge: str, seconds: float) -> None:
        """Set worker uptime in seconds."""
        self.worker_uptime_seconds.labels(bridge=bridge).set(seconds)

    def set_permanently_failed(self, bridge: str, failed: bool) -> None:
        """Set permanent failure flag."""
        self.worker_permanently_failed.labels(bridge=bridge).set(1 if failed else 0)


__all__ = ["MCPWorkerMetricsRecorder"]
