# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Evolution Timeline API Module (Issue #247)
Tracks and visualizes how code quality and patterns evolve over time.

Features:
- Historical metrics storage in Redis
- Timeline data retrieval with filtering
- Pattern evolution tracking
- Quality trend analysis
- Export capabilities (JSON, CSV)
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["code-evolution", "analytics"]
)  # Prefix set in router_registry

# Performance optimization: O(1) lookup for aggregation granularities (Issue #326)
AGGREGATION_GRANULARITIES = {"weekly", "monthly"}

# Redis key prefixes for evolution data
EVOLUTION_PREFIX = "evolution:"
SNAPSHOT_PREFIX = f"{EVOLUTION_PREFIX}snapshot:"
METRICS_PREFIX = f"{EVOLUTION_PREFIX}metrics:"
PATTERNS_PREFIX = f"{EVOLUTION_PREFIX}patterns:"


def _decode_redis_value(value) -> str:
    """Decode Redis bytes value to string (Issue #315)."""
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _get_snapshot_data(redis_client, keys: list) -> dict | None:
    """Get and decode snapshot data from Redis key (Issue #315: extracted).

    Returns:
        Parsed JSON data or None if unavailable
    """
    if not keys:
        return None
    key = _decode_redis_value(keys[0])
    json_data = redis_client.get(key)
    if not json_data:
        return None
    return json.loads(_decode_redis_value(json_data))


def _get_pattern_snapshots(redis_client, pattern_keys: list) -> list:
    """Get pattern snapshots from Redis keys (Issue #315, #480: pipeline batching)."""
    if not pattern_keys:
        return []

    # Filter out timeline keys first
    valid_keys = []
    for key in pattern_keys:
        key = _decode_redis_value(key)
        if ":timeline" not in key:
            valid_keys.append(key)

    if not valid_keys:
        return []

    # Issue #480: Use pipeline to batch all GET operations
    pipe = redis_client.pipeline()
    for key in valid_keys:
        pipe.get(key)
    results = pipe.execute()

    snapshots = []
    for snapshot_json in results:
        if snapshot_json:
            snapshot_json = _decode_redis_value(snapshot_json)
            snapshots.append(json.loads(snapshot_json))
    return snapshots


def _extract_pattern_types(all_keys: list) -> set:
    """Extract unique pattern types from Redis keys (Issue #315)."""
    pattern_types = set()
    for key in all_keys:
        key = _decode_redis_value(key)
        parts = key.replace(PATTERNS_PREFIX, "").split(":")
        if len(parts) >= 1 and parts[0] != "timeline":
            pattern_types.add(parts[0])
    return pattern_types


def _fetch_timeline_snapshots(redis_client, start_ts: float, end_ts: float) -> list:
    """
    Fetch timeline snapshots from Redis within a date range.

    Issue #281: Extracted from get_evolution_timeline to reduce nesting.
    Issue #480: Uses pipeline batching to avoid N+1 query pattern.

    Args:
        redis_client: Redis client instance
        start_ts: Start timestamp
        end_ts: End timestamp

    Returns:
        List of parsed snapshot dictionaries
    """
    snapshot_keys = redis_client.zrangebyscore(
        f"{EVOLUTION_PREFIX}timeline", start_ts, end_ts
    )

    if not snapshot_keys:
        return []

    # Decode all keys first
    decoded_keys = [
        key.decode("utf-8") if isinstance(key, bytes) else key for key in snapshot_keys
    ]

    # Issue #480: Use pipeline to batch all GET operations
    pipe = redis_client.pipeline()
    for key in decoded_keys:
        pipe.get(key)
    snapshot_data = pipe.execute()

    results = []
    for snapshot_json in snapshot_data:
        if snapshot_json:
            if isinstance(snapshot_json, bytes):
                snapshot_json = snapshot_json.decode("utf-8")
            results.append(json.loads(snapshot_json))
    return results


def _filter_timeline_by_metrics(
    timeline_data: List[Dict[str, Any]],
    requested_metrics: List[str],
) -> List[Dict[str, Any]]:
    """
    Filter timeline data to include only requested metrics.

    Issue #281: Extracted from get_evolution_timeline to simplify main function.

    Args:
        timeline_data: Raw timeline data from Redis
        requested_metrics: List of metric names to include

    Returns:
        Filtered timeline data
    """
    filtered_timeline = []
    for point in timeline_data:
        filtered_point = {"timestamp": point.get("timestamp")}
        for metric in requested_metrics:
            if metric in point:
                filtered_point[metric] = point[metric]
        filtered_timeline.append(filtered_point)
    return filtered_timeline


class QualitySnapshot(BaseModel):
    """A point-in-time quality snapshot"""

    timestamp: str
    overall_score: float = Field(ge=0, le=100)
    maintainability: float = Field(ge=0, le=100)
    testability: float = Field(ge=0, le=100)
    documentation: float = Field(ge=0, le=100)
    complexity: float = Field(ge=0, le=100)
    security: float = Field(ge=0, le=100)
    performance: float = Field(ge=0, le=100)
    total_files: int = 0
    total_lines: int = 0
    total_functions: int = 0
    total_classes: int = 0
    anti_patterns_count: int = 0
    problems_count: int = 0


class PatternSnapshot(BaseModel):
    """Pattern adoption snapshot"""

    timestamp: str
    pattern_type: str
    count: int
    severity_distribution: Dict[str, int] = {}
    top_files: List[str] = []


class EvolutionTimelineRequest(BaseModel):
    """Request for timeline data"""

    start_date: Optional[str] = None
    end_date: Optional[str] = None
    granularity: str = "daily"  # hourly, daily, weekly, monthly
    metrics: List[str] = ["overall_score", "complexity", "maintainability"]


def get_evolution_redis():
    """Get Redis client for evolution data storage"""
    return get_redis_client(database="analytics")


async def store_quality_snapshot(snapshot: QualitySnapshot) -> bool:
    """Store a quality snapshot in Redis.

    Issue #361: Uses asyncio.to_thread() to avoid blocking event loop
    when calling sync Redis operations.
    """
    redis_client = get_evolution_redis()
    if not redis_client:
        logger.warning("Redis not available for evolution tracking")
        return False

    try:
        # Store snapshot with timestamp-based key
        key = f"{SNAPSHOT_PREFIX}{snapshot.timestamp}"
        timestamp_score = datetime.fromisoformat(
            snapshot.timestamp.replace("Z", "+00:00")
        ).timestamp()

        # Issue #361: Execute sync Redis ops in thread pool
        def _store_snapshot():
            redis_client.set(key, snapshot.json(), ex=86400 * 365)  # Keep for 1 year
            redis_client.zadd(f"{EVOLUTION_PREFIX}timeline", {key: timestamp_score})

        await asyncio.to_thread(_store_snapshot)

        logger.info("Stored quality snapshot at %s", snapshot.timestamp)
        return True

    except Exception as e:
        logger.error("Failed to store quality snapshot: %s", e)
        return False


async def store_pattern_snapshot(snapshot: PatternSnapshot) -> bool:
    """Store a pattern snapshot in Redis.

    Issue #361: Uses asyncio.to_thread() to avoid blocking event loop
    when calling sync Redis operations.
    """
    redis_client = get_evolution_redis()
    if not redis_client:
        return False

    try:
        key = f"{PATTERNS_PREFIX}{snapshot.pattern_type}:{snapshot.timestamp}"
        timestamp_score = datetime.fromisoformat(
            snapshot.timestamp.replace("Z", "+00:00")
        ).timestamp()
        timeline_key = f"{PATTERNS_PREFIX}{snapshot.pattern_type}:timeline"

        # Issue #361: Execute sync Redis ops in thread pool
        def _store_pattern():
            redis_client.set(key, snapshot.json(), ex=86400 * 365)
            redis_client.zadd(timeline_key, {key: timestamp_score})

        await asyncio.to_thread(_store_pattern)

        return True

    except Exception as e:
        logger.error("Failed to store pattern snapshot: %s", e)
        return False


def _parse_date_range(start_date: Optional[str], end_date: Optional[str]) -> tuple:
    """Parse date range to timestamps (Issue #398: extracted)."""
    start_ts = (
        datetime.fromisoformat(start_date).timestamp()
        if start_date
        else (datetime.now() - timedelta(days=30)).timestamp()
    )
    end_ts = (
        datetime.fromisoformat(end_date).timestamp()
        if end_date
        else datetime.now().timestamp()
    )
    return start_ts, end_ts


def _no_data_response(
    message: str = "No evolution data. Redis required for timeline tracking.",
) -> dict:
    """Standardized no-data response (Issue #543)."""
    return {
        "status": "no_data",
        "message": message,
        "timeline": [],
        "patterns": {},
        "trends": {},
    }


def _build_timeline_response(
    timeline: list, start_date: str, end_date: str, granularity: str, metrics: list
) -> dict:
    """Build timeline success response (Issue #398: extracted)."""
    return {
        "status": "success",
        "timeline": timeline,
        "total_snapshots": len(timeline),
        "date_range": {"start": start_date, "end": end_date},
        "granularity": granularity,
        "metrics_available": metrics,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_evolution_timeline",
    error_code_prefix="EVOLUTION",
)
@router.get("/timeline")
async def get_evolution_timeline(
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    granularity: str = Query(
        "daily", description="Data granularity: hourly, daily, weekly, monthly"
    ),
    metrics: str = Query(
        "overall_score,complexity,maintainability",
        description="Comma-separated metrics",
    ),
    admin_check: bool = Depends(check_admin_permission),
):
    """Get code evolution timeline (Issue #398: refactored).

    Issue #744: Requires admin authentication."""
    redis_client = get_evolution_redis()
    requested_metrics = metrics.split(",")

    if not redis_client:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "Evolution tracking unavailable. Redis connection required.",
                "timeline": [],
                "metrics_available": requested_metrics,
            }
        )

    try:
        start_ts, end_ts = _parse_date_range(start_date, end_date)
        timeline_data = await asyncio.to_thread(
            _fetch_timeline_snapshots, redis_client, start_ts, end_ts
        )

        if granularity in AGGREGATION_GRANULARITIES and len(timeline_data) > 1:
            timeline_data = _aggregate_by_granularity(timeline_data, granularity)

        filtered_timeline = _filter_timeline_by_metrics(
            timeline_data, requested_metrics
        )
        return JSONResponse(
            _build_timeline_response(
                filtered_timeline, start_date, end_date, granularity, requested_metrics
            )
        )

    except Exception as e:
        logger.error("Error retrieving evolution timeline: %s", e)
        return JSONResponse(
            {
                "status": "no_data",
                "message": f"Evolution timeline unavailable: {str(e)}",
                "timeline": [],
            }
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pattern_evolution",
    error_code_prefix="EVOLUTION",
)
@router.get("/patterns")
async def get_pattern_evolution(
    pattern_type: Optional[str] = Query(
        None, description="Filter by pattern type (e.g., god_class, long_method)"
    ),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get pattern evolution data (Issue #315: depth 6→3).

    Tracks adoption/removal of patterns like god_class, long_method, etc.

    Issue #744: Requires admin authentication.
    """
    redis_client = get_evolution_redis()

    if not redis_client:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "Pattern evolution tracking unavailable. Redis connection required.",
                "patterns": {},
            }
        )

    try:
        # Issue #361 - run Redis ops in thread pool to avoid blocking
        def _fetch_patterns():
            result = {}
            if pattern_type:
                pattern_keys = (
                    redis_client.keys(f"{PATTERNS_PREFIX}{pattern_type}:*") or []
                )
                result[pattern_type] = _get_pattern_snapshots(
                    redis_client, pattern_keys
                )
            else:
                all_keys = redis_client.keys(f"{PATTERNS_PREFIX}*")
                pattern_types_list = _extract_pattern_types(all_keys)
                for ptype in pattern_types_list:
                    ptype_keys = redis_client.keys(f"{PATTERNS_PREFIX}{ptype}:2*")
                    result[ptype] = _get_pattern_snapshots(redis_client, ptype_keys)
            return result

        patterns_data = await asyncio.to_thread(_fetch_patterns)

        return JSONResponse(
            {
                "status": "success",
                "patterns": patterns_data,
                "pattern_types": list(patterns_data.keys()),
                "date_range": {"start": start_date, "end": end_date},
            }
        )

    except Exception as e:
        logger.error("Error retrieving pattern evolution: %s", e)
        return JSONResponse(
            {
                "status": "no_data",
                "message": f"Pattern evolution unavailable: {str(e)}",
                "patterns": {},
            }
        )


def _fetch_trend_snapshots_sync(
    redis_client, start_ts: float, end_ts: float
) -> List[Dict]:
    """Fetch snapshots from Redis within timestamp range (Issue #398, #480: pipeline batching)."""
    keys = redis_client.zrangebyscore(f"{EVOLUTION_PREFIX}timeline", start_ts, end_ts)

    if not keys:
        return []

    # Decode all keys first
    decoded_keys = [
        key.decode("utf-8") if isinstance(key, bytes) else key for key in keys
    ]

    # Issue #480: Use pipeline to batch all GET operations
    pipe = redis_client.pipeline()
    for key in decoded_keys:
        pipe.get(key)
    snapshot_data = pipe.execute()

    results = []
    for snapshot_json in snapshot_data:
        if snapshot_json:
            if isinstance(snapshot_json, bytes):
                snapshot_json = snapshot_json.decode("utf-8")
            results.append(json.loads(snapshot_json))
    return results


def _calculate_metric_trend(snapshots: List[Dict], metric: str) -> Optional[Dict]:
    """Calculate trend data for a single metric (Issue #398: extracted)."""
    values = [s.get(metric, 0) for s in snapshots if metric in s]
    if len(values) < 2:
        return None

    first_value = values[0]
    last_value = values[-1]
    change = last_value - first_value
    percent_change = (change / first_value * 100) if first_value > 0 else 0

    return {
        "first_value": first_value,
        "last_value": last_value,
        "change": round(change, 2),
        "percent_change": round(percent_change, 2),
        "direction": (
            "improving" if change > 0 else "declining" if change < 0 else "stable"
        ),
        "data_points": len(values),
    }


# Quality metrics to track for trends
_TREND_METRICS = [
    "overall_score",
    "maintainability",
    "testability",
    "documentation",
    "complexity",
    "security",
    "performance",
]


def _calculate_all_trends(snapshots: list) -> dict:
    """Calculate trends for all metrics (Issue #398: extracted)."""
    return {
        metric: data
        for metric in _TREND_METRICS
        if (data := _calculate_metric_trend(snapshots, metric))
    }


def _build_trends_success_response(
    trends: dict, days: int, snapshot_count: int
) -> dict:
    """Build trends success response (Issue #398: extracted)."""
    return {
        "status": "success",
        "trends": trends,
        "period_days": days,
        "snapshot_count": snapshot_count,
        "analysis_timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quality_trends",
    error_code_prefix="EVOLUTION",
)
@router.get("/trends")
async def get_quality_trends(
    days: int = Query(30, description="Number of days to analyze", ge=1, le=365),
    admin_check: bool = Depends(check_admin_permission),
):
    """Get quality trend analysis (Issue #398: refactored).

    Issue #744: Requires admin authentication."""
    redis_client = get_evolution_redis()

    if not redis_client:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "Quality trend analysis unavailable. Redis connection required.",
                "trends": {},
            }
        )

    try:
        start_ts = (datetime.now() - timedelta(days=days)).timestamp()
        end_ts = datetime.now().timestamp()
        snapshots = await asyncio.to_thread(
            _fetch_trend_snapshots_sync, redis_client, start_ts, end_ts
        )

        if len(snapshots) < 2:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": (
                        f"Insufficient data for trend analysis. "
                        f"Need at least 2 snapshots, found {len(snapshots)}."
                    ),
                    "trends": {},
                }
            )

        snapshots.sort(key=lambda x: x.get("timestamp", ""))
        return JSONResponse(
            _build_trends_success_response(
                _calculate_all_trends(snapshots), days, len(snapshots)
            )
        )

    except Exception as e:
        logger.error("Error calculating quality trends: %s", e)
        return JSONResponse(
            {
                "status": "no_data",
                "message": f"Quality trend analysis failed: {str(e)}",
                "trends": {},
            }
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_snapshot",
    error_code_prefix="EVOLUTION",
)
@router.post("/snapshot")
async def record_quality_snapshot(
    snapshot: QualitySnapshot,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Record a new quality snapshot.

    Called after each codebase analysis to track evolution.

    Issue #744: Requires admin authentication.
    """
    success = await store_quality_snapshot(snapshot)

    if success:
        return JSONResponse(
            {
                "status": "success",
                "message": f"Snapshot recorded at {snapshot.timestamp}",
                "snapshot": snapshot.dict(),
            }
        )
    else:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to store snapshot",
            },
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_pattern_snapshot",
    error_code_prefix="EVOLUTION",
)
@router.post("/pattern-snapshot")
async def record_pattern_snapshot(
    snapshot: PatternSnapshot,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Record a pattern snapshot.

    Tracks anti-pattern counts over time.

    Issue #744: Requires admin authentication.
    """
    success = await store_pattern_snapshot(snapshot)

    if success:
        return JSONResponse(
            {
                "status": "success",
                "message": f"Pattern snapshot recorded for {snapshot.pattern_type}",
                "snapshot": snapshot.dict(),
            }
        )
    else:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to store pattern snapshot",
            },
        )


def _parse_export_date_range(
    start_date: Optional[str], end_date: Optional[str]
) -> tuple:
    """Parse export date range with defaults (Issue #398: extracted)."""
    start_ts = datetime.fromisoformat(start_date).timestamp() if start_date else 0
    end_ts = (
        datetime.fromisoformat(end_date).timestamp()
        if end_date
        else datetime.now().timestamp()
    )
    return start_ts, end_ts


def _fetch_export_data_sync(redis_client, start_ts: float, end_ts: float) -> list:
    """Fetch export data from Redis synchronously (Issue #398, #480: pipeline batching)."""
    snapshot_keys = redis_client.zrangebyscore(
        f"{EVOLUTION_PREFIX}timeline", start_ts, end_ts
    )

    if not snapshot_keys:
        return []

    # Decode all keys first
    decoded_keys = [
        key.decode("utf-8") if isinstance(key, bytes) else key for key in snapshot_keys
    ]

    # Issue #480: Use pipeline to batch all GET operations
    pipe = redis_client.pipeline()
    for key in decoded_keys:
        pipe.get(key)
    snapshot_data = pipe.execute()

    results = []
    for snapshot_json in snapshot_data:
        if snapshot_json:
            snapshot_json = (
                snapshot_json.decode("utf-8")
                if isinstance(snapshot_json, bytes)
                else snapshot_json
            )
            results.append(json.loads(snapshot_json))
    return results


def _generate_csv_response(timeline_data: list) -> StreamingResponse:
    """Generate CSV streaming response (Issue #398: extracted)."""
    import csv
    import io

    output = io.StringIO()
    if timeline_data:
        fieldnames = list(timeline_data[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(timeline_data)
    csv_content = output.getvalue()
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=evolution_data_{datetime.now().strftime('%Y%m%d')}.csv"
        },
    )


def _generate_json_export_response(timeline_data: list) -> JSONResponse:
    """Generate JSON export response (Issue #398: extracted)."""
    return JSONResponse(
        {
            "status": "success",
            "export_format": "json",
            "data": timeline_data,
            "record_count": len(timeline_data),
            "exported_at": datetime.now().isoformat(),
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_evolution_data",
    error_code_prefix="EVOLUTION",
)
@router.get("/export")
async def export_evolution_data(
    format: str = Query("json", description="Export format: json, csv"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    admin_check: bool = Depends(check_admin_permission),
):
    """Export evolution data in JSON or CSV format (Issue #398: refactored, #543: no demo data).

    Issue #744: Requires admin authentication."""
    redis_client = get_evolution_redis()

    if not redis_client:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "Export unavailable. Redis connection required.",
                "data": [],
                "export_format": format,
            }
        )

    try:
        start_ts, end_ts = _parse_export_date_range(start_date, end_date)
        timeline_data = await asyncio.to_thread(
            _fetch_export_data_sync, redis_client, start_ts, end_ts
        )

        if not timeline_data:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No evolution data available for the specified date range.",
                    "data": [],
                    "export_format": format,
                }
            )

        return (
            _generate_csv_response(timeline_data)
            if format == "csv"
            else _generate_json_export_response(timeline_data)
        )

    except Exception as e:
        logger.error("Error exporting evolution data: %s", e)
        return JSONResponse(
            {
                "status": "no_data",
                "message": f"Export failed: {str(e)}",
                "data": [],
                "export_format": format,
            }
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_evolution_summary",
    error_code_prefix="EVOLUTION",
)
@router.get("/summary")
async def get_evolution_summary(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get a summary of code evolution including key statistics.

    Provides overview for dashboard display.

    Issue #744: Requires admin authentication.
    """
    redis_client = get_evolution_redis()

    summary = {
        "total_snapshots": 0,
        "date_range": {"first": None, "last": None},
        "latest_scores": {},
        "trend_direction": "unknown",
        "pattern_counts": {},
    }

    if redis_client:
        try:
            # Issue #361 - avoid blocking - fetch summary data in thread pool
            def _fetch_summary_data():
                total = redis_client.zcard(f"{EVOLUTION_PREFIX}timeline")
                first_data = None
                last_data = None
                if total > 0:
                    first_keys = redis_client.zrange(
                        f"{EVOLUTION_PREFIX}timeline", 0, 0
                    )
                    last_keys = redis_client.zrange(
                        f"{EVOLUTION_PREFIX}timeline", -1, -1
                    )
                    first_data = _get_snapshot_data(redis_client, first_keys)
                    last_data = _get_snapshot_data(redis_client, last_keys)
                return total, first_data, last_data

            total_snapshots, first_data, last_data = await asyncio.to_thread(
                _fetch_summary_data
            )
            summary["total_snapshots"] = total_snapshots

            if first_data:
                summary["date_range"]["first"] = first_data.get("timestamp")

            if last_data:
                summary["date_range"]["last"] = last_data.get("timestamp")
                summary["latest_scores"] = {
                    "overall_score": last_data.get("overall_score", 0),
                    "maintainability": last_data.get("maintainability", 0),
                    "complexity": last_data.get("complexity", 0),
                }

        except Exception as e:
            logger.error("Error getting evolution summary: %s", e)

    return JSONResponse({"status": "success", "summary": summary})


def _aggregate_by_granularity(
    data: List[Dict[str, Any]], granularity: str
) -> List[Dict[str, Any]]:
    """Aggregate timeline data by week or month"""
    from collections import defaultdict

    aggregated = defaultdict(list)

    for point in data:
        ts = point.get("timestamp", "")
        if not ts:
            continue

        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))

            if granularity == "weekly":
                # Use ISO week
                key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
            else:  # monthly
                key = f"{dt.year}-{dt.month:02d}"

            aggregated[key].append(point)
        except Exception:
            continue  # nosec B112 - Skipping malformed data points is intentional

    # Average values for each period
    result = []
    for period, points in sorted(aggregated.items()):
        avg_point = {"timestamp": period}
        numeric_fields = [
            "overall_score",
            "maintainability",
            "testability",
            "documentation",
            "complexity",
            "security",
            "performance",
            "total_files",
            "total_lines",
        ]

        for field in numeric_fields:
            values = [p.get(field, 0) for p in points if field in p]
            if values:
                avg_point[field] = round(sum(values) / len(values), 2)

        result.append(avg_point)

    return result


def _get_granularity_step(granularity: str) -> timedelta:
    """Get timedelta step for granularity (Issue #398: extracted)."""
    steps = {
        "hourly": timedelta(hours=1),
        "weekly": timedelta(weeks=1),
        "monthly": timedelta(days=30),
    }
    return steps.get(granularity, timedelta(days=1))


def _create_demo_data_point(  # nosec B311
    current: datetime, start: datetime, base_score: float
) -> dict:
    """Create a single demo data point (Issue #398: extracted).

    Note: Uses random.uniform for demo variance, not cryptographic purposes.
    """
    import random

    days_elapsed = (current - start).days
    trend = days_elapsed * 0.1
    return {
        "timestamp": current.isoformat(),
        "overall_score": min(100, max(0, base_score + trend + random.uniform(-3, 3))),
        "maintainability": min(100, max(0, 75 + trend * 0.8 + random.uniform(-2, 2))),
        "testability": min(100, max(0, 65 + trend * 0.5 + random.uniform(-2, 2))),
        "documentation": min(100, max(0, 60 + trend * 0.3 + random.uniform(-2, 2))),
        "complexity": min(100, max(0, 80 + trend * 0.6 + random.uniform(-2, 2))),
        "security": min(100, max(0, 78 + trend * 0.4 + random.uniform(-1, 1))),
        "performance": min(100, max(0, 72 + trend * 0.7 + random.uniform(-2, 2))),
        "total_files": 350 + days_elapsed,
        "total_lines": 65000 + days_elapsed * 100,
    }


def _generate_demo_timeline(
    start_date: Optional[str], end_date: Optional[str], granularity: str
) -> List[Dict[str, Any]]:
    """Generate demo timeline data for visualization testing (Issue #398: refactored).

    TEST ONLY - Not used in production responses (Issue #543).
    """
    start = (
        datetime.fromisoformat(start_date)
        if start_date
        else datetime.now() - timedelta(days=30)
    )
    end = datetime.fromisoformat(end_date) if end_date else datetime.now()
    step = _get_granularity_step(granularity)

    timeline = []
    current = start
    while current <= end:
        timeline.append(_create_demo_data_point(current, start, base_score=70))
        current += step
    return timeline


def _generate_demo_patterns() -> Dict[str, List[Dict[str, Any]]]:
    """Generate demo pattern evolution data.

    TEST ONLY - Not used in production responses (Issue #543).
    """
    patterns = {
        "god_class": [],
        "long_method": [],
        "duplicate_code": [],
        "hardcoded_value": [],
    }

    start = datetime.now() - timedelta(days=30)

    for i in range(30):
        current = start + timedelta(days=i)
        timestamp = current.isoformat()

        # Simulate decreasing anti-patterns over time
        patterns["god_class"].append(
            {
                "timestamp": timestamp,
                "count": max(0, 15 - i // 3),
                "pattern_type": "god_class",
            }
        )
        patterns["long_method"].append(
            {
                "timestamp": timestamp,
                "count": max(0, 45 - i),
                "pattern_type": "long_method",
            }
        )
        patterns["duplicate_code"].append(
            {
                "timestamp": timestamp,
                "count": max(0, 25 - i // 2),
                "pattern_type": "duplicate_code",
            }
        )
        patterns["hardcoded_value"].append(
            {
                "timestamp": timestamp,
                "count": max(0, 100 - i * 2),
                "pattern_type": "hardcoded_value",
            }
        )

    return patterns


# Demo trend data configuration: (first_value, last_value, direction)
_DEMO_TREND_CONFIG = {
    "overall_score": (70.0, 75.5, "improving"),
    "maintainability": (72.0, 78.0, "improving"),
    "complexity": (65.0, 68.0, "improving"),
    "testability": (60.0, 62.0, "improving"),
    "documentation": (55.0, 58.0, "improving"),
    "security": (80.0, 82.0, "improving"),
    "performance": (75.0, 76.0, "stable"),
}


def _build_demo_trend_entry(
    first: float, last: float, direction: str, days: int
) -> dict:
    """Build a single demo trend entry (Issue #398: extracted)."""
    change = last - first
    percent_change = round((change / first * 100) if first > 0 else 0, 2)
    return {
        "first_value": first,
        "last_value": last,
        "change": change,
        "percent_change": percent_change,
        "direction": direction,
        "data_points": days,
    }


def _generate_demo_trends(days: int) -> Dict[str, Any]:
    """Generate demo trend data (Issue #398: refactored).

    TEST ONLY - Not used in production responses (Issue #543).
    """
    return {
        metric: _build_demo_trend_entry(first, last, direction, days)
        for metric, (first, last, direction) in _DEMO_TREND_CONFIG.items()
    }


# =============================================================================
# Code Evolution Mining (Issue #243)
# =============================================================================


class EvolutionAnalysisRequest(BaseModel):
    """Request to trigger code evolution analysis"""

    repo_path: str = Field(description="Path to git repository to analyze")
    start_date: Optional[str] = Field(
        None, description="Start date for analysis (ISO format)"
    )
    end_date: Optional[str] = Field(
        None, description="End date for analysis (ISO format)"
    )
    commit_limit: int = Field(
        100, description="Maximum number of commits to analyze", ge=1, le=1000
    )


class EvolutionAnalysisResponse(BaseModel):
    """Response from evolution analysis"""

    status: str
    message: str
    commits_analyzed: int = 0
    emerging_patterns: List[Dict[str, Any]] = []
    declining_patterns: List[Dict[str, Any]] = []
    refactorings_detected: int = 0
    analysis_duration_seconds: float = 0.0


async def _store_pattern_snapshots(analysis_result: Dict) -> int:
    """
    Store pattern snapshots from analysis results (Issue #243).

    Returns number of snapshots stored.
    """
    snapshots_stored = 0

    try:
        timestamp = datetime.now().isoformat()

        # Store snapshots for each pattern type
        pattern_timeline = analysis_result.get("pattern_timeline", {})

        for month, patterns in pattern_timeline.items():
            for pattern_type, count in patterns.items():
                if count > 0:
                    snapshot = PatternSnapshot(
                        timestamp=timestamp,
                        pattern_type=pattern_type,
                        count=count,
                        severity_distribution={},
                        top_files=[],
                    )

                    success = await store_pattern_snapshot(snapshot)
                    if success:
                        snapshots_stored += 1

    except Exception as e:
        logger.error("Failed to store pattern snapshots: %s", e)

    return snapshots_stored


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="trigger_evolution_analysis",
    error_code_prefix="EVOLUTION",
)
@router.post("/analyze", response_model=EvolutionAnalysisResponse)
async def trigger_evolution_analysis(
    request: EvolutionAnalysisRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Trigger code evolution mining analysis on a git repository (Issue #243).

    Analyzes git history to track pattern evolution, detect refactorings,
    and identify emerging/declining code patterns.

    Requires admin authentication.
    """
    import time
    from pathlib import Path

    from code_intelligence.code_evolution_miner import CodeEvolutionMiner

    start_time = time.time()

    try:
        # Validate repo path
        repo_path = Path(request.repo_path)
        if not repo_path.exists():
            return EvolutionAnalysisResponse(
                status="error",
                message=f"Repository path not found: {request.repo_path}",
            )

        if not (repo_path / ".git").exists():
            return EvolutionAnalysisResponse(
                status="error",
                message=f"Not a git repository: {request.repo_path}",
            )

        # Parse dates
        start_date = (
            datetime.fromisoformat(request.start_date) if request.start_date else None
        )
        end_date = (
            datetime.fromisoformat(request.end_date) if request.end_date else None
        )

        # Run analysis in thread pool to avoid blocking
        def _run_analysis():
            miner = CodeEvolutionMiner(str(repo_path))
            return miner.analyze_evolution(start_date=start_date, end_date=end_date)

        analysis_result = await asyncio.to_thread(_run_analysis)

        # Store pattern snapshots in Redis for timeline tracking
        await _store_pattern_snapshots(analysis_result)

        duration = time.time() - start_time

        return EvolutionAnalysisResponse(
            status="success",
            message="Code evolution analysis completed successfully",
            commits_analyzed=analysis_result.get("commits_analyzed", 0),
            emerging_patterns=analysis_result.get("emerging_patterns", []),
            declining_patterns=analysis_result.get("declining_patterns", []),
            refactorings_detected=len(analysis_result.get("refactorings", [])),
            analysis_duration_seconds=round(duration, 2),
        )

    except Exception as e:
        logger.error("Evolution analysis failed: %s", e)
        return EvolutionAnalysisResponse(
            status="error",
            message=f"Analysis failed: {str(e)}",
            analysis_duration_seconds=round(time.time() - start_time, 2),
        )
