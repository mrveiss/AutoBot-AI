# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MCP Registry API - Centralized management for all AutoBot MCP tools
Provides unified access to all MCP bridges for frontend management

This registry aggregates MCP tools from all bridges:
- knowledge_mcp.py - Knowledge base operations (LlamaIndex, Redis vectors)
- vnc_mcp.py - VNC observation and browser context
- sequential_thinking_mcp.py - Dynamic problem-solving framework
- structured_thinking_mcp.py - 5-stage cognitive framework
- filesystem_mcp.py - Secure file and directory operations

Architecture:
-----------
Frontend MCP Manager
       ↓
mcp_registry.py (This module - aggregates all MCP tools with caching)
       ↓
┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│ knowledge_mcp│   vnc_mcp    │seq_thinking  │struct_thinking│ filesystem_mcp│
└──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘

Key Features:
- List all available MCP tools across all bridges
- In-memory caching with configurable TTL (Performance optimization - Issue #50)
- Get tool schemas and documentation
- Health checks for each MCP bridge
- Usage statistics and monitoring
- Cache invalidation endpoints
"""

import importlib
import importlib.metadata
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request

from api.system_health import ComponentHealth, register_health_probe
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config
from constants.network_constants import NetworkConstants
from services.mcp_bridge_manifest import MCPBridgeManifest
from type_defs.common import Metadata

from .schemas_code import (
    MCPBridgeManifestSchema,
    MCPBridgeToggleResponse,
    MCPRegistryBridgesResponse,
    MCPRegistryCacheInvalidateResponse,
    MCPRegistryCacheStatsResponse,
    MCPRegistryInfoResponse,
    MCPRegistryStatsResponse,
    MCPRegistryToolDetailResponse,
    MCPRegistryToolsResponse,
)

logger = get_logger(__name__)
router = APIRouter(
    prefix="",
    tags=["mcp", "registry"],
    dependencies=[Depends(check_admin_permission)],
)


# ============================================================================
# Cache Configuration (Issue #50 - MCP Registry Caching Optimization)
# ============================================================================

# Load cache configuration from environment
CACHE_ENABLED = bool(config.mcp_registry_cache_enabled)
CACHE_TTL_SECONDS = int(config.mcp_registry_cache_ttl or "300")

logger.info("MCP Registry Cache: enabled=%s, TTL=%ss", CACHE_ENABLED, CACHE_TTL_SECONDS)


class MCPToolCache:
    """
    In-memory cache for MCP Registry responses (Issue #50 optimization)

    Features:
    - Configurable TTL (default: 60 seconds)
    - Automatic cache expiration
    - Cache hit/miss logging
    - Manual invalidation support
    """

    def __init__(self, ttl_seconds: int = 60):
        """Initialize MCP registry cache with configurable TTL."""
        self.ttl = timedelta(seconds=ttl_seconds)
        self._tools_cache: Metadata | None = None
        self._tools_updated: datetime | None = None
        self._bridges_cache: Metadata | None = None
        self._bridges_updated: datetime | None = None
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "invalidations": 0,
        }

    def get_tools(self) -> Metadata | None:
        """Get cached tools if still valid"""
        if not CACHE_ENABLED:
            return None

        if self._tools_cache is None or self._tools_updated is None:
            self._stats["cache_misses"] += 1
            return None

        age = datetime.now(tz=timezone.utc) - self._tools_updated
        if age > self.ttl:
            logger.debug("MCP tools cache expired (age: %.1fs)", age.total_seconds())
            self._stats["cache_misses"] += 1
            return None

        logger.debug("MCP tools cache hit (age: %.1fs)", age.total_seconds())
        self._stats["cache_hits"] += 1
        return self._tools_cache

    def set_tools(self, data: Metadata) -> None:
        """Update tools cache"""
        if not CACHE_ENABLED:
            return

        self._tools_cache = data
        self._tools_updated = datetime.now(tz=timezone.utc)
        logger.info("MCP tools cache updated (TTL: %ss)", self.ttl.seconds)

    def get_bridges(self) -> Metadata | None:
        """Get cached bridges if still valid"""
        if not CACHE_ENABLED:
            return None

        if self._bridges_cache is None or self._bridges_updated is None:
            self._stats["cache_misses"] += 1
            return None

        age = datetime.now(tz=timezone.utc) - self._bridges_updated
        if age > self.ttl:
            logger.debug("MCP bridges cache expired (age: %.1fs)", age.total_seconds())
            self._stats["cache_misses"] += 1
            return None

        logger.debug("MCP bridges cache hit (age: %.1fs)", age.total_seconds())
        self._stats["cache_hits"] += 1
        return self._bridges_cache

    def set_bridges(self, data: Metadata) -> None:
        """Update bridges cache"""
        if not CACHE_ENABLED:
            return

        self._bridges_cache = data
        self._bridges_updated = datetime.now(tz=timezone.utc)
        logger.info("MCP bridges cache updated (TTL: %ss)", self.ttl.seconds)

    def invalidate_all(self) -> None:
        """Invalidate all caches"""
        self._tools_cache = None
        self._tools_updated = None
        self._bridges_cache = None
        self._bridges_updated = None
        self._stats["invalidations"] += 1
        logger.info("MCP Registry cache invalidated")

    def get_stats(self) -> Metadata:
        """Get cache statistics"""
        total_requests = self._stats["cache_hits"] + self._stats["cache_misses"]
        hit_rate = (self._stats["cache_hits"] / total_requests * 100) if total_requests > 0 else 0

        return {
            "enabled": CACHE_ENABLED,
            "ttl_seconds": self.ttl.seconds,
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "hit_rate_percent": round(hit_rate, 2),
            "invalidations": self._stats["invalidations"],
            "tools_cached": self._tools_cache is not None,
            "tools_cache_age_seconds": (
                round((datetime.now(tz=timezone.utc) - self._tools_updated).total_seconds(), 1)
                if self._tools_updated
                else None
            ),
            "bridges_cached": self._bridges_cache is not None,
            "bridges_cache_age_seconds": (
                round((datetime.now(tz=timezone.utc) - self._bridges_updated).total_seconds(), 1)
                if self._bridges_updated
                else None
            ),
        }


# Global cache instance
mcp_cache = MCPToolCache(ttl_seconds=CACHE_TTL_SECONDS)


# ============================================================================
# Bridge Toggle Service (Redis-backed per-bridge enable/disable)
# ============================================================================


class MCPBridgeToggleService(AsyncRedisClientMixin):
    """Manage per-bridge enable/disable state via Redis."""

    _redis_database = "main"

    async def is_bridge_enabled(self, name: str) -> bool:
        """Return True when bridge is enabled (default when key absent)."""
        try:
            redis = await self._get_redis()
            value = await redis.get(f"mcp_bridge:enabled:{name}")
            if value is None:
                return True
            if isinstance(value, bytes):
                value = value.decode()
            return value.lower() != "false"
        except Exception as e:
            logger.error("Failed to read bridge enabled state for %s: %s", name, e)
            return True

    async def get_enabled_batch(self, names: List[str]) -> Dict[str, bool]:
        """Return enabled state for all named bridges in a single mget call."""
        if not names:
            return {}
        try:
            redis = await self._get_redis()
            keys = [f"mcp_bridge:enabled:{n}" for n in names]
            values = await redis.mget(*keys)
            result: Dict[str, bool] = {}
            for name, value in zip(names, values):
                if value is None:
                    result[name] = True
                else:
                    if isinstance(value, bytes):
                        value = value.decode()
                    result[name] = value.lower() != "false"
            return result
        except Exception as e:
            logger.error("Failed to batch-read bridge enabled states: %s", e)
            return {n: True for n in names}

    async def set_bridge_enabled(self, name: str, enabled: bool) -> None:
        """Set the enabled state for a bridge (no TTL — state is intentionally persistent)."""
        try:
            redis = await self._get_redis()
            if redis is None:
                logger.warning("Redis unavailable; bridge toggle for '%s' not persisted", name)
                return
            await redis.set(f"mcp_bridge:enabled:{name}", "true" if enabled else "false")
        except Exception as e:
            logger.error("Failed to set bridge enabled state for %s: %s", name, e)
            raise


get_toggle_service = lazy_singleton(MCPBridgeToggleService)


# ============================================================================
# Plugin Discovery
# ============================================================================

# Each entry: (module_path, name, endpoint, features)
_BRIDGE_MODULE_REGISTRY: List[Tuple[str, str, str, List[str]]] = [
    (
        "api.knowledge_mcp",
        "knowledge_mcp",
        "/api/knowledge/mcp/tools",
        ["search", "add_documents", "vector_similarity", "statistics"],
    ),
    (
        "api.vnc_mcp",
        "vnc_mcp",
        "/api/vnc/mcp/tools",
        ["vnc_status", "observe_activity", "browser_context"],
    ),
    (
        "api.sequential_thinking_mcp",
        "sequential_thinking_mcp",
        "/api/sequential_thinking/mcp/tools",
        ["sequential_thinking", "thought_tracking", "branching", "revision"],
    ),
    (
        "api.structured_thinking_mcp",
        "structured_thinking_mcp",
        "/api/structured_thinking/mcp/tools",
        ["process_thought", "generate_summary", "clear_history", "stage_tracking"],
    ),
    (
        "api.filesystem_mcp",
        "filesystem_mcp",
        "/api/filesystem/mcp/tools",
        ["read_files", "write_files", "directory_management", "search", "metadata"],
    ),
    (
        "api.browser_mcp",
        "browser_mcp",
        "/api/browser/mcp/tools",
        ["navigate", "click", "fill", "screenshot", "evaluate", "wait", "scraping"],
    ),
    (
        "api.http_client_mcp",
        "http_client_mcp",
        "/api/http_client/mcp/tools",
        ["get", "post", "put", "patch", "delete", "head", "rate_limiting"],
    ),
    (
        "api.database_mcp",
        "database_mcp",
        "/api/database/mcp/tools",
        ["query", "execute", "schema", "tables", "statistics", "sql_injection_prevention"],
    ),
    (
        "api.git_mcp",
        "git_mcp",
        "/api/git/mcp/tools",
        ["status", "log", "diff", "branch", "blame", "show", "repository_whitelist"],
    ),
    (
        "api.prometheus_mcp",
        "prometheus_mcp",
        "/api/prometheus/mcp/tools",
        [
            "query_metric",
            "query_range",
            "get_system_metrics",
            "get_service_health",
            "get_vm_metrics",
            "list_available_metrics",
        ],
    ),
    (
        "api.redis_mcp",
        "redis_mcp",
        "/api/redis/mcp/tools",
        ["data_access", "vector_search", "hybrid_search", "ops_intelligence", "stream_health", "rbac_filtering"],
    ),
]

# Registry mapping name -> (manifest, module_path) for hot-reload support
_MANIFEST_REGISTRY: dict[str, Tuple[MCPBridgeManifest, str]] = {}


def discover_bridges() -> List[Tuple[str, str, str, List[str]]]:
    """Discover bridges via entry-points, then fall back to module-scan."""
    _MANIFEST_REGISTRY.clear()
    manifests: List[MCPBridgeManifest] = []

    # 1. Try entry-point based discovery
    try:
        eps = importlib.metadata.entry_points(group="autobot.mcp_bridges")
        for ep in eps:
            try:
                manifest: MCPBridgeManifest = ep.load()
                if isinstance(manifest, MCPBridgeManifest):
                    logger.info("Discovered bridge via entry-point: %s", manifest.name)
                    manifests.append(manifest)
            except Exception as e:
                logger.warning("Failed to load entry-point %s: %s", ep.name, e)
    except Exception as e:
        logger.debug("Entry-point discovery unavailable: %s", e)

    # 2. Module-scan fallback
    discovered_names = {m.name for m in manifests}
    for module_path, name, endpoint, features in _BRIDGE_MODULE_REGISTRY:
        if name in discovered_names:
            continue
        manifest = None
        try:
            mod = importlib.import_module(module_path)
            manifest = getattr(mod, "MANIFEST", None)
            if isinstance(manifest, MCPBridgeManifest):
                logger.debug("Discovered bridge MANIFEST via module scan: %s", name)
            else:
                manifest = None
        except Exception as e:
            logger.debug("Could not import %s for MANIFEST scan: %s", module_path, e)

        if manifest is None:
            manifest = MCPBridgeManifest(
                name=name,
                version="0.0.0",
                description="",
                features=features,
                endpoint=endpoint,
            )
            logger.warning("Bridge '%s' has no MANIFEST attribute — using minimal fallback (version=0.0.0)", name)

        manifests.append(manifest)
        _MANIFEST_REGISTRY[name] = (manifest, module_path)

    # Store entry-point manifests in registry too (module path unknown)
    for m in manifests:
        if m.name not in _MANIFEST_REGISTRY:
            _MANIFEST_REGISTRY[m.name] = (m, "")

    # Return as legacy tuples for backward compatibility
    result: List[Tuple[str, str, str, List[str]]] = []
    for m in manifests:
        result.append((m.name, m.description, m.endpoint or "", m.features))
    return result


# ============================================================================
# Pydantic Models
# ============================================================================


# ============================================================================
# MCP Bridge Registry
# ============================================================================

# Each entry: (name, description, endpoint, features) — populated at module load
MCP_BRIDGES = discover_bridges()


# ============================================================================
# Helper Functions (Issue #50 - Extract fetch logic for caching)
# ============================================================================


def _build_tool_entry(tool: dict, bridge_name: str, bridge_desc: str, endpoint: str, features: List[str]) -> dict:
    """Build a tool entry with bridge info. (Issue #315 - extracted)"""
    return {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["input_schema"],
        "bridge": bridge_name,
        "bridge_description": bridge_desc,
        "endpoint": f"{endpoint.replace('/tools', '')}/{tool['name']}",
        "features": features,
    }


async def _fetch_bridge_tools(
    http_client,
    backend_url: str,
    bridge_name: str,
    bridge_desc: str,
    endpoint: str,
    features: List[str],
) -> tuple:
    """Fetch tools from a single bridge. Returns (tools_list, success). (Issue #315 - extracted)"""
    try:
        async with await http_client.get(
            f"{backend_url}{endpoint}",
            timeout=aiohttp.ClientTimeout(total=3),
        ) as response:
            if response.status != 200:
                logger.warning("MCP bridge %s returned status %s", bridge_name, response.status)
                return [], False
            tools = await response.json()
            entries = [_build_tool_entry(t, bridge_name, bridge_desc, endpoint, features) for t in tools]
            return entries, True
    except aiohttp.ClientError as e:
        logger.error("HTTP error fetching tools from %s: %s", bridge_name, e)
    except Exception as e:
        logger.error("Failed to fetch tools from %s: %s", bridge_name, e)
    return [], False


async def _fetch_tools_from_bridges() -> Metadata:
    """
    Fetch tools from all MCP bridges (internal helper).

    This is the actual HTTP fetching logic, separated for caching support.
    """
    backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
    all_tools = []
    bridge_count = 0

    http_client = get_http_client()
    # Use extracted helpers (Issue #315 - reduced depth)
    for bridge_name, bridge_desc, endpoint, features in MCP_BRIDGES:
        tools, success = await _fetch_bridge_tools(
            http_client, backend_url, bridge_name, bridge_desc, endpoint, features
        )
        all_tools.extend(tools)
        if success:
            bridge_count += 1

    return {
        "status": "success",
        "total_tools": len(all_tools),
        "total_bridges": len(MCP_BRIDGES),
        "healthy_bridges": bridge_count,
        "tools": all_tools,
        "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        "cached": False,
    }


async def _fetch_bridges_info() -> Metadata:
    """
    Fetch bridge information from all MCP bridges (internal helper).

    This is the actual HTTP fetching logic, separated for caching support.
    Includes manifest info and per-bridge enabled status (Issue #4462).
    """
    backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
    bridges = []
    # Issue #380: Get http_client once before loop instead of per-iteration
    http_client = get_http_client()
    toggle_svc = get_toggle_service()

    # Iterate _MANIFEST_REGISTRY so reloaded manifests are always fresh (blocker #1)
    bridge_names = list(_MANIFEST_REGISTRY.keys())
    enabled_map = await toggle_svc.get_enabled_batch(bridge_names)

    for bridge_name, (manifest, _module_path) in _MANIFEST_REGISTRY.items():
        endpoint = manifest.endpoint or ""
        manifest_dict = MCPBridgeManifestSchema(
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            features=manifest.features,
            endpoint=manifest.endpoint,
            resource_limits=manifest.resource_limits,
        ).model_dump()

        enabled = enabled_map.get(bridge_name, True)

        bridge_info = {
            "name": bridge_name,
            "description": manifest.description,
            "endpoint": endpoint,
            "features": manifest.features,
            "status": "unavailable",
            "tool_count": 0,
            "manifest": manifest_dict,
            "enabled": enabled,
        }

        if not endpoint:
            # Entry-point bridges with no declared endpoint cannot be health-checked
            bridge_info["status"] = "unknown"
            bridge_info["error"] = "no endpoint configured"
        else:
            try:
                async with await http_client.get(
                    f"{backend_url}{endpoint}",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as response:
                    if response.status == 200:
                        tools = await response.json()
                        bridge_info["status"] = "healthy"
                        bridge_info["tool_count"] = len(tools)
                    else:
                        bridge_info["status"] = "degraded"
                        bridge_info["error"] = f"HTTP {response.status}"
            except aiohttp.ClientError as e:
                bridge_info["status"] = "unavailable"
                bridge_info["error"] = str(e)
                logger.error("HTTP error during health check for %s: %s", bridge_name, e)
            except Exception as e:
                bridge_info["status"] = "unavailable"
                bridge_info["error"] = str(e)
                logger.error("Health check failed for %s: %s", bridge_name, e)

        bridges.append(bridge_info)

    # Calculate overall health
    healthy_count = sum(1 for b in bridges if b["status"] == "healthy")

    return {
        "status": "success",
        "total_bridges": len(bridges),
        "healthy_bridges": healthy_count,
        "bridges": bridges,
        "last_checked": datetime.now(tz=timezone.utc).isoformat(),
        "cached": False,
    }


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/tools", response_model=MCPRegistryToolsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_all_mcp_tools",
    error_code_prefix="MCP_REGISTRY",
)
async def list_all_mcp_tools() -> Metadata:
    """
    List all available MCP tools from all bridges (with caching)

    Returns aggregated list of tools from:
    - knowledge_mcp (knowledge base operations)
    - vnc_mcp (VNC observation)
    - sequential_thinking_mcp (dynamic problem-solving)
    - structured_thinking_mcp (5-stage cognitive framework)
    - filesystem_mcp (secure file operations)

    Caching (Issue #50):
    - First request fetches from all bridges (~5 HTTP calls)
    - Subsequent requests return cached data (0 HTTP calls)
    - Cache expires after TTL (default: 60 seconds)

    Response format:
    {
        "total_tools": 25,
        "bridges": 5,
        "tools": [...],
        "cached": true/false,
        "last_updated": "..."
    }
    """
    # Check cache first
    cached_data = mcp_cache.get_tools()
    if cached_data is not None:
        # Mark as cached for response
        cached_data["cached"] = True
        return cached_data

    # Cache miss - fetch from bridges
    logger.info("Cache miss - fetching MCP tools from %s bridges", len(MCP_BRIDGES))
    tools_data = await _fetch_tools_from_bridges()

    # Update cache
    mcp_cache.set_tools(tools_data)

    return tools_data


@router.get("/bridges", response_model=MCPRegistryBridgesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_bridges",
    error_code_prefix="MCP_REGISTRY",
)
async def get_mcp_bridges() -> Metadata:
    """
    Get information about all MCP bridges (with caching)

    Returns health status and capabilities of each MCP bridge:
    - knowledge_mcp - Knowledge base operations
    - vnc_mcp - VNC observation
    - sequential_thinking_mcp - Dynamic problem-solving
    - structured_thinking_mcp - 5-stage cognitive framework
    - filesystem_mcp - Secure file operations

    Caching (Issue #50):
    - First request checks all bridges (~5 HTTP calls)
    - Subsequent requests return cached data (0 HTTP calls)
    - Cache expires after TTL (default: 60 seconds)

    Response includes:
    - Bridge name and description
    - Health status (healthy/degraded/unavailable)
    - Number of tools provided
    - Available features
    """
    # Check cache first
    cached_data = mcp_cache.get_bridges()
    if cached_data is not None:
        cached_data["cached"] = True
        return cached_data

    # Cache miss - fetch from bridges
    logger.info("Cache miss - fetching bridge info from %s bridges", len(MCP_BRIDGES))
    bridges_data = await _fetch_bridges_info()

    # Update cache
    mcp_cache.set_bridges(bridges_data)

    return bridges_data


@router.post("/cache/invalidate", response_model=MCPRegistryCacheInvalidateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="invalidate_mcp_cache",
    error_code_prefix="MCP_REGISTRY",
)
async def invalidate_mcp_cache() -> Metadata:
    """
    Manually invalidate MCP Registry cache (Issue #50)

    Use this endpoint to force cache refresh after:
    - Adding new MCP bridges
    - Bridge health changes
    - Configuration updates

    Returns:
        Confirmation of cache invalidation with timestamp
    """
    mcp_cache.invalidate_all()

    return {
        "status": "success",
        "message": "MCP Registry cache invalidated",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "cache_stats": mcp_cache.get_stats(),
    }


@router.get("/cache/stats", response_model=MCPRegistryCacheStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_cache_stats",
    error_code_prefix="MCP_REGISTRY",
)
async def get_mcp_cache_stats() -> Metadata:
    """
    Get MCP Registry cache statistics (Issue #50)

    Returns:
        - Cache hit/miss counts
        - Hit rate percentage
        - Cache age information
        - Configuration details
    """
    return {
        "status": "success",
        "cache": mcp_cache.get_stats(),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


def _find_bridge_by_name(bridge_name: str) -> tuple:
    """
    Find a bridge configuration by name.

    Issue #620.

    Args:
        bridge_name: Name of the MCP bridge to find

    Returns:
        Bridge tuple (name, description, endpoint, features)

    Raises:
        HTTPException: If bridge not found
    """
    bridge = next(
        (b for b in MCP_BRIDGES if b[0] == bridge_name),
        None,
    )
    if not bridge:
        raise HTTPException(status_code=404, detail=f"MCP bridge '{bridge_name}' not found")
    return bridge


async def _fetch_tools_from_bridge(backend_url: str, endpoint: str) -> list:
    """
    Fetch tools list from a specific bridge endpoint.

    Issue #620.

    Args:
        backend_url: Backend base URL
        endpoint: Bridge endpoint path

    Returns:
        List of tools from the bridge

    Raises:
        HTTPException: If bridge returns non-200 status
    """
    http_client = get_http_client()
    async with await http_client.get(
        f"{backend_url}{endpoint}",
        timeout=aiohttp.ClientTimeout(total=3),
    ) as response:
        if response.status != 200:
            raise HTTPException(
                status_code=502,
                detail=f"MCP bridge returned status {response.status}",
            )
        return await response.json()


def _find_tool_in_list(tools: list, tool_name: str, bridge_name: str) -> dict:
    """
    Find a specific tool in the tools list.

    Issue #620.

    Args:
        tools: List of tool definitions
        tool_name: Name of tool to find
        bridge_name: Bridge name (for error message)

    Returns:
        Tool definition dict

    Raises:
        HTTPException: If tool not found
    """
    tool = next(
        (t for t in tools if t["name"] == tool_name),
        None,
    )
    if not tool:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found in bridge '{bridge_name}'",
        )
    return tool


@router.get("/tools/{bridge_name}/{tool_name}", response_model=MCPRegistryToolDetailResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_tool_details",
    error_code_prefix="MCP_REGISTRY",
)
async def get_mcp_tool_details(bridge_name: str, tool_name: str) -> Metadata:
    """
    Get detailed information about a specific MCP tool.

    Issue #620: Refactored to use extracted helpers.

    Args:
        bridge_name: Name of the MCP bridge (e.g., "knowledge_mcp")
        tool_name: Name of the tool (e.g., "search_knowledge_base")

    Returns:
        Detailed tool information including full schema and bridge info
    """
    backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"

    # Find the bridge (Issue #620: uses helper)
    bridge = _find_bridge_by_name(bridge_name)
    _, bridge_desc, endpoint, _ = bridge  # Issue #382: features unused

    try:
        # Fetch tools from bridge (Issue #620: uses helper)
        tools = await _fetch_tools_from_bridge(backend_url, endpoint)

        # Find the specific tool (Issue #620: uses helper)
        tool = _find_tool_in_list(tools, tool_name, bridge_name)

        return {
            "status": "success",
            "tool": {
                **tool,
                "bridge": bridge_name,
                "bridge_description": bridge_desc,
                "endpoint": f"{endpoint.replace('/tools', '')}/{tool_name}",
            },
        }

    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        logger.error("HTTP error fetching tool details from %s: %s", bridge_name, e)
        raise HTTPException(status_code=502, detail="Failed to connect to MCP bridge")
    except Exception as e:
        logger.error("Failed to get tool details: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bridges/{name}/enable", response_model=MCPBridgeToggleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enable_mcp_bridge",
    error_code_prefix="MCP_REGISTRY",
)
async def enable_mcp_bridge(name: str) -> Metadata:
    """Enable a registered MCP bridge (Issue #4462)."""
    _find_bridge_by_name(name)
    toggle_svc = get_toggle_service()
    await toggle_svc.set_bridge_enabled(name, True)
    mcp_cache.invalidate_all()
    return {
        "status": "success",
        "bridge": name,
        "enabled": True,
        "message": f"Bridge '{name}' enabled",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/bridges/{name}/disable", response_model=MCPBridgeToggleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="disable_mcp_bridge",
    error_code_prefix="MCP_REGISTRY",
)
async def disable_mcp_bridge(name: str) -> Metadata:
    """Disable a registered MCP bridge (Issue #4462)."""
    _find_bridge_by_name(name)
    toggle_svc = get_toggle_service()
    await toggle_svc.set_bridge_enabled(name, False)
    mcp_cache.invalidate_all()
    return {
        "status": "success",
        "bridge": name,
        "enabled": False,
        "message": f"Bridge '{name}' disabled",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/bridges/{name}/reload", response_model=MCPBridgeToggleResponse, status_code=202)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reload_mcp_bridge",
    error_code_prefix="MCP_REGISTRY",
)
async def reload_mcp_bridge(name: str) -> Metadata:
    """Hot-reload a bridge module and refresh its manifest (Issue #4462).

    Returns 202 because importlib.reload only affects the current uvicorn worker;
    other workers retain the previous state until they are restarted.
    """
    _find_bridge_by_name(name)
    manifest_entry = _MANIFEST_REGISTRY.get(name)
    if not manifest_entry:
        raise HTTPException(status_code=404, detail=f"Bridge '{name}' not found in manifest registry")
    _, module_path = manifest_entry
    if not module_path:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Bridge '{name}' was registered via an entry-point (module path unknown) "
                "and cannot be hot-reloaded. Restart the server to pick up changes."
            ),
        )
    logger.warning(
        "reload_mcp_bridge('%s'): importlib.reload affects only the current uvicorn worker. "
        "Other workers retain the previous module state until restarted.",
        name,
    )
    try:
        mod = importlib.import_module(module_path)
        importlib.reload(mod)
        new_manifest = getattr(mod, "MANIFEST", None)
        if isinstance(new_manifest, MCPBridgeManifest):
            _MANIFEST_REGISTRY[name] = (new_manifest, module_path)
            logger.info("Reloaded bridge '%s' — MANIFEST updated", name)
        else:
            logger.warning("Reloaded bridge '%s' has no MANIFEST attribute", name)
    except Exception as e:
        logger.error("Failed to reload bridge '%s': %s", name, e)
        raise HTTPException(status_code=500, detail=f"Failed to reload bridge '{name}': {e}")
    mcp_cache.invalidate_all()
    toggle_svc = get_toggle_service()
    enabled = await toggle_svc.is_bridge_enabled(name)
    return {
        "status": "accepted",
        "bridge": name,
        "enabled": enabled,
        "message": (
            f"Bridge '{name}' reloaded on this worker. "
            "Other uvicorn workers retain the previous state until restarted."
        ),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@register_health_probe("mcp_registry")
async def probe_mcp_registry(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for the MCP bridge registry."""
    try:
        if not MCP_BRIDGES:
            return ComponentHealth(
                name="mcp_registry",
                status="degraded",
                detail="no MCP bridges configured",
            )
        return ComponentHealth(
            name="mcp_registry",
            status="ok",
            data={"bridge_count": len(MCP_BRIDGES)},
        )
    except Exception as exc:
        return ComponentHealth(
            name="mcp_registry",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


@router.get("/stats", response_model=MCPRegistryStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_registry_stats",
    error_code_prefix="MCP_REGISTRY",
)
async def get_mcp_registry_stats() -> Metadata:
    """
    Get usage statistics for MCP registry

    Uses cached data when available (Issue #50 optimization).

    Returns:
    - Total tools available
    - Bridge health summary
    - Tool categories
    - Feature availability
    - Cache statistics
    """
    # Get all tools (uses cache if available)
    tools_response = await list_all_mcp_tools()

    # Categorize by bridge
    bridge_tool_counts = {}
    for tool in tools_response.get("tools", []):
        bridge = tool["bridge"]
        bridge_tool_counts[bridge] = bridge_tool_counts.get(bridge, 0) + 1

    # Get bridge health (uses cache if available)
    bridges_response = await get_mcp_bridges()

    return {
        "status": "success",
        "overview": {
            "total_tools": tools_response["total_tools"],
            "total_bridges": tools_response["total_bridges"],
            "healthy_bridges": tools_response["healthy_bridges"],
        },
        "tools_by_bridge": bridge_tool_counts,
        "bridge_health": {b["name"]: b["status"] for b in bridges_response["bridges"]},
        "available_features": list(set(feature for _, _, _, features in MCP_BRIDGES for feature in features)),
        "cache": mcp_cache.get_stats(),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/", response_model=MCPRegistryInfoResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_registry_info",
    error_code_prefix="MCP_REGISTRY",
)
async def get_mcp_registry_info() -> Metadata:
    """
    Get information about the MCP Registry API

    Returns overview of MCP system architecture and available endpoints
    """
    return {
        "name": "AutoBot MCP Registry",
        "version": "1.1.0",  # Updated for Issue #50 caching
        "description": "Centralized registry for all AutoBot MCP tools and bridges",
        "architecture": {
            "purpose": "Aggregate and manage MCP tools from multiple bridges",
            "bridges": [
                {
                    "name": name,
                    "description": desc,
                    "features": features,
                }
                for name, desc, _, features in MCP_BRIDGES
            ],
        },
        "endpoints": {
            "list_tools": "GET /api/mcp/tools",
            "list_bridges": "GET /api/mcp/bridges",
            "tool_details": "GET /api/mcp/tools/{bridge}/{tool}",
            "health": "GET /api/mcp/health",
            "stats": "GET /api/mcp/stats",
            "cache_stats": "GET /api/mcp/cache/stats",
            "cache_invalidate": "POST /api/mcp/cache/invalidate",
        },
        "performance": {
            "caching": "Enabled" if CACHE_ENABLED else "Disabled",
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "note": "Issue #50 - MCP Registry Caching Optimization",
        },
        "note": "This is AutoBot's MCP (not Claude's MCP in .mcp/ folder)",
    }
