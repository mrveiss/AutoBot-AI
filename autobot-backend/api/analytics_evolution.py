# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse

from api.analytics_shared import resolve_source_or_404 as _resolve_source_or_404
from api.schemas_analytics import (
    AnalyticsEvolutionExportResponse,
    AnalyticsEvolutionPatternSnapshotResponse,
    AnalyticsEvolutionPatternsResponse,
    AnalyticsEvolutionSnapshotResponse,
    AnalyticsEvolutionSummaryResponse,
    AnalyticsEvolutionTimelineResponse,
    AnalyticsEvolutionTrendsResponse,
    DateRangeParams,
    EvolutionAnalysisRequest,
    EvolutionAnalysisResponse,
    EvolutionQualitySnapshot,
    PatternSnapshot,
)
from api.schemas_common import DataResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.redis_utils import decode_redis_value as _decode_redis_value
from autobot_shared.security.path_validator import validate_path
from autobot_shared.time_utils import parse_utc_iso

logger = get_logger(__name__)
router = APIRouter(tags=["code-evolution", "analytics"])  # Prefix set in router_registry


# Performance optimization: O(1) lookup for aggregation granularities (Issue #326)
AGGREGATION_GRANULARITIES = {"weekly", "monthly"}

# Redis key prefixes for evolution data (global, unscoped)
EVOLUTION_PREFIX = "evolution:"
SNAPSHOT_PREFIX = f"{EVOLUTION_PREFIX}snapshot:"
METRICS_PREFIX = f"{EVOLUTION_PREFIX}metrics:"
PATTERNS_PREFIX = f"{EVOLUTION_PREFIX}patterns:"


def _build_evolution_prefixes(source_id: str | None) -> tuple[str, str, str]:
    """Return (evolution_prefix, snapshot_prefix, patterns_prefix) scoped to source_id.

    Issue #3441: When source_id is provided, all Redis keys are namespaced as
    ``evolution:{source_id}:*`` so snapshots and patterns are stored and
    retrieved per-project rather than globally.

    Args:
        source_id: Project source identifier, or None for global data.

    Returns:
        Three-tuple of (evolution_prefix, snapshot_prefix, patterns_prefix).
    """
    if source_id:
        ev = f"evolution:{source_id}:"
    else:
        ev = EVOLUTION_PREFIX
    return ev, f"{ev}snapshot:", f"{ev}patterns:"


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
    return _extract_pattern_types_from_prefix(all_keys, PATTERNS_PREFIX)


def _extract_pattern_types_from_prefix(all_keys: list, patterns_prefix: str) -> set:
    """Extract unique pattern types from Redis keys using an arbitrary prefix.

    Issue #3441: Generalised form of _extract_pattern_types that accepts the
    prefix string so callers can work with per-project namespaces.

    Args:
        all_keys: Raw Redis key list (bytes or str).
        patterns_prefix: The prefix to strip before splitting on ``:``.

    Returns:
        Set of pattern type strings found after stripping the prefix.
    """
    pattern_types = set()
    for key in all_keys:
        key = _decode_redis_value(key)
        parts = key.replace(patterns_prefix, "").split(":")
        if len(parts) >= 1 and parts[0] != "timeline":
            pattern_types.add(parts[0])
    return pattern_types


def _fetch_timeline_snapshots(
    redis_client,
    start_ts: float,
    end_ts: float,
    evolution_prefix: str = EVOLUTION_PREFIX,
) -> list:
    """Fetch timeline snapshots from Redis within a date range.

    Issue #281: Extracted from get_evolution_timeline to reduce nesting.
    Issue #480: Uses pipeline batching to avoid N+1 query pattern.
    Issue #3441: Accepts evolution_prefix so callers can scope to a project
    namespace (``evolution:{source_id}:``).

    Args:
        redis_client: Redis client instance
        start_ts: Start timestamp
        end_ts: End timestamp
        evolution_prefix: Redis key prefix for the target namespace.

    Returns:
        List of parsed snapshot dictionaries
    """
    snapshot_keys = redis_client.zrangebyscore(f"{evolution_prefix}timeline", start_ts, end_ts)

    if not snapshot_keys:
        return []

    # Decode all keys first
    decoded_keys = [key.decode("utf-8") if isinstance(key, bytes) else key for key in snapshot_keys]

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


def get_evolution_redis():
    """Get Redis client for evolution data storage"""
    return get_redis_client(database="analytics")


async def store_quality_snapshot(snapshot: EvolutionQualitySnapshot) -> bool:
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
        timestamp_score = parse_utc_iso(snapshot.timestamp).timestamp()

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
        timestamp_score = parse_utc_iso(snapshot.timestamp).timestamp()
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


def _parse_date_range(start_date: str | None, end_date: str | None) -> tuple:
    """Parse date range to timestamps (Issue #398: extracted)."""
    start_ts = (
        parse_utc_iso(start_date).timestamp()
        if start_date
        else (datetime.now(tz=timezone.utc) - timedelta(days=30)).timestamp()
    )
    end_ts = parse_utc_iso(end_date).timestamp() if end_date else datetime.now(tz=timezone.utc).timestamp()
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


def _build_timeline_response(timeline: list, start_date: str, end_date: str, granularity: str, metrics: list) -> dict:
    """Build timeline success response (Issue #398: extracted)."""
    return {
        "status": "success",
        "timeline": timeline,
        "total_snapshots": len(timeline),
        "date_range": {"start": start_date, "end": end_date},
        "granularity": granularity,
        "metrics_available": metrics,
    }


@router.get("/timeline", response_model=DataResponse[AnalyticsEvolutionTimelineResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_evolution_timeline",
    error_code_prefix="ANALYTICS_EVOLUTION",
)
async def get_evolution_timeline(
    date_range: DateRangeParams = Depends(),
    granularity: str = Query("daily", description="Data granularity: hourly, daily, weekly, monthly"),
    metrics: str = Query(
        "overall_score,complexity,maintainability",
        description="Comma-separated metrics",
    ),
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
):
    """Get code evolution timeline (Issue #398: refactored).

    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is provided, timeline snapshots are read from
    the ``evolution:{source_id}:`` key namespace so only that project's
    history is returned.

    Issue #7110: ``start_date`` / ``end_date`` query params consolidated into
    ``DateRangeParams`` ``Depends()``. The two query params are unchanged at
    the HTTP boundary — only the Python signature shifts.
    """
    await _resolve_source_or_404(source_id)
    evolution_prefix, _snap, _pat = _build_evolution_prefixes(source_id)
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
        start_ts, end_ts = _parse_date_range(date_range.start_date, date_range.end_date)
        timeline_data = await asyncio.to_thread(
            _fetch_timeline_snapshots, redis_client, start_ts, end_ts, evolution_prefix
        )

        if granularity in AGGREGATION_GRANULARITIES and len(timeline_data) > 1:
            timeline_data = _aggregate_by_granularity(timeline_data, granularity)

        filtered_timeline = _filter_timeline_by_metrics(timeline_data, requested_metrics)
        return JSONResponse(
            _build_timeline_response(
                filtered_timeline,
                date_range.start_date,
                date_range.end_date,
                granularity,
                requested_metrics,
            )
        )

    except Exception as e:
        logger.error("Error retrieving evolution timeline: %s", e)
        return JSONResponse(
            {
                "status": "no_data",
                "message": "Evolution timeline unavailable",
                "timeline": [],
            }
        )


@router.get("/patterns", response_model=DataResponse[AnalyticsEvolutionPatternsResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pattern_evolution",
    error_code_prefix="ANALYTICS_EVOLUTION",
)
async def get_pattern_evolution(
    pattern_type: str | None = Query(None, description="Filter by pattern type (e.g., god_class, long_method)"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
):
    """
    Get pattern evolution data (Issue #315: depth 6→3).

    Tracks adoption/removal of patterns like god_class, long_method, etc.

    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is provided, pattern snapshots are read from
    the ``evolution:{source_id}:patterns:`` namespace so only that project's
    pattern history is returned.
    """
    await _resolve_source_or_404(source_id)
    _ev_prefix, _snap_prefix, patterns_prefix = _build_evolution_prefixes(source_id)
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
                pattern_keys = redis_client.keys(f"{patterns_prefix}{pattern_type}:*") or []
                result[pattern_type] = _get_pattern_snapshots(redis_client, pattern_keys)
            else:
                all_keys = redis_client.keys(f"{patterns_prefix}*")
                pattern_types_list = _extract_pattern_types_from_prefix(all_keys, patterns_prefix)
                for ptype in pattern_types_list:
                    ptype_keys = redis_client.keys(f"{patterns_prefix}{ptype}:2*")
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
                "message": "Pattern evolution unavailable",
                "patterns": {},
            }
        )


def _fetch_trend_snapshots_sync(
    redis_client,
    start_ts: float,
    end_ts: float,
    evolution_prefix: str = EVOLUTION_PREFIX,
) -> List[Dict]:
    """Fetch snapshots from Redis within timestamp range (Issue #398, #480: pipeline batching).

    Issue #3441: Accepts evolution_prefix so callers can scope queries to a
    project namespace (``evolution:{source_id}:``).
    """
    keys = redis_client.zrangebyscore(f"{evolution_prefix}timeline", start_ts, end_ts)

    if not keys:
        return []

    # Decode all keys first
    decoded_keys = [key.decode("utf-8") if isinstance(key, bytes) else key for key in keys]

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


def _calculate_metric_trend(snapshots: List[Dict], metric: str) -> Dict | None:
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
        "direction": ("improving" if change > 0 else "declining" if change < 0 else "stable"),
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
    return {metric: data for metric in _TREND_METRICS if (data := _calculate_metric_trend(snapshots, metric))}


def _build_trends_success_response(trends: dict, days: int, snapshot_count: int) -> dict:
    """Build trends success response (Issue #398: extracted)."""
    return {
        "status": "success",
        "trends": trends,
        "period_days": days,
        "snapshot_count": snapshot_count,
        "analysis_timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/trends", response_model=DataResponse[AnalyticsEvolutionTrendsResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quality_trends",
    error_code_prefix="ANALYTICS_EVOLUTION",
)
async def get_quality_trends(
    days: int = Query(30, description="Number of days to analyze", ge=1, le=365),
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
):
    """Get quality trend analysis (Issue #398: refactored).

    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is provided, snapshots are read from the
    ``evolution:{source_id}:`` namespace so trends reflect only that
    project's history.
    """
    await _resolve_source_or_404(source_id)
    evolution_prefix, _snap, _pat = _build_evolution_prefixes(source_id)
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
        start_ts = (datetime.now(tz=timezone.utc) - timedelta(days=days)).timestamp()
        end_ts = datetime.now(tz=timezone.utc).timestamp()
        snapshots = await asyncio.to_thread(
            _fetch_trend_snapshots_sync,
            redis_client,
            start_ts,
            end_ts,
            evolution_prefix,
        )

        if len(snapshots) < 2:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": (
                        f"Insufficient data for trend analysis. " f"Need at least 2 snapshots, found {len(snapshots)}."
                    ),
                    "trends": {},
                }
            )

        snapshots.sort(key=lambda x: x.get("timestamp", ""))
        return JSONResponse(_build_trends_success_response(_calculate_all_trends(snapshots), days, len(snapshots)))

    except Exception as e:
        logger.error("Error calculating quality trends: %s", e)
        return JSONResponse(
            {
                "status": "no_data",
                "message": "Quality trend analysis failed",
                "trends": {},
            }
        )


@router.post("/snapshot", response_model=DataResponse[AnalyticsEvolutionSnapshotResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_quality_snapshot",
    error_code_prefix="ANALYTICS_EVOLUTION",
)
async def record_quality_snapshot(
    snapshot: EvolutionQualitySnapshot,
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


@router.post("/pattern-snapshot", response_model=DataResponse[AnalyticsEvolutionPatternSnapshotResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_pattern_snapshot",
    error_code_prefix="ANALYTICS_EVOLUTION",
)
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


def _parse_export_date_range(start_date: str | None, end_date: str | None) -> tuple:
    """Parse export date range with defaults (Issue #398: extracted)."""
    start_ts = parse_utc_iso(start_date).timestamp() if start_date else 0
    end_ts = parse_utc_iso(end_date).timestamp() if end_date else datetime.now(tz=timezone.utc).timestamp()
    return start_ts, end_ts


def _fetch_export_data_sync(redis_client, start_ts: float, end_ts: float) -> list:
    """Fetch export data from Redis synchronously (Issue #398, #480: pipeline batching)."""
    snapshot_keys = redis_client.zrangebyscore(f"{EVOLUTION_PREFIX}timeline", start_ts, end_ts)

    if not snapshot_keys:
        return []

    # Decode all keys first
    decoded_keys = [key.decode("utf-8") if isinstance(key, bytes) else key for key in snapshot_keys]

    # Issue #480: Use pipeline to batch all GET operations
    pipe = redis_client.pipeline()
    for key in decoded_keys:
        pipe.get(key)
    snapshot_data = pipe.execute()

    results = []
    for snapshot_json in snapshot_data:
        if snapshot_json:
            snapshot_json = snapshot_json.decode("utf-8") if isinstance(snapshot_json, bytes) else snapshot_json
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
            "Content-Disposition": (
                "attachment; filename=evolution_data_" f"{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}.csv"
            )
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
            "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        }
    )


@router.get("/export", response_model=DataResponse[AnalyticsEvolutionExportResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_evolution_data",
    error_code_prefix="ANALYTICS_EVOLUTION",
)
async def export_evolution_data(
    format: str = Query("json", description="Export format: json, csv"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
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
        timeline_data = await asyncio.to_thread(_fetch_export_data_sync, redis_client, start_ts, end_ts)

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
            _generate_csv_response(timeline_data) if format == "csv" else _generate_json_export_response(timeline_data)
        )

    except Exception as e:
        logger.error("Error exporting evolution data: %s", e)
        return JSONResponse(
            {
                "status": "no_data",
                "message": "Export failed",
                "data": [],
                "export_format": format,
            }
        )


@router.get("/summary", response_model=DataResponse[AnalyticsEvolutionSummaryResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_evolution_summary",
    error_code_prefix="ANALYTICS_EVOLUTION",
)
async def get_evolution_summary(
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
):
    """
    Get a summary of code evolution including key statistics.

    Provides overview for dashboard display.

    Issue #744: Requires admin authentication.
    Issue #3436: Accepts optional source_id to scope results to a project.
    """
    await _resolve_source_or_404(source_id)
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
                    first_keys = redis_client.zrange(f"{EVOLUTION_PREFIX}timeline", 0, 0)
                    last_keys = redis_client.zrange(f"{EVOLUTION_PREFIX}timeline", -1, -1)
                    first_data = _get_snapshot_data(redis_client, first_keys)
                    last_data = _get_snapshot_data(redis_client, last_keys)
                return total, first_data, last_data

            total_snapshots, first_data, last_data = await asyncio.to_thread(_fetch_summary_data)
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


def _aggregate_by_granularity(data: List[Dict[str, Any]], granularity: str) -> List[Dict[str, Any]]:
    """Aggregate timeline data by week or month"""
    from collections import defaultdict

    aggregated = defaultdict(list)

    for point in data:
        ts = point.get("timestamp", "")
        if not ts:
            continue

        try:
            dt = parse_utc_iso(ts)

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


def _create_demo_data_point(current: datetime, start: datetime, base_score: float) -> dict:  # nosec B311
    """Create a single demo data point (Issue #398: extracted).

    Note: Uses random.uniform for demo variance, not cryptographic purposes.
    """
    import random

    days_elapsed = (current - start).days
    trend = days_elapsed * 0.1
    return {
        "timestamp": current.isoformat(),
        "overall_score": min(100, max(0, base_score + trend + random.uniform(-3, 3))),  # nosec B311 - analytics variance noise, not cryptographic
        "maintainability": min(100, max(0, 75 + trend * 0.8 + random.uniform(-2, 2))),  # nosec B311 - analytics variance noise
        "testability": min(100, max(0, 65 + trend * 0.5 + random.uniform(-2, 2))),  # nosec B311 - analytics variance noise
        "documentation": min(100, max(0, 60 + trend * 0.3 + random.uniform(-2, 2))),  # nosec B311 - analytics variance noise
        "complexity": min(100, max(0, 80 + trend * 0.6 + random.uniform(-2, 2))),  # nosec B311 - analytics variance noise
        "security": min(100, max(0, 78 + trend * 0.4 + random.uniform(-1, 1))),  # nosec B311 - analytics variance noise
        "performance": min(100, max(0, 72 + trend * 0.7 + random.uniform(-2, 2))),  # nosec B311 - analytics variance noise
        "total_files": 350 + days_elapsed,
        "total_lines": 65000 + days_elapsed * 100,
    }


def _generate_demo_timeline(start_date: str | None, end_date: str | None, granularity: str) -> List[Dict[str, Any]]:
    """Generate demo timeline data for visualization testing (Issue #398: refactored).

    TEST ONLY - Not used in production responses (Issue #543).
    """
    start = parse_utc_iso(start_date) if start_date else datetime.now(tz=timezone.utc) - timedelta(days=30)
    end = parse_utc_iso(end_date) if end_date else datetime.now(tz=timezone.utc)
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

    start = datetime.now(tz=timezone.utc) - timedelta(days=30)

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


def _build_demo_trend_entry(first: float, last: float, direction: str, days: int) -> dict:
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


async def _store_pattern_snapshots(analysis_result: Dict) -> int:
    """
    Store pattern snapshots from analysis results (Issue #243).

    Returns number of snapshots stored.
    """
    snapshots_stored = 0

    try:
        timestamp = datetime.now(tz=timezone.utc).isoformat()

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


def _validate_evolution_repo_path(repo_path_str: str):
    """Helper for trigger_evolution_analysis. Ref: #1088.

    Returns (repo_path, error_response) where error_response is None if valid.
    """

    try:
        repo_path = validate_path(repo_path_str)
    except ValueError:
        return None, EvolutionAnalysisResponse(
            status="error",
            message="Invalid repository path: outside allowed directories",
        )
    if not repo_path.exists():
        return None, EvolutionAnalysisResponse(
            status="error",
            message=f"Repository path not found: {repo_path_str}",
        )
    if not (repo_path / ".git").exists():  # codeql[py/path-injection]
        return None, EvolutionAnalysisResponse(
            status="error",
            message=f"Not a git repository: {repo_path_str}",
        )
    return repo_path, None  # codeql[py/path-injection]


@router.post("/analyze", response_model=EvolutionAnalysisResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="trigger_evolution_analysis",
    error_code_prefix="ANALYTICS_EVOLUTION",
)
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

    from code_intelligence.code_evolution_miner import CodeEvolutionMiner

    start_time = time.time()

    try:
        repo_path, err = _validate_evolution_repo_path(request.repo_path)
        if err:
            return err

        # Parse dates
        start_date = parse_utc_iso(request.start_date) if request.start_date else None
        end_date = parse_utc_iso(request.end_date) if request.end_date else None

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
            message="Analysis failed",
            analysis_duration_seconds=round(time.time() - start_time, 2),
        )
