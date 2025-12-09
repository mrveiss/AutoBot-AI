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

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from ..storage import get_redis_connection, get_code_collection

logger = logging.getLogger(__name__)

router = APIRouter()

# Issue #380: Module-level tuple for severity ordering in charts
_CHART_SEVERITY_ORDER = ("high", "medium", "low", "info", "hint")


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
    """Aggregate problem data from Redis (Issue #315 - extracted helper)."""
    # Issue #361 - avoid blocking
    def _scan_and_aggregate():
        total_problems = 0
        for key in redis_client.scan_iter(match="codebase:problems:*"):
            problems_data = redis_client.get(key)
            if not problems_data:
                continue
            problems = json.loads(problems_data)
            for problem in problems:
                total_problems += 1
                _aggregate_problem_data(
                    problem, problem_types, severity_counts, race_conditions, file_problems
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_chart_data",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/charts")
async def get_chart_data():
    """
    Get aggregated data for analytics charts.

    Returns data structures optimized for ApexCharts:
    - problem_types: Pie chart data for problem type distribution
    - severity_counts: Bar chart data for severity levels
    - race_conditions: Donut chart data for race condition categories
    - top_files: Horizontal bar chart for files with most problems
    - summary: Overall summary statistics
    """
    code_collection = get_code_collection()

    # Initialize aggregation containers
    problem_types: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    race_conditions: Dict[str, int] = {}
    file_problems: Dict[str, int] = {}
    total_problems = 0

    # Try ChromaDB first (Issue #315: refactored depth 7→3)
    if code_collection:
        try:
            results = code_collection.get(
                where={"type": "problem"}, include=["metadatas"]
            )
            for metadata in results.get("metadatas", []):
                total_problems += 1
                _aggregate_problem_data(
                    metadata, problem_types, severity_counts, race_conditions, file_problems
                )
            storage_type = "chromadb"
            logger.info(f"Aggregated chart data for {total_problems} problems")
        except Exception as chroma_error:
            logger.warning(f"ChromaDB query failed: {chroma_error}")
            code_collection = None

    # Fallback to Redis if ChromaDB fails
    if not code_collection:
        redis_client = await get_redis_connection()
        if not redis_client:
            return JSONResponse({
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "chart_data": None,
            })

        try:
            total_problems = await _aggregate_from_redis(
                redis_client, problem_types, severity_counts, race_conditions, file_problems
            )
            storage_type = "redis"
        except Exception as redis_error:
            logger.error(f"Redis query failed: {redis_error}")
            return JSONResponse(
                {"status": "error", "message": "Failed to retrieve chart data", "error": str(redis_error)},
                status_code=500,
            )

    # Convert to chart-friendly format (Issue #281: uses _dict_to_chart_data helper)

    # Problem types for pie chart (sorted by count descending)
    problem_types_data = _dict_to_chart_data(problem_types, "type")

    # Severity for bar chart (Issue #380: use module-level constant for ordering)
    severity_data = []
    for sev in _CHART_SEVERITY_ORDER:
        if sev in severity_counts:
            severity_data.append({"severity": sev, "count": severity_counts[sev]})
    # Add any unlisted severities
    for sev, count in severity_counts.items():
        if sev not in _CHART_SEVERITY_ORDER:
            severity_data.append({"severity": sev, "count": count})

    # Race conditions for donut chart
    race_conditions_data = _dict_to_chart_data(race_conditions, "category")

    # Top files for horizontal bar chart (top 15)
    top_files_data = _dict_to_chart_data(file_problems, "file", limit=15)

    return JSONResponse(
        {
            "status": "success",
            "chart_data": {
                "problem_types": problem_types_data,
                "severity_counts": severity_data,
                "race_conditions": race_conditions_data,
                "top_files": top_files_data,
                "summary": {
                    "total_problems": total_problems,
                    "unique_problem_types": len(problem_types),
                    "files_with_problems": len(file_problems),
                    "race_condition_count": sum(race_conditions.values()),
                },
            },
            "storage_type": storage_type,
        }
    )
