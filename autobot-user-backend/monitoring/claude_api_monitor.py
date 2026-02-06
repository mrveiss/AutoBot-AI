#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import statistics
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class APICallRecord:
    """Record of a single API call"""

    timestamp: float
    payload_size: int
    response_size: int
    response_time: float
    success: bool
    error_type: Optional[str] = None
    tool_name: Optional[str] = None
    context: Optional[str] = None


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
    Methods return empty/safe defaults. Use PrometheusMetricsManager.
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

    def get_recent_calls(self, minutes: int = 60) -> List[APICallRecord]:
        """
        Get calls from the last N minutes (thread-safe)

        DEPRECATED (Phase 5, Issue #348): Returns empty list. Use Prometheus query.
        """
        # REMOVED (Phase 5, Issue #348): call_history deque removed
        return []  # Return empty list for backwards compatibility

    def calculate_usage_rate(self, window_minutes: int = 60) -> float:
        """Calculate calls per minute in the given window"""
        recent_calls = self.get_recent_calls(window_minutes)
        if not recent_calls:
            return 0.0

        if window_minutes == 0:
            return len(recent_calls)

        return len(recent_calls) / window_minutes

    def calculate_payload_trend(self, window_minutes: int = 30) -> Dict[str, float]:
        """Calculate payload size trends"""
        recent_calls = self.get_recent_calls(window_minutes)
        if not recent_calls:
            return {"average": 0, "max": 0, "trend": 0}

        payload_sizes = [call.payload_size for call in recent_calls]

        # Calculate trend (simple linear regression slope)
        if len(payload_sizes) > 1:
            x_values = list(range(len(payload_sizes)))
            n = len(payload_sizes)
            sum_x = sum(x_values)
            sum_y = sum(payload_sizes)
            sum_xy = sum(x * y for x, y in zip(x_values, payload_sizes))
            sum_x2 = sum(x * x for x in x_values)

            trend = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        else:
            trend = 0

        return {
            "average": statistics.mean(payload_sizes),
            "max": max(payload_sizes),
            "min": min(payload_sizes),
            "trend": trend,
        }

    def get_tool_usage_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get usage statistics per tool (thread-safe)

        DEPRECATED (Phase 5, Issue #348): Returns empty dict. Use Prometheus query.
        """
        # REMOVED (Phase 5, Issue #348): tool_usage tracking removed
        return {}  # Return empty dict for backwards compatibility


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

    def _check_rate_alerts(self, tracker: UsageTracker) -> Optional[UsageAlert]:
        """Check rate limit alerts (Issue #315: extracted helper)."""
        rate_1min = tracker.calculate_usage_rate(1)
        rate_60min = tracker.calculate_usage_rate(60)
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

    def _check_payload_alert(self, tracker: UsageTracker) -> Optional[UsageAlert]:
        """Check payload size alerts (Issue #315: extracted helper)."""
        payload_trend = tracker.calculate_payload_trend(30)
        if payload_trend["max"] > 25000:
            return self._create_alert(
                "warning",
                f"Large payload detected: {payload_trend['max']} bytes",
                payload_trend,
                "Consider breaking large requests into smaller chunks",
            )
        return None

    def _check_error_rate_alert(self, tracker: UsageTracker) -> Optional[UsageAlert]:
        """Check error rate alerts (Issue #315: extracted helper)."""
        recent_calls = tracker.get_recent_calls(60)
        if not recent_calls:
            return None

        error_rate = sum(1 for call in recent_calls if not call.success) / len(
            recent_calls
        )
        if error_rate > 0.1:
            return self._create_alert(
                "critical",
                f"High error rate: {error_rate*100:.1f}%",
                {"error_rate": error_rate, "recent_calls": len(recent_calls)},
                "Check for API issues or adjust request patterns",
            )
        return None

    def check_usage_alerts(self, tracker: UsageTracker) -> List[UsageAlert]:
        """Check current usage and generate alerts if needed"""
        alerts = []

        # Check all alert conditions using helpers (Issue #315: reduced nesting)
        rate_alert = self._check_rate_alerts(tracker)
        if rate_alert:
            alerts.append(rate_alert)

        payload_alert = self._check_payload_alert(tracker)
        if payload_alert:
            alerts.append(payload_alert)

        error_alert = self._check_error_rate_alert(tracker)
        if error_alert:
            alerts.append(error_alert)

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

    def _create_alert(
        self, level: str, message: str, metrics: Dict[str, Any], recommendation: str
    ) -> UsageAlert:
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
            from src.monitoring.prometheus_metrics import get_metrics_manager

            self.prometheus = get_metrics_manager()
        except (ImportError, Exception) as e:
            logger.warning("Prometheus metrics not available: %s", e)
            self.prometheus = None

        logger.info("ClaudeAPIMonitor initialized")

    def record_api_call(
        self,
        payload_size: int,
        response_size: int = 0,
        response_time: float = 0.0,
        success: bool = True,
        error_type: Optional[str] = None,
        tool_name: Optional[str] = None,
        context: Optional[str] = None,
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
        alerts = self.alert_manager.check_usage_alerts(self.usage_tracker)
        if alerts:
            logger.info("Generated %s usage alerts", len(alerts))

    def predict_rate_limit_risk(self) -> Dict[str, Any]:
        """Predict the risk of hitting rate limits"""
        current_rpm = self.usage_tracker.calculate_usage_rate(1)
        current_rph = self.usage_tracker.calculate_usage_rate(60)

        # Calculate risk scores (0-100)
        rpm_risk = min(100, (current_rpm / self.rate_limit_rpm) * 100)
        rph_risk = min(100, (current_rph / self.rate_limit_rph) * 100)

        # Predict future usage based on trend
        recent_calls = self.usage_tracker.get_recent_calls(5)  # Last 5 minutes
        if len(recent_calls) >= 3:
            # Simple trend calculation
            times = [call.timestamp for call in recent_calls]
            rates = []
            for i in range(1, len(times)):
                window_size = times[i] - times[i - 1]
                if window_size > 0:
                    rate = 60 / window_size  # Convert to per-minute rate
                    rates.append(rate)

            if rates:
                trend = statistics.mean(rates)
                predicted_rpm = max(0, current_rpm + (trend * 5))  # 5-minute prediction
            else:
                predicted_rpm = current_rpm
        else:
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

    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive API usage statistics"""
        uptime = time.time() - self.start_time

        # Basic stats
        basic_stats = {
            "monitoring_uptime": uptime,
            "total_calls": self.usage_tracker.total_calls,
            "calls_per_hour": self.usage_tracker.total_calls / max(uptime / 3600, 1),
            "average_payload_size": (
                self.usage_tracker.total_payload_size
                / max(self.usage_tracker.total_calls, 1)
            ),
            "average_response_time": (
                self.usage_tracker.total_response_time
                / max(self.usage_tracker.total_calls, 1)
            ),
        }

        # Current usage
        current_usage = {
            "rpm_current": self.usage_tracker.calculate_usage_rate(1),
            "rpm_limit": self.rate_limit_rpm,
            "rph_current": self.usage_tracker.calculate_usage_rate(60),
            "rph_limit": self.rate_limit_rph,
        }

        # Tool usage
        tool_stats = self.usage_tracker.get_tool_usage_stats()

        # Payload analysis
        payload_trend = self.usage_tracker.calculate_payload_trend(30)

        # Risk prediction
        risk_prediction = self.predict_rate_limit_risk()

        # Recent alerts
        # REMOVED (Phase 5, Issue #348): alert_history deque removed
        recent_alerts = []  # Return empty list for backwards compatibility

        return {
            "basic_stats": basic_stats,
            "current_usage": current_usage,
            "tool_usage": tool_stats,
            "payload_analysis": payload_trend,
            "risk_prediction": risk_prediction,
            "recent_alerts": recent_alerts,
            "error_patterns": dict(self.usage_tracker.error_patterns),
        }

    def _check_rate_limit_recommendation(
        self, stats: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """Check if rate limit recommendation is needed. Issue #620."""
        if stats["risk_prediction"]["risk_score"] > 70:
            return {
                "type": "rate_limit",
                "priority": "high",
                "message": "API usage approaching limits",
                "action": "Implement request batching or increase delays between calls",
            }
        return None

    def _check_payload_size_recommendation(
        self, stats: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """Check if payload size recommendation is needed. Issue #620."""
        if stats["payload_analysis"]["average"] > self.payload_warning_size:
            return {
                "type": "payload_size",
                "priority": "medium",
                "message": "Large average payload size detected",
                "action": "Use payload optimization to reduce request sizes",
            }
        return None

    def _get_tool_usage_recommendations(
        self, stats: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Get recommendations for tools with large payloads. Issue #620."""
        recommendations = []
        for tool_name, tool_stats in stats["tool_usage"].items():
            if tool_stats["avg_payload_size"] > self.payload_warning_size:
                recommendations.append(
                    {
                        "type": "tool_optimization",
                        "priority": "medium",
                        "message": f"Tool '{tool_name}' using large payloads",
                        "action": f"Optimize {tool_name} usage patterns",
                    }
                )
        return recommendations

    def _check_error_rate_recommendation(self) -> Optional[Dict[str, str]]:
        """Check if error rate recommendation is needed. Issue #620."""
        recent_calls = self.usage_tracker.get_recent_calls(60)
        if not recent_calls:
            return None
        error_rate = sum(1 for call in recent_calls if not call.success) / len(
            recent_calls
        )
        if error_rate > 0.05:  # More than 5% errors
            return {
                "type": "error_rate",
                "priority": "high",
                "message": f"High error rate: {error_rate*100:.1f}%",
                "action": "Investigate and fix recurring API errors",
            }
        return None

    def get_optimization_recommendations(self) -> List[Dict[str, str]]:
        """Get recommendations for optimizing API usage. Issue #620."""
        recommendations = []
        stats = self.get_comprehensive_stats()

        rate_limit_rec = self._check_rate_limit_recommendation(stats)
        if rate_limit_rec:
            recommendations.append(rate_limit_rec)

        payload_rec = self._check_payload_size_recommendation(stats)
        if payload_rec:
            recommendations.append(payload_rec)

        recommendations.extend(self._get_tool_usage_recommendations(stats))

        error_rec = self._check_error_rate_recommendation()
        if error_rec:
            recommendations.append(error_rec)

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

        logger.log(
            log_level, f"Claude API Alert [{alert.level.upper()}]: {alert.message}"
        )
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
_global_monitor: Optional[ClaudeAPIMonitor] = None
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


def record_api_call(payload_size: int, **kwargs):
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
    monitor.record_api_call(payload_size, **kwargs)


def get_usage_stats() -> Dict[str, Any]:
    """Convenience function to get usage statistics"""
    monitor = get_api_monitor()
    return monitor.get_comprehensive_stats()


def check_rate_limit_risk() -> Dict[str, Any]:
    """Convenience function to check rate limit risk"""
    monitor = get_api_monitor()
    return monitor.predict_rate_limit_risk()


# Example usage and testing
if __name__ == "__main__":
    # Example usage
    monitor = ClaudeAPIMonitor()

    # Simulate some API calls
    for i in range(10):
        monitor.record_api_call(
            payload_size=1000 + i * 500,
            response_size=2000,
            response_time=0.5,
            success=True,
            tool_name="TodoWrite" if i % 3 == 0 else "Read",
            context="test_simulation",
        )
        time.sleep(0.1)

    # Get statistics
    stats = monitor.get_comprehensive_stats()
    print(f"Total calls: {stats['basic_stats']['total_calls']}")
    print(f"Risk level: {stats['risk_prediction']['risk_level']}")

    # Get recommendations
    recommendations = monitor.get_optimization_recommendations()
    for rec in recommendations:
        print(f"Recommendation: {rec['message']} - {rec['action']}")
