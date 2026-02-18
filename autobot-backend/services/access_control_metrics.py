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
from typing import List, Optional

from backend.type_defs.common import Metadata

from autobot_shared.redis_client import get_redis_client

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
                ex=self.retention_days * 86400,
            )

            # Update aggregated counters using helper
            await self._update_violation_counters(
                redis, date_str, violation_id, timestamp, endpoint, username
            )

            logger.debug(
                f"Recorded violation: {username} -> {endpoint} "
                f"(session owned by {actual_owner})"
            )
            return True

        except Exception as e:
            logger.error("Failed to record violation: %s", e)
            return False

    async def _update_violation_counters(
        self,
        redis,
        date_str: str,
        violation_id: str,
        timestamp: float,
        endpoint: str,
        username: str,
    ) -> None:
        """Update aggregated violation counters in Redis (Issue #665: extracted helper).

        Args:
            redis: Redis client
            date_str: Date string for key prefix
            violation_id: Unique violation ID
            timestamp: Violation timestamp
            endpoint: API endpoint
            username: Username who violated
        """
        retention_seconds = (self.retention_days + 1) * 86400

        async with redis.pipeline() as pipe:
            # Update daily counters
            await pipe.hincrby(f"violations:daily:{date_str}", "total", 1)
            await pipe.hincrby(f"violations:by_endpoint:{date_str}", endpoint, 1)
            await pipe.hincrby(f"violations:by_user:{date_str}", username, 1)
            await pipe.zadd(
                f"violations:timeline:{date_str}", {violation_id: timestamp}
            )

            # Set expirations
            await pipe.expire(f"violations:daily:{date_str}", retention_seconds)
            await pipe.expire(f"violations:by_endpoint:{date_str}", retention_seconds)
            await pipe.expire(f"violations:by_user:{date_str}", retention_seconds)
            await pipe.expire(f"violations:timeline:{date_str}", retention_seconds)

            await pipe.execute()

    def _aggregate_redis_counts(
        self,
        source_counts: dict,
        target_dict: dict,
    ) -> None:
        """
        Aggregate Redis hash counts, handling byte decoding.

        Issue #281: Extracted helper to reduce repetition in get_statistics.
        Handles the common pattern of decoding bytes and summing counts.

        Args:
            source_counts: Raw Redis hash data (may have bytes keys/values)
            target_dict: Target dictionary to aggregate counts into
        """
        for key, count in source_counts.items():
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            if isinstance(count, bytes):
                count = count.decode("utf-8")
            target_dict[key] = target_dict.get(key, 0) + int(count)

    def _process_daily_results(
        self, results: list, dates: list, stats: Metadata
    ) -> None:
        """Process pipeline results and aggregate into stats (Issue #665: extracted helper)."""
        for i, date in enumerate(dates):
            daily_data = results[i * 3]
            endpoint_counts = results[i * 3 + 1]
            user_counts = results[i * 3 + 2]

            # Process daily total
            if daily_data:
                total_key = (
                    b"total"
                    if isinstance(list(daily_data.keys())[0], bytes)
                    else "total"
                )
                daily_total = int(daily_data.get(total_key, 0))
                stats["by_day"][date] = daily_total
                stats["total_violations"] += daily_total

            # Process endpoint and user breakdowns
            self._aggregate_redis_counts(endpoint_counts, stats["by_endpoint"])
            self._aggregate_redis_counts(user_counts, stats["by_user"])

    def _calculate_daily_trend(self, stats: Metadata) -> None:
        """Calculate daily change percent if enough data exists (Issue #665: extracted helper)."""
        if len(stats["by_day"]) <= 1:
            return

        dates = sorted(stats["by_day"])
        if len(dates) >= 2:
            yesterday = stats["by_day"].get(dates[-2], 0)
            today = stats["by_day"].get(dates[-1], 0)

            if yesterday > 0:
                change = ((today - yesterday) / yesterday) * 100
                stats["daily_change_percent"] = round(change, 2)

    async def get_statistics(
        self, days: int = 7, include_details: bool = False
    ) -> Metadata:
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

            # Build list of dates to query
            dates = [
                (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                for day_offset in range(days)
            ]

            # Batch fetch all data using pipeline - eliminates N+1 queries
            async with redis.pipeline() as pipe:
                for date in dates:
                    await pipe.hgetall(f"violations:daily:{date}")
                    await pipe.hgetall(f"violations:by_endpoint:{date}")
                    await pipe.hgetall(f"violations:by_user:{date}")
                results = await pipe.execute()

            # Process results
            self._process_daily_results(results, dates, stats)

            # Get recent violations if requested
            if include_details:
                stats["recent_violations"] = await self._get_recent_violations(limit=20)

            # Calculate trends
            self._calculate_daily_trend(stats)

            return stats

        except Exception as e:
            logger.error("Failed to get statistics: %s", e)
            return {"error": str(e), "total_violations": 0}

    def _parse_json_violation_data(
        self,
        violation_data_results: list,
    ) -> List[Metadata]:
        """
        Parse JSON violation records from Redis data.

        Issue #281: Extracted helper to reduce complexity in _get_recent_violations.
        Handles bytes decoding and JSON parse error handling.

        Args:
            violation_data_results: Raw Redis data (may be bytes or strings)

        Returns:
            List of parsed violation dictionaries
        """
        violations = []
        for violation_data in violation_data_results:
            if not violation_data:
                continue
            if isinstance(violation_data, bytes):
                violation_data = violation_data.decode("utf-8")
            try:
                violations.append(json.loads(violation_data))
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug("Failed to parse violation data: %s", e)
        return violations

    async def _get_recent_violations(self, limit: int = 20) -> List[Metadata]:
        """
        Get most recent violations

        Args:
            limit: Maximum number of violations to return

        Returns:
            List of violation records
        """
        try:
            redis = await self._get_redis()

            # Build list of dates to query
            dates = [
                (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                for day_offset in range(min(7, self.retention_days))
            ]

            # Batch fetch violation IDs from all days using pipeline
            async with redis.pipeline() as pipe:
                for date in dates:
                    await pipe.zrevrange(f"violations:timeline:{date}", 0, limit - 1)
                timeline_results = await pipe.execute()

            # Collect all violation IDs (maintaining order by recency)
            all_violation_ids = []
            for vids in timeline_results:
                for vid in vids:
                    if isinstance(vid, bytes):
                        vid = vid.decode("utf-8")
                    all_violation_ids.append(vid)
                    if len(all_violation_ids) >= limit:
                        break
                if len(all_violation_ids) >= limit:
                    break

            if not all_violation_ids:
                return []

            # Batch fetch all violation details - eliminates N+1 queries
            async with redis.pipeline() as pipe:
                for vid in all_violation_ids:
                    await pipe.get(f"access_violation:{vid}")
                violation_data_results = await pipe.execute()

            # Parse results using extracted helper (Issue #281)
            violations = self._parse_json_violation_data(violation_data_results)
            return violations[:limit]

        except Exception as e:
            logger.error("Failed to get recent violations: %s", e)
            return []

    async def get_endpoint_statistics(self, endpoint: str, days: int = 7) -> Metadata:
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

            # Build list of dates to query
            dates = [
                (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                for day_offset in range(days)
            ]

            # Batch fetch all endpoint counts using pipeline - eliminates N+1 queries
            async with redis.pipeline() as pipe:
                for date in dates:
                    await pipe.hget(f"violations:by_endpoint:{date}", endpoint)
                results = await pipe.execute()

            # Process results
            for date, count in zip(dates, results):
                if count:
                    if isinstance(count, bytes):
                        count = count.decode("utf-8")

                    daily_count = int(count)
                    stats["by_day"][date] = daily_count
                    stats["total_violations"] += daily_count

            return stats

        except Exception as e:
            logger.error("Failed to get endpoint statistics: %s", e)
            return {"endpoint": endpoint, "error": str(e)}

    async def get_user_statistics(self, username: str, days: int = 7) -> Metadata:
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

            # Build list of dates to query
            dates = [
                (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                for day_offset in range(days)
            ]

            # Batch fetch all user counts using pipeline - eliminates N+1 queries
            async with redis.pipeline() as pipe:
                for date in dates:
                    await pipe.hget(f"violations:by_user:{date}", username)
                results = await pipe.execute()

            # Process results
            for date, count in zip(dates, results):
                if count:
                    if isinstance(count, bytes):
                        count = count.decode("utf-8")

                    daily_count = int(count)
                    stats["by_day"][date] = daily_count
                    stats["total_violations"] += daily_count

            return stats

        except Exception as e:
            logger.error("Failed to get user statistics: %s", e)
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
            # Collect all keys to delete first - eliminates N+1 individual delete calls
            all_keys_to_delete = []
            for days_back in range(self.retention_days, 365):  # Check up to 1 year back
                date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

                all_keys_to_delete.extend(
                    [
                        f"violations:daily:{date}",
                        f"violations:by_endpoint:{date}",
                        f"violations:by_user:{date}",
                        f"violations:timeline:{date}",
                    ]
                )

            # Batch delete all keys at once
            if all_keys_to_delete:
                deleted_count = await redis.delete(*all_keys_to_delete)

            logger.info("Cleaned up %s old metric keys", deleted_count)

        except Exception as e:
            logger.error("Failed to cleanup old metrics: %s", e)


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
