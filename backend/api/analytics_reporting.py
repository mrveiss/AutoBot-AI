# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Analytics Report API (Issue #271)

Provides a single endpoint that aggregates all analytics data from:
- Code quality health score
- Codebase analytics (problems, severity)
- Technical debt
- Performance patterns
- Bug predictions
"""

import logging
from datetime import datetime
from typing import Any, Dict

import aiohttp
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/unified", tags=["unified-analytics"])


async def fetch_quality_health() -> Dict[str, Any]:
    """Fetch quality health score data via HTTP."""
    try:
        from src.constants.network_constants import ServiceURLs

        backend_url = ServiceURLs.BACKEND_API
        # Use singleton HTTP client (Issue #65 P1: 60-80% overhead reduction)
        http_client = get_http_client()
        async with await http_client.get(
            f"{backend_url}/api/quality/health-score",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                logger.warning("Quality endpoint returned %s", response.status)
                return {"overall": 0, "grade": "N/A", "breakdown": {}}
    except Exception as e:
        logger.warning("Failed to fetch quality health: %s", e)
        return {"overall": 0, "grade": "N/A", "breakdown": {}}


async def fetch_codebase_charts() -> Dict[str, Any]:
    """Fetch codebase analytics chart data via HTTP."""
    try:
        import aiohttp

        from src.constants.network_constants import ServiceURLs

        backend_url = ServiceURLs.BACKEND_API
        # Use singleton HTTP client (Issue #65 P1: 60-80% overhead reduction)
        http_client = get_http_client()
        async with await http_client.get(
            f"{backend_url}/api/analytics/codebase/analytics/charts",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                logger.warning("Charts endpoint returned %s", response.status)
                return {
                    "chart_data": {
                        "problem_types": [],
                        "severity_counts": [],
                        "top_files": [],
                    }
                }
    except Exception as e:
        logger.warning("Failed to fetch codebase charts: %s", e)
        return {
            "chart_data": {"problem_types": [], "severity_counts": [], "top_files": []}
        }


async def fetch_debt_summary() -> Dict[str, Any]:
    """Fetch technical debt summary via HTTP."""
    try:
        import aiohttp

        from src.constants.network_constants import ServiceURLs

        backend_url = ServiceURLs.BACKEND_API
        # Use singleton HTTP client (Issue #65 P1: 60-80% overhead reduction)
        http_client = get_http_client()
        async with await http_client.get(
            f"{backend_url}/api/debt/summary",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                logger.warning("Debt endpoint returned %s", response.status)
                return {"summary": {"total_items": 0, "total_hours": 0}}
    except Exception as e:
        logger.warning("Failed to fetch debt summary: %s", e)
        return {"summary": {"total_items": 0, "total_hours": 0}}


async def fetch_performance_summary() -> Dict[str, Any]:
    """Fetch performance analysis summary via HTTP."""
    try:
        import aiohttp

        from src.constants.network_constants import ServiceURLs

        backend_url = ServiceURLs.BACKEND_API
        # Use singleton HTTP client (Issue #65 P1: 60-80% overhead reduction)
        http_client = get_http_client()
        async with await http_client.get(
            f"{backend_url}/api/performance/summary",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                logger.warning("Performance endpoint returned %s", response.status)
                return {"total_analyses": 0, "average_score": 0, "common_issues": []}
    except Exception as e:
        logger.warning("Failed to fetch performance summary: %s", e)
        return {"total_analyses": 0, "average_score": 0, "common_issues": []}


def calculate_unified_health_score(
    quality_data: Dict[str, Any],
    charts_data: Dict[str, Any],
    debt_data: Dict[str, Any],
    performance_data: Dict[str, Any],
) -> float:
    """
    Calculate unified health score from all sources.

    Weights:
    - Quality score: 40%
    - Issues impact: 30% (fewer issues = higher score)
    - Technical debt: 15%
    - Performance: 15%
    """
    # Quality component (40%)
    quality_score = quality_data.get("overall", 0)
    quality_component = quality_score * 0.4

    # Issues impact component (30%)
    chart_data = charts_data.get("chart_data", {})
    severity_counts = chart_data.get("severity_counts", [])

    total_issues = sum(s.get("count", 0) for s in severity_counts)
    # Normalize: 0 issues = 100, 1000+ issues = 0
    issues_score = max(0, 100 - (total_issues / 10))
    issues_component = issues_score * 0.3

    # Technical debt component (15%)
    debt_summary = debt_data.get("summary", {})
    debt_hours = debt_summary.get("total_hours", 0)
    # Normalize: 0 hours = 100, 100+ hours = 0
    debt_score = max(0, 100 - debt_hours)
    debt_component = debt_score * 0.15

    # Performance component (15%)
    perf_score = performance_data.get("average_score", 0)
    if perf_score == 0:
        # Use quality performance breakdown if no performance analysis
        perf_score = quality_data.get("breakdown", {}).get("performance", 70)
    perf_component = perf_score * 0.15

    return round(
        quality_component + issues_component + debt_component + perf_component, 1
    )


def get_grade(score: float) -> str:
    """Convert score to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


def _get_problem_category_mapping() -> list:
    """Get problem type keyword to category mapping (Issue #315)."""
    return [
        (("race",), "race_conditions"),
        (("debug", "print"), "debug_code"),
        (("long", "complex"), "complexity"),
        (("smell",), "code_smells"),
        (("perf",), "performance"),
        (("security",), "security"),
    ]


def _categorize_problem_type(problem_type: str) -> str:
    """Categorize a problem type (Issue #315)."""
    for keywords, category in _get_problem_category_mapping():
        if any(kw in problem_type for kw in keywords):
            return category
    return problem_type


def aggregate_categories(charts_data: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate issues by category (Issue #315 - reduced nesting)."""
    chart_data = charts_data.get("chart_data", {})
    problem_types = chart_data.get("problem_types", [])

    categories = {}
    for problem in problem_types:
        problem_type = problem.get("type", "unknown")
        count = problem.get("count", 0)

        # Map problem types to categories (Issue #315 - extracted)
        category = _categorize_problem_type(problem_type)

        if category not in categories:
            categories[category] = {"count": 0, "items": []}

        categories[category]["count"] += count
        categories[category]["items"].append({"type": problem_type, "count": count})

    return categories


@with_error_handling(
    category=ErrorCategory.API,
    error_code_prefix="UNIFIED",
)
@router.get("/report")
async def get_unified_report():
    """
    Get unified analytics report aggregating all analytics sources.

    Returns comprehensive code health overview including:
    - Overall health score
    - Issue summary by severity
    - Category breakdowns
    - Top problematic files
    - Quality breakdown
    - Recommendations
    """
    import asyncio

    # Fetch all data sources in parallel
    quality_data, charts_data, debt_data, performance_data = await asyncio.gather(
        fetch_quality_health(),
        fetch_codebase_charts(),
        fetch_debt_summary(),
        fetch_performance_summary(),
    )

    # Calculate unified health score
    health_score = calculate_unified_health_score(
        quality_data, charts_data, debt_data, performance_data
    )

    # Extract chart data
    chart_data = charts_data.get("chart_data", {})
    severity_counts = chart_data.get("severity_counts", [])
    top_files = chart_data.get("top_files", [])

    # Calculate totals by severity
    severity_totals = {s["severity"]: s["count"] for s in severity_counts}
    total_issues = sum(severity_totals.values())

    # Aggregate categories
    categories = aggregate_categories(charts_data)

    # Build response
    response = {
        "status": "success",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "health_score": health_score,
            "grade": get_grade(health_score),
            "total_issues": total_issues,
            "critical": severity_totals.get("critical", 0),
            "high": severity_totals.get("high", 0),
            "medium": severity_totals.get("medium", 0),
            "low": severity_totals.get("low", 0),
        },
        "quality": {
            "overall": quality_data.get("overall", 0),
            "grade": quality_data.get("grade", "N/A"),
            "breakdown": quality_data.get("breakdown", {}),
            "recommendations": quality_data.get("recommendations", []),
        },
        "categories": categories,
        "top_files": top_files[:10],  # Top 10 problematic files
        "technical_debt": {
            "total_items": debt_data.get("summary", {}).get("total_items", 0),
            "total_hours": debt_data.get("summary", {}).get("total_hours", 0),
            "total_cost_usd": debt_data.get("summary", {}).get("total_cost_usd", 0),
        },
        "performance": {
            "analyses_count": performance_data.get("total_analyses", 0),
            "average_score": performance_data.get("average_score", 0),
            "patterns_enabled": performance_data.get("patterns_enabled", 0),
            "common_issues": performance_data.get("common_issues", [])[:5],
        },
    }

    return JSONResponse(content=response)


@with_error_handling(
    category=ErrorCategory.API,
    error_code_prefix="UNIFIED",
)
@router.get("/summary")
async def get_quick_summary():
    """
    Get a quick summary of code health.

    Lightweight endpoint for dashboard cards.
    """
    import asyncio

    # Fetch essential data
    quality_data, charts_data = await asyncio.gather(
        fetch_quality_health(),
        fetch_codebase_charts(),
    )

    chart_data = charts_data.get("chart_data", {})
    severity_counts = chart_data.get("severity_counts", [])
    severity_totals = {s["severity"]: s["count"] for s in severity_counts}
    total_issues = sum(severity_totals.values())

    return JSONResponse(
        content={
            "health_score": quality_data.get("overall", 0),
            "grade": quality_data.get("grade", "N/A"),
            "total_issues": total_issues,
            "high_priority": severity_totals.get("high", 0)
            + severity_totals.get("critical", 0),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )


@with_error_handling(
    category=ErrorCategory.API,
    error_code_prefix="UNIFIED",
)
@router.get("/trends")
async def get_trends():
    """
    Get analytics trends over time.

    Note: Returns no_data status as trend storage requires historical snapshots.
    """
    return JSONResponse(
        content={
            "status": "no_data",
            "message": "Trend data requires historical snapshots.",
            "data": [],
        }
    )
