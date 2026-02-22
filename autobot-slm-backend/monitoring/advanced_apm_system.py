#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Advanced Application Performance Monitoring (APM) System
Detailed API tracking, cache analytics, database monitoring, and real-time alerting.
"""

import asyncio
import hashlib
import inspect
import json
import logging
import os
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from autobot_shared.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


@dataclass
class APIMetrics:
    """Detailed API performance metrics."""

    timestamp: str
    endpoint: str
    method: str
    status_code: int
    response_time_ms: float
    request_size_bytes: int
    response_size_bytes: int
    user_agent: Optional[str]
    client_ip: str
    database_queries: int
    cache_hits: int
    cache_misses: int
    memory_usage_mb: float
    cpu_time_ms: float
    error_message: Optional[str] = None
    trace_id: Optional[str] = None


@dataclass
class CacheMetrics:
    """Cache performance analytics."""

    timestamp: str
    cache_type: str  # redis, memory, file
    operation: str  # get, set, delete, flush
    key: str
    hit: bool
    response_time_ms: float
    data_size_bytes: int
    ttl_seconds: Optional[int]
    eviction_count: int
    memory_usage_mb: float
    hit_rate_percent: float


@dataclass
class DatabaseMetrics:
    """Database operation monitoring."""

    timestamp: str
    database: str
    operation: str
    table_or_collection: str
    execution_time_ms: float
    rows_affected: int
    query_complexity: str  # simple, medium, complex
    index_usage: bool
    memory_usage_mb: float
    connection_pool_size: int
    active_connections: int
    query_hash: str
    error_message: Optional[str] = None


@dataclass
class AlertRule:
    """Real-time alerting rule configuration."""

    name: str
    metric_type: str  # api, cache, database, system
    condition: str  # threshold, trend, anomaly
    threshold_value: float
    time_window_seconds: int
    severity: str  # low, medium, high, critical
    enabled: bool = True
    consecutive_violations: int = 1
    notification_channels: List[str] = field(default_factory=list)


@dataclass
class Alert:
    """Alert instance."""

    timestamp: str
    rule_name: str
    severity: str
    message: str
    metric_value: float
    threshold_value: float
    resolved: bool = False
    resolution_timestamp: Optional[str] = None


class PerformanceTracker:
    """Decorator and context manager for automatic performance tracking."""

    def __init__(self, apm_system: "AdvancedAPMSystem"):
        self.apm = apm_system

    def track_api(self, endpoint: str = None, method: str = "GET"):
        """Decorator for API endpoint tracking."""

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                endpoint_name = endpoint or f"{func.__module__}.{func.__name__}"
                trace_id = self._generate_trace_id()

                try:
                    # Track request start
                    await self.apm.start_api_tracking(endpoint_name, method, trace_id)

                    # Execute function
                    result = (
                        await func(*args, **kwargs)
                        if inspect.iscoroutinefunction(func)
                        else func(*args, **kwargs)
                    )

                    # Track successful completion
                    response_time = (time.time() - start_time) * 1000
                    await self.apm.complete_api_tracking(
                        endpoint_name, 200, response_time, trace_id
                    )

                    return result

                except Exception as e:
                    # Track error
                    response_time = (time.time() - start_time) * 1000
                    await self.apm.complete_api_tracking(
                        endpoint_name, 500, response_time, trace_id, str(e)
                    )
                    raise

            return wrapper

        return decorator

    def track_database(self, database: str, operation: str = "query"):
        """Decorator for database operation tracking."""

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()

                try:
                    result = (
                        await func(*args, **kwargs)
                        if inspect.iscoroutinefunction(func)
                        else func(*args, **kwargs)
                    )

                    execution_time = (time.time() - start_time) * 1000
                    await self.apm.track_database_operation(
                        database, operation, execution_time, success=True
                    )

                    return result

                except Exception as e:
                    execution_time = (time.time() - start_time) * 1000
                    await self.apm.track_database_operation(
                        database, operation, execution_time, success=False, error=str(e)
                    )
                    raise

            return wrapper

        return decorator

    def _generate_trace_id(self) -> str:
        """Generate unique trace ID for request correlation."""
        return hashlib.md5(  # nosec B324 - not used for security
            f"{time.time()}{threading.current_thread().ident}".encode()
        ).hexdigest()[:16]


class AdvancedAPMSystem:
    """Advanced Application Performance Monitoring System."""

    def __init__(
        self, redis_host: str = NetworkConstants.REDIS_VM_IP, redis_port: int = 6379
    ):
        self.logger = logging.getLogger(__name__)
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_client = None
        _base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        self.apm_data_path = Path(_base) / "logs" / "apm"
        self.apm_data_path.mkdir(parents=True, exist_ok=True)

        # Performance tracking
        self.active_requests = {}  # trace_id -> request_data
        self.api_metrics_buffer = deque(maxlen=1000)
        self.cache_metrics_buffer = deque(maxlen=1000)
        self.database_metrics_buffer = deque(maxlen=1000)

        # Alert system
        self.alert_rules: List[AlertRule] = []
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=500)

        # Cache monitoring
        self.cache_stats = defaultdict(
            lambda: {"hits": 0, "misses": 0, "total_size": 0, "operations": 0}
        )

        # Performance tracker
        self.tracker = PerformanceTracker(self)

        # Initialize default alert rules
        self._initialize_default_alert_rules()

    async def initialize_redis_connection(self):
        """Initialize Redis connection for APM data using canonical utility."""
        try:
            from autobot_shared.redis_client import get_redis_client

            self.redis_client = get_redis_client(database="metrics")
            if self.redis_client is None:
                raise Exception("Redis client initialization returned None")

            self.redis_client.ping()
            self.logger.info("✅ Redis connection established for APM")
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to Redis for APM: {e}")
            self.redis_client = None

    def _initialize_default_alert_rules(self):
        """Initialize default alerting rules."""
        self.alert_rules = [
            AlertRule(
                name="High API Response Time",
                metric_type="api",
                condition="threshold",
                threshold_value=5000.0,  # 5 seconds
                time_window_seconds=300,  # 5 minutes
                severity="high",
                consecutive_violations=3,
                notification_channels=["console", "log"],
            ),
            AlertRule(
                name="API Error Rate High",
                metric_type="api",
                condition="threshold",
                threshold_value=10.0,  # 10% error rate
                time_window_seconds=600,  # 10 minutes
                severity="critical",
                consecutive_violations=2,
                notification_channels=["console", "log"],
            ),
            AlertRule(
                name="Low Cache Hit Rate",
                metric_type="cache",
                condition="threshold",
                threshold_value=50.0,  # 50% hit rate
                time_window_seconds=900,  # 15 minutes
                severity="medium",
                consecutive_violations=5,
                notification_channels=["console"],
            ),
            AlertRule(
                name="Slow Database Queries",
                metric_type="database",
                condition="threshold",
                threshold_value=1000.0,  # 1 second
                time_window_seconds=300,  # 5 minutes
                severity="high",
                consecutive_violations=3,
                notification_channels=["console", "log"],
            ),
            AlertRule(
                name="Database Connection Pool Exhaustion",
                metric_type="database",
                condition="threshold",
                threshold_value=90.0,  # 90% pool utilization
                time_window_seconds=60,  # 1 minute
                severity="critical",
                consecutive_violations=1,
                notification_channels=["console", "log"],
            ),
        ]

    async def start_api_tracking(self, endpoint: str, method: str, trace_id: str):
        """Start tracking an API request."""
        self.active_requests[trace_id] = {
            "endpoint": endpoint,
            "method": method,
            "start_time": time.time(),
            "database_queries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    async def complete_api_tracking(
        self,
        endpoint: str,
        status_code: int,
        response_time: float,
        trace_id: str,
        error_message: Optional[str] = None,
    ):
        """Complete API request tracking."""
        try:
            request_data = self.active_requests.pop(trace_id, {})

            api_metric = APIMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                endpoint=endpoint,
                method=request_data.get("method", "GET"),
                status_code=status_code,
                response_time_ms=response_time,
                request_size_bytes=0,  # Would be extracted from request
                response_size_bytes=0,  # Would be extracted from response
                user_agent=None,  # Would be extracted from headers
                client_ip="127.0.0.1",  # Would be extracted from request
                database_queries=request_data.get("database_queries", 0),
                cache_hits=request_data.get("cache_hits", 0),
                cache_misses=request_data.get("cache_misses", 0),
                memory_usage_mb=self._get_current_memory_usage(),
                cpu_time_ms=response_time * 0.8,  # Estimated CPU time
                error_message=error_message,
                trace_id=trace_id,
            )

            self.api_metrics_buffer.append(api_metric)
            await self._store_api_metrics(api_metric)
            await self._check_api_alerts(api_metric)

        except Exception as e:
            self.logger.error(f"Error completing API tracking: {e}")

    async def track_cache_operation(
        self,
        cache_type: str,
        operation: str,
        key: str,
        hit: bool,
        response_time: float,
        data_size: int = 0,
        ttl: Optional[int] = None,
    ):
        """Track cache operation performance."""
        try:
            # Update cache stats
            cache_stat = self.cache_stats[cache_type]
            if hit:
                cache_stat["hits"] += 1
            else:
                cache_stat["misses"] += 1
            cache_stat["operations"] += 1
            cache_stat["total_size"] += data_size

            # Calculate hit rate
            total_ops = cache_stat["hits"] + cache_stat["misses"]
            hit_rate = (cache_stat["hits"] / total_ops * 100) if total_ops > 0 else 0

            cache_metric = CacheMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                cache_type=cache_type,
                operation=operation,
                key=key,
                hit=hit,
                response_time_ms=response_time,
                data_size_bytes=data_size,
                ttl_seconds=ttl,
                eviction_count=0,  # Would be tracked separately
                memory_usage_mb=self._get_cache_memory_usage(cache_type),
                hit_rate_percent=hit_rate,
            )

            self.cache_metrics_buffer.append(cache_metric)
            await self._store_cache_metrics(cache_metric)
            await self._check_cache_alerts(cache_metric)

        except Exception as e:
            self.logger.error(f"Error tracking cache operation: {e}")

    async def track_database_operation(
        self,
        database: str,
        operation: str,
        execution_time: float,
        success: bool = True,
        error: Optional[str] = None,
        rows_affected: int = 0,
        table: str = "unknown",
    ):
        """Track database operation performance."""
        try:
            # Determine query complexity based on execution time
            if execution_time < 10:
                complexity = "simple"
            elif execution_time < 100:
                complexity = "medium"
            else:
                complexity = "complex"

            # Generate query hash for tracking
            query_hash = hashlib.md5(  # nosec B324 - not used for security
                f"{database}:{operation}:{table}".encode()
            ).hexdigest()[:12]

            db_metric = DatabaseMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                database=database,
                operation=operation,
                table_or_collection=table,
                execution_time_ms=execution_time,
                rows_affected=rows_affected,
                query_complexity=complexity,
                index_usage=execution_time < 50,  # Assume index used if fast
                memory_usage_mb=self._get_current_memory_usage(),
                connection_pool_size=10,  # Would be actual pool size
                active_connections=5,  # Would be actual active count
                query_hash=query_hash,
                error_message=error,
            )

            self.database_metrics_buffer.append(db_metric)
            await self._store_database_metrics(db_metric)
            await self._check_database_alerts(db_metric)

        except Exception as e:
            self.logger.error(f"Error tracking database operation: {e}")

    def _get_current_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            import psutil

            process = psutil.Process()
            return process.memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0

    def _get_cache_memory_usage(self, cache_type: str) -> float:
        """Get cache-specific memory usage."""
        try:
            if cache_type == "redis" and self.redis_client:
                info = self.redis_client.info()
                return info.get("used_memory", 0) / (1024 * 1024)
            else:
                return self.cache_stats[cache_type]["total_size"] / (1024 * 1024)
        except Exception:
            return 0.0

    async def _store_api_metrics(self, metric: APIMetrics):
        """Store API metrics in Redis and files."""
        try:
            if self.redis_client:
                # Store in Redis with TTL
                metric_data = json.dumps(asdict(metric), default=str)
                self.redis_client.lpush("autobot:apm:api_metrics", metric_data)
                self.redis_client.ltrim(
                    "autobot:apm:api_metrics", 0, 9999
                )  # Keep 10k metrics

            # Store in daily file
            date_str = datetime.now().strftime("%Y%m%d")
            metrics_file = self.apm_data_path / f"api_metrics_{date_str}.jsonl"
            try:
                async with aiofiles.open(metrics_file, "a", encoding="utf-8") as f:
                    await f.write(json.dumps(asdict(metric), default=str) + "\n")
            except OSError as e:
                self.logger.error(f"Failed to write API metrics to {metrics_file}: {e}")

        except Exception as e:
            self.logger.error(f"Error storing API metrics: {e}")

    async def _store_cache_metrics(self, metric: CacheMetrics):
        """Store cache metrics."""
        try:
            if self.redis_client:
                metric_data = json.dumps(asdict(metric), default=str)
                self.redis_client.lpush("autobot:apm:cache_metrics", metric_data)
                self.redis_client.ltrim("autobot:apm:cache_metrics", 0, 9999)

            date_str = datetime.now().strftime("%Y%m%d")
            metrics_file = self.apm_data_path / f"cache_metrics_{date_str}.jsonl"
            try:
                async with aiofiles.open(metrics_file, "a", encoding="utf-8") as f:
                    await f.write(json.dumps(asdict(metric), default=str) + "\n")
            except OSError as e:
                self.logger.error(
                    f"Failed to write cache metrics to {metrics_file}: {e}"
                )

        except Exception as e:
            self.logger.error(f"Error storing cache metrics: {e}")

    async def _store_database_metrics(self, metric: DatabaseMetrics):
        """Store database metrics."""
        try:
            if self.redis_client:
                metric_data = json.dumps(asdict(metric), default=str)
                self.redis_client.lpush("autobot:apm:database_metrics", metric_data)
                self.redis_client.ltrim("autobot:apm:database_metrics", 0, 9999)

            date_str = datetime.now().strftime("%Y%m%d")
            metrics_file = self.apm_data_path / f"database_metrics_{date_str}.jsonl"
            try:
                async with aiofiles.open(metrics_file, "a", encoding="utf-8") as f:
                    await f.write(json.dumps(asdict(metric), default=str) + "\n")
            except OSError as e:
                self.logger.error(
                    f"Failed to write database metrics to {metrics_file}: {e}"
                )

        except Exception as e:
            self.logger.error(f"Error storing database metrics: {e}")

    async def _check_api_alerts(self, metric: APIMetrics):
        """Check API metrics against alert rules."""
        for rule in self.alert_rules:
            if rule.metric_type != "api" or not rule.enabled:
                continue

            try:
                violated = False

                if rule.name == "High API Response Time":
                    violated = metric.response_time_ms > rule.threshold_value
                elif rule.name == "API Error Rate High":
                    # Calculate error rate from recent metrics
                    recent_metrics = list(self.api_metrics_buffer)[
                        -50:
                    ]  # Last 50 requests
                    if len(recent_metrics) >= 10:
                        error_count = sum(
                            1 for m in recent_metrics if m.status_code >= 400
                        )
                        error_rate = (error_count / len(recent_metrics)) * 100
                        violated = error_rate > rule.threshold_value

                if violated:
                    await self._trigger_alert(
                        rule, metric.response_time_ms, metric.endpoint
                    )
                else:
                    await self._resolve_alert(rule.name)

            except Exception as e:
                self.logger.error(f"Error checking API alert {rule.name}: {e}")

    async def _check_cache_alerts(self, metric: CacheMetrics):
        """Check cache metrics against alert rules."""
        for rule in self.alert_rules:
            if rule.metric_type != "cache" or not rule.enabled:
                continue

            try:
                violated = False

                if rule.name == "Low Cache Hit Rate":
                    violated = metric.hit_rate_percent < rule.threshold_value

                if violated:
                    await self._trigger_alert(
                        rule, metric.hit_rate_percent, metric.cache_type
                    )
                else:
                    await self._resolve_alert(rule.name)

            except Exception as e:
                self.logger.error(f"Error checking cache alert {rule.name}: {e}")

    async def _check_database_alerts(self, metric: DatabaseMetrics):
        """Check database metrics against alert rules."""
        for rule in self.alert_rules:
            if rule.metric_type != "database" or not rule.enabled:
                continue

            try:
                violated = False

                if rule.name == "Slow Database Queries":
                    violated = metric.execution_time_ms > rule.threshold_value
                elif rule.name == "Database Connection Pool Exhaustion":
                    pool_utilization = (
                        metric.active_connections / metric.connection_pool_size
                    ) * 100
                    violated = pool_utilization > rule.threshold_value

                if violated:
                    await self._trigger_alert(
                        rule, metric.execution_time_ms, metric.database
                    )
                else:
                    await self._resolve_alert(rule.name)

            except Exception as e:
                self.logger.error(f"Error checking database alert {rule.name}: {e}")

    async def _trigger_alert(self, rule: AlertRule, metric_value: float, context: str):
        """Trigger an alert based on rule violation."""
        try:
            alert_key = f"{rule.name}:{context}"

            # Check if alert already active
            if alert_key in self.active_alerts:
                return

            # Create new alert
            msg = (
                f"{rule.name}: {context} - "
                f"Value: {metric_value:.2f}, Threshold: {rule.threshold_value:.2f}"
            )
            alert = Alert(
                timestamp=datetime.now(timezone.utc).isoformat(),
                rule_name=rule.name,
                severity=rule.severity,
                message=msg,
                metric_value=metric_value,
                threshold_value=rule.threshold_value,
            )

            self.active_alerts[alert_key] = alert
            self.alert_history.append(alert)

            # Send notifications
            await self._send_alert_notifications(alert, rule.notification_channels)

            self.logger.warning(f"🚨 ALERT: {alert.message}")

        except Exception as e:
            self.logger.error(f"Error triggering alert: {e}")

    async def _resolve_alert(self, rule_name: str):
        """Resolve active alerts for a rule."""
        try:
            resolved_keys = []
            for alert_key, alert in self.active_alerts.items():
                if alert.rule_name == rule_name and not alert.resolved:
                    alert.resolved = True
                    alert.resolution_timestamp = datetime.now(timezone.utc).isoformat()
                    resolved_keys.append(alert_key)
                    self.logger.info(f"✅ RESOLVED: {alert.message}")

            # Remove resolved alerts from active list
            for key in resolved_keys:
                del self.active_alerts[key]

        except Exception as e:
            self.logger.error(f"Error resolving alert: {e}")

    async def _send_alert_notifications(self, alert: Alert, channels: List[str]):
        """Send alert notifications to configured channels."""
        try:
            for channel in channels:
                if channel == "console":
                    # Use warning level for console alerts to maintain visibility
                    self.logger.warning(
                        "ALERT %s: %s", alert.severity.upper(), alert.message
                    )
                elif channel == "log":
                    self.logger.warning("ALERT: %s", alert.message)
                # Additional notification channels (email, webhook, etc.) would be implemented here

        except Exception as e:
            self.logger.error("Error sending alert notifications: %s", e)

    def _compute_api_summary(self, api_metrics: List[APIMetrics]) -> Dict[str, Any]:
        """Compute API performance summary.

        Helper for get_performance_summary.
        """
        response_times = [m.response_time_ms for m in api_metrics]
        error_count = sum(1 for m in api_metrics if m.status_code >= 400)

        return {
            "total_requests": len(api_metrics),
            "average_response_time": statistics.mean(response_times),
            "p95_response_time": (
                sorted(response_times)[int(len(response_times) * 0.95)]
                if response_times
                else 0
            ),
            "error_rate": (error_count / len(api_metrics)) * 100,
            "requests_per_minute": len(
                [
                    m
                    for m in api_metrics
                    if (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(m.timestamp.replace("Z", "+00:00"))
                    ).seconds
                    < 60
                ]
            ),
        }

    def _compute_cache_summary(self) -> Dict[str, Any]:
        """Compute cache performance summary.

        Helper for get_performance_summary.
        """
        cache_summary = {}
        for cache_type, stats in self.cache_stats.items():
            total_ops = stats["hits"] + stats["misses"]
            if total_ops > 0:
                cache_summary[cache_type] = {
                    "hit_rate": (stats["hits"] / total_ops) * 100,
                    "total_operations": total_ops,
                    "total_size_mb": stats["total_size"] / (1024 * 1024),
                }
        return cache_summary

    def _compute_db_summary(self, db_metrics: List[DatabaseMetrics]) -> Dict[str, Any]:
        """Compute database performance summary.

        Helper for get_performance_summary.
        """
        execution_times = [m.execution_time_ms for m in db_metrics]
        slow_queries = sum(1 for m in db_metrics if m.execution_time_ms > 1000)

        return {
            "total_queries": len(db_metrics),
            "average_execution_time": statistics.mean(execution_times),
            "slow_query_count": slow_queries,
            "slow_query_rate": (slow_queries / len(db_metrics)) * 100,
        }

    def _compute_alerts_summary(self) -> Dict[str, Any]:
        """Compute active alerts summary.

        Helper for get_performance_summary.
        """
        return {
            "active_alerts": len(self.active_alerts),
            "critical_alerts": len(
                [a for a in self.active_alerts.values() if a.severity == "critical"]
            ),
            "high_alerts": len(
                [a for a in self.active_alerts.values() if a.severity == "high"]
            ),
            "total_alert_rules": len(self.alert_rules),
            "enabled_rules": len([r for r in self.alert_rules if r.enabled]),
        }

    async def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        try:
            api_metrics = list(self.api_metrics_buffer)
            api_summary = self._compute_api_summary(api_metrics) if api_metrics else {}

            cache_summary = self._compute_cache_summary()

            db_metrics = list(self.database_metrics_buffer)
            db_summary = self._compute_db_summary(db_metrics) if db_metrics else {}

            alerts_summary = self._compute_alerts_summary()

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "api_performance": api_summary,
                "cache_performance": cache_summary,
                "database_performance": db_summary,
                "alerting": alerts_summary,
                "system_health": (
                    "healthy" if len(self.active_alerts) == 0 else "degraded"
                ),
            }

        except Exception as e:
            self.logger.error(f"Error generating performance summary: {e}")
            return {"error": str(e)}

    async def generate_apm_report(self) -> Dict[str, Any]:
        """Generate comprehensive APM report."""
        try:
            summary = await self.get_performance_summary()

            # Add detailed metrics
            report = {
                "summary": summary,
                "active_alerts": [
                    asdict(alert) for alert in self.active_alerts.values()
                ],
                "alert_rules": [asdict(rule) for rule in self.alert_rules],
                "recent_api_metrics": [
                    asdict(m) for m in list(self.api_metrics_buffer)[-20:]
                ],
                "recent_cache_metrics": [
                    asdict(m) for m in list(self.cache_metrics_buffer)[-20:]
                ],
                "recent_database_metrics": [
                    asdict(m) for m in list(self.database_metrics_buffer)[-20:]
                ],
                "cache_stats": dict(self.cache_stats),
            }

            # Store report
            await self._store_apm_report(report)

            return report

        except Exception as e:
            self.logger.error(f"Error generating APM report: {e}")
            return {"error": str(e)}

    async def _store_apm_report(self, report: Dict[str, Any]):
        """Store APM report."""
        try:
            if self.redis_client:
                self.redis_client.hset(
                    "autobot:apm:latest_report",
                    mapping={
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": json.dumps(report, default=str),
                    },
                )

            # Store in file
            report_file = (
                self.apm_data_path
                / f"apm_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            try:
                async with aiofiles.open(report_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(report, indent=2, default=str))
            except OSError as e:
                self.logger.error(f"Failed to write APM report to {report_file}: {e}")

        except Exception as e:
            self.logger.error(f"Error storing APM report: {e}")


# Global APM instance for easy access (thread-safe, Issue #613)
_apm_instance = None
_apm_instance_lock = threading.Lock()


def get_apm_instance() -> AdvancedAPMSystem:
    """Get global APM instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety while
    minimizing lock contention after initialization (Issue #613).
    """
    global _apm_instance
    if _apm_instance is None:
        with _apm_instance_lock:
            # Double-check after acquiring lock
            if _apm_instance is None:
                _apm_instance = AdvancedAPMSystem()
    return _apm_instance


# Convenience decorators
def track_api(endpoint: str = None, method: str = "GET"):
    """Convenience decorator for API tracking."""
    apm = get_apm_instance()
    return apm.tracker.track_api(endpoint, method)


def track_database(database: str, operation: str = "query"):
    """Convenience decorator for database tracking."""
    apm = get_apm_instance()
    return apm.tracker.track_database(database, operation)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import argparse

    async def main():
        parser = argparse.ArgumentParser(description="AutoBot Advanced APM System")
        parser.add_argument(
            "--monitor", action="store_true", help="Start APM monitoring"
        )
        parser.add_argument("--report", action="store_true", help="Generate APM report")
        parser.add_argument(
            "--test", action="store_true", help="Test APM functionality"
        )

        args = parser.parse_args()

        apm = AdvancedAPMSystem()
        await apm.initialize_redis_connection()

        if args.test:
            logger.info("🧪 Testing APM functionality...")

            # Test API tracking
            trace_id = "test_trace_123"
            await apm.start_api_tracking("/api/test", "GET", trace_id)
            await asyncio.sleep(0.1)  # Simulate processing
            await apm.complete_api_tracking("/api/test", 200, 100.0, trace_id)

            # Test cache tracking
            await apm.track_cache_operation("redis", "get", "test_key", True, 5.0, 1024)

            # Test database tracking
            await apm.track_database_operation(
                "redis", "query", 50.0, True, rows_affected=10
            )

            logger.info("✅ APM test completed")

        elif args.report:
            logger.info("📊 Generating APM report...")
            report = await apm.generate_apm_report()
            logger.info("%s", json.dumps(report, indent=2, default=str))

        elif args.monitor:
            logger.info("🚀 Starting APM monitoring...")
            logger.info("📊 Performance Summary:")
            while True:
                summary = await apm.get_performance_summary()
                logger.info(f"System Health: {summary.get('system_health', 'unknown')}")
                logger.info(
                    f"Active Alerts: {summary.get('alerting', {}).get('active_alerts', 0)}"
                )

                api_perf = summary.get("api_performance", {})
                if api_perf:
                    logger.info(f"API Requests: {api_perf.get('total_requests', 0)}")
                    logger.info(
                        f"Avg Response Time: {api_perf.get('average_response_time', 0):.2f}ms"
                    )
                    logger.info(f"Error Rate: {api_perf.get('error_rate', 0):.2f}%")

                logger.info("%s", "=" * 50)
                await asyncio.sleep(30)  # Update every 30 seconds

    asyncio.run(main())
