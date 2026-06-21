# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
FastAPI router for Redis MCP Bridge.

Issue #2511: Provides /api/redis/mcp/tools listing and per-tool POST endpoints.
Integrates RBAC filtering and routes to the appropriate handler module.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.redis_mcp.data_access import (
    handle_redis_delete,
    handle_redis_get,
    handle_redis_hget,
    handle_redis_hgetall,
    handle_redis_hset,
    handle_redis_lpush,
    handle_redis_lrange,
    handle_redis_rpush,
    handle_redis_scan_keys,
    handle_redis_set,
    handle_redis_ttl,
    handle_redis_type,
    handle_redis_xadd,
    handle_redis_xrange,
    handle_redis_zrange,
)
from api.redis_mcp.ops_intelligence import (
    handle_redis_client_list,
    handle_redis_dbsize,
    handle_redis_memory_stats,
    handle_redis_server_info,
    handle_redis_slowlog,
    handle_redis_stream_health,
)
from api.redis_mcp.rbac import (
    ToolAccess,
    check_tool_permission,
    get_tool_access,
    validate_key_namespace,
)
from api.redis_mcp.tools import get_all_tools
from api.redis_mcp.vector_search import (
    handle_redis_hybrid_search,
    handle_redis_vector_create_index,
    handle_redis_vector_index_info,
    handle_redis_vector_search,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_management.types import DATABASE_MAPPING
from type_defs.common import Metadata

logger = get_logger(__name__)

# Valid database names for parameter validation (#2511)
_VALID_DATABASES = frozenset(DATABASE_MAPPING.keys())

router = APIRouter(
    tags=["redis_mcp", "mcp"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class RedisToolCallRequest(BaseModel):
    """Generic tool call request for dispatch endpoint."""

    tool_name: str = ""
    arguments: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool listing endpoint
# ---------------------------------------------------------------------------


@router.get("/mcp/tools")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_redis_mcp_tools",
    error_code_prefix="REDIS_MCP",
)
async def get_redis_mcp_tools(
    current_user: dict = Depends(get_current_user),
) -> List[dict]:
    """List all Redis MCP tools available to the current user."""
    is_admin = _is_admin(current_user)
    all_tools = get_all_tools()
    # Filter out tools blocked for this role
    visible = []
    for tool in all_tools:
        allowed, _ = check_tool_permission(tool.name, is_admin)
        if allowed:
            visible.append(tool.model_dump())
    return visible


# ---------------------------------------------------------------------------
# Unified dispatch endpoint
# ---------------------------------------------------------------------------


@router.post("/mcp/call")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="call_redis_mcp_tool",
    error_code_prefix="REDIS_MCP",
)
async def call_redis_mcp_tool(
    request: RedisToolCallRequest,
    current_user: dict = Depends(get_current_user),
) -> Metadata:
    """Dispatch a Redis MCP tool call with RBAC enforcement."""
    tool_name = request.tool_name
    args = request.arguments
    is_admin = _is_admin(current_user)

    # RBAC check
    allowed, error_msg = check_tool_permission(tool_name, is_admin)
    if not allowed:
        raise HTTPException(status_code=403, detail=error_msg)

    access = get_tool_access(tool_name, is_admin)

    # Approval gate for destructive admin ops (Issue #2622)
    # If the caller provides approved=true (after user confirmation), skip the gate.
    if access == ToolAccess.APPROVAL_REQUIRED and not args.get("approved"):
        return {
            "status": "approval_required",
            "tool": tool_name,
            "message": (
                f"Tool '{tool_name}' requires explicit approval. " "Confirm to proceed with this destructive operation."
            ),
            "arguments": args,
        }

    # Namespace validation for write tools — validate ALL keys (#2511)
    keys = _extract_keys(args)
    if keys and access in (ToolAccess.SCOPED_WRITE, ToolAccess.FULL_WRITE):
        for key in keys:
            valid, ns_error = validate_key_namespace(key, is_admin, access)
            if not valid:
                raise HTTPException(status_code=403, detail=ns_error)

    # Database parameter validation (#2511)
    db = args.get("database")
    if db and db not in _VALID_DATABASES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid database '{db}'. Valid: {sorted(_VALID_DATABASES)}",
        )

    # Route to handler
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"Unknown Redis MCP tool: {tool_name}")
    return await handler(args)


# ---------------------------------------------------------------------------
# Per-tool POST endpoints (for MCP registry endpoint pattern)
# ---------------------------------------------------------------------------


@router.post("/mcp/{tool_name}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="redis_mcp_tool_endpoint",
    error_code_prefix="REDIS_MCP",
)
async def redis_mcp_tool_endpoint(
    tool_name: str,
    request: RedisToolCallRequest,
    current_user: dict = Depends(get_current_user),
) -> Metadata:
    """Individual tool endpoint for MCP registry compatibility."""
    request.tool_name = tool_name
    return await call_redis_mcp_tool(request, current_user)


# ---------------------------------------------------------------------------
# Handler dispatch table
# ---------------------------------------------------------------------------


async def _wrap_data_get(args: dict) -> Metadata:
    return await handle_redis_get(key=args["key"], database=args.get("database", "main"))


async def _wrap_data_set(args: dict) -> Metadata:
    return await handle_redis_set(
        key=args["key"],
        value=args["value"],
        ttl=args.get("ttl"),
        database=args.get("database", "main"),
    )


async def _wrap_data_delete(args: dict) -> Metadata:
    return await handle_redis_delete(keys=args["keys"], database=args.get("database", "main"))


async def _wrap_data_hget(args: dict) -> Metadata:
    return await handle_redis_hget(
        key=args["key"],
        field=args["field"],
        database=args.get("database", "main"),
    )


async def _wrap_data_hgetall(args: dict) -> Metadata:
    return await handle_redis_hgetall(key=args["key"], database=args.get("database", "main"))


async def _wrap_data_hset(args: dict) -> Metadata:
    return await handle_redis_hset(
        key=args["key"],
        mapping=args["mapping"],
        database=args.get("database", "main"),
    )


async def _wrap_data_lrange(args: dict) -> Metadata:
    return await handle_redis_lrange(
        key=args["key"],
        start=args.get("start", 0),
        stop=args.get("stop", -1),
        database=args.get("database", "main"),
    )


async def _wrap_data_lpush(args: dict) -> Metadata:
    return await handle_redis_lpush(
        key=args["key"],
        values=args["values"],
        ttl=args.get("ttl"),
        database=args.get("database", "main"),
    )


async def _wrap_data_rpush(args: dict) -> Metadata:
    return await handle_redis_rpush(
        key=args["key"],
        values=args["values"],
        ttl=args.get("ttl"),
        database=args.get("database", "main"),
    )


async def _wrap_data_zrange(args: dict) -> Metadata:
    return await handle_redis_zrange(
        key=args["key"],
        start=args.get("start", 0),
        stop=args.get("stop", -1),
        withscores=args.get("withscores", False),
        database=args.get("database", "main"),
    )


async def _wrap_data_xrange(args: dict) -> Metadata:
    return await handle_redis_xrange(
        key=args["key"],
        start=args.get("start", "-"),
        end=args.get("end", "+"),
        count=args.get("count"),
        database=args.get("database", "main"),
    )


async def _wrap_data_xadd(args: dict) -> Metadata:
    return await handle_redis_xadd(
        key=args["key"],
        fields=args["fields"],
        maxlen=args.get("maxlen"),
        ttl=args.get("ttl"),
        database=args.get("database", "main"),
    )


async def _wrap_data_scan_keys(args: dict) -> Metadata:
    return await handle_redis_scan_keys(
        pattern=args.get("pattern", "*"),
        count=args.get("count", 100),
        database=args.get("database", "main"),
    )


async def _wrap_data_type(args: dict) -> Metadata:
    return await handle_redis_type(key=args["key"], database=args.get("database", "main"))


async def _wrap_data_ttl(args: dict) -> Metadata:
    return await handle_redis_ttl(key=args["key"], database=args.get("database", "main"))


async def _wrap_vector_create_index(args: dict) -> Metadata:
    return await handle_redis_vector_create_index(
        index_name=args.get("index_name", "idx:agent_memory"),
        prefix=args.get("prefix", "autobot:agent:memory:"),
        vector_field=args.get("vector_field", "embedding"),
        dimensions=args.get("dimensions", 1536),
        distance_metric=args.get("distance_metric", "COSINE"),
        extra_fields=args.get("extra_fields"),
        database=args.get("database", "memory"),
    )


async def _wrap_vector_search(args: dict) -> Metadata:
    return await handle_redis_vector_search(
        query_vector=args.get("query_vector"),
        query_text=args.get("query_text"),
        index_name=args.get("index_name", "idx:agent_memory"),
        top_k=args.get("top_k", 10),
        return_fields=args.get("return_fields"),
        database=args.get("database", "memory"),
    )


async def _wrap_hybrid_search(args: dict) -> Metadata:
    return await handle_redis_hybrid_search(
        query_vector=args.get("query_vector"),
        query_text=args.get("query_text"),
        filter_expression=args.get("filter_expression", ""),
        index_name=args.get("index_name", "idx:agent_memory"),
        top_k=args.get("top_k", 10),
        return_fields=args.get("return_fields"),
        database=args.get("database", "memory"),
    )


async def _wrap_vector_index_info(args: dict) -> Metadata:
    return await handle_redis_vector_index_info(
        index_name=args.get("index_name", "idx:agent_memory"),
        database=args.get("database", "memory"),
    )


async def _wrap_ops_server_info(args: dict) -> Metadata:
    return await handle_redis_server_info(
        section=args.get("section"),
        database=args.get("database", "main"),
    )


async def _wrap_ops_dbsize(args: dict) -> Metadata:
    return await handle_redis_dbsize(database=args.get("database", "main"))


async def _wrap_ops_memory_stats(args: dict) -> Metadata:
    return await handle_redis_memory_stats(database=args.get("database", "main"))


async def _wrap_ops_stream_health(args: dict) -> Metadata:
    return await handle_redis_stream_health(key=args["key"], database=args.get("database", "main"))


async def _wrap_ops_client_list(args: dict) -> Metadata:
    return await handle_redis_client_list(database=args.get("database", "main"))


async def _wrap_ops_slowlog(args: dict) -> Metadata:
    return await handle_redis_slowlog(
        count=args.get("count", 10),
        database=args.get("database", "main"),
    )


_TOOL_HANDLERS = {
    # Data Access
    "redis_get": _wrap_data_get,
    "redis_set": _wrap_data_set,
    "redis_delete": _wrap_data_delete,
    "redis_hget": _wrap_data_hget,
    "redis_hgetall": _wrap_data_hgetall,
    "redis_hset": _wrap_data_hset,
    "redis_lrange": _wrap_data_lrange,
    "redis_lpush": _wrap_data_lpush,
    "redis_rpush": _wrap_data_rpush,
    "redis_zrange": _wrap_data_zrange,
    "redis_xrange": _wrap_data_xrange,
    "redis_xadd": _wrap_data_xadd,
    "redis_scan_keys": _wrap_data_scan_keys,
    "redis_type": _wrap_data_type,
    "redis_ttl": _wrap_data_ttl,
    # Vector Search
    "redis_vector_create_index": _wrap_vector_create_index,
    "redis_vector_search": _wrap_vector_search,
    "redis_hybrid_search": _wrap_hybrid_search,
    "redis_vector_index_info": _wrap_vector_index_info,
    # Ops Intelligence
    "redis_server_info": _wrap_ops_server_info,
    "redis_dbsize": _wrap_ops_dbsize,
    "redis_memory_stats": _wrap_ops_memory_stats,
    "redis_stream_health": _wrap_ops_stream_health,
    "redis_client_list": _wrap_ops_client_list,
    "redis_slowlog": _wrap_ops_slowlog,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_admin(user: dict) -> bool:
    """Check if the user has admin role."""
    role = user.get("role", "user")
    return role in ("admin", "superadmin")


def _extract_keys(args: dict) -> list[str]:
    """Extract all keys from tool arguments for namespace validation."""
    if "key" in args:
        return [args["key"]]
    if "keys" in args and args["keys"]:
        return list(args["keys"])
    return []
