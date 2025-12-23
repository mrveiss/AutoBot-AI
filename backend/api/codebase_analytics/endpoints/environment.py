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
# Lock for thread-safe access to _env_analysis_cache (Issue #559)
_env_analysis_cache_lock = asyncio.Lock()


def _get_environment_analyzer():
    """
    Get EnvironmentAnalyzer instance.

    Lazy import to avoid circular dependencies and allow graceful degradation
    if the tools module is not available.

    Issue #542: Fixed import path resolution by adding project root to sys.path
    before the tools path, allowing env_analyzer.py to import from src.utils.
    """
    try:
        # Issue #542: Add project root FIRST so env_analyzer.py can import from src.utils
        project_root = str(Path(__file__).resolve().parents[4])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        # Add tools path second for importing the analyzer module itself
        tools_path = str(Path(__file__).resolve().parents[4] / "tools" / "code-analysis-suite")
        if tools_path not in sys.path:
            sys.path.insert(0, tools_path)

        from src.env_analyzer import EnvironmentAnalyzer
        return EnvironmentAnalyzer()
    except ImportError as e:
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

    # Get project root if path not specified
    project_root = str(Path(__file__).resolve().parents[4])
    if not path:
        path = project_root

    # Security: Validate path is within project root to prevent path traversal
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

    # Parse patterns
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

        # Run analysis with timeout
        # Handle both async and sync analyzer methods
        ANALYSIS_TIMEOUT = 120  # 2 minute timeout for large codebases
        try:
            coro = analyzer.analyze_codebase(path, pattern_list)
            # Check if the method returns a coroutine
            if asyncio.iscoroutine(coro):
                analysis = await asyncio.wait_for(coro, timeout=ANALYSIS_TIMEOUT)
            else:
                # If sync method, run in thread pool
                loop = asyncio.get_event_loop()
                analysis = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: coro),
                    timeout=ANALYSIS_TIMEOUT
                )
        except asyncio.TimeoutError:
            logger.warning("Environment analysis timed out after %d seconds", ANALYSIS_TIMEOUT)
            return JSONResponse({
                "status": "partial",
                "message": f"Analysis timed out after {ANALYSIS_TIMEOUT}s. Try with fewer patterns.",
                "total_hardcoded_values": 0,
                "categories": {},
                "recommendations_count": 0,
            })

        result = {
            "status": "success",
            "path": path,
            "total_hardcoded_values": analysis.get("total_hardcoded_values", 0),
            "high_priority_count": analysis.get("high_priority_count", 0),
            "recommendations_count": analysis.get("recommendations_count", 0),
            "categories": analysis.get("categories", {}),
            "analysis_time_seconds": analysis.get("analysis_time_seconds", 0),
            "hardcoded_values": analysis.get("hardcoded_details", [])[:50],  # Limit to 50 for response size
            "recommendations": analysis.get("configuration_recommendations", [])[:20],  # Limit recommendations
            "metrics": analysis.get("metrics", {}),
            "storage_type": "live_analysis",
        }

        # Cache the results (thread-safe, Issue #559)
        async with _env_analysis_cache_lock:
            _env_analysis_cache = result
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
