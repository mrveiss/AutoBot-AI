# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
API Endpoint Checker endpoints for codebase analytics (Issue #527)

Provides endpoints to:
- List all backend API endpoints
- List all frontend API calls
- Get endpoint coverage analysis
- Find orphaned endpoints (unused)
- Find missing endpoints (called but not defined)
"""

import asyncio
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

from ..api_endpoint_scanner import APIEndpointChecker
from ..models import APIEndpointAnalysis
from .shared import resolve_scan_root

logger = get_logger(__name__)

router = APIRouter()

# Cache for analysis results (simple in-memory cache).
# Issue #12330: Keyed by source_id (or "default") to prevent cross-project
# leakage -- a single global "latest" entry returned one project's endpoint
# coverage for every other selected source.
_analysis_cache: Dict[str, APIEndpointAnalysis] = {}
# Lock for thread-safe access to _analysis_cache (Issue #559)
_analysis_cache_lock = asyncio.Lock()


def _cache_key(source_id: str | None) -> str:
    """Cache key for a source. Issue #12330: scope per project, not global."""
    return source_id or "default"


def _get_checker(project_root: Path | None = None) -> APIEndpointChecker:
    """Get or create the API endpoint checker instance.

    Issue #12330: Bind the checker to the requested source's root so it scans
    the selected project rather than AutoBot's own root.
    """
    return APIEndpointChecker(project_root=project_root)


async def _get_or_run_analysis(source_id: str | None) -> APIEndpointAnalysis:
    """Return cached analysis for a source, or run it scoped to that source.

    Issue #12330: Both the cache lookup and a cache-miss analysis are scoped to
    the resolved source root so no two projects share results.
    """
    key = _cache_key(source_id)
    async with _analysis_cache_lock:
        cached = _analysis_cache.get(key)
    if cached is not None:
        return cached

    root = await resolve_scan_root(source_id)
    checker = _get_checker(root)
    analysis = await asyncio.to_thread(checker.run_full_analysis)

    async with _analysis_cache_lock:
        _analysis_cache[key] = analysis
    return analysis


@router.get("/api-endpoints")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_api_endpoints",
    error_code_prefix="CODEBASE",
)
async def get_api_endpoints(
    source_id: str | None = Query(None, description="#12330: scope to the selected code source"),
) -> JSONResponse:
    """
    Get all backend API endpoints.

    Returns list of all FastAPI route definitions found in the backend.
    Issue #12330: Scoped to the selected source's clone path.
    """
    root = await resolve_scan_root(source_id)
    checker = _get_checker(root)
    endpoints = await asyncio.to_thread(checker.get_backend_endpoints)

    return JSONResponse(
        {
            "status": "success",
            "total": len(endpoints),
            "endpoints": [ep.model_dump() for ep in endpoints],
        }
    )


@router.get("/api-calls")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_frontend_api_calls",
    error_code_prefix="CODEBASE",
)
async def get_frontend_api_calls(
    source_id: str | None = Query(None, description="#12330: scope to the selected code source"),
) -> JSONResponse:
    """
    Get all frontend API calls.

    Returns list of all API calls found in frontend TypeScript/Vue files.
    Issue #12330: Scoped to the selected source's clone path.
    """
    root = await resolve_scan_root(source_id)
    checker = _get_checker(root)
    calls = await asyncio.to_thread(checker.get_frontend_calls)

    return JSONResponse(
        {
            "status": "success",
            "total": len(calls),
            "api_calls": [call.model_dump() for call in calls],
        }
    )


@router.get("/endpoint-coverage")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_endpoint_coverage",
    error_code_prefix="CODEBASE",
)
async def get_endpoint_coverage(
    source_id: str | None = Query(None, description="#12330: scope coverage to the selected code source"),
) -> JSONResponse:
    """
    Get full API endpoint coverage analysis.

    Returns comprehensive analysis including:
    - Total backend endpoints
    - Total frontend calls
    - Used endpoints (with call counts)
    - Orphaned endpoints (unused)
    - Missing endpoints (called but not defined)
    - Coverage percentage

    Issue #12330: Analysis is scoped to the selected source's clone path and
    cached per-source so one project's coverage never leaks into another's.
    """
    analysis = await _get_or_run_analysis(source_id)

    return JSONResponse(
        {
            "status": "success",
            "summary": {
                "backend_endpoints": analysis.backend_endpoints,
                "frontend_calls": analysis.frontend_calls,
                "used_endpoints": analysis.used_endpoints,
                "orphaned_endpoints": analysis.orphaned_endpoints,
                "missing_endpoints": analysis.missing_endpoints,
                "coverage_percentage": analysis.coverage_percentage,
            },
            "scan_timestamp": analysis.scan_timestamp,
        }
    )


@router.get("/endpoint-analysis")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_endpoint_analysis_full",
    error_code_prefix="CODEBASE",
)
async def get_endpoint_analysis_full(
    source_id: str | None = Query(None, description="#12330: scope analysis to the selected code source"),
) -> JSONResponse:
    """
    Get complete API endpoint analysis with all details.

    Returns full analysis including all endpoints, calls, and mismatches.
    Use /endpoint-coverage for a summary only.
    Issue #12330: Scoped and cached per source.
    """
    analysis = await _get_or_run_analysis(source_id)

    return JSONResponse(
        {
            "status": "success",
            "analysis": analysis.model_dump(),
        }
    )


@router.get("/orphaned-endpoints")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_orphaned_endpoints",
    error_code_prefix="CODEBASE",
)
async def get_orphaned_endpoints(
    source_id: str | None = Query(None, description="#12330: scope to the selected code source"),
) -> JSONResponse:
    """
    Get orphaned endpoints (defined but never called).

    These are backend endpoints that have no matching frontend calls.
    They may be unused code that can be removed.
    Issue #12330: Scoped and cached per source.
    """
    analysis = await _get_or_run_analysis(source_id)

    return JSONResponse(
        {
            "status": "success",
            "total": len(analysis.orphaned),
            "orphaned_endpoints": [ep.model_dump() for ep in analysis.orphaned],
        }
    )


@router.get("/missing-endpoints")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_missing_endpoints",
    error_code_prefix="CODEBASE",
)
async def get_missing_endpoints(
    source_id: str | None = Query(None, description="#12330: scope to the selected code source"),
) -> JSONResponse:
    """
    Get missing endpoints (called but not defined).

    These are frontend API calls that have no matching backend endpoint.
    They may indicate bugs or deprecated endpoint usage.
    Issue #12330: Scoped and cached per source.
    """
    analysis = await _get_or_run_analysis(source_id)

    return JSONResponse(
        {
            "status": "success",
            "total": len(analysis.missing),
            "missing_endpoints": [ep.model_dump() for ep in analysis.missing],
        }
    )


@router.get("/used-endpoints")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_used_endpoints",
    error_code_prefix="CODEBASE",
)
async def get_used_endpoints(
    source_id: str | None = Query(None, description="#12330: scope to the selected code source"),
) -> JSONResponse:
    """
    Get actively used endpoints with their call counts.

    Returns endpoints that are both defined in backend and called from frontend.
    Issue #12330: Scoped and cached per source.
    """
    analysis = await _get_or_run_analysis(source_id)

    # Sort by call count (most used first)
    sorted_used = sorted(
        analysis.used,
        key=lambda x: x.call_count,
        reverse=True,
    )

    return JSONResponse(
        {
            "status": "success",
            "total": len(sorted_used),
            "used_endpoints": [
                {
                    "endpoint": u.endpoint.model_dump(),
                    "call_count": u.call_count,
                    "callers": [c.model_dump() for c in u.callers[:5]],  # Limit callers
                }
                for u in sorted_used
            ],
        }
    )


@router.post("/refresh-endpoint-cache")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="refresh_endpoint_cache",
    error_code_prefix="CODEBASE",
)
async def refresh_endpoint_cache(
    source_id: str | None = Query(None, description="#12330: refresh the selected source's cache entry"),
) -> JSONResponse:
    """
    Force refresh the endpoint analysis cache for a source.

    Call this after making code changes to get updated results.
    Issue #12330: Rebuilds only the requested source's entry, scoped to that
    source's clone path, so refreshing one project does not evict or overwrite
    another project's cached analysis.
    """
    root = await resolve_scan_root(source_id)
    checker = _get_checker(root)
    analysis = await asyncio.to_thread(checker.run_full_analysis)

    # Update cache (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        _analysis_cache[_cache_key(source_id)] = analysis

    return JSONResponse(
        {
            "status": "success",
            "message": "Endpoint cache refreshed",
            "summary": {
                "backend_endpoints": analysis.backend_endpoints,
                "frontend_calls": analysis.frontend_calls,
                "coverage_percentage": analysis.coverage_percentage,
            },
        }
    )
