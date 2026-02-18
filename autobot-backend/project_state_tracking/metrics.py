# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project State Tracking Metrics Module

Metric calculations and Redis interactions for state tracking.

Part of Issue #381 - God Class Refactoring
"""

import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional

from .models import StateSnapshot
from .types import REDIS_METRIC_KEYS, TrackingMetric

logger = logging.getLogger(__name__)


async def get_redis_metric(redis_client: Any, key: str, default: int = 0) -> int:
    """Helper to get metric from Redis with fallback"""
    try:
        if not redis_client:
            return default

        value = await redis_client.get(key)
        return int(value) if value else default

    except Exception as e:
        logger.debug("Redis metric fetch failed for %s: %s", key, e)
        return default


async def get_error_rate(redis_client: Any, fallback_count: int = 0) -> float:
    """Calculate current error rate based on recent error data"""
    try:
        if not redis_client:
            return 0.0

        # Get error count from current hour
        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)

        error_key = f"{REDIS_METRIC_KEYS['error_count']}:{current_hour.timestamp()}"
        error_count = await get_redis_metric(redis_client, error_key, 0)

        # Get total API calls from last hour for rate calculation
        api_key = f"{REDIS_METRIC_KEYS['api_calls']}:{current_hour.timestamp()}"
        api_calls = await get_redis_metric(
            redis_client, api_key, 1
        )  # Avoid division by zero

        # Calculate error rate as percentage
        error_rate = (error_count / api_calls) * 100 if api_calls > 0 else 0.0

        return round(error_rate, 2)

    except Exception as e:
        logger.warning("Error calculating error rate: %s", e)
        return 0.0


async def get_user_interactions_count(
    redis_client: Any, fallback_count: int = 0
) -> int:
    """Get current user interactions count from last 24 hours"""
    try:
        if not redis_client:
            return fallback_count

        total_interactions = 0
        now = datetime.now()

        for i in range(24):  # Last 24 hours
            hour = now - timedelta(hours=i)
            hour_key = hour.replace(minute=0, second=0, microsecond=0)
            key = f"{REDIS_METRIC_KEYS['user_interactions']}:{hour_key.timestamp()}"
            interactions = await get_redis_metric(redis_client, key, 0)
            total_interactions += interactions

        return total_interactions

    except Exception as e:
        logger.warning("Error getting user interactions count: %s", e)
        return fallback_count


async def get_api_calls_count(redis_client: Any, fallback_count: int = 0) -> int:
    """Get current API calls count from last 24 hours"""
    try:
        if not redis_client:
            return fallback_count

        total_calls = 0
        now = datetime.now()

        for i in range(24):  # Last 24 hours
            hour = now - timedelta(hours=i)
            hour_key = hour.replace(minute=0, second=0, microsecond=0)
            key = f"{REDIS_METRIC_KEYS['api_calls']}:{hour_key.timestamp()}"
            calls = await get_redis_metric(redis_client, key, 0)
            total_calls += calls

        return total_calls

    except Exception as e:
        logger.warning("Error getting API calls count: %s", e)
        return fallback_count


def calculate_progression_velocity(
    state_history: List[StateSnapshot],
) -> float:
    """Calculate rate of phase progression over last 7 days"""
    if len(state_history) < 2:
        return 0.0

    # Look at last 7 days of data
    seven_days_ago = datetime.now() - timedelta(days=7)
    recent_snapshots = [s for s in state_history if s.timestamp >= seven_days_ago]

    if len(recent_snapshots) < 2:
        return 0.0

    # Calculate change in phase completion
    first_completion = recent_snapshots[0].system_metrics.get(
        TrackingMetric.PHASE_COMPLETION, 0
    )
    last_completion = recent_snapshots[-1].system_metrics.get(
        TrackingMetric.PHASE_COMPLETION, 0
    )

    days_elapsed = (
        recent_snapshots[-1].timestamp - recent_snapshots[0].timestamp
    ).days or 1

    return (last_completion - first_completion) / days_elapsed


async def get_metrics_summary(
    redis_client: Any,
    error_count: int,
    api_call_count: int,
    user_interaction_count: int,
    error_boundary_manager: Optional[Any] = None,
) -> dict:
    """Get a comprehensive summary of tracked metrics"""
    try:
        return {
            "error_tracking": {
                "current_error_rate": await get_error_rate(redis_client),
                "total_errors_tracked": error_count,
                "last_update": datetime.now().isoformat(),
            },
            "api_tracking": {
                "total_api_calls_24h": await get_api_calls_count(
                    redis_client, api_call_count
                ),
                "current_session_calls": api_call_count,
                "last_update": datetime.now().isoformat(),
            },
            "user_interactions": {
                "total_interactions_24h": await get_user_interactions_count(
                    redis_client, user_interaction_count
                ),
                "current_session_interactions": user_interaction_count,
                "last_update": datetime.now().isoformat(),
            },
            "system_health": {
                "redis_connected": redis_client is not None,
                "error_boundary_available": error_boundary_manager is not None,
                "tracking_active": True,
            },
        }
    except Exception as e:
        logger.error("Error getting metrics summary: %s", e)
        return {"error": str(e)}
