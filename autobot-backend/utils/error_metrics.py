# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Error Metrics Collection and Monitoring

Tracks error occurrences, aggregates statistics, and provides monitoring data
for the error handling system. Integrates with error_boundaries and error_catalog.

Phase 5 (Issue #348 / #9983):
  WRITE path — boundary_manager → record_error_metric → ErrorMetricsCollector.record_error
               → prometheus.record_error(category, component, error_code)
               → autobot_errors_total{category, component, error_code} counter

  READ  path — implemented here: instant/range PromQL via the shared
               autobot_shared.monitoring.prometheus_query helper.

NOTE on labels:
  ``autobot_errors_total`` carries labels: category / component / error_code.
  There is NO ``severity`` label on this counter — severity lives only in the
  per-event Redis records written by boundary_manager (``autobot:errors:*``).

Resolution state:
  Prometheus is aggregate-only and cannot resolve individual traces.
  ``mark_resolved`` stores the trace_id in a Redis set (``errors:resolved``)
  with a configurable TTL (env var AUTOBOT_ERROR_RESOLVED_TTL_SECONDS,
  default 7 days).  ``_fetch_recent_errors_from_redis`` in boundary_manager
  annotates each error dict with ``resolved=True`` when its trace_id is present
  in that set.
"""

import asyncio
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from autobot_shared.error_boundaries import ErrorCategory
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Module-level TTL constant (env-var backed, never hard-coded)
# ---------------------------------------------------------------------------

def _resolve_error_resolved_ttl() -> int:
    """Return TTL seconds for errors:resolved Redis set membership.

    Reads AUTOBOT_ERROR_RESOLVED_TTL_SECONDS via config.misc (str field,
    empty = default).  Falls back to 7 days.
    """
    from autobot_shared.ssot_constants import TTL_7_DAYS

    raw = getattr(config.misc, "error_resolved_ttl_seconds", "")
    if not raw:
        return TTL_7_DAYS
    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "AUTOBOT_ERROR_RESOLVED_TTL_SECONDS=%r is not an integer; "
            "falling back to 7 days",
            raw,
        )
        return TTL_7_DAYS
    if value <= 0:
        logger.warning(
            "AUTOBOT_ERROR_RESOLVED_TTL_SECONDS=%d must be positive; "
            "falling back to 7 days",
            value,
        )
        return TTL_7_DAYS
    return value


_ERROR_RESOLVED_TTL: int = _resolve_error_resolved_ttl()

_REDIS_RESOLVED_KEY = "errors:resolved"


def _escape_promql_label_value(value: str) -> str:
    """Escape a string for safe interpolation inside a PromQL double-quoted
    label value (#9983 review — prevents PromQL injection via request params).

    Per Prometheus rules, backslash and double-quote are the only characters
    that can terminate or escape within a quoted label value, so escaping them
    fully contains the value. Length is capped as defence-in-depth.
    """
    return value[:128].replace("\\", "\\\\").replace('"', '\\"')


@dataclass
class ErrorMetric:
    """
    Single error occurrence metric

    DEPRECATED (Phase 5, Issue #348): No longer used. Metrics stored in Prometheus only.
    Kept for backward compatibility.
    """

    error_code: str | None
    category: str
    component: str
    function: str
    timestamp: float
    message: str
    trace_id: str | None = None
    user_id: str | None = None
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

    error_code: str | None
    category: str
    component: str
    total_count: int = 0
    last_occurrence: float | None = None
    first_occurrence: float | None = None
    hourly_counts: Dict[str, int] = field(default_factory=dict)
    retry_count: int = 0
    resolved_count: int = 0
    error_rate: float = 0.0  # errors per minute

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)


class ErrorMetricsCollector:
    """
    Collects and aggregates error metrics.

    Phase 5 (Issue #348 / #9983): Prometheus is the write target; PromQL is
    the read source.  Resolution state is tracked in Redis only (Prometheus
    cannot address individual traces).

    Features:
    - Error recording to Prometheus
    - Instant-query summary / top-errors via PromQL
    - Range-query timeline via PromQL
    - Redis-backed per-trace resolution state
    - Alerting threshold detection
    """

    def __init__(self, redis_client=None):
        """
        Initialize error metrics collector

        Args:
            redis_client: DEPRECATED - no longer used (kept for API compat)
        """
        if redis_client is not None:
            logger.warning(
                "redis_client parameter is deprecated and ignored. "
                "Prometheus is now the primary metrics store."
            )

        self._alert_thresholds: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._last_error_counts: Dict[str, int] = defaultdict(int)

        # Prometheus write client (local counter only)
        try:
            from monitoring.prometheus_metrics import get_metrics_manager

            self.prometheus = get_metrics_manager()
        except (ImportError, Exception) as e:
            logger.warning("Prometheus metrics not available: %s", e)
            self.prometheus = None

        # Lazy Redis client for resolution-state set
        self._redis = None

    def _get_redis(self):
        """Return the shared Redis client, initialising it on first call."""
        if self._redis is None:
            try:
                from autobot_shared.redis_client import get_redis_client

                self._redis = get_redis_client()
            except Exception as exc:
                logger.warning("Redis client unavailable for error resolution: %s", exc)
        return self._redis

    # ------------------------------------------------------------------
    # WRITE PATH
    # ------------------------------------------------------------------

    async def record_error(
        self,
        error_code: str | None,
        category: ErrorCategory,
        component: str,
        function: str,
        message: str,
        trace_id: str | None = None,
        user_id: str | None = None,
        retry_attempted: bool = False,
    ) -> None:
        """
        Record an error occurrence to Prometheus.

        Phase 5 (Issue #348): Records to Prometheus only.
        """
        if self.prometheus:
            self.prometheus.record_error(category.value, component, error_code or "unknown")

        async with self._lock:
            threshold_key = f"{component}:{error_code or category.value}"
            self._last_error_counts[threshold_key] += 1
            current_count = self._last_error_counts[threshold_key]

        await self._check_alerts(component, error_code, current_count)
        logger.debug("Recorded error metric to Prometheus: %s/%s", component, error_code or category.value)

    async def _check_alerts(self, component: str, error_code: str | None, current_count: int) -> None:
        """Check if error count exceeds alert thresholds and send notifications."""
        threshold_key = f"{component}:{error_code or 'any'}"
        threshold = self._alert_thresholds.get(threshold_key, 0)
        if threshold > 0 and current_count >= threshold:
            logger.warning(
                "Error alert threshold exceeded: %s (%d >= %d)",
                threshold_key,
                current_count,
                threshold,
            )
            await self._send_alert_notification(component, error_code, current_count, threshold)

    async def _send_alert_notification(
        self,
        component: str,
        error_code: str | None,
        current_count: int,
        threshold: int,
    ) -> None:
        """Log alert threshold exceeded (AlertManager handles actual notifications)."""
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
            "Error threshold exceeded [%s] %s/%s: %d errors (threshold: %d). "
            "AlertManager will handle notifications based on Prometheus metrics.",
            severity.upper(),
            component,
            error_code or "any",
            current_count,
            threshold,
        )

    # ------------------------------------------------------------------
    # READ PATH — Prometheus-backed
    # ------------------------------------------------------------------

    async def mark_resolved(self, trace_id: str) -> bool:
        """
        Mark an error trace as resolved via Redis set membership.

        Prometheus is aggregate-only and cannot address individual traces;
        resolution state is therefore stored in Redis set ``errors:resolved``
        with TTL ``_ERROR_RESOLVED_TTL`` (env AUTOBOT_ERROR_RESOLVED_TTL_SECONDS,
        default 7 days).

        Returns:
            True on success, False if Redis is unavailable.
        """
        redis = self._get_redis()
        if redis is None:
            logger.warning("mark_resolved: Redis unavailable, cannot persist resolution for %s", trace_id)
            return False
        try:
            await asyncio.to_thread(redis.sadd, _REDIS_RESOLVED_KEY, trace_id)
            await asyncio.to_thread(redis.expire, _REDIS_RESOLVED_KEY, _ERROR_RESOLVED_TTL)
            logger.info("Error trace %s marked as resolved (TTL=%ds)", trace_id, _ERROR_RESOLVED_TTL)
            return True
        except Exception as exc:
            logger.error("Failed to mark trace %s as resolved: %s", trace_id, exc)
            return False

    async def is_resolved(self, trace_id: str) -> bool:
        """Return True if *trace_id* is in the resolved set."""
        redis = self._get_redis()
        if redis is None:
            return False
        try:
            return bool(await asyncio.to_thread(redis.sismember, _REDIS_RESOLVED_KEY, trace_id))
        except Exception:
            return False

    async def get_resolved_ids(self) -> set[str]:
        """Return the full set of resolved error/trace ids (one Redis call).

        Lets async callers annotate a batch of recent errors with their
        ``resolved`` status without an N+1 of ``is_resolved`` (#9983).
        """
        redis = self._get_redis()
        if redis is None:
            return set()
        try:
            members = await asyncio.to_thread(redis.smembers, _REDIS_RESOLVED_KEY)
            return {m.decode() if isinstance(m, bytes) else str(m) for m in (members or [])}
        except Exception:
            return set()

    async def get_summary(self) -> Dict[str, Any]:
        """
        Return a comprehensive error metrics summary from Prometheus.

        PromQL queries:
          total        = ``sum(autobot_errors_total)``
          by_category  = ``sum by (category)(autobot_errors_total)``
          by_component = ``sum by (component)(autobot_errors_total)``
          unique count = ``count(sum by (component, error_code)(autobot_errors_total))``

        NOTE: ``autobot_errors_total`` has no ``severity`` label — severity is
        only available in the per-event Redis records (``autobot:errors:*``).

        Returns empty/zero dict when Prometheus is unreachable.
        """
        try:
            from autobot_shared.monitoring.prometheus_query import query_instant
        except ImportError:
            logger.warning("prometheus_query helper unavailable")
            return _empty_summary()

        total_data, cat_data, comp_data, uniq_data = await asyncio.gather(
            query_instant("sum(autobot_errors_total)"),
            query_instant("sum by (category)(autobot_errors_total)"),
            query_instant("sum by (component)(autobot_errors_total)"),
            query_instant("count(sum by (component, error_code)(autobot_errors_total))"),
        )

        total = _scalar_from_instant(total_data)
        category_breakdown = _label_map_from_instant(cat_data, "category")
        component_breakdown = _label_map_from_instant(comp_data, "component")
        distinct_error_types = int(_scalar_from_instant(uniq_data))

        return {
            "total_errors": int(total),
            "unique_error_types": distinct_error_types,
            "category_breakdown": category_breakdown,
            "component_breakdown": component_breakdown,
            "alert_thresholds_configured": len(self._alert_thresholds),
            "prometheus_available": True,
        }

    async def get_top_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Return the top-N most frequent errors from Prometheus.

        PromQL: ``topk(<limit>, sum by (component, error_code)(autobot_errors_total))``

        Returns a list of dicts:
          ``{"component": str, "error_code": str, "count": int}``

        Empty list when Prometheus is unreachable.
        """
        try:
            from autobot_shared.monitoring.prometheus_query import query_instant
        except ImportError:
            logger.warning("prometheus_query helper unavailable")
            return []

        promql = f"topk({limit}, sum by (component, error_code)(autobot_errors_total))"
        data = await query_instant(promql)
        if data is None:
            return []
        results = []
        for item in data.get("result", []):
            metric = item.get("metric", {})
            _, val = item.get("value", [None, "0"])
            results.append(
                {
                    "component": metric.get("component", "unknown"),
                    "error_code": metric.get("error_code", "unknown"),
                    "count": int(float(val)),
                }
            )
        return results

    async def get_error_timeline(
        self, hours: int = 24, component: str | None = None
    ) -> List[Dict[str, Any]]:
        """
        Return time-bucketed error rate points from Prometheus.

        PromQL:
          no filter  → ``sum(rate(autobot_errors_total[5m]))``
          with filter→ ``sum(rate(autobot_errors_total{component="<c>"}[5m]))``

        Returns a list of ``{"timestamp": ISO-str, "value": float}`` dicts,
        or ``[]`` when Prometheus is unreachable.
        """
        try:
            from autobot_shared.monitoring.prometheus_query import query_range
        except ImportError:
            logger.warning("prometheus_query helper unavailable")
            return []

        if component:
            # Security (#9983 review): the component label value comes from a
            # request query param — escape per Prometheus rules so it cannot
            # break out of the quoted label and inject arbitrary PromQL.
            safe_component = _escape_promql_label_value(component)
            promql = f'sum(rate(autobot_errors_total{{component="{safe_component}"}}[5m]))'
        else:
            promql = "sum(rate(autobot_errors_total[5m]))"

        points = await query_range(promql, hours=hours, step="5m")
        return [{"timestamp": p["timestamp"], "value": p["value"]} for p in points]

    # ------------------------------------------------------------------
    # Deprecated / legacy stubs kept for API compatibility
    # ------------------------------------------------------------------

    def get_stats(self, component: str | None = None) -> List[ErrorStats]:
        """DEPRECATED (Phase 5, Issue #348): returns empty list."""
        logger.warning(
            "get_stats() is deprecated. Query Prometheus directly:\n"
            "  sum(autobot_errors_total) by (component, category, error_code)"
        )
        return []

    def get_category_breakdown(self) -> Dict[str, int]:
        """DEPRECATED (Phase 5, Issue #348): returns empty dict."""
        logger.warning(
            "get_category_breakdown() is deprecated. Query Prometheus:\n"
            "  sum(autobot_errors_total) by (category)"
        )
        return {}

    def get_component_breakdown(self) -> Dict[str, int]:
        """DEPRECATED (Phase 5, Issue #348): returns empty dict."""
        logger.warning(
            "get_component_breakdown() is deprecated. Query Prometheus:\n"
            "  sum(autobot_errors_total) by (component)"
        )
        return {}

    def set_alert_threshold(self, component: str, error_code: str | None, threshold: int) -> None:
        """Set alert threshold for a component/error combination."""
        threshold_key = f"{component}:{error_code or 'any'}"
        self._alert_thresholds[threshold_key] = threshold
        logger.info("Set alert threshold: %s = %s", threshold_key, threshold)

    async def cleanup_old_metrics(self) -> int:
        """DEPRECATED (Phase 5, Issue #348): no-op; Prometheus handles retention."""
        logger.warning(
            "cleanup_old_metrics() is deprecated. "
            "Configure Prometheus retention in prometheus.yml instead."
        )
        return 0

    async def reset_stats(self, component: str | None = None) -> None:
        """Reset local threshold counters only (Prometheus counters are immutable)."""
        async with self._lock:
            if component:
                keys_to_remove = [k for k in self._last_error_counts if k.startswith(f"{component}:")]
                for key in keys_to_remove:
                    del self._last_error_counts[key]
                logger.info("Reset threshold counters for component: %s", component)
            else:
                self._last_error_counts.clear()
                logger.info("Reset all threshold counters")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _empty_summary() -> Dict[str, Any]:
    """Return a zero-valued summary when Prometheus is unavailable."""
    return {
        "total_errors": 0,
        "unique_error_types": 0,
        "category_breakdown": {},
        "component_breakdown": {},
        "alert_thresholds_configured": 0,
        "prometheus_available": False,
    }


def _scalar_from_instant(data: Dict[str, Any] | None) -> float:
    """Extract scalar value from a Prometheus instant query result."""
    if data is None:
        return 0.0
    results = data.get("result", [])
    if not results:
        return 0.0
    _, val = results[0].get("value", [None, "0"])
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _label_map_from_instant(data: Dict[str, Any] | None, label_key: str) -> Dict[str, int]:
    """Build {label_value: count} from a by-label instant query."""
    if data is None:
        return {}
    out: Dict[str, int] = {}
    for item in data.get("result", []):
        label_val = item.get("metric", {}).get(label_key, "unknown")
        _, val = item.get("value", [None, "0"])
        try:
            out[label_val] = int(float(val))
        except (TypeError, ValueError):
            out[label_val] = 0
    return out


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_metrics_collector = lazy_singleton(ErrorMetricsCollector)


def get_metrics_collector(redis_client=None) -> ErrorMetricsCollector:
    """
    Return the global metrics collector instance (thread-safe singleton).
    """
    return _metrics_collector(redis_client)


async def record_error_metric(
    error_code: str | None,
    category: ErrorCategory,
    component: str,
    function: str,
    message: str,
    **kwargs,
) -> None:
    """Convenience function to record an error metric."""
    collector = get_metrics_collector()
    await collector.record_error(error_code, category, component, function, message, **kwargs)
