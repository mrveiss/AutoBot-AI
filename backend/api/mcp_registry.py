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

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.constants.network_constants import NetworkConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["mcp", "registry"])


# ============================================================================
# Cache Configuration (Issue #50 - MCP Registry Caching Optimization)
# ============================================================================

# Load cache configuration from environment
CACHE_ENABLED = os.getenv("MCP_REGISTRY_CACHE_ENABLED", "true").lower() == "true"
CACHE_TTL_SECONDS = int(os.getenv("MCP_REGISTRY_CACHE_TTL", "60"))

logger.info(
    f"MCP Registry Cache: enabled={CACHE_ENABLED}, TTL={CACHE_TTL_SECONDS}s"
)


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
        self.ttl = timedelta(seconds=ttl_seconds)
        self._tools_cache: Optional[Dict[str, Any]] = None
        self._tools_updated: Optional[datetime] = None
        self._bridges_cache: Optional[Dict[str, Any]] = None
        self._bridges_updated: Optional[datetime] = None
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "invalidations": 0,
        }

    def get_tools(self) -> Optional[Dict[str, Any]]:
        """Get cached tools if still valid"""
        if not CACHE_ENABLED:
            return None

        if self._tools_cache is None or self._tools_updated is None:
            self._stats["cache_misses"] += 1
            return None

        age = datetime.now() - self._tools_updated
        if age > self.ttl:
            logger.debug(f"MCP tools cache expired (age: {age.total_seconds():.1f}s)")
            self._stats["cache_misses"] += 1
            return None

        logger.debug(f"MCP tools cache hit (age: {age.total_seconds():.1f}s)")
        self._stats["cache_hits"] += 1
        return self._tools_cache

    def set_tools(self, data: Dict[str, Any]) -> None:
        """Update tools cache"""
        if not CACHE_ENABLED:
            return

        self._tools_cache = data
        self._tools_updated = datetime.now()
        logger.info(f"MCP tools cache updated (TTL: {self.ttl.seconds}s)")

    def get_bridges(self) -> Optional[Dict[str, Any]]:
        """Get cached bridges if still valid"""
        if not CACHE_ENABLED:
            return None

        if self._bridges_cache is None or self._bridges_updated is None:
            self._stats["cache_misses"] += 1
            return None

        age = datetime.now() - self._bridges_updated
        if age > self.ttl:
            logger.debug(f"MCP bridges cache expired (age: {age.total_seconds():.1f}s)")
            self._stats["cache_misses"] += 1
            return None

        logger.debug(f"MCP bridges cache hit (age: {age.total_seconds():.1f}s)")
        self._stats["cache_hits"] += 1
        return self._bridges_cache

    def set_bridges(self, data: Dict[str, Any]) -> None:
        """Update bridges cache"""
        if not CACHE_ENABLED:
            return

        self._bridges_cache = data
        self._bridges_updated = datetime.now()
        logger.info(f"MCP bridges cache updated (TTL: {self.ttl.seconds}s)")

    def invalidate_all(self) -> None:
        """Invalidate all caches"""
        self._tools_cache = None
        self._tools_updated = None
        self._bridges_cache = None
        self._bridges_updated = None
        self._stats["invalidations"] += 1
        logger.info("MCP Registry cache invalidated")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self._stats["cache_hits"] + self._stats["cache_misses"]
        hit_rate = (
            (self._stats["cache_hits"] / total_requests * 100)
            if total_requests > 0
            else 0
        )

        return {
            "enabled": CACHE_ENABLED,
            "ttl_seconds": self.ttl.seconds,
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "hit_rate_percent": round(hit_rate, 2),
            "invalidations": self._stats["invalidations"],
            "tools_cached": self._tools_cache is not None,
            "tools_cache_age_seconds": (
                round((datetime.now() - self._tools_updated).total_seconds(), 1)
                if self._tools_updated
                else None
            ),
            "bridges_cached": self._bridges_cache is not None,
            "bridges_cache_age_seconds": (
                round((datetime.now() - self._bridges_updated).total_seconds(), 1)
                if self._bridges_updated
                else None
            ),
        }


# Global cache instance
mcp_cache = MCPToolCache(ttl_seconds=CACHE_TTL_SECONDS)


# ============================================================================
# Pydantic Models
# ============================================================================


class MCPToolInfo(BaseModel):
    """Information about an MCP tool"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    bridge: str  # Which MCP bridge provides this tool
    endpoint: str  # Full endpoint URL


class MCPBridgeInfo(BaseModel):
    """Information about an MCP bridge"""

    name: str
    description: str
    status: str  # "healthy", "degraded", "unavailable"
    tool_count: int
    endpoint: str
    features: List[str]


class MCPRegistryStats(BaseModel):
    """Overall MCP registry statistics"""

    total_bridges: int
    total_tools: int
    healthy_bridges: int
    last_updated: str


# ============================================================================
# MCP Bridge Registry
# ============================================================================

# Each entry: (name, description, endpoint, features)
MCP_BRIDGES = [
    (
        "knowledge_mcp",
        "Knowledge Base Operations (LlamaIndex + Redis Vectors)",
        "/api/knowledge/mcp/tools",
        ["search", "add_documents", "vector_similarity", "statistics"],
    ),
    (
        "vnc_mcp",
        "VNC Observation and Browser Context",
        "/api/vnc/mcp/tools",
        ["vnc_status", "observe_activity", "browser_context"],
    ),
    (
        "sequential_thinking_mcp",
        "Sequential Thinking - Dynamic Problem-Solving Framework",
        "/api/sequential_thinking/mcp/tools",
        ["sequential_thinking", "thought_tracking", "branching", "revision"],
    ),
    (
        "structured_thinking_mcp",
        "Structured Thinking - 5-Stage Cognitive Framework",
        "/api/structured_thinking/mcp/tools",
        ["process_thought", "generate_summary", "clear_history", "stage_tracking"],
    ),
    (
        "filesystem_mcp",
        "Filesystem Operations - Secure File & Directory Access",
        "/api/filesystem/mcp/tools",
        ["read_files", "write_files", "directory_management", "search", "metadata"],
    ),
]


# ============================================================================
# Helper Functions (Issue #50 - Extract fetch logic for caching)
# ============================================================================


async def _fetch_tools_from_bridges() -> Dict[str, Any]:
    """
    Fetch tools from all MCP bridges (internal helper).

    This is the actual HTTP fetching logic, separated for caching support.
    """
    backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:8001"
    all_tools = []
    bridge_count = 0

    for bridge_name, bridge_desc, endpoint, features in MCP_BRIDGES:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{backend_url}{endpoint}",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as response:
                    if response.status == 200:
                        tools = await response.json()
                        bridge_count += 1

                        # Add bridge info to each tool
                        for tool in tools:
                            all_tools.append(
                                {
                                    "name": tool["name"],
                                    "description": tool["description"],
                                    "input_schema": tool["input_schema"],
                                    "bridge": bridge_name,
                                    "bridge_description": bridge_desc,
                                    "endpoint": f"{endpoint.replace('/tools', '')}/{tool['name']}",
                                    "features": features,
                                }
                            )
                    else:
                        logger.warning(
                            f"MCP bridge {bridge_name} returned status {response.status}"
                        )
        except Exception as e:
            logger.error(f"Failed to fetch tools from {bridge_name}: {e}")

    return {
        "status": "success",
        "total_tools": len(all_tools),
        "total_bridges": len(MCP_BRIDGES),
        "healthy_bridges": bridge_count,
        "tools": all_tools,
        "last_updated": datetime.now().isoformat(),
        "cached": False,
    }


async def _fetch_bridges_info() -> Dict[str, Any]:
    """
    Fetch bridge information from all MCP bridges (internal helper).

    This is the actual HTTP fetching logic, separated for caching support.
    """
    backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:8001"
    bridges = []

    for bridge_name, bridge_desc, endpoint, features in MCP_BRIDGES:
        bridge_info = {
            "name": bridge_name,
            "description": bridge_desc,
            "endpoint": endpoint,
            "features": features,
            "status": "unavailable",
            "tool_count": 0,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
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
        except Exception as e:
            bridge_info["status"] = "unavailable"
            bridge_info["error"] = str(e)
            logger.error(f"Health check failed for {bridge_name}: {e}")

        bridges.append(bridge_info)

    # Calculate overall health
    healthy_count = sum(1 for b in bridges if b["status"] == "healthy")

    return {
        "status": "success",
        "total_bridges": len(bridges),
        "healthy_bridges": healthy_count,
        "bridges": bridges,
        "last_checked": datetime.now().isoformat(),
        "cached": False,
    }


# ============================================================================
# API Endpoints
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_all_mcp_tools",
    error_code_prefix="MCP_REGISTRY",
)
@router.get("/tools")
async def list_all_mcp_tools() -> Dict[str, Any]:
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
    logger.info(f"Cache miss - fetching MCP tools from {len(MCP_BRIDGES)} bridges")
    tools_data = await _fetch_tools_from_bridges()

    # Update cache
    mcp_cache.set_tools(tools_data)

    return tools_data


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_bridges",
    error_code_prefix="MCP_REGISTRY",
)
@router.get("/bridges")
async def get_mcp_bridges() -> Dict[str, Any]:
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
    logger.info(f"Cache miss - fetching bridge info from {len(MCP_BRIDGES)} bridges")
    bridges_data = await _fetch_bridges_info()

    # Update cache
    mcp_cache.set_bridges(bridges_data)

    return bridges_data


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="invalidate_mcp_cache",
    error_code_prefix="MCP_REGISTRY",
)
@router.post("/cache/invalidate")
async def invalidate_mcp_cache() -> Dict[str, Any]:
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
        "timestamp": datetime.now().isoformat(),
        "cache_stats": mcp_cache.get_stats(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_cache_stats",
    error_code_prefix="MCP_REGISTRY",
)
@router.get("/cache/stats")
async def get_mcp_cache_stats() -> Dict[str, Any]:
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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_tool_details",
    error_code_prefix="MCP_REGISTRY",
)
@router.get("/tools/{bridge_name}/{tool_name}")
async def get_mcp_tool_details(bridge_name: str, tool_name: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific MCP tool

    Args:
        bridge_name: Name of the MCP bridge (e.g., "knowledge_mcp")
        tool_name: Name of the tool (e.g., "search_knowledge_base")

    Returns:
        Detailed tool information including:
        - Full schema
        - Usage examples
        - Bridge information
    """
    backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:8001"

    # Find the bridge
    bridge = next(
        (b for b in MCP_BRIDGES if b[0] == bridge_name),
        None,
    )

    if not bridge:
        raise HTTPException(
            status_code=404, detail=f"MCP bridge '{bridge_name}' not found"
        )

    bridge_name_found, bridge_desc, endpoint, features = bridge

    try:
        # Fetch all tools from the bridge
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{backend_url}{endpoint}",
                timeout=aiohttp.ClientTimeout(total=3),
            ) as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=502,
                        detail=f"MCP bridge returned status {response.status}",
                    )

                tools = await response.json()

                # Find the specific tool
                tool = next(
                    (t for t in tools if t["name"] == tool_name),
                    None,
                )

                if not tool:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Tool '{tool_name}' not found in bridge '{bridge_name}'",
                    )

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
    except Exception as e:
        logger.error(f"Failed to get tool details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_registry_health",
    error_code_prefix="MCP_REGISTRY",
)
@router.get("/health")
async def get_mcp_registry_health() -> Dict[str, Any]:
    """
    Get overall health status of MCP registry system

    Note: This endpoint always fetches fresh data (no caching)
    to provide accurate health status.

    Checks:
    - All MCP bridges reachable
    - Tool counts
    - Response times
    """
    backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:8001"
    health_checks = []

    for bridge_name, bridge_desc, endpoint, features in MCP_BRIDGES:
        start_time = datetime.now()
        check = {
            "bridge": bridge_name,
            "status": "unknown",
            "response_time_ms": 0,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{backend_url}{endpoint}",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as response:
                    response_time = (datetime.now() - start_time).total_seconds() * 1000
                    check["response_time_ms"] = round(response_time, 2)

                    if response.status == 200:
                        tools = await response.json()
                        check["status"] = "healthy"
                        check["tool_count"] = len(tools)
                    else:
                        check["status"] = "degraded"
                        check["error"] = f"HTTP {response.status}"
        except Exception as e:
            check["status"] = "unavailable"
            check["error"] = str(e)

        health_checks.append(check)

    # Overall status
    healthy_bridges = sum(1 for c in health_checks if c["status"] == "healthy")
    overall_status = "healthy" if healthy_bridges == len(MCP_BRIDGES) else "degraded"

    return {
        "status": overall_status,
        "total_bridges": len(MCP_BRIDGES),
        "healthy_bridges": healthy_bridges,
        "checks": health_checks,
        "cache_stats": mcp_cache.get_stats(),
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_registry_stats",
    error_code_prefix="MCP_REGISTRY",
)
@router.get("/stats")
async def get_mcp_registry_stats() -> Dict[str, Any]:
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
        "bridge_health": {
            b["name"]: b["status"] for b in bridges_response["bridges"]
        },
        "available_features": list(
            set(
                feature
                for _, _, _, features in MCP_BRIDGES
                for feature in features
            )
        ),
        "cache": mcp_cache.get_stats(),
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_registry_info",
    error_code_prefix="MCP_REGISTRY",
)
@router.get("/")
async def get_mcp_registry_info() -> Dict[str, Any]:
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
