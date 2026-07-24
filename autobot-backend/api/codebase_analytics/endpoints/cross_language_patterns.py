# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Cross-Language Pattern Detection API endpoints (Issue #244)

Provides endpoints to:
- Run cross-language pattern analysis
- Get DTO mismatches between backend/frontend
- Get validation duplications
- Get API contract mismatches
- Get semantic pattern matches
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from code_intelligence.cross_language_patterns import CrossLanguagePatternDetector

from .shared import resolve_scan_root

logger = get_logger(__name__)

router = APIRouter()

# Cache for analysis results.
# Issue #12356: Keyed by source_id (or "default") to prevent cross-project
# leakage -- a single global "latest" entry returned one project's cross-language
# patterns for every other selected source.
_analysis_cache: dict = {}
# Lock for thread-safe access to _analysis_cache (Issue #559)
_analysis_cache_lock = asyncio.Lock()


def _cache_key(source_id: str | None) -> str:
    """Cache key for a source. Issue #12356: scope per project, not global."""
    return source_id or "default"


def _get_detector(
    project_root: Path | None = None,
    source_id: str | None = None,
    use_llm: bool = True,
    use_cache: bool = True,
) -> CrossLanguagePatternDetector:
    """Get or create the pattern detector instance.

    Issue #12356: Bind the detector to the requested source's clone path and
    scope tag so it scans the selected project and keys its ChromaDB pattern
    collection/query + embedding cache per source, rather than defaulting to
    AutoBot's own root and a shared, unscoped collection.
    """
    return CrossLanguagePatternDetector(
        project_root=str(project_root) if project_root else None,
        use_llm=use_llm,
        use_cache=use_cache,
        embedding_model="nomic-embed-text",
        source_id=source_id,
    )


async def _get_cached_analysis(source_id: str | None):
    """Return the cached analysis for a source, or None (Issue #12356).

    Reads only the requested source's entry so one project's cached patterns
    are never returned for another selected source.
    """
    async with _analysis_cache_lock:
        return _analysis_cache.get(_cache_key(source_id))


@router.post("/cross-language/analyze")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_cross_language_analysis",
    error_code_prefix="CODEBASE",
)
async def run_cross_language_analysis(
    use_llm: bool = True,
    use_cache: bool = True,
    source_id: str | None = Query(None, description="#12356: scope analysis to the selected code source"),
) -> JSONResponse:
    """
    Run full cross-language pattern analysis.

    Analyzes Python backend and TypeScript/Vue frontend for:
    - DTO/type mismatches
    - Validation duplications
    - API contract mismatches
    - Semantic pattern similarities

    Args:
        use_llm: Whether to use LLM for semantic analysis (default: True)
        use_cache: Whether to cache results (default: True)
        source_id: Scope the scan and cache to the selected code source
            (Issue #12356). Falls back to AutoBot's own root only when no source
            is resolvable.

    Returns:
        Complete analysis results with all detected patterns
    """
    # Issue #12356: scan the requested source's clone path (not AutoBot's own
    # root) and key both the detector and this cache entry per source.
    scan_root = await resolve_scan_root(source_id)
    detector = _get_detector(
        project_root=scan_root,
        source_id=source_id,
        use_llm=use_llm,
        use_cache=use_cache,
    )

    analysis = await detector.run_analysis()

    # Cache the result per source (thread-safe, Issue #559 / #12356)
    async with _analysis_cache_lock:
        _analysis_cache[_cache_key(source_id)] = analysis

    return JSONResponse(
        {
            "status": "success",
            "analysis": analysis.to_dict(),
        }
    )


@router.get("/cross-language/summary")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cross_language_summary",
    error_code_prefix="CODEBASE",
)
async def get_cross_language_summary(
    source_id: str | None = Query(None, description="#12356: scope to the selected code source"),
) -> JSONResponse:
    """
    Get summary of latest cross-language analysis.

    Returns cached results if available, otherwise returns empty status.
    Use POST /cross-language/analyze to trigger a new analysis.
    Issue #12356: Reads only the selected source's cached analysis.
    """
    # Check cache first (thread-safe, Issue #559 / #12356: per-source)
    analysis = await _get_cached_analysis(source_id)
    if analysis is None:
        # Return empty status instead of auto-running full analysis
        # Full analysis can take minutes and should only be triggered
        # via POST /analyze endpoint explicitly
        return JSONResponse(
            {
                "status": "empty",
                "message": "No analysis available. Click 'Full Scan' to run analysis.",
                "has_cached_data": False,
            }
        )

    return JSONResponse(
        {
            "status": "success",
            "has_cached_data": True,
            "summary": {
                "analysis_id": analysis.analysis_id,
                "scan_timestamp": analysis.scan_timestamp.isoformat(),
                "files_analyzed": {
                    "python": analysis.python_files_analyzed,
                    "typescript": analysis.typescript_files_analyzed,
                    "vue": analysis.vue_files_analyzed,
                    "total": (
                        analysis.python_files_analyzed
                        + analysis.typescript_files_analyzed
                        + analysis.vue_files_analyzed
                    ),
                },
                "issues": {
                    "critical": analysis.critical_issues,
                    "high": analysis.high_issues,
                    "medium": analysis.medium_issues,
                    "low": analysis.low_issues,
                    "total": analysis.total_patterns,
                },
                "findings": {
                    "dto_mismatches": len(analysis.dto_mismatches),
                    "validation_duplications": len(analysis.validation_duplications),
                    "api_contract_mismatches": len(analysis.api_contract_mismatches),
                    "semantic_matches": len(analysis.pattern_matches),
                },
                "performance": {
                    "analysis_time_ms": analysis.analysis_time_ms,
                    "embeddings_generated": analysis.embeddings_generated,
                    "cache_hits": analysis.cache_hits,
                    "cache_misses": analysis.cache_misses,
                },
            },
        }
    )


@router.get("/cross-language/dto-mismatches")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dto_mismatches",
    error_code_prefix="CODEBASE",
)
async def get_dto_mismatches(
    source_id: str | None = Query(None, description="#12356: scope to the selected code source"),
) -> JSONResponse:
    """
    Get DTO/type mismatches between backend and frontend.

    Returns mismatches where Python models and TypeScript interfaces differ.
    Issue #12356: Reads only the selected source's cached analysis.
    """
    # Check cache (thread-safe, Issue #559 / #12356: per-source)
    analysis = await _get_cached_analysis(source_id)
    if analysis is None:
        return JSONResponse(
            {
                "status": "error",
                "message": "No analysis available. Run /cross-language/analyze first.",
            },
            status_code=400,
        )

    return JSONResponse(
        {
            "status": "success",
            "total": len(analysis.dto_mismatches),
            "mismatches": [m.to_dict() for m in analysis.dto_mismatches],
        }
    )


@router.get("/cross-language/validation-duplications")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_validation_duplications",
    error_code_prefix="CODEBASE",
)
async def get_validation_duplications(
    source_id: str | None = Query(None, description="#12356: scope to the selected code source"),
) -> JSONResponse:
    """
    Get duplicated validation logic across languages.

    Returns validation rules that exist in both Python and TypeScript.
    Issue #12356: Reads only the selected source's cached analysis.
    """
    # Check cache (thread-safe, Issue #559 / #12356: per-source)
    analysis = await _get_cached_analysis(source_id)
    if analysis is None:
        return JSONResponse(
            {
                "status": "error",
                "message": "No analysis available. Run /cross-language/analyze first.",
            },
            status_code=400,
        )

    return JSONResponse(
        {
            "status": "success",
            "total": len(analysis.validation_duplications),
            "duplications": [v.to_dict() for v in analysis.validation_duplications],
        }
    )


@router.get("/cross-language/api-mismatches")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_api_contract_mismatches",
    error_code_prefix="CODEBASE",
)
async def get_api_contract_mismatches(
    source_id: str | None = Query(None, description="#12356: scope to the selected code source"),
) -> JSONResponse:
    """
    Get API contract mismatches between backend and frontend.

    Returns endpoints that are:
    - Orphaned (backend has, frontend doesn't call)
    - Missing (frontend calls, backend doesn't have)

    Issue #12356: Reads only the selected source's cached analysis.
    """
    # Check cache (thread-safe, Issue #559 / #12356: per-source)
    analysis = await _get_cached_analysis(source_id)
    if analysis is None:
        return JSONResponse(
            {
                "status": "error",
                "message": "No analysis available. Run /cross-language/analyze first.",
            },
            status_code=400,
        )

    orphaned = [m for m in analysis.api_contract_mismatches if m.mismatch_type == "orphaned_endpoint"]
    missing = [m for m in analysis.api_contract_mismatches if m.mismatch_type == "missing_endpoint"]

    return JSONResponse(
        {
            "status": "success",
            "total": len(analysis.api_contract_mismatches),
            "orphaned_count": len(orphaned),
            "missing_count": len(missing),
            "orphaned": [m.to_dict() for m in orphaned],
            "missing": [m.to_dict() for m in missing],
        }
    )


@router.get("/cross-language/semantic-matches")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_semantic_matches",
    error_code_prefix="CODEBASE",
)
async def get_semantic_matches(
    min_similarity: float = 0.7,
    limit: int = 50,
    source_id: str | None = Query(None, description="#12356: scope to the selected code source"),
) -> JSONResponse:
    """
    Get semantically similar patterns across languages.

    Returns patterns in Python that have similar counterparts in TypeScript,
    detected using LLM embeddings and ChromaDB vector search.

    Args:
        min_similarity: Minimum similarity score (0.0-1.0, default: 0.7)
        limit: Maximum number of matches to return (default: 50)
        source_id: Scope to the selected code source (Issue #12356)
    """
    # Check cache (thread-safe, Issue #559 / #12356: per-source)
    analysis = await _get_cached_analysis(source_id)
    if analysis is None:
        return JSONResponse(
            {
                "status": "error",
                "message": "No analysis available. Run /cross-language/analyze first.",
            },
            status_code=400,
        )

    # Filter by similarity threshold
    filtered_matches = [m for m in analysis.pattern_matches if m.similarity_score >= min_similarity]

    # Sort by similarity (highest first)
    filtered_matches.sort(key=lambda x: x.similarity_score, reverse=True)

    # Limit results
    filtered_matches = filtered_matches[:limit]

    return JSONResponse(
        {
            "status": "success",
            "total": len(filtered_matches),
            "min_similarity": min_similarity,
            "matches": [m.to_dict() for m in filtered_matches],
        }
    )


@router.get("/cross-language/patterns")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_patterns_by_category",
    error_code_prefix="CODEBASE",
)
async def get_patterns_by_category(
    category: str | None = None,
    severity: str | None = None,
    limit: int = 100,
    source_id: str | None = Query(None, description="#12356: scope to the selected code source"),
) -> JSONResponse:
    """
    Get detected patterns filtered by category and/or severity.

    Args:
        category: Filter by category (api_contract, data_types, validation, etc.)
        severity: Filter by severity (critical, high, medium, low, info)
        limit: Maximum patterns to return (default: 100)
        source_id: Scope to the selected code source (Issue #12356)
    """
    # Check cache (thread-safe, Issue #559 / #12356: per-source)
    analysis = await _get_cached_analysis(source_id)
    if analysis is None:
        return JSONResponse(
            {
                "status": "error",
                "message": "No analysis available. Run /cross-language/analyze first.",
            },
            status_code=400,
        )

    patterns = analysis.patterns

    # Apply filters
    if category:
        patterns = [p for p in patterns if p.category.value == category]

    if severity:
        patterns = [p for p in patterns if p.severity.value == severity]

    # Limit results
    patterns = patterns[:limit]

    return JSONResponse(
        {
            "status": "success",
            "total": len(patterns),
            "filters": {
                "category": category,
                "severity": severity,
            },
            "patterns": [p.to_dict() for p in patterns],
        }
    )


@router.post("/cross-language/clear-cache")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_cross_language_cache",
    error_code_prefix="CODEBASE",
)
async def clear_cross_language_cache(
    source_id: str | None = Query(None, description="#12356: clear only this source's cache entry"),
) -> JSONResponse:
    """
    Clear the cross-language analysis cache.

    Call this after making code changes to get fresh results.
    Issue #12356: Clears only the requested source's entry so clearing one
    project's cache does not evict another project's cached analysis.
    """
    # Clear cache (thread-safe, Issue #559 / #12356: per-source)
    async with _analysis_cache_lock:
        _analysis_cache.pop(_cache_key(source_id), None)

    return JSONResponse(
        {
            "status": "success",
            "message": "Cross-language analysis cache cleared",
        }
    )
