# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Feature Flags Admin API

Provides admin-only endpoints for managing feature flags and viewing
access control violation metrics during safe rollout.

Endpoints:
- GET /api/admin/feature-flags - List all feature flags
- PUT /api/admin/feature-flags/{name} - Update feature flag mode
- GET /api/admin/access-control/metrics - Get violation statistics
- GET /api/admin/access-control/endpoint/{endpoint} - Endpoint-specific stats
- GET /api/admin/access-control/user/{username} - User-specific stats
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List

from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.services.access_control_metrics import (
    AccessControlMetrics,
    get_metrics_service,
)
from backend.services.audit_logger import audit_log
from backend.services.feature_flags import (
    EnforcementMode,
    FeatureFlags,
    get_feature_flags,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin", "feature-flags"])


# Request/Response Models
class EnforcementModeUpdate(BaseModel):
    """Update enforcement mode request"""

    mode: EnforcementMode = Field(..., description="New enforcement mode")


class FeatureFlagInfo(BaseModel):
    """Feature flag information"""

    name: str
    current_mode: str
    description: str
    available_modes: List[str]


class ViolationStatistics(BaseModel):
    """Access control violation statistics"""

    total_violations: int
    period_days: int
    by_endpoint: Dict[str, int]
    by_user: Dict[str, int]
    by_day: Dict[str, int]
    current_mode: str


# Dependency for admin authentication
async def require_admin(
    current_user: Dict = Depends(get_current_user),
) -> Dict:
    """
    Require admin role for access to feature flags endpoints.

    Uses the authentication middleware to verify the user is authenticated
    and has admin privileges. Falls back to development mode if auth is disabled.

    Args:
        current_user: Authenticated user from auth middleware

    Returns:
        User information dict

    Raises:
        HTTPException: 403 if user lacks admin role
    """
    # Check if user has admin role
    user_role = current_user.get("role", "").lower()
    if user_role != "admin":
        logger.warning(
            f"Non-admin user '{current_user.get('username', 'unknown')}' "
            f"attempted to access feature flags (role: {user_role})"
        )
        raise HTTPException(
            status_code=403,
            detail="Admin access required for feature flag management",
        )

    return current_user


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_feature_flags_status",
    error_code_prefix="FEATURE_FLAGS",
)
@router.get("/feature-flags/status")
async def get_feature_flags_status(
    admin: Dict = Depends(require_admin),
    flags: FeatureFlags = Depends(get_feature_flags),
):
    """
    Get current feature flags status and rollout statistics

    Returns:
        Feature flag status and change history
    """
    try:
        stats = await flags.get_rollout_statistics()
        return {"success": True, "data": stats}

    except Exception as e:
        logger.error("Failed to get feature flags status: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_enforcement_mode",
    error_code_prefix="FEATURE_FLAGS",
)
@router.put("/feature-flags/enforcement-mode")
async def update_enforcement_mode(
    update: EnforcementModeUpdate,
    admin: Dict = Depends(require_admin),
    flags: FeatureFlags = Depends(get_feature_flags),
):
    """
    Update global access control enforcement mode

    Modes:
    - DISABLED: No enforcement, no validation
    - LOG_ONLY: Validate and audit violations, but don't block
    - ENFORCED: Full enforcement, block unauthorized access

    Args:
        update: New enforcement mode

    Returns:
        Success confirmation with new mode
    """
    try:
        # Set new mode
        success = await flags.set_enforcement_mode(update.mode)

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to update enforcement mode"
            )

        # Audit log the change
        await audit_log(
            operation="config.update",
            result="success",
            user_id=admin.get("username", "admin"),
            resource="feature_flag:access_control:enforcement_mode",
            details={
                "previous_mode": "unknown",  # Could fetch from history
                "new_mode": update.mode.value,
                "action": "enforcement_mode_update",
            },
        )

        logger.info(
            f"Enforcement mode updated to {update.mode.value} by {admin.get('username')}"
        )

        return {
            "success": True,
            "message": f"Enforcement mode updated to {update.mode.value}",
            "data": {
                "new_mode": update.mode.value,
                "updated_by": admin.get("username"),
                "updated_at": datetime.now().isoformat(),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update enforcement mode: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to update mode: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="set_endpoint_enforcement",
    error_code_prefix="FEATURE_FLAGS",
)
@router.put("/feature-flags/endpoint/{endpoint:path}")
async def set_endpoint_enforcement(
    endpoint: str,
    update: EnforcementModeUpdate,
    admin: Dict = Depends(require_admin),
    flags: FeatureFlags = Depends(get_feature_flags),
):
    """
    Set enforcement mode for a specific endpoint

    Allows gradual rollout by enabling enforcement per-endpoint

    Args:
        endpoint: API endpoint path (e.g., /api/chat/sessions/{session_id})
        update: Enforcement mode for this endpoint

    Returns:
        Success confirmation
    """
    try:
        success = await flags.set_endpoint_enforcement(endpoint, update.mode)

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to set endpoint enforcement"
            )

        # Audit log
        await audit_log(
            operation="config.update",
            result="success",
            user_id=admin.get("username", "admin"),
            resource=f"feature_flag:endpoint:{endpoint}",
            details={"endpoint": endpoint, "new_mode": update.mode.value},
        )

        return {
            "success": True,
            "message": f"Endpoint {endpoint} enforcement set to {update.mode.value}",
            "data": {"endpoint": endpoint, "mode": update.mode.value},
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to set endpoint enforcement: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="remove_endpoint_enforcement",
    error_code_prefix="FEATURE_FLAGS",
)
@router.delete("/feature-flags/endpoint/{endpoint:path}")
async def remove_endpoint_enforcement(
    endpoint: str,
    admin: Dict = Depends(require_admin),
    flags: FeatureFlags = Depends(get_feature_flags),
):
    """
    Remove endpoint-specific enforcement override

    Endpoint will revert to using global enforcement mode

    Args:
        endpoint: API endpoint path

    Returns:
        Success confirmation
    """
    try:
        success = await flags.set_endpoint_enforcement(endpoint, None)

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to remove endpoint override"
            )

        return {
            "success": True,
            "message": f"Endpoint override removed for {endpoint}",
            "data": {"endpoint": endpoint, "reverted_to": "global_mode"},
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to remove endpoint enforcement: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_access_control_metrics",
    error_code_prefix="FEATURE_FLAGS",
)
@router.get("/access-control/metrics")
async def get_access_control_metrics(
    days: int = Query(7, ge=1, le=30, description="Number of days to include"),
    include_details: bool = Query(
        False, description="Include recent violation details"
    ),
    admin: Dict = Depends(require_admin),
    metrics: AccessControlMetrics = Depends(get_metrics_service),
    flags: FeatureFlags = Depends(get_feature_flags),
):
    """
    Get access control violation statistics

    Used during LOG_ONLY mode to analyze violations before full enforcement

    Args:
        days: Number of days to include in statistics (1-30)
        include_details: Include list of recent violations

    Returns:
        Violation statistics including:
        - Total violations
        - Breakdown by endpoint
        - Breakdown by user
        - Daily trends
        - Current enforcement mode
    """
    try:
        # Issue #379: Parallelize independent async calls
        stats, current_mode = await asyncio.gather(
            metrics.get_statistics(days=days, include_details=include_details),
            flags.get_enforcement_mode(),
        )

        return {"success": True, "data": {**stats, "current_mode": current_mode.value}}

    except Exception as e:
        logger.error("Failed to get access control metrics: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_endpoint_metrics",
    error_code_prefix="FEATURE_FLAGS",
)
@router.get("/access-control/endpoint/{endpoint:path}")
async def get_endpoint_metrics(
    endpoint: str,
    days: int = Query(7, ge=1, le=30),
    admin: Dict = Depends(require_admin),
    metrics: AccessControlMetrics = Depends(get_metrics_service),
):
    """
    Get violation statistics for a specific endpoint

    Args:
        endpoint: API endpoint path
        days: Number of days to analyze

    Returns:
        Endpoint-specific violation statistics
    """
    try:
        stats = await metrics.get_endpoint_statistics(endpoint, days=days)

        return {"success": True, "data": stats}

    except Exception as e:
        logger.error("Failed to get endpoint metrics: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_user_metrics",
    error_code_prefix="FEATURE_FLAGS",
)
@router.get("/access-control/user/{username}")
async def get_user_metrics(
    username: str,
    days: int = Query(7, ge=1, le=30),
    admin: Dict = Depends(require_admin),
    metrics: AccessControlMetrics = Depends(get_metrics_service),
):
    """
    Get violation statistics for a specific user

    Args:
        username: Username to analyze
        days: Number of days to analyze

    Returns:
        User-specific violation statistics
    """
    try:
        stats = await metrics.get_user_statistics(username, days=days)

        return {"success": True, "data": stats}

    except Exception as e:
        logger.error("Failed to get user metrics: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_old_metrics",
    error_code_prefix="FEATURE_FLAGS",
)
@router.post("/access-control/cleanup")
async def cleanup_old_metrics(
    admin: Dict = Depends(require_admin),
    metrics: AccessControlMetrics = Depends(get_metrics_service),
):
    """
    Manually trigger cleanup of old metrics

    Note: Metrics auto-expire via Redis TTL, but this can force immediate cleanup

    Returns:
        Success confirmation
    """
    try:
        await metrics.cleanup_old_metrics()

        return {"success": True, "message": "Old metrics cleanup completed"}

    except Exception as e:
        logger.error("Failed to cleanup metrics: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
