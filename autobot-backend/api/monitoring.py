# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Comprehensive Performance Monitoring API
Real-time monitoring dashboard for GPU/NPU utilization, multi-modal AI performance,
and distributed system optimization.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import aiohttp
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, StreamingResponse

# Hardware monitor moved to monitoring_hardware.py (Issue #213)
from api.monitoring_hardware import hardware_monitor

# Import monitoring utility functions
from api.monitoring_utils import (
    _analyze_resource_utilization,
    _calculate_overall_health,
    _calculate_performance_score,
    _convert_metrics_to_csv,
    _identify_bottlenecks,
)
from api.schemas_system import (
    AlertCheckResponse,
    AlertManagerResponse,
    ClaudeApiStatusResponse,
    CurrentMetricsResponse,
    GitHubStatusResponse,
    MetricsQuery,
    MonitoringActionResponse,
    MonitoringStatus,
    OptimizationRecommendation,
    PerformanceAlert,
    ServicesSummaryResponse,
    TestPerformanceResponse,
    ThresholdUpdate,
    ThresholdUpdateResponse,
)
from auth_middleware import check_admin_permission

# Import AutoBot monitoring system
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import get_config
from config.registry import ConfigRegistry

# Issue #474: Import ServiceURLs for AlertManager integration
from constants.network_constants import ServiceURLs
from constants.threshold_constants import TimingConstants
from type_defs.common import Metadata
from utils.performance_monitor import (
    add_alert_callback,
    collect_metrics,
    get_optimization_recommendations,
    get_performance_dashboard,
    monitor_performance,
    performance_monitor,
    start_monitoring,
    stop_monitoring,
)

logger = get_logger(__name__)

# Prometheus server URL — loaded once at import time via SSOT config (Issue #1283)
_ssot = get_config()
_PROMETHEUS_URL = f"http://{_ssot.vm.main}:{_ssot.port.prometheus}"


# External API status (extracted from monitoring_compat.py, Issue #1283)


async def _query_prometheus_instant(query: str) -> float | None:
    """Execute an instant PromQL query and return the scalar value.

    Uses the singleton HTTP client for connection reuse (Issue #65).

    Args:
        query: PromQL query string.

    Returns:
        Float value or None if no data or on error.
    """
    try:
        http_client = get_http_client()
        params = {"query": query}
        async with await http_client.get(
            f"{_PROMETHEUS_URL}/api/v1/query",
            params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status != 200:
                logger.warning("Prometheus instant query failed: %s", response.status)
                return None
            data = await response.json()
            if data.get("status") != "success":
                return None
            results = data.get("data", {}).get("result", [])
            if not results:
                return None
            return float(results[0]["value"][1])
    except aiohttp.ClientError as e:
        logger.error("Prometheus connection error: %s", e)
        return None
    except (KeyError, IndexError, ValueError) as e:
        logger.error("Error parsing Prometheus instant response: %s", e)
        return None


async def _query_prometheus_range(
    query: str, start: datetime, end: datetime, step: str = "15s"
) -> List[Dict[str, Any]]:
    """Execute a range PromQL query and return time-series data points.

    Uses the singleton HTTP client for connection reuse (Issue #65).

    Args:
        query: PromQL query string.
        start: Start of the query window.
        end: End of the query window.
        step: Resolution step (e.g. "15s", "1m").

    Returns:
        List of dicts with 'timestamp', 'value', and 'labels' keys.
    """
    try:
        http_client = get_http_client()
        params = {
            "query": query,
            "start": start.isoformat() + "Z",
            "end": end.isoformat() + "Z",
            "step": step,
        }
        async with await http_client.get(
            f"{_PROMETHEUS_URL}/api/v1/query_range",
            params=params,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status != 200:
                logger.warning("Prometheus range query failed: %s", response.status)
                return []
            data = await response.json()
            if data.get("status") != "success":
                return []
            results = data.get("data", {}).get("result", [])
            if not results:
                return []
            points: List[Dict[str, Any]] = []
            for result in results:
                metric = result.get("metric", {})
                for timestamp, value in result.get("values", []):
                    points.append(
                        {
                            "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                            "value": float(value),
                            "labels": metric,
                        }
                    )
            return points
    except aiohttp.ClientError as e:
        logger.error("Prometheus connection error: %s", e)
        return []
    except (KeyError, ValueError) as e:
        logger.error("Error parsing Prometheus range response: %s", e)
        return []


# Issue #474: AlertManager API timeout and cache
_ALERTMANAGER_TIMEOUT = 5.0  # seconds
_alertmanager_cache: Dict[str, Any] = {"alerts": [], "timestamp": 0, "ttl": 10}


async def _fetch_alertmanager_alerts() -> List[Dict[str, Any]]:
    """Fetch active alerts from Prometheus AlertManager.

    Issue #474: Provides real-time alert data from AlertManager.

    Returns:
        List of active alerts in frontend-compatible format.
    """
    current_time = time.time()

    # Return cached data if still valid
    if current_time - _alertmanager_cache["timestamp"] < _alertmanager_cache["ttl"]:
        return _alertmanager_cache["alerts"]

    try:
        async with aiohttp.ClientSession() as session:
            # AlertManager v2 API for active alerts
            url = f"{ServiceURLs.ALERTMANAGER_API}/api/v2/alerts"
            async with session.get(url, timeout=_ALERTMANAGER_TIMEOUT) as response:
                if response.status == 200:
                    raw_alerts = await response.json()
                    formatted_alerts = _format_alertmanager_alerts(raw_alerts)
                    _alertmanager_cache["alerts"] = formatted_alerts
                    _alertmanager_cache["timestamp"] = current_time
                    return formatted_alerts
                else:
                    logger.warning("AlertManager returned status %d", response.status)
                    return _alertmanager_cache["alerts"]  # Return stale cache
    except asyncio.TimeoutError:
        logger.warning("AlertManager request timed out")
        return _alertmanager_cache["alerts"]
    except aiohttp.ClientError as e:
        logger.warning("AlertManager connection error: %s", e)
        return _alertmanager_cache["alerts"]
    except Exception as e:
        logger.error("Failed to fetch AlertManager alerts: %s", e)
        return _alertmanager_cache["alerts"]


def _format_alertmanager_alerts(raw_alerts: List[Dict]) -> List[Dict[str, Any]]:
    """Convert AlertManager alert format to frontend-compatible format.

    Issue #474: Transforms AlertManager API response to match frontend expectations.
    """
    formatted = []
    for alert in raw_alerts:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})

        # Map AlertManager severity to frontend format
        severity = labels.get("severity", "medium")
        if severity == "warning":
            severity = "warning"
        elif severity in ("critical", "error"):
            severity = "critical"
        elif severity in ("info", "low"):
            severity = "info"

        formatted.append(
            {
                "timestamp": time.time(),  # Current time for sorting
                "starts_at": alert.get("startsAt", ""),
                "ends_at": alert.get("endsAt"),
                "severity": severity,
                "category": labels.get("component", labels.get("alertname", "system")),
                "message": annotations.get("summary", labels.get("alertname", "Alert")),
                "description": annotations.get("description", ""),
                "recommendation": annotations.get("recommendation", "Check system logs"),
                "alertname": labels.get("alertname", ""),
                "fingerprint": alert.get("fingerprint", ""),
                "status": alert.get("status", {}).get("state", "active"),
                "labels": labels,
                "source": "alertmanager",
            }
        )

    return formatted


router = APIRouter(tags=["AutoBot Monitoring"])

# Performance optimization: O(1) lookup for critical service statuses (Issue #326)
CRITICAL_SERVICE_STATUSES = {"critical", "offline"}


# WebSocket connection manager for real-time updates
class MonitoringWebSocketManager:
    def __init__(self):
        """Initialize WebSocket manager with connection tracking and update task."""
        self.active_connections: List[WebSocket] = []
        self.update_task: asyncio.Task | None = None
        self.update_interval = 2.0  # Send updates every 2 seconds

    async def connect(self, websocket: WebSocket):
        """Accept WebSocket connection and start periodic update task if first."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Active connections: {len(self.active_connections)}")

        # Start update task if this is the first connection
        if len(self.active_connections) == 1 and not self.update_task:
            self.update_task = asyncio.create_task(self._send_periodic_updates())

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection and cancel update task if last."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Active connections: {len(self.active_connections)}")

        # Stop update task if no connections
        if len(self.active_connections) == 0 and self.update_task:
            self.update_task.cancel()
            self.update_task = None

    async def broadcast_update(self, data: Metadata):
        """Broadcast update to all connected clients"""
        if not self.active_connections:
            return

        message = json.dumps(data, default=str)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning("Failed to send WebSocket message: %s", e)
                disconnected.append(connection)

        # Remove disconnected connections
        for connection in disconnected:
            self.disconnect(connection)

    async def _send_periodic_updates(self):
        """Send periodic performance updates to connected clients"""
        while self.active_connections:
            try:
                # Get current performance data (Issue #430: properly await async function)
                dashboard = await get_performance_dashboard()

                # Prepare update message
                update = {
                    "type": "performance_update",
                    "timestamp": time.time(),
                    "data": dashboard,
                }

                await self.broadcast_update(update)
                await asyncio.sleep(self.update_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in periodic updates: %s", e)
                await asyncio.sleep(self.update_interval)


# Global WebSocket manager
ws_manager = MonitoringWebSocketManager()


def _resolve_service_urls() -> tuple:
    """Helper for get_services_health. Ref: #1088, #6769.

    Resolve health-check URLs for NPU worker, browser, Ollama, and ChromaDB
    from the config manager, falling back to known static addresses on any error.
    """
    try:
        npu_url = f"http://{_ssot.vm.npu}:{_ssot.port.npu}/health"
        browser_url = f"http://{_ssot.vm.browser}:{_ssot.port.browser}/health"
        ollama_url = f"http://{_ssot.vm.ollama}:{_ssot.port.ollama}/api/version"
        chromadb_url = f"http://{_ssot.vm.aistack}:{_ssot.port.aistack}/api/v2/heartbeat"
    except Exception:
        # Issue #1229: Use ConfigRegistry (defaults from SSOT via registry_defaults)
        npu_host = ConfigRegistry.get("vm.npu")
        npu_port = ConfigRegistry.get("port.npu")
        browser_host = ConfigRegistry.get("vm.browser")
        browser_port = ConfigRegistry.get("port.browser")
        ollama_host = ConfigRegistry.get("vm.llm")
        ollama_port = ConfigRegistry.get("port.ollama")
        chromadb_host = ConfigRegistry.get("vm.aistack")
        chromadb_port = ConfigRegistry.get("port.aistack")
        npu_url = f"http://{npu_host}:{npu_port}/health"
        browser_url = f"http://{browser_host}:{browser_port}/health"
        ollama_url = f"http://{ollama_host}:{ollama_port}/api/version"
        chromadb_url = f"http://{chromadb_host}:{chromadb_port}/api/v2/heartbeat"
    return npu_url, browser_url, ollama_url, chromadb_url


def _safe_result(res, default=("offline", "Error")):
    """Return res if it is a tuple, else default. Ref: #2735."""
    return res if isinstance(res, tuple) else default


def _to_service_entry(name: str, host: str, port: int, status: str, msg: str) -> dict:
    """Build a single ServicesSummary-compatible dict. Ref: #2735."""
    is_healthy = status == "online"
    return {
        "name": name,
        "host": host,
        "port": port,
        "status": "healthy" if is_healthy else "offline",
        "response_time_ms": 0,
        "health_score": 100 if is_healthy else 0,
        "uptime_hours": 0,
    }


def _build_service_list(results: list) -> list:
    """Helper for get_services_health. Ref: #1088, #6769.

    Unpack asyncio.gather results into a ServicesSummary-compatible list.
    Each entry is a dict with name, host, port, status, response_time_ms,
    health_score, and uptime_hours fields.
    """
    redis_s, redis_m = _safe_result(results[0])
    npu_s, npu_m = _safe_result(results[1])
    ollama_s, ollama_m = _safe_result(results[2])
    browser_s, browser_m = _safe_result(results[3])
    chromadb_s, chromadb_m = _safe_result(results[4])

    # Issue #1229/#2671: Use ConfigRegistry (defaults from SSOT via registry_defaults)
    return [
        _to_service_entry(
            "Backend API",
            ConfigRegistry.get("vm.main"),
            int(ConfigRegistry.get("port.backend")),
            "online",
            "Running",
        ),
        _to_service_entry(
            "Redis",
            ConfigRegistry.get("vm.redis"),
            int(ConfigRegistry.get("port.redis")),
            redis_s,
            redis_m,
        ),
        _to_service_entry(
            "NPU Worker",
            ConfigRegistry.get("vm.npu"),
            int(ConfigRegistry.get("port.npu")),
            npu_s,
            npu_m,
        ),
        _to_service_entry(
            "Ollama",
            ConfigRegistry.get("vm.llm"),
            int(ConfigRegistry.get("port.ollama")),
            ollama_s,
            ollama_m,
        ),
        _to_service_entry(
            "Browser",
            ConfigRegistry.get("vm.browser"),
            int(ConfigRegistry.get("port.browser")),
            browser_s,
            browser_m,
        ),
        _to_service_entry(
            "ChromaDB",
            ConfigRegistry.get("vm.aistack"),
            int(ConfigRegistry.get("port.aistack")),
            chromadb_s,
            chromadb_m,
        ),
    ]


def _compute_overall_status(svc_list: list) -> dict:
    """Helper for get_services_health. Ref: #1088.

    Derive aggregate health counts and overall_status string from a service
    list produced by _build_service_list.  Returns the full ServicesSummary
    response dict (without the 'services' key -- caller merges it).
    """
    healthy = sum(1 for s in svc_list if s["status"] == "healthy")
    total = len(svc_list)
    degraded = 0
    critical = total - healthy

    if critical == 0:
        overall = "healthy"
    elif healthy > critical:
        overall = "degraded"
    else:
        overall = "critical"

    return {
        "total_services": total,
        "healthy_services": healthy,
        "degraded_services": degraded,
        "critical_services": critical,
        "overall_status": overall,
        "health_percentage": round((healthy / total) * 100) if total else 0,
    }


@router.get("/services/health", response_model=ServicesSummaryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_services_health",
    error_code_prefix="MONITORING",
)
async def get_services_health():
    """Return service health in ServicesSummary format for frontend.

    Issue #1006: Frontend composables (usePrometheusMetrics, SystemArchitectureDiagram,
    ApiClient, api.ts) all call /api/monitoring/services/health expecting a
    ServicesSummary-shaped response.  Delegates to service_monitor helpers.
    """
    from api.service_monitor import _check_http_health, _check_redis_health

    npu_url, browser_url, ollama_url, chromadb_url = _resolve_service_urls()

    results = await asyncio.gather(
        _check_redis_health(),
        _check_http_health(npu_url),
        _check_http_health(ollama_url),
        _check_http_health(browser_url),
        _check_http_health(chromadb_url),
        return_exceptions=True,
    )

    svc_list = _build_service_list(results)
    summary = _compute_overall_status(svc_list)
    summary["services"] = svc_list
    return summary


@router.get("/status", response_model=MonitoringStatus)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_monitoring_status",
    error_code_prefix="MONITORING",
)
async def get_monitoring_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get current monitoring system status. Issue #744: Requires admin authentication."""
    dashboard = await get_performance_dashboard()  # Issue #430: properly await

    # Calculate uptime
    uptime_seconds = 0
    if performance_monitor.monitoring_active:
        uptime_seconds = time.time() - getattr(performance_monitor, "start_time", time.time())

    # Count metrics collected
    metrics_collected = (
        len(performance_monitor.gpu_metrics_buffer)
        + len(performance_monitor.npu_metrics_buffer)
        + len(performance_monitor.multimodal_metrics_buffer)
        + len(performance_monitor.system_metrics_buffer)
    )

    return MonitoringStatus(
        active=performance_monitor.monitoring_active,
        uptime_seconds=uptime_seconds,
        collection_interval=performance_monitor.collection_interval,
        hardware_acceleration=dashboard.get("hardware_acceleration", {}),
        metrics_collected=metrics_collected,
        alerts_count=len(performance_monitor.performance_alerts),
    )


@router.post("/start", response_model=MonitoringActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_monitoring_endpoint",
    error_code_prefix="MONITORING",
)
async def start_monitoring_endpoint(
    admin_check: bool = Depends(check_admin_permission),
    background_tasks: BackgroundTasks = None,
):
    """Start AutoBot performance monitoring. Issue #744: Requires admin authentication."""
    if performance_monitor.monitoring_active:
        return {
            "status": "already_running",
            "message": "AutoBot monitoring is already active",
        }

    # Start monitoring in background
    background_tasks.add_task(start_monitoring)

    # Add alert callback for WebSocket broadcasting
    async def alert_callback(alerts: List[Metadata]):
        """Broadcast performance alerts to connected WebSocket clients."""
        await ws_manager.broadcast_update(
            {
                "type": "performance_alerts",
                "timestamp": time.time(),
                "alerts": alerts,
            }
        )

    add_alert_callback(alert_callback)

    return {
        "status": "started",
        "message": "AutoBot comprehensive performance monitoring started",
        "collection_interval": performance_monitor.collection_interval,
    }


@router.post("/stop", response_model=MonitoringActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_monitoring_endpoint",
    error_code_prefix="MONITORING",
)
async def stop_monitoring_endpoint(
    admin_check: bool = Depends(check_admin_permission),
):
    """Stop AutoBot performance monitoring. Issue #744: Requires admin authentication."""
    if not performance_monitor.monitoring_active:
        return {
            "status": "not_running",
            "message": "AutoBot monitoring is not currently active",
        }

    await stop_monitoring()

    return {
        "status": "stopped",
        "message": "AutoBot performance monitoring stopped",
    }


@router.get("/dashboard", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dashboard_endpoint",
    error_code_prefix="MONITORING",
)
async def get_dashboard_endpoint(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get comprehensive performance dashboard. Issue #744: Requires admin authentication."""
    dashboard = await get_performance_dashboard()  # Issue #430: properly await

    # Add additional analysis
    dashboard["analysis"] = {
        "overall_health": _calculate_overall_health(dashboard),
        "performance_score": _calculate_performance_score(dashboard),
        "bottlenecks": _identify_bottlenecks(dashboard),
        "resource_utilization": _analyze_resource_utilization(dashboard),
    }

    return dashboard


@router.get("/dashboard/overview", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dashboard_overview",
    error_code_prefix="MONITORING",
)
async def get_dashboard_overview(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get dashboard overview data for frontend. Issue #744: Requires admin authentication."""
    dashboard = await get_performance_dashboard()  # Issue #430: properly await

    # Add additional analysis
    dashboard["analysis"] = {
        "overall_health": _calculate_overall_health(dashboard),
        "performance_score": _calculate_performance_score(dashboard),
        "bottlenecks": _identify_bottlenecks(dashboard),
        "resource_utilization": _analyze_resource_utilization(dashboard),
    }

    return dashboard


@router.get("/metrics/current", response_model=CurrentMetricsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_metrics",
    error_code_prefix="MONITORING",
)
async def get_current_metrics(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get current performance metrics snapshot. Issue #744: Requires admin authentication."""
    metrics = await collect_metrics()
    return {
        "timestamp": time.time(),
        "metrics": metrics,
        "collection_successful": metrics.get("collection_successful", False),
    }


@router.post("/metrics/query", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="query_metrics",
    error_code_prefix="MONITORING",
)
async def query_metrics(
    admin_check: bool = Depends(check_admin_permission),
    query: MetricsQuery = None,
):
    """Query historical performance metrics with filters. Issue #744: Requires admin authentication."""
    result = {
        "query": query.dict(),
        "timestamp": time.time(),
        "metrics": {},
        "trends": {},
        "alerts": [],
    }

    # Calculate time range
    end_time = time.time()
    start_time = end_time - (query.time_range_minutes * 60)

    # Filter metrics by time range and categories
    categories = query.categories or [
        "gpu",
        "npu",
        "multimodal",
        "system",
        "services",
    ]

    for category in categories:
        # Issue #372: Use model methods to reduce feature envy
        if category == "gpu" and performance_monitor.gpu_metrics_buffer:
            filtered_metrics = [
                m for m in performance_monitor.gpu_metrics_buffer if start_time <= m.timestamp <= end_time
            ]
            result["metrics"]["gpu"] = [m.to_query_dict() for m in filtered_metrics]

        elif category == "npu" and performance_monitor.npu_metrics_buffer:
            filtered_metrics = [
                m for m in performance_monitor.npu_metrics_buffer if start_time <= m.timestamp <= end_time
            ]
            result["metrics"]["npu"] = [m.to_query_dict() for m in filtered_metrics]

        elif category == "system" and performance_monitor.system_metrics_buffer:
            filtered_metrics = [
                m for m in performance_monitor.system_metrics_buffer if start_time <= m.timestamp <= end_time
            ]
            result["metrics"]["system"] = [m.to_query_dict() for m in filtered_metrics]

    # Include trends if requested
    if query.include_trends:
        result["trends"] = performance_monitor._calculate_performance_trends()

    # Include recent alerts if requested
    if query.include_alerts:
        result["alerts"] = [
            alert
            for alert in performance_monitor.performance_alerts
            if start_time <= alert.get("timestamp", 0) <= end_time
        ]

    return result


@router.get("/optimization/recommendations", response_model=List[OptimizationRecommendation])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_optimization_recommendations_endpoint",
    error_code_prefix="MONITORING",
)
async def get_optimization_recommendations_endpoint(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get performance optimization recommendations. Issue #744: Requires admin authentication."""
    recommendations = await get_optimization_recommendations()  # Issue #430: await

    return [
        OptimizationRecommendation(
            category=rec["category"],
            priority=rec["priority"],
            recommendation=rec["recommendation"],
            action=rec["action"],
            expected_improvement=rec["expected_improvement"],
        )
        for rec in recommendations
    ]


@router.get("/alerts", response_model=List[PerformanceAlert])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_alerts",
    error_code_prefix="MONITORING",
)
async def get_performance_alerts(
    admin_check: bool = Depends(check_admin_permission),
    severity: str | None = Query(None, description="Filter by severity"),
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of alerts"),
):
    """Get performance alerts with optional filtering. Issue #744: Requires admin authentication."""
    alerts = list(performance_monitor.performance_alerts)

    # Apply filters
    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity]

    if category:
        alerts = [a for a in alerts if a.get("category") == category]

    # Sort by timestamp (most recent first) and limit
    alerts.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    alerts = alerts[:limit]

    return [
        PerformanceAlert(
            category=alert["category"],
            severity=alert["severity"],
            message=alert["message"],
            recommendation=alert["recommendation"],
            timestamp=alert["timestamp"],
        )
        for alert in alerts
    ]


@router.get("/alerts/check", response_model=AlertCheckResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_alerts",
    error_code_prefix="MONITORING",
)
async def check_alerts(
    admin_check: bool = Depends(check_admin_permission),
):
    """Check for performance alerts. Issue #744: Requires admin authentication.

    Issue #474: Now includes alerts from both performance_monitor (legacy) and
    Prometheus AlertManager (preferred). AlertManager alerts take precedence
    and include richer metadata from the Prometheus alerting rules.
    """
    # Get legacy performance alerts
    legacy_alerts = list(performance_monitor.performance_alerts)
    for alert in legacy_alerts:
        alert["source"] = "performance_monitor"

    # Issue #474: Fetch AlertManager alerts
    alertmanager_alerts = await _fetch_alertmanager_alerts()

    # Combine alerts (AlertManager first, then legacy)
    all_alerts = alertmanager_alerts + legacy_alerts

    return {
        "timestamp": time.time(),
        "alerts": all_alerts,
        "total_count": len(all_alerts),
        "critical_count": sum(1 for a in all_alerts if a.get("severity") == "critical"),
        "warning_count": sum(1 for a in all_alerts if a.get("severity") == "warning"),
        "high_count": sum(1 for a in all_alerts if a.get("severity") == "high"),
        "sources": {
            "alertmanager": len(alertmanager_alerts),
            "performance_monitor": len(legacy_alerts),
        },
    }


@router.get("/alerts/alertmanager", response_model=AlertManagerResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_alertmanager_alerts",
    error_code_prefix="MONITORING",
)
async def get_alertmanager_alerts(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get alerts directly from Prometheus AlertManager. Issue #744: Requires admin authentication.

    Issue #474: Direct access to AlertManager alerts with full metadata.
    This is the preferred endpoint for alert queries as it uses the
    Prometheus alerting stack rather than legacy monitoring.
    """
    alerts = await _fetch_alertmanager_alerts()

    # Group by severity
    by_severity = {"critical": [], "high": [], "warning": [], "info": []}
    for alert in alerts:
        severity = alert.get("severity", "info")
        if severity in by_severity:
            by_severity[severity].append(alert)
        else:
            by_severity["info"].append(alert)

    return {
        "timestamp": time.time(),
        "source": "alertmanager",
        "alertmanager_url": ServiceURLs.ALERTMANAGER_API,
        "alerts": alerts,
        "total_count": len(alerts),
        "by_severity": {
            "critical": len(by_severity["critical"]),
            "high": len(by_severity["high"]),
            "warning": len(by_severity["warning"]),
            "info": len(by_severity["info"]),
        },
        "active_alerts": by_severity,
    }


@router.post("/thresholds/update", response_model=ThresholdUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_performance_threshold",
    error_code_prefix="MONITORING",
)
async def update_performance_threshold(
    admin_check: bool = Depends(check_admin_permission),
    threshold: ThresholdUpdate = None,
):
    """Update performance monitoring thresholds. Issue #744: Requires admin authentication."""
    # Update threshold in monitoring system
    threshold_key = f"{threshold.category}_{threshold.metric}"

    if threshold_key in performance_monitor.performance_baselines:
        old_value = performance_monitor.performance_baselines[threshold_key]
        performance_monitor.performance_baselines[threshold_key] = threshold.threshold

        return {
            "status": "updated",
            "threshold_key": threshold_key,
            "old_value": old_value,
            "new_value": threshold.threshold,
            "comparison": threshold.comparison,
        }
    else:
        return {
            "status": "created",
            "threshold_key": threshold_key,
            "new_value": threshold.threshold,
            "comparison": threshold.comparison,
        }


@router.get("/export/metrics", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_metrics",
    error_code_prefix="MONITORING",
)
async def export_metrics(
    admin_check: bool = Depends(check_admin_permission),
    format: str = Query("json", pattern="^(json|csv)$"),
    time_range_hours: int = Query(1, ge=1, le=168),  # Max 1 week
):
    """Export performance metrics in JSON or CSV format. Issue #744: Requires admin authentication."""
    end_time = time.time()
    start_time = end_time - (time_range_hours * 3600)

    export_data = _build_export_data(start_time, end_time, time_range_hours, format)
    _filter_all_metrics(export_data, start_time, end_time)

    if format == "json":
        return _build_json_export_response(export_data, end_time)
    elif format == "csv":
        return _build_csv_export_response(export_data, end_time)


def _build_export_data(start_time: float, end_time: float, time_range_hours: int, format: str) -> dict:
    """Build initial export data structure (Issue #665: extracted helper)."""
    return {
        "export_info": {
            "timestamp": end_time,
            "time_range_hours": time_range_hours,
            "start_time": start_time,
            "end_time": end_time,
            "format": format,
        },
        "gpu_metrics": [],
        "npu_metrics": [],
        "system_metrics": [],
        "service_metrics": {},
    }


def _filter_all_metrics(export_data: dict, start_time: float, end_time: float) -> None:
    """Filter all metric types by time range (Issue #665: extracted helper)."""
    # Filter GPU metrics
    for metric in performance_monitor.gpu_metrics_buffer:
        if start_time <= metric.timestamp <= end_time:
            export_data["gpu_metrics"].append(metric.__dict__)

    # Filter NPU metrics
    for metric in performance_monitor.npu_metrics_buffer:
        if start_time <= metric.timestamp <= end_time:
            export_data["npu_metrics"].append(metric.__dict__)

    # Filter system metrics
    for metric in performance_monitor.system_metrics_buffer:
        if start_time <= metric.timestamp <= end_time:
            export_data["system_metrics"].append(metric.__dict__)

    # Filter service metrics
    for (
        service_name,
        metrics_buffer,
    ) in performance_monitor.service_metrics_buffer.items():
        filtered_metrics = [m.__dict__ for m in metrics_buffer if start_time <= m.timestamp <= end_time]
        if filtered_metrics:
            export_data["service_metrics"][service_name] = filtered_metrics


def _build_json_export_response(export_data: dict, end_time: float) -> JSONResponse:
    """Build JSON export response (Issue #665: extracted helper)."""
    return JSONResponse(
        content=export_data,
        headers={"Content-Disposition": (f"attachment; filename=autobot_metrics_{int(end_time)}.json")},
    )


def _build_csv_export_response(export_data: dict, end_time: float) -> StreamingResponse:
    """Build CSV export response (Issue #665: extracted helper)."""
    csv_content = _convert_metrics_to_csv(export_data)

    async def generate():
        """Yield CSV content as encoded bytes."""
        yield csv_content.encode()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": (f"attachment; filename=autobot_metrics_{int(end_time)}.csv")},
    )


async def _handle_get_current_metrics(websocket: WebSocket, command: dict) -> None:
    """Handle get_current_metrics WebSocket command (Issue #315: extracted)."""
    metrics = await collect_metrics()
    await websocket.send_text(json.dumps({"type": "metrics_response", "data": metrics}, default=str))


async def _handle_update_interval(websocket: WebSocket, command: dict) -> None:
    """Handle update_interval WebSocket command (Issue #315: extracted)."""
    new_interval = command.get("interval", 2.0)
    if not (0.5 <= new_interval <= 30.0):
        return
    ws_manager.update_interval = new_interval
    await websocket.send_text(json.dumps({"type": "interval_updated", "interval": new_interval}))


# WebSocket command handlers (Issue #315: dictionary dispatch pattern)
_MONITORING_WS_HANDLERS = {
    "get_current_metrics": _handle_get_current_metrics,
    "update_interval": _handle_update_interval,
}


@router.websocket("/realtime")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="realtime_monitoring_websocket",
    error_code_prefix="MONITORING",
)
async def realtime_monitoring_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time performance monitoring updates.

    Issue #315: Refactored to use dictionary dispatch for command handling.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive_text()
            try:
                command = json.loads(message)
                handler = _MONITORING_WS_HANDLERS.get(command.get("type"))
                if handler:
                    await handler(websocket, command)
            except json.JSONDecodeError as e:
                logger.debug("Invalid JSON in monitoring WebSocket: %s", e)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        ws_manager.disconnect(websocket)


# Helper functions
# Performance monitoring decorator endpoint
@router.post("/test/performance", response_model=TestPerformanceResponse)
@monitor_performance("api_test")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_performance_monitoring",
    error_code_prefix="MONITORING",
)
async def test_performance_monitoring(
    admin_check: bool = Depends(check_admin_permission),
):
    """Test endpoint to demonstrate performance monitoring. Issue #744: Requires admin authentication."""
    # Simulate some work
    await asyncio.sleep(TimingConstants.MICRO_DELAY)

    # Collect current metrics
    metrics = await collect_metrics()

    return {
        "message": "Performance monitoring test completed",
        "metrics_collected": metrics.get("collection_successful", False),
        "timestamp": time.time(),
    }


# Issue #1288: Prometheus metrics endpoints removed — consolidated into
# api/prometheus_endpoint.py at /api/metrics/prometheus (no auth, for scraping).
# The auth-protected duplicates here were unusable by Prometheus server.


# Issue #1190: Hardware stub endpoints for analytics dashboard
@router.get("/hardware/npu", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_hardware_npu_status",
    error_code_prefix="MONITORING",
)
async def get_hardware_npu_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get NPU hardware status. Issue #729: infrastructure monitoring on SLM server."""
    return await hardware_monitor.get_npu_status()


@router.get("/hardware/gpu", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_hardware_gpu_status",
    error_code_prefix="MONITORING",
)
async def get_hardware_gpu_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get GPU hardware status. Issue #729: infrastructure monitoring on SLM server."""
    return await hardware_monitor.get_gpu_status()


@router.get("/hardware/system", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_hardware_system_status",
    error_code_prefix="MONITORING",
)
async def get_hardware_system_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get system resource metrics (CPU, memory, disk)."""
    return await hardware_monitor.get_system_resources()


# External API status endpoints — extracted from monitoring_compat.py (Issue #1283)


@router.get("/claude-api/status", response_model=ClaudeApiStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_claude_api_status",
    error_code_prefix="MONITORING",
)
async def get_claude_api_status():
    """Get Claude API status via Prometheus metrics.

    Returns Prometheus-scraped Claude API rate limits, p95 latency, and
    failure rate.  Extracted from monitoring_compat.py (Issue #1283).
    """
    logger.info("Querying Claude API status from Prometheus")

    rate_limit, request_rate, p95_latency, failure_rate = await asyncio.gather(
        _query_prometheus_instant("autobot_claude_api_rate_limit_remaining"),
        _query_prometheus_instant("rate(autobot_claude_api_requests_total[5m]) * 60"),
        _query_prometheus_instant(
            "histogram_quantile(0.95, " "rate(autobot_claude_api_response_time_seconds_bucket[5m]))"
        ),
        _query_prometheus_instant(
            'rate(autobot_claude_api_requests_total{success="false"}[5m])'
            " / rate(autobot_claude_api_requests_total[5m])"
        ),
    )

    return {
        "success": True,
        "claude_api_status": {
            "rate_limit_remaining": rate_limit,
            "requests_per_minute": request_rate,
            "p95_latency_seconds": p95_latency,
            "failure_rate": failure_rate,
        },
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/github/status", response_model=GitHubStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_github_status",
    error_code_prefix="MONITORING",
)
async def get_github_status():
    """Get GitHub API status via Prometheus metrics.

    Returns Prometheus-scraped GitHub API rate limits, operation counts, and
    p95 latency.  Extracted from monitoring_compat.py (Issue #1283).
    """
    logger.info("Querying GitHub API status from Prometheus")

    rate_limit, total_ops, p95_latency = await asyncio.gather(
        _query_prometheus_instant("autobot_github_api_rate_limit_remaining"),
        _query_prometheus_instant("sum(autobot_github_api_operations_total)"),
        _query_prometheus_instant("histogram_quantile(0.95, " "rate(autobot_github_api_duration_seconds_bucket[5m]))"),
    )

    return {
        "success": True,
        "github_status": {
            "rate_limit_remaining": rate_limit,
            "total_operations": total_ops,
            "p95_latency_seconds": p95_latency,
        },
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
