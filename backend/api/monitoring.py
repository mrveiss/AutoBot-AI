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
from typing import Dict, List, Optional

from backend.type_defs.common import Metadata
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Import AutoBot monitoring system
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.performance_monitor import (
    add_phase9_alert_callback,
    collect_phase9_metrics,
    get_phase9_optimization_recommendations,
    get_phase9_performance_dashboard,
    monitor_performance,
    phase9_monitor,
    start_monitoring,
    stop_monitoring,
)

# Import monitoring utility functions
from backend.api.monitoring_utils import (
    _analyze_resource_utilization,
    _calculate_gpu_efficiency,
    _calculate_npu_efficiency,
    _calculate_overall_health,
    _calculate_performance_score,
    _convert_metrics_to_csv,
    _identify_bottlenecks,
)

# Import hardware monitor (extracted from this file - Issue #213)
from backend.api.monitoring_hardware import HardwareMonitor, hardware_monitor

logger = logging.getLogger(__name__)
router = APIRouter(tags=["AutoBot Monitoring"])


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
        self.active_connections: List[WebSocket] = []
        self.update_task: Optional[asyncio.Task] = None
        self.update_interval = 2.0  # Send updates every 2 seconds

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"WebSocket connected. Active connections: {len(self.active_connections)}"
        )

        # Start update task if this is the first connection
        if len(self.active_connections) == 1 and not self.update_task:
            self.update_task = asyncio.create_task(self._send_periodic_updates())

    def disconnect(self, websocket: WebSocket):
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
                logger.warning(f"Failed to send WebSocket message: {e}")
                disconnected.append(connection)

        # Remove disconnected connections
        for connection in disconnected:
            self.disconnect(connection)

    async def _send_periodic_updates(self):
        """Send periodic performance updates to connected clients"""
        while self.active_connections:
            try:
                # Get current performance data
                dashboard = get_phase9_performance_dashboard()

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
                logger.error(f"Error in periodic updates: {e}")
                await asyncio.sleep(self.update_interval)


# Global WebSocket manager
ws_manager = MonitoringWebSocketManager()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_monitoring_status",
    error_code_prefix="MONITORING",
)
@router.get("/status", response_model=MonitoringStatus)
async def get_monitoring_status():
    """Get current monitoring system status"""
    dashboard = get_phase9_performance_dashboard()

    # Calculate uptime
    uptime_seconds = 0
    if phase9_monitor.monitoring_active:
        uptime_seconds = time.time() - getattr(
            phase9_monitor, "start_time", time.time()
        )

    # Count metrics collected
    metrics_collected = (
        len(phase9_monitor.gpu_metrics_buffer)
        + len(phase9_monitor.npu_metrics_buffer)
        + len(phase9_monitor.multimodal_metrics_buffer)
        + len(phase9_monitor.system_metrics_buffer)
    )

    return MonitoringStatus(
        active=phase9_monitor.monitoring_active,
        uptime_seconds=uptime_seconds,
        collection_interval=phase9_monitor.collection_interval,
        hardware_acceleration=dashboard.get("hardware_acceleration", {}),
        metrics_collected=metrics_collected,
        alerts_count=len(phase9_monitor.performance_alerts),
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_monitoring",
    error_code_prefix="MONITORING",
)
@router.post("/start")
async def start_monitoring_endpoint(background_tasks: BackgroundTasks):
    """Start AutoBot performance monitoring"""
    if phase9_monitor.monitoring_active:
        return {
            "status": "already_running",
            "message": "AutoBot monitoring is already active",
        }

    # Start monitoring in background
    background_tasks.add_task(start_monitoring)

    # Add alert callback for WebSocket broadcasting
    async def alert_callback(alerts: List[Metadata]):
        await ws_manager.broadcast_update(
            {
                "type": "performance_alerts",
                "timestamp": time.time(),
                "alerts": alerts,
            }
        )

    add_phase9_alert_callback(alert_callback)

    return {
        "status": "started",
        "message": "AutoBot comprehensive performance monitoring started",
        "collection_interval": phase9_monitor.collection_interval,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_monitoring",
    error_code_prefix="MONITORING",
)
@router.post("/stop")
async def stop_monitoring_endpoint():
    """Stop AutoBot performance monitoring"""
    if not phase9_monitor.monitoring_active:
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
async def get_performance_dashboard():
    """Get comprehensive performance dashboard"""
    dashboard = get_phase9_performance_dashboard()

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
async def get_dashboard_overview():
    """Get dashboard overview data for frontend"""
    dashboard = get_phase9_performance_dashboard()

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
async def get_current_metrics():
    """Get current performance metrics snapshot"""
    metrics = await collect_phase9_metrics()
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
async def query_metrics(query: MetricsQuery):
    """Query historical performance metrics with filters"""
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
        if category == "gpu" and phase9_monitor.gpu_metrics_buffer:
            filtered_metrics = [
                m
                for m in phase9_monitor.gpu_metrics_buffer
                if start_time <= m.timestamp <= end_time
            ]
            result["metrics"]["gpu"] = [
                {
                    "timestamp": m.timestamp,
                    "utilization_percent": m.utilization_percent,
                    "memory_utilization_percent": m.memory_utilization_percent,
                    "temperature_celsius": m.temperature_celsius,
                    "power_draw_watts": m.power_draw_watts,
                }
                for m in filtered_metrics
            ]

        elif category == "npu" and phase9_monitor.npu_metrics_buffer:
            filtered_metrics = [
                m
                for m in phase9_monitor.npu_metrics_buffer
                if start_time <= m.timestamp <= end_time
            ]
            result["metrics"]["npu"] = [
                {
                    "timestamp": m.timestamp,
                    "utilization_percent": m.utilization_percent,
                    "acceleration_ratio": m.acceleration_ratio,
                    "inference_count": m.inference_count,
                    "average_inference_time_ms": m.average_inference_time_ms,
                }
                for m in filtered_metrics
            ]

        elif category == "system" and phase9_monitor.system_metrics_buffer:
            filtered_metrics = [
                m
                for m in phase9_monitor.system_metrics_buffer
                if start_time <= m.timestamp <= end_time
            ]
            result["metrics"]["system"] = [
                {
                    "timestamp": m.timestamp,
                    "cpu_usage_percent": m.cpu_usage_percent,
                    "memory_usage_percent": m.memory_usage_percent,
                    "cpu_load_1m": m.cpu_load_1m,
                    "network_latency_ms": m.network_latency_ms,
                }
                for m in filtered_metrics
            ]

    # Include trends if requested
    if query.include_trends:
        result["trends"] = phase9_monitor._calculate_performance_trends()

    # Include recent alerts if requested
    if query.include_alerts:
        result["alerts"] = [
            alert
            for alert in phase9_monitor.performance_alerts
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
async def get_optimization_recommendations():
    """Get performance optimization recommendations"""
    recommendations = get_phase9_optimization_recommendations()

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
    severity: Optional[str] = Query(None, description="Filter by severity"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of alerts"),
):
    """Get performance alerts with optional filtering"""
    alerts = list(phase9_monitor.performance_alerts)

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
async def check_alerts():
    """Check for performance alerts"""
    alerts = list(phase9_monitor.performance_alerts)

    return {
        "timestamp": time.time(),
        "alerts": alerts,
        "total_count": len(alerts),
        "critical_count": sum(1 for a in alerts if a.get("severity") == "critical"),
        "warning_count": sum(1 for a in alerts if a.get("severity") == "warning"),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_performance_threshold",
    error_code_prefix="MONITORING",
)
@router.post("/thresholds/update")
async def update_performance_threshold(threshold: ThresholdUpdate):
    """Update performance monitoring thresholds"""
    # Update threshold in monitoring system
    threshold_key = f"{threshold.category}_{threshold.metric}"

    if threshold_key in phase9_monitor.performance_baselines:
        old_value = phase9_monitor.performance_baselines[threshold_key]
        phase9_monitor.performance_baselines[threshold_key] = threshold.threshold

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
    operation="get_gpu_details",
    error_code_prefix="MONITORING",
)
@router.get("/hardware/gpu")
async def get_gpu_details():
    """Get detailed GPU information and metrics"""
    gpu_metrics = await phase9_monitor.collect_gpu_metrics()

    if not gpu_metrics:
        return {"available": False, "message": "GPU not available or accessible"}

    return {
        "available": True,
        "current_metrics": gpu_metrics.__dict__,
        "historical_data": [
            {
                "timestamp": m.timestamp,
                "utilization_percent": m.utilization_percent,
                "memory_utilization_percent": m.memory_utilization_percent,
                "temperature_celsius": m.temperature_celsius,
            }
            for m in list(phase9_monitor.gpu_metrics_buffer)[-60:]  # Last 60 samples
        ],
        "optimization_status": {
            "target_utilization": phase9_monitor.performance_baselines[
                "gpu_utilization_target"
            ],
            "current_efficiency": _calculate_gpu_efficiency(gpu_metrics),
            "throttling_detected": (
                gpu_metrics.thermal_throttling or gpu_metrics.power_throttling
            ),
        },
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_npu_details",
    error_code_prefix="MONITORING",
)
@router.get("/hardware/npu")
async def get_npu_details():
    """Get detailed NPU information and metrics"""
    npu_metrics = await phase9_monitor.collect_npu_metrics()

    if not npu_metrics:
        return {"available": False, "message": "NPU not available or not supported"}

    return {
        "available": True,
        "current_metrics": npu_metrics.__dict__,
        "historical_data": [
            {
                "timestamp": m.timestamp,
                "utilization_percent": m.utilization_percent,
                "acceleration_ratio": m.acceleration_ratio,
                "inference_count": m.inference_count,
            }
            for m in list(phase9_monitor.npu_metrics_buffer)[-60:]  # Last 60 samples
        ],
        "optimization_status": {
            "target_acceleration": phase9_monitor.performance_baselines[
                "npu_acceleration_target"
            ],
            "current_efficiency": _calculate_npu_efficiency(npu_metrics),
            "wsl_limitation": npu_metrics.wsl_limitation,
        },
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_services_health",
    error_code_prefix="MONITORING",
)
@router.get("/services/health")
async def get_services_health():
    """Get health status of all monitored services"""
    service_metrics = await phase9_monitor.collect_service_performance_metrics()

    services_health = {
        "timestamp": time.time(),
        "total_services": len(service_metrics),
        "healthy_services": sum(1 for s in service_metrics if s.status == "healthy"),
        "degraded_services": sum(1 for s in service_metrics if s.status == "degraded"),
        "critical_services": sum(
            1 for s in service_metrics if s.status in ["critical", "offline"]
        ),
        "services": [],
    }

    for service in service_metrics:
        services_health["services"].append(
            {
                "name": service.service_name,
                "host": service.host,
                "port": service.port,
                "status": service.status,
                "response_time_ms": service.response_time_ms,
                "health_score": service.health_score,
                "uptime_hours": service.uptime_hours,
            }
        )

    # Calculate overall system health
    if services_health["critical_services"] > 0:
        overall_status = "critical"
    elif services_health["degraded_services"] > 0:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    services_health["overall_status"] = overall_status
    services_health["health_percentage"] = (
        round(
            (services_health["healthy_services"] / services_health["total_services"])
            * 100,
            1,
        )
        if services_health["total_services"] > 0
        else 0
    )

    return services_health


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_metrics",
    error_code_prefix="MONITORING",
)
@router.get("/export/metrics")
async def export_metrics(
    format: str = Query("json", pattern="^(json|csv)$"),
    time_range_hours: int = Query(1, ge=1, le=168),  # Max 1 week
):
    """Export performance metrics in JSON or CSV format"""
    # Calculate time range
    end_time = time.time()
    start_time = end_time - (time_range_hours * 3600)

    # Collect all metrics within time range
    export_data = {
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

    # Filter GPU metrics
    for metric in phase9_monitor.gpu_metrics_buffer:
        if start_time <= metric.timestamp <= end_time:
            export_data["gpu_metrics"].append(metric.__dict__)

    # Filter NPU metrics
    for metric in phase9_monitor.npu_metrics_buffer:
        if start_time <= metric.timestamp <= end_time:
            export_data["npu_metrics"].append(metric.__dict__)

    # Filter system metrics
    for metric in phase9_monitor.system_metrics_buffer:
        if start_time <= metric.timestamp <= end_time:
            export_data["system_metrics"].append(metric.__dict__)

    # Filter service metrics
    for (
        service_name,
        metrics_buffer,
    ) in phase9_monitor.service_metrics_buffer.items():
        filtered_metrics = [
            m.__dict__ for m in metrics_buffer if start_time <= m.timestamp <= end_time
        ]
        if filtered_metrics:
            export_data["service_metrics"][service_name] = filtered_metrics

    if format == "json":
        # Return JSON response
        return JSONResponse(
            content=export_data,
            headers={
                "Content-Disposition": (
                    f"attachment; filename=autobot_metrics_{int(end_time)}.json"
                )
            },
        )

    elif format == "csv":
        # Convert to CSV and return as streaming response
        csv_content = _convert_metrics_to_csv(export_data)

        async def generate():
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


@router.websocket("/realtime")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="realtime_monitoring_websocket",
    error_code_prefix="MONITORING",
)
async def realtime_monitoring_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time performance monitoring updates"""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle client messages
            message = await websocket.receive_text()

            # Handle client commands
            try:
                command = json.loads(message)
                if command.get("type") == "get_current_metrics":
                    metrics = await collect_phase9_metrics()
                    await websocket.send_text(
                        json.dumps(
                            {"type": "metrics_response", "data": metrics}, default=str
                        )
                    )

                elif command.get("type") == "update_interval":
                    new_interval = command.get("interval", 2.0)
                    if 0.5 <= new_interval <= 30.0:
                        ws_manager.update_interval = new_interval
                        await websocket.send_text(
                            json.dumps(
                                {"type": "interval_updated", "interval": new_interval}
                            )
                        )

            except json.JSONDecodeError:
                # Ignore invalid JSON messages
                pass

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
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
async def test_performance_monitoring():
    """Test endpoint to demonstrate performance monitoring"""
    # Simulate some work
    await asyncio.sleep(0.1)

    # Collect current metrics
    metrics = await collect_phase9_metrics()

    return {
        "message": "Performance monitoring test completed",
        "metrics_collected": metrics.get("collection_successful", False),
        "timestamp": time.time(),
    }




# ===== PROMETHEUS METRICS ENDPOINTS =====

from src.monitoring.prometheus_metrics import get_metrics_manager


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
async def get_prometheus_metrics():
    """
    Prometheus metrics endpoint.

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
async def metrics_health_check():
    """Health check for Prometheus metrics system"""
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
