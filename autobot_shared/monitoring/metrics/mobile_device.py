# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Mobile Device Pairing Metrics Recorder

Metrics for mobile device pairing, push notifications, and device management.
Created as part of GH#4463 - Mobile Device Pairing for Push Notifications.

Covers:
- Pairing attempts (success, expired, invalid)
- Push notification delivery (per platform)
- Device cleanup operations
- Active device count (per platform)
"""

from prometheus_client import Counter, Gauge

from .base import BaseMetricsRecorder


class MobileDeviceMetricsRecorder(BaseMetricsRecorder):
    """Recorder for mobile device pairing and push notification metrics."""

    def _init_metrics(self) -> None:
        """Initialize mobile device metrics.

        Delegates to helper methods for each metric category.
        """
        self._init_pairing_metrics()
        self._init_push_metrics()
        self._init_cleanup_metrics()
        self._init_device_count_metrics()

    def _init_pairing_metrics(self) -> None:
        """Initialize device pairing metrics."""
        self.pairing_attempts_total = Counter(
            "autobot_device_pairing_attempts_total",
            "Total device pairing attempts",
            ["status"],  # status: success, expired, invalid
            registry=self.registry,
        )

    def _init_push_metrics(self) -> None:
        """Initialize push notification metrics."""
        self.push_sent_total = Counter(
            "autobot_device_push_sent_total",
            "Total push notifications sent to mobile devices",
            ["platform", "status"],  # platform: ios, android, pwa; status: success, failure
            registry=self.registry,
        )

    def _init_cleanup_metrics(self) -> None:
        """Initialize cleanup job metrics."""
        self.cleanup_removed_total = Counter(
            "autobot_device_cleanup_removed_total",
            "Total stale devices removed by cleanup job",
            registry=self.registry,
        )

    def _init_device_count_metrics(self) -> None:
        """Initialize active device count metrics."""
        self.active_device_count = Gauge(
            "autobot_device_active_count",
            "Current number of active paired devices",
            ["platform"],  # platform: ios, android, pwa
            registry=self.registry,
        )

    # =========================================================================
    # Pairing Methods
    # =========================================================================

    def record_pairing_attempt(self, status: str) -> None:
        """Record a device pairing attempt.

        Args:
            status: Pairing status - "success", "expired", or "invalid"
        """
        self.pairing_attempts_total.labels(status=status).inc()

    # =========================================================================
    # Push Notification Methods
    # =========================================================================

    def record_push_sent(self, platform: str, status: str) -> None:
        """Record a push notification sent to a mobile device.

        Args:
            platform: Device platform - "ios", "android", or "pwa"
            status: Delivery status - "success" or "failure"
        """
        self.push_sent_total.labels(platform=platform, status=status).inc()

    # =========================================================================
    # Cleanup Methods
    # =========================================================================

    def record_cleanup_removed(self, count: int) -> None:
        """Record devices removed by the cleanup job.

        Args:
            count: Number of devices removed
        """
        self.cleanup_removed_total.inc(count)

    # =========================================================================
    # Device Count Methods
    # =========================================================================

    def set_active_device_count(self, platform: str, count: int) -> None:
        """Set the current number of active devices for a platform.

        Args:
            platform: Device platform - "ios", "android", or "pwa"
            count: Number of active devices
        """
        self.active_device_count.labels(platform=platform).set(count)


__all__ = ["MobileDeviceMetricsRecorder"]
