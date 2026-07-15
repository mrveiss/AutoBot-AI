#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Claude API Usage Monitoring and Tracking System

DEPRECATED (Phase 5, Issue #348): This entire module is deprecated.
Claude API metrics are now tracked in PrometheusMetricsManager.
The in-memory deque buffers and local tracking are no longer needed.

For Claude API metrics, use:
- Prometheus: autobot_claude_api_requests_total, autobot_claude_api_response_time_seconds
- Grafana dashboard: autobot-claude-api
- REST API: /api/metrics/claude-api/status (deprecated, use Grafana)

This module remains for backwards compatibility but will be REMOVED in v3.0.
"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# Lazy-loaded reference to the shared Prometheus query helper (#10721).
# Set once on first call; patchable in tests without triggering ssot_config.
_prometheus_query_instant = None


def _get_prometheus_query_instant():
    """Return ``query_instant`` from autobot_shared, caching after first load.

    Returns ``None`` if the shared module is not importable (e.g. in CI
    environments where ssot_config is not wired).  Callers must treat
    ``None`` as "Prometheus unavailable → return 0.0".
    """
    global _prometheus_query_instant
    if _prometheus_query_instant is None:
        try:
            from autobot_shared.monitoring.prometheus_query import query_instant

            _prometheus_query_instant = query_instant
        except Exception:  # ImportError or config-init failure
            pass
    return _prometheus_query_instant


@dataclass
class APICallRecord:
    """Record of a single API call"""

    timestamp: float
    payload_size: int
    response_size: int
    response_time: float
    success: bool
    error_type: str | None = None
    tool_name: str | None = None
    context: str | None = None


@dataclass
class UsageAlert:
    """Alert for API usage concerns"""

    timestamp: float
    level: str  # warning, critical, info
    message: str
    metrics: Dict[str, Any]
    recommendation: str


class UsageTracker:
    """
    Tracks API usage patterns and calculates metrics

    DEPRECATED (Phase 5, Issue #348): All in-memory buffers removed.
    ``calculate_usage_rate`` now queries Prometheus. Use PrometheusMetricsManager.
    """

    def __init__(self, history_limit: int = 1000):
        """Initialize usage tracker with history limit and counters."""
        self.history_limit = history_limit
        # REMOVED (Phase 5, Issue #348): self.call_history = deque(maxlen=history_limit)
        # REMOVED (Phase 5, Issue #348): self.tool_usage = defaultdict(list)
        self.error_patterns = defaultdict(int)
        self._stats_lock = threading.Lock()  # Lock for thread-safe stats access

        # Performance metrics
        self.total_calls = 0
        self.total_payload_size = 0
        self.total_response_size = 0
        self.total_response_time = 0.0

        import warnings

        warnings.warn(
            "UsageTracker is deprecated. All in-memory tracking removed. "
            "Use PrometheusMetricsManager for metrics. Will be removed in v3.0.",
            DeprecationWarning,
            stacklevel=2,
        )

    def add_call(self, record: APICallRecord):
        """
        Add a new API call record (thread-safe)

        DEPRECATED (Phase 5, Issue #348): No-op. Use PrometheusMetricsManager.record_claude_api_request()
        """
        # REMOVED (Phase 5, Issue #348): All deque append operations removed
        # Only update basic counters for backwards compatibility
        with self._stats_lock:
            self.total_calls += 1
            self.total_payload_size += record.payload_size
            self.total_response_size += record.response_size
            self.total_response_time += record.response_time

            # Track error patterns (no memory growth - dict only)
            if not record.success and record.error_type:
                self.error_patterns[record.error_type] += 1

    async def calculate_usage_rate(self, window_minutes: int = 60) -> float:
        """Calculate calls per minute in the given window.

        Backed by Prometheus ``autobot_claude_api_requests_total`` via
        ``increase()`` over the requested window (#10721 — replaces the
        removed in-memory deque).  Returns 0.0 when Prometheus is
        unreachable; never silently fabricates data.
        """
        query_instant = _get_prometheus_query_instant()
        if query_instant is None:
            return 0.0

        # Clamp to 1-minute minimum so PromQL window is always valid.
        window = f"{max(window_minutes, 1)}m"
        promql = f"sum(increase(autobot_claude_api_requests_total[{window}]))"
        data = await query_instant(promql)
        if data is None or not data.get("result"):
            return 0.0
        try:
            total_calls = float(data["result"][0]["value"][1])
            if window_minutes == 0:
                return total_calls
            return total_calls / window_minutes
        except (IndexError, KeyError, ValueError):
            return 0.0


class AlertManager:
    """
    Manages alerts and warnings for API usage

    DEPRECATED (Phase 5, Issue #348): All in-memory buffers removed.
    Methods return empty/safe defaults. Use Prometheus Alertmanager.
    """

    def __init__(self, alert_cooldown: int = 300):  # 5 minutes
        """Initialize alert manager with cooldown period and callbacks."""
        self.alert_cooldown = alert_cooldown
        self.last_alerts = {}
        # REMOVED (Phase 5, Issue #348): self.alert_history = deque(maxlen=100)
        self.alert_callbacks: List[Callable] = []

        import warnings

        warnings.warn(
            "AlertManager is deprecated. All in-memory alerting removed. "
            "Use Prometheus Alertmanager for alerts. Will be removed in v3.0.",
            DeprecationWarning,
            stacklevel=2,
        )

    def add_alert_callback(self, callback: Callable[[UsageAlert], None]):
        """Add a callback function for alerts"""
        self.alert_callbacks.append(callback)

    async def _check_rate_alerts(self, tracker: UsageTracker) -> UsageAlert | None:
        """Check rate limit alerts (#10721: async — backed by Prometheus)."""
        rate_1min = await tracker.calculate_usage_rate(1)
        rate_60min = await tracker.calculate_usage_rate(60)
        rates = {"rate_1min": rate_1min, "rate_60min": rate_60min}

        if rate_1min > 50:
            return self._create_alert(
                "critical",
                f"High API usage rate: {rate_1min:.1f} calls/minute",
                rates,
                "Reduce request frequency to avoid rate limits",
            )
        if rate_1min > 30:
            return self._create_alert(
                "warning",
                f"Elevated API usage rate: {rate_1min:.1f} calls/minute",
                rates,
                "Consider batching requests or adding delays",
            )
        return None

    async def check_usage_alerts(self, tracker: UsageTracker) -> List[UsageAlert]:
        """Check current usage and generate alerts if needed"""
        alerts = []

        # Rate alerts backed by Prometheus (#10721)
        rate_alert = await self._check_rate_alerts(tracker)
        if rate_alert:
            alerts.append(rate_alert)

        # NOTE: per-call error-rate and payload alerts removed (#10721):
        # they depended on the deque-backed get_recent_calls() which was
        # removed in Phase 5 (#348).  Use Prometheus Alertmanager rules
        # for autobot_claude_api_requests_total{success="false"} instead.

        # Process and store alerts
        current_time = time.time()
        filtered_alerts = []
        for alert in alerts:
            if self._should_send_alert(alert, current_time):
                filtered_alerts.append(alert)
                # REMOVED (Phase 5, Issue #348): self.alert_history.append(alert)
                self.last_alerts[alert.level] = current_time

                # Send to callbacks
                for callback in self.alert_callbacks:
                    try:
                        callback(alert)
                    except Exception as e:
                        logger.error("Alert callback failed: %s", e)

        return filtered_alerts

    def _create_alert(self, level: str, message: str, metrics: Dict[str, Any], recommendation: str) -> UsageAlert:
        """Create a new usage alert"""
        return UsageAlert(
            timestamp=time.time(),
            level=level,
            message=message,
            metrics=metrics,
            recommendation=recommendation,
        )

    def _should_send_alert(self, alert: UsageAlert, current_time: float) -> bool:
        """Check if alert should be sent based on cooldown"""
        last_alert_time = self.last_alerts.get(alert.level, 0)
        return current_time - last_alert_time >= self.alert_cooldown


class ClaudeAPIMonitor:
    """
    Main Claude API monitoring system.

    Provides comprehensive monitoring, alerting, and analytics
    for Claude API usage to prevent conversation crashes.

    DEPRECATED (Phase 2, Issue #345): Claude API metrics are now tracked in PrometheusMetricsManager.
    This class will be REMOVED in Phase 5.
    """

    def __init__(
        self,
        rate_limit_rpm: int = 50,
        rate_limit_rph: int = 2000,
        payload_warning_size: int = 20000,
        payload_max_size: int = 30000,
    ):
        """Initialize Claude API monitor with rate limits and alert system."""
        self.rate_limit_rpm = rate_limit_rpm
        self.rate_limit_rph = rate_limit_rph
        self.payload_warning_size = payload_warning_size
        self.payload_max_size = payload_max_size

        # Core components
        self.usage_tracker = UsageTracker()
        self.alert_manager = AlertManager()

        # Monitoring state
        self.monitoring_active = True
        self.start_time = time.time()

        # Analytics
        self.prediction_window = 300  # 5 minutes for predictions

        # Setup default alert callback
        self.alert_manager.add_alert_callback(self._log_alert)

        # Phase 2 (Issue #345): Add Prometheus integration for dual-write migration
        try:
            from monitoring.prometheus_metrics import get_metrics_manager

            self.prometheus = get_metrics_manager()
        except (ImportError, Exception) as e:
            logger.warning("Prometheus metrics not available: %s", e)
            self.prometheus = None

        logger.info("ClaudeAPIMonitor initialized")

    async def record_api_call(
        self,
        payload_size: int,
        response_size: int = 0,
        response_time: float = 0.0,
        success: bool = True,
        error_type: str | None = None,
        tool_name: str | None = None,
        context: str | None = None,
    ):
        """Record a completed API call"""

        if not self.monitoring_active:
            return

        record = APICallRecord(
            timestamp=time.time(),
            payload_size=payload_size,
            response_size=response_size,
            response_time=response_time,
            success=success,
            error_type=error_type,
            tool_name=tool_name,
            context=context,
        )

        self.usage_tracker.add_call(record)

        # Phase 2 (Issue #345): Push to Prometheus
        if self.prometheus:
            self.prometheus.record_claude_api_request(tool_name or "unknown", success)
            if payload_size > 0:
                self.prometheus.record_claude_api_payload(payload_size)
            if response_time > 0:
                self.prometheus.record_claude_api_response_time(response_time)

        # Check for immediate alerts
        alerts = await self.alert_manager.check_usage_alerts(self.usage_tracker)
        if alerts:
            logger.info("Generated %s usage alerts", len(alerts))

    async def predict_rate_limit_risk(self) -> Dict[str, Any]:
        """Predict the risk of hitting rate limits"""
        current_rpm = await self.usage_tracker.calculate_usage_rate(1)
        current_rph = await self.usage_tracker.calculate_usage_rate(60)

        # Calculate risk scores (0-100)
        rpm_risk = min(100, (current_rpm / self.rate_limit_rpm) * 100)
        rph_risk = min(100, (current_rph / self.rate_limit_rph) * 100)

        # NOTE: per-call trend prediction removed (#10721): depended on the
        # deque-backed get_recent_calls() removed in Phase 5 (#348).
        predicted_rpm = current_rpm

        # Overall risk assessment
        max_risk = max(rpm_risk, rph_risk)
        if max_risk > 90:
            risk_level = "critical"
        elif max_risk > 70:
            risk_level = "high"
        elif max_risk > 50:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "risk_score": max_risk,
            "current_rpm": current_rpm,
            "current_rph": current_rph,
            "predicted_rpm": predicted_rpm,
            "rpm_utilization": rpm_risk,
            "rph_utilization": rph_risk,
            "recommendation": self._get_risk_recommendation(risk_level, max_risk),
        }

    async def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive API usage statistics"""
        uptime = time.time() - self.start_time

        # Basic stats (in-memory counters are still maintained)
        basic_stats = {
            "monitoring_uptime": uptime,
            "total_calls": self.usage_tracker.total_calls,
            "calls_per_hour": self.usage_tracker.total_calls / max(uptime / 3600, 1),
            "average_payload_size": (self.usage_tracker.total_payload_size / max(self.usage_tracker.total_calls, 1)),
            "average_response_time": (self.usage_tracker.total_response_time / max(self.usage_tracker.total_calls, 1)),
        }

        # Current usage (backed by Prometheus #10721)
        current_usage = {
            "rpm_current": await self.usage_tracker.calculate_usage_rate(1),
            "rpm_limit": self.rate_limit_rpm,
            "rph_current": await self.usage_tracker.calculate_usage_rate(60),
            "rph_limit": self.rate_limit_rph,
        }

        # Risk prediction (async #10721)
        risk_prediction = await self.predict_rate_limit_risk()

        # REMOVED (Phase 5, Issue #348): tool_usage — backed by get_tool_usage_stats() deque
        # REMOVED (Phase 5, Issue #348): payload_analysis — backed by calculate_payload_trend() deque
        # REMOVED (Phase 5, Issue #348): alert_history deque removed

        return {
            "basic_stats": basic_stats,
            "current_usage": current_usage,
            "risk_prediction": risk_prediction,
            "recent_alerts": [],
            "error_patterns": dict(self.usage_tracker.error_patterns),
        }

    def _check_rate_limit_recommendation(self, stats: Dict[str, Any]) -> Dict[str, str] | None:
        """Check if rate limit recommendation is needed. Issue #620."""
        if stats["risk_prediction"]["risk_score"] > 70:
            return {
                "type": "rate_limit",
                "priority": "high",
                "message": "API usage approaching limits",
                "action": "Implement request batching or increase delays between calls",
            }
        return None

    def _check_payload_size_recommendation(self, stats: Dict[str, Any]) -> Dict[str, str] | None:
        """Check if payload size recommendation is needed. Issue #620."""
        avg_payload = stats["basic_stats"]["average_payload_size"]
        if avg_payload > self.payload_warning_size:
            return {
                "type": "payload_size",
                "priority": "medium",
                "message": "Large average payload size detected",
                "action": "Use payload optimization to reduce request sizes",
            }
        return None

    def _get_tool_usage_recommendations(self, stats: Dict[str, Any]) -> List[Dict[str, str]]:
        """Get recommendations for tools with large payloads. Issue #620.

        Returns empty list: per-tool payload breakdown unavailable without the
        in-memory deque removed in Phase 5 (#348 / #10721).
        """
        return []

    async def get_optimization_recommendations(self) -> List[Dict[str, str]]:
        """Get recommendations for optimizing API usage. Issue #620."""
        recommendations = []
        stats = await self.get_comprehensive_stats()

        rate_limit_rec = self._check_rate_limit_recommendation(stats)
        if rate_limit_rec:
            recommendations.append(rate_limit_rec)

        payload_rec = self._check_payload_size_recommendation(stats)
        if payload_rec:
            recommendations.append(payload_rec)

        recommendations.extend(self._get_tool_usage_recommendations(stats))

        # NOTE: _check_error_rate_recommendation removed (#10721):
        # depended on get_recent_calls() deque removed in Phase 5 (#348).

        return recommendations

    def _get_risk_recommendation(self, risk_level: str, risk_score: float) -> str:
        """Get recommendation based on risk level"""
        if risk_level == "critical":
            return "Immediate action required: Stop non-essential API calls"
        elif risk_level == "high":
            return "Reduce API call frequency and optimize payload sizes"
        elif risk_level == "medium":
            return "Consider implementing request batching"
        else:
            return "API usage is within safe limits"

    def _log_alert(self, alert: UsageAlert):
        """Default alert logging callback"""
        level_map = {
            "info": logging.INFO,
            "warning": logging.WARNING,
            "critical": logging.ERROR,
        }
        log_level = level_map.get(alert.level, logging.INFO)

        logger.log(log_level, f"Claude API Alert [{alert.level.upper()}]: {alert.message}")
        logger.log(log_level, f"Recommendation: {alert.recommendation}")

    def enable_monitoring(self):
        """Enable API monitoring"""
        self.monitoring_active = True
        logger.info("Claude API monitoring enabled")

    def disable_monitoring(self):
        """Disable API monitoring"""
        self.monitoring_active = False
        logger.info("Claude API monitoring disabled")

    def reset_statistics(self):
        """Reset all monitoring statistics"""
        self.usage_tracker = UsageTracker()
        self.alert_manager = AlertManager()
        self.start_time = time.time()
        logger.info("Claude API monitoring statistics reset")


# Global monitor instance (thread-safe)
_global_monitor: ClaudeAPIMonitor | None = None
_global_monitor_lock = threading.Lock()


def get_api_monitor() -> ClaudeAPIMonitor:
    """
    Get the global API monitor instance (thread-safe).

    DEPRECATED (Phase 5, Issue #348): Use PrometheusMetricsManager instead.
    This function and the ClaudeAPIMonitor class will be removed in v3.0.
    """
    import warnings

    warnings.warn(
        "get_api_monitor() is deprecated. Use PrometheusMetricsManager for "
        "Claude API metrics. This will be removed in v3.0.",
        DeprecationWarning,
        stacklevel=2,
    )

    global _global_monitor
    if _global_monitor is None:
        with _global_monitor_lock:
            # Double-check after acquiring lock
            if _global_monitor is None:
                _global_monitor = ClaudeAPIMonitor()
    return _global_monitor


async def record_api_call(payload_size: int, **kwargs):
    """
    Convenience function to record an API call.

    DEPRECATED (Phase 5, Issue #348): Use PrometheusMetricsManager.record_claude_api_request()
    """
    import warnings

    warnings.warn(
        "record_api_call() is deprecated. Use PrometheusMetricsManager for "
        "Claude API metrics. This will be removed in v3.0.",
        DeprecationWarning,
        stacklevel=2,
    )
    monitor = get_api_monitor()
    await monitor.record_api_call(payload_size, **kwargs)


async def get_usage_stats() -> Dict[str, Any]:
    """Convenience function to get usage statistics"""
    monitor = get_api_monitor()
    return await monitor.get_comprehensive_stats()


async def check_rate_limit_risk() -> Dict[str, Any]:
    """Convenience function to check rate limit risk"""
    monitor = get_api_monitor()
    return await monitor.predict_rate_limit_risk()


# Example usage and testing
if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async def _main():
        monitor = ClaudeAPIMonitor()

        # Simulate some API calls
        for i in range(10):
            await monitor.record_api_call(
                payload_size=1000 + i * 500,
                response_size=2000,
                response_time=0.5,
                success=True,
                tool_name="TodoWrite" if i % 3 == 0 else "Read",
                context="test_simulation",
            )
            time.sleep(0.1)

        # Get statistics
        stats = await monitor.get_comprehensive_stats()
        logger.info(f"Total calls: {stats['basic_stats']['total_calls']}")
        logger.info(f"Risk level: {stats['risk_prediction']['risk_level']}")

        # Get recommendations
        recommendations = await monitor.get_optimization_recommendations()
        for rec in recommendations:
            logger.info(f"Recommendation: {rec['message']} - {rec['action']}")

    asyncio.run(_main())
