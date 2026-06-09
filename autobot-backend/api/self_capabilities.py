# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Self-Capabilities Router

Exposes GET /api/self/capabilities — a live, dynamically derived view of all
registered FastAPI routes.  The endpoint crawls the app's OpenAPI schema on
first request (and on every schema change), categorises routes by their
OpenAPI tag(s) and HTTP method, caches the result with a configurable TTL,
and returns the payload in a format that LLM agents can consume directly.

Issue #3295: replace the hardcoded endpoint list in llm_self_awareness.py.
"""

import asyncio
import hashlib
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.openapi.utils import get_openapi

from api.schemas_agent import SelfCapabilitiesResponse
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.ttl_constants import TTL_5_MINUTES

logger = get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# In-process cache (singleton per worker process — acceptable for LLM hints)
# ---------------------------------------------------------------------------
_CACHE_TTL: int = TTL_5_MINUTES  # seconds

_cache: Dict[str, Any] | None = None
_cache_ts: float = 0.0
_cache_schema_hash: str = ""
_cache_lock = asyncio.Lock()


def _schema_hash(app_routes_count: int) -> str:
    """Cheap fingerprint: route count is enough to detect new registrations."""
    # usedforsecurity=False: fingerprint only, not a security hash  # noqa: S324
    return hashlib.md5(str(app_routes_count).encode(), usedforsecurity=False).hexdigest()  # noqa: S324


def _cache_is_valid(current_hash: str) -> bool:
    """Return True if the cached result is still fresh and routes are unchanged."""
    if _cache is None:
        return False
    if time.monotonic() - _cache_ts >= _CACHE_TTL:
        return False
    return _cache_schema_hash == current_hash


# ---------------------------------------------------------------------------
# Core discovery logic
# ---------------------------------------------------------------------------


def _openapi_paths(app: Any) -> Dict[str, Any]:
    """Extract OpenAPI paths dict from the live app, generating schema if needed."""
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description or "",
        routes=app.routes,
    )
    return schema.get("paths", {})


def _operation_type(method: str) -> str:
    """Map HTTP method to a human-readable operation type."""
    mapping = {
        "get": "query",
        "post": "create",
        "put": "update",
        "patch": "update",
        "delete": "delete",
    }
    return mapping.get(method.lower(), method.lower())


def _build_endpoint_entry(path: str, method: str, op: Dict[str, Any]) -> Dict[str, Any]:
    """Build a single endpoint descriptor dict from an OpenAPI operation object."""
    return {
        "path": path,
        "method": method.upper(),
        "operation_type": _operation_type(method),
        "summary": op.get("summary", ""),
        "description": op.get("description", ""),
        "tags": op.get("tags", ["untagged"]),
        "operation_id": op.get("operationId", ""),
    }


def _collect_endpoints(paths: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten OpenAPI paths into a list of endpoint descriptors."""
    _http_methods = {"get", "post", "put", "patch", "delete", "head", "options"}
    endpoints: List[Dict[str, Any]] = []
    for path, path_item in paths.items():
        for method, op in path_item.items():
            if method.lower() in _http_methods and isinstance(op, dict):
                endpoints.append(_build_endpoint_entry(path, method, op))
    return endpoints


def _categorise_by_tag(endpoints: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Group endpoint paths by their first OpenAPI tag."""
    by_tag: Dict[str, List[str]] = {}
    for ep in endpoints:
        tag = ep["tags"][0] if ep["tags"] else "untagged"
        by_tag.setdefault(tag, [])
        path_with_method = f"{ep['method']} {ep['path']}"
        if path_with_method not in by_tag[tag]:
            by_tag[tag].append(path_with_method)
    return by_tag


def _categorise_by_operation(endpoints: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Group endpoint paths by operation type (query/create/update/delete)."""
    by_op: Dict[str, List[str]] = {}
    for ep in endpoints:
        op_type = ep["operation_type"]
        by_op.setdefault(op_type, [])
        if ep["path"] not in by_op[op_type]:
            by_op[op_type].append(ep["path"])
    return by_op


def _paths_only(endpoints: List[Dict[str, Any]]) -> List[str]:
    """Extract unique path strings from endpoint list, preserving order."""
    seen: set = set()
    result: List[str] = []
    for ep in endpoints:
        if ep["path"] not in seen:
            seen.add(ep["path"])
            result.append(ep["path"])
    return result


def _build_payload(endpoints: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Assemble the full /api/self/capabilities response payload."""
    return {
        "total_endpoints": len(endpoints),
        "unique_paths": len(_paths_only(endpoints)),
        "endpoints": endpoints,
        "by_tag": _categorise_by_tag(endpoints),
        "by_operation_type": _categorise_by_operation(endpoints),
        "api_paths": _paths_only(endpoints),
    }


# ---------------------------------------------------------------------------
# Public discovery function (also used by llm_self_awareness.py)
# ---------------------------------------------------------------------------


async def discover_endpoints(app: Any) -> Dict[str, Any]:
    """
    Return live endpoint discovery data for the given FastAPI app.

    Results are cached for TTL_5_MINUTES and invalidated automatically when
    the number of registered routes changes (e.g., after optional routers load).

    Args:
        app: The FastAPI application instance.

    Returns:
        Dict containing endpoint list, tag groupings, and operation-type groupings.
    """
    global _cache, _cache_ts, _cache_schema_hash

    current_hash = _schema_hash(len(app.routes))

    # Fast path — no lock needed for read
    if _cache_is_valid(current_hash):
        return _cache  # type: ignore[return-value]

    async with _cache_lock:
        # Re-check after acquiring lock (another coroutine may have refreshed)
        if _cache_is_valid(current_hash):
            return _cache  # type: ignore[return-value]

        logger.info("endpoint-discovery: refreshing cache (routes=%d)", len(app.routes))
        paths = await asyncio.to_thread(_openapi_paths, app)
        endpoints = _collect_endpoints(paths)
        payload = _build_payload(endpoints)

        _cache = payload
        _cache_ts = time.monotonic()
        _cache_schema_hash = current_hash

        logger.info(
            "endpoint-discovery: cached %d endpoints across %d paths",
            len(endpoints),
            payload["unique_paths"],
        )
        return payload


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/capabilities",
    summary="Dynamic endpoint capability discovery",
    description=(
        "Returns a dynamically derived list of all registered API endpoints, "
        "grouped by OpenAPI tag and operation type.  The result is derived from "
        "the live FastAPI OpenAPI schema (not hardcoded) and is cached with a "
        f"{TTL_5_MINUTES // 60}-minute TTL that resets on route changes."
    ),
    tags=["self", "capabilities"],
    response_model=SelfCapabilitiesResponse,
)
@with_error_handling(category=ErrorCategory.SYSTEM)
async def get_capabilities(request: Request) -> Dict[str, Any]:
    """Live endpoint discovery for LLM self-awareness (Issue #3295)."""
    return await discover_endpoints(request.app)
