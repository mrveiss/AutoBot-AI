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
import logging
import time
from typing import Any, Dict, List, Optional

import aiohttp
from auth_middleware import check_admin_permission
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Import AutoBot monitoring system
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

# Import monitoring utility functions
from backend.api.monitoring_utils import (
    _analyze_resource_utilization,
    _calculate_overall_health,
    _calculate_performance_score,
    _convert_metrics_to_csv,
    _identify_bottlenecks,
)

# Issue #474: Import ServiceURLs for AlertManager integration
from backend.constants.network_constants import ServiceURLs
from backend.type_defs.common import Metadata
from backend.utils.performance_monitor import (
    add_alert_callback,
    collect_metrics,
    get_optimization_recommendations,
    get_performance_dashboard,
    monitor_performance,
    performance_monitor,
    start_monitoring,
    stop_monitoring,
)
from config import ConfigManager

# Hardware monitor moved to monitoring_hardware.py (Issue #213)

logger = logging.getLogger(__name__)
config = ConfigManager()

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
                "recommendation": annotations.get(
                    "recommendation", "Check system logs"
                ),
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


class MonitoringStatus(BaseModel):
    """Monitoring system status"""

    active: bool
    uptime_seconds: float
    collection_interval: float
    hardware_acceleration: Dict[str, bool]
    metrics_collected: int
    alerts_count: int


class PerformanceAlert(BaseModel):
    """Performance alert model"""

    category: str
    severity: str
    message: str
    recommendation: str
    timestamp: float


class OptimizationRecommendation(BaseModel):
    """Performance optimization recommendation"""

    category: str
    priority: str
    recommendation: str
    action: str
    expected_improvement: str


class MetricsQuery(BaseModel):
    """Query parameters for metrics retrieval"""

    categories: Optional[List[str]] = Field(
        None, description="Metric categories to include"
    )
    time_range_minutes: int = Field(
        10, ge=1, le=1440, description="Time range in minutes"
    )
    include_trends: bool = Field(True, description="Include trend analysis")
    include_alerts: bool = Field(True, description="Include recent alerts")


class ThresholdUpdate(BaseModel):
    """Performance threshold update"""

    category: str
    metric: str
    threshold: float
    comparison: str = Field(..., pattern="^(gt|lt|eq)$")


# WebSocket connection manager for real-time updates
class MonitoringWebSocketManager:
    def __init__(self):
        """Initialize WebSocket manager with connection tracking and update task."""
        self.active_connections: List[WebSocket] = []
        self.update_task: Optional[asyncio.Task] = None
        self.update_interval = 2.0  # Send updates every 2 seconds

    async def connect(self, websocket: WebSocket):
        """Accept WebSocket connection and start periodic update task if first."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"WebSocket connected. Active connections: {len(self.active_connections)}"
        )

        # Start update task if this is the first connection
        if len(self.active_connections) == 1 and not self.update_task:
            self.update_task = asyncio.create_task(self._send_periodic_updates())

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection and cancel update task if last."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            f"WebSocket disconnected. Active connections: {len(self.active_connections)}"
        )

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_services_health",
    error_code_prefix="MONITORING",
)
@router.get("/services/health")
async def get_services_health():
    """Return service health in ServicesSummary format for frontend.

    Issue #1006: Frontend composables (usePrometheusMetrics, SystemArchitectureDiagram,
    ApiClient, api.ts) all call /api/monitoring/services/health expecting a
    ServicesSummary-shaped response.  Delegates to service_monitor helpers.
    """
    from backend.api.service_monitor import _check_http_health, _check_redis_health

    try:
        npu_url = config.get_service_url("npu_worker", "health")
        browser_url = config.get_service_url("browser", "health")
        ollama_url = f"{config.get_ollama_url()}/api/version"
    except Exception:
        npu_url = "http://172.16.168.22:8081/health"
        browser_url = "http://172.16.168.25:3000/health"
        ollama_url = "http://172.16.168.24:11434/api/version"

    results = await asyncio.gather(
        _check_redis_health(),
        _check_http_health(npu_url),
        _check_http_health(ollama_url),
        _check_http_health(browser_url),
        return_exceptions=True,
    )

    def _safe(res, default=("offline", "Error")):
        return res if isinstance(res, tuple) else default

    redis_s, redis_m = _safe(results[0])
    npu_s, npu_m = _safe(results[1])
    ollama_s, ollama_m = _safe(results[2])
    browser_s, browser_m = _safe(results[3])

    def _to_service(name, host, port, status, msg):
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

    svc_list = [
        _to_service("Backend API", "172.16.168.20", 8443, "online", "Running"),
        _to_service("Redis", "172.16.168.23", 6379, redis_s, redis_m),
        _to_service("NPU Worker", "172.16.168.22", 8081, npu_s, npu_m),
        _to_service("Ollama", "172.16.168.24", 11434, ollama_s, ollama_m),
        _to_service("Browser", "172.16.168.25", 3000, browser_s, browser_m),
    ]

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
        "services": svc_list,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_monitoring_status",
    error_code_prefix="MONITORING",
)
@router.get("/status", response_model=MonitoringStatus)
async def get_monitoring_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get current monitoring system status. Issue #744: Requires admin authentication."""
    dashboard = await get_performance_dashboard()  # Issue #430: properly await

    # Calculate uptime
    uptime_seconds = 0
    if performance_monitor.monitoring_active:
        uptime_seconds = time.time() - getattr(
            performance_monitor, "start_time", time.time()
        )

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_monitoring",
    error_code_prefix="MONITORING",
)
@router.post("/start")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_monitoring",
    error_code_prefix="MONITORING",
)
@router.post("/stop")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_dashboard",
    error_code_prefix="MONITORING",
)
@router.get("/dashboard")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dashboard_overview",
    error_code_prefix="MONITORING",
)
@router.get("/dashboard/overview")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_metrics",
    error_code_prefix="MONITORING",
)
@router.get("/metrics/current")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="query_metrics",
    error_code_prefix="MONITORING",
)
@router.post("/metrics/query")
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
                m
                for m in performance_monitor.gpu_metrics_buffer
                if start_time <= m.timestamp <= end_time
            ]
            result["metrics"]["gpu"] = [m.to_query_dict() for m in filtered_metrics]

        elif category == "npu" and performance_monitor.npu_metrics_buffer:
            filtered_metrics = [
                m
                for m in performance_monitor.npu_metrics_buffer
                if start_time <= m.timestamp <= end_time
            ]
            result["metrics"]["npu"] = [m.to_query_dict() for m in filtered_metrics]

        elif category == "system" and performance_monitor.system_metrics_buffer:
            filtered_metrics = [
                m
                for m in performance_monitor.system_metrics_buffer
                if start_time <= m.timestamp <= end_time
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_optimization_recommendations",
    error_code_prefix="MONITORING",
)
@router.get(
    "/optimization/recommendations", response_model=List[OptimizationRecommendation]
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_alerts",
    error_code_prefix="MONITORING",
)
@router.get("/alerts", response_model=List[PerformanceAlert])
async def get_performance_alerts(
    admin_check: bool = Depends(check_admin_permission),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    category: Optional[str] = Query(None, description="Filter by category"),
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_alerts",
    error_code_prefix="MONITORING",
)
@router.get("/alerts/check")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_alertmanager_alerts",
    error_code_prefix="MONITORING",
)
@router.get("/alerts/alertmanager")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_performance_threshold",
    error_code_prefix="MONITORING",
)
@router.post("/thresholds/update")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_metrics",
    error_code_prefix="MONITORING",
)
@router.get("/export/metrics")
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


def _build_export_data(
    start_time: float, end_time: float, time_range_hours: int, format: str
) -> dict:
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
        filtered_metrics = [
            m.__dict__ for m in metrics_buffer if start_time <= m.timestamp <= end_time
        ]
        if filtered_metrics:
            export_data["service_metrics"][service_name] = filtered_metrics


def _build_json_export_response(export_data: dict, end_time: float) -> JSONResponse:
    """Build JSON export response (Issue #665: extracted helper)."""
    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": (
                f"attachment; filename=autobot_metrics_{int(end_time)}.json"
            )
        },
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
        headers={
            "Content-Disposition": (
                f"attachment; filename=autobot_metrics_{int(end_time)}.csv"
            )
        },
    )


async def _handle_get_current_metrics(websocket: WebSocket, command: dict) -> None:
    """Handle get_current_metrics WebSocket command (Issue #315: extracted)."""
    metrics = await collect_metrics()
    await websocket.send_text(
        json.dumps({"type": "metrics_response", "data": metrics}, default=str)
    )


async def _handle_update_interval(websocket: WebSocket, command: dict) -> None:
    """Handle update_interval WebSocket command (Issue #315: extracted)."""
    new_interval = command.get("interval", 2.0)
    if not (0.5 <= new_interval <= 30.0):
        return
    ws_manager.update_interval = new_interval
    await websocket.send_text(
        json.dumps({"type": "interval_updated", "interval": new_interval})
    )


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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_performance_monitoring",
    error_code_prefix="MONITORING",
)
@router.post("/test/performance")
@monitor_performance("api_test")
async def test_performance_monitoring(
    admin_check: bool = Depends(check_admin_permission),
):
    """Test endpoint to demonstrate performance monitoring. Issue #744: Requires admin authentication."""
    # Simulate some work
    await asyncio.sleep(0.1)

    # Collect current metrics
    metrics = await collect_metrics()

    return {
        "message": "Performance monitoring test completed",
        "metrics_collected": metrics.get("collection_successful", False),
        "timestamp": time.time(),
    }


# ===== PROMETHEUS METRICS ENDPOINTS =====

from backend.monitoring.prometheus_metrics import get_metrics_manager


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_prometheus_metrics",
    error_code_prefix="MONITORING",
)
@router.get(
    "/metrics",
    summary="Prometheus Metrics Endpoint",
    description="Exposes metrics in Prometheus format for scraping",
)
async def get_prometheus_metrics(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Prometheus metrics endpoint. Issue #744: Requires admin authentication.

    Returns metrics in Prometheus text format for scraping by Prometheus server.
    Includes timeout tracking, latency metrics, connection pool stats,
    circuit breaker state, and request success/failure rates.
    """
    metrics_manager = get_metrics_manager()
    metrics_data = metrics_manager.get_metrics()

    return Response(
        content=metrics_data, media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="metrics_health_check",
    error_code_prefix="MONITORING",
)
@router.get(
    "/health/metrics",
    summary="Metrics Health Check",
    description="Verify metrics collection is working",
)
async def metrics_health_check(
    admin_check: bool = Depends(check_admin_permission),
):
    """Health check for Prometheus metrics system. Issue #744: Requires admin authentication."""
    metrics_manager = get_metrics_manager()
    metrics_data = metrics_manager.get_metrics()

    return {
        "status": "healthy",
        "metrics_count": len(metrics_data.decode("utf-8").split("\n")),
        "endpoint": "/api/monitoring/metrics",
        "format": "Prometheus text format",
        "metric_categories": [
            # Redis & Performance Metrics
            "autobot_timeout_total",
            "autobot_operation_duration_seconds",
            "autobot_timeout_rate",
            "autobot_redis_pool_connections",
            "autobot_redis_pool_saturation_ratio",
            "autobot_circuit_breaker_events_total",
            "autobot_circuit_breaker_state",
            "autobot_circuit_breaker_failure_count",
            "autobot_redis_requests_total",
            "autobot_redis_success_rate",
            # Workflow Metrics
            "autobot_workflow_executions_total",
            "autobot_workflow_duration_seconds",
            "autobot_workflow_steps_executed_total",
            "autobot_active_workflows",
            "autobot_workflow_approvals_total",
            # GitHub Integration Metrics
            "autobot_github_operations_total",
            "autobot_github_api_duration_seconds",
            "autobot_github_rate_limit_remaining",
            "autobot_github_commits_total",
            "autobot_github_pull_requests_total",
            "autobot_github_issues_total",
            # Task Execution Metrics
            "autobot_tasks_executed_total",
            "autobot_task_duration_seconds",
            "autobot_active_tasks",
            "autobot_task_queue_size",
            "autobot_task_retries_total",
        ],
    }
