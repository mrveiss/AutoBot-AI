# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Analysis Analytics API Module
Provides code analysis and quality assessment endpoints
Extracted from analytics.py to maintain <20 functions per file
"""

import asyncio
import logging
import threading
from datetime import datetime
from pathlib import Path

from auth_middleware import check_admin_permission
from backend.api.analytics_models import CodeAnalysisRequest
from fastapi import APIRouter, Depends, HTTPException

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

# Import shared analytics controller from analytics module
# This will be set after analytics.py is updated
analytics_controller = None
analytics_state = None

# Thread-safe lock for global state modifications (Issue #481 - race condition fix)
_analytics_deps_lock = threading.Lock()

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics", "code-analysis"])


def set_analytics_dependencies(controller, state):
    """Set dependencies from main analytics module (thread-safe)"""
    global analytics_controller, analytics_state
    with _analytics_deps_lock:
        analytics_controller = controller
        analytics_state = state


# ============================================================================
# CODE ANALYSIS INTEGRATION ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="index_codebase",
    error_code_prefix="ANALYTICS",
)
@router.post("/code/index")
async def index_codebase(
    request: CodeAnalysisRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Trigger codebase indexing and analysis

    Issue #744: Requires admin authentication.
    """
    # Validate request
    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(Path(request.target_path).exists):
        raise HTTPException(
            status_code=400,
            detail=f"Target path does not exist: {request.target_path}",
        )

    # Perform analysis
    results = await analytics_controller.perform_code_analysis(request)

    return {
        "status": "completed",
        "request": request.dict(),
        "results": results,
        "cached_for_reuse": True,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_analysis_status",
    error_code_prefix="ANALYTICS",
)
@router.get("/code/status")
async def get_code_analysis_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get current code analysis status and capabilities

    Issue #744: Requires admin authentication.
    """
    # Issue #619: Parallelize independent file existence checks
    code_analysis_exists, code_index_exists = await asyncio.gather(
        asyncio.to_thread(analytics_controller.code_analysis_path.exists),
        asyncio.to_thread(analytics_controller.code_index_path.exists),
    )
    status = {
        "tools_available": {
            "code_analysis_suite": code_analysis_exists,
            "code_index_mcp": code_index_exists,
        },
        "last_analysis_time": analytics_state.get("last_analysis_time"),
        "cache_status": {
            "has_cached_results": bool(analytics_state.get("code_analysis_cache")),
            "cache_timestamp": analytics_state.get("last_analysis_time"),
        },
        "supported_analysis_types": ["full", "incremental", "communication_chains"],
    }

    # Add tool details if available
    # Issue #358 - avoid blocking (reuse exists checks from above)
    if code_analysis_exists:
        # Issue #358 - use lambda to defer glob execution to thread
        scripts_available = await asyncio.to_thread(
            lambda: list(analytics_controller.code_analysis_path.glob("scripts/*.py"))
        )
        status["code_analysis_suite"] = {
            "path": str(analytics_controller.code_analysis_path),
            "scripts_available": scripts_available,
        }

    if code_index_exists:
        # Issue #358 - avoid blocking
        config_path = analytics_controller.code_index_path / "pyproject.toml"
        config_available = await asyncio.to_thread(config_path.exists)
        status["code_index_mcp"] = {
            "path": str(analytics_controller.code_index_path),
            "config_available": config_available,
        }

    return status


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_quality_assessment",
    error_code_prefix="ANALYTICS",
)
@router.get("/quality/assessment")
async def get_code_quality_assessment(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get comprehensive code quality assessment for frontend dashboard

    Issue #744: Requires admin authentication.
    """
    # Get cached analysis or trigger new one
    cached_analysis = analytics_state.get("code_analysis_cache")

    # Default quality scores
    quality_assessment = {
        "overall_score": 75,
        "maintainability": 80,
        "testability": 70,
        "documentation": 65,
        "complexity": 85,
        "security": 75,
        "performance": 80,
        "timestamp": datetime.now().isoformat(),
    }

    # If we have cached analysis, use it
    if cached_analysis and "code_analysis" in cached_analysis:
        code_data = cached_analysis["code_analysis"]

        # Calculate quality metrics based on analysis
        complexity = code_data.get("complexity", 5)
        quality_assessment["complexity"] = max(0, (10 - complexity) * 10)

        quality_assessment["testability"] = code_data.get("test_coverage", 70)
        quality_assessment["documentation"] = code_data.get("doc_coverage", 65)

        # Calculate maintainability
        maintainability = code_data.get("maintainability", "good")
        maintainability_scores = {
            "excellent": 95,
            "good": 80,
            "fair": 65,
            "poor": 40,
        }
        quality_assessment["maintainability"] = maintainability_scores.get(
            maintainability, 80
        )

        # Overall score is average of all factors
        quality_assessment["overall_score"] = round(
            (
                quality_assessment["maintainability"]
                + quality_assessment["testability"]
                + quality_assessment["documentation"]
                + quality_assessment["complexity"]
                + quality_assessment["security"]
                + quality_assessment["performance"]
            )
            / 6,
            1,
        )

    return quality_assessment


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_quality_metrics",
    error_code_prefix="ANALYTICS",
)
@router.get("/code/quality-metrics")
async def get_code_quality_metrics(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get code quality metrics from cached analysis

    Issue #744: Requires admin authentication.
    """
    cached_analysis = analytics_state.get("code_analysis_cache")

    if not cached_analysis:
        return {
            "status": "no_analysis_available",
            "message": "No cached code analysis found. Run /code/index first.",
            "suggestion": "POST /api/analytics/code/index with analysis_type='full'",
        }

    # Extract quality metrics
    quality_metrics = {
        "analysis_timestamp": cached_analysis.get("timestamp"),
        "codebase_metrics": cached_analysis.get("codebase_metrics", {}),
        "quality_indicators": {},
        "recommendations": [],
    }

    # Process code analysis results if available
    if "code_analysis" in cached_analysis:
        code_data = cached_analysis["code_analysis"]

        quality_metrics["quality_indicators"] = {
            "complexity_score": code_data.get("complexity", 0),
            "maintainability": code_data.get("maintainability", "unknown"),
            "test_coverage": code_data.get("test_coverage", 0),
            "documentation_coverage": code_data.get("doc_coverage", 0),
        }

        # Generate recommendations
        if code_data.get("complexity", 0) > 7:
            quality_metrics["recommendations"].append(
                {
                    "type": "complexity",
                    "message": (
                        "High complexity detected. Consider refactoring complex functions."
                    ),
                    "priority": "medium",
                }
            )

        if code_data.get("test_coverage", 0) < 70:
            quality_metrics["recommendations"].append(
                {
                    "type": "testing",
                    "message": "Low test coverage. Consider adding more unit tests.",
                    "priority": "high",
                }
            )

    return quality_metrics


def _build_chain_correlation(static_endpoints: list, runtime_patterns: dict) -> dict:
    """Helper for get_communication_chains. Ref: #1088."""
    correlation = {}
    for endpoint in static_endpoints:
        if endpoint in runtime_patterns:
            response_times = analytics_controller.response_times[endpoint]
            correlation[endpoint] = {
                "static_detected": True,
                "runtime_calls": runtime_patterns[endpoint],
                "avg_response_time": (
                    sum(response_times) / len(response_times) if response_times else 0
                ),
            }
    return correlation


def _build_chain_insights(static_endpoints: list, runtime_patterns: dict) -> list:
    """Helper for get_communication_chains. Ref: #1088."""
    insights = []
    unused = [ep for ep in static_endpoints if ep not in runtime_patterns]
    if unused:
        insights.append(
            {
                "type": "unused_endpoints",
                "message": (
                    f"Found {len(unused)} endpoints that are defined but not used"
                ),
                "details": unused[:5],
            }
        )
    runtime_only = [ep for ep in runtime_patterns if ep not in static_endpoints]
    if runtime_only:
        insights.append(
            {
                "type": "undocumented_endpoints",
                "message": (
                    f"Found {len(runtime_only)} endpoints in use but not in static analysis"
                ),
                "details": runtime_only[:5],
            }
        )
    return insights


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_communication_chains",
    error_code_prefix="ANALYTICS",
)
@router.get("/code/communication-chains")
async def get_communication_chains(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get communication chain analysis from code analysis

    Issue #744: Requires admin authentication.
    """
    cached_analysis = analytics_state.get("code_analysis_cache")

    if not cached_analysis or "communication_chains" not in cached_analysis:
        return {
            "status": "no_analysis_available",
            "message": "No communication chain analysis found.",
            "suggestion": (
                "POST /api/analytics/code/index with analysis_type='communication_chains'"
            ),
        }

    chains = cached_analysis["communication_chains"]
    static_endpoints = chains.get("api_endpoints", [])
    runtime_patterns = analytics_controller.api_frequencies

    enhanced_chains = {
        "static_analysis": chains,
        "runtime_patterns": dict(analytics_controller.communication_chains),
        "correlation_analysis": _build_chain_correlation(
            static_endpoints, runtime_patterns
        ),
        "insights": _build_chain_insights(static_endpoints, runtime_patterns),
    }

    return enhanced_chains


def _build_endpoint_correlation_data(
    static_patterns: dict,
    runtime_patterns: dict,
) -> dict:
    """
    Build correlation data for each endpoint from static and runtime patterns.

    Issue #620: Extracted from analyze_communication_chains_detailed.

    Args:
        static_patterns: Static analysis patterns
        runtime_patterns: Runtime API frequency patterns

    Returns:
        Dict mapping endpoints to correlation data
    """
    correlation_data = {}
    for endpoint in static_patterns.get("api_endpoints", []):
        response_times = analytics_controller.response_times.get(endpoint, [])
        runtime_calls = runtime_patterns.get(endpoint, 0)

        correlation_data[endpoint] = {
            "static_detected": True,
            "runtime_calls": runtime_calls,
            "avg_response_time": sum(response_times) / max(len(response_times), 1),
            "error_rate": (
                analytics_controller.error_counts.get(endpoint, 0)
                / max(runtime_calls, 1)
                * 100
            ),
        }
    return correlation_data


def _generate_communication_chain_insights(
    static_patterns: dict,
    runtime_patterns: dict,
    correlation_data: dict,
) -> list:
    """
    Generate insights from communication chain analysis.

    Issue #620: Extracted from analyze_communication_chains_detailed.

    Args:
        static_patterns: Static analysis patterns
        runtime_patterns: Runtime API frequency patterns
        correlation_data: Endpoint correlation data

    Returns:
        List of insight dictionaries
    """
    insights = []

    # Find unused endpoints
    unused_endpoints = [
        ep
        for ep in static_patterns.get("api_endpoints", [])
        if ep not in runtime_patterns
    ]
    if unused_endpoints:
        insights.append(
            {
                "type": "unused_endpoints",
                "count": len(unused_endpoints),
                "endpoints": unused_endpoints[:10],
                "recommendation": "Consider removing unused endpoints or adding tests",
            }
        )

    # Find high error rate endpoints
    high_error_endpoints = [
        ep for ep, data in correlation_data.items() if data["error_rate"] > 5.0
    ]
    if high_error_endpoints:
        insights.append(
            {
                "type": "high_error_endpoints",
                "count": len(high_error_endpoints),
                "endpoints": high_error_endpoints,
                "recommendation": "Investigate and fix endpoints with high error rates",
            }
        )

    return insights


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_communication_chains_detailed",
    error_code_prefix="ANALYTICS",
)
@router.post("/code/analyze/communication-chains")
async def analyze_communication_chains_detailed(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Perform detailed communication chain analysis.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored to use extracted helper methods.
    """
    analysis_request = CodeAnalysisRequest(
        analysis_type="communication_chains", include_metrics=True
    )
    results = await analytics_controller.perform_code_analysis(analysis_request)

    # Enhance with runtime correlation
    if results.get("status") == "success":
        runtime_patterns = analytics_controller.api_frequencies
        static_patterns = results.get("communication_chains", {})

        # Build correlation data (Issue #620: uses helper)
        correlation_data = _build_endpoint_correlation_data(
            static_patterns, runtime_patterns
        )
        results["runtime_correlation"] = correlation_data

        # Generate insights (Issue #620: uses helper)
        results["insights"] = _generate_communication_chain_insights(
            static_patterns, runtime_patterns, correlation_data
        )

    return results


def _calculate_security_score(cached_analysis: dict) -> float:
    """
    Calculate security score from ChromaDB problems (Issue #665: extracted).

    Issue #543: Calculate security score from actual problems.

    Args:
        cached_analysis: Cached code analysis data

    Returns:
        Security score (0-100)
    """
    try:
        from backend.api.codebase_analytics.storage import get_code_collection

        code_collection = get_code_collection()
        if not code_collection:
            return 0.0  # No data available

        security_results = code_collection.get(
            where={
                "type": "problem",
                "problem_type": {"$in": ["security", "hardcode", "vulnerability"]},
            },
            include=["metadatas"],
        )
        security_issue_count = len(security_results.get("metadatas", []))

        # Get total files from codebase_metrics
        total_files = cached_analysis.get("codebase_metrics", {}).get(
            "total_files", 100
        )

        # Score: 100 - (issues per file * 100), min 0
        if total_files > 0:
            return round(max(0, 100 - (security_issue_count / total_files * 100)), 1)
        return 0.0  # No files analyzed

    except Exception as e:
        logger.warning("Failed to calculate security score: %s", e)
        return 0.0  # Unknown when can't calculate


def _calculate_quality_factors(cached_analysis: dict) -> dict:
    """
    Calculate quality factors from cached analysis (Issue #665: extracted).

    Args:
        cached_analysis: Cached code analysis data

    Returns:
        Dict of quality factor scores
    """
    quality_factors = {
        "complexity": 0,
        "maintainability": 0,
        "test_coverage": 0,
        "documentation": 0,
        "security": 0,
    }

    if "code_analysis" not in cached_analysis:
        return quality_factors

    code_data = cached_analysis["code_analysis"]

    # Complexity score (inverted - lower complexity is better)
    complexity = code_data.get("complexity", 10)
    quality_factors["complexity"] = max(0, (10 - complexity) * 10)

    # Test coverage
    quality_factors["test_coverage"] = code_data.get("test_coverage", 0)

    # Documentation coverage
    quality_factors["documentation"] = code_data.get("doc_coverage", 0)

    # Maintainability (convert to numeric)
    maintainability = code_data.get("maintainability", "poor")
    maintainability_scores = {
        "excellent": 95,
        "good": 80,
        "fair": 65,
        "poor": 40,
    }
    quality_factors["maintainability"] = maintainability_scores.get(maintainability, 40)

    # Security score
    quality_factors["security"] = _calculate_security_score(cached_analysis)

    return quality_factors


def _score_to_grade(score: float) -> str:
    """Convert numeric score to letter grade (Issue #665: extracted)."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_quality_score",
    error_code_prefix="ANALYTICS",
)
@router.get("/code/metrics/quality-score")
async def get_code_quality_score(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get comprehensive code quality score.

    Issue #665: Refactored with extracted helper functions.
    Issue #744: Requires admin authentication.
    """
    cached_analysis = analytics_state.get("code_analysis_cache")

    if not cached_analysis:
        # Trigger new analysis
        analysis_request = CodeAnalysisRequest(analysis_type="full")
        cached_analysis = await analytics_controller.perform_code_analysis(
            analysis_request
        )

    # Calculate quality factors (Issue #665: uses helper)
    quality_factors = _calculate_quality_factors(cached_analysis)

    # Calculate overall score
    overall_score = sum(quality_factors.values()) / len(quality_factors)

    return {
        "overall_score": round(overall_score, 1),
        "grade": _score_to_grade(overall_score),
        "quality_factors": quality_factors,
        "recommendations": [],
        "last_analysis": cached_analysis.get("timestamp"),
        "codebase_metrics": cached_analysis.get("codebase_metrics", {}),
    }
