# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VNC MCP Bridge
Exposes VNC observation capabilities as MCP tools for AutoBot's LLM agents
Integrates with backend VNC proxy for browser and desktop observation
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List

import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.http_client import get_http_client
from backend.constants.network_constants import NetworkConstants
from backend.type_defs.common import Metadata

logger = logging.getLogger(__name__)
router = APIRouter(tags=["vnc_mcp", "mcp", "vnc"])

# Lock for thread-safe access to vnc_observations
_vnc_observations_lock = asyncio.Lock()

# VNC observation cache
vnc_observations = {
    "desktop": {"recent_activity": [], "last_check": None},
    "browser": {"recent_activity": [], "last_check": None},
}

# Issue #281: MCP tool definitions extracted from get_vnc_mcp_tools
# Tuple of (name, description, input_schema) for each VNC tool
VNC_MCP_TOOL_DEFINITIONS = (
    (
        "check_vnc_status",
        (
            "Check if VNC connection is active and accessible. Use this to verify browser or "
            "desktop VNC is available before attempting observations."
        ),
        {
            "type": "object",
            "properties": {
                "vnc_type": {
                    "type": "string",
                    "enum": ["desktop", "browser"],
                    "description": "Which VNC to check: 'desktop' (main machine) or 'browser' (Playwright headed mode)",
                    "default": "browser",
                }
            },
            "required": [],
        },
    ),
    (
        "observe_vnc_activity",
        (
            "Observe recent VNC activity and traffic. Returns statistics about WebSocket "
            "traffic, connection state, and recent interactions. Useful for understanding "
            "what the human is viewing/doing in the browser or desktop."
        ),
        {
            "type": "object",
            "properties": {
                "vnc_type": {
                    "type": "string",
                    "enum": ["desktop", "browser"],
                    "description": "Which VNC to observe: 'desktop' or 'browser'",
                    "default": "browser",
                },
                "duration_seconds": {
                    "type": "integer",
                    "description": "How many seconds of recent activity to include",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 60,
                },
            },
            "required": ["vnc_type"],
        },
    ),
    (
        "get_browser_vnc_context",
        (
            "Get current context from browser VNC: what page is visible, "
            "what the human is doing. Combines VNC observations with Playwright state for full picture."
        ),
        {
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
)


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: Metadata


class VNCStatusRequest(BaseModel):
    """Request model for VNC status check"""

    vnc_type: str = Field("browser", description="VNC type: 'desktop' or 'browser'")


class VNCObservationRequest(BaseModel):
    """Request model for VNC observations"""

    vnc_type: str = Field("browser", description="VNC type: 'desktop' or 'browser'")
    duration_seconds: int = Field(
        5, description="How many seconds of recent activity to return"
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vnc_mcp_tools",
    error_code_prefix="VNC_MCP",
)
@router.get("/mcp/tools")
async def get_vnc_mcp_tools() -> List[MCPTool]:
    """
    Get available MCP tools for VNC observation.

    Issue #281: Refactored to use module-level VNC_MCP_TOOL_DEFINITIONS.
    Reduced from 72 lines to ~10 lines (86% reduction).

    These tools allow AutoBot's LLM agents to:
    - Check if VNC connections are active
    - Observe browser/desktop activity via VNC proxy
    - Get real-time status of what humans are viewing
    """
    return [
        MCPTool(name=name, description=desc, input_schema=schema)
        for name, desc, schema in VNC_MCP_TOOL_DEFINITIONS
    ]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_vnc_status_mcp",
    error_code_prefix="VNC_MCP",
)
@router.post("/mcp/check_vnc_status")
async def check_vnc_status_mcp(request: VNCStatusRequest) -> Metadata:
    """
    MCP tool implementation: check_vnc_status

    Check if specified VNC connection is active and accessible
    """
    vnc_type = request.vnc_type
    backend_url = (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
    )

    try:
        http_client = get_http_client()
        async with await http_client.get(
            f"{backend_url}/api/vnc-proxy/{vnc_type}/status",
            timeout=aiohttp.ClientTimeout(total=5),
        ) as response:
            status_data = await response.json()

            return {
                "success": True,
                "vnc_type": vnc_type,
                "accessible": status_data.get("accessible", False),
                "endpoint": status_data.get("endpoint"),
                "status_code": response.status,
                "message": (
                    f"VNC {vnc_type} is {'accessible' if status_data.get('accessible') else 'not accessible'}"
                ),
            }
    except aiohttp.ClientError as e:
        logger.error("HTTP error checking VNC status for %s: %s", vnc_type, e)
        return {
            "success": False,
            "vnc_type": vnc_type,
            "accessible": False,
            "error": str(e),
            "message": f"HTTP error checking VNC {vnc_type} status",
        }
    except Exception as e:
        logger.error("Failed to check VNC status for %s: %s", vnc_type, e)
        return {
            "success": False,
            "vnc_type": vnc_type,
            "accessible": False,
            "error": str(e),
            "message": f"Failed to check VNC {vnc_type} status",
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="observe_vnc_activity_mcp",
    error_code_prefix="VNC_MCP",
)
@router.post("/mcp/observe_vnc_activity")
async def observe_vnc_activity_mcp(request: VNCObservationRequest) -> Metadata:
    """
    MCP tool implementation: observe_vnc_activity

    Observe recent VNC WebSocket traffic and activity

    Note: This returns cached observations from the VNC proxy.
    The backend VNC proxy logs all WebSocket frames, and this tool
    retrieves those logs for agent observation.
    """
    vnc_type = request.vnc_type
    duration = request.duration_seconds

    # Get cached observations (thread-safe)
    async with _vnc_observations_lock:
        cache = vnc_observations.get(vnc_type, {})
        recent_activity = list(cache.get("recent_activity", []))  # Copy list
        last_check = cache.get("last_check")

    # Filter by duration
    cutoff_time = datetime.now() - timedelta(seconds=duration)
    filtered_activity = [
        obs
        for obs in recent_activity
        if obs.get("timestamp")
        and datetime.fromisoformat(obs["timestamp"]) > cutoff_time
    ]

    return {
        "success": True,
        "vnc_type": vnc_type,
        "duration_seconds": duration,
        "observation_count": len(filtered_activity),
        "observations": filtered_activity,
        "last_check": last_check.isoformat() if last_check else None,
        "message": (
            f"Retrieved {len(filtered_activity)} VNC observations from last {duration}s"
        ),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_browser_vnc_context_mcp",
    error_code_prefix="VNC_MCP",
)
@router.post("/mcp/get_browser_vnc_context")
async def get_browser_vnc_context_mcp() -> Metadata:
    """
    MCP tool implementation: get_browser_vnc_context

    Get comprehensive context about what's happening in the browser VNC:
    - Current Playwright page state (URL, title)
    - Recent VNC activity (user interactions)
    - Combined view for full situational awareness
    """
    backend_url = (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
    )
    browser_vm_url = f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}"

    context = {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "playwright_state": {},
        "vnc_state": {},
    }

    # Get Playwright state using singleton HTTP client
    http_client = get_http_client()
    try:
        async with await http_client.get(
            f"{browser_vm_url}/health", timeout=aiohttp.ClientTimeout(total=3)
        ) as response:
            if response.status == 200:
                playwright_data = await response.json()
                context["playwright_state"] = {
                    "healthy": playwright_data.get("status") == "healthy",
                    "browser_connected": playwright_data.get(
                        "browser_connected", False
                    ),
                }
    except aiohttp.ClientError as e:
        logger.warning("HTTP error getting Playwright state: %s", e)
        context["playwright_state"] = {"error": str(e)}
    except Exception as e:
        logger.warning("Failed to get Playwright state: %s", e)
        context["playwright_state"] = {"error": str(e)}

    # Get VNC state using singleton HTTP client
    try:
        async with await http_client.get(
            f"{backend_url}/api/vnc-proxy/browser/status",
            timeout=aiohttp.ClientTimeout(total=3),
        ) as response:
            if response.status == 200:
                vnc_data = await response.json()
                context["vnc_state"] = {
                    "accessible": vnc_data.get("accessible", False),
                    "endpoint": vnc_data.get("endpoint"),
                }

                # Include recent observations (thread-safe)
                async with _vnc_observations_lock:
                    cache = vnc_observations.get("browser", {})
                    recent = list(cache.get("recent_activity", [])[-5:])
                context["vnc_state"]["recent_observations"] = recent
    except aiohttp.ClientError as e:
        logger.warning("HTTP error getting VNC state: %s", e)
        context["vnc_state"] = {"error": str(e)}
    except Exception as e:
        logger.warning("Failed to get VNC state: %s", e)
        context["vnc_state"] = {"error": str(e)}

    return context


# Observation recording endpoint (called by VNC proxy)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_vnc_observation",
    error_code_prefix="VNC_MCP",
)
@router.post("/observations/{vnc_type}")
async def record_vnc_observation(vnc_type: str, observation: Metadata):
    """
    Record VNC observation from the proxy

    This endpoint is called by the VNC WebSocket proxy to log observations
    for later retrieval by MCP tools
    """
    # Add timestamp
    observation["timestamp"] = datetime.now().isoformat()

    # Thread-safe update of observations
    async with _vnc_observations_lock:
        if vnc_type not in vnc_observations:
            raise HTTPException(status_code=404, detail=f"Unknown VNC type: {vnc_type}")

        # Append to recent activity (keep last 100)
        vnc_observations[vnc_type]["recent_activity"].append(observation)
        vnc_observations[vnc_type]["recent_activity"] = vnc_observations[vnc_type][
            "recent_activity"
        ][-100:]
        vnc_observations[vnc_type]["last_check"] = datetime.now()

    logger.debug(
        "Recorded VNC observation for %s: %s", vnc_type, observation.get("type")
    )

    return {"success": True, "recorded": True}
