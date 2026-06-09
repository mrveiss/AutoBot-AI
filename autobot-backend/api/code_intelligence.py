# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Code Intelligence API Endpoints

Provides REST API for code analysis features including:
- Anti-pattern detection
- Code smell identification
- Codebase health metrics

Part of Issue #221 - Anti-Pattern Detection System
Parent Epic: #217 - Advanced Code Intelligence
"""

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from api.schemas_code import (
    CachedSecurityScoreResponse,
    ClearStuckResponse,
    CodeIntelAnalysisRequest,
    CodeIntelAnalysisResultResponse,
    CodeIntelHealthScoreResultResponse,
    CodeIntelligenceTaskStatusResponse,
    CodeIntelPatternTypesResultResponse,
    CodeIntelQuickScanRequest,
    CodeIntelScanFileResultResponse,
    CodeIntelSuggestionsRequest,
    EvolutionAnalyzeResultResponse,
    EvolutionPatternsResultResponse,
    EvolutionRefactoringsResultResponse,
    EvolutionReportResultResponse,
    EvolutionTimelineResultResponse,
    FindingsPlaceholderResponse,
    PerformanceAnalysisRequest,
    PerformanceAnalyzeResultResponse,
    PerformanceFileScanRequest,
    PerformanceIssueTypesResultResponse,
    PerformanceScanFileResultResponse,
    PerformanceScoreResultResponse,
    RedisAnalysisRequest,
    RedisAnalyzeResultResponse,
    RedisFileScanRequest,
    RedisHealthScoreResultResponse,
    RedisOptimizationTypesResultResponse,
    RedisScanFileResultResponse,
    SecurityAnalysisRequest,
    SecurityAnalyzeResultResponse,
    SecurityFileScanRequest,
    SecurityScanFileResultResponse,
    SecurityScoreResultResponse,
    SecurityVulnTypesResultResponse,
    StartTaskResponse,
    SuggestionsResponse,
)
from api.schemas_common import DataResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import parse_utc_iso
from code_intelligence.anti_pattern_detector import (
    AntiPatternDetector,
    AntiPatternSeverity,
)
from code_intelligence.performance_analyzer import (
    PerformanceAnalyzer,
    PerformanceSeverity,
    get_performance_issue_types,
)
from code_intelligence.redis_optimizer import OptimizationSeverity, RedisOptimizer
from code_intelligence.security_analyzer import (
    SecurityAnalyzer,
    SecuritySeverity,
    get_vulnerability_types,
)
from constants.ttl_constants import TTL_5_MINUTES
from tasks.analytics_tasks import run_security_analysis
from utils.catalog_http_exceptions import raise_internal_error, raise_invalid_input, raise_not_found
from utils.celery_task_status import celery_result_to_status, get_latest_task_result, store_latest_task_id

logger = get_logger(__name__)


router = APIRouter()

_REDIS_PREFIX = "sec_task:"

# Issue #380: Module-level tuple for severity ordering (used in 4 endpoints)
_SEVERITY_ORDER = ("info", "low", "medium", "high", "critical")

# Issue #281: Pattern type definitions extracted from get_supported_pattern_types
# This enables reuse and reduces function length
PATTERN_TYPE_DEFINITIONS = {
    # Bloaters
    "god_class": {
        "name": "God Class",
        "category": "bloater",
        "description": "Class with too many methods or responsibilities",
        "threshold": f">{AntiPatternDetector.GOD_CLASS_METHOD_THRESHOLD} methods "
        f"or >{AntiPatternDetector.GOD_CLASS_LINE_THRESHOLD} lines",
    },
    "long_method": {
        "name": "Long Method",
        "category": "bloater",
        "description": "Function with too many lines",
        "threshold": f">{AntiPatternDetector.LONG_METHOD_THRESHOLD} lines",
    },
    "long_parameter_list": {
        "name": "Long Parameter List",
        "category": "bloater",
        "description": "Function with too many parameters",
        "threshold": f">{AntiPatternDetector.LONG_PARAMETER_THRESHOLD} parameters",
    },
    "large_file": {
        "name": "Large File",
        "category": "bloater",
        "description": "File with excessive lines of code",
        "threshold": f">{AntiPatternDetector.LARGE_FILE_THRESHOLD} lines",
    },
    "deep_nesting": {
        "name": "Deep Nesting",
        "category": "bloater",
        "description": "Code with excessive nesting levels",
        "threshold": f">{AntiPatternDetector.DEEP_NESTING_THRESHOLD} levels",
    },
    "data_clumps": {
        "name": "Data Clumps",
        "category": "bloater",
        "description": "Groups of parameters that always appear together",
        "threshold": "3+ common parameters across functions",
    },
    # Couplers
    "circular_dependency": {
        "name": "Circular Dependency",
        "category": "coupler",
        "description": "Modules that import each other in a cycle",
        "threshold": "Any cycle detected",
    },
    "feature_envy": {
        "name": "Feature Envy",
        "category": "coupler",
        "description": "Method uses another object's data more than its own",
        "threshold": "More external accesses than self accesses",
    },
    "message_chains": {
        "name": "Message Chains",
        "category": "coupler",
        "description": "Long chains of method calls (a.b().c().d())",
        "threshold": f">{AntiPatternDetector.MESSAGE_CHAIN_THRESHOLD} chained calls",
    },
    # Dispensables
    "dead_code": {
        "name": "Dead Code",
        "category": "dispensable",
        "description": "Unreachable or unused code",
        "threshold": "Code after return/raise, empty except blocks",
    },
    "lazy_class": {
        "name": "Lazy Class",
        "category": "dispensable",
        "description": "Class that does too little",
        "threshold": f"<={AntiPatternDetector.LAZY_CLASS_METHOD_THRESHOLD} methods",
    },
    # Naming Issues
    "inconsistent_naming": {
        "name": "Inconsistent Naming",
        "category": "naming",
        "description": "Mixed naming conventions (snake_case vs camelCase)",
        "threshold": ">20% mixing of styles",
    },
    "single_letter_variable": {
        "name": "Single Letter Variable",
        "category": "naming",
        "description": "Non-descriptive single-letter variable names",
        "threshold": "Single letter (except i,j,k,n,x,y,z in loops)",
    },
    "magic_number": {
        "name": "Magic Number",
        "category": "naming",
        "description": "Unexplained numeric literals repeated in code",
        "threshold": f"Same number appears >{AntiPatternDetector.MAGIC_NUMBER_THRESHOLD} times",
    },
    # Other
    "complex_conditional": {
        "name": "Complex Conditional",
        "category": "other",
        "description": "Overly complex boolean expressions",
        "threshold": f">{AntiPatternDetector.COMPLEX_CONDITIONAL_THRESHOLD} conditions",
    },
    "missing_docstring": {
        "name": "Missing Docstring",
        "category": "other",
        "description": "Public function or class without documentation",
        "threshold": "No docstring on public entity",
    },
}

# Issue #281: Redis optimization type definitions extracted from get_redis_optimization_types
# This enables reuse and reduces function length
REDIS_OPTIMIZATION_TYPES = {
    # Pipeline opportunities
    "sequential_gets": {
        "name": "Sequential GETs",
        "category": "pipeline",
        "description": "Multiple GET operations that can be batched with MGET or pipeline",
        "recommendation": "Use redis.mget(keys) or pipeline() for batching",
    },
    "sequential_sets": {
        "name": "Sequential SETs",
        "category": "pipeline",
        "description": "Multiple SET operations that can be batched with MSET or pipeline",
        "recommendation": "Use redis.mset(mapping) or pipeline() for batching",
    },
    "loop_operations": {
        "name": "Loop Operations",
        "category": "pipeline",
        "description": "Redis operations inside loops causing O(N) network round-trips",
        "recommendation": "Collect keys first, then batch with pipeline()",
    },
    # Lua script candidates
    "read_modify_write": {
        "name": "Read-Modify-Write",
        "category": "lua_script",
        "description": "GET followed by SET - race condition risk",
        "recommendation": "Use Lua script or WATCH/MULTI/EXEC for atomicity",
    },
    "conditional_set": {
        "name": "Conditional SET",
        "category": "lua_script",
        "description": "SET based on condition - potential race",
        "recommendation": "Use SETNX, SET NX, or Lua script",
    },
    # Data structure optimizations
    "string_to_hash": {
        "name": "String to Hash",
        "category": "data_structure",
        "description": "Multiple related string keys could be a Hash",
        "recommendation": "Use HSET/HGET with single key for related data",
    },
    "inefficient_scan": {
        "name": "Inefficient Scan",
        "category": "data_structure",
        "description": "KEYS command blocks Redis - use SCAN instead",
        "recommendation": "Replace KEYS with SCAN for non-blocking iteration",
    },
    "missing_expiry": {
        "name": "Missing Expiry",
        "category": "data_structure",
        "description": "SET without TTL - potential memory leak",
        "recommendation": "Add ex=<seconds> parameter to SET operations",
    },
    # Connection patterns
    "connection_per_request": {
        "name": "Connection Per Request",
        "category": "connection",
        "description": "Direct redis.Redis() instantiation - should use pool",  # noqa: redis
        "recommendation": "Use get_redis_client() from autobot_shared.redis_client",
    },
    "blocking_in_async": {
        "name": "Blocking in Async",
        "category": "connection",
        "description": "Sync Redis calls in async function - blocks event loop",
        "recommendation": "Use async Redis client with await",
    },
    # Cache patterns
    "cache_stampede_risk": {
        "name": "Cache Stampede Risk",
        "category": "cache",
        "description": "Cache miss pattern without lock protection",
        "recommendation": "Use distributed lock or probabilistic early expiration",
    },
}

# Issue #281: Redis optimization categories
REDIS_OPTIMIZATION_CATEGORIES = (
    "pipeline",
    "lua_script",
    "data_structure",
    "connection",
    "cache",
)


# =============================================================================
# Helper Functions for Score Grading (Issue #315 - extracted/refactored)
# =============================================================================


def _calculate_grade_from_score(score: float) -> str:
    """
    Calculate letter grade from numeric score.

    (Issue #315 - extracted/refactored)

    Args:
        score: Numeric score from 0-100

    Returns:
        Letter grade: A, B, C, D, or F
    """
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _get_redis_status_message(score: float) -> str:
    """
    Get status message for Redis health score.

    (Issue #315 - extracted/refactored)

    Args:
        score: Redis health score from 0-100

    Returns:
        Human-readable status message
    """
    if score >= 90:
        return "Excellent Redis usage patterns"
    if score >= 80:
        return "Good Redis usage with minor improvements possible"
    if score >= 70:
        return "Fair Redis usage - several optimizations recommended"
    if score >= 60:
        return "Poor Redis usage - significant optimization needed"
    return "Critical Redis usage issues - immediate attention required"


def _get_security_status_message(score: float) -> str:
    """
    Get status message for security score.

    (Issue #315 - extracted/refactored)

    Args:
        score: Security score from 0-100

    Returns:
        Human-readable status message
    """
    if score >= 90:
        return "Excellent security posture"
    if score >= 80:
        return "Good security with minor issues"
    if score >= 70:
        return "Fair security - several vulnerabilities to address"
    if score >= 50:
        return "Poor security - significant vulnerabilities present"
    return "Critical security issues - immediate attention required"


def _get_performance_status_message(score: float) -> str:
    """
    Get status message for performance score.

    (Issue #315 - extracted/refactored)

    Args:
        score: Performance score from 0-100

    Returns:
        Human-readable status message
    """
    if score >= 90:
        return "Excellent performance - minimal issues"
    if score >= 80:
        return "Good performance with minor optimizations possible"
    if score >= 70:
        return "Fair performance - several optimizations recommended"
    if score >= 50:
        return "Performance issues detected - optimization needed"
    return "Critical performance problems - immediate action required"


def _calculate_health_score(anti_patterns: list) -> float:
    """
    Calculate health score from list of anti-patterns.

    Issue #686: Uses exponential decay scoring to prevent score overflow.
    Scores now degrade gracefully instead of immediately hitting 0.

    Args:
        anti_patterns: List of detected anti-patterns

    Returns:
        Health score from 1-100
    """
    from code_intelligence.shared.scoring import calculate_exponential_score

    # Calculate weighted deduction
    severity_penalties = {
        AntiPatternSeverity.INFO: 0.5,
        AntiPatternSeverity.LOW: 1,
        AntiPatternSeverity.MEDIUM: 2,
        AntiPatternSeverity.HIGH: 4,
        AntiPatternSeverity.CRITICAL: 8,
    }

    total_deduction = 0.0
    for pattern in anti_patterns:
        penalty = severity_penalties.get(pattern.severity, 1)
        total_deduction += penalty

    # Issue #686: Use exponential decay instead of linear deduction
    return calculate_exponential_score(total_deduction)


def _calculate_redis_health_score(results: list) -> float:
    """
    Calculate Redis health score from optimization results.

    Issue #686: Uses exponential decay scoring to prevent score overflow.
    Scores now degrade gracefully instead of immediately hitting 0.

    Args:
        results: List of Redis optimization findings

    Returns:
        Health score from 1-100
    """
    from code_intelligence.shared.scoring import calculate_exponential_score

    # Calculate weighted deduction
    severity_penalties = {
        OptimizationSeverity.INFO: 0.5,
        OptimizationSeverity.LOW: 1,
        OptimizationSeverity.MEDIUM: 2,
        OptimizationSeverity.HIGH: 4,
        OptimizationSeverity.CRITICAL: 8,
    }

    total_deduction = 0.0
    for result in results:
        penalty = severity_penalties.get(result.severity, 1)
        total_deduction += penalty

    # Issue #686: Use exponential decay instead of linear deduction
    return calculate_exponential_score(total_deduction)


async def _validate_analysis_path(path: str) -> None:
    """
    Validate that a path exists and is a directory.

    Issue #665: Extracted from security_analyze and performance_analyze.

    Args:
        path: Path to validate

    Raises:
        HTTPException: If path doesn't exist or isn't a directory
    """
    path_exists = await asyncio.to_thread(os.path.exists, path)
    if not path_exists:
        raise_invalid_input("path", f"does not exist: {path}")

    is_dir = await asyncio.to_thread(os.path.isdir, path)
    if not is_dir:
        raise_invalid_input("path", f"not a directory: {path}")


def _filter_results_by_severity(results: list, min_severity: str | None) -> list:
    """
    Filter analysis results by minimum severity level.

    Issue #665: Extracted from security_analyze and performance_analyze.

    Args:
        results: List of analysis result objects with severity attribute
        min_severity: Minimum severity level to include

    Returns:
        Filtered list of results
    """
    if not min_severity:
        return results

    try:
        min_idx = _SEVERITY_ORDER.index(min_severity.lower())
        return [r for r in results if _SEVERITY_ORDER.index(r.severity.value) >= min_idx]
    except ValueError as e:
        logger.debug("Value parsing failed during severity filtering: %s", e)
        return results


# =============================================================================
# Helper Functions for Endpoint Refactoring (Issue #620)
# =============================================================================


async def _validate_path_exists(path: str) -> None:
    """
    Validate that a path exists on the filesystem.

    Raises HTTPException with 400 status if path does not exist.
    Issue #620.

    Args:
        path: Filesystem path to validate

    Raises:
        HTTPException: If path does not exist
    """
    path_exists = await asyncio.to_thread(os.path.exists, path)
    if not path_exists:
        raise_invalid_input("path", f"does not exist: {path}")


async def _validate_path_is_directory(path: str) -> None:
    """
    Validate that a path is a directory.

    Raises HTTPException with 400 status if path is not a directory.
    Issue #620.

    Args:
        path: Filesystem path to validate

    Raises:
        HTTPException: If path is not a directory
    """
    is_dir = await asyncio.to_thread(os.path.isdir, path)
    if not is_dir:
        raise_invalid_input("path", f"not a directory: {path}")


def _filter_antipatterns_by_severity(
    anti_patterns: list,
    min_severity: str | None,
) -> list:
    """
    Filter anti-patterns by minimum severity level.

    Issue #620.

    Args:
        anti_patterns: List of detected anti-patterns
        min_severity: Minimum severity level to include

    Returns:
        Filtered list of anti-patterns
    """
    if not min_severity:
        return anti_patterns

    try:
        min_idx = _SEVERITY_ORDER.index(min_severity.lower())
        return [p for p in anti_patterns if _SEVERITY_ORDER.index(p.severity.value) >= min_idx]
    except ValueError:
        logger.warning("Invalid severity filter: %s", min_severity)
        return anti_patterns


async def _run_redis_analysis(
    optimizer: RedisOptimizer,
    path: str,
    exclude_patterns: list | None,
) -> list:
    """
    Execute Redis analysis on file or directory.

    Issue #620.

    Args:
        optimizer: RedisOptimizer instance
        path: Path to analyze
        exclude_patterns: Patterns to exclude from analysis

    Returns:
        List of optimization results
    """
    is_file = await asyncio.to_thread(os.path.isfile, path)
    if is_file:
        return await asyncio.to_thread(optimizer.analyze_file, path)
    return await asyncio.to_thread(
        optimizer.analyze_directory,
        path,
        exclude_patterns=exclude_patterns,
    )


def _filter_redis_results_by_severity(
    results: list,
    min_severity: str | None,
) -> list:
    """
    Filter Redis optimization results by minimum severity level.

    Issue #620.

    Args:
        results: List of Redis optimization results
        min_severity: Minimum severity level to include

    Returns:
        Filtered list of results
    """
    if not min_severity:
        return results

    try:
        min_idx = _SEVERITY_ORDER.index(min_severity.lower())
        return [r for r in results if _SEVERITY_ORDER.index(r.severity.value) >= min_idx]
    except ValueError:
        logger.warning("Invalid severity filter: %s", min_severity)
        return results


def _build_redis_analysis_response(
    path: str,
    results: list,
    summary: dict,
) -> dict:
    """
    Build JSON response content for Redis analysis endpoint.

    Issue #620.

    Args:
        path: Analyzed path
        results: List of optimization results
        summary: Analysis summary from optimizer

    Returns:
        Response content dictionary
    """
    return {
        "status": "success",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "path": path,
        "optimizations": [r.to_dict() for r in results],
        "summary": summary,
    }


async def _generate_report_response(
    analyzer,
    path: str,
    format_type: str,
) -> JSONResponse:
    """
    Generate report response in requested format (json or markdown).

    Issue #620.

    Args:
        analyzer: Analyzer instance with generate_report method
        path: Analyzed path
        format_type: Report format ('json' or 'markdown')

    Returns:
        JSONResponse with report content
    """
    report = await asyncio.to_thread(analyzer.generate_report, format=format_type)

    if format_type == "markdown":
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "path": path,
                "format": "markdown",
                "report": report,
            },
        )

    import json as json_module

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "path": path,
            "format": "json",
            "report": json_module.loads(report),
        },
    )


@router.post("/analyze", response_model=DataResponse[CodeIntelAnalysisResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_codebase",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def analyze_codebase(
    request: CodeIntelAnalysisRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Analyze code for anti-patterns and quality issues.

    Accepts either a directory path for bulk analysis or inline code.
    Issue #1008: Added inline code analysis support.
    """
    # Inline code analysis (frontend sends {code, language, filename})
    if request.code is not None:
        return _analyze_inline_code(request)

    # Directory-based analysis (original behavior)
    if not request.path:
        raise_invalid_input("path", "either 'path' or 'code' must be provided")
    await _validate_path_exists(request.path)
    await _validate_path_is_directory(request.path)

    try:
        detector = AntiPatternDetector(exclude_dirs=request.exclude_dirs)
        report = await asyncio.to_thread(detector.analyze_directory, request.path)
        report.anti_patterns = _filter_antipatterns_by_severity(
            report.anti_patterns,
            request.min_severity,
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "report": report.to_dict(),
            },
        )

    except Exception as e:
        logger.error("Analysis failed: %s", e)
        raise_internal_error("Analysis failed")


def _analyze_inline_code(request: CodeIntelAnalysisRequest) -> JSONResponse:
    """Analyze inline code snippet. Issue #1008."""
    code = request.code
    lines = code.split("\n")
    line_count = len(lines)
    language = request.language or "python"

    # Basic metrics computation
    non_empty = [ln for ln in lines if ln.strip()]
    comment_lines = [ln for ln in lines if ln.strip().startswith("#")]
    comment_ratio = len(comment_lines) / len(non_empty) if non_empty else 0.0

    # Count functions and classes
    func_count = sum(1 for ln in lines if ln.strip().startswith("def "))
    class_count = sum(1 for ln in lines if ln.strip().startswith("class "))

    # Quality scoring heuristic
    quality_score = 85.0
    issues = []
    if line_count > 300:
        quality_score -= 10
        issues.append(
            {
                "severity": "medium",
                "category": "quality",
                "message": "File exceeds 300 lines",
            }
        )
    if func_count > 0:
        avg_func_len = line_count / func_count
        if avg_func_len > 50:
            quality_score -= 5
            issues.append(
                {
                    "severity": "low",
                    "category": "quality",
                    "message": "Average function length exceeds 50 lines",
                }
            )

    return JSONResponse(
        status_code=200,
        content={
            "id": f"inline-{datetime.now(tz=timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "code": code[:500],
            "language": language,
            "filename": request.filename or "inline",
            "metrics": {
                "lines_of_code": line_count,
                "cyclomatic_complexity": func_count + 1,
                "maintainability_index": quality_score,
                "code_duplication_percent": 0.0,
                "comment_ratio": round(comment_ratio, 3),
                "function_count": func_count,
                "class_count": class_count,
            },
            "quality_score": quality_score,
            "issues": issues,
            "suggestions": [],
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    )


@router.post("/suggestions", response_model=SuggestionsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_suggestions",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_code_suggestions(
    request: CodeIntelSuggestionsRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """Return code improvement suggestions. Issue #1006."""
    lines = request.code.split("\n")
    suggestions = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") and len(stripped) > 80:
            suggestions.append(
                {
                    "id": f"sug-{i}",
                    "type": "style",
                    "priority": "low",
                    "title": "Long function signature",
                    "description": f"Line {i + 1} is long",
                    "impact": "readability",
                }
            )
    return {"suggestions": suggestions}


@router.post("/scan-file", response_model=DataResponse[CodeIntelScanFileResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="quick_scan_file",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def quick_scan_file(
    request: CodeIntelQuickScanRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Quick scan a single Python file for anti-patterns.

    Issue #744: Requires admin authentication.

    Faster than full codebase analysis when you only need
    to check one file.
    """
    file_exists = await asyncio.to_thread(os.path.exists, request.file_path)
    if not file_exists:
        raise_invalid_input("file_path", f"does not exist: {request.file_path}")

    if not request.file_path.endswith(".py"):
        raise_invalid_input("file_path", "only Python (.py) files are supported")

    try:
        detector = AntiPatternDetector()
        results = await asyncio.to_thread(detector.analyze_file, request.file_path)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "file_path": request.file_path,
                "patterns": [p.to_dict() for p in results["patterns"]],
                "statistics": {
                    "class_count": results["class_count"],
                    "function_count": results["function_count"],
                    "issues_found": len(results["patterns"]),
                },
            },
        )

    except Exception as e:
        logger.error("File scan failed: %s", e)
        raise_internal_error("Scan failed")


@router.get("/health-score", response_model=DataResponse[CodeIntelHealthScoreResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_health_score",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_codebase_health_score(
    path: str = Query(..., description="Directory path to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get a simple health score for a codebase.

    Issue #744: Requires admin authentication.

    Returns a score from 0-100 based on the number and severity
    of anti-patterns detected.
    """
    path_exists = await asyncio.to_thread(os.path.exists, path)
    if not path_exists:
        raise_invalid_input("path", f"does not exist: {path}")

    try:
        detector = AntiPatternDetector()
        report = await asyncio.to_thread(detector.analyze_directory, path)

        # Calculate health score
        score = _calculate_health_score(report.anti_patterns)

        # Determine grade using extracted helper
        grade = _calculate_grade_from_score(score)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "path": path,
                "health_score": round(score, 1),
                "grade": grade,
                "total_issues": len(report.anti_patterns),
                "files_analyzed": report.total_files,
                "severity_breakdown": report.severity_distribution,
            },
        )

    except Exception as e:
        logger.error("Health score calculation failed: %s", e)
        raise_internal_error("Health check failed")


@router.get("/pattern-types", response_model=DataResponse[CodeIntelPatternTypesResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_supported_pattern_types",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_supported_pattern_types(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get list of supported anti-pattern types.

    Issue #744: Requires admin authentication.
    Issue #281: Refactored to use module-level PATTERN_TYPE_DEFINITIONS constant.
    Reduced from 120 lines to ~15 lines.

    Returns all pattern types that the detector can identify,
    along with their descriptions and thresholds.
    """
    # Issue #281: Use module-level constant for pattern definitions
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "pattern_types": PATTERN_TYPE_DEFINITIONS,
            "total_types": len(PATTERN_TYPE_DEFINITIONS),
        },
    )


# =============================================================================
# Redis Optimization Endpoints (Issue #220)
# =============================================================================


@router.post("/redis/analyze", response_model=DataResponse[RedisAnalyzeResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_redis_usage_endpoint",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def analyze_redis_usage_endpoint(
    request: RedisAnalysisRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Analyze Redis usage patterns in a codebase.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored using Extract Method pattern.

    Identifies optimization opportunities including pipeline opportunities,
    Lua script candidates, data structure improvements, connection management
    patterns, and cache invalidation strategies.

    Part of Issue #220 - Redis Operation Optimizer
    """
    await _validate_path_exists(request.path)

    try:
        optimizer = RedisOptimizer(project_root=request.path)
        results = await _run_redis_analysis(
            optimizer,
            request.path,
            request.exclude_patterns,
        )
        results = _filter_redis_results_by_severity(results, request.min_severity)

        optimizer.results = results
        summary = optimizer.get_summary()
        response_content = _build_redis_analysis_response(request.path, results, summary)

        return JSONResponse(status_code=200, content=response_content)

    except Exception as e:
        logger.error("Redis analysis failed: %s", e)
        raise_internal_error("Redis analysis failed")


@router.post("/redis/scan-file", response_model=DataResponse[RedisScanFileResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_redis_file",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def scan_redis_file(
    request: RedisFileScanRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Quick scan a single Python file for Redis optimization opportunities.

    Issue #744: Requires admin authentication.

    Faster than full codebase analysis when you only need
    to check one file's Redis usage.
    """
    file_exists = await asyncio.to_thread(os.path.exists, request.file_path)
    if not file_exists:
        raise_invalid_input("file_path", f"does not exist: {request.file_path}")

    if not request.file_path.endswith(".py"):
        raise_invalid_input("file_path", "only Python (.py) files are supported")

    try:
        optimizer = RedisOptimizer()
        results = await asyncio.to_thread(optimizer.analyze_file, request.file_path)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "file_path": request.file_path,
                "optimizations": [r.to_dict() for r in results],
                "total_findings": len(results),
                "severity_breakdown": {
                    sev.value: len([r for r in results if r.severity == sev]) for sev in OptimizationSeverity
                },
            },
        )

    except Exception as e:
        logger.error("Redis file scan failed: %s", e)
        raise_internal_error("Scan failed")


@router.get("/redis/optimization-types", response_model=DataResponse[RedisOptimizationTypesResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_optimization_types",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_redis_optimization_types(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get list of supported Redis optimization types.

    Issue #744: Requires admin authentication.
    Issue #281: Refactored to use module-level REDIS_OPTIMIZATION_TYPES and
    REDIS_OPTIMIZATION_CATEGORIES constants. Reduced from 96 lines to ~15 lines.

    Returns all optimization types that the analyzer can identify,
    along with their descriptions and recommendations.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "optimization_types": REDIS_OPTIMIZATION_TYPES,
            "total_types": len(REDIS_OPTIMIZATION_TYPES),
            "categories": list(REDIS_OPTIMIZATION_CATEGORIES),
        },
    )


# Issue #1034: TTL cache for Redis health score (path -> (timestamp, response))
_redis_health_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_REDIS_HEALTH_CACHE_TTL = TTL_5_MINUTES
_REDIS_HEALTH_TIMEOUT = 30.0  # seconds


@router.get("/redis/health-score", response_model=DataResponse[RedisHealthScoreResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_usage_health_score",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_redis_usage_health_score(
    path: str = Query(..., description="Directory path to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get a Redis usage health score for a codebase.

    Issue #744: Requires admin authentication.
    Issue #1034: Cached with TTL + timeout to prevent 504s.

    Returns a score from 0-100 based on the number and severity
    of optimization opportunities detected.
    """
    path_exists = await asyncio.to_thread(os.path.exists, path)
    if not path_exists:
        raise_invalid_input("path", f"does not exist: {path}")

    # Issue #1034: Return cached result if still valid
    cached = _redis_health_cache.get(path)
    if cached and (time.monotonic() - cached[0]) < _REDIS_HEALTH_CACHE_TTL:
        return JSONResponse(status_code=200, content=cached[1])

    try:
        response_content = await asyncio.wait_for(
            _run_redis_health_analysis(path),
            timeout=_REDIS_HEALTH_TIMEOUT,
        )
        _redis_health_cache[path] = (time.monotonic(), response_content)
        return JSONResponse(status_code=200, content=response_content)

    except asyncio.TimeoutError:
        logger.warning(
            "Redis health analysis timed out after %.0fs for %s",
            _REDIS_HEALTH_TIMEOUT,
            path,
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"Analysis timed out after {int(_REDIS_HEALTH_TIMEOUT)}s. "
                "The codebase may be too large for real-time scanning."
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Redis health score calculation failed: %s", e)
        raise_internal_error("Health check failed")


async def _run_redis_health_analysis(path: str) -> Dict[str, Any]:
    """Run Redis health analysis in a thread. Issue #1034."""
    optimizer = RedisOptimizer(project_root=path)
    results = await asyncio.to_thread(optimizer.analyze_directory, path)

    score = _calculate_redis_health_score(results)
    grade = _calculate_grade_from_score(score)
    status = _get_redis_status_message(score)

    return {
        "status": "success",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "path": path,
        "health_score": round(score, 1),
        "grade": grade,
        "status_message": status,
        "total_optimizations": len(results),
        "files_with_issues": len(set(r.file_path for r in results)),
        "severity_breakdown": {
            sev.value: len([r for r in results if r.severity == sev]) for sev in OptimizationSeverity
        },
        "category_breakdown": optimizer.get_summary().get("by_type", {}),
    }


# ============================================================================
# Security Analysis Endpoints (Issue #219)
# ============================================================================


@router.post("/security/analyze", response_model=DataResponse[SecurityAnalyzeResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="security_analyze",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def security_analyze(
    request: SecurityAnalysisRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Analyze a codebase for security vulnerabilities.

    Issue #744: Requires admin authentication.
    Issue #665: Refactored to use helper functions.

    Scans all Python files in the specified directory for:
    - SQL injection patterns
    - Hardcoded secrets and credentials
    - Weak cryptography usage
    - Command injection risks
    - Insecure deserialization
    - Missing input validation
    - And more (OWASP Top 10 mapping)
    """
    await _validate_analysis_path(request.path)

    try:
        analyzer = SecurityAnalyzer(
            project_root=request.path,
            exclude_patterns=request.exclude_patterns,
        )
        results = await asyncio.to_thread(analyzer.analyze_directory)
        results = _filter_results_by_severity(results, request.min_severity)
        summary = analyzer.get_summary()

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "path": request.path,
                "summary": summary,
                "findings": [r.to_dict() for r in results],
                "total_findings": len(results),
            },
        )

    except Exception as e:
        logger.error("Security analysis failed: %s", e)
        raise_internal_error("Security analysis failed")


@router.post("/security/scan-file", response_model=DataResponse[SecurityScanFileResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="security_scan_file",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def security_scan_file(
    request: SecurityFileScanRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Scan a single file for security vulnerabilities.

    Issue #744: Requires admin authentication.

    Quick scan of a single Python file for security issues.
    """
    file_exists = await asyncio.to_thread(os.path.exists, request.file_path)
    if not file_exists:
        raise_invalid_input("file_path", f"does not exist: {request.file_path}")

    if not request.file_path.endswith(".py"):
        raise_invalid_input("file_path", "only Python files (.py) are supported")

    try:
        analyzer = SecurityAnalyzer()
        results = await asyncio.to_thread(analyzer.analyze_file, request.file_path)

        # Group by vulnerability type
        by_type = {}
        for result in results:
            vtype = result.vulnerability_type.value
            if vtype not in by_type:
                by_type[vtype] = []
            by_type[vtype].append(result.to_dict())

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "file": request.file_path,
                "findings": [r.to_dict() for r in results],
                "total_findings": len(results),
                "by_type": by_type,
                "severity_counts": {
                    sev.value: len([r for r in results if r.severity == sev]) for sev in SecuritySeverity
                },
            },
        )

    except Exception as e:
        logger.error("Security file scan failed: %s", e)
        raise_internal_error("File scan failed")


@router.get("/security/vulnerability-types", response_model=DataResponse[SecurityVulnTypesResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_vulnerability_types",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def list_vulnerability_types(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get all supported vulnerability types with OWASP mappings.

    Issue #744: Requires admin authentication.

    Returns list of all vulnerability types that can be detected,
    along with their OWASP Top 10 2021 category mappings.
    """
    vuln_types = get_vulnerability_types()

    # Group by OWASP category
    by_owasp = {}
    for vt in vuln_types:
        owasp = vt["owasp"]
        if owasp not in by_owasp:
            by_owasp[owasp] = []
        by_owasp[owasp].append(vt["type"])

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "vulnerability_types": vuln_types,
            "total_types": len(vuln_types),
            "by_owasp_category": by_owasp,
        },
    )


@router.get("/security/score", response_model=DataResponse[SecurityScoreResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_security_score",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_security_score(
    path: str = Query(..., description="Directory path to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get security health score for a codebase.

    Issue #744: Requires admin authentication.

    Returns a score from 0-100 based on the number and severity
    of security vulnerabilities detected. Higher scores indicate
    better security posture.
    """
    path_exists = await asyncio.to_thread(os.path.exists, path)
    if not path_exists:
        raise_invalid_input("path", f"does not exist: {path}")

    try:
        analyzer = SecurityAnalyzer(project_root=path)
        await asyncio.to_thread(analyzer.analyze_directory)
        summary = analyzer.get_summary()

        # Generate grade and status using extracted helpers
        score = summary["security_score"]
        grade = _calculate_grade_from_score(score)
        status = _get_security_status_message(score)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "path": path,
                "security_score": score,
                "grade": grade,
                "risk_level": summary["risk_level"],
                "status_message": status,
                "total_findings": summary["total_findings"],
                "critical_issues": summary["critical_issues"],
                "high_issues": summary["high_issues"],
                "files_analyzed": summary["files_analyzed"],
                "severity_breakdown": summary["by_severity"],
                "owasp_breakdown": summary["by_owasp_category"],
            },
        )

    except Exception as e:
        logger.error("Security score calculation failed: %s", e)
        raise_internal_error("Security score calculation failed")


@router.get("/security/report", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_security_report",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_security_report(
    path: str = Query(..., description="Directory path to analyze"),
    format: str = Query(default="json", description="Report format: json or markdown"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Generate a comprehensive security report.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored using Extract Method pattern.

    Returns a detailed security analysis report including executive summary,
    all findings with remediation advice, OWASP Top 10 mapping, and
    top recommendations.
    """
    await _validate_path_exists(path)

    try:
        analyzer = SecurityAnalyzer(project_root=path)
        await asyncio.to_thread(analyzer.analyze_directory)
        return await _generate_report_response(analyzer, path, format)

    except Exception as e:
        logger.error("Security report generation failed: %s", e)
        raise_internal_error("Report generation failed")


# ============================================================================
# Performance Analysis Endpoints (Issue #222)
# ============================================================================


@router.post("/performance/analyze", response_model=DataResponse[PerformanceAnalyzeResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="performance_analyze",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def performance_analyze(
    request: PerformanceAnalysisRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Analyze a codebase for performance issues.

    Issue #744: Requires admin authentication.
    Issue #665: Refactored to use helper functions.

    Detects:
    - N+1 query patterns
    - Nested loop complexity
    - Sync operations in async context
    - Sequential awaits (should be parallel)
    - String concatenation in loops
    - Inefficient data structures
    """
    await _validate_analysis_path(request.path)

    try:
        analyzer = PerformanceAnalyzer(
            project_root=request.path,
            exclude_patterns=request.exclude_patterns,
        )
        results = await asyncio.to_thread(analyzer.analyze_directory)
        results = _filter_results_by_severity(results, request.min_severity)
        summary = analyzer.get_summary()

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "path": request.path,
                "summary": summary,
                "findings": [r.to_dict() for r in results],
                "total_findings": len(results),
            },
        )

    except Exception as e:
        logger.error("Performance analysis failed: %s", e)
        raise_internal_error("Performance analysis failed")


@router.post("/performance/scan-file", response_model=DataResponse[PerformanceScanFileResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="performance_scan_file",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def performance_scan_file(
    request: PerformanceFileScanRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Scan a single file for performance issues.

    Issue #744: Requires admin authentication.

    Quick scan of a single Python file for performance bottlenecks.
    """
    file_exists = await asyncio.to_thread(os.path.exists, request.file_path)
    if not file_exists:
        raise_invalid_input("file_path", f"does not exist: {request.file_path}")

    if not request.file_path.endswith(".py"):
        raise_invalid_input("file_path", "only Python files (.py) are supported")

    try:
        analyzer = PerformanceAnalyzer()
        results = await asyncio.to_thread(analyzer.analyze_file, request.file_path)

        # Group by issue type
        by_type = {}
        for result in results:
            itype = result.issue_type.value
            if itype not in by_type:
                by_type[itype] = []
            by_type[itype].append(result.to_dict())

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "file": request.file_path,
                "findings": [r.to_dict() for r in results],
                "total_findings": len(results),
                "by_type": by_type,
                "severity_counts": {
                    sev.value: len([r for r in results if r.severity == sev]) for sev in PerformanceSeverity
                },
            },
        )

    except Exception as e:
        logger.error("Performance file scan failed: %s", e)
        raise_internal_error("File scan failed")


@router.get("/performance/issue-types", response_model=DataResponse[PerformanceIssueTypesResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_performance_issue_types",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def list_performance_issue_types(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get all supported performance issue types.

    Issue #744: Requires admin authentication.

    Returns list of all performance issues that can be detected,
    along with their categories.
    """
    issue_types = get_performance_issue_types()

    # Group by category
    by_category = {}
    for it in issue_types:
        cat = it["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(it["type"])

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "issue_types": issue_types,
            "total_types": len(issue_types),
            "by_category": by_category,
        },
    )


@router.get("/performance/score", response_model=DataResponse[PerformanceScoreResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_score",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_performance_score(
    path: str = Query(..., description="Directory path to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get performance health score for a codebase.

    Issue #744: Requires admin authentication.
    Issue #2655: Return no_data (200) instead of 400 when path does not exist
    so the frontend can display an informative message without treating it as an error.

    Returns a score from 0-100 based on the number and severity
    of performance issues detected. Higher scores indicate
    better performance.
    """
    path_exists = await asyncio.to_thread(os.path.exists, path)
    if not path_exists:
        logger.warning("Performance score: path does not exist: %s", path)
        return JSONResponse(
            status_code=200,
            content={
                "status": "no_data",
                "message": f"Path does not exist: {path}",
                "performance_score": 0,
            },
        )

    try:
        analyzer = PerformanceAnalyzer(project_root=path)
        await asyncio.to_thread(analyzer.analyze_directory)
        summary = analyzer.get_summary()

        # Get score and grade, generate status using extracted helper
        score = summary["performance_score"]
        grade = summary["grade"]
        status = _get_performance_status_message(score)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "path": path,
                "performance_score": score,
                "grade": grade,
                "status_message": status,
                "total_issues": summary["total_issues"],
                "critical_issues": summary["critical_issues"],
                "high_issues": summary["high_issues"],
                "files_analyzed": summary["files_analyzed"],
                "severity_breakdown": summary["by_severity"],
                "top_issues": summary["top_issues"],
            },
        )

    except Exception as e:
        logger.error("Performance score calculation failed: %s", e)
        raise_internal_error("Performance score calculation failed")


@router.get("/performance/report", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_report",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_performance_report(
    path: str = Query(..., description="Directory path to analyze"),
    format: str = Query(default="json", description="Report format: json or markdown"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Generate a comprehensive performance report.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored using Extract Method pattern.

    Returns a detailed performance analysis report including summary with
    score and grade, all findings with optimization recommendations,
    complexity analysis, and top recommendations.
    """
    await _validate_path_exists(path)

    try:
        analyzer = PerformanceAnalyzer(project_root=path)
        await asyncio.to_thread(analyzer.analyze_directory)
        return await _generate_report_response(analyzer, path, format)

    except Exception as e:
        logger.error("Performance report generation failed: %s", e)
        raise_internal_error("Report generation failed")


# Issue #243: Code Evolution Mining Endpoints

from code_intelligence.code_evolution_miner import CodeEvolutionMiner


@router.post("/evolution/analyze", response_model=DataResponse[EvolutionAnalyzeResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_code_evolution",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def analyze_code_evolution(
    path: str = Query(..., description="Repository path to analyze"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Analyze code evolution over git history.

    Issue #243: Code Evolution Mining from Git History
    Issue #744: Requires admin authentication.

    Analyzes git history to identify emerging patterns, declining patterns,
    and refactoring events. Returns comprehensive evolution report.

    Args:
        path: Repository path to analyze
        start_date: Optional start date for analysis period (ISO format)
        end_date: Optional end date for analysis period (ISO format)

    Returns:
        Evolution report with emerging/declining patterns and refactorings
    """
    await _validate_path_exists(path)

    try:
        # Parse dates if provided
        start = parse_utc_iso(start_date) if start_date else None
        end = parse_utc_iso(end_date) if end_date else None

        # Analyze evolution
        miner = CodeEvolutionMiner(path)
        report = await asyncio.to_thread(miner.analyze_evolution, start, end)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "report": report,
            },
        )

    except ValueError:
        raise_invalid_input("date", "invalid date format")
    except Exception as e:
        logger.error("Evolution analysis failed: %s", e)
        raise_internal_error("Evolution analysis failed")


@router.get("/evolution/patterns", response_model=DataResponse[EvolutionPatternsResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pattern_evolution",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_pattern_evolution(
    path: str = Query(..., description="Repository path to analyze"),
    pattern_type: str | None = Query(None, description="Filter by pattern type"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get pattern evolution metrics.

    Issue #243: Code Evolution Mining from Git History
    Issue #744: Requires admin authentication.

    Returns metrics about how patterns evolve over time including
    adoption rates, trends (emerging/stable/declining), and first/last seen dates.

    Args:
        path: Repository path to analyze
        pattern_type: Optional filter for specific pattern type

    Returns:
        Pattern evolution metrics
    """
    await _validate_path_exists(path)

    try:
        miner = CodeEvolutionMiner(path)
        # Run basic analysis first
        await asyncio.to_thread(miner.analyze_evolution)

        # Get pattern metrics
        metrics = await asyncio.to_thread(miner.get_pattern_metrics)

        # Filter if pattern_type specified
        if pattern_type and pattern_type in metrics:
            metrics = {pattern_type: metrics[pattern_type]}

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "path": path,
                "pattern_metrics": metrics,
            },
        )

    except Exception as e:
        logger.error("Pattern evolution retrieval failed: %s", e)
        raise_internal_error("Pattern evolution failed")


@router.get("/evolution/refactorings", response_model=DataResponse[EvolutionRefactoringsResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_refactorings",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def detect_refactorings(
    path: str = Query(..., description="Repository path to analyze"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results to return"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Detect refactoring events in git history.

    Issue #243: Code Evolution Mining from Git History
    Issue #744: Requires admin authentication.

    Identifies commits that likely contain refactorings based on commit
    messages and file change patterns.

    Args:
        path: Repository path to analyze
        limit: Maximum number of refactorings to return

    Returns:
        List of detected refactoring commits
    """
    await _validate_path_exists(path)

    try:
        miner = CodeEvolutionMiner(path)
        refactorings = await asyncio.to_thread(miner.refactoring_detector.detect_refactorings)

        # Limit results
        refactorings = refactorings[:limit]

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "path": path,
                "refactorings": refactorings,
                "total": len(refactorings),
            },
        )

    except Exception as e:
        logger.error("Refactoring detection failed: %s", e)
        raise_internal_error("Refactoring detection failed")


@router.get("/evolution/timeline", response_model=DataResponse[EvolutionTimelineResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_evolution_timeline",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_evolution_timeline(
    path: str = Query(..., description="Repository path to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Generate evolution timeline visualization data.

    Issue #243: Code Evolution Mining from Git History
    Issue #744: Requires admin authentication.

    Returns timeline data showing pattern counts over time, suitable for
    visualization in charts/graphs.

    Args:
        path: Repository path to analyze

    Returns:
        Timeline data with monthly pattern counts
    """
    await _validate_path_exists(path)

    try:
        miner = CodeEvolutionMiner(path)
        # Run basic analysis first
        await asyncio.to_thread(miner.analyze_evolution)

        # Generate timeline
        timeline_data = await asyncio.to_thread(miner.generate_timeline_data)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "path": path,
                "timeline": timeline_data["timeline"],
            },
        )

    except Exception as e:
        logger.error("Timeline generation failed: %s", e)
        raise_internal_error("Timeline generation failed")


async def _run_evolution_analysis(miner, start, end) -> tuple:
    """Helper for get_full_evolution_report. Ref: #1088."""
    evolution_report = await asyncio.to_thread(miner.analyze_evolution, start, end)
    pattern_metrics = await asyncio.to_thread(miner.get_pattern_metrics)
    timeline_data = await asyncio.to_thread(miner.generate_timeline_data)
    return evolution_report, pattern_metrics, timeline_data


def _build_evolution_summary(evolution_report: dict) -> dict:
    """Helper for get_full_evolution_report. Ref: #1088."""
    return {
        "emerging_patterns_count": len(evolution_report["emerging_patterns"]),
        "declining_patterns_count": len(evolution_report["declining_patterns"]),
        "refactorings_count": len(evolution_report["refactorings"]),
        "commits_analyzed": evolution_report["commits_analyzed"],
    }


@router.get("/evolution/report", response_model=DataResponse[EvolutionReportResultResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_full_evolution_report",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_full_evolution_report(
    path: str = Query(..., description="Repository path to analyze"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Generate comprehensive code evolution report.

    Issue #243: Code Evolution Mining from Git History
    Issue #744: Requires admin authentication.

    Combines evolution analysis, pattern metrics, refactorings, and timeline
    into a single comprehensive report.

    Args:
        path: Repository path to analyze
        start_date: Optional start date for analysis period
        end_date: Optional end date for analysis period

    Returns:
        Comprehensive evolution report
    """
    await _validate_path_exists(path)

    try:
        # Parse dates if provided
        start = parse_utc_iso(start_date) if start_date else None
        end = parse_utc_iso(end_date) if end_date else None

        miner = CodeEvolutionMiner(path)
        (
            evolution_report,
            pattern_metrics,
            timeline_data,
        ) = await _run_evolution_analysis(miner, start, end)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "path": path,
                "evolution": evolution_report,
                "pattern_metrics": pattern_metrics,
                "timeline": timeline_data["timeline"],
                "summary": _build_evolution_summary(evolution_report),
            },
        )

    except ValueError:
        raise_invalid_input("date", "invalid date format")
    except Exception as e:
        logger.error("Evolution report generation failed: %s", e)
        raise_internal_error("Evolution report failed")


# ------------------------------------------------------------------
# Background task endpoints for security score (#1304)
# ------------------------------------------------------------------


@router.get("/security/score/cached", response_model=CachedSecurityScoreResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cached_security_score",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_cached_security_score(
    source_id: str | None = Query(default=None, description="GH#8436: scope result by project source_id"),
):
    """Return the latest completed security score result (#1540, GH#8436)."""
    prefix = f"{_REDIS_PREFIX}{source_id}:" if source_id else _REDIS_PREFIX
    cached = await get_latest_task_result(prefix)
    if cached and cached.get("result"):
        return {
            "status": "success",
            "from_cache": True,
            "completed_at": cached.get("completed_at"),
            **cached["result"],
        }
    return {"status": "no_data"}


_NO_PATH_RESULT = {"status": "no_data", "message": "Path does not exist", "security_score": 0}


@router.post("/security/score/analyze", response_model=StartTaskResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_security_analysis",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def start_security_analysis(
    path: str = Query(..., description="Directory path to analyze"),
    source_id: str | None = Query(default=None, description="GH#8436: scope cached result by project source_id"),
    admin_check: bool = Depends(check_admin_permission),
):
    """Enqueue security score analysis as a Celery task (GH#6505).

    Issue #2655: Return a completed no_data task when the path does not exist.
    GH#8436: scope latest-result cache by source_id.
    """
    path_exists = await asyncio.to_thread(os.path.exists, path)
    if not path_exists:
        logger.warning("Security score analysis: path does not exist: %s", path)
        return {
            "task_id": "no_path",
            "status": "completed",
            "result": {**_NO_PATH_RESULT, "message": f"Path does not exist: {path}"},
        }
    prefix = f"{_REDIS_PREFIX}{source_id}:" if source_id else _REDIS_PREFIX
    result = run_security_analysis.delay(path)
    await store_latest_task_id(prefix, result.id)
    return {"task_id": result.id, "status": "pending"}


@router.get("/security/score/status/{task_id}", response_model=CodeIntelligenceTaskStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_security_score_status",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_security_score_status(task_id: str):
    """Get security score analysis task status (GH#8437: handle no_path sentinel)."""
    if task_id == "no_path":
        return {
            "task_id": "no_path",
            "status": "completed",
            "progress": 100.0,
            "current_step": "Complete",
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result": _NO_PATH_RESULT,
        }
    status = celery_result_to_status(AsyncResult(task_id))
    if status is None:
        raise_not_found("Task", task_id)
    return status


@router.post("/security/score/tasks/clear-stuck", response_model=ClearStuckResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_stuck_sec_tasks",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def clear_stuck_sec_tasks(
    force: bool = Query(default=False, description="Force clear ALL running tasks"),
):
    """No-op: Celery handles stuck-task recovery automatically (GH#6505)."""
    return {"cleared_count": 0, "message": "Celery handles task recovery automatically"}


# Issue #2068: Stub GET endpoints for security/performance/redis findings.
# The full analysis is available via the POST /analyze endpoints above.
# These GET stubs prevent 404s and return a consistent "not yet implemented" response.


@router.get("/security/findings", response_model=FindingsPlaceholderResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_security_findings",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_security_findings(
    admin_check: bool = Depends(check_admin_permission),
):
    """Placeholder for security findings summary (Issue #2068).

    Full security analysis is available via POST /security/analyze.
    Returns an empty findings list with a descriptive message.
    """
    logger.debug("GET /security/findings called — returning placeholder response")
    return {
        "findings": [],
        "score": None,
        "message": "Security findings analysis not yet implemented as a GET endpoint. "
        "Use POST /api/code-intelligence/security/analyze with a path parameter.",
    }


@router.get("/performance/findings", response_model=FindingsPlaceholderResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_findings",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_performance_findings(
    admin_check: bool = Depends(check_admin_permission),
):
    """Placeholder for performance findings summary (Issue #2068).

    Full performance analysis is available via POST /performance/analyze.
    Returns an empty findings list with a descriptive message.
    """
    logger.debug("GET /performance/findings called — returning placeholder response")
    return {
        "findings": [],
        "score": None,
        "message": "Performance findings analysis not yet implemented as a GET endpoint. "
        "Use POST /api/code-intelligence/performance/analyze with a path parameter.",
    }


@router.get("/redis/findings", response_model=FindingsPlaceholderResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_findings",
    error_code_prefix="CODE_INTELLIGENCE",
)
async def get_redis_findings(
    admin_check: bool = Depends(check_admin_permission),
):
    """Placeholder for Redis optimization findings summary (Issue #2068).

    Full Redis analysis is available via POST /redis/analyze.
    Returns an empty findings list with a descriptive message.
    """
    logger.debug("GET /redis/findings called — returning placeholder response")
    return {
        "findings": [],
        "score": None,
        "message": "Redis optimization findings analysis not yet implemented as a GET endpoint. "
        "Use POST /api/code-intelligence/redis/analyze with a path parameter.",
    }
