# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
from typing import Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from ..api_endpoint_scanner import APIEndpointChecker
from ..models import APIEndpointAnalysis

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache for analysis results (simple in-memory cache)
_analysis_cache: Dict[str, APIEndpointAnalysis] = {}
# Lock for thread-safe access to _analysis_cache (Issue #559)
_analysis_cache_lock = asyncio.Lock()


def _get_checker() -> APIEndpointChecker:
    """Get or create the API endpoint checker instance."""
    return APIEndpointChecker()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_api_endpoints",
    error_code_prefix="CODEBASE",
)
@router.get("/api-endpoints")
async def get_api_endpoints() -> JSONResponse:
    """
    Get all backend API endpoints.

    Returns list of all FastAPI route definitions found in the backend.
    """
    checker = _get_checker()
    endpoints = checker.get_backend_endpoints()

    return JSONResponse(
        {
            "status": "success",
            "total": len(endpoints),
            "endpoints": [ep.model_dump() for ep in endpoints],
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_frontend_api_calls",
    error_code_prefix="CODEBASE",
)
@router.get("/api-calls")
async def get_frontend_api_calls() -> JSONResponse:
    """
    Get all frontend API calls.

    Returns list of all API calls found in frontend TypeScript/Vue files.
    """
    checker = _get_checker()
    calls = checker.get_frontend_calls()

    return JSONResponse(
        {
            "status": "success",
            "total": len(calls),
            "api_calls": [call.model_dump() for call in calls],
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_endpoint_coverage",
    error_code_prefix="CODEBASE",
)
@router.get("/endpoint-coverage")
async def get_endpoint_coverage() -> JSONResponse:
    """
    Get full API endpoint coverage analysis.

    Returns comprehensive analysis including:
    - Total backend endpoints
    - Total frontend calls
    - Used endpoints (with call counts)
    - Orphaned endpoints (unused)
    - Missing endpoints (called but not defined)
    - Coverage percentage
    """
    checker = _get_checker()
    analysis = checker.run_full_analysis()

    # Cache the result (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        _analysis_cache["latest"] = analysis

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_endpoint_analysis_full",
    error_code_prefix="CODEBASE",
)
@router.get("/endpoint-analysis")
async def get_endpoint_analysis_full() -> JSONResponse:
    """
    Get complete API endpoint analysis with all details.

    Returns full analysis including all endpoints, calls, and mismatches.
    Use /endpoint-coverage for a summary only.
    """
    checker = _get_checker()
    analysis = checker.run_full_analysis()

    # Cache the result (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        _analysis_cache["latest"] = analysis

    return JSONResponse(
        {
            "status": "success",
            "analysis": analysis.model_dump(),
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_orphaned_endpoints",
    error_code_prefix="CODEBASE",
)
@router.get("/orphaned-endpoints")
async def get_orphaned_endpoints() -> JSONResponse:
    """
    Get orphaned endpoints (defined but never called).

    These are backend endpoints that have no matching frontend calls.
    They may be unused code that can be removed.
    """
    # Check cache first (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        if "latest" in _analysis_cache:
            analysis = _analysis_cache["latest"]
        else:
            checker = _get_checker()
            analysis = checker.run_full_analysis()
            _analysis_cache["latest"] = analysis

    return JSONResponse(
        {
            "status": "success",
            "total": len(analysis.orphaned),
            "orphaned_endpoints": [ep.model_dump() for ep in analysis.orphaned],
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_missing_endpoints",
    error_code_prefix="CODEBASE",
)
@router.get("/missing-endpoints")
async def get_missing_endpoints() -> JSONResponse:
    """
    Get missing endpoints (called but not defined).

    These are frontend API calls that have no matching backend endpoint.
    They may indicate bugs or deprecated endpoint usage.
    """
    # Check cache first (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        if "latest" in _analysis_cache:
            analysis = _analysis_cache["latest"]
        else:
            checker = _get_checker()
            analysis = checker.run_full_analysis()
            _analysis_cache["latest"] = analysis

    return JSONResponse(
        {
            "status": "success",
            "total": len(analysis.missing),
            "missing_endpoints": [ep.model_dump() for ep in analysis.missing],
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_used_endpoints",
    error_code_prefix="CODEBASE",
)
@router.get("/used-endpoints")
async def get_used_endpoints() -> JSONResponse:
    """
    Get actively used endpoints with their call counts.

    Returns endpoints that are both defined in backend and called from frontend.
    """
    # Check cache first (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        if "latest" in _analysis_cache:
            analysis = _analysis_cache["latest"]
        else:
            checker = _get_checker()
            analysis = checker.run_full_analysis()
            _analysis_cache["latest"] = analysis

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="refresh_endpoint_cache",
    error_code_prefix="CODEBASE",
)
@router.post("/refresh-endpoint-cache")
async def refresh_endpoint_cache() -> JSONResponse:
    """
    Force refresh the endpoint analysis cache.

    Call this after making code changes to get updated results.
    """
    global _analysis_cache

    checker = _get_checker()
    analysis = checker.run_full_analysis()

    # Update cache (thread-safe, Issue #559)
    async with _analysis_cache_lock:
        _analysis_cache = {}
        _analysis_cache["latest"] = analysis

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
