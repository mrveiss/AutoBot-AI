# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Metrics API endpoints for workflow performance monitoring
"""

import asyncio
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query

# Prometheus query helpers shared from monitoring module (Issue #1283)
from api.monitoring import _query_prometheus_range
from api.schemas_analytics import (
    MetricsDashboardResponse,
    MetricsExportResponse,
    MetricsMonitoringStartResponse,
    MetricsMonitoringStopResponse,
    MetricsPerformanceSummaryResponse,
    MetricsSystemCurrentResponse,
    MetricsSystemHistoryResponse,
    MetricsSystemSummaryResponse,
    MetricsWorkflowResponse,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from metrics.system_monitor import system_monitor
from metrics.workflow_metrics import workflow_metrics

logger = get_logger(__name__)

router = APIRouter()


@router.get("/workflow/{workflow_id}", response_model=MetricsWorkflowResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_workflow_metrics",
    error_code_prefix="METRICS",
)
async def get_workflow_metrics(workflow_id: str):
    """Get metrics for a specific workflow"""
    try:
        stats = workflow_metrics.get_workflow_stats(workflow_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Workflow metrics not found")

        return {"success": True, "workflow_id": workflow_id, "metrics": stats}

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get workflow metrics")


@router.get("/performance/summary", response_model=MetricsPerformanceSummaryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_summary",
    error_code_prefix="METRICS",
)
async def get_performance_summary(
    time_window_hours: int = Query(default=24, ge=1, le=168, description="Time window in hours (1-168)")
):
    """Get overall performance summary"""
    try:
        summary = workflow_metrics.get_performance_summary(time_window_hours)

        return {"success": True, "performance_summary": summary}

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get performance summary")


@router.get("/system/current", response_model=MetricsSystemCurrentResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_system_metrics",
    error_code_prefix="METRICS",
)
async def get_current_system_metrics():
    """Get current system resource metrics"""
    try:
        metrics = system_monitor.get_current_metrics()

        return {"success": True, "system_metrics": metrics}

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get system metrics")


# CPU/memory time-series via Prometheus — extracted from monitoring_compat.py (Issue #1283)

_HISTORY_DURATION_MAP = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
}


@router.get("/system/history", response_model=MetricsSystemHistoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_metrics_history",
    error_code_prefix="METRICS",
)
async def get_system_metrics_history(
    duration: str = Query("1h", description="Time duration (e.g., 15m, 1h, 6h, 1d, 7d)"),
    step: str = Query("15s", description="Data point resolution interval"),
):
    """Get historical CPU and memory metrics from Prometheus.

    Supports time windows from 15 minutes to 7 days.  Queries Prometheus for
    autobot_cpu_usage_percent and autobot_memory_usage_percent range data.
    Extracted from monitoring_compat.py (Issue #1283).
    """
    logger.info("Fetching system metrics history: duration=%s step=%s", duration, step)

    delta = _HISTORY_DURATION_MAP.get(duration, timedelta(hours=1))
    end = now_utc()
    start = end - delta

    cpu_history, memory_history = await asyncio.gather(
        _query_prometheus_range("autobot_cpu_usage_percent", start, end, step),
        _query_prometheus_range("autobot_memory_usage_percent", start, end, step),
    )

    return {
        "success": True,
        "cpu_history": cpu_history,
        "memory_history": memory_history,
        "time_range": {"start": start.isoformat(), "end": end.isoformat()},
    }


@router.get("/system/summary", response_model=MetricsSystemSummaryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_summary",
    error_code_prefix="METRICS",
)
async def get_system_summary(
    minutes: int = Query(default=10, ge=1, le=60, description="Time window in minutes (1-60)")
):
    """Get system resource usage summary"""
    try:
        summary = system_monitor.get_resource_summary(minutes)

        return {"success": True, "resource_summary": summary}

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get resource summary")


# Health check moved to consolidated health service
# See backend/services/consolidated_health_service.py
# Use /api/system/health?detailed=true for comprehensive status


@router.get("/export/workflow", response_model=MetricsExportResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_workflow_metrics",
    error_code_prefix="METRICS",
)
async def export_workflow_metrics(format: str = Query(default="json", description="Export format")):
    """Export workflow metrics data"""
    try:
        export_data = workflow_metrics.export_metrics(format)

        return {"success": True, "format": format, "data": export_data}

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to export metrics")


@router.get("/export/system", response_model=MetricsExportResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_system_metrics",
    error_code_prefix="METRICS",
)
async def export_system_metrics(format: str = Query(default="json", description="Export format")):
    """Export system resource monitoring data"""
    try:
        export_data = system_monitor.export_resource_data(format)

        return {"success": True, "format": format, "data": export_data}

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to export system data")


@router.post("/system/monitoring/start", response_model=MetricsMonitoringStartResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_system_monitoring",
    error_code_prefix="METRICS",
)
async def start_system_monitoring():
    """Start continuous system monitoring"""
    try:
        await system_monitor.start_monitoring()

        return {
            "success": True,
            "message": "System monitoring started",
            "collection_interval": system_monitor.collection_interval,
        }

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to start monitoring")


@router.post("/system/monitoring/stop", response_model=MetricsMonitoringStopResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_system_monitoring",
    error_code_prefix="METRICS",
)
async def stop_system_monitoring():
    """Stop continuous system monitoring"""
    try:
        await system_monitor.stop_monitoring()

        return {"success": True, "message": "System monitoring stopped"}

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to stop monitoring")


@router.get("/dashboard", response_model=MetricsDashboardResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_metrics_dashboard",
    error_code_prefix="METRICS",
)
async def get_metrics_dashboard():
    """Get comprehensive metrics dashboard data"""
    try:
        # Get workflow performance summary
        workflow_summary = workflow_metrics.get_performance_summary(24)

        # Get system health check
        system_health = system_monitor.check_resource_thresholds()

        # Get system summary
        system_summary = system_monitor.get_resource_summary(30)

        # Get current metrics
        current_metrics = system_monitor.get_current_metrics()

        dashboard_data = {
            "timestamp": current_metrics.get("timestamp"),
            "workflow_performance": workflow_summary,
            "system_health": system_health,
            "resource_usage": system_summary,
            "current_status": {
                "cpu_percent": current_metrics.get("cpu_percent", 0),
                "memory_percent": current_metrics.get("memory_percent", 0),
                "disk_percent": current_metrics.get("disk_percent", 0),
                "monitoring_active": system_monitor.monitoring_active,
            },
            "active_workflows": len(workflow_metrics.active_workflows),
        }

        return {"success": True, "dashboard": dashboard_data}

    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get dashboard data")
