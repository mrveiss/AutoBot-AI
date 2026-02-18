# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Error Metrics Collection and Monitoring

Tracks error occurrences, aggregates statistics, and provides monitoring data
for the error handling system. Integrates with error_boundaries and error_catalog.
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from autobot_shared.error_boundaries import ErrorCategory

logger = logging.getLogger(__name__)

# Thread-safe imports
import threading


@dataclass
class ErrorMetric:
    """
    Single error occurrence metric

    DEPRECATED (Phase 5, Issue #348): No longer used. Metrics stored in Prometheus only.
    Kept for backward compatibility.
    """

    error_code: Optional[str]
    category: str
    component: str
    function: str
    timestamp: float
    message: str
    trace_id: Optional[str] = None
    user_id: Optional[str] = None
    retry_attempted: bool = False
    resolved: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class ErrorStats:
    """
    Aggregated error statistics

    DEPRECATED (Phase 5, Issue #348): No longer used. Query Prometheus for stats.
    Kept for backward compatibility.
    """

    error_code: Optional[str]
    category: str
    component: str
    total_count: int = 0
    last_occurrence: Optional[float] = None
    first_occurrence: Optional[float] = None
    hourly_counts: Dict[str, int] = field(default_factory=dict)
    retry_count: int = 0
    resolved_count: int = 0
    error_rate: float = 0.0  # errors per minute

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)


class ErrorMetricsCollector:
    """
    Collects and aggregates error metrics

    Phase 5 (Issue #348): Refactored to use Prometheus as the single source of truth.
    All metrics are stored in Prometheus only. In-memory buffers have been removed.

    Features:
    - Error recording to Prometheus
    - Alerting threshold detection
    - Integration with monitoring alerts system
    """

    def __init__(self, redis_client=None):
        """
        Initialize error metrics collector

        Args:
            redis_client: DEPRECATED - no longer used (kept for API compatibility)
        """
        # Phase 5 (Issue #348): Redis persistence removed, arg kept for API compat
        if redis_client is not None:
            logger.warning(
                "redis_client parameter is deprecated and ignored. "
                "Prometheus is now the primary metrics store."
            )

        # Phase 5 (Issue #348): Keep only alert thresholds and lock
        self._alert_thresholds: Dict[str, int] = {}
        self._lock = asyncio.Lock()

        # Track last error count per component for threshold checking
        self._last_error_counts: Dict[str, int] = defaultdict(int)

        # Phase 2 (Issue #345): Prometheus integration - primary metrics store
        try:
            from monitoring.prometheus_metrics import get_metrics_manager

            self.prometheus = get_metrics_manager()
        except (ImportError, Exception) as e:
            logger.warning("Prometheus metrics not available: %s", e)
            self.prometheus = None

    async def record_error(
        self,
        error_code: Optional[str],
        category: ErrorCategory,
        component: str,
        function: str,
        message: str,
        trace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        retry_attempted: bool = False,
    ) -> None:
        """
        Record an error occurrence

        Phase 5 (Issue #348): Records to Prometheus only, no in-memory storage.

        Args:
            error_code: Error code from catalog (if applicable)
            category: Error category
            component: Component name
            function: Function name
            message: Error message
            trace_id: Optional trace ID
            user_id: Optional user ID
            retry_attempted: Whether retry was attempted
        """
        # Phase 5 (Issue #348): Record to Prometheus (single source of truth)
        if self.prometheus:
            self.prometheus.record_error(
                category.value, component, error_code or "unknown"
            )

        # Check alert thresholds (increment count for threshold checking)
        async with self._lock:
            threshold_key = f"{component}:{error_code or category.value}"
            self._last_error_counts[threshold_key] += 1
            current_count = self._last_error_counts[threshold_key]

        # Check if threshold exceeded
        await self._check_alerts(component, error_code, current_count)

        logger.debug(
            f"Recorded error metric to Prometheus: {component}/{error_code or category.value}"
        )

    async def _check_alerts(
        self, component: str, error_code: Optional[str], current_count: int
    ) -> None:
        """
        Check if error count exceeds alert thresholds and send notifications

        Phase 5 (Issue #348): Uses simple error count instead of ErrorStats object.
        """
        threshold_key = f"{component}:{error_code or 'any'}"
        threshold = self._alert_thresholds.get(threshold_key, 0)

        if threshold > 0 and current_count >= threshold:
            logger.warning(
                f"⚠️ Error alert threshold exceeded: {threshold_key} "
                f"({current_count} >= {threshold})"
            )
            # Send alert notification via monitoring_alerts system
            await self._send_alert_notification(
                component=component,
                error_code=error_code,
                current_count=current_count,
                threshold=threshold,
            )

    async def _send_alert_notification(
        self,
        component: str,
        error_code: Optional[str],
        current_count: int,
        threshold: int,
    ) -> None:
        """
        Log alert threshold exceeded.

        Issue #69: Alerting is now handled by Prometheus AlertManager.
        Errors recorded to Prometheus will trigger AlertManager rules defined in
        config/prometheus/alertmanager_rules.yml which send notifications via
        the webhook at backend/api/alertmanager_webhook.py.

        This method now only logs the threshold breach for debugging purposes.
        """
        # Determine severity for logging
        ratio = current_count / threshold if threshold > 0 else 1
        if ratio >= 3:
            severity = "critical"
        elif ratio >= 2:
            severity = "high"
        elif ratio >= 1.5:
            severity = "medium"
        else:
            severity = "low"

        logger.warning(
            f"Error threshold exceeded [{severity.upper()}] {component}/{error_code or 'any'}: "
            f"{current_count} errors (threshold: {threshold}). "
            f"AlertManager will handle notifications based on Prometheus metrics."
        )

    async def mark_resolved(self, trace_id: str) -> bool:
        """
        DEPRECATED (Phase 5, Issue #348): No longer supported.

        Resolution tracking should be done via Prometheus labels or external systems.

        Args:
            trace_id: Trace ID of the error

        Returns:
            False (not supported)
        """
        logger.warning(
            "mark_resolved() is deprecated. Use Prometheus labels or external tracking."
        )
        return False

    def get_stats(self, component: Optional[str] = None) -> List[ErrorStats]:
        """
        DEPRECATED (Phase 5, Issue #348): No in-memory stats available.

        Use Prometheus PromQL queries instead:
        - Total errors: sum(autobot_errors_total)
        - By component: sum(autobot_errors_total) by (component)

        Args:
            component: Optional component filter (ignored)

        Returns:
            Empty list (not supported)
        """
        logger.warning(
            "get_stats() is deprecated. Query Prometheus directly:\n"
            "  sum(autobot_errors_total) by (component, category, error_code)"
        )
        return []

    def get_error_timeline(
        self, hours: int = 24, component: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        DEPRECATED (Phase 5, Issue #348): No in-memory timeline available.

        Use Prometheus PromQL queries instead:
        - rate(autobot_errors_total[1h])
        - increase(autobot_errors_total[24h])

        Args:
            hours: Number of hours to include (ignored)
            component: Optional component filter (ignored)

        Returns:
            Empty dict (not supported)
        """
        logger.warning(
            "get_error_timeline() is deprecated. Query Prometheus:\n"
            f"  rate(autobot_errors_total[{hours}h]) or increase(autobot_errors_total[{hours}h])"
        )
        return {}

    def get_category_breakdown(self) -> Dict[str, int]:
        """
        DEPRECATED (Phase 5, Issue #348): No in-memory breakdown available.

        Use Prometheus PromQL query:
        - sum(autobot_errors_total) by (category)

        Returns:
            Empty dict (not supported)
        """
        logger.warning(
            "get_category_breakdown() is deprecated. Query Prometheus:\n"
            "  sum(autobot_errors_total) by (category)"
        )
        return {}

    def get_component_breakdown(self) -> Dict[str, int]:
        """
        DEPRECATED (Phase 5, Issue #348): No in-memory breakdown available.

        Use Prometheus PromQL query:
        - sum(autobot_errors_total) by (component)

        Returns:
            Empty dict (not supported)
        """
        logger.warning(
            "get_component_breakdown() is deprecated. Query Prometheus:\n"
            "  sum(autobot_errors_total) by (component)"
        )
        return {}

    def get_top_errors(self, limit: int = 10) -> List[ErrorStats]:
        """
        DEPRECATED (Phase 5, Issue #348): No in-memory stats available.

        Use Prometheus PromQL query:
        - topk(10, sum(autobot_errors_total) by (error_code, component))

        Args:
            limit: Number of top errors to return (ignored)

        Returns:
            Empty list (not supported)
        """
        logger.warning(
            f"get_top_errors() is deprecated. Query Prometheus:\n"
            f"  topk({limit}, sum(autobot_errors_total) by (error_code, component))"
        )
        return []

    def set_alert_threshold(
        self, component: str, error_code: Optional[str], threshold: int
    ) -> None:
        """
        Set alert threshold for a component/error combination

        Args:
            component: Component name
            error_code: Error code (or None for any error in component)
            threshold: Error count threshold for alerts
        """
        threshold_key = f"{component}:{error_code or 'any'}"
        self._alert_thresholds[threshold_key] = threshold
        logger.info("Set alert threshold: %s = %s", threshold_key, threshold)

    async def cleanup_old_metrics(self) -> int:
        """
        DEPRECATED (Phase 5, Issue #348): No in-memory metrics to clean up.

        Prometheus handles retention automatically via its configuration.

        Returns:
            0 (not supported)
        """
        logger.warning(
            "cleanup_old_metrics() is deprecated. "
            "Configure Prometheus retention in prometheus.yml instead."
        )
        return 0

    def get_summary(self) -> Dict[str, Any]:
        """
        DEPRECATED (Phase 5, Issue #348): No in-memory summary available.

        Use Prometheus PromQL queries for comprehensive metrics:
        - Total errors: sum(autobot_errors_total)
        - By category: sum(autobot_errors_total) by (category)
        - By component: sum(autobot_errors_total) by (component)
        - Top errors: topk(5, sum(autobot_errors_total) by (error_code))

        Returns:
            Minimal summary indicating deprecated status
        """
        logger.warning(
            "get_summary() is deprecated. Query Prometheus for comprehensive metrics."
        )
        return {
            "status": "deprecated",
            "message": "Use Prometheus PromQL queries for error metrics",
            "prometheus_available": self.prometheus is not None,
            "alert_thresholds_configured": len(self._alert_thresholds),
        }

    async def reset_stats(self, component: Optional[str] = None) -> None:
        """
        DEPRECATED (Phase 5, Issue #348): No in-memory stats to reset.

        To reset Prometheus metrics, restart the application or use Prometheus
        administrative APIs.

        Args:
            component: Optional component to reset (ignored)
        """
        logger.warning(
            "reset_stats() is deprecated. Restart application or use Prometheus admin APIs."
        )
        # Only reset local counter for threshold checking
        async with self._lock:
            if component:
                keys_to_remove = [
                    key
                    for key in self._last_error_counts.keys()
                    if key.startswith(f"{component}:")
                ]
                for key in keys_to_remove:
                    del self._last_error_counts[key]
                logger.info("Reset threshold counters for component: %s", component)
            else:
                self._last_error_counts.clear()
                logger.info("Reset all threshold counters")


# Global metrics collector instance (thread-safe)
_metrics_collector: Optional[ErrorMetricsCollector] = None
_metrics_collector_lock = threading.Lock()


def get_metrics_collector(redis_client=None) -> ErrorMetricsCollector:
    """
    Get global metrics collector instance (thread-safe)

    Args:
        redis_client: Optional Redis client for persistence

    Returns:
        ErrorMetricsCollector instance
    """
    global _metrics_collector

    if _metrics_collector is None:
        with _metrics_collector_lock:
            # Double-check after acquiring lock
            if _metrics_collector is None:
                _metrics_collector = ErrorMetricsCollector(redis_client)

    return _metrics_collector


async def record_error_metric(
    error_code: Optional[str],
    category: ErrorCategory,
    component: str,
    function: str,
    message: str,
    **kwargs,
) -> None:
    """
    Convenience function to record error metric

    Args:
        error_code: Error code from catalog
        category: Error category
        component: Component name
        function: Function name
        message: Error message
        **kwargs: Additional metric fields
    """
    collector = get_metrics_collector()
    await collector.record_error(
        error_code, category, component, function, message, **kwargs
    )
