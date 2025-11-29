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

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evolution", tags=["code-evolution", "analytics"])

# Redis key prefixes for evolution data
EVOLUTION_PREFIX = "evolution:"
SNAPSHOT_PREFIX = f"{EVOLUTION_PREFIX}snapshot:"
METRICS_PREFIX = f"{EVOLUTION_PREFIX}metrics:"
PATTERNS_PREFIX = f"{EVOLUTION_PREFIX}patterns:"


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
    """Store a quality snapshot in Redis"""
    redis_client = get_evolution_redis()
    if not redis_client:
        logger.warning("Redis not available for evolution tracking")
        return False

    try:
        # Store snapshot with timestamp-based key
        key = f"{SNAPSHOT_PREFIX}{snapshot.timestamp}"
        redis_client.set(key, snapshot.json(), ex=86400 * 365)  # Keep for 1 year

        # Add to sorted set for time-based queries
        timestamp_score = datetime.fromisoformat(
            snapshot.timestamp.replace("Z", "+00:00")
        ).timestamp()
        redis_client.zadd(f"{EVOLUTION_PREFIX}timeline", {key: timestamp_score})

        logger.info(f"Stored quality snapshot at {snapshot.timestamp}")
        return True

    except Exception as e:
        logger.error(f"Failed to store quality snapshot: {e}")
        return False


async def store_pattern_snapshot(snapshot: PatternSnapshot) -> bool:
    """Store a pattern snapshot in Redis"""
    redis_client = get_evolution_redis()
    if not redis_client:
        return False

    try:
        key = f"{PATTERNS_PREFIX}{snapshot.pattern_type}:{snapshot.timestamp}"
        redis_client.set(key, snapshot.json(), ex=86400 * 365)

        # Add to pattern-specific timeline
        timestamp_score = datetime.fromisoformat(
            snapshot.timestamp.replace("Z", "+00:00")
        ).timestamp()
        redis_client.zadd(
            f"{PATTERNS_PREFIX}{snapshot.pattern_type}:timeline", {key: timestamp_score}
        )

        return True

    except Exception as e:
        logger.error(f"Failed to store pattern snapshot: {e}")
        return False


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_evolution_timeline",
    error_code_prefix="EVOLUTION",
)
@router.get("/timeline")
async def get_evolution_timeline(
    start_date: Optional[str] = Query(
        None, description="Start date (ISO format, e.g., 2025-01-01)"
    ),
    end_date: Optional[str] = Query(
        None, description="End date (ISO format, e.g., 2025-12-31)"
    ),
    granularity: str = Query(
        "daily", description="Data granularity: hourly, daily, weekly, monthly"
    ),
    metrics: str = Query(
        "overall_score,complexity,maintainability",
        description="Comma-separated list of metrics to include",
    ),
):
    """
    Get code evolution timeline data for visualization.

    Returns quality metrics over time for charting.
    """
    redis_client = get_evolution_redis()

    if not redis_client:
        # Return demo data if Redis unavailable
        return JSONResponse(
            {
                "status": "demo",
                "message": "Redis unavailable, returning demo timeline data",
                "timeline": _generate_demo_timeline(start_date, end_date, granularity),
                "metrics_available": metrics.split(","),
            }
        )

    try:
        # Parse date range
        if start_date:
            start_ts = datetime.fromisoformat(start_date).timestamp()
        else:
            start_ts = (datetime.now() - timedelta(days=30)).timestamp()

        if end_date:
            end_ts = datetime.fromisoformat(end_date).timestamp()
        else:
            end_ts = datetime.now().timestamp()

        # Get snapshots from Redis sorted set
        snapshot_keys = redis_client.zrangebyscore(
            f"{EVOLUTION_PREFIX}timeline", start_ts, end_ts
        )

        timeline_data = []
        for key in snapshot_keys:
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            snapshot_json = redis_client.get(key)
            if snapshot_json:
                if isinstance(snapshot_json, bytes):
                    snapshot_json = snapshot_json.decode("utf-8")
                snapshot = json.loads(snapshot_json)
                timeline_data.append(snapshot)

        # Apply granularity aggregation if needed
        if granularity in ["weekly", "monthly"] and len(timeline_data) > 1:
            timeline_data = _aggregate_by_granularity(timeline_data, granularity)

        # Filter to requested metrics
        requested_metrics = metrics.split(",")
        filtered_timeline = []
        for point in timeline_data:
            filtered_point = {"timestamp": point.get("timestamp")}
            for metric in requested_metrics:
                if metric in point:
                    filtered_point[metric] = point[metric]
            filtered_timeline.append(filtered_point)

        return JSONResponse(
            {
                "status": "success",
                "timeline": filtered_timeline,
                "total_snapshots": len(filtered_timeline),
                "date_range": {"start": start_date, "end": end_date},
                "granularity": granularity,
                "metrics_available": requested_metrics,
            }
        )

    except Exception as e:
        logger.error(f"Error retrieving evolution timeline: {e}")
        return JSONResponse(
            {
                "status": "error",
                "message": str(e),
                "timeline": _generate_demo_timeline(start_date, end_date, granularity),
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
):
    """
    Get pattern evolution data showing how anti-patterns change over time.

    Tracks adoption/removal of patterns like god_class, long_method, etc.
    """
    redis_client = get_evolution_redis()

    if not redis_client:
        return JSONResponse(
            {
                "status": "demo",
                "message": "Redis unavailable, returning demo pattern data",
                "patterns": _generate_demo_patterns(),
            }
        )

    try:
        patterns_data = {}

        if pattern_type:
            # Get specific pattern timeline
            pattern_keys = redis_client.keys(f"{PATTERNS_PREFIX}{pattern_type}:*")
            if not pattern_keys:
                pattern_keys = []

            patterns_data[pattern_type] = []
            for key in pattern_keys:
                if isinstance(key, bytes):
                    key = key.decode("utf-8")
                if ":timeline" in key:
                    continue  # Skip the timeline sorted set key

                snapshot_json = redis_client.get(key)
                if snapshot_json:
                    if isinstance(snapshot_json, bytes):
                        snapshot_json = snapshot_json.decode("utf-8")
                    patterns_data[pattern_type].append(json.loads(snapshot_json))
        else:
            # Get all pattern types
            all_keys = redis_client.keys(f"{PATTERNS_PREFIX}*")
            pattern_types = set()

            for key in all_keys:
                if isinstance(key, bytes):
                    key = key.decode("utf-8")
                # Extract pattern type from key
                parts = key.replace(PATTERNS_PREFIX, "").split(":")
                if len(parts) >= 1 and parts[0] != "timeline":
                    pattern_types.add(parts[0])

            for ptype in pattern_types:
                patterns_data[ptype] = []
                ptype_keys = redis_client.keys(f"{PATTERNS_PREFIX}{ptype}:2*")
                for key in ptype_keys:
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")
                    snapshot_json = redis_client.get(key)
                    if snapshot_json:
                        if isinstance(snapshot_json, bytes):
                            snapshot_json = snapshot_json.decode("utf-8")
                        patterns_data[ptype].append(json.loads(snapshot_json))

        return JSONResponse(
            {
                "status": "success",
                "patterns": patterns_data,
                "pattern_types": list(patterns_data.keys()),
                "date_range": {"start": start_date, "end": end_date},
            }
        )

    except Exception as e:
        logger.error(f"Error retrieving pattern evolution: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e), "patterns": _generate_demo_patterns()}
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quality_trends",
    error_code_prefix="EVOLUTION",
)
@router.get("/trends")
async def get_quality_trends(
    days: int = Query(30, description="Number of days to analyze", ge=1, le=365),
):
    """
    Get quality trend analysis showing improvement/degradation over time.

    Calculates trend direction, velocity, and predictions.
    """
    redis_client = get_evolution_redis()

    if not redis_client:
        return JSONResponse(
            {
                "status": "demo",
                "message": "Redis unavailable, returning demo trend data",
                "trends": _generate_demo_trends(days),
            }
        )

    try:
        # Get snapshots for the period
        end_ts = datetime.now().timestamp()
        start_ts = (datetime.now() - timedelta(days=days)).timestamp()

        snapshot_keys = redis_client.zrangebyscore(
            f"{EVOLUTION_PREFIX}timeline", start_ts, end_ts
        )

        if len(snapshot_keys) < 2:
            return JSONResponse(
                {
                    "status": "insufficient_data",
                    "message": f"Need at least 2 snapshots for trend analysis, found {len(snapshot_keys)}",
                    "trends": _generate_demo_trends(days),
                }
            )

        # Load snapshots
        snapshots = []
        for key in snapshot_keys:
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            snapshot_json = redis_client.get(key)
            if snapshot_json:
                if isinstance(snapshot_json, bytes):
                    snapshot_json = snapshot_json.decode("utf-8")
                snapshots.append(json.loads(snapshot_json))

        # Sort by timestamp
        snapshots.sort(key=lambda x: x.get("timestamp", ""))

        # Calculate trends for each metric
        metrics = [
            "overall_score",
            "maintainability",
            "testability",
            "documentation",
            "complexity",
            "security",
            "performance",
        ]

        trends = {}
        for metric in metrics:
            values = [s.get(metric, 0) for s in snapshots if metric in s]
            if len(values) >= 2:
                first_value = values[0]
                last_value = values[-1]
                change = last_value - first_value
                percent_change = (change / first_value * 100) if first_value > 0 else 0

                trends[metric] = {
                    "first_value": first_value,
                    "last_value": last_value,
                    "change": round(change, 2),
                    "percent_change": round(percent_change, 2),
                    "direction": (
                        "improving" if change > 0 else "declining" if change < 0 else "stable"
                    ),
                    "data_points": len(values),
                }

        return JSONResponse(
            {
                "status": "success",
                "trends": trends,
                "period_days": days,
                "snapshot_count": len(snapshots),
                "analysis_timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error calculating quality trends: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e), "trends": _generate_demo_trends(days)}
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_snapshot",
    error_code_prefix="EVOLUTION",
)
@router.post("/snapshot")
async def record_quality_snapshot(snapshot: QualitySnapshot):
    """
    Record a new quality snapshot.

    Called after each codebase analysis to track evolution.
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
async def record_pattern_snapshot(snapshot: PatternSnapshot):
    """
    Record a pattern snapshot.

    Tracks anti-pattern counts over time.
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
):
    """
    Export evolution data in JSON or CSV format.

    Useful for external analysis or reporting.
    """
    redis_client = get_evolution_redis()

    # Get timeline data
    timeline_data = []

    if redis_client:
        try:
            if start_date:
                start_ts = datetime.fromisoformat(start_date).timestamp()
            else:
                start_ts = 0

            if end_date:
                end_ts = datetime.fromisoformat(end_date).timestamp()
            else:
                end_ts = datetime.now().timestamp()

            snapshot_keys = redis_client.zrangebyscore(
                f"{EVOLUTION_PREFIX}timeline", start_ts, end_ts
            )

            for key in snapshot_keys:
                if isinstance(key, bytes):
                    key = key.decode("utf-8")
                snapshot_json = redis_client.get(key)
                if snapshot_json:
                    if isinstance(snapshot_json, bytes):
                        snapshot_json = snapshot_json.decode("utf-8")
                    timeline_data.append(json.loads(snapshot_json))

        except Exception as e:
            logger.error(f"Error exporting evolution data: {e}")
            timeline_data = _generate_demo_timeline(start_date, end_date, "daily")
    else:
        timeline_data = _generate_demo_timeline(start_date, end_date, "daily")

    if format == "csv":
        # Generate CSV
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
    else:
        # Return JSON
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
    operation="get_evolution_summary",
    error_code_prefix="EVOLUTION",
)
@router.get("/summary")
async def get_evolution_summary():
    """
    Get a summary of code evolution including key statistics.

    Provides overview for dashboard display.
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
            # Count total snapshots
            summary["total_snapshots"] = redis_client.zcard(f"{EVOLUTION_PREFIX}timeline")

            # Get date range
            if summary["total_snapshots"] > 0:
                first_keys = redis_client.zrange(f"{EVOLUTION_PREFIX}timeline", 0, 0)
                last_keys = redis_client.zrange(f"{EVOLUTION_PREFIX}timeline", -1, -1)

                if first_keys:
                    first_key = first_keys[0]
                    if isinstance(first_key, bytes):
                        first_key = first_key.decode("utf-8")
                    first_json = redis_client.get(first_key)
                    if first_json:
                        if isinstance(first_json, bytes):
                            first_json = first_json.decode("utf-8")
                        first_data = json.loads(first_json)
                        summary["date_range"]["first"] = first_data.get("timestamp")

                if last_keys:
                    last_key = last_keys[0]
                    if isinstance(last_key, bytes):
                        last_key = last_key.decode("utf-8")
                    last_json = redis_client.get(last_key)
                    if last_json:
                        if isinstance(last_json, bytes):
                            last_json = last_json.decode("utf-8")
                        last_data = json.loads(last_json)
                        summary["date_range"]["last"] = last_data.get("timestamp")
                        summary["latest_scores"] = {
                            "overall_score": last_data.get("overall_score", 0),
                            "maintainability": last_data.get("maintainability", 0),
                            "complexity": last_data.get("complexity", 0),
                        }

        except Exception as e:
            logger.error(f"Error getting evolution summary: {e}")

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
            continue

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


def _generate_demo_timeline(
    start_date: Optional[str], end_date: Optional[str], granularity: str
) -> List[Dict[str, Any]]:
    """Generate demo timeline data for visualization testing"""
    import random

    if start_date:
        start = datetime.fromisoformat(start_date)
    else:
        start = datetime.now() - timedelta(days=30)

    if end_date:
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now()

    timeline = []
    current = start
    base_score = 70

    while current <= end:
        # Simulate gradual improvement with some noise
        days_elapsed = (current - start).days
        trend = days_elapsed * 0.1  # Slight improvement over time
        noise = random.uniform(-3, 3)

        timeline.append(
            {
                "timestamp": current.isoformat(),
                "overall_score": min(100, max(0, base_score + trend + noise)),
                "maintainability": min(100, max(0, 75 + trend * 0.8 + random.uniform(-2, 2))),
                "testability": min(100, max(0, 65 + trend * 0.5 + random.uniform(-2, 2))),
                "documentation": min(100, max(0, 60 + trend * 0.3 + random.uniform(-2, 2))),
                "complexity": min(100, max(0, 80 + trend * 0.6 + random.uniform(-2, 2))),
                "security": min(100, max(0, 78 + trend * 0.4 + random.uniform(-1, 1))),
                "performance": min(100, max(0, 72 + trend * 0.7 + random.uniform(-2, 2))),
                "total_files": 350 + days_elapsed,
                "total_lines": 65000 + days_elapsed * 100,
            }
        )

        if granularity == "hourly":
            current += timedelta(hours=1)
        elif granularity == "weekly":
            current += timedelta(weeks=1)
        elif granularity == "monthly":
            current += timedelta(days=30)
        else:
            current += timedelta(days=1)

    return timeline


def _generate_demo_patterns() -> Dict[str, List[Dict[str, Any]]]:
    """Generate demo pattern evolution data"""
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
            {"timestamp": timestamp, "count": max(0, 15 - i // 3), "pattern_type": "god_class"}
        )
        patterns["long_method"].append(
            {"timestamp": timestamp, "count": max(0, 45 - i), "pattern_type": "long_method"}
        )
        patterns["duplicate_code"].append(
            {"timestamp": timestamp, "count": max(0, 25 - i // 2), "pattern_type": "duplicate_code"}
        )
        patterns["hardcoded_value"].append(
            {"timestamp": timestamp, "count": max(0, 100 - i * 2), "pattern_type": "hardcoded_value"}
        )

    return patterns


def _generate_demo_trends(days: int) -> Dict[str, Any]:
    """Generate demo trend data"""
    return {
        "overall_score": {
            "first_value": 70.0,
            "last_value": 75.5,
            "change": 5.5,
            "percent_change": 7.86,
            "direction": "improving",
            "data_points": days,
        },
        "maintainability": {
            "first_value": 72.0,
            "last_value": 78.0,
            "change": 6.0,
            "percent_change": 8.33,
            "direction": "improving",
            "data_points": days,
        },
        "complexity": {
            "first_value": 65.0,
            "last_value": 68.0,
            "change": 3.0,
            "percent_change": 4.62,
            "direction": "improving",
            "data_points": days,
        },
        "testability": {
            "first_value": 60.0,
            "last_value": 62.0,
            "change": 2.0,
            "percent_change": 3.33,
            "direction": "improving",
            "data_points": days,
        },
        "documentation": {
            "first_value": 55.0,
            "last_value": 58.0,
            "change": 3.0,
            "percent_change": 5.45,
            "direction": "improving",
            "data_points": days,
        },
        "security": {
            "first_value": 80.0,
            "last_value": 82.0,
            "change": 2.0,
            "percent_change": 2.5,
            "direction": "improving",
            "data_points": days,
        },
        "performance": {
            "first_value": 75.0,
            "last_value": 76.0,
            "change": 1.0,
            "percent_change": 1.33,
            "direction": "stable",
            "data_points": days,
        },
    }
