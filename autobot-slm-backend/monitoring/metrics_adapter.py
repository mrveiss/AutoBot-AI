# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Metrics Adapter for Phase 1 Migration (Issue #344)

Provides dual-write capability during monitoring consolidation.
Writes to both Prometheus and legacy systems during transition.
"""

import logging
import threading
from typing import Optional

from monitoring.prometheus_metrics import get_metrics_manager

logger = logging.getLogger(__name__)


class MetricsAdapter:
    """
    Dual-write adapter for metric migration period.

    During Phase 1-2, writes metrics to both:
    - PrometheusMetricsManager (new system)
    - Legacy metric collectors (old system)

    This ensures zero downtime during migration.
    """

    def __init__(self):
        """Initialize metrics adapter bridging Prometheus and legacy systems."""
        self.prometheus = get_metrics_manager()
        self._legacy_system_metrics = None
        self._legacy_error_metrics = None
        self._legacy_claude_monitor = None

    def _get_legacy_system_metrics(self):
        """Lazy load legacy SystemMetricsCollector"""
        if self._legacy_system_metrics is None:
            try:
                from utils.system_metrics import SystemMetricsCollector

                self._legacy_system_metrics = SystemMetricsCollector()
            except ImportError:
                logger.warning(
                    "Legacy SystemMetricsCollector not available for dual-write"
                )
        return self._legacy_system_metrics

    def _get_legacy_error_metrics(self):
        """Lazy load legacy ErrorMetricsCollector"""
        if self._legacy_error_metrics is None:
            try:
                from utils.error_metrics import ErrorMetricsCollector

                # ErrorMetricsCollector may require redis_client parameter
                self._legacy_error_metrics = ErrorMetricsCollector()
            except ImportError:
                logger.warning(
                    "Legacy ErrorMetricsCollector not available for dual-write"
                )
        return self._legacy_error_metrics

    def _get_legacy_claude_monitor(self):
        """Lazy load legacy ClaudeAPIMonitor"""
        if self._legacy_claude_monitor is None:
            try:
                from monitoring.claude_api_monitor import ClaudeAPIMonitor

                self._legacy_claude_monitor = ClaudeAPIMonitor()
            except ImportError:
                logger.warning("Legacy ClaudeAPIMonitor not available for dual-write")
        return self._legacy_claude_monitor

    # System Metrics

    def record_system_cpu(self, cpu_percent: float):
        """Record CPU usage to both systems"""
        # Write to Prometheus (primary)
        self.prometheus.update_system_cpu(cpu_percent)

        # Write to legacy system (during migration)
        legacy = self._get_legacy_system_metrics()
        if legacy and hasattr(legacy, "record_cpu_usage"):
            try:
                legacy.record_cpu_usage(cpu_percent)
            except Exception as e:
                logger.debug("Legacy CPU recording failed: %s", e)

    def record_system_memory(self, memory_percent: float):
        """Record memory usage to both systems"""
        # Write to Prometheus (primary)
        self.prometheus.update_system_memory(memory_percent)

        # Write to legacy system (during migration)
        legacy = self._get_legacy_system_metrics()
        if legacy and hasattr(legacy, "record_memory_usage"):
            try:
                legacy.record_memory_usage(memory_percent)
            except Exception as e:
                logger.debug("Legacy memory recording failed: %s", e)

    def record_system_disk(self, mount_point: str, disk_percent: float):
        """Record disk usage to both systems"""
        # Write to Prometheus (primary)
        self.prometheus.update_system_disk(mount_point, disk_percent)

        # Write to legacy system (during migration)
        legacy = self._get_legacy_system_metrics()
        if legacy and hasattr(legacy, "record_disk_usage"):
            try:
                legacy.record_disk_usage(mount_point, disk_percent)
            except Exception as e:
                logger.debug("Legacy disk recording failed: %s", e)

    def record_network_bytes(self, direction: str, bytes_count: int):
        """Record network bytes to both systems"""
        # Write to Prometheus (primary)
        self.prometheus.record_network_bytes(direction, bytes_count)

        # Write to legacy system (during migration)
        legacy = self._get_legacy_system_metrics()
        if legacy and hasattr(legacy, "record_network_bytes"):
            try:
                legacy.record_network_bytes(direction, bytes_count)
            except Exception as e:
                logger.debug("Legacy network recording failed: %s", e)

    # Error Metrics

    def record_error(
        self, category: str, component: str, error_code: str = "unknown", **kwargs
    ):
        """Record error to both systems"""
        # Write to Prometheus (primary)
        self.prometheus.record_error(category, component, error_code)

        # Write to legacy system (during migration)
        legacy = self._get_legacy_error_metrics()
        if legacy and hasattr(legacy, "record_error"):
            try:
                legacy.record_error(category, component, error_code, **kwargs)
            except Exception as e:
                logger.debug("Legacy error recording failed: %s", e)

    def update_error_rate(self, component: str, time_window: str, rate: float):
        """Update error rate in both systems"""
        # Write to Prometheus (primary)
        self.prometheus.update_error_rate(component, time_window, rate)

        # Legacy system may not have this method - skip if not available

    # Claude API Metrics

    def record_claude_api_request(
        self, tool_name: str, success: bool, payload_bytes: Optional[int] = None
    ):
        """Record Claude API request to both systems"""
        # Write to Prometheus (primary)
        self.prometheus.record_claude_api_request(tool_name, success)
        if payload_bytes:
            self.prometheus.record_claude_api_payload(payload_bytes)

        # Write to legacy system (during migration)
        legacy = self._get_legacy_claude_monitor()
        if legacy and hasattr(legacy, "record_request"):
            try:
                legacy.record_request(tool_name, success, payload_bytes)
            except Exception as e:
                logger.debug("Legacy Claude API recording failed: %s", e)

    def record_claude_api_response_time(self, response_time_seconds: float):
        """Record Claude API response time to both systems"""
        # Write to Prometheus (primary)
        self.prometheus.record_claude_api_response_time(response_time_seconds)

        # Write to legacy system (during migration)
        legacy = self._get_legacy_claude_monitor()
        if legacy and hasattr(legacy, "record_response_time"):
            try:
                legacy.record_response_time(response_time_seconds)
            except Exception as e:
                logger.debug("Legacy Claude API response time recording failed: %s", e)

    def update_claude_api_rate_limit(self, remaining: int):
        """Update Claude API rate limit in both systems"""
        # Write to Prometheus (primary)
        self.prometheus.update_claude_api_rate_limit(remaining)

        # Write to legacy system (during migration)
        legacy = self._get_legacy_claude_monitor()
        if legacy and hasattr(legacy, "update_rate_limit"):
            try:
                legacy.update_rate_limit(remaining)
            except Exception as e:
                logger.debug("Legacy Claude API rate limit update failed: %s", e)

    # Service Health Metrics

    def record_service_health(
        self, service_name: str, health_score: float, status: str = "online"
    ):
        """Record service health to both systems"""
        # Write to Prometheus (primary)
        self.prometheus.update_service_health(service_name, health_score)
        self.prometheus.update_service_status(service_name, status)

        # Legacy system may not have this method - skip if not available

    def record_service_response_time(self, service_name: str, response_time: float):
        """Record service response time to both systems"""
        # Write to Prometheus (primary)
        self.prometheus.record_service_response_time(service_name, response_time)

        # Legacy system may not have this method - skip if not available


# Global adapter instance (thread-safe)
_adapter_instance: Optional[MetricsAdapter] = None
_adapter_instance_lock = threading.Lock()


def get_metrics_adapter() -> MetricsAdapter:
    """Get or create global metrics adapter (thread-safe)."""
    global _adapter_instance
    if _adapter_instance is None:
        with _adapter_instance_lock:
            # Double-check after acquiring lock
            if _adapter_instance is None:
                _adapter_instance = MetricsAdapter()
    return _adapter_instance
