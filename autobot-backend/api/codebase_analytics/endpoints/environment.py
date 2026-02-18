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

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

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
            return JSONResponse(
                {
                    "status": "error",
                    "message": "Invalid path: must be within project root",
                    "total_hardcoded_values": 0,
                    "categories": {},
                    "recommendations_count": 0,
                },
                status_code=400,
            )
    except Exception as e:
        logger.warning("Invalid path provided: %s - %s", path, e)
        return JSONResponse(
            {
                "status": "error",
                "message": f"Invalid path: {str(e)}",
                "total_hardcoded_values": 0,
                "categories": {},
                "recommendations_count": 0,
            },
            status_code=400,
        )

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
                loop.run_in_executor(None, lambda: coro), timeout=ANALYSIS_TIMEOUT
            )
    except asyncio.TimeoutError:
        logger.warning(
            "Environment analysis timed out after %d seconds", ANALYSIS_TIMEOUT
        )
        return None


async def _run_llm_filtered_analysis(
    analyzer,
    path: str,
    pattern_list: list,
    llm_model: str,
    filter_priority: Optional[str],
):
    """
    Run environment analysis with LLM filtering (Issue #633).

    Args:
        analyzer: EnvironmentAnalyzer instance
        path: Path to analyze
        pattern_list: List of glob patterns
        llm_model: Ollama model to use for filtering
        filter_priority: Priority level to filter ('high', 'medium', 'low', or None for all)

    Returns:
        Analysis result with LLM filtering applied, or None if timed out
    """
    # Issue #633: Extended timeout for LLM filtering (2 min base + 2 min for LLM)
    LLM_ANALYSIS_TIMEOUT = 240
    try:
        coro = analyzer.analyze_codebase_with_llm_filter(
            path,
            pattern_list,
            llm_model=llm_model,
            filter_priority=filter_priority,
        )
        if asyncio.iscoroutine(coro):
            return await asyncio.wait_for(coro, timeout=LLM_ANALYSIS_TIMEOUT)
        else:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, lambda: coro), timeout=LLM_ANALYSIS_TIMEOUT
            )
    except asyncio.TimeoutError:
        logger.warning(
            "LLM-filtered environment analysis timed out after %d seconds",
            LLM_ANALYSIS_TIMEOUT,
        )
        return None


def _build_environment_result(
    analysis: dict, path: str, for_display: bool = True
) -> dict:
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
        "is_truncated": for_display
        and (
            len(analysis.get("hardcoded_details", [])) > 50
            or len(analysis.get("configuration_recommendations", [])) > 20
        ),
    }


def _get_environment_analyzer():
    """
    Get EnvironmentAnalyzer instance.

    Lazy import to avoid circular dependencies and allow graceful degradation
    if the tools module is not available.

    Issue #542: Fixed import path resolution by adding project root to sys.path
    before the tools path, allowing env_analyzer.py to import from utils.

    Issue #611: Fixed namespace conflict - the 'src' package from project root
    is cached in sys.modules, preventing import of src.env_analyzer from
    tools/code-analysis-suite. Use importlib to load directly from file path.
    """
    try:
        import importlib.util

        # Issue #542: Add project root so env_analyzer.py can import from utils
        project_root = str(Path(__file__).resolve().parents[4])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        # Issue #611: Load env_analyzer directly from file to avoid namespace conflict
        env_analyzer_path = (
            Path(__file__).resolve().parents[4]
            / "tools"
            / "code-analysis-suite"
            / "src"
            / "env_analyzer.py"
        )

        if not env_analyzer_path.exists():
            logger.warning(
                "EnvironmentAnalyzer not available: %s does not exist",
                env_analyzer_path,
            )
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


def _build_error_response(message: str, status: str = "error") -> dict:
    """
    Build a standard error response for environment analysis.

    Issue #665: Extracted from get_environment_analysis to reduce function length.
    """
    return {
        "status": status,
        "message": message,
        "total_hardcoded_values": 0,
        "categories": {},
        "recommendations_count": 0,
    }


async def _check_env_analysis_cache(
    use_llm_filter: bool, refresh: bool
) -> Optional[JSONResponse]:
    """
    Check if cached environment analysis is available and valid.

    Issue #665: Extracted from get_environment_analysis to reduce function length.

    Returns:
        JSONResponse with cached data if valid, None if cache miss or refresh needed.
    """
    # Issue #633: LLM filter results are dynamic, don't use cache
    cache_valid = not use_llm_filter

    async with _env_analysis_cache_lock:
        if _env_analysis_cache and not refresh and cache_valid:
            logger.info(
                "Returning cached environment analysis (%d hardcoded values)",
                _env_analysis_cache.get("total_hardcoded_values", 0),
            )
            return JSONResponse(_env_analysis_cache)

    return None


async def _execute_env_analysis(
    analyzer,
    path: str,
    pattern_list: list,
    use_llm_filter: bool,
    llm_model: str,
    filter_priority: str,
) -> Optional[dict]:
    """
    Execute environment analysis with optional LLM filtering.

    Issue #665: Extracted from get_environment_analysis to reduce function length.

    Returns:
        Analysis result dict, or None if timed out.
    """
    if use_llm_filter:
        # Issue #633: Convert 'all' to None for the filter
        priority = None if filter_priority == "all" else filter_priority
        return await _run_llm_filtered_analysis(
            analyzer, path, pattern_list, llm_model, priority
        )
    else:
        return await _run_environment_analysis(analyzer, path, pattern_list)


async def _cache_env_analysis_results(
    result: dict, full_result: dict, use_llm_filter: bool
) -> None:
    """
    Cache environment analysis results (thread-safe).

    Issue #665: Extracted from get_environment_analysis to reduce function length.
    Issue #633: Only cache non-LLM-filtered results (LLM filtering is dynamic).
    """
    global _env_analysis_cache, _env_analysis_full_cache

    if not use_llm_filter:
        async with _env_analysis_cache_lock:
            _env_analysis_cache = result
            _env_analysis_full_cache = full_result


def _add_llm_filtering_metadata(
    result: dict, analysis: dict, use_llm_filter: bool
) -> None:
    """
    Add LLM filtering metadata to result if applicable.

    Issue #665: Extracted from get_environment_analysis to reduce function length.
    """
    if use_llm_filter and "llm_filtering" in analysis:
        result["llm_filtering"] = analysis["llm_filtering"]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_environment_analysis",
    error_code_prefix="CODEBASE",
)
@router.get("/env-analysis")
async def get_environment_analysis(
    path: str = Query(
        None, description="Root path to analyze (defaults to project root)"
    ),
    refresh: bool = Query(False, description="Force fresh analysis instead of cache"),
    patterns: str = Query(
        "**/*.py", description="Glob patterns for files to scan, comma-separated"
    ),
    use_llm_filter: bool = Query(
        False, description="Issue #633: Use LLM to filter false positives"
    ),
    llm_model: str = Query("llama3.2:1b", description="Ollama model for LLM filtering"),
    filter_priority: str = Query(
        "high",
        description="Priority level to filter: 'high', 'medium', 'low', or 'all'",
    ),
):
    """
    Analyze codebase for hardcoded values and environment variable opportunities (Issue #538).
    Issue #665: Refactored to use extracted helpers for cache, analysis, and result building.
    """
    # Check cache first (Issue #559: thread-safe, Issue #633: LLM filter bypass)
    cached = await _check_env_analysis_cache(use_llm_filter, refresh)
    if cached:
        return cached

    # Setup path and validate security
    project_root = _get_project_root()
    if not path:
        path = project_root

    error_response = _validate_env_path_security(path, project_root)
    if error_response:
        return error_response

    pattern_list = [p.strip() for p in patterns.split(",")]

    try:
        # Get analyzer instance
        analyzer = _get_environment_analyzer()
        if not analyzer:
            return JSONResponse(
                _build_error_response(
                    "EnvironmentAnalyzer not available. Check tools installation."
                )
            )

        # Execute analysis
        analysis = await _execute_env_analysis(
            analyzer, path, pattern_list, use_llm_filter, llm_model, filter_priority
        )

        if analysis is None:
            return JSONResponse(
                _build_error_response(
                    "Analysis timed out after 120s. Try with fewer patterns.",
                    status="partial",
                )
            )

        # Build results
        result = _build_environment_result(analysis, path, for_display=True)
        full_result = _build_environment_result(analysis, path, for_display=False)

        _add_llm_filtering_metadata(result, analysis, use_llm_filter)
        _add_llm_filtering_metadata(full_result, analysis, use_llm_filter)

        # Cache results (Issue #559, #633)
        await _cache_env_analysis_results(result, full_result, use_llm_filter)

        logger.info(
            "Environment analysis complete: %d hardcoded values, %d recommendations%s",
            result["total_hardcoded_values"],
            result["recommendations_count"],
            " (LLM filtered)" if use_llm_filter else "",
        )

        return JSONResponse(result)

    except Exception as e:
        logger.error("Environment analysis failed: %s", e, exc_info=True)
        return JSONResponse(
            _build_error_response(f"Environment analysis failed: {str(e)}")
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_env_recommendations",
    error_code_prefix="CODEBASE",
)
@router.get("/env-recommendations")
async def get_env_recommendations(
    path: str = Query(
        None, description="Root path to analyze (defaults to project root)"
    ),
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
    # Check cache first (thread-safe, Issue #559)
    async with _env_analysis_cache_lock:
        if _env_analysis_cache and _env_analysis_cache.get("recommendations"):
            return JSONResponse(
                {
                    "status": "success",
                    "recommendations": _env_analysis_cache["recommendations"],
                    "total": len(_env_analysis_cache["recommendations"]),
                    "source": "cache",
                }
            )

    # Run fresh analysis if no cache
    if not path:
        path = str(Path(__file__).resolve().parents[4])

    try:
        analyzer = _get_environment_analyzer()
        if not analyzer:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "EnvironmentAnalyzer not available",
                    "recommendations": [],
                    "total": 0,
                }
            )

        analysis = await analyzer.analyze_codebase(path)
        recommendations = analysis.get("configuration_recommendations", [])

        return JSONResponse(
            {
                "status": "success",
                "recommendations": recommendations[:20],
                "total": len(recommendations),
                "source": "live_analysis",
            }
        )

    except Exception as e:
        logger.error("Failed to get env recommendations: %s", e, exc_info=True)
        return JSONResponse(
            {
                "status": "error",
                "message": str(e),
                "recommendations": [],
                "total": 0,
            }
        )


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
        result = [
            v for v in result if v.get("severity", "").lower() == severity.lower()
        ]
    return result


def _sort_by_severity(values: list) -> list:
    """
    Sort values by severity (high first).

    Issue #665: Extracted helper for severity sorting.
    """
    return sorted(
        values, key=lambda v: _SEVERITY_ORDER.get(v.get("severity", "low").lower(), 3)
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
    category: str = Query(
        None, description="Filter by category (e.g., 'security', 'port', 'hostname')"
    ),
    severity: str = Query(
        None, description="Filter by severity ('high', 'medium', 'low')"
    ),
    limit: int = Query(None, description="Limit number of results (default: all)"),
    include_recommendations: bool = Query(
        True, description="Include recommendations in export"
    ),
):
    """
    Export full environment analysis results without truncation (Issue #631).
    Issue #665: Refactored to use extracted helpers for filtering and sorting.
    """
    # Check cache (thread-safe, Issue #559)
    async with _env_analysis_cache_lock:
        if not _env_analysis_full_cache:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "No cached analysis available. Run environment analysis first.",
                    "hardcoded_values": [],
                    "recommendations": [],
                    "total": 0,
                },
                status_code=404,
            )
        full_data = _env_analysis_full_cache.copy()

    # Validate severity (Issue #665: use module constant)
    if severity and severity.lower() not in _VALID_SEVERITIES:
        return JSONResponse(
            {
                "status": "error",
                "message": f"Invalid severity '{severity}'. Must be one of: {', '.join(sorted(_VALID_SEVERITIES))}",
                "hardcoded_values": [],
                "recommendations": [],
                "total": 0,
            },
            status_code=400,
        )

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
        len(hardcoded_values),
        full_data.get("total_hardcoded_values", 0),
        category or "all",
        severity or "all",
    )

    return JSONResponse(
        {
            "status": "success",
            "path": full_data.get("path", ""),
            "export_timestamp": full_data.get("analysis_time_seconds", 0),
            "total_in_export": len(hardcoded_values),
            "total_in_analysis": full_data.get("total_hardcoded_values", 0),
            "categories": category_counts,
            "filters_applied": {
                "category": category,
                "severity": severity,
                "limit": limit,
            },
            "hardcoded_values": hardcoded_values,
            "recommendations": recommendations if include_recommendations else [],
            "recommendations_count": (
                len(recommendations) if include_recommendations else 0
            ),
        }
    )
