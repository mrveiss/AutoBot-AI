# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Access Control Metrics Collection Service

Tracks access control violations during LOG_ONLY mode for safe rollout analysis.
Stores metrics in Redis DB 4 (metrics) with 7-day retention.

Features:
- Per-endpoint violation tracking
- Per-user violation tracking
- Time-series data for trend analysis
- Aggregated statistics for dashboard
- Automatic cleanup of old data
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.constants.network_constants import NetworkConstants
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class AccessControlMetrics:
    """
    Track and analyze access control violations for safe rollout

    Metrics stored:
    - Individual violations (7-day retention)
    - Aggregated counts by endpoint
    - Aggregated counts by user
    - Daily summaries
    - Time-series data for trending
    """

    def __init__(self, retention_days: int = 7):
        """
        Initialize metrics collection service

        Args:
            retention_days: How long to keep detailed metrics (default: 7 days)
        """
        self.retention_days = retention_days
        self._redis = None

    async def _get_redis(self):
        """Get Redis metrics database (DB 4)"""
        if not self._redis:
            # Get async Redis client for metrics database (returns coroutine, must await)
            self._redis = await get_redis_client(async_client=True, database="metrics")
        return self._redis

    async def record_violation(
        self,
        session_id: str,
        username: str,
        actual_owner: str,
        endpoint: str,
        ip_address: str,
        enforcement_mode: str = "log_only",
    ) -> bool:
        """
        Record an access control violation

        Args:
            session_id: Chat session ID (will be truncated for privacy)
            username: User who attempted access
            actual_owner: Actual owner of the session
            endpoint: API endpoint accessed
            ip_address: Client IP address
            enforcement_mode: Current enforcement mode when violation occurred

        Returns:
            True if recorded successfully
        """
        try:
            redis = await self._get_redis()

            timestamp = datetime.now().timestamp()
            date_str = datetime.now().strftime("%Y-%m-%d")
            violation_id = str(uuid.uuid4())

            # Create violation record
            violation_data = {
                "id": violation_id,
                "session_id": session_id[:16] + "...",  # Truncate for privacy
                "username": username,
                "actual_owner": actual_owner,
                "endpoint": endpoint,
                "ip_address": ip_address,
                "enforcement_mode": enforcement_mode,
                "timestamp": timestamp,
                "date": date_str,
            }

            # Store individual violation with expiration
            violation_key = f"access_violation:{violation_id}"
            await redis.set(
                violation_key,
                json.dumps(violation_data),
                ex=self.retention_days * 86400,  # Expire after retention period
            )

            # Update aggregated counters
            async with redis.pipeline() as pipe:
                # Total count for the day
                await pipe.hincrby(f"violations:daily:{date_str}", "total", 1)

                # Count by endpoint
                await pipe.hincrby(f"violations:by_endpoint:{date_str}", endpoint, 1)

                # Count by user
                await pipe.hincrby(f"violations:by_user:{date_str}", username, 1)

                # Add to time-series sorted set
                await pipe.zadd(
                    f"violations:timeline:{date_str}", {violation_id: timestamp}
                )

                # Set expiration on daily keys
                retention_seconds = (self.retention_days + 1) * 86400
                await pipe.expire(f"violations:daily:{date_str}", retention_seconds)
                await pipe.expire(
                    f"violations:by_endpoint:{date_str}", retention_seconds
                )
                await pipe.expire(f"violations:by_user:{date_str}", retention_seconds)
                await pipe.expire(f"violations:timeline:{date_str}", retention_seconds)

                await pipe.execute()

            logger.debug(
                f"Recorded violation: {username} -> {endpoint} "
                f"(session owned by {actual_owner})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to record violation: {e}")
            return False

    async def get_statistics(
        self, days: int = 7, include_details: bool = False
    ) -> Dict[str, Any]:
        """
        Get aggregated violation statistics

        Args:
            days: Number of days to include in statistics
            include_details: Include recent violation details

        Returns:
            Dictionary with violation statistics
        """
        try:
            redis = await self._get_redis()

            stats = {
                "total_violations": 0,
                "by_endpoint": {},
                "by_user": {},
                "by_day": {},
                "period_days": days,
            }

            # Collect data from each day in the period
            for day_offset in range(days):
                date = (datetime.now() - timedelta(days=day_offset)).strftime(
                    "%Y-%m-%d"
                )

                # Get daily total
                daily_data = await redis.hgetall(f"violations:daily:{date}")
                if daily_data:
                    total_key = (
                        b"total"
                        if isinstance(list(daily_data.keys())[0], bytes)
                        else "total"
                    ),
                    daily_total = int(daily_data.get(total_key, 0))
                    stats["by_day"][date] = daily_total
                    stats["total_violations"] += daily_total

                # Get endpoint breakdown
                endpoint_counts = await redis.hgetall(f"violations:by_endpoint:{date}")
                for endpoint, count in endpoint_counts.items():
                    if isinstance(endpoint, bytes):
                        endpoint = endpoint.decode("utf-8")
                    if isinstance(count, bytes):
                        count = count.decode("utf-8")

                    stats["by_endpoint"][endpoint] = stats["by_endpoint"].get(
                        endpoint, 0
                    ) + int(count)

                # Get user breakdown
                user_counts = await redis.hgetall(f"violations:by_user:{date}")
                for user, count in user_counts.items():
                    if isinstance(user, bytes):
                        user = user.decode("utf-8")
                    if isinstance(count, bytes):
                        count = count.decode("utf-8")

                    stats["by_user"][user] = stats["by_user"].get(user, 0) + int(count)

            # Get recent violations if requested
            if include_details:
                stats["recent_violations"] = await self._get_recent_violations(limit=20)

            # Calculate trends
            if len(stats["by_day"]) > 1:
                dates = sorted(stats["by_day"].keys())
                if len(dates) >= 2:
                    yesterday = stats["by_day"].get(dates[-2], 0)
                    today = stats["by_day"].get(dates[-1], 0)

                    if yesterday > 0:
                        change = ((today - yesterday) / yesterday) * 100
                        stats["daily_change_percent"] = round(change, 2)

            return stats

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"error": str(e), "total_violations": 0}

    async def _get_recent_violations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get most recent violations

        Args:
            limit: Maximum number of violations to return

        Returns:
            List of violation records
        """
        try:
            redis = await self._get_redis()
            violations = []

            # Search last 7 days
            for day_offset in range(min(7, self.retention_days)):
                date = (datetime.now() - timedelta(days=day_offset)).strftime(
                    "%Y-%m-%d"
                )

                # Get violation IDs from timeline (sorted by timestamp, newest first)
                violation_ids = await redis.zrevrange(
                    f"violations:timeline:{date}", 0, limit - len(violations)
                )

                # Fetch violation details
                for vid in violation_ids:
                    if isinstance(vid, bytes):
                        vid = vid.decode("utf-8")

                    violation_key = f"access_violation:{vid}"
                    violation_data = await redis.get(violation_key)

                    if violation_data:
                        if isinstance(violation_data, bytes):
                            violation_data = violation_data.decode("utf-8")

                        try:
                            violations.append(json.loads(violation_data))
                        except Exception:
                            pass

                if len(violations) >= limit:
                    break

            return violations[:limit]

        except Exception as e:
            logger.error(f"Failed to get recent violations: {e}")
            return []

    async def get_endpoint_statistics(
        self, endpoint: str, days: int = 7
    ) -> Dict[str, Any]:
        """
        Get statistics for a specific endpoint

        Args:
            endpoint: API endpoint path
            days: Number of days to include

        Returns:
            Endpoint-specific statistics
        """
        try:
            redis = await self._get_redis()

            stats = {
                "endpoint": endpoint,
                "total_violations": 0,
                "by_day": {},
                "period_days": days,
            }

            for day_offset in range(days):
                date = (datetime.now() - timedelta(days=day_offset)).strftime(
                    "%Y-%m-%d"
                )

                count = await redis.hget(f"violations:by_endpoint:{date}", endpoint)
                if count:
                    if isinstance(count, bytes):
                        count = count.decode("utf-8")

                    daily_count = int(count)
                    stats["by_day"][date] = daily_count
                    stats["total_violations"] += daily_count

            return stats

        except Exception as e:
            logger.error(f"Failed to get endpoint statistics: {e}")
            return {"endpoint": endpoint, "error": str(e)}

    async def get_user_statistics(self, username: str, days: int = 7) -> Dict[str, Any]:
        """
        Get statistics for a specific user

        Args:
            username: Username to analyze
            days: Number of days to include

        Returns:
            User-specific statistics
        """
        try:
            redis = await self._get_redis()

            stats = {
                "username": username,
                "total_violations": 0,
                "by_day": {},
                "period_days": days,
            }

            for day_offset in range(days):
                date = (datetime.now() - timedelta(days=day_offset)).strftime(
                    "%Y-%m-%d"
                )

                count = await redis.hget(f"violations:by_user:{date}", username)
                if count:
                    if isinstance(count, bytes):
                        count = count.decode("utf-8")

                    daily_count = int(count)
                    stats["by_day"][date] = daily_count
                    stats["total_violations"] += daily_count

            return stats

        except Exception as e:
            logger.error(f"Failed to get user statistics: {e}")
            return {"username": username, "error": str(e)}

    async def cleanup_old_metrics(self):
        """
        Manually cleanup metrics older than retention period

        Note: Most cleanup happens automatically via Redis TTL,
        but this can be called for immediate cleanup
        """
        try:
            redis = await self._get_redis()
            deleted_count = 0

            # Clean up daily keys older than retention period
            for days_back in range(self.retention_days, 365):  # Check up to 1 year back
                date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

                keys_to_delete = [
                    f"violations:daily:{date}",
                    f"violations:by_endpoint:{date}",
                    f"violations:by_user:{date}",
                    f"violations:timeline:{date}",
                ]

                deleted = await redis.delete(*keys_to_delete)
                deleted_count += deleted

            logger.info(f"Cleaned up {deleted_count} old metric keys")

        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}")


# Global metrics instance
_metrics_service: Optional[AccessControlMetrics] = None
_metrics_lock = asyncio.Lock()


async def get_metrics_service() -> AccessControlMetrics:
    """Get or create global metrics service instance"""
    global _metrics_service

    async with _metrics_lock:
        if _metrics_service is None:
            _metrics_service = AccessControlMetrics()
            logger.info("Access control metrics service initialized")
        return _metrics_service
