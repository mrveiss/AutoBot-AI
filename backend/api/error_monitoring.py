#!/usr/bin/env python3
"""
Error Monitoring API

Provides endpoints for monitoring system errors and error boundary statistics.
"""

import json
import logging
import os
import sys
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from src.config_helper import cfg
from src.constants.network_constants import NetworkConstants

# Add project root to path for imports
# Add project root to path for imports
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.utils.error_boundaries import get_error_boundary_manager, get_error_statistics

logger = logging.getLogger(__name__)

# Create FastAPI router
router = APIRouter(tags=["Error Monitoring"])


@router.get("/statistics")
async def get_system_error_statistics():
    """Get system-wide error statistics"""
    try:
        stats = get_error_statistics()
        return {"status": "success", "data": stats}
    except Exception as e:
        logger.error(f"Failed to get error statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/recent")
async def get_recent_errors(limit: int = 20):
    """Get recent error reports"""
    try:
        limit = min(limit, 100)  # Cap at 100

        manager = get_error_boundary_manager()

        # Get recent errors from Redis
        pattern = "autobot:errors:*"
        error_keys = manager.redis_client.keys(pattern)

        recent_errors = []
        for key in error_keys[-limit:]:  # Get latest errors
            error_data = manager.redis_client.get(key)
            if error_data:
                recent_errors.append(json.loads(error_data))

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
        logger.error(f"Failed to get recent errors: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/categories")
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
        logger.error(f"Failed to get error categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/components")
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
        logger.error(f"Failed to get component errors: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/health")
async def get_error_system_health():
    """Get error system health status"""
    try:
        stats = get_error_statistics()
        total_errors = stats.get("total_errors", 0)
        severities = stats.get("severities", {})

        # Determine health status based on error counts
        critical_errors = severities.get("critical", 0)
        high_errors = severities.get("high", 0)

        if critical_errors > 0:
            health_status = "critical"
            health_score = 0
        elif high_errors > 5:
            health_status = "degraded"
            health_score = 30
        elif total_errors > 20:
            health_status = "warning"
            health_score = 70
        elif total_errors > 0:
            health_status = "healthy"
            health_score = 90
        else:
            health_status = "excellent"
            health_score = 100

        return {
            "status": "success",
            "data": {
                "health_status": health_status,
                "health_score": health_score,
                "total_errors": total_errors,
                "critical_errors": critical_errors,
                "high_errors": high_errors,
                "recommendations": _get_health_recommendations(health_status, stats),
            },
        }
    except Exception as e:
        logger.error(f"Failed to get error system health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/clear")
async def clear_error_history(authorization: Optional[str] = Header(None)):
    """Clear error history (admin only)"""
    try:
        # This would typically require authentication
        if not authorization or authorization != "Bearer admin_token":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
            )

        manager = get_error_boundary_manager()

        # Clear Redis error keys
        pattern = "autobot:errors:*"
        error_keys = manager.redis_client.keys(pattern)

        if error_keys:
            manager.redis_client.delete(*error_keys)

        # Clear in-memory errors
        manager.error_reports.clear()

        return {
            "status": "success",
            "message": f"Cleared {len(error_keys)} error records",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear error history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


class TestErrorRequest(BaseModel):
    error_type: str = "ValueError"
    message: str = "Test error for error boundary system"


@router.post("/test-error")
async def test_error_system(request: TestErrorRequest):
    """Test the error boundary system (development only)"""
    try:
        # Only allow in development mode
        if cfg.get('environment.mode', 'development') != "development":
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
        logger.error(f"Test error triggered: {e}")
        return {
            "status": "success",
            "message": "Error boundary system triggered successfully",
            "error_caught": str(e),
            "error_type": type(e).__name__,
        }


def _get_health_recommendations(health_status: str, stats: Dict[str, Any]) -> list:
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
        recommendations.append(
            "High network errors - check network connectivity and " "external services"
        )

    if categories.get("database", 0) > 3:
        recommendations.append(
            "Database errors detected - verify database connections and " "integrity"
        )

    if categories.get("llm", 0) > 5:
        recommendations.append(
            "LLM service issues - check LLM provider status and configuration"
        )

    if severities.get("high", 0) > 10:
        recommendations.append(
            "Many high-severity errors - review system configuration and " "resources"
        )

    # Component-specific recommendations
    top_components = sorted(components.items(), key=lambda x: x[1], reverse=True)[:3]
    if top_components:
        most_problematic = top_components[0][0]
        recommendations.append(
            f"Focus on '{most_problematic}' component - highest error count"
        )

    if not recommendations:
        recommendations.append(
            "System error handling is working well - continue monitoring"
        )

    return recommendations
