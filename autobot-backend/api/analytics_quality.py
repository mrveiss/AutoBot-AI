# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Real-time Code Quality Dashboard API (Issue #230)

Provides endpoints for real-time code quality metrics, health scores,
pattern distribution, and quality trends.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from api.analytics_shared import resolve_source_root_or_404 as _resolve_source_root_or_404
from api.schemas_analytics import (
    AnalyticsQualityExportData,
    HealthScore,
    MetricCategory,
    QualityComplexityResponse,
    QualityDrillDownResponse,
    QualityGrade,
    QualityHealthScoreResponse,
    QualityMetricsResponse,
    QualityPatternsResponse,
    QualitySnapshotResponse,
    QualityTrendsResponse,
)
from api.schemas_common import DataResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import parse_utc_iso

logger = get_logger(__name__)

router = APIRouter(tags=["code-quality", "analytics"])  # Prefix set in router_registry


# ============================================================================
# Models
# ============================================================================


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

    weighted_sum = sum(metrics.get(category, 70) * weight for category, weight in weights.items())

    overall = min(100, max(0, weighted_sum))
    grade = get_grade(overall)

    # Generate recommendations based on low scores
    recommendations = []
    for category, score in metrics.items():
        if score < 60:
            recommendations.append(f"Critical: Improve {category} (current score: {score:.1f})")
        elif score < 70:
            recommendations.append(f"Warning: Address {category} issues (current score: {score:.1f})")

    return HealthScore(
        overall=overall,
        grade=grade,
        trend=0,  # Will be calculated from historical data
        breakdown=metrics,
        recommendations=recommendations[:5],  # Top 5 recommendations
    )


async def get_quality_data_from_storage(
    source_root: "Path" | None = None,
    source_id: str | None = None,
) -> dict[str, Any]:
    """Retrieve quality data from Redis or ChromaDB.

    Issue #541: Now calculates real quality metrics from actual analysis data
    instead of returning static demo values.
    Issue #3441: Accepts optional source_root to scope results to a project
    directory.  When provided, all problem file paths are checked to confirm
    they reside under source_root before contributing to metrics.  The Redis
    cache key is namespaced by the resolved path so per-project results are
    stored independently.
    Issue #6670: Accepts optional source_id used to look up per-source
    codebase_stats from ChromaDB; without it, per-source dashboards always
    fell back to the global stats document and returned no_data.

    Args:
        source_root: Absolute path to the project clone directory, or None
                     for global (unscoped) results.
        source_id:   Project source ID for per-source ChromaDB stats lookup.
    """
    # Derive a stable cache key suffix from the resolved path (if scoped)
    cache_suffix = f":{source_root}" if source_root else ""
    cache_key = f"code_quality:latest{cache_suffix}"

    # First try Redis cache for pre-calculated metrics
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if redis:
            # Issue #361 - avoid blocking
            data = await asyncio.to_thread(redis.get, cache_key)
            if data:
                cached = json.loads(data)
                # Only use cache if it has real data (not demo)
                if cached.get("source") == "calculated":
                    return cached
    except Exception as e:
        logger.warning("Failed to get quality data from Redis: %s", e)

    # Calculate real metrics from ChromaDB (Issue #541, #543, #6670)
    real_data = await calculate_real_quality_metrics(source_root=source_root, source_id=source_id)
    if real_data:
        # Cache the calculated data
        try:
            from autobot_shared.redis_client import get_redis_client

            redis = get_redis_client(async_client=False, database="analytics")
            if redis:
                real_data["source"] = "calculated"
                await asyncio.to_thread(
                    redis.setex,
                    cache_key,
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


async def _get_problems_from_chromadb(
    source_root: "Path" | None = None,
    source_id: str | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Fetch problems and stats from ChromaDB.

    Issue #3441: When source_root is provided, only problems whose file_path
    resolves to a path under source_root are included.  This scopes quality
    metrics to the selected project's files only.

    Issue #6670: When source_id is provided, the codebase_stats document is
    looked up under the per-source key ``codebase_stats_{source_id}`` first,
    falling back to the global ``codebase_stats`` document. This matches the
    write path in chromadb_storage.py:649 and the read pattern already used
    by sources.py:447-456 and stats.py:222.

    Args:
        source_root: Absolute path used to filter problem file paths.  Pass
                     None to return all problems regardless of location.
        source_id:   Optional project source ID used to look up per-source
                     codebase_stats.  Pass None for the global stats key.

    Returns:
        Tuple of (problems list, codebase stats dict)
    """
    problems = []
    stats = {}

    try:
        from api.codebase_analytics.storage import get_code_collection_async

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
                file_path = metadata.get("file_path", "")
                # Issue #3441: filter to source_root when provided
                if source_root is not None and file_path:
                    candidate = (source_root / file_path).resolve()
                    try:
                        candidate.relative_to(source_root.resolve())
                    except ValueError:
                        continue
                problems.append(
                    {
                        "type": metadata.get("problem_type", "unknown"),
                        "severity": metadata.get("severity", "low"),
                        "file_path": file_path,
                        "description": metadata.get("description", ""),
                    }
                )

        # Fetch codebase stats — per-source key first, fall back to global (#6670, #1716)
        stats_results = None
        if source_id:
            stats_results = await collection.get(
                ids=[f"codebase_stats_{source_id}"],
                include=["metadatas"],
            )
        if not stats_results or not stats_results.get("metadatas"):
            stats_results = await collection.get(
                ids=["codebase_stats"],
                include=["metadatas"],
            )
        if stats_results and stats_results.get("metadatas"):
            stats = stats_results["metadatas"][0]

        logger.debug(
            "Fetched %d problems from ChromaDB (source_root=%s, source_id=%s)",
            len(problems),
            source_root,
            source_id,
        )
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
        "long_function",
        "code_smell",
        "technical_debt",
        "complexity",
        "code_smell_god_class",
        "code_smell_long_method",
        "code_smell_duplicate_code",
        "code_smell_feature_envy",
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
        "race_condition",
        "bug_prediction",
        "parse_error",
        "error_handling",
        "null_check",
        "exception",
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
        "hardcode",
        "ip",
        "port",
        "url",
        "api_key",
        "secret",
        "race_condition",
        "security",
        "vulnerability",
        "injection",
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
        "performance",
        "optimization",
        "complexity",
        "loop",
        "n_plus_one",
        "blocking",
        "async",
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
            hotspots.append(
                {
                    "file": file_path,
                    "complexity": max_cyclomatic,  # Estimate
                    "lines": 0,  # Would need file analysis
                }
            )
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


def _build_quality_trends(metrics: dict[str, float], days: int = 30) -> list[dict]:
    """
    Build quality trend data for the specified number of days.

    Issue #620: Extracted from calculate_real_quality_metrics to reduce function length.

    Args:
        metrics: Dictionary of metric scores (maintainability, reliability, etc.)
        days: Number of days of trend data to generate

    Returns:
        List of trend data points with date and weighted score
    """
    # Weights for calculating overall weighted score
    weights = {
        "maintainability": 0.25,
        "reliability": 0.20,
        "security": 0.20,
        "performance": 0.15,
        "testability": 0.10,
        "documentation": 0.10,
    }

    weighted_score = sum(metrics.get(category, 0) * weight for category, weight in weights.items())

    return [
        {
            "date": (datetime.now(tz=timezone.utc) - timedelta(days=i)).isoformat(),
            "score": weighted_score,
        }
        for i in range(days, -1, -1)
    ]


def _calculate_all_quality_scores(
    problems: list[dict],
    stats: dict[str, Any],
    total_files: int,
) -> dict[str, float]:
    """
    Calculate all quality metric scores from problems and stats.

    Issue #620: Extracted from calculate_real_quality_metrics.

    Args:
        problems: List of problem dictionaries from analysis
        stats: Codebase statistics from analysis
        total_files: Total number of files in codebase

    Returns:
        Dictionary mapping metric categories to scores
    """
    metrics = {
        "maintainability": _calculate_maintainability_score(problems, total_files),
        "reliability": _calculate_reliability_score(problems),
        "security": _calculate_security_score(problems),
        "performance": _calculate_performance_score(problems),
        "testability": _calculate_testability_score(stats, total_files),
        "documentation": _calculate_documentation_score(stats),
    }

    logger.info(
        "Calculated quality metrics: maintainability=%.1f, reliability=%.1f, "
        "security=%.1f, performance=%.1f, testability=%.1f, documentation=%.1f",
        metrics["maintainability"],
        metrics["reliability"],
        metrics["security"],
        metrics["performance"],
        metrics["testability"],
        metrics["documentation"],
    )

    return metrics


async def calculate_real_quality_metrics(
    source_root: "Path" | None = None,
    source_id: str | None = None,
) -> dict[str, Any] | None:
    """Calculate real quality metrics from ChromaDB analysis data.

    Issue #541: This replaces static demo values with actual calculated metrics.
    Issue #620: Refactored to use helper functions.
    Issue #3441: Accepts optional source_root to scope metrics to a project
    directory.  When provided, only problems under source_root contribute to
    the returned scores.
    Issue #6670: Accepts optional source_id forwarded to ChromaDB stats lookup
    so per-source codebase_stats documents are read.

    Args:
        source_root: Absolute path used to filter problems.  None means global.
        source_id:   Project source ID for per-source stats lookup.

    Returns:
        Dict with calculated quality metrics, or None if no data available
    """
    # Fetch data from ChromaDB (scoped to source_root when provided)
    problems, stats = await _get_problems_from_chromadb(source_root=source_root, source_id=source_id)

    # Issue #543: If no data, return None - endpoints will return no_data status
    if not problems and not stats:
        logger.info("No analysis data found in ChromaDB")
        return None

    # Get file counts
    total_files = int(stats.get("total_files", 0)) or 100  # Default estimate
    total_lines = int(stats.get("total_lines", 0)) or 10000

    # Calculate metrics using helper (Issue #620)
    metrics = _calculate_all_quality_scores(problems, stats, total_files)

    return {
        "metrics": {k: round(v, 1) for k, v in metrics.items()},
        "patterns": _categorize_problems_for_patterns(problems),
        "complexity": _calculate_complexity_metrics(stats, problems),
        "stats": {
            "file_count": total_files,
            "line_count": total_lines,
            "issues_count": len(problems),
        },
        "trends": _build_quality_trends(metrics),
        "source": "calculated",
        "calculated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def _no_data_response(
    message: str = "No analysis data. Run codebase indexing first.",
) -> dict:
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


def _filter_problems_by_category(problems: list[dict], category: str, severity: str | None) -> list[dict]:
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
    category_problems = [p for p in problems if any(t in p.get("type", "").lower() for t in target_types)]

    if severity:
        category_problems = [p for p in category_problems if p.get("severity") == severity]

    return category_problems


def _group_problems_by_file(problems: list[dict], file_filter: str | None) -> dict[str, list[dict]]:
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

        result_files.append(
            {
                "path": file_path,
                "issues": issue_count,
                "score": score,
                "top_issue": top_issue[:100],
            }
        )

    result_files.sort(key=lambda x: x["issues"], reverse=True)
    return result_files


def _build_quality_export_report(format_type: str, health: Any, metrics: dict, data: dict) -> dict:
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
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
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
    writer.writerow(["Health", "Overall Score", f"{health.overall:.1f}", health.grade.value])

    for cat, val in metrics.items():
        writer.writerow(
            [
                "Metrics",
                cat.replace("_", " ").title(),
                f"{val:.1f}",
                get_grade(val).value,
            ]
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
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove disconnected WebSocket."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

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


@router.get("/health-score", response_model=QualityHealthScoreResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_health_score",
    error_code_prefix="ANALYTICS_QUALITY",
)
async def get_health_score(
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Get current codebase health score with breakdown.

    Returns overall health score, grade, and recommendations.
    Issue #543: Returns no_data status when no analysis data available.
    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is supplied, results are scoped to that
    project's clone directory so only files under source_root contribute.
    """
    source_root = await _resolve_source_root_or_404(source_id)
    data = await get_quality_data_from_storage(source_root=source_root, source_id=source_id)

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
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/metrics", response_model=QualityMetricsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quality_metrics",
    error_code_prefix="ANALYTICS_QUALITY",
)
async def get_quality_metrics(
    category: MetricCategory | None = Query(None, description="Filter by category"),
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Get all quality metrics or filter by category.

    Returns detailed metrics with grades and trends.
    Issue #543: Returns no_data status when no analysis data available.
    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is supplied, results are scoped to that
    project's clone directory so only files under source_root contribute.
    """
    source_root = await _resolve_source_root_or_404(source_id)
    data = await get_quality_data_from_storage(source_root=source_root, source_id=source_id)

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

    return {
        "status": "success",
        "metrics": sorted(metrics, key=lambda x: x["value"], reverse=True),
    }


@router.get("/patterns", response_model=QualityPatternsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pattern_distribution",
    error_code_prefix="ANALYTICS_QUALITY",
)
async def get_pattern_distribution(
    severity: str | None = Query(None, description="Filter by severity"),
    limit: int = Query(20, ge=1, le=100),
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Get distribution of code patterns detected in the codebase.

    Returns pattern types with counts, percentages, and severity.
    Issue #543: Returns no_data status when no analysis data available.
    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is supplied, results are scoped to that
    project's clone directory so only files under source_root contribute.
    """
    source_root = await _resolve_source_root_or_404(source_id)
    data = await get_quality_data_from_storage(source_root=source_root, source_id=source_id)

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


@router.get("/complexity", response_model=QualityComplexityResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_complexity_metrics",
    error_code_prefix="ANALYTICS_QUALITY",
)
async def get_complexity_metrics(
    top_n: int = Query(10, ge=1, le=50, description="Number of hotspots to return"),
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Get code complexity analysis with hotspots.

    Returns cyclomatic and cognitive complexity metrics.
    Issue #543: Returns no_data status when no analysis data available.
    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is supplied, results are scoped to that
    project's clone directory so only files under source_root contribute.
    """
    source_root = await _resolve_source_root_or_404(source_id)
    data = await get_quality_data_from_storage(source_root=source_root, source_id=source_id)

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
                "recommendation": (
                    "Consider refactoring this file" if h.get("complexity", 0) > 15 else "Monitor complexity"
                ),
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


def _filter_trends_by_period(trends: list, cutoff: datetime) -> list:
    """Helper for get_quality_trends. Ref: #1088.

    Filters raw trend data points to only include those on or after cutoff.
    Silently skips entries with unparseable date values.
    """
    filtered = []
    for t in trends:
        try:
            date = parse_utc_iso(t.get("date", ""))
            if date >= cutoff:
                filtered.append(t)
        except (ValueError, TypeError):
            continue
    return filtered


def _calculate_trend_statistics(scores: list) -> dict:
    """Helper for get_quality_trends. Ref: #1088.

    Computes summary statistics (current, previous, change, direction,
    average, min, max) from a list of quality scores.
    Returns zeroed stats dict when the list is empty.
    """
    if not scores:
        return {
            "current": 0,
            "previous": 0,
            "change": 0,
            "direction": "stable",
            "average": 0,
            "min": 0,
            "max": 0,
        }

    current = scores[-1]
    previous = scores[0]
    change = ((current - previous) / previous * 100) if previous > 0 else 0
    return {
        "current": current,
        "previous": previous,
        "change": change,
        "direction": "up" if change > 0 else "down" if change < 0 else "stable",
        "average": sum(scores) / len(scores),
        "min": min(scores),
        "max": max(scores),
    }


@router.get("/trends", response_model=QualityTrendsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quality_trends",
    error_code_prefix="ANALYTICS_QUALITY",
)
async def get_quality_trends(
    period: str = Query("30d", pattern="^(7d|14d|30d|90d)$"),
    metric: str | None = Query(None, description="Specific metric to trend"),
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Get quality score trends over time.

    Returns historical data for trend analysis.
    Issue #543: Returns no_data status when no analysis data available.
    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is supplied, results are scoped to that
    project's clone directory so only files under source_root contribute.
    """
    source_root = await _resolve_source_root_or_404(source_id)
    data = await get_quality_data_from_storage(source_root=source_root, source_id=source_id)

    if data is None:
        return _no_data_response()

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=int(period[:-1]))
    filtered_trends = _filter_trends_by_period(data.get("trends", []), cutoff)
    scores = [t.get("score", 0) for t in filtered_trends]

    return {
        "status": "success",
        "period": period,
        "data_points": filtered_trends,
        "statistics": _calculate_trend_statistics(scores),
        "metric": metric or "overall",
    }


@router.get("/snapshot", response_model=QualitySnapshotResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quality_snapshot",
    error_code_prefix="ANALYTICS_QUALITY",
)
async def get_quality_snapshot(
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Get complete quality snapshot for the current state.

    Returns all metrics, patterns, and statistics in one response.
    Issue #543: Returns no_data status when no analysis data available.
    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is supplied, results are scoped to that
    project's clone directory so only files under source_root contribute.
    """
    source_root = await _resolve_source_root_or_404(source_id)
    data = await get_quality_data_from_storage(source_root=source_root, source_id=source_id)

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
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
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
            "critical": sum(p.get("count", 0) for p in patterns if p.get("severity") == "critical"),
            "high": sum(p.get("count", 0) for p in patterns if p.get("severity") == "high"),
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


@router.get("/drill-down/{category}", response_model=QualityDrillDownResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="drill_down_category",
    error_code_prefix="ANALYTICS_QUALITY",
)
async def drill_down_category(
    category: str,
    file_filter: str | None = Query(None, description="Filter by file path"),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Drill down into a specific quality category.

    Returns detailed issues and files for the category.
    Issue #543: Now queries real ChromaDB data instead of demo data.
    Issue #665: Refactored using helper functions for clarity.
    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is supplied, results are scoped to that
    project's clone directory so only files under source_root contribute.
    """
    source_root = await _resolve_source_root_or_404(source_id)
    problems, stats = await _get_problems_from_chromadb(source_root=source_root)

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
        "average_score": (sum(f["score"] for f in result_files) / len(result_files) if result_files else 0),
        "files": result_files[:limit],
        "filters_applied": {
            "file": file_filter,
            "severity": severity,
        },
    }


@router.get("/export", response_model=DataResponse[AnalyticsQualityExportData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_quality_report",
    error_code_prefix="ANALYTICS_QUALITY",
)
async def export_quality_report(
    format: str = Query("json", pattern="^(json|csv|pdf)$"),
    admin_check: bool = Depends(check_admin_permission),
) -> JSONResponse:
    """
    Export quality report in specified format.

    Supports JSON, CSV, and PDF formats.
    Issue #543: Returns no_data status when no analysis data available.
    Issue #665: Refactored using helper functions for clarity.
    Issue #744: Requires admin authentication.
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="websocket_quality_updates",
    error_code_prefix="ANALYTICS_QUALITY",
)
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
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    )
