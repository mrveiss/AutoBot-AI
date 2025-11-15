"""
MCP Registry API - Centralized management for all AutoBot MCP tools
Provides unified access to all MCP bridges for frontend management

This registry aggregates MCP tools from all bridges:
- knowledge_mcp.py - Knowledge base operations (LlamaIndex, Redis vectors)
- vnc_mcp.py - VNC observation and browser context
- [Future MCP bridges added here]

Architecture:
-----------
Frontend MCP Manager
       ↓
mcp_registry.py (This module - aggregates all MCP tools)
       ↓
┌──────────────┬──────────────┬──────────────┐
│ knowledge_mcp│   vnc_mcp    │  future_mcp  │
└──────────────┴──────────────┴──────────────┘

Key Features:
- List all available MCP tools across all bridges
- Get tool schemas and documentation
- Health checks for each MCP bridge
- Usage statistics and monitoring
- Tool execution routing
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.constants.network_constants import NetworkConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mcp", tags=["mcp", "registry"])


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


# MCP Bridge Registry
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
]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_all_mcp_tools",
    error_code_prefix="MCP_REGISTRY",
)
@router.get("/tools")
async def list_all_mcp_tools() -> Dict[str, Any]:
    """
    List all available MCP tools from all bridges

    Returns aggregated list of tools from:
    - knowledge_mcp (knowledge base operations)
    - vnc_mcp (VNC observation)
    - Future MCP bridges

    Response format:
    {
        "total_tools": 8,
        "bridges": 2,
        "tools": [
            {
                "name": "search_knowledge_base",
                "description": "Search knowledge base...",
                "bridge": "knowledge_mcp",
                "endpoint": "/api/knowledge/mcp/search_knowledge_base",
                "input_schema": {...}
            },
            ...
        ]
    }
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
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_bridges",
    error_code_prefix="MCP_REGISTRY",
)
@router.get("/bridges")
async def get_mcp_bridges() -> Dict[str, Any]:
    """
    Get information about all MCP bridges

    Returns health status and capabilities of each MCP bridge:
    - knowledge_mcp - Knowledge base operations
    - vnc_mcp - VNC observation
    - Future bridges

    Response includes:
    - Bridge name and description
    - Health status (healthy/degraded/unavailable)
    - Number of tools provided
    - Available features
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

    Returns:
    - Total tools available
    - Bridge health summary
    - Tool categories
    - Feature availability
    """
    # Get all tools
    tools_response = await list_all_mcp_tools()

    # Categorize by bridge
    bridge_tool_counts = {}
    for tool in tools_response.get("tools", []):
        bridge = tool["bridge"]
        bridge_tool_counts[bridge] = bridge_tool_counts.get(bridge, 0) + 1

    # Get bridge health
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
        "version": "1.0.0",
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
        },
        "note": "This is AutoBot's MCP (not Claude's MCP in .mcp/ folder)",
    }
