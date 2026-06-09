#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Error Monitoring API

Provides endpoints for monitoring system errors and error boundary statistics.
"""

import asyncio
import json
import os
import sys

from fastapi import APIRouter, Header, HTTPException, Request, status

from api.schemas_analytics import (
    AlertThresholdRequest,
    ErrorMonitoringAlertThresholdResponse,
    ErrorMonitoringCleanupResponse,
    ErrorMonitoringClearResponse,
    ErrorMonitoringDataResponse,
    ErrorMonitoringResolveResponse,
    ErrorMonitoringTestErrorResponse,
    TestErrorRequest,
)
from api.system_health import ComponentHealth, register_health_probe
from autobot_shared.error_boundaries import (
    ErrorCategory,
    get_error_boundary_manager,
    get_error_statistics,
    with_error_handling,
)
from autobot_shared.logging_manager import get_logger
from config.manager import get_config_manager
from type_defs.common import Metadata
from utils.error_metrics import get_metrics_collector

config = get_config_manager()

# Add project root to path for imports
# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = get_logger(__name__)

# Create FastAPI router
router = APIRouter(tags=["Error Monitoring"])


@router.get("/statistics", response_model=ErrorMonitoringDataResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_error_statistics",
    error_code_prefix="ERROR_MONITORING",
)
async def get_system_error_statistics():
    """Get system-wide error statistics"""
    try:
        stats = get_error_statistics()
        return {"status": "success", "data": stats}
    except Exception as e:
        logger.error("Failed to get error statistics: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/recent", response_model=ErrorMonitoringDataResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_recent_errors",
    error_code_prefix="ERROR_MONITORING",
)
async def get_recent_errors(limit: int = 20):
    """Get recent error reports"""
    try:
        limit = min(limit, 100)  # Cap at 100

        manager = get_error_boundary_manager()

        # Issue #361 - avoid blocking - fetch errors in thread pool
        # Issue #480 - fix N+1 query pattern using pipeline batching
        def _fetch_recent_errors():
            pattern = "autobot:errors:*"
            error_keys = manager.redis_client.keys(pattern)

            if not error_keys:
                return []

            # Use pipeline to batch all GET operations (Issue #480)
            keys_to_fetch = error_keys[-limit:]
            pipe = manager.redis_client.pipeline()
            for key in keys_to_fetch:
                pipe.get(key)
            results = pipe.execute()

            recent_errors = []
            for error_data in results:
                if error_data:
                    recent_errors.append(json.loads(error_data))
            return recent_errors

        recent_errors = await asyncio.to_thread(_fetch_recent_errors)

        # Sort by timestamp (most recent first)
        recent_errors.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

        return {
            "status": "success",
            "data": {
                "errors": recent_errors[:limit],
                "total_count": len(recent_errors),
            },
        }
    except Exception as e:
        logger.error("Failed to get recent errors: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/categories", response_model=ErrorMonitoringDataResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_error_categories",
    error_code_prefix="ERROR_MONITORING",
)
async def get_error_categories():
    """Get error breakdown by category"""
    try:
        stats = get_error_statistics()
        categories = stats.get("categories", {})

        # Calculate percentages
        total = sum(categories.values())
        category_stats = {}

        for category, count in categories.items():
            percentage = (count / total * 100) if total > 0 else 0
            category_stats[category] = {
                "count": count,
                "percentage": round(percentage, 2),
            }

        return {
            "status": "success",
            "data": {"categories": category_stats, "total_errors": total},
        }
    except Exception as e:
        logger.error("Failed to get error categories: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/components", response_model=ErrorMonitoringDataResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_error_by_component",
    error_code_prefix="ERROR_MONITORING",
)
async def get_error_by_component():
    """Get error breakdown by component"""
    try:
        stats = get_error_statistics()
        components = stats.get("components", {})

        # Sort by error count
        sorted_components = sorted(components.items(), key=lambda x: x[1], reverse=True)

        return {
            "status": "success",
            "data": {
                "components": dict(sorted_components),
                "most_problematic": sorted_components[:5] if sorted_components else [],
            },
        }
    except Exception as e:
        logger.error("Failed to get component errors: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


def _calculate_health_status(critical_errors: int, high_errors: int, total_errors: int) -> tuple:
    """Calculate health status and score from error counts. (Issue #315 - extracted)"""
    # Check thresholds in priority order (Issue #315 - replaces chained if/elif)
    thresholds = [
        (critical_errors > 0, "critical", 0),
        (high_errors > 5, "degraded", 30),
        (total_errors > 20, "warning", 70),
        (total_errors > 0, "healthy", 90),
    ]
    for condition, status_val, score in thresholds:
        if condition:
            return status_val, score
    return "excellent", 100


@register_health_probe("error_monitoring")
async def probe_error_monitoring(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for error-monitoring service."""
    try:
        stats = get_error_statistics()
        total_errors = stats.get("total_errors", 0)
        severities = stats.get("severities", {}) or {}
        critical = severities.get("critical", 0)
        high = severities.get("high", 0)
        health_status, _ = _calculate_health_status(critical, high, total_errors)
        if health_status in ("excellent", "healthy"):
            return ComponentHealth(name="error_monitoring", status="ok")
        if health_status in ("warning", "degraded"):
            return ComponentHealth(
                name="error_monitoring",
                status="degraded",
                detail=health_status,
            )
        return ComponentHealth(
            name="error_monitoring",
            status="down",
            detail=health_status,
        )
    except Exception as exc:
        return ComponentHealth(
            name="error_monitoring",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


@router.post("/clear", response_model=ErrorMonitoringClearResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_error_history",
    error_code_prefix="ERROR_MONITORING",
)
async def clear_error_history(authorization: str | None = Header(None)):
    """Clear error history (admin only)"""
    try:
        # This would typically require authentication
        if not authorization or authorization != "Bearer admin_token":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

        manager = get_error_boundary_manager()

        # Issue #361 - avoid blocking - clear Redis errors in thread pool
        def _clear_redis_errors():
            pattern = "autobot:errors:*"
            error_keys = manager.redis_client.keys(pattern)
            if error_keys:
                manager.redis_client.delete(*error_keys)
            return len(error_keys) if error_keys else 0

        cleared_count = await asyncio.to_thread(_clear_redis_errors)

        # Clear in-memory errors
        manager.error_reports.clear()

        return {
            "status": "success",
            "message": f"Cleared {cleared_count} error records",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to clear error history: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/test-error", response_model=ErrorMonitoringTestErrorResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_error_system",
    error_code_prefix="ERROR_MONITORING",
)
async def test_error_system(request: TestErrorRequest):
    """Test the error boundary system (development only)"""
    try:
        # Only allow in development mode
        if config.get("environment.mode", "development") != "development":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Test endpoints only available in development mode",
            )

        # Create test error
        if request.error_type == "ValueError":
            raise ValueError(request.message)
        elif request.error_type == "ConnectionError":
            raise ConnectionError(request.message)
        elif request.error_type == "TimeoutError":
            raise TimeoutError(request.message)
        else:
            raise Exception(request.message)

    except HTTPException:
        raise
    except Exception as e:
        # This should trigger the error boundary system
        logger.error("Test error triggered: %s", e)
        return {
            "status": "success",
            "message": "Error boundary system triggered successfully",
            "error_caught": "Internal server error",
            "error_type": type(e).__name__,
        }


def _get_health_recommendations(health_status: str, stats: Metadata) -> list:
    """Generate health recommendations based on error patterns"""
    recommendations = []

    categories = stats.get("categories", {})
    components = stats.get("components", {})
    severities = stats.get("severities", {})

    if health_status == "critical":
        recommendations.extend(
            [
                "Immediate attention required - critical errors detected",
                "Check system logs and contact system administrator",
                "Consider system restart or service restoration",
            ]
        )

    if categories.get("network", 0) > 5:
        recommendations.append("High network errors - check network connectivity and " "external services")

    if categories.get("database", 0) > 3:
        recommendations.append("Database errors detected - verify database connections and " "integrity")

    if categories.get("llm", 0) > 5:
        recommendations.append("LLM service issues - check LLM provider status and configuration")

    if severities.get("high", 0) > 10:
        recommendations.append("Many high-severity errors - review system configuration and " "resources")

    # Component-specific recommendations
    top_components = sorted(components.items(), key=lambda x: x[1], reverse=True)[:3]
    if top_components:
        most_problematic = top_components[0][0]
        recommendations.append(f"Focus on '{most_problematic}' component - highest error count")

    if not recommendations:
        recommendations.append("System error handling is working well - continue monitoring")

    return recommendations


# =============================================================================
# NEW: Error Metrics Endpoints (Phase 5)
# =============================================================================


@router.get("/metrics/summary", response_model=ErrorMonitoringDataResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_metrics_summary",
    error_code_prefix="ERROR_MONITORING",
)
async def get_metrics_summary():
    """
    Get comprehensive error metrics summary

    Returns aggregated metrics including error rates, retry counts,
    and breakdowns by category and component.
    """
    try:
        collector = get_metrics_collector()
        summary = collector.get_summary()

        return {"status": "success", "data": summary}
    except Exception as e:
        logger.error("Failed to get metrics summary: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/metrics/timeline", response_model=ErrorMonitoringDataResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_error_timeline_endpoint",
    error_code_prefix="ERROR_MONITORING",
)
async def get_error_timeline_endpoint(hours: int = 24, component: str | None = None):
    """
    Get error timeline data for visualization

    Args:
        hours: Number of hours to include (1-168)
        component: Optional component filter
    """
    try:
        hours = min(max(hours, 1), 168)  # Clamp to 1-168 hours

        collector = get_metrics_collector()
        timeline = collector.get_error_timeline(hours=hours, component=component)

        return {
            "status": "success",
            "data": {
                "timeline": [
                    {"hour": hour, "error_count": len(errors), "errors": errors} for hour, errors in timeline.items()
                ],
                "hours": hours,
                "component": component,
            },
        }
    except Exception as e:
        logger.error("Failed to get error timeline: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/metrics/top-errors", response_model=ErrorMonitoringDataResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_top_errors_endpoint",
    error_code_prefix="ERROR_MONITORING",
)
async def get_top_errors_endpoint(limit: int = 10):
    """
    Get top N most frequent errors

    Args:
        limit: Number of top errors to return (1-50)
    """
    try:
        limit = min(max(limit, 1), 50)  # Clamp to 1-50

        collector = get_metrics_collector()
        top_errors = collector.get_top_errors(limit=limit)

        return {
            "status": "success",
            "data": {"top_errors": [stats.to_dict() for stats in top_errors]},
        }
    except Exception as e:
        logger.error("Failed to get top errors: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/metrics/resolve/{trace_id}", response_model=ErrorMonitoringResolveResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mark_error_resolved_endpoint",
    error_code_prefix="ERROR_MONITORING",
)
async def mark_error_resolved_endpoint(trace_id: str):
    """
    Mark an error as resolved

    Args:
        trace_id: Trace ID of the error to mark as resolved
    """
    try:
        collector = get_metrics_collector()
        success = await collector.mark_resolved(trace_id)

        if success:
            return {
                "status": "success",
                "message": f"Error {trace_id} marked as resolved",
            }
        else:
            return {
                "status": "not_found",
                "message": f"Error {trace_id} not found",
            }
    except Exception as e:
        logger.error("Failed to mark error resolved: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/metrics/alert-threshold", response_model=ErrorMonitoringAlertThresholdResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="set_alert_threshold_endpoint",
    error_code_prefix="ERROR_MONITORING",
)
async def set_alert_threshold_endpoint(request: AlertThresholdRequest):
    """
    Set alert threshold for a component/error

    Args:
        component: Component name
        error_code: Optional error code (None = any error in component)
        threshold: Error count threshold for alerts
    """
    try:
        collector = get_metrics_collector()
        collector.set_alert_threshold(request.component, request.error_code, request.threshold)

        threshold_key = f"{request.component}:{request.error_code or 'any'}"

        return {
            "status": "success",
            "message": f"Set alert threshold: {threshold_key} = {request.threshold}",
            "threshold_key": threshold_key,
            "threshold": request.threshold,
        }
    except Exception as e:
        logger.error("Failed to set alert threshold: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/metrics/cleanup", response_model=ErrorMonitoringCleanupResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_metrics_endpoint",
    error_code_prefix="ERROR_MONITORING",
)
async def cleanup_metrics_endpoint():
    """
    Clean up old metrics beyond retention period

    Removes metrics older than the configured retention period.
    """
    try:
        collector = get_metrics_collector()
        removed = await collector.cleanup_old_metrics()

        return {
            "status": "success",
            "message": f"Cleaned up {removed} old metrics",
            "removed_count": removed,
        }
    except Exception as e:
        logger.error("Failed to cleanup metrics: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
