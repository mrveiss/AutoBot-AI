# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Metrics API endpoints for workflow performance monitoring
"""

from backend.metrics.system_monitor import system_monitor
from backend.metrics.workflow_metrics import workflow_metrics
from fastapi import APIRouter, HTTPException, Query

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_workflow_metrics",
    error_code_prefix="METRICS",
)
@router.get("/workflow/{workflow_id}")
async def get_workflow_metrics(workflow_id: str):
    """Get metrics for a specific workflow"""
    try:
        stats = workflow_metrics.get_workflow_stats(workflow_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Workflow metrics not found")

        return {"success": True, "workflow_id": workflow_id, "metrics": stats}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get workflow metrics: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_summary",
    error_code_prefix="METRICS",
)
@router.get("/performance/summary")
async def get_performance_summary(
    time_window_hours: int = Query(
        default=24, ge=1, le=168, description="Time window in hours (1-168)"
    )
):
    """Get overall performance summary"""
    try:
        summary = workflow_metrics.get_performance_summary(time_window_hours)

        return {"success": True, "performance_summary": summary}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get performance summary: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_system_metrics",
    error_code_prefix="METRICS",
)
@router.get("/system/current")
async def get_current_system_metrics():
    """Get current system resource metrics"""
    try:
        metrics = system_monitor.get_current_metrics()

        return {"success": True, "system_metrics": metrics}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get system metrics: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_summary",
    error_code_prefix="METRICS",
)
@router.get("/system/summary")
async def get_system_summary(
    minutes: int = Query(
        default=10, ge=1, le=60, description="Time window in minutes (1-60)"
    )
):
    """Get system resource usage summary"""
    try:
        summary = system_monitor.get_resource_summary(minutes)

        return {"success": True, "resource_summary": summary}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get resource summary: {str(e)}"
        )


# Health check moved to consolidated health service
# See backend/services/consolidated_health_service.py
# Use /api/system/health?detailed=true for comprehensive status


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_workflow_metrics",
    error_code_prefix="METRICS",
)
@router.get("/export/workflow")
async def export_workflow_metrics(
    format: str = Query(default="json", description="Export format")
):
    """Export workflow metrics data"""
    try:
        export_data = workflow_metrics.export_metrics(format)

        return {"success": True, "format": format, "data": export_data}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to export metrics: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_system_metrics",
    error_code_prefix="METRICS",
)
@router.get("/export/system")
async def export_system_metrics(
    format: str = Query(default="json", description="Export format")
):
    """Export system resource monitoring data"""
    try:
        export_data = system_monitor.export_resource_data(format)

        return {"success": True, "format": format, "data": export_data}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to export system data: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_system_monitoring",
    error_code_prefix="METRICS",
)
@router.post("/system/monitoring/start")
async def start_system_monitoring():
    """Start continuous system monitoring"""
    try:
        await system_monitor.start_monitoring()

        return {
            "success": True,
            "message": "System monitoring started",
            "collection_interval": system_monitor.collection_interval,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start monitoring: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_system_monitoring",
    error_code_prefix="METRICS",
)
@router.post("/system/monitoring/stop")
async def stop_system_monitoring():
    """Stop continuous system monitoring"""
    try:
        await system_monitor.stop_monitoring()

        return {"success": True, "message": "System monitoring stopped"}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop monitoring: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_metrics_dashboard",
    error_code_prefix="METRICS",
)
@router.get("/dashboard")
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

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get dashboard data: {str(e)}"
        )
