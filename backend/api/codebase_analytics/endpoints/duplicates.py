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
                ).run_analysis()
            ),
            timeout=AnalyticsConfig.DUPLICATE_DETECTION_TIMEOUT
        )
        return analysis
    except asyncio.TimeoutError:
        logger.warning(
            "Duplicate detection timed out after %d seconds",
            AnalyticsConfig.DUPLICATE_DETECTION_TIMEOUT
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
        duplicates_for_frontend.append({
            "file1": _make_relative_path(dup.file1, project_root),
            "file2": _make_relative_path(dup.file2, project_root),
            "start_line1": dup.start_line1,
            "end_line1": dup.end_line1,
            "start_line2": dup.start_line2,
            "end_line2": dup.end_line2,
            "similarity": round(dup.similarity * 100, 1),
            "lines": dup.line_count,
            "code_snippet": dup.code_snippet[:200] if dup.code_snippet else "",
        })

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
            all_duplicates.append({
                "file1": metadata.get("file1", ""),
                "file2": metadata.get("file2", ""),
                "similarity": float(metadata.get("similarity", 0)),
                "lines": int(metadata.get("lines", 0)),
                "code_snippet": metadata.get("code_snippet", ""),
            })

        return {
            "status": "success",
            "duplicates": all_duplicates,
            "total_count": len(all_duplicates),
            "storage_type": "chromadb_fallback",
            "warning": f"Live analysis failed, showing cached results: {error_msg}",
        }
    except Exception:
        return None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_duplicate_code",
    error_code_prefix="CODEBASE",
)
@router.get("/duplicates")
async def get_duplicate_code(
    refresh: bool = Query(False, description="Force fresh analysis instead of cache"),
    min_similarity: float = Query(0.5, description="Minimum similarity threshold (0.0-1.0)"),
    use_semantic: bool = Query(False, description="Enable LLM-based semantic analysis (Issue #554)"),
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
    global _duplicate_cache

    # Use cached results if available and not refreshing
    if _duplicate_cache and not refresh:
        logger.info("Returning cached duplicate analysis (%d duplicates)", _duplicate_cache.get("total_count", 0))
        return JSONResponse(_duplicate_cache)

    project_root = _get_project_root()

    try:
        # Try semantic analysis first if requested
        analysis = None
        if use_semantic:
            analysis = await _run_semantic_analysis(project_root, min_similarity)

        # Fall back to standard analysis
        if analysis is None:
            analysis = await _run_standard_analysis(project_root, min_similarity)

        # Handle timeout case
        if analysis is None:
            return JSONResponse({
                "status": "partial",
                "message": f"Analysis timed out after {AnalyticsConfig.DUPLICATE_DETECTION_TIMEOUT}s. Try a higher min_similarity threshold.",
                "duplicates": [],
                "total_count": 0,
                "storage_type": "timeout",
            })

        # Convert and cache results
        result = _convert_analysis_to_result(analysis, project_root)
        _duplicate_cache = result

        logger.info(
            "Duplicate analysis complete: %d duplicates (%d high, %d medium, %d low)",
            analysis.total_duplicates,
            analysis.high_similarity_count,
            analysis.medium_similarity_count,
            analysis.low_similarity_count,
        )

        return JSONResponse(result)

    except Exception as e:
        logger.error("Duplicate detection failed: %s", e, exc_info=True)

        # Try ChromaDB fallback
        fallback = _get_chromadb_fallback(str(e))
        if fallback:
            return JSONResponse(fallback)

        return JSONResponse({
            "status": "error",
            "message": f"Duplicate detection failed: {str(e)}",
            "duplicates": [],
            "total_count": 0,
        })


def _make_relative_path(path: str, project_root: str) -> str:
    """Convert absolute path to relative path for cleaner display."""
    try:
        return str(Path(path).relative_to(project_root))
    except ValueError:
        return path


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_config_duplicates",
    error_code_prefix="CODEBASE",
)
@router.get("/config-duplicates")
async def detect_config_duplicates_endpoint(
    use_semantic: bool = Query(False, description="Enable LLM-based semantic analysis (Issue #554)"),
):
    """
    Detect configuration value duplicates across codebase (Issue #341).

    Returns configuration values that appear in multiple files,
    helping enforce single-source-of-truth principle.

    Issue #554: Enhanced with optional semantic analysis:
    - use_semantic=True enables LLM-based semantic config pattern matching
    - Results cached in Redis for performance

    Args:
        use_semantic: Enable semantic duplicate detection via LLM embeddings

    Returns:
        JSONResponse with duplicate detection results
    """
    from ..config_duplication_detector import ConfigDuplicationDetector, detect_config_duplicates

    # Get project root (4 levels up from this file: endpoints -> codebase_analytics -> api -> backend -> root)
    project_root = Path(__file__).resolve().parents[4]

    # Issue #554: Use async method with semantic analysis if enabled
    if use_semantic:
        try:
            detector = ConfigDuplicationDetector(
                str(project_root),
                use_semantic_analysis=True,
            )
            # Issue #666: Wrap blocking file I/O in asyncio.to_thread
            await asyncio.to_thread(detector.scan_directory)
            result = {
                "duplicates_found": 0,
                "duplicates": await detector.find_duplicates_async(),
                # Issue #666: Wrap blocking call in asyncio.to_thread
                "report": await asyncio.to_thread(detector.generate_report),
            }
            result["duplicates_found"] = len(result["duplicates"])
            logger.info("Semantic config duplicate analysis complete")
        except Exception as e:
            logger.warning("Semantic analysis failed, falling back to standard: %s", e)
            # Issue #666: Wrap blocking file I/O in asyncio.to_thread
            result = await asyncio.to_thread(detect_config_duplicates, str(project_root))
    else:
        # Run standard detection
        # Issue #666: Wrap blocking file I/O in asyncio.to_thread
        result = await asyncio.to_thread(detect_config_duplicates, str(project_root))

    # Convert duplicates dict to array format for frontend compatibility
    # Backend returns: {value: {value, count, sources, duplicates}}
    # Frontend expects: [{value, locations: [{file, line}]}]
    duplicates_dict = result["duplicates"]
    duplicates_array = []
    for value, details in duplicates_dict.items():
        all_locations = details.get("sources", []) + details.get("duplicates", [])
        duplicates_array.append({
            "value": value,
            "count": details.get("count", len(all_locations)),
            "locations": [{"file": loc["file"], "line": loc["line"]} for loc in all_locations],
        })

    return JSONResponse(
        {
            "status": "success",
            "duplicates_found": result["duplicates_found"],
            "duplicates": duplicates_array,
            "report": result["report"],
        }
    )
