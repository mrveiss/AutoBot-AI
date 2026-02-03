# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Metrics Recorder

Metrics for system resource monitoring.
Extracted from PrometheusMetricsManager as part of Issue #394.
"""

from prometheus_client import CollectorRegistry, Counter, Gauge

from .base import BaseMetricsRecorder


class SystemMetricsRecorder(BaseMetricsRecorder):
    """Recorder for system resource metrics."""

    def _init_metrics(self) -> None:
        """Initialize system metrics."""
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

    def update_cpu(self, cpu_percent: float) -> None:
        """Update CPU usage metric."""
        self.system_cpu_usage.set(cpu_percent)

    def update_memory(self, memory_percent: float) -> None:
        """Update memory usage metric."""
        self.system_memory_usage.set(memory_percent)

    def update_disk(self, mount_point: str, disk_percent: float) -> None:
        """Update disk usage metric."""
        self.system_disk_usage.labels(mount_point=mount_point).set(disk_percent)

    def record_network_bytes(self, direction: str, bytes_count: int) -> None:
        """Record network bytes transferred."""
        self.system_network_bytes.labels(direction=direction).inc(bytes_count)


__all__ = ["SystemMetricsRecorder"]
