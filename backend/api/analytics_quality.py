# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Real-time Code Quality Dashboard API (Issue #230)

Provides endpoints for real-time code quality metrics, health scores,
pattern distribution, and quality trends.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["code-quality", "analytics"])  # Prefix set in router_registry


# ============================================================================
# Models
# ============================================================================


class QualityGrade(str, Enum):
    """Quality grades from A to F."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class MetricCategory(str, Enum):
    """Categories of quality metrics."""

    MAINTAINABILITY = "maintainability"
    RELIABILITY = "reliability"
    SECURITY = "security"
    PERFORMANCE = "performance"
    TESTABILITY = "testability"
    DOCUMENTATION = "documentation"


class QualityMetric(BaseModel):
    """Individual quality metric."""

    name: str
    category: MetricCategory
    value: float = Field(..., ge=0, le=100)
    grade: QualityGrade
    trend: float = Field(default=0, description="Percentage change from previous period")
    details: Optional[dict[str, Any]] = None


class HealthScore(BaseModel):
    """Overall codebase health score."""

    overall: float = Field(..., ge=0, le=100)
    grade: QualityGrade
    trend: float = Field(default=0)
    breakdown: dict[str, float] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class PatternDistribution(BaseModel):
    """Distribution of code patterns."""

    pattern_type: str
    count: int
    percentage: float
    severity: str
    examples: list[str] = Field(default_factory=list)


class ComplexityMetrics(BaseModel):
    """Code complexity analysis."""

    average_cyclomatic: float
    max_cyclomatic: int
    average_cognitive: float
    max_cognitive: int
    hotspots: list[dict[str, Any]] = Field(default_factory=list)
    distribution: dict[str, int] = Field(default_factory=dict)


class QualitySnapshot(BaseModel):
    """Complete quality snapshot at a point in time."""

    timestamp: datetime
    health_score: HealthScore
    metrics: list[QualityMetric]
    patterns: list[PatternDistribution]
    complexity: ComplexityMetrics
    file_count: int
    line_count: int
    issues_count: int


# ============================================================================
# Utility Functions
# ============================================================================


def get_grade(score: float) -> QualityGrade:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return QualityGrade.A
    if score >= 80:
        return QualityGrade.B
    if score >= 70:
        return QualityGrade.C
    if score >= 60:
        return QualityGrade.D
    return QualityGrade.F


def calculate_health_score(metrics: dict[str, float]) -> HealthScore:
    """Calculate overall health score from individual metrics."""
    weights = {
        "maintainability": 0.25,
        "reliability": 0.20,
        "security": 0.20,
        "performance": 0.15,
        "testability": 0.10,
        "documentation": 0.10,
    }

    weighted_sum = sum(
        metrics.get(category, 70) * weight for category, weight in weights.items()
    )

    overall = min(100, max(0, weighted_sum))
    grade = get_grade(overall)

    # Generate recommendations based on low scores
    recommendations = []
    for category, score in metrics.items():
        if score < 60:
            recommendations.append(
                f"Critical: Improve {category} (current score: {score:.1f})"
            )
        elif score < 70:
            recommendations.append(
                f"Warning: Address {category} issues (current score: {score:.1f})"
            )

    return HealthScore(
        overall=overall,
        grade=grade,
        trend=0,  # Will be calculated from historical data
        breakdown=metrics,
        recommendations=recommendations[:5],  # Top 5 recommendations
    )


async def get_quality_data_from_storage() -> dict[str, Any]:
    """Retrieve quality data from Redis or ChromaDB.

    Issue #541: Now calculates real quality metrics from actual analysis data
    instead of returning static demo values.
    """
    # First try Redis cache for pre-calculated metrics
    try:
        from src.utils.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if redis:
            # Issue #361 - avoid blocking
            data = await asyncio.to_thread(redis.get, "code_quality:latest")
            if data:
                cached = json.loads(data)
                # Only use cache if it has real data (not demo)
                if cached.get("source") == "calculated":
                    return cached
    except Exception as e:
        logger.warning("Failed to get quality data from Redis: %s", e)

    # Calculate real metrics from ChromaDB (Issue #541, #543)
    real_data = await calculate_real_quality_metrics()
    if real_data:
        # Cache the calculated data
        try:
            from src.utils.redis_client import get_redis_client

            redis = get_redis_client(async_client=False, database="analytics")
            if redis:
                real_data["source"] = "calculated"
                await asyncio.to_thread(
                    redis.setex,
                    "code_quality:latest",
                    300,  # 5 minute cache
                    json.dumps(real_data),
                )
        except Exception as e:
            logger.debug("Failed to cache quality data: %s", e)
        return real_data

    # Issue #543: Return None instead of demo data - endpoints handle no_data response
    return None


# ============================================================================
# Real Quality Metrics Calculation (Issue #541)
# ============================================================================


async def _get_problems_from_chromadb() -> tuple[list[dict], dict[str, Any]]:
    """
    Fetch problems and stats from ChromaDB.

    Returns:
        Tuple of (problems list, codebase stats dict)
    """
    problems = []
    stats = {}

    try:
        from backend.api.codebase_analytics.storage import get_code_collection_async

        collection = await get_code_collection_async()
        if not collection:
            return problems, stats

        # Fetch all problems
        results = await collection.get(
            where={"type": "problem"},
            include=["metadatas"],
        )
        if results and results.get("metadatas"):
            for metadata in results["metadatas"]:
                problems.append({
                    "type": metadata.get("problem_type", "unknown"),
                    "severity": metadata.get("severity", "low"),
                    "file_path": metadata.get("file_path", ""),
                    "description": metadata.get("description", ""),
                })

        # Fetch codebase stats
        stats_results = await collection.get(
            ids=["codebase_stats"],
            include=["metadatas"],
        )
        if stats_results and stats_results.get("metadatas"):
            stats = stats_results["metadatas"][0]

        logger.debug("Fetched %d problems from ChromaDB", len(problems))
    except Exception as e:
        logger.warning("Failed to fetch problems from ChromaDB: %s", e)

    return problems, stats


def _calculate_maintainability_score(
    problems: list[dict],
    total_files: int,
) -> float:
    """
    Calculate maintainability score based on problem density.

    Fewer problems per file = higher maintainability score.
    Score formula: 100 - (problem_count * severity_weight / total_files * 10)
    """
    if total_files == 0:
        return 75.0  # Default when no data

    severity_weights = {"high": 3.0, "medium": 1.5, "low": 0.5}

    # Filter for maintainability-related problems
    maintainability_types = {
        "long_function", "code_smell", "technical_debt", "complexity",
        "code_smell_god_class", "code_smell_long_method",
        "code_smell_duplicate_code", "code_smell_feature_envy",
    }

    weighted_problems = 0.0
    for problem in problems:
        problem_type = problem.get("type", "").lower()
        # Include general code smells and technical debt
        if any(mt in problem_type for mt in maintainability_types):
            severity = problem.get("severity", "low")
            weighted_problems += severity_weights.get(severity, 0.5)

    # Calculate score: fewer problems = higher score
    # Normalize by file count to handle different project sizes
    problem_density = weighted_problems / max(total_files, 1)
    score = 100.0 - (problem_density * 15.0)  # 15 points per problem per file

    return max(0.0, min(100.0, score))


def _calculate_reliability_score(problems: list[dict]) -> float:
    """
    Calculate reliability score based on error handling and bug prediction.

    Fewer reliability issues = higher score.
    """
    severity_weights = {"high": 5.0, "medium": 2.0, "low": 0.5}

    # Filter for reliability-related problems
    reliability_types = {
        "race_condition", "bug_prediction", "parse_error",
        "error_handling", "null_check", "exception",
    }

    weighted_problems = 0.0
    for problem in problems:
        problem_type = problem.get("type", "").lower()
        if any(rt in problem_type for rt in reliability_types):
            severity = problem.get("severity", "low")
            weighted_problems += severity_weights.get(severity, 0.5)

    # Base score of 95, reduced by reliability issues
    score = 95.0 - (weighted_problems * 2.0)

    return max(0.0, min(100.0, score))


def _calculate_security_score(problems: list[dict]) -> float:
    """
    Calculate security score based on security vulnerabilities and hardcoded values.

    Security issues heavily impact the score.
    """
    severity_weights = {"high": 10.0, "medium": 5.0, "low": 1.0}

    # Filter for security-related problems
    security_types = {
        "hardcode", "ip", "port", "url", "api_key", "secret",
        "race_condition", "security", "vulnerability", "injection",
    }

    weighted_problems = 0.0
    for problem in problems:
        problem_type = problem.get("type", "").lower()
        if any(st in problem_type for st in security_types):
            severity = problem.get("severity", "low")
            weighted_problems += severity_weights.get(severity, 1.0)

    # Base score of 100, heavily reduced by security issues
    score = 100.0 - (weighted_problems * 3.0)

    return max(0.0, min(100.0, score))


def _calculate_performance_score(problems: list[dict]) -> float:
    """
    Calculate performance score based on performance-related issues.
    """
    severity_weights = {"high": 4.0, "medium": 2.0, "low": 0.5}

    # Filter for performance-related problems
    performance_types = {
        "performance", "optimization", "complexity", "loop",
        "n_plus_one", "blocking", "async",
    }

    weighted_problems = 0.0
    for problem in problems:
        problem_type = problem.get("type", "").lower()
        if any(pt in problem_type for pt in performance_types):
            severity = problem.get("severity", "low")
            weighted_problems += severity_weights.get(severity, 0.5)

    # Base score of 90, reduced by performance issues
    score = 90.0 - (weighted_problems * 2.0)

    return max(0.0, min(100.0, score))


def _calculate_testability_score(
    stats: dict[str, Any],
    total_files: int,
) -> float:
    """
    Calculate testability score based on test file presence and complexity.

    Higher test coverage and simpler code = higher testability.
    """
    # Get test file count from stats
    test_files = int(stats.get("test_files", 0))

    if total_files == 0:
        return 65.0  # Default when no data

    # Calculate test file ratio
    test_ratio = test_files / total_files

    # Base score from test coverage (target: 20% of files should be tests)
    coverage_score = min(100.0, test_ratio * 500.0)  # 20% = 100 score

    # Adjust for code complexity (if available)
    avg_complexity = float(stats.get("average_cyclomatic", 0))
    if avg_complexity > 0:
        # Higher complexity = lower testability
        complexity_penalty = min(30.0, avg_complexity * 2.0)
        coverage_score -= complexity_penalty

    return max(0.0, min(100.0, coverage_score))


def _calculate_documentation_score(stats: dict[str, Any]) -> float:
    """
    Calculate documentation score based on docstring ratio.

    Uses actual docstring_ratio from codebase analysis.
    """
    # Get docstring ratio from stats
    docstring_ratio = stats.get("docstring_ratio", "0%")

    # Parse percentage string
    if isinstance(docstring_ratio, str):
        try:
            score = float(docstring_ratio.rstrip("%"))
        except (ValueError, AttributeError):
            score = 0.0
    else:
        score = float(docstring_ratio) * 100.0 if docstring_ratio < 1 else float(docstring_ratio)

    # Scale the score (target: 30% docstrings = 100% score)
    # This means 15% docstrings = 50% score
    scaled_score = min(100.0, score * 3.33)

    return max(0.0, min(100.0, scaled_score))


def _categorize_problems_for_patterns(
    problems: list[dict],
) -> list[dict[str, Any]]:
    """
    Categorize problems into pattern distribution for display.
    """
    # Count by type category
    categories = {
        "anti_pattern": {"count": 0, "severity": "high"},
        "code_smell": {"count": 0, "severity": "medium"},
        "best_practice": {"count": 0, "severity": "info"},
        "security_vulnerability": {"count": 0, "severity": "critical"},
        "performance_issue": {"count": 0, "severity": "high"},
        "technical_debt": {"count": 0, "severity": "medium"},
        "bug_risk": {"count": 0, "severity": "high"},
    }

    for problem in problems:
        problem_type = problem.get("type", "").lower()
        severity = problem.get("severity", "low")

        if "security" in problem_type or "hardcode" in problem_type:
            categories["security_vulnerability"]["count"] += 1
            if severity == "high":
                categories["security_vulnerability"]["severity"] = "critical"
        elif "performance" in problem_type:
            categories["performance_issue"]["count"] += 1
        elif "code_smell" in problem_type or "anti_pattern" in problem_type:
            if severity == "high":
                categories["anti_pattern"]["count"] += 1
            else:
                categories["code_smell"]["count"] += 1
        elif "technical_debt" in problem_type or "todo" in problem_type or "fixme" in problem_type:
            categories["technical_debt"]["count"] += 1
        elif "bug" in problem_type or "race" in problem_type:
            categories["bug_risk"]["count"] += 1
        else:
            # Default to code smell
            categories["code_smell"]["count"] += 1

    # Convert to list format
    patterns = [
        {"type": key, "count": val["count"], "severity": val["severity"]}
        for key, val in categories.items()
        if val["count"] > 0
    ]

    # Sort by count descending
    patterns.sort(key=lambda x: x["count"], reverse=True)

    return patterns


def _calculate_complexity_metrics(
    stats: dict[str, Any],
    problems: list[dict],
) -> dict[str, Any]:
    """
    Calculate complexity metrics from stats and problems.
    """
    # Extract complexity from stats
    avg_cyclomatic = float(stats.get("average_cyclomatic", 0)) or 4.0
    max_cyclomatic = int(stats.get("max_cyclomatic", 0)) or 20

    # Find complexity-related problems for hotspots
    hotspots = []
    seen_files = set()

    for problem in problems:
        problem_type = problem.get("type", "").lower()
        file_path = problem.get("file_path", "")

        if file_path in seen_files:
            continue

        if "complexity" in problem_type or "long_function" in problem_type:
            hotspots.append({
                "file": file_path,
                "complexity": max_cyclomatic,  # Estimate
                "lines": 0,  # Would need file analysis
            })
            seen_files.add(file_path)

    # Limit hotspots
    hotspots = hotspots[:10]

    return {
        "average_cyclomatic": avg_cyclomatic,
        "max_cyclomatic": max_cyclomatic,
        "average_cognitive": avg_cyclomatic * 1.5,  # Estimate
        "max_cognitive": max_cyclomatic * 1.5,
        "hotspots": hotspots,
    }


async def calculate_real_quality_metrics() -> Optional[dict[str, Any]]:
    """
    Calculate real quality metrics from ChromaDB analysis data.

    Issue #541: This replaces static demo values with actual calculated metrics.

    Returns:
        Dict with calculated quality metrics, or None if no data available
    """
    # Fetch data from ChromaDB
    problems, stats = await _get_problems_from_chromadb()

    # Issue #543: If no data, return None - endpoints will return no_data status
    if not problems and not stats:
        logger.info("No analysis data found in ChromaDB")
        return None

    # Get file counts
    total_files = int(stats.get("total_files", 0)) or 100  # Default estimate
    total_lines = int(stats.get("total_lines", 0)) or 10000

    # Calculate individual metrics
    maintainability = _calculate_maintainability_score(problems, total_files)
    reliability = _calculate_reliability_score(problems)
    security = _calculate_security_score(problems)
    performance = _calculate_performance_score(problems)
    testability = _calculate_testability_score(stats, total_files)
    documentation = _calculate_documentation_score(stats)

    logger.info(
        "Calculated quality metrics: maintainability=%.1f, reliability=%.1f, "
        "security=%.1f, performance=%.1f, testability=%.1f, documentation=%.1f",
        maintainability, reliability, security, performance, testability, documentation,
    )

    # Build patterns from problems
    patterns = _categorize_problems_for_patterns(problems)

    # Calculate complexity metrics
    complexity = _calculate_complexity_metrics(stats, problems)

    # Build trends (would need historical data, for now just current)
    trends = [
        {
            "date": (datetime.now() - timedelta(days=i)).isoformat(),
            "score": (maintainability * 0.25 + reliability * 0.20 + security * 0.20 +
                     performance * 0.15 + testability * 0.10 + documentation * 0.10),
        }
        for i in range(30, -1, -1)
    ]

    return {
        "metrics": {
            "maintainability": round(maintainability, 1),
            "reliability": round(reliability, 1),
            "security": round(security, 1),
            "performance": round(performance, 1),
            "testability": round(testability, 1),
            "documentation": round(documentation, 1),
        },
        "patterns": patterns,
        "complexity": complexity,
        "stats": {
            "file_count": total_files,
            "line_count": total_lines,
            "issues_count": len(problems),
        },
        "trends": trends,
        "source": "calculated",
        "calculated_at": datetime.now().isoformat(),
    }


def _no_data_response(message: str = "No analysis data. Run codebase indexing first.") -> dict:
    """
    Standardized no-data response for quality endpoints.

    Issue #543: Replaces demo data with proper no_data status.
    """
    return {
        "status": "no_data",
        "message": message,
        "metrics": {},
        "patterns": [],
        "complexity": {},
        "stats": {},
        "trends": [],
    }


# Issue #665: Category type mapping for drill-down filtering
_CATEGORY_TYPE_MAP: dict[str, set[str]] = {
    "maintainability": {"code_smell", "long_function", "complexity", "technical_debt"},
    "reliability": {"race_condition", "bug_prediction", "error_handling"},
    "security": {"hardcode", "ip", "port", "url", "security", "vulnerability"},
    "performance": {"performance", "optimization", "loop"},
    "testability": {"test_coverage", "complexity"},
    "documentation": {"missing_docstring", "documentation"},
}


def _filter_problems_by_category(
    problems: list[dict], category: str, severity: Optional[str]
) -> list[dict]:
    """
    Filter problems by category type and optional severity.

    Issue #665: Extracted from drill_down_category for clarity.

    Args:
        problems: List of problem dictionaries
        category: Quality category to filter by
        severity: Optional severity level filter

    Returns:
        Filtered list of problems matching criteria
    """
    target_types = _CATEGORY_TYPE_MAP.get(category.lower(), set())
    category_problems = [
        p for p in problems
        if any(t in p.get("type", "").lower() for t in target_types)
    ]

    if severity:
        category_problems = [p for p in category_problems if p.get("severity") == severity]

    return category_problems


def _group_problems_by_file(
    problems: list[dict], file_filter: Optional[str]
) -> dict[str, list[dict]]:
    """
    Group problems by file path with optional filtering.

    Issue #665: Extracted from drill_down_category for clarity.

    Args:
        problems: List of problem dictionaries
        file_filter: Optional file path substring filter

    Returns:
        Dictionary mapping file paths to their problems
    """
    file_issues: dict[str, list] = {}
    for problem in problems:
        file_path = problem.get("file_path", "unknown")
        if file_filter and file_filter.lower() not in file_path.lower():
            continue
        if file_path not in file_issues:
            file_issues[file_path] = []
        file_issues[file_path].append(problem)
    return file_issues


def _build_drill_down_file_results(file_issues: dict[str, list[dict]]) -> list[dict]:
    """
    Build result file list with calculated scores.

    Issue #665: Extracted from drill_down_category for clarity.

    Args:
        file_issues: Dictionary mapping file paths to their issues

    Returns:
        List of file result dictionaries with scores
    """
    result_files = []
    for file_path, issues in file_issues.items():
        issue_count = len(issues)
        high_count = sum(1 for i in issues if i.get("severity") == "high")
        score = max(0, 100 - (issue_count * 5) - (high_count * 10))

        top_issue = issues[0].get("description", "Quality issue") if issues else ""

        result_files.append({
            "path": file_path,
            "issues": issue_count,
            "score": score,
            "top_issue": top_issue[:100],
        })

    result_files.sort(key=lambda x: x["issues"], reverse=True)
    return result_files


def _build_quality_export_report(
    format_type: str, health: Any, metrics: dict, data: dict
) -> dict:
    """
    Build quality export report dictionary.

    Issue #665: Extracted from export_quality_report for clarity.

    Args:
        format_type: Export format (json, csv, pdf)
        health: HealthScore object with overall score and recommendations
        metrics: Quality metrics dictionary
        data: Full data dictionary with patterns, complexity, stats

    Returns:
        Report dictionary with all quality data
    """
    return {
        "generated_at": datetime.now().isoformat(),
        "format": format_type,
        "health_score": {
            "overall": health.overall,
            "grade": health.grade.value,
            "breakdown": health.breakdown,
        },
        "metrics": metrics,
        "patterns": data.get("patterns", []),
        "complexity": data.get("complexity", {}),
        "stats": data.get("stats", {}),
        "recommendations": health.recommendations,
    }


def _export_quality_as_csv(health: Any, metrics: dict) -> str:
    """
    Generate CSV content for quality report export.

    Issue #665: Extracted from export_quality_report for clarity.

    Args:
        health: HealthScore object with overall score
        metrics: Quality metrics dictionary

    Returns:
        CSV content as string
    """
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Section", "Metric", "Value", "Grade"])
    writer.writerow(
        ["Health", "Overall Score", f"{health.overall:.1f}", health.grade.value]
    )

    for cat, val in metrics.items():
        writer.writerow(
            ["Metrics", cat.replace("_", " ").title(), f"{val:.1f}", get_grade(val).value]
        )

    return output.getvalue()


# ============================================================================
# WebSocket Connection Manager
# ============================================================================


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        """Initialize connection manager with empty active connections list."""
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"WebSocket connected. Total connections: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """Remove disconnected WebSocket."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                f"WebSocket disconnected. Total connections: {len(self.active_connections)}"
            )

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# ============================================================================
# REST Endpoints
# ============================================================================


@router.get("/health-score")
async def get_health_score() -> dict[str, Any]:
    """
    Get current codebase health score with breakdown.

    Returns overall health score, grade, and recommendations.
    Issue #543: Returns no_data status when no analysis data available.
    """
    data = await get_quality_data_from_storage()

    # Issue #543: Handle no data case
    if data is None:
        return _no_data_response()

    metrics = data.get("metrics", {})
    if not metrics:
        return _no_data_response()

    health = calculate_health_score(metrics)

    return {
        "status": "success",
        "overall": health.overall,
        "grade": health.grade.value,
        "trend": health.trend,
        "breakdown": health.breakdown,
        "recommendations": health.recommendations,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/metrics")
async def get_quality_metrics(
    category: Optional[MetricCategory] = Query(None, description="Filter by category"),
) -> dict[str, Any]:
    """
    Get all quality metrics or filter by category.

    Returns detailed metrics with grades and trends.
    Issue #543: Returns no_data status when no analysis data available.
    """
    data = await get_quality_data_from_storage()

    # Issue #543: Handle no data case
    if data is None:
        return _no_data_response()

    raw_metrics = data.get("metrics", {})
    if not raw_metrics:
        return _no_data_response()

    metrics = []
    for cat, value in raw_metrics.items():
        try:
            metric_cat = MetricCategory(cat)
            if category and metric_cat != category:
                continue

            metrics.append(
                {
                    "name": cat.replace("_", " ").title(),
                    "category": cat,
                    "value": value,
                    "grade": get_grade(value).value,
                    "trend": 0,  # Would be calculated from historical data
                    "weight": {
                        "maintainability": 0.25,
                        "reliability": 0.20,
                        "security": 0.20,
                        "performance": 0.15,
                        "testability": 0.10,
                        "documentation": 0.10,
                    }.get(cat, 0.1),
                }
            )
        except ValueError:
            continue

    return {"status": "success", "metrics": sorted(metrics, key=lambda x: x["value"], reverse=True)}


@router.get("/patterns")
async def get_pattern_distribution(
    severity: Optional[str] = Query(None, description="Filter by severity"),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """
    Get distribution of code patterns detected in the codebase.

    Returns pattern types with counts, percentages, and severity.
    Issue #543: Returns no_data status when no analysis data available.
    """
    data = await get_quality_data_from_storage()

    # Issue #543: Handle no data case
    if data is None:
        return _no_data_response()

    patterns = data.get("patterns", [])

    if severity:
        patterns = [p for p in patterns if p.get("severity") == severity]

    total = sum(p.get("count", 0) for p in patterns)

    result = []
    for pattern in patterns[:limit]:
        count = pattern.get("count", 0)
        result.append(
            {
                "type": pattern.get("type", "unknown"),
                "display_name": pattern.get("type", "").replace("_", " ").title(),
                "count": count,
                "percentage": (count / total * 100) if total > 0 else 0,
                "severity": pattern.get("severity", "info"),
                "icon": {
                    "anti_pattern": "warning",
                    "code_smell": "smell",
                    "best_practice": "check",
                    "security_vulnerability": "shield",
                    "performance_issue": "speed",
                }.get(pattern.get("type", ""), "info"),
            }
        )

    return {"status": "success", "patterns": result}


@router.get("/complexity")
async def get_complexity_metrics(
    top_n: int = Query(10, ge=1, le=50, description="Number of hotspots to return"),
) -> dict[str, Any]:
    """
    Get code complexity analysis with hotspots.

    Returns cyclomatic and cognitive complexity metrics.
    Issue #543: Returns no_data status when no analysis data available.
    """
    data = await get_quality_data_from_storage()

    # Issue #543: Handle no data case
    if data is None:
        return _no_data_response()

    complexity = data.get("complexity", {})

    # Calculate complexity distribution
    distribution = {
        "low": 0,  # 1-5
        "moderate": 0,  # 6-10
        "high": 0,  # 11-20
        "very_high": 0,  # 21+
    }

    # In real implementation, this would aggregate from all files
    hotspots = complexity.get("hotspots", [])[:top_n]

    return {
        "averages": {
            "cyclomatic": complexity.get("average_cyclomatic", 0),
            "cognitive": complexity.get("average_cognitive", 0),
        },
        "maximums": {
            "cyclomatic": complexity.get("max_cyclomatic", 0),
            "cognitive": complexity.get("max_cognitive", 0),
        },
        "hotspots": [
            {
                "file": h.get("file", ""),
                "complexity": h.get("complexity", 0),
                "lines": h.get("lines", 0),
                "recommendation": "Consider refactoring this file"
                if h.get("complexity", 0) > 15
                else "Monitor complexity",
            }
            for h in hotspots
        ],
        "distribution": distribution,
        "threshold_warnings": {
            "cyclomatic_warning": 10,
            "cyclomatic_critical": 20,
            "cognitive_warning": 15,
            "cognitive_critical": 25,
        },
        "status": "success",
    }


@router.get("/trends")
async def get_quality_trends(
    period: str = Query("30d", regex="^(7d|14d|30d|90d)$"),
    metric: Optional[str] = Query(None, description="Specific metric to trend"),
) -> dict[str, Any]:
    """
    Get quality score trends over time.

    Returns historical data for trend analysis.
    Issue #543: Returns no_data status when no analysis data available.
    """
    data = await get_quality_data_from_storage()

    # Issue #543: Handle no data case
    if data is None:
        return _no_data_response()

    trends = data.get("trends", [])

    # Filter by period
    days = int(period[:-1])
    cutoff = datetime.now() - timedelta(days=days)

    filtered_trends = []
    for t in trends:
        try:
            date = datetime.fromisoformat(t.get("date", ""))
            if date >= cutoff:
                filtered_trends.append(t)
        except (ValueError, TypeError):
            continue

    # Calculate trend statistics
    scores = [t.get("score", 0) for t in filtered_trends]

    if scores:
        current = scores[-1] if scores else 0
        previous = scores[0] if scores else 0
        change = ((current - previous) / previous * 100) if previous > 0 else 0

        stats = {
            "current": current,
            "previous": previous,
            "change": change,
            "direction": "up" if change > 0 else "down" if change < 0 else "stable",
            "average": sum(scores) / len(scores),
            "min": min(scores),
            "max": max(scores),
        }
    else:
        stats = {
            "current": 0,
            "previous": 0,
            "change": 0,
            "direction": "stable",
            "average": 0,
            "min": 0,
            "max": 0,
        }

    return {
        "status": "success",
        "period": period,
        "data_points": filtered_trends,
        "statistics": stats,
        "metric": metric or "overall",
    }


@router.get("/snapshot")
async def get_quality_snapshot() -> dict[str, Any]:
    """
    Get complete quality snapshot for the current state.

    Returns all metrics, patterns, and statistics in one response.
    Issue #543: Returns no_data status when no analysis data available.
    """
    data = await get_quality_data_from_storage()

    # Issue #543: Handle no data case
    if data is None:
        return _no_data_response()

    metrics = data.get("metrics", {})
    if not metrics:
        return _no_data_response()

    health = calculate_health_score(metrics)
    patterns = data.get("patterns", [])
    complexity = data.get("complexity", {})
    stats = data.get("stats", {})

    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "health_score": {
            "overall": health.overall,
            "grade": health.grade.value,
            "breakdown": health.breakdown,
        },
        "metrics": [
            {
                "category": cat,
                "value": val,
                "grade": get_grade(val).value,
            }
            for cat, val in metrics.items()
        ],
        "patterns_summary": {
            "total": sum(p.get("count", 0) for p in patterns),
            "critical": sum(
                p.get("count", 0)
                for p in patterns
                if p.get("severity") == "critical"
            ),
            "high": sum(
                p.get("count", 0) for p in patterns if p.get("severity") == "high"
            ),
        },
        "complexity_summary": {
            "avg_cyclomatic": complexity.get("average_cyclomatic", 0),
            "max_cyclomatic": complexity.get("max_cyclomatic", 0),
            "hotspot_count": len(complexity.get("hotspots", [])),
        },
        "codebase_stats": {
            "files": stats.get("file_count", 0),
            "lines": stats.get("line_count", 0),
            "issues": stats.get("issues_count", 0),
        },
    }


@router.get("/drill-down/{category}")
async def drill_down_category(
    category: str,
    file_filter: Optional[str] = Query(None, description="Filter by file path"),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """
    Drill down into a specific quality category.

    Returns detailed issues and files for the category.
    Issue #543: Now queries real ChromaDB data instead of demo data.
    Issue #665: Refactored using helper functions for clarity.
    """
    problems, stats = await _get_problems_from_chromadb()

    if not problems:
        return _no_data_response("No analysis data for category drill-down.")

    # Issue #665: Use extracted helper functions
    category_problems = _filter_problems_by_category(problems, category, severity)
    file_issues = _group_problems_by_file(category_problems, file_filter)
    result_files = _build_drill_down_file_results(file_issues)

    return {
        "status": "success",
        "category": category,
        "display_name": category.replace("_", " ").title(),
        "total_files": len(result_files),
        "total_issues": sum(f["issues"] for f in result_files),
        "average_score": sum(f["score"] for f in result_files) / len(result_files)
        if result_files
        else 0,
        "files": result_files[:limit],
        "filters_applied": {
            "file": file_filter,
            "severity": severity,
        },
    }


@router.get("/export")
async def export_quality_report(
    format: str = Query("json", regex="^(json|csv|pdf)$"),
) -> JSONResponse:
    """
    Export quality report in specified format.

    Supports JSON, CSV, and PDF formats.
    Issue #543: Returns no_data status when no analysis data available.
    Issue #665: Refactored using helper functions for clarity.
    """
    data = await get_quality_data_from_storage()

    if data is None:
        return JSONResponse(content=_no_data_response())

    metrics = data.get("metrics", {})
    if not metrics:
        return JSONResponse(content=_no_data_response())

    health = calculate_health_score(metrics)

    # Issue #665: Use extracted helper functions
    if format == "json":
        report = _build_quality_export_report(format, health, metrics, data)
        return JSONResponse(content=report)
    elif format == "csv":
        csv_content = _export_quality_as_csv(health, metrics)
        return JSONResponse(
            content={"format": "csv", "content": csv_content},
            media_type="application/json",
        )
    else:
        return JSONResponse(
            content={"error": "PDF export not yet implemented", "format": format},
            status_code=501,
        )


# ============================================================================
# WebSocket Endpoint
# ============================================================================


async def _handle_ws_subscribe(websocket: WebSocket, data: dict) -> None:
    """Handle WebSocket subscribe message (Issue #315: extracted)."""
    await websocket.send_json({"type": "subscribed", "metrics": data.get("metrics", [])})


async def _handle_ws_refresh(websocket: WebSocket, data: dict) -> None:
    """Handle WebSocket refresh message (Issue #315: extracted)."""
    snapshot = await get_quality_snapshot()
    await websocket.send_json({"type": "snapshot", "data": snapshot})


async def _handle_ws_ping(websocket: WebSocket, data: dict) -> None:
    """Handle WebSocket ping message (Issue #315: extracted)."""
    await websocket.send_json({"type": "pong"})


# WebSocket message handlers (Issue #315: dictionary dispatch pattern)
_WS_MESSAGE_HANDLERS = {
    "subscribe": _handle_ws_subscribe,
    "refresh": _handle_ws_refresh,
    "ping": _handle_ws_ping,
}


@router.websocket("/ws")
async def websocket_quality_updates(websocket: WebSocket):
    """
    WebSocket endpoint for real-time quality updates.

    Clients receive updates when quality metrics change.
    Issue #315: Refactored to use dictionary dispatch for message handling.
    """
    await manager.connect(websocket)

    # Send initial snapshot
    try:
        snapshot = await get_quality_snapshot()
        await websocket.send_json({"type": "snapshot", "data": snapshot})

        # Keep connection alive and handle incoming messages
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)

                # Handle message using dispatch pattern (Issue #315)
                msg_type = data.get("type")
                handler = _WS_MESSAGE_HANDLERS.get(msg_type)
                if handler:
                    await handler(websocket, data)

            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        manager.disconnect(websocket)


# ============================================================================
# Broadcast Function (for use by other modules)
# ============================================================================


async def broadcast_quality_update(update_type: str, data: dict):
    """
    Broadcast quality update to all connected WebSocket clients.

    Called by indexer or analysis modules when quality changes.
    """
    await manager.broadcast(
        {
            "type": update_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }
    )
