# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Stub Prometheus Metrics for AutoBot user backend.

This is a stub implementation that provides no-op metrics recording
until full Prometheus integration is migrated (Issue #781 fallout).

The real implementation is in autobot-slm-backend/monitoring/prometheus_metrics.py.
TODO: Merge monitoring implementations or create shared monitoring package.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PrometheusMetricsManager:
    """
    Stub Prometheus metrics manager with no-op methods.

    Provides the same interface as the real implementation but
    does nothing - useful for development/testing without Prometheus.
    """

    _instance: Optional["PrometheusMetricsManager"] = None

    def __new__(cls):
        """Singleton pattern for metrics manager."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize stub metrics manager."""
        if self._initialized:
            return
        self._initialized = True
        logger.debug("Stub PrometheusMetricsManager initialized (no-op)")

    def record_request(
        self,
        database: str = "default",
        operation: str = "general",
        success: bool = True,
        latency_ms: float = 0.0,
        **kwargs: Any
    ) -> None:
        """Record a request metric (no-op stub)."""

    def record_circuit_breaker_event(
        self, database: str = "default", event: str = "trip", **kwargs: Any
    ) -> None:
        """Record a circuit breaker event (no-op stub)."""

    def record_latency(
        self,
        operation: str,
        latency_ms: float,
        labels: Optional[Dict[str, str]] = None,
        **kwargs: Any
    ) -> None:
        """Record latency metric (no-op stub)."""

    def record_timeout(
        self, operation: str, timeout_type: str = "operation", **kwargs: Any
    ) -> None:
        """Record timeout metric (no-op stub)."""

    def record_error(self, operation: str, error_type: str, **kwargs: Any) -> None:
        """Record error metric (no-op stub)."""

    def record_success(self, operation: str, **kwargs: Any) -> None:
        """Record success metric (no-op stub)."""

    def inc_counter(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        value: float = 1.0,
        **kwargs: Any
    ) -> None:
        """Increment counter (no-op stub)."""

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        **kwargs: Any
    ) -> None:
        """Set gauge value (no-op stub)."""

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        **kwargs: Any
    ) -> None:
        """Observe histogram value (no-op stub)."""

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics (stub returns empty dict)."""
        return {}

    def generate_latest(self) -> str:
        """Generate Prometheus format output (stub returns empty string)."""
        return ""

    # Issue #876: Missing methods called by system_metrics.py and multimodal_performance_monitor.py
    def update_system_cpu(self, cpu_percent: float, **kwargs: Any) -> None:
        """Update system CPU usage metric (no-op stub)."""

    def update_system_memory(self, memory_percent: float, **kwargs: Any) -> None:
        """Update system memory usage metric (no-op stub)."""

    def update_system_disk(self, path: str, disk_percent: float, **kwargs: Any) -> None:
        """Update system disk usage metric (no-op stub)."""

    def record_network_bytes(
        self, direction: str, bytes_count: int, **kwargs: Any
    ) -> None:
        """Record network bytes sent/received (no-op stub)."""

    def update_service_status(self, service: str, status: str, **kwargs: Any) -> None:
        """Update service health status (no-op stub)."""

    def record_service_response_time(
        self, service: str, response_time: float, **kwargs: Any
    ) -> None:
        """Record service response time (no-op stub)."""

    def set_gpu_available(self, available: bool, **kwargs: Any) -> None:
        """Set GPU availability status (no-op stub)."""

    def update_gpu_metrics(
        self,
        gpu_id: int,
        gpu_name: str,
        utilization: float,
        memory_utilization: float,
        temperature: float,
        power_watts: float,
        **kwargs: Any
    ) -> None:
        """Update GPU metrics (no-op stub)."""

    def record_multimodal_processing(
        self, modality: str, processing_time: float, success: bool, **kwargs: Any
    ) -> None:
        """Record multimodal processing metrics (no-op stub)."""


# Singleton instance
_metrics_manager: Optional[PrometheusMetricsManager] = None


def get_metrics_manager() -> PrometheusMetricsManager:
    """
    Get the singleton PrometheusMetricsManager instance.

    Returns:
        PrometheusMetricsManager: The stub metrics manager instance
    """
    global _metrics_manager
    if _metrics_manager is None:
        _metrics_manager = PrometheusMetricsManager()
    return _metrics_manager
