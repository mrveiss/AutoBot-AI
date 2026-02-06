# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Ownership and Expertise endpoints (Issue #248)

Provides:
- Code ownership analysis per file/directory
- Expertise scoring by contributor
- Knowledge gap detection
- Team coverage metrics
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

router = APIRouter(prefix="/ownership", tags=["ownership"])

# Cache for ownership analysis (in-memory, refreshed on demand)
_ownership_analysis_cache: Optional[dict] = None
_ownership_analysis_cache_lock = asyncio.Lock()


def _get_ownership_analyzer():
    """
    Get OwnershipAnalyzer instance.

    Lazy import to avoid circular dependencies and allow graceful degradation
    if the tools module is not available.
    """
    try:
        import importlib.util

        # Add project root so ownership_analyzer.py can import from src.utils
        project_root = str(Path(__file__).resolve().parents[4])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        # Load ownership_analyzer directly from file to avoid namespace conflict
        analyzer_path = (
            Path(__file__).resolve().parents[4]
            / "tools"
            / "code-analysis-suite"
            / "src"
            / "ownership_analyzer.py"
        )

        if not analyzer_path.exists():
            logger.warning(
                "OwnershipAnalyzer not available: %s does not exist", analyzer_path
            )
            return None

        spec = importlib.util.spec_from_file_location(
            "ownership_analyzer", analyzer_path
        )
        if spec is None or spec.loader is None:
            logger.warning("OwnershipAnalyzer not available: Could not load spec")
            return None

        analyzer_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(analyzer_module)

        return analyzer_module.OwnershipAnalyzer()
    except Exception as e:
        logger.warning("OwnershipAnalyzer not available: %s", e)
        return None


def _get_project_root() -> str:
    """Get project root path (4 levels up from this file)."""
    return str(Path(__file__).resolve().parents[4])


def _validate_path_security(path: str, project_root: str) -> Optional[JSONResponse]:
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
                    "summary": {},
                    "file_ownership": [],
                    "directory_ownership": [],
                    "expertise_scores": [],
                    "knowledge_gaps": [],
                    "metrics": {},
                },
                status_code=400,
            )
    except Exception as e:
        logger.warning("Invalid path provided: %s - %s", path, e)
        return JSONResponse(
            {
                "status": "error",
                "message": f"Invalid path: {str(e)}",
                "summary": {},
            },
            status_code=400,
        )

    return None


async def _run_ownership_analysis(analyzer, path: str, pattern_list: list, days: int):
    """
    Run ownership analysis with timeout.

    Args:
        analyzer: OwnershipAnalyzer instance
        path: Path to analyze
        pattern_list: List of glob patterns
        days: Days for recency scoring

    Returns:
        Analysis result or None if timed out
    """
    ANALYSIS_TIMEOUT = 180  # 3 minute timeout for git operations
    try:
        coro = analyzer.analyze_ownership(path, pattern_list, days)
        if asyncio.iscoroutine(coro):
            return await asyncio.wait_for(coro, timeout=ANALYSIS_TIMEOUT)
        else:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, lambda: coro), timeout=ANALYSIS_TIMEOUT
            )
    except asyncio.TimeoutError:
        logger.warning(
            "Ownership analysis timed out after %d seconds", ANALYSIS_TIMEOUT
        )
        return None


def _build_ownership_result(analysis: dict, path: str) -> dict:
    """Build success result from analysis data with limits on list sizes."""
    return {
        "status": "success",
        "path": path,
        "analysis_time_seconds": analysis.get("analysis_time_seconds", 0),
        "summary": analysis.get("summary", {}),
        "file_ownership": analysis.get("file_ownership", [])[:50],
        "directory_ownership": analysis.get("directory_ownership", [])[:30],
        "expertise_scores": analysis.get("expertise_scores", [])[:20],
        "knowledge_gaps": analysis.get("knowledge_gaps", [])[:30],
        "metrics": analysis.get("metrics", {}),
        "storage_type": "live_analysis",
    }


def _build_ownership_error_response(message: str, include_lists: bool = True) -> dict:
    """Build error response for ownership analysis.

    Issue #665: Extracted from get_ownership_analysis to reduce function length.

    Args:
        message: Error message to include
        include_lists: Whether to include empty list fields

    Returns:
        Error response dictionary
    """
    response = {
        "status": "error",
        "message": message,
        "summary": {},
    }
    if include_lists:
        response.update(
            {
                "file_ownership": [],
                "directory_ownership": [],
                "expertise_scores": [],
                "knowledge_gaps": [],
                "metrics": {},
            }
        )
    return response


def _build_expertise_response(
    scores: list, total: int, source: str, status: str = "success"
) -> dict:
    """Build response for expertise scores endpoint.

    Issue #665: Extracted from get_expertise_scores to reduce function length.

    Args:
        scores: List of expertise scores
        total: Total number of scores
        source: Data source (cache or live_analysis)
        status: Response status

    Returns:
        Response dictionary
    """
    return {
        "status": status,
        "expertise_scores": scores,
        "total": total,
        "source": source,
    }


def _build_expertise_error(message: str) -> dict:
    """Build error response for expertise scores endpoint.

    Issue #665: Extracted from get_expertise_scores to reduce function length.

    Args:
        message: Error message

    Returns:
        Error response dictionary
    """
    return {
        "status": "error",
        "message": message,
        "expertise_scores": [],
        "total": 0,
    }


def _build_knowledge_gaps_response(
    gaps: list, total: int, source: str, status: str = "success"
) -> dict:
    """Build response for knowledge gaps endpoint.

    Issue #665: Extracted from get_knowledge_gaps to reduce function length.

    Args:
        gaps: List of knowledge gaps
        total: Total number of gaps
        source: Data source (cache or live_analysis)
        status: Response status

    Returns:
        Response dictionary
    """
    return {
        "status": status,
        "knowledge_gaps": gaps,
        "total": total,
        "source": source,
    }


def _build_knowledge_gaps_error(message: str) -> dict:
    """Build error response for knowledge gaps endpoint.

    Issue #665: Extracted from get_knowledge_gaps to reduce function length.

    Args:
        message: Error message

    Returns:
        Error response dictionary
    """
    return {
        "status": "error",
        "message": message,
        "knowledge_gaps": [],
        "total": 0,
    }


async def _check_ownership_cache(refresh: bool) -> Optional[JSONResponse]:
    """Check cache for ownership analysis results.

    Issue #665: Extracted from get_ownership_analysis to reduce function length.
    """
    async with _ownership_analysis_cache_lock:
        if _ownership_analysis_cache and not refresh:
            logger.info(
                "Returning cached ownership analysis (%d files)",
                _ownership_analysis_cache.get("summary", {}).get("total_files", 0),
            )
            return JSONResponse(_ownership_analysis_cache)
    return None


async def _cache_ownership_result(result: dict) -> None:
    """Cache ownership analysis result.

    Issue #665: Extracted from get_ownership_analysis to reduce function length.
    """
    global _ownership_analysis_cache
    async with _ownership_analysis_cache_lock:
        _ownership_analysis_cache = result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_ownership_analysis",
    error_code_prefix="CODEBASE",
)
@router.get("/analysis")
async def get_ownership_analysis(
    path: str = Query(None, description="Root path to analyze"),
    refresh: bool = Query(False, description="Force fresh analysis"),
    patterns: str = Query("**/*.py,**/*.ts,**/*.vue", description="Glob patterns"),
    days: int = Query(90, description="Days for recency scoring"),
):
    """Analyze code ownership (Issue #248). Issue #665: Refactored with helpers."""
    cached = await _check_ownership_cache(refresh)
    if cached:
        return cached

    project_root = _get_project_root()
    if not path:
        path = project_root

    error_response = _validate_path_security(path, project_root)
    if error_response:
        return error_response

    pattern_list = [p.strip() for p in patterns.split(",")]

    try:
        analyzer = _get_ownership_analyzer()
        if not analyzer:
            return JSONResponse(
                _build_ownership_error_response(
                    "OwnershipAnalyzer not available. Check tools installation."
                )
            )

        analysis = await _run_ownership_analysis(analyzer, path, pattern_list, days)
        if analysis is None:
            return JSONResponse(
                {
                    "status": "partial",
                    "message": "Analysis timed out after 180s. Try with fewer patterns.",
                    "summary": {},
                }
            )

        result = _build_ownership_result(analysis, path)
        await _cache_ownership_result(result)

        logger.info(
            "Ownership analysis complete: %d files, %d gaps",
            result["summary"].get("total_files", 0),
            result["summary"].get("knowledge_gaps_count", 0),
        )
        return JSONResponse(result)

    except Exception as e:
        logger.error("Ownership analysis failed: %s", e, exc_info=True)
        return JSONResponse(
            _build_ownership_error_response(
                f"Ownership analysis failed: {str(e)}", include_lists=False
            )
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_expertise_scores",
    error_code_prefix="CODEBASE",
)
@router.get("/expertise")
async def get_expertise_scores(
    path: str = Query(None, description="Root path to analyze"),
):
    """
    Get contributor expertise scores for a codebase (Issue #248).
    Issue #665: Refactored to use extracted helpers for response building.

    Returns expertise rankings based on:
    - Lines of code authored
    - Commit frequency
    - Recency of contributions
    - Number of files/directories owned
    """
    # Check cache first
    async with _ownership_analysis_cache_lock:
        if _ownership_analysis_cache and _ownership_analysis_cache.get(
            "expertise_scores"
        ):
            scores = _ownership_analysis_cache["expertise_scores"]
            return JSONResponse(_build_expertise_response(scores, len(scores), "cache"))

    # Run fresh analysis if no cache
    project_root = _get_project_root()
    if not path:
        path = project_root

    # Security: Validate path is within project root
    error_response = _validate_path_security(path, project_root)
    if error_response:
        return error_response

    try:
        analyzer = _get_ownership_analyzer()
        if not analyzer:
            return JSONResponse(
                _build_expertise_error("OwnershipAnalyzer not available")
            )

        analysis = await analyzer.analyze_ownership(path)
        expertise_scores = analysis.get("expertise_scores", [])

        return JSONResponse(
            _build_expertise_response(
                expertise_scores[:20], len(expertise_scores), "live_analysis"
            )
        )

    except Exception as e:
        logger.error("Failed to get expertise scores: %s", e, exc_info=True)
        return JSONResponse(_build_expertise_error(str(e)))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_gaps",
    error_code_prefix="CODEBASE",
)
@router.get("/knowledge-gaps")
async def get_knowledge_gaps(
    path: str = Query(None, description="Root path to analyze"),
    risk_level: str = Query(
        None, description="Filter by risk level (critical, high, medium, low)"
    ),
):
    """
    Get knowledge gaps in the codebase (Issue #248).
    Issue #665: Refactored to use extracted helpers for response building.

    Detects areas with:
    - Single contributor (bus factor = 1)
    - Inactive maintainers
    - High ownership concentration
    """
    # Check cache first
    async with _ownership_analysis_cache_lock:
        if _ownership_analysis_cache and _ownership_analysis_cache.get(
            "knowledge_gaps"
        ):
            gaps = _ownership_analysis_cache["knowledge_gaps"]
            if risk_level:
                gaps = [g for g in gaps if g.get("risk_level") == risk_level]
            return JSONResponse(
                _build_knowledge_gaps_response(gaps, len(gaps), "cache")
            )

    # Run fresh analysis if no cache
    project_root = _get_project_root()
    if not path:
        path = project_root

    # Security: Validate path is within project root
    error_response = _validate_path_security(path, project_root)
    if error_response:
        return error_response

    try:
        analyzer = _get_ownership_analyzer()
        if not analyzer:
            return JSONResponse(
                _build_knowledge_gaps_error("OwnershipAnalyzer not available")
            )

        analysis = await analyzer.analyze_ownership(path)
        gaps = analysis.get("knowledge_gaps", [])

        if risk_level:
            gaps = [g for g in gaps if g.get("risk_level") == risk_level]

        return JSONResponse(
            _build_knowledge_gaps_response(gaps[:30], len(gaps), "live_analysis")
        )

    except Exception as e:
        logger.error("Failed to get knowledge gaps: %s", e, exc_info=True)
        return JSONResponse(_build_knowledge_gaps_error(str(e)))
