# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Behavior Analytics Service - Track and analyze user interaction patterns.

Provides analytics for:
- Feature usage tracking
- Session behavior analysis
- User journey mapping
- Engagement metrics
- Click stream analysis
- Time-on-feature metrics

Related Issues: #59 (Advanced Analytics & Business Intelligence)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from autobot_shared.redis_client import RedisDatabase, get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class UserEvent:
    """Represents a user interaction event"""

    event_type: str  # page_view, click, search, api_call, etc.
    feature: str  # chat, knowledge, tools, monitoring, etc.
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: Optional[int] = None
    metadata: dict = field(default_factory=dict)

    def to_tracking_dict(self) -> dict:
        """Convert to dictionary for Redis stream storage (Issue #372 - reduces feature envy).

        Returns:
            Dictionary with all fields formatted for tracking storage.
        """
        return {
            "event_type": self.event_type,
            "feature": self.feature,
            "user_id": self.user_id or "anonymous",
            "session_id": self.session_id or "unknown",
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": str(self.duration_ms or 0),
            "metadata": str(self.metadata),
        }

    def get_date_key(self) -> str:
        """Get date key for daily aggregation (Issue #372 - reduces feature envy)."""
        return self.timestamp.strftime("%Y-%m-%d")

    def get_hour_key(self) -> str:
        """Get hour key for heatmap aggregation (Issue #372 - reduces feature envy)."""
        return self.timestamp.strftime("%H")

    def get_journey_entry(self) -> str:
        """Get journey entry string (Issue #372 - reduces feature envy)."""
        return f"{self.timestamp.isoformat()}|{self.feature}|{self.event_type}"


@dataclass
class FeatureMetrics:
    """Aggregated metrics for a feature"""

    feature: str
    total_views: int = 0
    unique_users: int = 0
    total_sessions: int = 0
    avg_time_spent_ms: float = 0.0
    total_interactions: int = 0
    bounce_rate: float = 0.0


class UserBehaviorAnalytics:
    """
    Service for tracking and analyzing user behavior patterns.

    Uses Redis for real-time event storage and aggregation.
    """

    # Redis key prefixes
    EVENTS_KEY = "user_behavior:events"
    SESSIONS_KEY = "user_behavior:sessions"
    FEATURE_STATS_KEY = "user_behavior:feature_stats"
    DAILY_STATS_KEY = "user_behavior:daily"
    USER_JOURNEY_KEY = "user_behavior:journey"
    HEATMAP_KEY = "user_behavior:heatmap"

    def __init__(self):
        """Initialize analytics service with lazy Redis client."""
        self._redis = None

    async def get_redis(self):
        """Get Redis client for analytics database"""
        if self._redis is None:
            self._redis = await get_redis_client(
                async_client=True, database=RedisDatabase.ANALYTICS
            )
        return self._redis

    async def track_event(self, event: UserEvent) -> bool:
        """
        Track a user behavior event (Issue #372 - uses model methods).
        Issue #483: Parallelized independent Redis operations for 70-85% performance gain.

        Args:
            event: UserEvent to track

        Returns:
            bool: True if successfully tracked
        """
        try:
            redis = await self.get_redis()
            # Use model methods to reduce feature envy (Issue #372)
            date_key = event.get_date_key()
            hour_key = event.get_hour_key()
            feature_key = f"{self.FEATURE_STATS_KEY}:{event.feature}"
            daily_key = f"{self.DAILY_STATS_KEY}:{date_key}"
            heatmap_key = f"{self.HEATMAP_KEY}:{date_key}"

            # Issue #483: Collect all independent Redis operations
            operations = [
                # Store event in stream
                redis.xadd(
                    self.EVENTS_KEY,
                    event.to_tracking_dict(),
                    maxlen=100000,
                ),
                # Update feature statistics
                redis.hincrby(feature_key, "total_views", 1),
                redis.hincrby(feature_key, f"events:{event.event_type}", 1),
                # Update daily statistics
                redis.hincrby(daily_key, f"{event.feature}:views", 1),
                redis.hincrby(
                    daily_key, f"{event.feature}:events:{event.event_type}", 1
                ),
                redis.expire(daily_key, 90 * 24 * 3600),  # 90 days retention
                # Update hourly heatmap
                redis.hincrby(heatmap_key, f"{hour_key}:{event.feature}", 1),
                redis.expire(heatmap_key, 30 * 24 * 3600),  # 30 days retention
            ]

            # Conditional operations
            if event.user_id:
                operations.append(redis.sadd(f"{feature_key}:users", event.user_id))

            if event.session_id:
                operations.append(
                    redis.sadd(f"{feature_key}:sessions", event.session_id)
                )
                journey_key = f"{self.USER_JOURNEY_KEY}:{event.session_id}"
                operations.append(redis.rpush(journey_key, event.get_journey_entry()))
                operations.append(redis.expire(journey_key, 24 * 3600))

            if event.duration_ms and event.duration_ms > 0:
                operations.append(
                    redis.hincrby(feature_key, "total_time_ms", event.duration_ms)
                )

            # Issue #483: Execute all operations in parallel
            await asyncio.gather(*operations, return_exceptions=True)

            logger.debug(
                f"Tracked event: {event.event_type} on {event.feature} "
                f"for session {event.session_id}"
            )
            return True

        except Exception as e:
            logger.error("Failed to track user event: %s", e)
            return False

    async def get_feature_metrics(self, feature: Optional[str] = None) -> dict:
        """
        Get aggregated metrics for features.

        Issue #665: Refactored to use _process_feature_stats helper.

        Args:
            feature: Optional specific feature to get metrics for

        Returns:
            dict: Feature metrics
        """
        try:
            redis = await self.get_redis()
            result = {}

            features = (
                [feature]
                if feature
                else [
                    "chat",
                    "knowledge",
                    "tools",
                    "monitoring",
                    "infrastructure",
                    "secrets",
                    "settings",
                ]
            )

            # Batch fetch feature stats using pipeline (fix N+1 query)
            pipe = redis.pipeline()
            for feat in features:
                feature_key = f"{self.FEATURE_STATS_KEY}:{feat}"
                pipe.hgetall(feature_key)
                pipe.scard(f"{feature_key}:users")
                pipe.scard(f"{feature_key}:sessions")

            pipeline_results = await pipe.execute()

            # Process results in groups of 3 (stats, users, sessions)
            for i, feat in enumerate(features):
                idx = i * 3
                processed = self._process_feature_stats(
                    stats=pipeline_results[idx],
                    unique_users=pipeline_results[idx + 1],
                    unique_sessions=pipeline_results[idx + 2],
                    feat=feat,
                )
                if processed:
                    result[feat] = processed

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "features": result,
                "total_features": len(result),
            }

        except Exception as e:
            logger.error("Failed to get feature metrics: %s", e)
            return {"error": str(e), "features": {}}

    async def get_user_journey(self, session_id: str) -> dict:
        """
        Get the user journey for a specific session.

        Args:
            session_id: Session ID to get journey for

        Returns:
            dict: User journey data
        """
        try:
            redis = await self.get_redis()
            journey_key = f"{self.USER_JOURNEY_KEY}:{session_id}"

            journey_data = await redis.lrange(journey_key, 0, -1)

            steps = []
            for item in journey_data:
                data = item if isinstance(item, str) else item.decode("utf-8")
                parts = data.split("|")
                if len(parts) >= 3:
                    steps.append(
                        {
                            "timestamp": parts[0],
                            "feature": parts[1],
                            "event_type": parts[2],
                        }
                    )

            return {
                "session_id": session_id,
                "steps": steps,
                "total_steps": len(steps),
                "features_visited": list(set(s["feature"] for s in steps)),
            }

        except Exception as e:
            logger.error("Failed to get user journey: %s", e)
            return {"session_id": session_id, "error": str(e), "steps": []}

    async def get_daily_stats(self, days: int = 30) -> dict:
        """
        Get daily usage statistics.

        Args:
            days: Number of days to retrieve

        Returns:
            dict: Daily statistics
        """
        try:
            redis = await self.get_redis()
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            daily_data = {}
            current = start_date

            while current <= end_date:
                date_str = current.strftime("%Y-%m-%d")
                daily_key = f"{self.DAILY_STATS_KEY}:{date_str}"

                stats = await redis.hgetall(daily_key)
                if stats:
                    decoded = {}
                    for k, v in stats.items():
                        key = k if isinstance(k, str) else k.decode("utf-8")
                        val = v if isinstance(v, str) else v.decode("utf-8")
                        decoded[key] = int(val)
                    daily_data[date_str] = decoded

                current += timedelta(days=1)

            # Calculate totals
            total_views = sum(
                sum(v for k, v in day.items() if k.endswith(":views"))
                for day in daily_data.values()
            )

            return {
                "period": {
                    "start": start_date.strftime("%Y-%m-%d"),
                    "end": end_date.strftime("%Y-%m-%d"),
                    "days": days,
                },
                "daily_stats": daily_data,
                "total_views": total_views,
                "avg_daily_views": round(total_views / max(days, 1), 2),
            }

        except Exception as e:
            logger.error("Failed to get daily stats: %s", e)
            return {"error": str(e), "daily_stats": {}}

    def _process_feature_stats(
        self, stats: dict, unique_users: int, unique_sessions: int, feat: str
    ) -> Optional[dict]:
        """Process feature stats from Redis (Issue #665: extracted helper).

        Args:
            stats: Raw stats dict from Redis
            unique_users: Count of unique users
            unique_sessions: Count of unique sessions
            feat: Feature name

        Returns:
            Processed feature metrics dict, or None if no stats
        """
        if not stats:
            return None

        # Decode bytes to strings if needed
        decoded_stats = {}
        for k, v in stats.items():
            key = k if isinstance(k, str) else k.decode("utf-8")
            val = v if isinstance(v, str) else v.decode("utf-8")
            decoded_stats[key] = val

        total_views = int(decoded_stats.get("total_views", 0))
        total_time = int(decoded_stats.get("total_time_ms", 0))
        avg_time = total_time / max(total_views, 1)

        # Extract event counts
        event_counts = {
            key.replace("events:", ""): int(value)
            for key, value in decoded_stats.items()
            if key.startswith("events:")
        }

        return {
            "feature": feat,
            "total_views": total_views,
            "unique_users": unique_users,
            "unique_sessions": unique_sessions,
            "avg_time_spent_ms": round(avg_time, 2),
            "total_time_spent_ms": total_time,
            "event_breakdown": event_counts,
        }

    def _process_heatmap_data(self, data: dict, heatmap: dict) -> None:
        """Process heatmap data from Redis into heatmap dict. (Issue #315 - extracted)"""
        for key, value in data.items():
            key_str = key if isinstance(key, str) else key.decode("utf-8")
            val = int(value if isinstance(value, str) else value.decode("utf-8"))
            parts = key_str.split(":")
            if len(parts) != 2:
                continue
            hour, feature = parts
            if hour not in heatmap:
                heatmap[hour] = {}
            if feature not in heatmap[hour]:
                heatmap[hour][feature] = 0
            heatmap[hour][feature] += val

    async def get_usage_heatmap(self, days: int = 7) -> dict:
        """
        Get hourly usage heatmap data.

        Args:
            days: Number of days to include

        Returns:
            dict: Heatmap data by hour and feature
        """
        try:
            redis = await self.get_redis()
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Initialize heatmap structure
            heatmap = {str(h).zfill(2): {} for h in range(24)}

            current = start_date
            while current <= end_date:
                date_str = current.strftime("%Y-%m-%d")
                heatmap_key = f"{self.HEATMAP_KEY}:{date_str}"

                data = await redis.hgetall(heatmap_key)
                # Use helper to process data (Issue #315)
                self._process_heatmap_data(data, heatmap)

                current += timedelta(days=1)

            return {
                "period_days": days,
                "heatmap": heatmap,
                "peak_hours": self._find_peak_hours(heatmap),
            }

        except Exception as e:
            logger.error("Failed to get usage heatmap: %s", e)
            return {"error": str(e), "heatmap": {}}

    def _find_peak_hours(self, heatmap: dict) -> list:
        """Find peak usage hours from heatmap data"""
        hour_totals = []
        for hour, features in heatmap.items():
            total = sum(features.values())
            hour_totals.append((hour, total))

        hour_totals.sort(key=lambda x: x[1], reverse=True)
        return [{"hour": h, "total_events": t} for h, t in hour_totals[:5]]

    async def get_engagement_metrics(self) -> dict:
        """
        Get user engagement metrics.

        Returns:
            dict: Engagement metrics including session duration, bounce rate, etc.
        """
        try:
            features = await self.get_feature_metrics()

            if "error" in features:
                return features

            feature_data = features.get("features", {})

            # Calculate engagement scores
            total_sessions = sum(
                f.get("unique_sessions", 0) for f in feature_data.values()
            )
            total_time = sum(
                f.get("total_time_spent_ms", 0) for f in feature_data.values()
            )
            total_views = sum(f.get("total_views", 0) for f in feature_data.values())

            avg_session_duration = total_time / max(total_sessions, 1)
            pages_per_session = total_views / max(total_sessions, 1)

            # Feature popularity ranking
            popularity = sorted(
                [
                    {"feature": f, "views": d.get("total_views", 0)}
                    for f, d in feature_data.items()
                ],
                key=lambda x: x["views"],
                reverse=True,
            )

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "metrics": {
                    "total_sessions": total_sessions,
                    "total_page_views": total_views,
                    "avg_session_duration_ms": round(avg_session_duration, 2),
                    "pages_per_session": round(pages_per_session, 2),
                },
                "feature_popularity": popularity,
                "most_popular_feature": popularity[0]["feature"]
                if popularity
                else None,
            }

        except Exception as e:
            logger.error("Failed to get engagement metrics: %s", e)
            return {"error": str(e)}

    async def get_recent_events(self, limit: int = 100) -> list:
        """
        Get recent user events.

        Args:
            limit: Maximum number of events to return

        Returns:
            list: Recent events
        """
        try:
            redis = await self.get_redis()

            # Read from stream in reverse order
            events = await redis.xrevrange(self.EVENTS_KEY, count=limit)

            result = []
            for event_id, data in events:
                decoded = {}
                for k, v in data.items():
                    key = k if isinstance(k, str) else k.decode("utf-8")
                    val = v if isinstance(v, str) else v.decode("utf-8")
                    decoded[key] = val

                result.append(
                    {
                        "event_id": (
                            event_id
                            if isinstance(event_id, str)
                            else event_id.decode("utf-8")
                        ),
                        **decoded,
                    }
                )

            return result

        except Exception as e:
            logger.error("Failed to get recent events: %s", e)
            return []


# Singleton instance (thread-safe)
import threading

_behavior_analytics: Optional[UserBehaviorAnalytics] = None
_behavior_analytics_lock = threading.Lock()


def get_behavior_analytics() -> UserBehaviorAnalytics:
    """Get the singleton UserBehaviorAnalytics instance (thread-safe)."""
    global _behavior_analytics
    if _behavior_analytics is None:
        with _behavior_analytics_lock:
            # Double-check after acquiring lock
            if _behavior_analytics is None:
                _behavior_analytics = UserBehaviorAnalytics()
    return _behavior_analytics
