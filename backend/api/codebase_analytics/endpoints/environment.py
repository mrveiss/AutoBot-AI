# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Environment analysis endpoints (Issue #538)

Provides:
- Environment variable detection and recommendations
- Hardcoded value identification
- Configuration centralization suggestions
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache for environment analysis (in-memory, refreshed on demand)
_env_analysis_cache: Optional[dict] = None
# Full analysis cache for export (Issue #631)
_env_analysis_full_cache: Optional[dict] = None
# Lock for thread-safe access to _env_analysis_cache (Issue #559)
_env_analysis_cache_lock = asyncio.Lock()


def _get_project_root() -> str:
    """Get project root path (4 levels up from this file)."""
    return str(Path(__file__).resolve().parents[4])


def _validate_env_path_security(path: str, project_root: str) -> Optional[JSONResponse]:
    """
    Validate that path is within project root.

    Returns:
        JSONResponse error if validation fails, None if valid
    """
    try:
        resolved_path = Path(path).resolve()
        if not str(resolved_path).startswith(project_root):
            logger.warning("Path traversal attempt blocked: %s", path)
            return JSONResponse({
                "status": "error",
                "message": "Invalid path: must be within project root",
                "total_hardcoded_values": 0,
                "categories": {},
                "recommendations_count": 0,
            }, status_code=400)
    except Exception as e:
        logger.warning("Invalid path provided: %s - %s", path, e)
        return JSONResponse({
            "status": "error",
            "message": f"Invalid path: {str(e)}",
            "total_hardcoded_values": 0,
            "categories": {},
            "recommendations_count": 0,
        }, status_code=400)

    return None


async def _run_environment_analysis(analyzer, path: str, pattern_list: list):
    """
    Run environment analysis with timeout.

    Args:
        analyzer: EnvironmentAnalyzer instance
        path: Path to analyze
        pattern_list: List of glob patterns

    Returns:
        Analysis result or None if timed out
    """
    ANALYSIS_TIMEOUT = 120  # 2 minute timeout for large codebases
    try:
        coro = analyzer.analyze_codebase(path, pattern_list)
        if asyncio.iscoroutine(coro):
            return await asyncio.wait_for(coro, timeout=ANALYSIS_TIMEOUT)
        else:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, lambda: coro),
                timeout=ANALYSIS_TIMEOUT
            )
    except asyncio.TimeoutError:
        logger.warning("Environment analysis timed out after %d seconds", ANALYSIS_TIMEOUT)
        return None


def _build_environment_result(analysis: dict, path: str, for_display: bool = True) -> dict:
    """
    Build result from analysis data.

    Args:
        analysis: Raw analysis data from EnvironmentAnalyzer
        path: Path that was analyzed
        for_display: If True, limit list sizes for UI performance.
                     If False (export), return all data.

    Issue #631: for_display=False returns full data for export.
    """
    hardcoded_values = analysis.get("hardcoded_details", [])
    recommendations = analysis.get("configuration_recommendations", [])

    # For display, limit to 50 items (UI performance)
    # For export, include all items
    if for_display:
        hardcoded_values = hardcoded_values[:50]
        recommendations = recommendations[:20]

    return {
        "status": "success",
        "path": path,
        "total_hardcoded_values": analysis.get("total_hardcoded_values", 0),
        "high_priority_count": analysis.get("high_priority_count", 0),
        "recommendations_count": analysis.get("recommendations_count", 0),
        "categories": analysis.get("categories", {}),
        "analysis_time_seconds": analysis.get("analysis_time_seconds", 0),
        "hardcoded_values": hardcoded_values,
        "recommendations": recommendations,
        "metrics": analysis.get("metrics", {}),
        "storage_type": "live_analysis",
        # Issue #631: Add truncation info for display mode
        "is_truncated": for_display and (
            len(analysis.get("hardcoded_details", [])) > 50 or
            len(analysis.get("configuration_recommendations", [])) > 20
        ),
    }


def _get_environment_analyzer():
    """
    Get EnvironmentAnalyzer instance.

    Lazy import to avoid circular dependencies and allow graceful degradation
    if the tools module is not available.

    Issue #542: Fixed import path resolution by adding project root to sys.path
    before the tools path, allowing env_analyzer.py to import from src.utils.

    Issue #611: Fixed namespace conflict - the 'src' package from project root
    is cached in sys.modules, preventing import of src.env_analyzer from
    tools/code-analysis-suite. Use importlib to load directly from file path.
    """
    try:
        import importlib.util

        # Issue #542: Add project root so env_analyzer.py can import from src.utils
        project_root = str(Path(__file__).resolve().parents[4])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        # Issue #611: Load env_analyzer directly from file to avoid namespace conflict
        env_analyzer_path = Path(__file__).resolve().parents[4] / "tools" / "code-analysis-suite" / "src" / "env_analyzer.py"

        if not env_analyzer_path.exists():
            logger.warning("EnvironmentAnalyzer not available: %s does not exist", env_analyzer_path)
            return None

        spec = importlib.util.spec_from_file_location("env_analyzer", env_analyzer_path)
        if spec is None or spec.loader is None:
            logger.warning("EnvironmentAnalyzer not available: Could not load spec")
            return None

        env_analyzer_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(env_analyzer_module)

        return env_analyzer_module.EnvironmentAnalyzer()
    except Exception as e:
        logger.warning("EnvironmentAnalyzer not available: %s", e)
        return None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_environment_analysis",
    error_code_prefix="CODEBASE",
)
@router.get("/env-analysis")
async def get_environment_analysis(
    path: str = Query(None, description="Root path to analyze (defaults to project root)"),
    refresh: bool = Query(False, description="Force fresh analysis instead of cache"),
    patterns: str = Query("**/*.py", description="Glob patterns for files to scan, comma-separated"),
):
    """
    Analyze codebase for hardcoded values and environment variable opportunities (Issue #538).

    Uses the EnvironmentAnalyzer to detect:
    - Hardcoded file paths
    - Hardcoded URLs and hostnames
    - Hardcoded ports and connection strings
    - API keys and secrets
    - Configuration values that should be externalized

    Args:
        path: Root path to analyze (defaults to project root)
        refresh: Force fresh analysis instead of using cached results
        patterns: Comma-separated glob patterns for files to scan

    Returns:
        JSON with hardcoded values, recommendations, and metrics
    """
    global _env_analysis_cache

    # Use cached results if available and not refreshing (thread-safe, Issue #559)
    async with _env_analysis_cache_lock:
        if _env_analysis_cache and not refresh:
            logger.info(
                "Returning cached environment analysis (%d hardcoded values)",
                _env_analysis_cache.get("total_hardcoded_values", 0)
            )
            return JSONResponse(_env_analysis_cache)

    project_root = _get_project_root()
    if not path:
        path = project_root

    # Security validation
    error_response = _validate_env_path_security(path, project_root)
    if error_response:
        return error_response

    pattern_list = [p.strip() for p in patterns.split(",")]

    try:
        analyzer = _get_environment_analyzer()
        if not analyzer:
            return JSONResponse({
                "status": "error",
                "message": "EnvironmentAnalyzer not available. Check tools installation.",
                "total_hardcoded_values": 0,
                "categories": {},
                "recommendations_count": 0,
            })

        analysis = await _run_environment_analysis(analyzer, path, pattern_list)
        if analysis is None:
            return JSONResponse({
                "status": "partial",
                "message": "Analysis timed out after 120s. Try with fewer patterns.",
                "total_hardcoded_values": 0,
                "categories": {},
                "recommendations_count": 0,
            })

        result = _build_environment_result(analysis, path, for_display=True)

        # Issue #631: Build full result for export (no truncation)
        full_result = _build_environment_result(analysis, path, for_display=False)

        # Cache the results (thread-safe, Issue #559)
        async with _env_analysis_cache_lock:
            global _env_analysis_full_cache
            _env_analysis_cache = result
            _env_analysis_full_cache = full_result

        logger.info(
            "Environment analysis complete: %d hardcoded values, %d recommendations",
            result["total_hardcoded_values"],
            result["recommendations_count"],
        )

        return JSONResponse(result)

    except Exception as e:
        logger.error("Environment analysis failed: %s", e, exc_info=True)
        return JSONResponse({
            "status": "error",
            "message": f"Environment analysis failed: {str(e)}",
            "total_hardcoded_values": 0,
            "categories": {},
            "recommendations_count": 0,
        })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_env_recommendations",
    error_code_prefix="CODEBASE",
)
@router.get("/env-recommendations")
async def get_env_recommendations(
    path: str = Query(None, description="Root path to analyze (defaults to project root)"),
):
    """
    Get environment variable recommendations for a codebase (Issue #538).

    Returns actionable recommendations for creating/updating .env files
    based on detected hardcoded values.

    Args:
        path: Root path to analyze

    Returns:
        JSON with prioritized recommendations
    """
    global _env_analysis_cache

    # Check cache first (thread-safe, Issue #559)
    async with _env_analysis_cache_lock:
        if _env_analysis_cache and _env_analysis_cache.get("recommendations"):
            return JSONResponse({
                "status": "success",
                "recommendations": _env_analysis_cache["recommendations"],
                "total": len(_env_analysis_cache["recommendations"]),
                "source": "cache",
            })

    # Run fresh analysis if no cache
    if not path:
        path = str(Path(__file__).resolve().parents[4])

    try:
        analyzer = _get_environment_analyzer()
        if not analyzer:
            return JSONResponse({
                "status": "error",
                "message": "EnvironmentAnalyzer not available",
                "recommendations": [],
                "total": 0,
            })

        analysis = await analyzer.analyze_codebase(path)
        recommendations = analysis.get("configuration_recommendations", [])

        return JSONResponse({
            "status": "success",
            "recommendations": recommendations[:20],
            "total": len(recommendations),
            "source": "live_analysis",
        })

    except Exception as e:
        logger.error("Failed to get env recommendations: %s", e, exc_info=True)
        return JSONResponse({
            "status": "error",
            "message": str(e),
            "recommendations": [],
            "total": 0,
        })


# =============================================================================
# Export Helpers (Issue #665)
# =============================================================================

# Module-level constant for severity ordering (Issue #380 pattern)
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_VALID_SEVERITIES = {"high", "medium", "low"}


def _filter_hardcoded_values(
    values: list, category: Optional[str], severity: Optional[str]
) -> list:
    """
    Filter hardcoded values by category and/or severity.

    Issue #665: Extracted helper for filtering logic.
    """
    result = values
    if category:
        result = [v for v in result if v.get("type", "").lower() == category.lower()]
    if severity:
        result = [v for v in result if v.get("severity", "").lower() == severity.lower()]
    return result


def _sort_by_severity(values: list) -> list:
    """
    Sort values by severity (high first).

    Issue #665: Extracted helper for severity sorting.
    """
    return sorted(
        values,
        key=lambda v: _SEVERITY_ORDER.get(v.get("severity", "low").lower(), 3)
    )


def _calculate_category_breakdown(values: list) -> dict:
    """
    Calculate count breakdown by category.

    Issue #665: Extracted helper for category counting.
    """
    counts = {}
    for v in values:
        cat = v.get("type", "unknown")
        counts[cat] = counts.get(cat, 0) + 1
    return counts


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_env_analysis",
    error_code_prefix="CODEBASE",
)
@router.get("/env-analysis/export")
async def export_env_analysis(
    category: str = Query(None, description="Filter by category (e.g., 'security', 'port', 'hostname')"),
    severity: str = Query(None, description="Filter by severity ('high', 'medium', 'low')"),
    limit: int = Query(None, description="Limit number of results (default: all)"),
    include_recommendations: bool = Query(True, description="Include recommendations in export"),
):
    """
    Export full environment analysis results without truncation (Issue #631).
    Issue #665: Refactored to use extracted helpers for filtering and sorting.
    """
    global _env_analysis_full_cache

    # Check cache (thread-safe, Issue #559)
    async with _env_analysis_cache_lock:
        if not _env_analysis_full_cache:
            return JSONResponse({
                "status": "error",
                "message": "No cached analysis available. Run environment analysis first.",
                "hardcoded_values": [], "recommendations": [], "total": 0,
            }, status_code=404)
        full_data = _env_analysis_full_cache.copy()

    # Validate severity (Issue #665: use module constant)
    if severity and severity.lower() not in _VALID_SEVERITIES:
        return JSONResponse({
            "status": "error",
            "message": f"Invalid severity '{severity}'. Must be one of: {', '.join(sorted(_VALID_SEVERITIES))}",
            "hardcoded_values": [], "recommendations": [], "total": 0,
        }, status_code=400)

    # Issue #631: Copy to avoid mutating cache; Issue #665: use helpers
    hardcoded_values = list(full_data.get("hardcoded_values", []))
    hardcoded_values = _filter_hardcoded_values(hardcoded_values, category, severity)
    hardcoded_values = _sort_by_severity(hardcoded_values)

    # Apply limit after sorting (high severity first)
    if limit and limit > 0:
        hardcoded_values = hardcoded_values[:limit]

    recommendations = full_data.get("recommendations", [])
    category_counts = _calculate_category_breakdown(hardcoded_values)

    logger.info(
        "Environment analysis export: %d/%d items (category=%s, severity=%s)",
        len(hardcoded_values), full_data.get("total_hardcoded_values", 0),
        category or "all", severity or "all",
    )

    return JSONResponse({
        "status": "success",
        "path": full_data.get("path", ""),
        "export_timestamp": full_data.get("analysis_time_seconds", 0),
        "total_in_export": len(hardcoded_values),
        "total_in_analysis": full_data.get("total_hardcoded_values", 0),
        "categories": category_counts,
        "filters_applied": {"category": category, "severity": severity, "limit": limit},
        "hardcoded_values": hardcoded_values,
        "recommendations": recommendations if include_recommendations else [],
        "recommendations_count": len(recommendations) if include_recommendations else 0,
    })
