# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.code_intelligence.cross_language_patterns import (
    CrossLanguagePatternDetector,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache for analysis results
_analysis_cache: dict = {}
# Lock for thread-safe access to _analysis_cache (Issue #559)
_analysis_cache_lock = asyncio.Lock()


def _get_detector() -> CrossLanguagePatternDetector:
    """Get or create the pattern detector instance."""
    return CrossLanguagePatternDetector(
        use_llm=True,
        use_cache=True,
        embedding_model="nomic-embed-text",
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_cross_language_analysis",
    error_code_prefix="CODEBASE",
)
@router.post("/cross-language/analyze")
async def run_cross_language_analysis(
    use_llm: bool = True,
    use_cache: bool = True,
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

    Returns:
        Complete analysis results with all detected patterns
    """
    detector = CrossLanguagePatternDetector(
        use_llm=use_llm,
        use_cache=use_cache,
    )

    analysis = await detector.run_analysis()

    # Cache the result (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        _analysis_cache["latest"] = analysis

    return JSONResponse(
        {
            "status": "success",
            "analysis": analysis.to_dict(),
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cross_language_summary",
    error_code_prefix="CODEBASE",
)
@router.get("/cross-language/summary")
async def get_cross_language_summary() -> JSONResponse:
    """
    Get summary of latest cross-language analysis.

    Returns cached results if available, otherwise returns empty status.
    Use POST /cross-language/analyze to trigger a new analysis.
    """
    # Check cache first (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        if "latest" not in _analysis_cache:
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
        analysis = _analysis_cache["latest"]

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_dto_mismatches",
    error_code_prefix="CODEBASE",
)
@router.get("/cross-language/dto-mismatches")
async def get_dto_mismatches() -> JSONResponse:
    """
    Get DTO/type mismatches between backend and frontend.

    Returns mismatches where Python models and TypeScript interfaces differ.
    """
    # Check cache (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        if "latest" not in _analysis_cache:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "No analysis available. Run /cross-language/analyze first.",
                },
                status_code=400,
            )
        analysis = _analysis_cache["latest"]

    return JSONResponse(
        {
            "status": "success",
            "total": len(analysis.dto_mismatches),
            "mismatches": [m.to_dict() for m in analysis.dto_mismatches],
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_validation_duplications",
    error_code_prefix="CODEBASE",
)
@router.get("/cross-language/validation-duplications")
async def get_validation_duplications() -> JSONResponse:
    """
    Get duplicated validation logic across languages.

    Returns validation rules that exist in both Python and TypeScript.
    """
    # Check cache (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        if "latest" not in _analysis_cache:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "No analysis available. Run /cross-language/analyze first.",
                },
                status_code=400,
            )
        analysis = _analysis_cache["latest"]

    return JSONResponse(
        {
            "status": "success",
            "total": len(analysis.validation_duplications),
            "duplications": [v.to_dict() for v in analysis.validation_duplications],
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_api_contract_mismatches",
    error_code_prefix="CODEBASE",
)
@router.get("/cross-language/api-mismatches")
async def get_api_contract_mismatches() -> JSONResponse:
    """
    Get API contract mismatches between backend and frontend.

    Returns endpoints that are:
    - Orphaned (backend has, frontend doesn't call)
    - Missing (frontend calls, backend doesn't have)
    """
    # Check cache (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        if "latest" not in _analysis_cache:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "No analysis available. Run /cross-language/analyze first.",
                },
                status_code=400,
            )
        analysis = _analysis_cache["latest"]

    orphaned = [
        m
        for m in analysis.api_contract_mismatches
        if m.mismatch_type == "orphaned_endpoint"
    ]
    missing = [
        m
        for m in analysis.api_contract_mismatches
        if m.mismatch_type == "missing_endpoint"
    ]

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_semantic_matches",
    error_code_prefix="CODEBASE",
)
@router.get("/cross-language/semantic-matches")
async def get_semantic_matches(
    min_similarity: float = 0.7,
    limit: int = 50,
) -> JSONResponse:
    """
    Get semantically similar patterns across languages.

    Returns patterns in Python that have similar counterparts in TypeScript,
    detected using LLM embeddings and ChromaDB vector search.

    Args:
        min_similarity: Minimum similarity score (0.0-1.0, default: 0.7)
        limit: Maximum number of matches to return (default: 50)
    """
    # Check cache (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        if "latest" not in _analysis_cache:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "No analysis available. Run /cross-language/analyze first.",
                },
                status_code=400,
            )
        analysis = _analysis_cache["latest"]

    # Filter by similarity threshold
    filtered_matches = [
        m for m in analysis.pattern_matches if m.similarity_score >= min_similarity
    ]

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_patterns_by_category",
    error_code_prefix="CODEBASE",
)
@router.get("/cross-language/patterns")
async def get_patterns_by_category(
    category: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
) -> JSONResponse:
    """
    Get detected patterns filtered by category and/or severity.

    Args:
        category: Filter by category (api_contract, data_types, validation, etc.)
        severity: Filter by severity (critical, high, medium, low, info)
        limit: Maximum patterns to return (default: 100)
    """
    # Check cache (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        if "latest" not in _analysis_cache:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "No analysis available. Run /cross-language/analyze first.",
                },
                status_code=400,
            )
        analysis = _analysis_cache["latest"]

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_cross_language_cache",
    error_code_prefix="CODEBASE",
)
@router.post("/cross-language/clear-cache")
async def clear_cross_language_cache() -> JSONResponse:
    """
    Clear the cross-language analysis cache.

    Call this after making code changes to get fresh results.
    """
    global _analysis_cache

    # Clear cache (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        _analysis_cache = {}

    return JSONResponse(
        {
            "status": "success",
            "message": "Cross-language analysis cache cleared",
        }
    )
