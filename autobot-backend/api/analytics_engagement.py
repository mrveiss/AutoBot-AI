# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Engagement Metrics Analytics API

Provides endpoints for tracking user engagement metrics across features.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from api.schemas_analytics import EngagementMetricsResponse
from api.schemas_common import DataResponse
from autobot_shared.error_boundaries import with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client

logger = get_logger(__name__)

router = APIRouter(prefix="/engagement-metrics", tags=["engagement", "analytics"])


@router.get("", response_model=DataResponse[EngagementMetricsResponse])
@with_error_handling
async def get_engagement_metrics():
    """Get engagement metrics for all features."""
    redis = get_redis_client()

    try:
        # Retrieve engagement metrics from Redis
        # Format: engagement:feature:<feature_name> -> {count, last_accessed}
        pass

        if redis:
            # Scan for all engagement keys
            cursor = 0
            feature_counts = {}

            while True:
                cursor, keys = redis.scan(cursor, match="engagement:feature:*", count=100)

                for key in keys:
                    feature_name = key.decode().replace("engagement:feature:", "")
                    count = redis.get(f"engagement:feature:{feature_name}:count")
                    if count:
                        feature_counts[feature_name] = int(count)

                if cursor == 0:
                    break

        # Calculate feature popularity
        sorted_features = sorted(feature_counts.items(), key=lambda x: x[1], reverse=True)
        feature_popularity = [{"feature": f, "count": c} for f, c in sorted_features[:10]]
        most_popular = sorted_features[0][0] if sorted_features else None

        # Build response
        response = EngagementMetricsResponse(
            timestamp=datetime.now(timezone.utc).isoformat(),
            metrics={
                "total_features_tracked": len(feature_counts),
                "total_interactions": sum(feature_counts.values()),
                "average_interactions_per_feature": (
                    sum(feature_counts.values()) // len(feature_counts) if feature_counts else 0
                ),
            },
            feature_popularity=feature_popularity,
            most_popular_feature=most_popular,
        )

        return DataResponse(data=response)

    except Exception as e:
        logger.error(f"Error retrieving engagement metrics: {e}")
        # Return empty response on error
        return DataResponse(
            data=EngagementMetricsResponse(
                timestamp=datetime.now(timezone.utc).isoformat(),
                metrics={},
                feature_popularity=[],
                most_popular_feature=None,
            )
        )
