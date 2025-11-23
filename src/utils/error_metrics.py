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
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json

from src.utils.error_catalog import get_error, ErrorDefinition
from src.utils.error_boundaries import ErrorCategory

logger = logging.getLogger(__name__)


@dataclass
class ErrorMetric:
    """Single error occurrence metric"""

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
    """Aggregated error statistics"""

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

    Features:
    - Real-time error tracking
    - Time-series aggregation
    - Component-level statistics
    - Alerting threshold detection
    - Redis-backed persistence
    """

    def __init__(self, redis_client=None):
        """
        Initialize error metrics collector

        Args:
            redis_client: Optional Redis client for persistence
        """
        self._redis = redis_client
        self._metrics: List[ErrorMetric] = []
        self._stats: Dict[str, ErrorStats] = defaultdict(self._create_stats)
        self._alert_thresholds: Dict[str, int] = {}
        self._max_metrics_memory = 10000  # Keep last 10k metrics in memory

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

        # Metrics retention (24 hours)
        self._retention_seconds = 86400

    def _create_stats(self) -> ErrorStats:
        """Create default ErrorStats instance"""
        return ErrorStats(error_code=None, category="unknown", component="unknown")

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
        timestamp = time.time()

        # Create metric
        metric = ErrorMetric(
            error_code=error_code,
            category=category.value,
            component=component,
            function=function,
            timestamp=timestamp,
            message=message,
            trace_id=trace_id,
            user_id=user_id,
            retry_attempted=retry_attempted,
        )

        async with self._lock:
            # Add to metrics list
            self._metrics.append(metric)

            # Trim old metrics from memory
            if len(self._metrics) > self._max_metrics_memory:
                self._metrics = self._metrics[-self._max_metrics_memory :]

            # Update stats
            stats_key = f"{component}:{error_code or category.value}"
            stats = self._stats[stats_key]

            if stats.error_code is None:
                stats.error_code = error_code
                stats.category = category.value
                stats.component = component

            stats.total_count += 1
            stats.last_occurrence = timestamp

            if stats.first_occurrence is None:
                stats.first_occurrence = timestamp

            if retry_attempted:
                stats.retry_count += 1

            # Update hourly counts
            hour_key = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:00")
            stats.hourly_counts[hour_key] = stats.hourly_counts.get(hour_key, 0) + 1

            # Calculate error rate (errors per minute over last hour)
            one_hour_ago = timestamp - 3600
            recent_count = sum(1 for m in self._metrics if m.timestamp > one_hour_ago)
            stats.error_rate = recent_count / 60.0

        # Persist to Redis if available
        if self._redis:
            await self._persist_metric(metric)

        # Check alert thresholds
        await self._check_alerts(component, error_code, stats)

        logger.debug(
            f"Recorded error metric: {component}/{error_code or category.value}"
        )

    async def _persist_metric(self, metric: ErrorMetric) -> None:
        """Persist metric to Redis"""
        try:
            if not self._redis:
                return

            # Store in Redis sorted set (by timestamp)
            key = f"error_metrics:{metric.component}"
            score = metric.timestamp
            value = json.dumps(metric.to_dict())

            await self._redis.zadd(key, {value: score})

            # Set expiration
            await self._redis.expire(key, self._retention_seconds)

        except Exception as e:
            logger.warning(f"Failed to persist metric to Redis: {e}")

    async def _check_alerts(
        self, component: str, error_code: Optional[str], stats: ErrorStats
    ) -> None:
        """Check if error stats exceed alert thresholds"""
        threshold_key = f"{component}:{error_code or 'any'}"
        threshold = self._alert_thresholds.get(threshold_key, 0)

        if threshold > 0 and stats.total_count >= threshold:
            logger.warning(
                f"⚠️ Error alert threshold exceeded: {threshold_key} "
                f"({stats.total_count} >= {threshold})"
            )
            # TODO: Send alert notification

    async def mark_resolved(self, trace_id: str) -> bool:
        """
        Mark an error as resolved

        Args:
            trace_id: Trace ID of the error

        Returns:
            True if error was found and marked resolved
        """
        async with self._lock:
            for metric in self._metrics:
                if metric.trace_id == trace_id:
                    metric.resolved = True

                    # Update stats
                    stats_key = (
                        f"{metric.component}:{metric.error_code or metric.category}"
                    )
                    if stats_key in self._stats:
                        self._stats[stats_key].resolved_count += 1

                    return True

        return False

    def get_stats(self, component: Optional[str] = None) -> List[ErrorStats]:
        """
        Get error statistics

        Args:
            component: Optional component filter

        Returns:
            List of ErrorStats
        """
        if component:
            return [
                stats
                for key, stats in self._stats.items()
                if stats.component == component
            ]
        else:
            return list(self._stats.values())

    def get_recent_errors(
        self, limit: int = 100, component: Optional[str] = None
    ) -> List[ErrorMetric]:
        """
        Get recent error metrics

        Args:
            limit: Maximum number of metrics to return
            component: Optional component filter

        Returns:
            List of recent ErrorMetric objects
        """
        metrics = self._metrics

        if component:
            metrics = [m for m in metrics if m.component == component]

        # Return most recent first
        return sorted(metrics, key=lambda m: m.timestamp, reverse=True)[:limit]

    def get_error_timeline(
        self, hours: int = 24, component: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get error timeline data for visualization

        Args:
            hours: Number of hours to include
            component: Optional component filter

        Returns:
            Dictionary mapping hour keys to error lists
        """
        cutoff = time.time() - (hours * 3600)
        recent_metrics = [m for m in self._metrics if m.timestamp > cutoff]

        if component:
            recent_metrics = [m for m in recent_metrics if m.component == component]

        timeline: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for metric in recent_metrics:
            hour_key = datetime.fromtimestamp(metric.timestamp).strftime(
                "%Y-%m-%d %H:00"
            )
            timeline[hour_key].append(
                {
                    "category": metric.category,
                    "component": metric.component,
                    "error_code": metric.error_code,
                    "message": metric.message,
                }
            )

        return dict(timeline)

    def get_category_breakdown(self) -> Dict[str, int]:
        """Get error count breakdown by category"""
        breakdown: Dict[str, int] = defaultdict(int)

        for stats in self._stats.values():
            breakdown[stats.category] += stats.total_count

        return dict(breakdown)

    def get_component_breakdown(self) -> Dict[str, int]:
        """Get error count breakdown by component"""
        breakdown: Dict[str, int] = defaultdict(int)

        for stats in self._stats.values():
            breakdown[stats.component] += stats.total_count

        return dict(breakdown)

    def get_top_errors(self, limit: int = 10) -> List[ErrorStats]:
        """
        Get top N most frequent errors

        Args:
            limit: Number of top errors to return

        Returns:
            List of ErrorStats sorted by frequency
        """
        return sorted(self._stats.values(), key=lambda s: s.total_count, reverse=True)[
            :limit
        ]

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
        logger.info(f"Set alert threshold: {threshold_key} = {threshold}")

    async def cleanup_old_metrics(self) -> int:
        """
        Clean up old metrics beyond retention period

        Returns:
            Number of metrics removed
        """
        cutoff = time.time() - self._retention_seconds

        async with self._lock:
            original_count = len(self._metrics)
            self._metrics = [m for m in self._metrics if m.timestamp > cutoff]
            removed = original_count - len(self._metrics)

        if removed > 0:
            logger.info(f"Cleaned up {removed} old error metrics")

        return removed

    def get_summary(self) -> Dict[str, Any]:
        """
        Get overall error metrics summary

        Returns:
            Summary dictionary with key metrics
        """
        total_errors = sum(s.total_count for s in self._stats.values())
        total_retries = sum(s.retry_count for s in self._stats.values())
        total_resolved = sum(s.resolved_count for s in self._stats.values())

        # Calculate average error rate
        error_rates = [s.error_rate for s in self._stats.values() if s.error_rate > 0]
        avg_error_rate = sum(error_rates) / len(error_rates) if error_rates else 0.0

        return {
            "total_errors": total_errors,
            "unique_error_types": len(self._stats),
            "total_retries": total_retries,
            "total_resolved": total_resolved,
            "avg_error_rate": round(avg_error_rate, 2),
            "category_breakdown": self.get_category_breakdown(),
            "component_breakdown": self.get_component_breakdown(),
            "top_errors": [s.to_dict() for s in self.get_top_errors(5)],
            "metrics_in_memory": len(self._metrics),
        }

    async def reset_stats(self, component: Optional[str] = None) -> None:
        """
        Reset error statistics

        Args:
            component: Optional component to reset (None = reset all)
        """
        async with self._lock:
            if component:
                # Reset only specified component
                keys_to_remove = [
                    key
                    for key, stats in self._stats.items()
                    if stats.component == component
                ]
                for key in keys_to_remove:
                    del self._stats[key]

                self._metrics = [m for m in self._metrics if m.component != component]

                logger.info(f"Reset error metrics for component: {component}")
            else:
                # Reset all
                self._stats.clear()
                self._metrics.clear()
                logger.info("Reset all error metrics")


# Global metrics collector instance
_metrics_collector: Optional[ErrorMetricsCollector] = None


def get_metrics_collector(redis_client=None) -> ErrorMetricsCollector:
    """
    Get global metrics collector instance

    Args:
        redis_client: Optional Redis client for persistence

    Returns:
        ErrorMetricsCollector instance
    """
    global _metrics_collector

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
