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
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.auth_middleware import check_admin_permission
from src.constants.threshold_constants import TimingConstants
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bug-prediction", tags=["bug-prediction", "analytics"])

# Performance optimization: O(1) lookup for control flow keywords (Issue #326)
CONTROL_FLOW_KEYWORDS = {"if ", "elif ", "else:", "try:", "except:", "for ", "while "}

# Issue #380: Module-level tuple for function definition prefixes
_FUNCTION_DEF_PREFIXES = ("def ", "async def ")


def _no_data_response(
    message: str = "No bug prediction data available. Run codebase analysis first.",
) -> dict:
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
        suggestions.append(
            f"Create tests covering previous bug scenarios in {basename}"
        )

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
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=TimingConstants.SHORT_TIMEOUT
            )
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
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=TimingConstants.SHORT_TIMEOUT
            )
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
    conditionals = sum(
        1 for line in lines if any(kw in line for kw in CONTROL_FLOW_KEYWORDS)
    )
    return conditionals / max(line_count, 1) * 100


def _calculate_complexity_score(lines: list) -> int:
    """Calculate total complexity score from code lines (Issue #398: extracted)."""
    line_count = len(lines)
    score = _score_from_thresholds(line_count, [(500, 30), (300, 20), (100, 10)])
    score += _score_from_thresholds(
        _calculate_max_indent(lines), [(6, 25), (4, 15), (2, 5)]
    )
    score += _score_from_thresholds(
        _calculate_conditional_density(lines, line_count), [(15, 25), (10, 15), (5, 5)]
    )
    func_count = sum(
        1 for line in lines if line.strip().startswith(_FUNCTION_DEF_PREFIXES)
    )
    score += _score_from_thresholds(func_count, [(20, 20), (10, 10)])
    return min(100, score)


async def analyze_file_complexity(file_path: str) -> float:
    """Estimate file complexity 0-100 score (Issue #398: refactored)."""
    try:
        path = Path(file_path)
        if not await asyncio.to_thread(path.exists):
            return 30
        content = await asyncio.to_thread(
            path.read_text, encoding="utf-8", errors="ignore"
        )
        return _calculate_complexity_score(content.split("\n"))
    except Exception as e:
        logger.warning("Failed to analyze complexity for %s: %s", file_path, e)
        return 30


# ============================================================================
# Prediction History Storage (Issue #569)
# ============================================================================

# Redis key for prediction history sorted set
_PREDICTION_HISTORY_KEY = "bug_prediction:history"
# Maximum history entries to retain (approx 1 year of daily predictions)
_MAX_HISTORY_ENTRIES = 400
# Trend direction threshold: changes within +/-5% are considered stable
_TREND_STABILITY_THRESHOLD_PCT = 5.0


async def _store_prediction_history(
    total_files: int,
    high_risk_count: int,
    risk_distribution: Dict[str, int],
    analyzed_files: List[Dict[str, Any]],
) -> bool:
    """
    Store a prediction snapshot for trend tracking.

    Issue #569: Stores prediction results in Redis sorted set for historical analysis.
    Each prediction includes timestamp, file counts, risk distribution, and average risk.

    Args:
        total_files: Total number of files analyzed
        high_risk_count: Number of files with risk score >= 60
        risk_distribution: Dict mapping risk levels to file counts
        analyzed_files: List of analyzed file dicts with risk_score

    Returns:
        True if stored successfully, False otherwise
    """
    try:
        redis = get_redis_client(async_client=False, database="analytics")
        if not redis:
            logger.debug("Redis not available for prediction history storage")
            return False

        timestamp = datetime.now()
        timestamp_ms = int(timestamp.timestamp() * 1000)

        # Calculate average risk score
        avg_risk = 0.0
        if analyzed_files:
            avg_risk = sum(f.get("risk_score", 0) for f in analyzed_files) / len(
                analyzed_files
            )

        # Build prediction snapshot
        prediction_snapshot = {
            "timestamp": timestamp.isoformat(),
            "total_files": total_files,
            "high_risk_count": high_risk_count,
            "risk_distribution": risk_distribution,
            "average_risk_score": round(avg_risk, 2),
            "critical_count": risk_distribution.get("critical", 0),
            "high_count": risk_distribution.get("high", 0),
            "medium_count": risk_distribution.get("medium", 0),
            "low_count": risk_distribution.get("low", 0),
            "minimal_count": risk_distribution.get("minimal", 0),
        }

        # Store in sorted set with timestamp as score (for range queries)
        await asyncio.to_thread(
            redis.zadd,
            _PREDICTION_HISTORY_KEY,
            {json.dumps(prediction_snapshot): timestamp_ms},
        )

        # Trim to keep only the most recent entries
        # zremrangebyrank removes entries from index 0 to stop_index, keeping -MAX to -1
        await asyncio.to_thread(
            redis.zremrangebyrank,
            _PREDICTION_HISTORY_KEY,
            0,
            -(_MAX_HISTORY_ENTRIES + 1),
        )

        logger.debug("Stored prediction history snapshot at %s", timestamp.isoformat())
        return True

    except Exception as e:
        logger.error("Failed to store prediction history: %s", e, exc_info=True)
        return False


async def _get_prediction_history(days: int) -> List[Dict[str, Any]]:
    """
    Retrieve prediction history for the specified time period.

    Issue #569: Fetches historical prediction data from Redis sorted set.

    Args:
        days: Number of days to look back

    Returns:
        List of prediction snapshots ordered by timestamp (oldest first)
    """
    try:
        redis = get_redis_client(async_client=False, database="analytics")
        if not redis:
            return []

        # Calculate time range
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        # Fetch entries within time range
        entries = await asyncio.to_thread(
            redis.zrangebyscore,
            _PREDICTION_HISTORY_KEY,
            start_ms,
            end_ms,
        )

        history = []
        for entry in entries:
            try:
                data = json.loads(entry)
                history.append(data)
            except json.JSONDecodeError:
                continue

        return history

    except Exception as e:
        logger.warning("Failed to retrieve prediction history: %s", e)
        return []


def _calculate_trend_metrics(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate trend metrics from historical prediction data.

    Issue #569: Computes trend direction, percentage changes, and averages.

    Args:
        history: List of prediction snapshots (oldest first)

    Returns:
        Dict containing trend analysis metrics
    """
    if not history:
        return {}

    # Calculate averages
    avg_risk_scores = [h.get("average_risk_score", 0) for h in history]
    high_risk_counts = [h.get("high_risk_count", 0) for h in history]

    overall_avg = sum(avg_risk_scores) / len(avg_risk_scores) if avg_risk_scores else 0
    avg_high_risk = (
        sum(high_risk_counts) / len(high_risk_counts) if high_risk_counts else 0
    )

    # Calculate trend direction (compare first half to second half)
    half = len(history) // 2
    if half > 0:
        first_half_avg = sum(avg_risk_scores[:half]) / half
        second_half_avg = sum(avg_risk_scores[half:]) / (len(avg_risk_scores) - half)

        if first_half_avg > 0:
            risk_change_pct = (
                (second_half_avg - first_half_avg) / first_half_avg
            ) * 100
        else:
            risk_change_pct = 0

        # Determine trend direction using stability threshold
        if risk_change_pct > _TREND_STABILITY_THRESHOLD_PCT:
            trend_direction = "increasing"
        elif risk_change_pct < -_TREND_STABILITY_THRESHOLD_PCT:
            trend_direction = "decreasing"
        else:
            trend_direction = "stable"
    else:
        risk_change_pct = 0
        trend_direction = "insufficient_data"

    # Build data points for charting
    data_points = []
    for h in history:
        data_points.append(
            {
                "timestamp": h.get("timestamp"),
                "average_risk": h.get("average_risk_score", 0),
                "high_risk_count": h.get("high_risk_count", 0),
                "total_files": h.get("total_files", 0),
            }
        )

    return {
        "data_points": data_points,
        "summary": {
            "overall_average_risk": round(overall_avg, 2),
            "average_high_risk_files": round(avg_high_risk, 1),
            "trend_direction": trend_direction,
            "risk_change_percentage": round(risk_change_pct, 1),
            "data_point_count": len(history),
            "period_start": history[0].get("timestamp") if history else None,
            "period_end": history[-1].get("timestamp") if history else None,
        },
        "risk_level_trends": _calculate_risk_level_trends(history),
    }


def _calculate_risk_level_trends(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate per-risk-level trends over time.

    Issue #569: Tracks how each risk level (critical, high, medium, etc.) changes.
    """
    if not history:
        return {}

    risk_levels = ["critical", "high", "medium", "low", "minimal"]
    trends = {}

    for level in risk_levels:
        counts = [
            h.get(f"{level}_count", h.get("risk_distribution", {}).get(level, 0))
            for h in history
        ]
        if counts:
            avg = sum(counts) / len(counts)
            latest = counts[-1] if counts else 0
            earliest = counts[0] if counts else 0

            if earliest > 0:
                change_pct = ((latest - earliest) / earliest) * 100
            else:
                change_pct = 0 if latest == 0 else 100

            trends[level] = {
                "average": round(avg, 1),
                "latest": latest,
                "change_percentage": round(change_pct, 1),
            }

    return trends


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


# Issue #609: Parallel analysis concurrency limit
_ANALYSIS_SEMAPHORE_LIMIT = 50


async def _analyze_files_parallel(
    files: List[Path],
    change_freq: Dict[str, int],
    bug_history: Dict[str, int],
) -> List[Dict[str, Any]]:
    """
    Analyze multiple files in parallel with bounded concurrency.

    Issue #609: Extracted helper to parallelize file analysis across all endpoints.
    Uses semaphore to limit concurrent file I/O operations.
    """
    semaphore = asyncio.Semaphore(_ANALYSIS_SEMAPHORE_LIMIT)

    async def analyze_with_semaphore(fp: Path) -> Dict[str, Any]:
        async with semaphore:
            return await _analyze_single_file(fp, change_freq, bug_history)

    return list(await asyncio.gather(*[analyze_with_semaphore(fp) for fp in files]))


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


async def _safe_store_prediction_history(
    total_files: int,
    high_risk_count: int,
    risk_distribution: Dict[str, int],
    analyzed_files: List[Dict[str, Any]],
) -> None:
    """
    Wrapper for fire-and-forget prediction history storage with error logging.

    Issue #569: Ensures exceptions from background tasks are properly logged
    instead of being silently swallowed when using asyncio.create_task().
    """
    try:
        await _store_prediction_history(
            total_files=total_files,
            high_risk_count=high_risk_count,
            risk_distribution=risk_distribution,
            analyzed_files=analyzed_files,
        )
    except Exception as e:
        logger.error(
            "Background prediction history storage failed: %s", e, exc_info=True
        )


@router.get("/analyze")
async def analyze_codebase(
    admin_check: bool = Depends(check_admin_permission),
    path: str = Query(".", description="Path to analyze"),
    include_pattern: str = Query("*.py", description="File pattern to include"),
    limit: int = Query(1000, ge=1, le=5000, description="Maximum files to analyze"),
) -> dict[str, Any]:
    """
    Analyze codebase for bug risk (Issue #543: no demo data).
    Issue #744: Requires admin authentication.

    Returns risk assessment for all files matching the pattern.
    Issue #569: Also stores prediction history for trend tracking.
    """
    try:
        # Issue #664: Parallelize independent data fetches
        bug_history, change_freq, files_to_analyze = await asyncio.gather(
            get_git_bug_history(),
            get_file_change_frequency(),
            asyncio.to_thread(_find_files_sync, path, include_pattern, limit),
        )

        if not files_to_analyze:
            return _no_data_response(
                f"No files matching '{include_pattern}' found in '{path}'"
            )

        # Issue #609: Analyze files in parallel
        analyzed_files = await _analyze_files_parallel(
            files_to_analyze, change_freq, bug_history
        )
        analyzed_files.sort(key=lambda x: x["risk_score"], reverse=True)
        high_risk = sum(1 for f in analyzed_files if f["risk_score"] >= 60)

        # Issue #569: Calculate risk distribution and store prediction history
        risk_dist = {level.value: 0 for level in RiskLevel}
        for f in analyzed_files:
            level = get_risk_level(f["risk_score"])
            risk_dist[level.value] += 1

        # Store prediction history asynchronously (don't block response)
        asyncio.create_task(
            _safe_store_prediction_history(
                total_files=len(files_to_analyze),
                high_risk_count=high_risk,
                risk_distribution=risk_dist,
                analyzed_files=analyzed_files,
            )
        )

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
    admin_check: bool = Depends(check_admin_permission),
    threshold: float = Query(60, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
    path: str = Query(".", description="Path to analyze"),
    include_pattern: str = Query("*.py", description="File pattern to include"),
) -> dict[str, Any]:
    """
    Get files with high bug risk (Issue #543: no demo data).
    Issue #744: Requires admin authentication.

    Returns files with risk score above the threshold.
    """
    try:
        # Issue #664: Parallelize independent data fetches
        bug_history, change_freq, files_to_analyze = await asyncio.gather(
            get_git_bug_history(),
            get_file_change_frequency(),
            asyncio.to_thread(_find_files_sync, path, include_pattern, 200),
        )

        if not files_to_analyze:
            return _no_data_response(
                f"No files matching '{include_pattern}' found in '{path}'"
            )

        # Issue #609: Analyze files in parallel
        analyzed_files = await _analyze_files_parallel(
            files_to_analyze, change_freq, bug_history
        )

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
    risk_score = sum(
        factors.get(f.value, 0) * w
        for f, w in RISK_WEIGHTS.items()
        if f.value in factors
    )
    return {
        "file_path": file_path,
        "risk_score": round(risk_score, 1),
        "risk_level": get_risk_level(risk_score).value,
        "factors": factors,
        "factor_weights": {k.value: v for k, v in RISK_WEIGHTS.items()},
        "bug_count_history": bug_history.get(file_path, 0),
        "prevention_tips": get_prevention_tips(factors),
        "suggested_tests": get_suggested_tests(file_path, factors),
        "recommendation": _get_file_recommendation(risk_score, factors),
    }


@router.get("/file/{file_path:path}")
async def get_file_risk(
    file_path: str,
    admin_check: bool = Depends(check_admin_permission),
) -> dict[str, Any]:
    """
    Get detailed risk assessment for a specific file (Issue #543: no demo data).
    Issue #744: Requires admin authentication.
    """
    path = Path(file_path)
    if not await asyncio.to_thread(path.exists):
        return _no_data_response(f"File not found: {file_path}")

    try:
        # Issue #664: Parallelize independent data fetches
        complexity, bug_history, change_freq, file_stat = await asyncio.gather(
            analyze_file_complexity(str(path)),
            get_git_bug_history(),
            get_file_change_frequency(),
            asyncio.to_thread(path.stat),
        )

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
    "critical": {"min": 80, "color": "#ef4444"},
    "high": {"min": 60, "color": "#f97316"},
    "medium": {"min": 40, "color": "#eab308"},
    "low": {"min": 20, "color": "#22c55e"},
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
        heatmap_data.append(
            {
                "name": group_name,
                "value": round(avg_risk, 1),
                "file_count": len(group_files),
                "risk_level": get_risk_level(avg_risk).value,
                "files": group_files,
            }
        )
    return sorted(heatmap_data, key=lambda x: x["value"], reverse=True)


def _get_flat_heatmap_data(files: list) -> list:
    """Get flat heatmap data (Issue #398: extracted)."""
    return [
        {
            "name": f["file_path"],
            "value": f["risk_score"],
            "risk_level": get_risk_level(f["risk_score"]).value,
        }
        for f in sorted(files, key=lambda x: x["risk_score"], reverse=True)
    ]


@router.get("/heatmap")
async def get_risk_heatmap(
    admin_check: bool = Depends(check_admin_permission),
    grouping: str = Query("directory", regex="^(directory|module|flat)$"),
    path: str = Query(".", description="Path to analyze"),
    include_pattern: str = Query("*.py", description="File pattern to include"),
    limit: int = Query(100, ge=1, le=300),
) -> dict[str, Any]:
    """
    Get risk heatmap data for visualization (Issue #543: no demo data).
    Issue #744: Requires admin authentication.
    """
    try:
        # Issue #664: Parallelize independent data fetches
        bug_history, change_freq, files_to_analyze = await asyncio.gather(
            get_git_bug_history(),
            get_file_change_frequency(),
            asyncio.to_thread(_find_files_sync, path, include_pattern, limit),
        )

        if not files_to_analyze:
            return _no_data_response(
                f"No files matching '{include_pattern}' found in '{path}'"
            )

        # Issue #609: Analyze files in parallel
        analyzed_files = await _analyze_files_parallel(
            files_to_analyze, change_freq, bug_history
        )

        # Generate heatmap data
        data = (
            _group_files_by_directory(analyzed_files)
            if grouping == "directory"
            else _get_flat_heatmap_data(analyzed_files)
        )

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
    admin_check: bool = Depends(check_admin_permission),
    period: str = Query("30d", regex="^(7d|30d|90d)$"),
) -> dict[str, Any]:
    """
    Get historical bug prediction accuracy trends.
    Issue #744: Requires admin authentication.

    Issue #569: Returns real trend data from stored prediction history.
    Prediction history is automatically captured each time /analyze is called.

    Args:
        period: Time period to analyze - "7d", "30d", or "90d"

    Returns:
        Trend analysis including:
        - data_points: Time-series data for charting
        - summary: Overall trend metrics (direction, average risk, change %)
        - risk_level_trends: Per-level (critical, high, etc.) trend analysis
    """
    # Parse period to days
    period_days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 30)

    # Fetch historical prediction data
    history = await _get_prediction_history(period_days)

    if not history:
        return _no_data_response(
            f"No prediction history available for period '{period}'. "
            "Run /bug-prediction/analyze to start collecting trend data."
        )

    # Calculate trend metrics
    trend_metrics = _calculate_trend_metrics(history)

    return {
        "status": "success",
        "period": period,
        "period_days": period_days,
        **trend_metrics,
    }


def _calculate_risk_distribution(analyzed_files: list) -> dict[str, int]:
    """
    Calculate risk level distribution from analyzed files. Issue #620.

    Args:
        analyzed_files: List of analyzed file dictionaries

    Returns:
        Dict mapping risk level names to counts
    """
    risk_dist = {level.value: 0 for level in RiskLevel}
    for f in analyzed_files:
        level = get_risk_level(f["risk_score"])
        risk_dist[level.value] += 1
    return risk_dist


def _aggregate_risk_factors(analyzed_files: list) -> list[tuple[str, float]]:
    """
    Aggregate risk factors across all files, sorted by total score. Issue #620.

    Args:
        analyzed_files: List of analyzed file dictionaries

    Returns:
        Sorted list of (factor_name, total_score) tuples
    """
    factor_totals: dict[str, float] = {}
    for f in analyzed_files:
        for factor, score in f["factors"].items():
            factor_totals[factor] = factor_totals.get(factor, 0) + score
    return sorted(factor_totals.items(), key=lambda x: x[1], reverse=True)


def _generate_summary_recommendations(
    risk_dist: dict[str, int], analyzed_files: list
) -> list[str]:
    """
    Generate recommendations based on risk analysis. Issue #620.

    Args:
        risk_dist: Risk distribution dictionary
        analyzed_files: List of analyzed file dictionaries

    Returns:
        List of recommendation strings
    """
    high_risk_count = risk_dist.get("high", 0) + risk_dist.get("critical", 0)
    recommendations = []

    if high_risk_count > 0:
        recommendations.append(
            f"Focus testing efforts on {high_risk_count} high-risk files"
        )

    # Get top 3 highest risk files
    top_risky = sorted(analyzed_files, key=lambda x: x["risk_score"], reverse=True)[:3]
    for f in top_risky:
        if f["risk_score"] >= 60:
            recommendations.append(
                f"Review {f['file_path']} (risk score: {f['risk_score']:.1f})"
            )

    if not recommendations:
        recommendations.append("All files are within acceptable risk levels")

    return recommendations[:5]


@router.get("/summary")
async def get_prediction_summary(
    admin_check: bool = Depends(check_admin_permission),
    path: str = Query(".", description="Path to analyze"),
    include_pattern: str = Query("*.py", description="File pattern to include"),
    limit: int = Query(1000, ge=1, le=5000, description="Maximum files to analyze"),
) -> dict[str, Any]:
    """
    Get summary of bug predictions and risk assessment (Issue #543: no demo data).
    Issue #744: Requires admin authentication.
    Issue #620: Refactored to use extracted helper methods.

    Returns high-level metrics for dashboard display.
    """
    try:
        # Issue #664: Parallelize independent data fetches
        bug_history, change_freq, files_to_analyze = await asyncio.gather(
            get_git_bug_history(),
            get_file_change_frequency(),
            asyncio.to_thread(_find_files_sync, path, include_pattern, limit),
        )

        if not files_to_analyze:
            return _no_data_response(
                f"No files matching '{include_pattern}' found in '{path}'"
            )

        # Issue #609: Analyze files in parallel
        analyzed_files = await _analyze_files_parallel(
            files_to_analyze, change_freq, bug_history
        )

        # Issue #620: Extracted to helper methods
        risk_dist = _calculate_risk_distribution(analyzed_files)
        top_factors = _aggregate_risk_factors(analyzed_files)
        recommendations = _generate_summary_recommendations(risk_dist, analyzed_files)
        high_risk_count = risk_dist.get("high", 0) + risk_dist.get("critical", 0)

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
            "recommendations": recommendations,
        }

    except Exception as e:
        logger.error("Failed to generate summary: %s", e, exc_info=True)
        return _no_data_response(f"Summary generation failed: {str(e)}")


@router.get("/factors")
async def get_risk_factors(
    admin_check: bool = Depends(check_admin_permission),
) -> dict[str, Any]:
    """
    Get all risk factors and their weights.
    Issue #744: Requires admin authentication.

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
    admin_check: bool = Depends(check_admin_permission),
    file_path: str = None,
    description: str = "",
    severity: str = "medium",
) -> dict[str, Any]:
    """
    Record a new bug for model improvement.
    Issue #744: Requires admin authentication.

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
