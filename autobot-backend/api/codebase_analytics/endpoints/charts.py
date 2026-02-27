# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chart data endpoints for analytics visualization
"""

import asyncio
import json
import logging
from typing import Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

from ..storage import get_code_collection, get_redis_connection

logger = logging.getLogger(__name__)

router = APIRouter()

# Issue #380: Module-level tuple for severity ordering in charts
_CHART_SEVERITY_ORDER = ("high", "medium", "low", "info", "hint")


def _try_chromadb_aggregation(
    code_collection,
    problem_types: Dict[str, int],
    severity_counts: Dict[str, int],
    race_conditions: Dict[str, int],
    file_problems: Dict[str, int],
) -> tuple[int, bool]:
    """
    Try to aggregate problem data from ChromaDB collection.

    Issue #665: Extracted from get_chart_data to reduce complexity.

    Returns:
        Tuple of (total_problems, success) where success indicates if aggregation worked.
    """
    if not code_collection:
        return 0, False

    try:
        results = code_collection.get(where={"type": "problem"}, include=["metadatas"])
        total = 0
        for metadata in results.get("metadatas", []):
            total += 1
            _aggregate_problem_data(
                metadata, problem_types, severity_counts, race_conditions, file_problems
            )
        logger.info("Aggregated chart data for %s problems", total)
        return total, True
    except Exception as chroma_error:
        logger.warning("ChromaDB query failed: %s", chroma_error)
        return 0, False


def _build_severity_chart_data(severity_counts: Dict[str, int]) -> list[dict]:
    """
    Build severity chart data with proper ordering.

    Issue #665: Extracted from get_chart_data.
    Issue #380: Uses module-level constant for severity ordering.

    Args:
        severity_counts: Dict mapping severity levels to counts

    Returns:
        List of dicts with 'severity' and 'count' fields in proper order
    """
    severity_data = []
    # Add severities in defined order
    for sev in _CHART_SEVERITY_ORDER:
        if sev in severity_counts:
            severity_data.append({"severity": sev, "count": severity_counts[sev]})
    # Add any unlisted severities at the end
    for sev, count in severity_counts.items():
        if sev not in _CHART_SEVERITY_ORDER:
            severity_data.append({"severity": sev, "count": count})
    return severity_data


def _build_chart_response(
    problem_types: Dict[str, int],
    severity_counts: Dict[str, int],
    race_conditions: Dict[str, int],
    file_problems: Dict[str, int],
    total_problems: int,
    storage_type: str,
) -> dict:
    """
    Build the final chart response dictionary.

    Issue #665: Extracted from get_chart_data.
    Issue #281: Uses _dict_to_chart_data helper for conversions.
    """
    return {
        "status": "success",
        "chart_data": {
            "problem_types": _dict_to_chart_data(problem_types, "type"),
            "severity_counts": _build_severity_chart_data(severity_counts),
            "race_conditions": _dict_to_chart_data(race_conditions, "category"),
            "top_files": _dict_to_chart_data(file_problems, "file", limit=15),
            "summary": {
                "total_problems": total_problems,
                "unique_problem_types": len(problem_types),
                "files_with_problems": len(file_problems),
                "race_condition_count": sum(race_conditions.values()),
            },
        },
        "storage_type": storage_type,
    }


def _aggregate_problem_data(
    metadata: dict,
    problem_types: Dict[str, int],
    severity_counts: Dict[str, int],
    race_conditions: Dict[str, int],
    file_problems: Dict[str, int],
) -> None:
    """Aggregate a single problem into chart data structures (Issue #315)."""
    # Aggregate by problem type
    ptype = metadata.get("problem_type") or metadata.get("type", "unknown")
    problem_types[ptype] = problem_types.get(ptype, 0) + 1

    # Aggregate by severity
    severity = metadata.get("severity", "low")
    severity_counts[severity] = severity_counts.get(severity, 0) + 1

    # Aggregate race conditions separately
    if "race" in ptype.lower() or "thread" in ptype.lower():
        race_conditions[ptype] = race_conditions.get(ptype, 0) + 1

    # Count problems per file
    file_path = metadata.get("file_path", "unknown")
    file_problems[file_path] = file_problems.get(file_path, 0) + 1


async def _aggregate_from_redis(
    redis_client,
    problem_types: Dict[str, int],
    severity_counts: Dict[str, int],
    race_conditions: Dict[str, int],
    file_problems: Dict[str, int],
) -> int:
    """Aggregate problem data from Redis.

    Issue #315: Extracted helper.
    Issue #361: Avoid blocking with asyncio.to_thread.
    Issue #561: Fixed N+1 query pattern - now uses pipeline batching.
    """

    def _scan_and_aggregate():
        # Issue #561: Collect all keys first, then batch fetch with pipeline
        keys = list(redis_client.scan_iter(match="codebase:problems:*"))
        if not keys:
            return 0

        # Batch fetch all values using pipeline (eliminates N+1 pattern)
        pipe = redis_client.pipeline()
        for key in keys:
            pipe.get(key)
        results = pipe.execute()

        total_problems = 0
        for problems_data in results:
            if not problems_data:
                continue
            problems = json.loads(problems_data)
            for problem in problems:
                total_problems += 1
                _aggregate_problem_data(
                    problem,
                    problem_types,
                    severity_counts,
                    race_conditions,
                    file_problems,
                )
        return total_problems

    return await asyncio.to_thread(_scan_and_aggregate)


def _dict_to_chart_data(
    data: Dict[str, int],
    key_name: str,
    limit: int = None,
    descending: bool = True,
) -> list[dict]:
    """
    Convert aggregation dict to chart-friendly list of dicts.

    Issue #281: Extracted helper to reduce repetition in get_chart_data.

    Args:
        data: Dict mapping keys to counts
        key_name: Name for key field in output dicts (e.g., 'type', 'severity')
        limit: Max items to return (None = all)
        descending: Sort by count descending (True) or ascending (False)

    Returns:
        List of dicts with key_name and 'count' fields, sorted by count
    """
    sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=descending)
    if limit:
        sorted_items = sorted_items[:limit]
    return [{key_name: key, "count": count} for key, count in sorted_items]


async def _get_redis_fallback_chart_data(
    problem_types: Dict[str, int],
    severity_counts: Dict[str, int],
    race_conditions: Dict[str, int],
    file_problems: Dict[str, int],
):
    """Helper for get_chart_data. Ref: #1088.

    Returns (total_problems, storage_type) or a JSONResponse on error/no-data.
    """
    redis_client = await get_redis_connection()
    if not redis_client:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "chart_data": None,
            }
        )
    try:
        total_problems = await _aggregate_from_redis(
            redis_client,
            problem_types,
            severity_counts,
            race_conditions,
            file_problems,
        )
        return total_problems, "redis"
    except Exception as redis_error:
        logger.error("Redis query failed: %s", redis_error)
        return JSONResponse(
            {
                "status": "error",
                "message": "Failed to retrieve chart data",
                "error": str(redis_error),
            },
            status_code=500,
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_chart_data",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/charts")
async def get_chart_data():
    """
    Get aggregated data for analytics charts.

    Issue #665: Refactored from 98 lines to use extracted helper methods.

    Returns data structures optimized for ApexCharts:
    - problem_types: Pie chart data for problem type distribution
    - severity_counts: Bar chart data for severity levels
    - race_conditions: Donut chart data for race condition categories
    - top_files: Horizontal bar chart for files with most problems
    - summary: Overall summary statistics
    """
    code_collection = await asyncio.to_thread(get_code_collection)
    problem_types: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    race_conditions: Dict[str, int] = {}
    file_problems: Dict[str, int] = {}

    # Try ChromaDB first (Issue #665: uses _try_chromadb_aggregation helper)
    total_problems, success = await asyncio.to_thread(
        _try_chromadb_aggregation,
        code_collection,
        problem_types,
        severity_counts,
        race_conditions,
        file_problems,
    )

    if success:
        storage_type = "chromadb"
    else:
        # Fallback to Redis if ChromaDB fails (Issue #1088: uses _get_redis_fallback_chart_data)
        result = await _get_redis_fallback_chart_data(
            problem_types, severity_counts, race_conditions, file_problems
        )
        if isinstance(result, JSONResponse):
            return result
        total_problems, storage_type = result

    # Build and return chart response (Issue #665: uses _build_chart_response helper)
    return JSONResponse(
        _build_chart_response(
            problem_types,
            severity_counts,
            race_conditions,
            file_problems,
            total_problems,
            storage_type,
        )
    )
