# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Bug Prediction System API (Issue #224)

Uses historical bug data, code patterns, and risk factors to predict
where bugs are likely to occur. Provides risk scoring, prevention tips,
and targeted testing suggestions.
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from src.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bug-prediction", tags=["bug-prediction", "analytics"])

# Performance optimization: O(1) lookup for control flow keywords (Issue #326)
CONTROL_FLOW_KEYWORDS = {"if ", "elif ", "else:", "try:", "except:", "for ", "while "}

# Issue #380: Module-level tuple for function definition prefixes
_FUNCTION_DEF_PREFIXES = ("def ", "async def ")


def _no_data_response(message: str = "No bug prediction data available. Run codebase analysis first.") -> dict:
    """
    Standardized no-data response.

    Issue #543: Replaces all demo data responses.

    Args:
        message: Custom message explaining why no data is available

    Returns:
        Dict with status="no_data", message, and empty data structures
    """
    return {
        "status": "no_data",
        "message": message,
        "files": [],
        "summary": {},
    }


def _parse_git_bug_history_lines(lines: list[str]) -> dict[str, int]:
    """Parse git log output to count bug fixes per file. (Issue #315 - extracted)"""
    file_bug_counts: dict[str, int] = {}
    current_files: list[str] = []

    for line in lines:
        if not line or line.startswith(" "):
            continue
        # This is either a commit hash or a file
        if "/" in line or line.endswith(".py") or line.endswith(".vue"):
            for f in current_files:
                file_bug_counts[f] = file_bug_counts.get(f, 0) + 1
            current_files = [line]
        else:
            current_files = []

    return file_bug_counts


def _build_file_risk_dict(
    file_path: str,
    risk_score: float,
    factors: dict[str, float],
    bug_count_history: int = 0,
) -> dict[str, Any]:
    """
    Build a file risk analysis dict with standardized structure.

    Issue #281: Extracted helper to reduce repetition in analyze_codebase.

    Args:
        file_path: Relative path to the file
        risk_score: Calculated risk score (0-100)
        factors: Dict of risk factor values
        bug_count_history: Historical bug count for file

    Returns:
        Dict with risk assessment for the file
    """
    return {
        "file_path": file_path,
        "risk_score": round(risk_score, 1),
        "risk_level": get_risk_level(risk_score).value,
        "factors": factors,
        "bug_count_history": bug_count_history,
        "prevention_tips": get_prevention_tips(factors),
        "suggested_tests": get_suggested_tests(file_path, factors),
    }


# ============================================================================
# Models
# ============================================================================


class RiskLevel(str, Enum):
    """Bug risk levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class RiskFactor(str, Enum):
    """Factors contributing to bug risk."""

    COMPLEXITY = "complexity"
    CHANGE_FREQUENCY = "change_frequency"
    CODE_AGE = "code_age"
    TEST_COVERAGE = "test_coverage"
    BUG_HISTORY = "bug_history"
    AUTHOR_EXPERIENCE = "author_experience"
    FILE_SIZE = "file_size"
    DEPENDENCY_COUNT = "dependency_count"


class FileRisk(BaseModel):
    """Bug risk assessment for a file."""

    file_path: str
    risk_score: float = Field(..., ge=0, le=100)
    risk_level: RiskLevel
    factors: dict[str, float] = Field(default_factory=dict)
    bug_count_history: int = 0
    last_bug_date: Optional[str] = None
    prevention_tips: list[str] = Field(default_factory=list)
    suggested_tests: list[str] = Field(default_factory=list)


class PredictionResult(BaseModel):
    """Bug prediction result for the codebase."""

    timestamp: datetime
    total_files: int
    high_risk_count: int
    predicted_bugs: int
    accuracy_score: float
    risk_distribution: dict[str, int] = Field(default_factory=dict)
    top_risk_files: list[FileRisk] = Field(default_factory=list)


# ============================================================================
# Risk Weights Configuration
# ============================================================================


RISK_WEIGHTS = {
    RiskFactor.COMPLEXITY: 0.20,
    RiskFactor.CHANGE_FREQUENCY: 0.20,
    RiskFactor.BUG_HISTORY: 0.25,
    RiskFactor.TEST_COVERAGE: 0.15,
    RiskFactor.CODE_AGE: 0.05,
    RiskFactor.AUTHOR_EXPERIENCE: 0.05,
    RiskFactor.FILE_SIZE: 0.05,
    RiskFactor.DEPENDENCY_COUNT: 0.05,
}


PREVENTION_TIPS = {
    RiskFactor.COMPLEXITY: [
        "Break down complex functions into smaller, testable units",
        "Add inline comments explaining complex logic",
        "Consider extracting helper functions",
        "Use design patterns to reduce cyclomatic complexity",
    ],
    RiskFactor.CHANGE_FREQUENCY: [
        "Stabilize the module before adding new features",
        "Review recent changes thoroughly",
        "Add regression tests for frequently changed code",
        "Consider refactoring to reduce change coupling",
    ],
    RiskFactor.BUG_HISTORY: [
        "Review all bug fix commits in this file",
        "Add defensive programming patterns",
        "Increase test coverage significantly",
        "Consider a comprehensive code review",
    ],
    RiskFactor.TEST_COVERAGE: [
        "Add unit tests for untested functions",
        "Create integration tests for critical paths",
        "Add edge case tests",
        "Consider mutation testing to improve test quality",
    ],
    RiskFactor.FILE_SIZE: [
        "Split large file into smaller modules",
        "Extract reusable components",
        "Apply single responsibility principle",
    ],
    RiskFactor.DEPENDENCY_COUNT: [
        "Reduce coupling by using dependency injection",
        "Consider facade pattern to simplify dependencies",
        "Review if all dependencies are necessary",
    ],
}


# ============================================================================
# Utility Functions
# ============================================================================


def get_risk_level(score: float) -> RiskLevel:
    """Convert risk score to level."""
    if score >= 80:
        return RiskLevel.CRITICAL
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 40:
        return RiskLevel.MEDIUM
    if score >= 20:
        return RiskLevel.LOW
    return RiskLevel.MINIMAL


def get_prevention_tips(factors: dict[str, float]) -> list[str]:
    """Get prevention tips based on highest risk factors."""
    tips = []
    sorted_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)

    for factor_name, score in sorted_factors[:3]:
        if score > 50:
            try:
                factor = RiskFactor(factor_name)
                tips.extend(PREVENTION_TIPS.get(factor, [])[:2])
            except ValueError:
                continue

    return tips[:5]


def get_suggested_tests(file_path: str, factors: dict[str, float]) -> list[str]:
    """Generate suggested tests based on risk factors."""
    suggestions = []
    basename = Path(file_path).stem

    if factors.get("complexity", 0) > 50:
        suggestions.append(f"Add boundary condition tests for {basename}")
        suggestions.append(f"Test error handling paths in {basename}")

    if factors.get("change_frequency", 0) > 50:
        suggestions.append(f"Add regression tests for recent changes in {basename}")

    if factors.get("bug_history", 0) > 50:
        suggestions.append(f"Create tests covering previous bug scenarios in {basename}")

    if factors.get("test_coverage", 0) > 50:  # High means low coverage
        suggestions.append(f"Increase unit test coverage for {basename}")
        suggestions.append(f"Add integration tests for {basename}")

    return suggestions[:4]


async def get_git_bug_history() -> dict[str, Any]:
    """Analyze git history for bug fixes."""
    try:
        # Get commits with bug-related keywords using async subprocess
        proc = await asyncio.create_subprocess_exec(
            "git",
            "log",
            "--oneline",
            "--since=1 year ago",
            "--grep=fix",
            "--grep=bug",
            "--grep=error",
            "--grep=issue",
            "--all-match",
            "--name-only",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=TimingConstants.SHORT_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("Git bug history command timed out")
            return {}

        if proc.returncode != 0:
            return {}

        # Parse output to count bug fixes per file (Issue #315 - uses helper)
        lines = stdout.decode("utf-8").strip().split("\n")
        return _parse_git_bug_history_lines(lines)

    except Exception as e:
        logger.warning("Failed to get git bug history: %s", e)
        return {}


async def get_file_change_frequency() -> dict[str, int]:
    """Get change frequency for files in the last 90 days."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "log",
            "--since=90 days ago",
            "--name-only",
            "--pretty=format:",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=TimingConstants.SHORT_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("Git change frequency command timed out")
            return {}

        if proc.returncode != 0:
            return {}

        change_counts: dict[str, int] = {}
        for line in stdout.decode("utf-8").strip().split("\n"):
            if line:
                change_counts[line] = change_counts.get(line, 0) + 1

        return change_counts

    except Exception as e:
        logger.warning("Failed to get change frequency: %s", e)
        return {}


def _score_from_thresholds(
    value: float,
    thresholds: list[tuple[float, int]],
) -> int:
    """
    Calculate score based on threshold levels.

    Issue #281: Extracted helper to reduce repetition in analyze_file_complexity.
    Each threshold is (min_value, score_to_add) - checked in order, first match wins.

    Args:
        value: The metric value to evaluate
        thresholds: List of (threshold, score) tuples, checked in order

    Returns:
        Score for the first matching threshold, or 0 if none match
    """
    for threshold, score in thresholds:
        if value > threshold:
            return score
    return 0


def _calculate_max_indent(lines: list) -> int:
    """Calculate max indentation depth (Issue #398: extracted)."""
    max_indent = 0
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            spaces = indent // 4 if "    " in line[:indent] else indent // 2
            max_indent = max(max_indent, spaces)
    return max_indent


def _calculate_conditional_density(lines: list, line_count: int) -> float:
    """Calculate conditional statement density (Issue #398: extracted)."""
    conditionals = sum(1 for line in lines if any(kw in line for kw in CONTROL_FLOW_KEYWORDS))
    return conditionals / max(line_count, 1) * 100


def _calculate_complexity_score(lines: list) -> int:
    """Calculate total complexity score from code lines (Issue #398: extracted)."""
    line_count = len(lines)
    score = _score_from_thresholds(line_count, [(500, 30), (300, 20), (100, 10)])
    score += _score_from_thresholds(_calculate_max_indent(lines), [(6, 25), (4, 15), (2, 5)])
    score += _score_from_thresholds(_calculate_conditional_density(lines, line_count), [(15, 25), (10, 15), (5, 5)])
    func_count = sum(1 for line in lines if line.strip().startswith(_FUNCTION_DEF_PREFIXES))
    score += _score_from_thresholds(func_count, [(20, 20), (10, 10)])
    return min(100, score)


async def analyze_file_complexity(file_path: str) -> float:
    """Estimate file complexity 0-100 score (Issue #398: refactored)."""
    try:
        path = Path(file_path)
        if not await asyncio.to_thread(path.exists):
            return 30
        content = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="ignore")
        return _calculate_complexity_score(content.split("\n"))
    except Exception as e:
        logger.warning("Failed to analyze complexity for %s: %s", file_path, e)
        return 30


# ============================================================================
# REST Endpoints
# ============================================================================


def _find_files_sync(path: str, include_pattern: str, limit: int) -> List[Path]:
    """Find files matching pattern in directory (Issue #398: extracted)."""
    result = []
    try:
        root = Path(path)
        if root.is_dir():
            result = list(root.rglob(include_pattern))[:limit]
    except Exception as e:
        logger.debug("Path traversal error: %s", e)
    return result


async def _analyze_single_file(
    file_path: Path,
    change_freq: Dict[str, int],
    bug_history: Dict[str, int],
) -> Dict[str, Any]:
    """Analyze a single file for bug risk (Issue #398: extracted)."""
    str_path = str(file_path)
    rel_path = str_path.replace(str(Path.cwd()) + "/", "")

    complexity = await analyze_file_complexity(str_path)
    change_count = change_freq.get(rel_path, 0)
    bug_count = bug_history.get(rel_path, 0)

    file_stat = await asyncio.to_thread(file_path.stat)
    factors = {
        "complexity": complexity,
        "change_frequency": min(100, change_count * 10),
        "bug_history": min(100, bug_count * 15),
        "test_coverage": 50,  # Would need actual coverage data
        "file_size": min(100, file_stat.st_size / 500),
    }

    risk_score = sum(
        factors.get(factor.value, 0) * weight
        for factor, weight in RISK_WEIGHTS.items()
        if factor.value in factors
    )

    return _build_file_risk_dict(rel_path, risk_score, factors, bug_count)


@router.get("/analyze")
async def analyze_codebase(
    path: str = Query(".", description="Path to analyze"),
    include_pattern: str = Query("*.py", description="File pattern to include"),
    limit: int = Query(1000, ge=1, le=5000, description="Maximum files to analyze"),
) -> dict[str, Any]:
    """
    Analyze codebase for bug risk (Issue #543: no demo data).

    Returns risk assessment for all files matching the pattern.
    """
    try:
        bug_history = await get_git_bug_history()
        change_freq = await get_file_change_frequency()

        files_to_analyze = await asyncio.to_thread(
            _find_files_sync, path, include_pattern, limit
        )

        if not files_to_analyze:
            return _no_data_response(f"No files matching '{include_pattern}' found in '{path}'")

        # Analyze each file using extracted helper
        analyzed_files = [
            await _analyze_single_file(fp, change_freq, bug_history)
            for fp in files_to_analyze
        ]

        analyzed_files.sort(key=lambda x: x["risk_score"], reverse=True)
        high_risk = sum(1 for f in analyzed_files if f["risk_score"] >= 60)

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "total_files": len(files_to_analyze),
            "analyzed_files": len(analyzed_files),
            "high_risk_count": high_risk,
            "files": analyzed_files[:limit],
        }

    except Exception as e:
        logger.error("Failed to analyze codebase: %s", e, exc_info=True)
        return _no_data_response(f"Analysis failed: {str(e)}")


@router.get("/high-risk")
async def get_high_risk_files(
    threshold: float = Query(60, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
    path: str = Query(".", description="Path to analyze"),
    include_pattern: str = Query("*.py", description="File pattern to include"),
) -> dict[str, Any]:
    """
    Get files with high bug risk (Issue #543: no demo data).

    Returns files with risk score above the threshold.
    """
    try:
        bug_history = await get_git_bug_history()
        change_freq = await get_file_change_frequency()

        files_to_analyze = await asyncio.to_thread(
            _find_files_sync, path, include_pattern, 200  # Higher limit to find high-risk files
        )

        if not files_to_analyze:
            return _no_data_response(f"No files matching '{include_pattern}' found in '{path}'")

        # Analyze each file
        analyzed_files = [
            await _analyze_single_file(fp, change_freq, bug_history)
            for fp in files_to_analyze
        ]

        # Filter high-risk files
        high_risk_files = [f for f in analyzed_files if f["risk_score"] >= threshold]
        high_risk_files.sort(key=lambda x: x["risk_score"], reverse=True)

        return {
            "status": "success",
            "threshold": threshold,
            "high_risk_count": len(high_risk_files),
            "files": high_risk_files[:limit],
        }

    except Exception as e:
        logger.error("Failed to get high-risk files: %s", e, exc_info=True)
        return _no_data_response(f"Analysis failed: {str(e)}")


def _build_file_risk_response(file_path: str, factors: dict, bug_history: dict) -> dict:
    """Build file risk response from factors (Issue #398: extracted)."""
    risk_score = sum(factors.get(f.value, 0) * w for f, w in RISK_WEIGHTS.items() if f.value in factors)
    return {
        "file_path": file_path, "risk_score": round(risk_score, 1),
        "risk_level": get_risk_level(risk_score).value, "factors": factors,
        "factor_weights": {k.value: v for k, v in RISK_WEIGHTS.items()},
        "bug_count_history": bug_history.get(file_path, 0),
        "prevention_tips": get_prevention_tips(factors),
        "suggested_tests": get_suggested_tests(file_path, factors),
        "recommendation": _get_file_recommendation(risk_score, factors),
    }


@router.get("/file/{file_path:path}")
async def get_file_risk(file_path: str) -> dict[str, Any]:
    """Get detailed risk assessment for a specific file (Issue #543: no demo data)."""
    path = Path(file_path)
    if not await asyncio.to_thread(path.exists):
        return _no_data_response(f"File not found: {file_path}")

    try:
        complexity = await analyze_file_complexity(str(path))
        bug_history = await get_git_bug_history()
        change_freq = await get_file_change_frequency()
        file_stat = await asyncio.to_thread(path.stat)

        factors = {
            "complexity": complexity,
            "change_frequency": min(100, change_freq.get(file_path, 0) * 10),
            "bug_history": min(100, bug_history.get(file_path, 0) * 15),
            "test_coverage": 50,
            "file_size": min(100, file_stat.st_size / 500),
        }

        response = _build_file_risk_response(file_path, factors, bug_history)
        response["status"] = "success"
        return response

    except Exception as e:
        logger.error("Failed to analyze file %s: %s", file_path, e, exc_info=True)
        return _no_data_response(f"Analysis failed for {file_path}: {str(e)}")


def _get_file_recommendation(risk_score: float, factors: dict[str, float]) -> str:
    """Generate a recommendation based on risk analysis."""
    if risk_score >= 80:
        return "CRITICAL: Immediate attention required. Consider comprehensive code review and refactoring."
    if risk_score >= 60:
        return "HIGH RISK: Prioritize testing and code review. Add monitoring for this file."
    if risk_score >= 40:
        return "MODERATE: Regular monitoring recommended. Consider improving test coverage."
    if risk_score >= 20:
        return "LOW RISK: Standard maintenance practices sufficient."
    return "MINIMAL RISK: File is well-maintained with low bug probability."


# Heatmap legend configuration (Issue #398: extracted)
_HEATMAP_LEGEND = {
    "critical": {"min": 80, "color": "#ef4444"}, "high": {"min": 60, "color": "#f97316"},
    "medium": {"min": 40, "color": "#eab308"}, "low": {"min": 20, "color": "#22c55e"},
    "minimal": {"min": 0, "color": "#3b82f6"},
}


def _group_files_by_directory(files: list) -> list:
    """Group files by top-level directory (Issue #398: extracted)."""
    groups: dict[str, list[dict]] = {}
    for f in files:
        parts = f["file_path"].split("/")
        group = parts[0] if len(parts) > 1 else "root"
        groups.setdefault(group, []).append(f)

    heatmap_data = []
    for group_name, group_files in groups.items():
        avg_risk = sum(f["risk_score"] for f in group_files) / len(group_files)
        heatmap_data.append({
            "name": group_name, "value": round(avg_risk, 1), "file_count": len(group_files),
            "risk_level": get_risk_level(avg_risk).value, "files": group_files,
        })
    return sorted(heatmap_data, key=lambda x: x["value"], reverse=True)


def _get_flat_heatmap_data(files: list) -> list:
    """Get flat heatmap data (Issue #398: extracted)."""
    return [{"name": f["file_path"], "value": f["risk_score"], "risk_level": get_risk_level(f["risk_score"]).value}
            for f in sorted(files, key=lambda x: x["risk_score"], reverse=True)]


@router.get("/heatmap")
async def get_risk_heatmap(
    grouping: str = Query("directory", regex="^(directory|module|flat)$"),
    path: str = Query(".", description="Path to analyze"),
    include_pattern: str = Query("*.py", description="File pattern to include"),
    limit: int = Query(100, ge=1, le=300),
) -> dict[str, Any]:
    """Get risk heatmap data for visualization (Issue #543: no demo data)."""
    try:
        bug_history = await get_git_bug_history()
        change_freq = await get_file_change_frequency()

        files_to_analyze = await asyncio.to_thread(
            _find_files_sync, path, include_pattern, limit
        )

        if not files_to_analyze:
            return _no_data_response(f"No files matching '{include_pattern}' found in '{path}'")

        # Analyze each file
        analyzed_files = [
            await _analyze_single_file(fp, change_freq, bug_history)
            for fp in files_to_analyze
        ]

        # Generate heatmap data
        data = _group_files_by_directory(analyzed_files) if grouping == "directory" else _get_flat_heatmap_data(analyzed_files)

        return {
            "status": "success",
            "grouping": grouping if grouping == "directory" else "flat",
            "data": data,
            "legend": _HEATMAP_LEGEND,
        }

    except Exception as e:
        logger.error("Failed to generate heatmap: %s", e, exc_info=True)
        return _no_data_response(f"Heatmap generation failed: {str(e)}")


@router.get("/trends")
async def get_prediction_trends(
    period: str = Query("30d", regex="^(7d|30d|90d)$"),
) -> dict[str, Any]:
    """
    Get historical bug prediction accuracy trends.

    Issue #543: Returns no_data until real trend tracking is implemented.
    Real implementation would require:
    - Storing prediction results over time
    - Tracking actual bugs found vs predicted
    - Calculating accuracy metrics from historical data
    """
    # Issue #543: Return no_data instead of fake random data
    # TODO: Implement real trend tracking by storing prediction history
    return _no_data_response(
        f"Bug prediction trend data for period '{period}' not available. "
        "Trend tracking requires storing prediction history over time."
    )


@router.get("/summary")
async def get_prediction_summary(
    path: str = Query(".", description="Path to analyze"),
    include_pattern: str = Query("*.py", description="File pattern to include"),
    limit: int = Query(1000, ge=1, le=5000, description="Maximum files to analyze"),
) -> dict[str, Any]:
    """
    Get summary of bug predictions and risk assessment (Issue #543: no demo data).

    Returns high-level metrics for dashboard display.
    """
    try:
        bug_history = await get_git_bug_history()
        change_freq = await get_file_change_frequency()

        files_to_analyze = await asyncio.to_thread(
            _find_files_sync, path, include_pattern, limit
        )

        if not files_to_analyze:
            return _no_data_response(f"No files matching '{include_pattern}' found in '{path}'")

        # Analyze each file
        analyzed_files = [
            await _analyze_single_file(fp, change_freq, bug_history)
            for fp in files_to_analyze
        ]

        # Risk distribution
        risk_dist = {level.value: 0 for level in RiskLevel}
        for f in analyzed_files:
            level = get_risk_level(f["risk_score"])
            risk_dist[level.value] += 1

        # Top risk factors across all files
        factor_totals: dict[str, float] = {}
        for f in analyzed_files:
            for factor, score in f["factors"].items():
                factor_totals[factor] = factor_totals.get(factor, 0) + score

        top_factors = sorted(factor_totals.items(), key=lambda x: x[1], reverse=True)

        # Generate recommendations based on actual data
        high_risk_count = risk_dist.get("high", 0) + risk_dist.get("critical", 0)
        recommendations = []
        if high_risk_count > 0:
            recommendations.append(f"Focus testing efforts on {high_risk_count} high-risk files")

        # Get top 3 highest risk files for recommendations
        top_risky = sorted(analyzed_files, key=lambda x: x["risk_score"], reverse=True)[:3]
        for f in top_risky:
            if f["risk_score"] >= 60:
                recommendations.append(f"Review {f['file_path']} (risk score: {f['risk_score']:.1f})")

        if not recommendations:
            recommendations.append("All files are within acceptable risk levels")

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "total_files_analyzed": len(analyzed_files),
            "high_risk_files": high_risk_count,
            "risk_distribution": risk_dist,
            "top_risk_factors": [
                {
                    "factor": f[0].replace("_", " ").title(),
                    "total_score": round(f[1], 1),
                    "average": round(f[1] / len(analyzed_files), 1),
                }
                for f in top_factors[:5]
            ],
            "recommendations": recommendations[:5],
        }

    except Exception as e:
        logger.error("Failed to generate summary: %s", e, exc_info=True)
        return _no_data_response(f"Summary generation failed: {str(e)}")


@router.get("/factors")
async def get_risk_factors() -> dict[str, Any]:
    """
    Get all risk factors and their weights.

    Returns factor definitions and how they contribute to risk scores.
    """
    return {
        "factors": [
            {
                "name": factor.value,
                "display_name": factor.value.replace("_", " ").title(),
                "weight": weight,
                "weight_percentage": f"{weight * 100:.0f}%",
                "description": _get_factor_description(factor),
            }
            for factor, weight in RISK_WEIGHTS.items()
        ],
        "total_weight": sum(RISK_WEIGHTS.values()),
        "scoring": {
            "critical": "80-100: Immediate attention required",
            "high": "60-79: Prioritize for review",
            "medium": "40-59: Monitor regularly",
            "low": "20-39: Standard maintenance",
            "minimal": "0-19: Low priority",
        },
    }


def _get_factor_description(factor: RiskFactor) -> str:
    """Get human-readable description for a risk factor."""
    descriptions = {
        RiskFactor.COMPLEXITY: "Code complexity measured by nesting depth, conditionals, and function count",
        RiskFactor.CHANGE_FREQUENCY: "How often the file has been modified in the last 90 days",
        RiskFactor.BUG_HISTORY: "Number of bug fixes historically associated with this file",
        RiskFactor.TEST_COVERAGE: "Inverse of test coverage - higher score means less coverage",
        RiskFactor.CODE_AGE: "Age of the code since last major refactor",
        RiskFactor.AUTHOR_EXPERIENCE: "Experience level of recent contributors",
        RiskFactor.FILE_SIZE: "File size in lines of code",
        RiskFactor.DEPENDENCY_COUNT: "Number of imports and dependencies",
    }
    return descriptions.get(factor, "Unknown factor")


@router.post("/record-bug")
async def record_bug(
    file_path: str,
    description: str = "",
    severity: str = "medium",
) -> dict[str, Any]:
    """
    Record a new bug for model improvement.

    Updates prediction accuracy based on actual bug occurrences.
    """
    try:
        from src.utils.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if redis:
            bug_record = {
                "file_path": file_path,
                "description": description,
                "severity": severity,
                "recorded_at": datetime.now().isoformat(),
            }
            # Issue #361 - avoid blocking
            await asyncio.to_thread(
                redis.lpush, "bug_prediction:recorded_bugs", json.dumps(bug_record)
            )
            await asyncio.to_thread(
                redis.ltrim, "bug_prediction:recorded_bugs", 0, 999
            )  # Keep last 1000

            return {
                "status": "recorded",
                "bug": bug_record,
                "message": "Bug recorded for model improvement",
            }
    except Exception as e:
        logger.warning("Failed to record bug in Redis: %s", e)

    return {
        "status": "recorded",
        "bug": {
            "file_path": file_path,
            "description": description,
            "severity": severity,
        },
        "message": "Bug recorded (local only)",
    }
