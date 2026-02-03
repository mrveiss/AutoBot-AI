# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Duplicate code detection endpoints (Issue #528)

Provides:
- On-demand duplicate code detection using DuplicateCodeDetector
- Cached results in ChromaDB for persistence

Issue #554: Enhanced with semantic analysis support:
- Optional LLM-based semantic duplicate detection
- Redis caching for analysis results
- ChromaDB vector embeddings for code similarity
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.constants.threshold_constants import AnalyticsConfig
from src.utils.error_boundaries import ErrorCategory, with_error_handling

from ..duplicate_detector import DuplicateCodeDetector, detect_duplicates_async
from ..storage import get_code_collection

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache for duplicate analysis (in-memory, refreshed on demand)
_duplicate_cache: Optional[dict] = None


def _get_project_root() -> str:
    """Get project root path (4 levels up from this file)."""
    return str(Path(__file__).resolve().parents[4])


async def _run_semantic_analysis(project_root: str, min_similarity: float):
    """
    Run semantic duplicate analysis using LLM embeddings.

    Args:
        project_root: Root directory to analyze
        min_similarity: Minimum similarity threshold

    Returns:
        Analysis result or None if failed
    """
    try:
        analysis = await detect_duplicates_async(
            project_root=project_root,
            min_similarity=min_similarity,
            use_semantic_analysis=True,
        )
        logger.info("Semantic duplicate analysis complete")
        return analysis
    except Exception as e:
        logger.warning("Semantic analysis failed, falling back to standard: %s", e)
        return None


async def _run_standard_analysis(project_root: str, min_similarity: float):
    """
    Run standard duplicate analysis in thread pool with timeout.

    Args:
        project_root: Root directory to analyze
        min_similarity: Minimum similarity threshold

    Returns:
        Analysis result or None if timed out
    """
    loop = asyncio.get_event_loop()
    try:
        analysis = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: DuplicateCodeDetector(
                    project_root=project_root,
                    min_similarity=min_similarity,
                ).run_analysis(),
            ),
            timeout=AnalyticsConfig.DUPLICATE_DETECTION_TIMEOUT,
        )
        return analysis
    except asyncio.TimeoutError:
        logger.warning(
            "Duplicate detection timed out after %d seconds",
            AnalyticsConfig.DUPLICATE_DETECTION_TIMEOUT,
        )
        return None


def _convert_analysis_to_result(analysis, project_root: str) -> dict:
    """
    Convert analysis result to frontend-compatible format.

    Args:
        analysis: DuplicateAnalysis result
        project_root: Project root for relative paths

    Returns:
        Frontend-compatible result dict
    """
    duplicates_for_frontend = []
    for dup in analysis.duplicates:
        duplicates_for_frontend.append(
            {
                "file1": _make_relative_path(dup.file1, project_root),
                "file2": _make_relative_path(dup.file2, project_root),
                "start_line1": dup.start_line1,
                "end_line1": dup.end_line1,
                "start_line2": dup.start_line2,
                "end_line2": dup.end_line2,
                "similarity": round(dup.similarity * 100, 1),
                "lines": dup.line_count,
                "code_snippet": dup.code_snippet[:200] if dup.code_snippet else "",
            }
        )

    return {
        "status": "success",
        "duplicates": duplicates_for_frontend,
        "total_count": analysis.total_duplicates,
        "high_similarity_count": analysis.high_similarity_count,
        "medium_similarity_count": analysis.medium_similarity_count,
        "low_similarity_count": analysis.low_similarity_count,
        "total_duplicate_lines": analysis.total_duplicate_lines,
        "files_analyzed": analysis.files_analyzed,
        "scan_timestamp": analysis.scan_timestamp,
        "storage_type": "live_analysis",
    }


def _get_chromadb_fallback(error_msg: str) -> Optional[dict]:
    """
    Get cached duplicates from ChromaDB as fallback.

    Args:
        error_msg: Error message to include in warning

    Returns:
        Fallback result dict or None if unavailable
    """
    code_collection = get_code_collection()
    if not code_collection:
        return None

    try:
        results = code_collection.get(
            where={"type": "duplicate"}, include=["metadatas"]
        )

        all_duplicates = []
        for metadata in results.get("metadatas", []):
            all_duplicates.append(
                {
                    "file1": metadata.get("file1", ""),
                    "file2": metadata.get("file2", ""),
                    "similarity": float(metadata.get("similarity", 0)),
                    "lines": int(metadata.get("lines", 0)),
                    "code_snippet": metadata.get("code_snippet", ""),
                }
            )

        return {
            "status": "success",
            "duplicates": all_duplicates,
            "total_count": len(all_duplicates),
            "storage_type": "chromadb_fallback",
            "warning": f"Live analysis failed, showing cached results: {error_msg}",
        }
    except Exception:
        return None


def _build_timeout_response() -> dict:
    """
    Build response for analysis timeout case.

    Issue #620: Extracted from get_duplicate_code to reduce function length.

    Returns:
        JSONResponse-compatible dict for timeout scenario
    """
    return {
        "status": "partial",
        "message": (
            f"Analysis timed out after {AnalyticsConfig.DUPLICATE_DETECTION_TIMEOUT}s. "
            "Try a higher min_similarity threshold."
        ),
        "duplicates": [],
        "total_count": 0,
        "storage_type": "timeout",
    }


def _build_detection_error_response(error_msg: str) -> dict:
    """
    Build error response for duplicate detection failure.

    Issue #620: Extracted from get_duplicate_code to reduce function length.

    Args:
        error_msg: Error message to include

    Returns:
        JSONResponse-compatible dict for error scenario
    """
    return {
        "status": "error",
        "message": f"Duplicate detection failed: {error_msg}",
        "duplicates": [],
        "total_count": 0,
    }


def _process_and_cache_analysis(analysis, project_root: str) -> dict:
    """
    Convert analysis to result dict and log completion.

    Issue #620: Extracted from get_duplicate_code to reduce function length.

    Args:
        analysis: Analysis result object
        project_root: Project root path

    Returns:
        Result dict suitable for JSONResponse
    """
    global _duplicate_cache

    result = _convert_analysis_to_result(analysis, project_root)
    _duplicate_cache = result

    logger.info(
        "Duplicate analysis complete: %d duplicates (%d high, %d medium, %d low)",
        analysis.total_duplicates,
        analysis.high_similarity_count,
        analysis.medium_similarity_count,
        analysis.low_similarity_count,
    )

    return result


async def _run_duplicate_analysis(
    project_root: str, min_similarity: float, use_semantic: bool
):
    """
    Run duplicate analysis with semantic or standard detection.

    Issue #620: Extracted from get_duplicate_code to reduce function length.

    Args:
        project_root: Root directory to analyze
        min_similarity: Minimum similarity threshold
        use_semantic: Whether to use semantic analysis

    Returns:
        Analysis result or None if timeout/failure
    """
    analysis = None

    if use_semantic:
        analysis = await _run_semantic_analysis(project_root, min_similarity)

    if analysis is None:
        analysis = await _run_standard_analysis(project_root, min_similarity)

    return analysis


def _check_duplicate_cache(refresh: bool) -> Optional[JSONResponse]:
    """
    Check if cached results are available and return them.

    Issue #620: Extracted from get_duplicate_code to reduce function length.

    Args:
        refresh: Whether to force fresh analysis

    Returns:
        JSONResponse with cached data, or None if cache miss/refresh requested
    """
    if _duplicate_cache and not refresh:
        logger.info(
            "Returning cached duplicate analysis (%d duplicates)",
            _duplicate_cache.get("total_count", 0),
        )
        return JSONResponse(_duplicate_cache)
    return None


def _handle_detection_failure(error: Exception) -> JSONResponse:
    """
    Handle duplicate detection failure with fallback.

    Issue #620: Extracted from get_duplicate_code to reduce function length.

    Args:
        error: Exception that occurred

    Returns:
        JSONResponse with fallback data or error response
    """
    logger.error("Duplicate detection failed: %s", error, exc_info=True)

    fallback = _get_chromadb_fallback(str(error))
    if fallback:
        return JSONResponse(fallback)

    return JSONResponse(_build_detection_error_response(str(error)))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_duplicate_code",
    error_code_prefix="CODEBASE",
)
@router.get("/duplicates")
async def get_duplicate_code(
    refresh: bool = Query(False, description="Force fresh analysis instead of cache"),
    min_similarity: float = Query(
        0.5, description="Minimum similarity threshold (0.0-1.0)"
    ),
    use_semantic: bool = Query(
        False, description="Enable LLM-based semantic analysis (Issue #554)"
    ),
):
    """
    Get duplicate code detected in the codebase (Issue #528).

    Uses the DuplicateCodeDetector for real analysis of:
    - Exact hash matches (100% similarity)
    - Near-duplicate code blocks (token-based similarity)
    - Semantic duplicates via LLM embeddings (Issue #554, when use_semantic=True)

    Args:
        refresh: Force fresh analysis instead of using cached results
        min_similarity: Minimum similarity threshold (0.5 = 50%)
        use_semantic: Enable LLM-based semantic duplicate detection (Issue #554)

    Returns:
        JSON with duplicates, statistics, and analysis metadata
    """
    # Check cache first - Issue #620: Use helper
    cached = _check_duplicate_cache(refresh)
    if cached:
        return cached

    project_root = _get_project_root()

    try:
        # Run analysis (semantic or standard) - Issue #620: Use helper
        analysis = await _run_duplicate_analysis(
            project_root, min_similarity, use_semantic
        )

        # Handle timeout case - Issue #620: Use helper
        if analysis is None:
            return JSONResponse(_build_timeout_response())

        # Convert, cache, and return results - Issue #620: Use helper
        result = _process_and_cache_analysis(analysis, project_root)
        return JSONResponse(result)

    except Exception as e:
        # Issue #620: Use helper for error handling
        return _handle_detection_failure(e)


def _make_relative_path(path: str, project_root: str) -> str:
    """Convert absolute path to relative path for cleaner display."""
    try:
        return str(Path(path).relative_to(project_root))
    except ValueError:
        return path


async def _run_semantic_config_detection(project_root: Path) -> Optional[dict]:
    """
    Run semantic config duplicate detection.

    Issue #620: Extracted from detect_config_duplicates_endpoint.

    Args:
        project_root: Project root path

    Returns:
        Detection result dict or None if failed
    """
    from ..config_duplication_detector import ConfigDuplicationDetector

    try:
        detector = ConfigDuplicationDetector(
            str(project_root),
            use_semantic_analysis=True,
        )
        await asyncio.to_thread(detector.scan_directory)
        result = {
            "duplicates_found": 0,
            "duplicates": await detector.find_duplicates_async(),
            "report": await asyncio.to_thread(detector.generate_report),
        }
        result["duplicates_found"] = len(result["duplicates"])
        logger.info("Semantic config duplicate analysis complete")
        return result
    except Exception as e:
        logger.warning("Semantic analysis failed, falling back to standard: %s", e)
        return None


async def _run_standard_config_detection(project_root: Path) -> dict:
    """
    Run standard config duplicate detection.

    Issue #620: Extracted from detect_config_duplicates_endpoint.

    Args:
        project_root: Project root path

    Returns:
        Detection result dict
    """
    from ..config_duplication_detector import detect_config_duplicates

    return await asyncio.to_thread(detect_config_duplicates, str(project_root))


def _convert_config_duplicates_to_array(duplicates_dict: dict) -> list:
    """
    Convert duplicates dict to frontend-compatible array format.

    Issue #620: Extracted from detect_config_duplicates_endpoint.

    Args:
        duplicates_dict: Backend format {value: {value, count, sources, duplicates}}

    Returns:
        Frontend format [{value, count, locations: [{file, line}]}]
    """
    duplicates_array = []
    for value, details in duplicates_dict.items():
        all_locations = details.get("sources", []) + details.get("duplicates", [])
        duplicates_array.append(
            {
                "value": value,
                "count": details.get("count", len(all_locations)),
                "locations": [
                    {"file": loc["file"], "line": loc["line"]} for loc in all_locations
                ],
            }
        )
    return duplicates_array


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_config_duplicates",
    error_code_prefix="CODEBASE",
)
@router.get("/config-duplicates")
async def detect_config_duplicates_endpoint(
    use_semantic: bool = Query(
        False, description="Enable LLM-based semantic analysis (Issue #554)"
    ),
):
    """
    Detect configuration value duplicates across codebase (Issue #341).

    Issue #554: Enhanced with optional semantic analysis.
    Issue #620: Refactored to use helper functions.

    Args:
        use_semantic: Enable semantic duplicate detection via LLM embeddings

    Returns:
        JSONResponse with duplicate detection results
    """
    project_root = Path(__file__).resolve().parents[4]

    # Issue #620: Use helpers for detection
    result = None
    if use_semantic:
        result = await _run_semantic_config_detection(project_root)

    if result is None:
        result = await _run_standard_config_detection(project_root)

    # Issue #620: Use helper for array conversion
    duplicates_array = _convert_config_duplicates_to_array(result["duplicates"])

    return JSONResponse(
        {
            "status": "success",
            "duplicates_found": result["duplicates_found"],
            "duplicates": duplicates_array,
            "report": result["report"],
        }
    )
