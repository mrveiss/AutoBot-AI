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

Issue #22274: this crawl is THE route registry. ``api/developer.py`` derives its
endpoint view from ``discover_endpoints``; ``api/registry.py`` ``APIRegistry`` is
the hand-written router-level catalogue (prefix/tags/auth per mounted module), a
different granularity that the loader tests read, kept as router metadata rather
than a second route list. Every route record names the service that serves it
(``serving_service``); ``route_records`` is the accessor the self-model ingests.
"""

import asyncio
import hashlib
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.utils import get_openapi

from api.schemas_agent import SelfCapabilitiesResponse
from api.user_management.dependencies import get_current_user
from autobot_shared.api_routing.router_routes import effective_route_count
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.service_registry_core import SERVICE_DEFINITIONS
from constants.ttl_constants import TTL_5_MINUTES

logger = get_logger(__name__)

# #16375: every route here was reachable anonymously. Gated at the ROUTER so a
# route added later inherits it. Authentication only:
# a read-only description of the API's own capabilities.
router = APIRouter(dependencies=[Depends(get_current_user)])

# The service whose FastAPI app this process crawls (#22274). Named through the one
# service table, so a rename there fails here at import rather than drifting.
SERVING_SERVICE: str = SERVICE_DEFINITIONS["backend"].name

# ---------------------------------------------------------------------------
# In-process cache (singleton per worker process — acceptable for LLM hints)
# ---------------------------------------------------------------------------
_CACHE_TTL: int = TTL_5_MINUTES  # seconds

_cache: Dict[str, Any] | None = None
_cache_ts: float = 0.0
_cache_schema_hash: str = ""
_cache_lock = asyncio.Lock()


def _schema_hash(app: Any) -> str:
    """Cheap fingerprint of the served route table.

    Counted through ``effective_route_count`` rather than ``len(app.routes)``
    (#15093). Under ``fastapi>=0.139`` — the declared floor — ``app.routes``
    holds one deferred entry per ``include_router`` **call**, so its length moves
    when a router is mounted and not when an endpoint is added inside one that
    is already mounted. That is the common case, and it left the cache serving a
    stale table for a full TTL while the docstring promised the opposite. The
    traversal is a walk over route objects, not schema generation, so this stays
    cheap enough to run on the fast path.
    """
    # usedforsecurity=False: fingerprint only, not a security hash  # noqa: S324
    return hashlib.md5(str(effective_route_count(app)).encode(), usedforsecurity=False).hexdigest()  # noqa: S324


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
        "serving_service": SERVING_SERVICE,
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

    Results are cached for TTL_5_MINUTES and invalidated automatically when the
    number of served routes changes — counted through the mount-aware traversal,
    so an endpoint added inside an already-mounted router busts the cache too
    (#15093).

    Args:
        app: The FastAPI application instance.

    Returns:
        Dict containing endpoint list, tag groupings, and operation-type groupings.
    """
    global _cache, _cache_ts, _cache_schema_hash

    current_hash = _schema_hash(app)

    # Fast path — no lock needed for read
    if _cache_is_valid(current_hash):
        return _cache  # type: ignore[return-value]

    async with _cache_lock:
        # Re-check after acquiring lock (another coroutine may have refreshed)
        if _cache_is_valid(current_hash):
            return _cache  # type: ignore[return-value]

        logger.info("endpoint-discovery: refreshing cache (routes=%d)", effective_route_count(app))
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


def _route_record(ep: Dict[str, Any]) -> Dict[str, Any]:
    """One endpoint descriptor as a plain self-model record."""
    return {
        "kind": "route",
        "name": f"{ep['method']} {ep['path']}",
        "serving_service": ep["serving_service"],
        "fields": {k: ep[k] for k in ("path", "method", "operation_type", "summary", "tags", "operation_id")},
    }


async def route_records(app: Any) -> List[Dict[str, Any]]:
    """The route catalogue as plain records (kind, stable name, serving service, fields) (#22274)."""
    payload = await discover_endpoints(app)
    return [_route_record(ep) for ep in payload["endpoints"]]


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
        f"{TTL_5_MINUTES // 60}-minute TTL that resets when the served route table changes."
    ),
    tags=["self", "capabilities"],
    response_model=SelfCapabilitiesResponse,
)
@with_error_handling(category=ErrorCategory.SYSTEM)
async def get_capabilities(request: Request) -> Dict[str, Any]:
    """Live endpoint discovery for LLM self-awareness (Issue #3295)."""
    return await discover_endpoints(request.app)
