# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Health Metrics Recorder

Metrics for service health monitoring.
Extracted from PrometheusMetricsManager as part of Issue #394.
"""

from prometheus_client import CollectorRegistry, Gauge, Histogram

from .base import BaseMetricsRecorder

# Service status value mapping
# Maps status strings to numeric values for Prometheus metrics
# 0 = down/offline, 1 = up/healthy, 2 = warning/degraded
_SERVICE_STATUS_VALUES = {
    "offline": 0,
    "error": 0,
    "critical": 0,
    "online": 1,
    "healthy": 1,
    "up": 1,
    "warning": 2,
    "degraded": 2,
}


class ServiceHealthMetricsRecorder(BaseMetricsRecorder):
    """Recorder for service health metrics."""

    def _init_metrics(self) -> None:
        """Initialize service health metrics."""
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

    def update_health(self, service_name: str, health_score: float) -> None:
        """Update service health score."""
        self.service_health_score.labels(service_name=service_name).set(health_score)

    def record_response_time(self, service_name: str, response_time: float) -> None:
        """Record service response time."""
        self.service_response_time.labels(service_name=service_name).observe(
            response_time
        )

    def update_status(self, service_name: str, status: str) -> None:
        """Update service status."""
        status_value = _SERVICE_STATUS_VALUES.get(status.lower(), 0)
        self.service_status.labels(service_name=service_name, status=status).set(
            status_value
        )


__all__ = ["ServiceHealthMetricsRecorder"]
