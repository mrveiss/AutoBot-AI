# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Behavior Analytics API Module - Endpoints for tracking and analyzing user behavior.

Provides API endpoints for:
- Event tracking
- Feature usage metrics
- User journey analysis
- Engagement metrics
- Usage heatmaps
- Daily statistics

Related Issues: #59 (Advanced Analytics & Business Intelligence)
"""

import asyncio

from fastapi import APIRouter, Depends, Query

from api.schemas_analytics import (
    BehaviorDailyStatsResponse,
    BehaviorEngagementResponse,
    BehaviorFeatureComparisonResponse,
    BehaviorFeatureMetricsResponse,
    BehaviorHeatmapResponse,
    BehaviorPeakUsageResponse,
    BehaviorRecentEventsResponse,
    BehaviorSummaryResponse,
    BehaviorTrackEventResponse,
    TrackEventRequest,
    UserJourneyResponse,
)
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, utc_timestamp
from services.user_behavior_analytics import UserEvent, get_behavior_analytics

logger = get_logger(__name__)
router = APIRouter(prefix="/behavior", tags=["analytics", "behavior"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


# ============================================================================
# EVENT TRACKING ENDPOINTS
# ============================================================================


@router.post("/track", response_model=BehaviorTrackEventResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="track_user_event",
    error_code_prefix="ANALYTICS_BEHAVIOR",
)
async def track_user_event(
    request: TrackEventRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Track a user behavior event.

    Records user interactions for analytics purposes.

    Issue #744: Requires authenticated user.
    """
    analytics = get_behavior_analytics()

    event = UserEvent(
        event_type=request.event_type,
        feature=request.feature,
        user_id=request.user_id,
        session_id=request.session_id,
        timestamp=now_utc(),
        duration_ms=request.duration_ms,
        metadata=request.metadata or {},
    )

    success = await analytics.track_event(event)

    return {
        "status": "tracked" if success else "failed",
        "event_type": request.event_type,
        "feature": request.feature,
        "timestamp": event.timestamp.isoformat(),
    }


@router.get("/events/recent", response_model=BehaviorRecentEventsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_recent_events",
    error_code_prefix="ANALYTICS_BEHAVIOR",
)
async def get_recent_events(
    limit: int = Query(default=100, ge=1, le=1000, description="Number of events to return"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get recent user events.

    Returns the most recent tracked events.

    Issue #744: Requires admin authentication.
    """
    analytics = get_behavior_analytics()
    events = await analytics.get_recent_events(limit)

    return {
        "count": len(events),
        "events": events,
    }


# ============================================================================
# FEATURE METRICS ENDPOINTS
# ============================================================================


@router.get("/features", response_model=BehaviorFeatureMetricsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_feature_metrics",
    error_code_prefix="ANALYTICS_BEHAVIOR",
)
async def get_feature_metrics(
    feature: str | None = Query(None, description="Specific feature to get metrics for"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get feature usage metrics.

    Returns aggregated metrics for all features or a specific feature.

    Issue #744: Requires admin authentication.
    """
    analytics = get_behavior_analytics()
    metrics = await analytics.get_feature_metrics(feature)

    return metrics


@router.get("/features/comparison", response_model=BehaviorFeatureComparisonResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_feature_comparison",
    error_code_prefix="ANALYTICS_BEHAVIOR",
)
async def get_feature_comparison(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Compare usage across all features.

    Returns a side-by-side comparison of feature metrics.

    Issue #744: Requires admin authentication.
    """
    analytics = get_behavior_analytics()
    metrics = await analytics.get_feature_metrics()

    if "error" in metrics:
        return metrics

    features = metrics.get("features", {})

    # Create comparison data
    comparison = []
    for name, data in features.items():
        comparison.append(
            {
                "feature": name,
                "views": data.get("total_views", 0),
                "users": data.get("unique_users", 0),
                "sessions": data.get("unique_sessions", 0),
                "avg_time_ms": data.get("avg_time_spent_ms", 0),
            }
        )

    # Sort by views
    comparison.sort(key=lambda x: x["views"], reverse=True)

    return {
        "timestamp": utc_timestamp(),
        "comparison": comparison,
        "total_features": len(comparison),
    }


# ============================================================================
# USER JOURNEY ENDPOINTS
# ============================================================================


@router.get("/journey/{session_id}", response_model=UserJourneyResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_user_journey",
    error_code_prefix="ANALYTICS_BEHAVIOR",
)
async def get_user_journey(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get the user journey for a specific session.

    Returns the sequence of features and events for a session.

    Issue #744: Requires admin authentication.
    """
    analytics = get_behavior_analytics()
    journey = await analytics.get_user_journey(session_id)

    return UserJourneyResponse(
        session_id=journey.get("session_id", session_id),
        steps=journey.get("steps", []),
        total_steps=journey.get("total_steps", 0),
        features_visited=journey.get("features_visited", []),
    )


# ============================================================================
# ENGAGEMENT METRICS ENDPOINTS
# ============================================================================


@router.get("/engagement", response_model=BehaviorEngagementResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_engagement_metrics",
    error_code_prefix="ANALYTICS_BEHAVIOR",
)
async def get_engagement_metrics(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get user engagement metrics.

    Returns overall engagement statistics including session duration,
    pages per session, and feature popularity.

    Issue #744: Requires admin authentication.
    """
    analytics = get_behavior_analytics()
    metrics = await analytics.get_engagement_metrics()

    return metrics


# ============================================================================
# USAGE STATISTICS ENDPOINTS
# ============================================================================


@router.get("/stats/daily", response_model=BehaviorDailyStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_daily_stats",
    error_code_prefix="ANALYTICS_BEHAVIOR",
)
async def get_daily_stats(
    days: int = Query(default=30, ge=1, le=90, description="Number of days to retrieve"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get daily usage statistics.

    Returns daily breakdown of feature usage.

    Issue #744: Requires admin authentication.
    """
    analytics = get_behavior_analytics()
    stats = await analytics.get_daily_stats(days)

    return stats


@router.get("/stats/heatmap", response_model=BehaviorHeatmapResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_usage_heatmap",
    error_code_prefix="ANALYTICS_BEHAVIOR",
)
async def get_usage_heatmap(
    days: int = Query(default=7, ge=1, le=30, description="Number of days to include"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get hourly usage heatmap.

    Returns usage patterns by hour of day across features.

    Issue #744: Requires admin authentication.
    """
    analytics = get_behavior_analytics()
    heatmap = await analytics.get_usage_heatmap(days)

    return heatmap


@router.get("/stats/peak", response_model=BehaviorPeakUsageResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_peak_usage",
    error_code_prefix="ANALYTICS_BEHAVIOR",
)
async def get_peak_usage(
    days: int = Query(default=7, ge=1, le=30, description="Number of days to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get peak usage times.

    Returns information about when the platform is most actively used.

    Issue #744: Requires admin authentication.
    """
    analytics = get_behavior_analytics()
    heatmap_data = await analytics.get_usage_heatmap(days)

    if "error" in heatmap_data:
        return heatmap_data

    peak_hours = heatmap_data.get("peak_hours", [])

    # Determine peak time description
    if peak_hours:
        top_hour = int(peak_hours[0]["hour"])
        if 6 <= top_hour < 12:
            period = "morning"
        elif 12 <= top_hour < 17:
            period = "afternoon"
        elif 17 <= top_hour < 21:
            period = "evening"
        else:
            period = "night"
    else:
        period = "unknown"

    return {
        "period_days": days,
        "peak_hours": peak_hours,
        "peak_period": period,
        "recommendation": (
            f"Consider scheduling intensive tasks outside peak hours "
            f"({peak_hours[0]['hour'] if peak_hours else 'N/A'}:00)"
        ),
    }


# ============================================================================
# SUMMARY ENDPOINTS
# ============================================================================


@router.get("/summary", response_model=BehaviorSummaryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_behavior_summary",
    error_code_prefix="ANALYTICS_BEHAVIOR",
)
async def get_behavior_summary(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get comprehensive behavior analytics summary.

    Returns a high-level overview of user behavior patterns.

    Issue #744: Requires admin authentication.
    """
    analytics = get_behavior_analytics()

    # Issue #619: Parallelize independent metrics fetches
    engagement, daily_stats, heatmap = await asyncio.gather(
        analytics.get_engagement_metrics(),
        analytics.get_daily_stats(7),
        analytics.get_usage_heatmap(7),
    )

    return {
        "timestamp": utc_timestamp(),
        "engagement": engagement.get("metrics", {}),
        "feature_popularity": engagement.get("feature_popularity", []),
        "most_popular_feature": engagement.get("most_popular_feature"),
        "weekly_stats": {
            "total_views": daily_stats.get("total_views", 0),
            "avg_daily_views": daily_stats.get("avg_daily_views", 0),
        },
        "peak_hours": heatmap.get("peak_hours", []),
    }
