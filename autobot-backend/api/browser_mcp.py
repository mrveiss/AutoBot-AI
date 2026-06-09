# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Browser Automation MCP Bridge
Exposes browser automation operations as MCP tools for LLM agents
Integrates with AutoBot's Browser VM (uses NetworkConstants.BROWSER_VM_IP) using Playwright

Provides comprehensive browser automation capabilities:
- Navigation (navigate, go_back, go_forward)
- Interaction (click, fill, select, hover)
- Capture (screenshot, get_text, get_attribute)
- Execution (evaluate JavaScript)
- Waiting (wait_for_selector)

Security Model:
- URL whitelist enforcement
- Script validation and sanitization
- Rate limiting for automation requests
- Comprehensive audit logging
- No persistent browser state between requests

Issue #49 - Additional MCP Bridges (Browser, HTTP, Database, Git)
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, Depends, HTTPException

from api.schemas_code import MCPTool
from api.schemas_system import (
    BrowserClickRequest,
    BrowserClickResponse,
    BrowserEvaluateRequest,
    BrowserEvaluateResponse,
    BrowserFillRequest,
    BrowserFillResponse,
    BrowserGetAttributeRequest,
    BrowserGetAttributeResponse,
    BrowserGetTextRequest,
    BrowserGetTextResponse,
    BrowserHoverRequest,
    BrowserHoverResponse,
    BrowserInterceptApiRequest,
    BrowserInterceptApiResponse,
    BrowserMcpStatusResponse,
    BrowserNavigateRequest,
    BrowserNavigateResponse,
    BrowserPageSnapshotRequest,
    BrowserPageSnapshotResponse,
    BrowserScreenshotRequest,
    BrowserScreenshotResponse,
    BrowserSelectRequest,
    BrowserSelectResponse,
    BrowserWaitForSelectorRequest,
    BrowserWaitForSelectorResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from constants.network_constants import NetworkConstants
from research_browser_manager import get_research_browser_manager
from services.mcp_bridge_manifest import MCPBridgeManifest
from services.web_pipeline.interceptor import XHRInterceptor
from services.web_pipeline.snapshot import AccessibilitySnapshot
from type_defs.common import Metadata

MANIFEST = MCPBridgeManifest(
    name="browser_mcp",
    version="1.0.0",
    description="Browser Automation - Secure Web Interaction via Playwright",
    features=["navigate", "click", "fill", "screenshot", "evaluate", "wait", "scraping"],
    endpoint="/api/browser/mcp/tools",
)

logger = get_logger(__name__)
router = APIRouter(
    tags=["browser_mcp", "mcp"],
    dependencies=[Depends(check_admin_permission)],
)

# Performance optimization: O(1) lookup for allowed URL schemes (Issue #326)
ALLOWED_URL_SCHEMES = {"http", "https"}

# Security Configuration
BROWSER_VM_URL = f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}"

# URL Whitelist - Only these domains are allowed
ALLOWED_URL_PATTERNS = [
    r"^https?://localhost",
    r"^https?://127\.0\.0\.1",
    r"^https?://172\.16\.168\.\d+",  # AutoBot VMs
    r"^https?://.*\.example\.com$",  # Example - add real domains
    r"^https?://github\.com",
    r"^https?://.*\.github\.com",
    r"^https?://.*\.githubusercontent\.com",
]

# Rate limiting: max requests per minute
MAX_REQUESTS_PER_MINUTE = 60
request_counter = {"count": 0, "reset_time": now_utc()}
_rate_limit_lock = asyncio.Lock()

# Blocked JavaScript patterns (security) - enhanced to prevent bypass vectors
BLOCKED_JS_PATTERNS = [
    r"eval\s*\(",
    r"Function\s*\(",
    r"document\.cookie",
    r"localStorage",
    r"sessionStorage",
    r"XMLHttpRequest",
    r"fetch\s*\(",
    r"window\.open",
    # Enhanced patterns to prevent bypass vectors
    r'\["eval"\]',  # Bracket notation: window["eval"]()
    r"\['eval'\]",  # Single quote bracket notation
    r"globalThis\.",  # Alternative global access
    r"document\.write",  # XSS vector
    r"\.innerHTML\s*=",  # DOM manipulation
    r"window\.location\s*=",  # Navigation hijacking
    r"window\[['\"]",  # Generic bracket access to window
    r"this\[['\"]eval",  # this["eval"] bypass
]


def is_url_allowed(url: str) -> bool:
    """
    Validate URL against whitelist patterns

    Security measures:
    - Pattern-based URL validation
    - Block potentially dangerous schemes
    - Prevent access to internal/private networks (except AutoBot VMs)
    """
    try:
        parsed = urlparse(url)

        # Block dangerous schemes
        if parsed.scheme not in ALLOWED_URL_SCHEMES:
            logger.warning("Blocked non-HTTP scheme: %s", parsed.scheme)
            return False

        # Check against whitelist patterns
        for pattern in ALLOWED_URL_PATTERNS:
            if re.match(pattern, url):
                return True

        logger.warning("URL not in whitelist: %s", url)
        return False

    except Exception as e:
        logger.error("URL validation error for %s: %s", url, e)
        return False


def is_script_safe(script: str) -> bool:
    """
    Validate JavaScript code for potentially dangerous patterns

    Security measures:
    - Block eval() and Function() constructors
    - Block cookie/storage access
    - Block network requests from scripts
    - Block window manipulation
    """
    try:
        for pattern in BLOCKED_JS_PATTERNS:
            if re.search(pattern, script, re.IGNORECASE):
                logger.warning("Blocked dangerous JavaScript pattern: %s", pattern)
                return False
        return True
    except Exception as e:
        logger.error("Script validation error: %s", e)
        return False


async def check_rate_limit() -> bool:
    """
    Enforce rate limiting for browser automation requests

    Returns True if request is allowed, False if rate limit exceeded

    Uses asyncio.Lock for thread safety in concurrent async environments
    """
    async with _rate_limit_lock:
        now = now_utc()
        elapsed = (now - request_counter["reset_time"]).total_seconds()

        # Reset counter every minute (in-place modification for thread safety)
        if elapsed >= 60:
            request_counter["count"] = 0
            request_counter["reset_time"] = now

        if request_counter["count"] >= MAX_REQUESTS_PER_MINUTE:
            logger.warning(f"Rate limit exceeded: {request_counter['count']} requests/min")
            return False

        request_counter["count"] += 1
        return True


def _get_browser_navigation_tools() -> List[MCPTool]:
    """
    Get MCP tools for browser navigation operations.

    Issue #281: Extracted from get_browser_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.

    Returns:
        List of navigation-related browser MCP tools
    """
    return [
        MCPTool(
            name="navigate",
            description="Navigate browser to specified URL with configurable wait conditions",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                        "description": "Wait condition",
                        "default": "load",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in milliseconds",
                        "default": 30000,
                    },
                },
                "required": ["url"],
            },
        ),
        MCPTool(
            name="wait_for_selector",
            description="Wait for element to appear or reach specified state",
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector to wait for",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in milliseconds",
                        "default": 30000,
                    },
                    "state": {
                        "type": "string",
                        "enum": ["attached", "detached", "visible", "hidden"],
                        "description": "Element state to wait for",
                        "default": "visible",
                    },
                },
                "required": ["selector"],
            },
        ),
    ]


def _create_click_tool() -> MCPTool:
    """
    Create MCP tool definition for clicking elements.

    Issue #620.
    """
    return MCPTool(
        name="click",
        description="Click on an element identified by CSS selector",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector for element",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds",
                    "default": 5000,
                },
            },
            "required": ["selector"],
        },
    )


def _create_fill_tool() -> MCPTool:
    """
    Create MCP tool definition for filling input fields.

    Issue #620.
    """
    return MCPTool(
        name="fill",
        description="Fill input field with specified value",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector for input field",
                },
                "value": {"type": "string", "description": "Value to fill"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds",
                    "default": 5000,
                },
            },
            "required": ["selector", "value"],
        },
    )


def _create_select_tool() -> MCPTool:
    """
    Create MCP tool definition for selecting dropdown options.

    Issue #620.
    """
    return MCPTool(
        name="select",
        description="Select option from dropdown/select element",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector for select element",
                },
                "value": {"type": "string", "description": "Value to select"},
            },
            "required": ["selector", "value"],
        },
    )


def _create_hover_tool() -> MCPTool:
    """
    Create MCP tool definition for hovering over elements.

    Issue #620.
    """
    return MCPTool(
        name="hover",
        description="Hover mouse over element",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector for element",
                }
            },
            "required": ["selector"],
        },
    )


def _get_browser_interaction_tools() -> List[MCPTool]:
    """
    Get MCP tools for browser interaction operations (click, fill, select, hover).

    Issue #281: Extracted from get_browser_mcp_tools to reduce function length.
    Issue #620: Further refactored to use individual tool creation helpers.

    Returns:
        List of interaction-related browser MCP tools
    """
    return [
        _create_click_tool(),
        _create_fill_tool(),
        _create_select_tool(),
        _create_hover_tool(),
    ]


def _create_screenshot_tool() -> MCPTool:
    """Helper for _get_browser_extraction_tools. Build screenshot MCPTool. Ref: #1088."""
    return MCPTool(
        name="screenshot",
        description="Capture screenshot of page or specific element",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector for element (full page if omitted)",
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Capture full scrollable page",
                    "default": False,
                },
            },
        },
    )


def _create_evaluate_tool() -> MCPTool:
    """Helper for _get_browser_extraction_tools. Build evaluate MCPTool. Ref: #1088."""
    return MCPTool(
        name="evaluate",
        description="Execute JavaScript code in browser context (with security restrictions)",
        input_schema={
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "JavaScript code to execute",
                }
            },
            "required": ["script"],
        },
    )


def _create_get_text_tool() -> MCPTool:
    """Helper for _get_browser_extraction_tools. Build get_text MCPTool. Ref: #1088."""
    return MCPTool(
        name="get_text",
        description="Extract text content from element",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector for element",
                }
            },
            "required": ["selector"],
        },
    )


def _create_get_attribute_tool() -> MCPTool:
    """Helper for _get_browser_extraction_tools. Build get_attribute MCPTool. Ref: #1088."""
    return MCPTool(
        name="get_attribute",
        description="Get attribute value from element",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector for element",
                },
                "attribute": {"type": "string", "description": "Attribute name"},
            },
            "required": ["selector", "attribute"],
        },
    )


def _get_browser_extraction_tools() -> List[MCPTool]:
    """Get MCP tools for browser extraction operations. Ref: #1088.

    Issue #281: Extracted from get_browser_mcp_tools to reduce function length.
    """
    return [
        _create_screenshot_tool(),
        _create_evaluate_tool(),
        _create_get_text_tool(),
        _create_get_attribute_tool(),
    ]


def _get_web_pipeline_tools() -> List[MCPTool]:
    """MCP tools that expose web-pipeline services (#5136 Phase 1, closes #5138)."""
    return [
        MCPTool(
            name="page_snapshot",
            description=(
                "Capture the ARIA accessibility tree of a research browser session. "
                "Returns an indented plain-text representation suitable for LLM consumption. "
                "Requires an active session_id from the research browser manager."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Research browser session ID",
                    }
                },
                "required": ["session_id"],
            },
        ),
        MCPTool(
            name="intercept_api",
            description=(
                "Collect XHR / fetch() requests captured since the last page navigation "
                "in a research browser session. The interception script is injected "
                "automatically on the first call per session. Returns a list of "
                "{url, method, response_status, response_body} dicts."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Research browser session ID",
                    }
                },
                "required": ["session_id"],
            },
        ),
    ]


@router.get("/mcp/tools", response_model=List[MCPTool])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_browser_mcp_tools",
    error_code_prefix="BROWSER_MCP",
)
async def get_browser_mcp_tools() -> List[MCPTool]:
    """Get available MCP tools for browser automation operations"""
    # Issue #281: Use extracted helpers for tool definitions by category
    tools = []
    tools.extend(_get_browser_navigation_tools())
    tools.extend(_get_browser_interaction_tools())
    tools.extend(_get_browser_extraction_tools())
    tools.extend(_get_web_pipeline_tools())  # #5136 Phase 1
    return tools


# Tool Implementations


async def send_to_browser_vm(action: str, params: Metadata) -> Metadata:
    """
    Send automation command to Browser VM

    This is the core communication layer with the Playwright server
    running on the Browser VM (NetworkConstants.BROWSER_VM_IP)
    """
    try:
        http_client = get_http_client()
        payload = {"action": action, "params": params}
        async with await http_client.post(
            f"{BROWSER_VM_URL}/automation",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise HTTPException(
                    status_code=502,
                    detail=f"Browser VM error: {response.status} - {error_text}",
                )
            try:
                return await response.json()
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON response from Browser VM: %s", e)
                raise HTTPException(
                    status_code=502,
                    detail="Invalid JSON response from Browser VM",
                )
    except asyncio.TimeoutError:
        logger.error("Browser VM request timed out after 60 seconds")
        raise HTTPException(
            status_code=504,
            detail="Browser VM request timed out",
        )
    except aiohttp.ClientError as e:
        logger.error("Browser VM connection error: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Browser VM unavailable",
        )


@router.post("/mcp/navigate", response_model=BrowserNavigateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="navigate_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def navigate_mcp(request: BrowserNavigateRequest) -> Metadata:
    """Navigate browser to URL with security validation"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    if not is_url_allowed(request.url):
        raise HTTPException(
            status_code=403,
            detail=f"URL not in whitelist: {request.url}",
        )

    logger.info("Browser navigation to: %s", request.url)

    result = await send_to_browser_vm(
        "navigate",
        {
            "url": request.url,
            "wait_until": request.wait_until,
            "timeout": request.timeout,
        },
    )

    return {
        "success": True,
        "action": "navigate",
        "url": request.url,
        "result": result,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/click", response_model=BrowserClickResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="click_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def click_mcp(request: BrowserClickRequest) -> Metadata:
    """Click on element by selector"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    logger.info("Browser click on: %s", request.selector)

    result = await send_to_browser_vm(
        "click",
        {"selector": request.selector, "timeout": request.timeout},
    )

    return {
        "success": True,
        "action": "click",
        "selector": request.selector,
        "result": result,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/fill", response_model=BrowserFillResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="fill_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def fill_mcp(request: BrowserFillRequest) -> Metadata:
    """Fill form field with value"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    logger.info("Browser fill: %s", request.selector)

    result = await send_to_browser_vm(
        "fill",
        {
            "selector": request.selector,
            "value": request.value,
            "timeout": request.timeout,
        },
    )

    return {
        "success": True,
        "action": "fill",
        "selector": request.selector,
        "value_length": len(request.value),
        "result": result,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/screenshot", response_model=BrowserScreenshotResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="screenshot_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def screenshot_mcp(request: BrowserScreenshotRequest) -> Metadata:
    """Capture screenshot of page or element"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    logger.info(f"Browser screenshot: selector={request.selector}, full_page={request.full_page}")

    result = await send_to_browser_vm(
        "screenshot",
        {"selector": request.selector, "full_page": request.full_page},
    )

    return {
        "success": True,
        "action": "screenshot",
        "selector": request.selector,
        "full_page": request.full_page,
        "base64_image": result.get("image"),
        "mime_type": "image/png",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/evaluate", response_model=BrowserEvaluateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="evaluate_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def evaluate_mcp(request: BrowserEvaluateRequest) -> Metadata:
    """Execute JavaScript with security validation"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    if not is_script_safe(request.script):
        raise HTTPException(
            status_code=403,
            detail="JavaScript contains blocked patterns (security restriction)",
        )

    logger.info("Browser evaluate: %s...", request.script[:100])

    result = await send_to_browser_vm("evaluate", {"script": request.script})

    return {
        "success": True,
        "action": "evaluate",
        "script_preview": request.script[:100],
        "result": result.get("result"),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/wait_for_selector", response_model=BrowserWaitForSelectorResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="wait_for_selector_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def wait_for_selector_mcp(request: BrowserWaitForSelectorRequest) -> Metadata:
    """Wait for element to reach specified state"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    logger.info("Browser wait_for_selector: %s (%s)", request.selector, request.state)

    result = await send_to_browser_vm(
        "wait_for_selector",
        {
            "selector": request.selector,
            "timeout": request.timeout,
            "state": request.state,
        },
    )

    return {
        "success": True,
        "action": "wait_for_selector",
        "selector": request.selector,
        "state": request.state,
        "result": result,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/get_text", response_model=BrowserGetTextResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_text_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def get_text_mcp(request: BrowserGetTextRequest) -> Metadata:
    """Extract text content from element"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    logger.info("Browser get_text: %s", request.selector)

    result = await send_to_browser_vm("get_text", {"selector": request.selector})

    return {
        "success": True,
        "action": "get_text",
        "selector": request.selector,
        "text": result.get("text"),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/get_attribute", response_model=BrowserGetAttributeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_attribute_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def get_attribute_mcp(request: BrowserGetAttributeRequest) -> Metadata:
    """Get attribute value from element"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    logger.info("Browser get_attribute: %s -> %s", request.selector, request.attribute)

    result = await send_to_browser_vm(
        "get_attribute",
        {"selector": request.selector, "attribute": request.attribute},
    )

    return {
        "success": True,
        "action": "get_attribute",
        "selector": request.selector,
        "attribute": request.attribute,
        "value": result.get("value"),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/select", response_model=BrowserSelectResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="select_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def select_mcp(request: BrowserSelectRequest) -> Metadata:
    """Select option from dropdown"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    logger.info("Browser select: %s -> %s", request.selector, request.value)

    result = await send_to_browser_vm(
        "select",
        {"selector": request.selector, "value": request.value},
    )

    return {
        "success": True,
        "action": "select",
        "selector": request.selector,
        "value": request.value,
        "result": result,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/hover", response_model=BrowserHoverResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="hover_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def hover_mcp(request: BrowserHoverRequest) -> Metadata:
    """Hover mouse over element"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    logger.info("Browser hover: %s", request.selector)

    result = await send_to_browser_vm("hover", {"selector": request.selector})

    return {
        "success": True,
        "action": "hover",
        "selector": request.selector,
        "result": result,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/mcp/status", response_model=BrowserMcpStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_browser_mcp_status",
    error_code_prefix="BROWSER_MCP",
)
async def get_browser_mcp_status() -> Metadata:
    """Get Browser MCP bridge status and statistics"""
    # Check Browser VM connectivity
    vm_status = "unavailable"
    try:
        http_client = get_http_client()
        async with await http_client.get(
            f"{BROWSER_VM_URL}/health",
            timeout=aiohttp.ClientTimeout(total=5),
        ) as response:
            if response.status == 200:
                vm_status = "healthy"
            else:
                vm_status = "degraded"
    except Exception:
        vm_status = "unavailable"

    # Thread-safe access to rate limit state
    async with _rate_limit_lock:
        current_count = request_counter["count"]
        reset_time_iso = request_counter["reset_time"].isoformat()

    return {
        "success": True,
        "bridge": "browser_mcp",
        "browser_vm": {
            "url": BROWSER_VM_URL,
            "status": vm_status,
        },
        "security": {
            "url_whitelist_patterns": len(ALLOWED_URL_PATTERNS),
            "blocked_js_patterns": len(BLOCKED_JS_PATTERNS),
            "rate_limit": f"{MAX_REQUESTS_PER_MINUTE} requests/minute",
        },
        "rate_limit_status": {
            "current_count": current_count,
            "max_per_minute": MAX_REQUESTS_PER_MINUTE,
            "reset_time": reset_time_iso,
        },
        "tools_available": 12,  # updated for page_snapshot + intercept_api (#5136)
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/page_snapshot", response_model=BrowserPageSnapshotResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="page_snapshot_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def page_snapshot_mcp(request: BrowserPageSnapshotRequest) -> Metadata:
    """Return the ARIA accessibility tree for a research browser session as plain text.

    Wires in AccessibilitySnapshot from services/web_pipeline/snapshot.py (#5136 Phase 1,
    closes #5138).
    """
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    manager = get_research_browser_manager()
    session = manager.get_session(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.page is None:
        raise HTTPException(status_code=400, detail="Browser page not initialized")

    logger.info("page_snapshot_mcp: session=%s", request.session_id)

    snap = AccessibilitySnapshot()
    tree = await snap.capture(session.page)
    accessibility_text = snap.to_text(tree) if tree is not None else ""

    return {
        "success": True,
        "action": "page_snapshot",
        "session_id": request.session_id,
        "accessibility_text": accessibility_text,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/mcp/intercept_api", response_model=BrowserInterceptApiResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="intercept_api_mcp",
    error_code_prefix="BROWSER_MCP",
)
async def intercept_api_mcp(request: BrowserInterceptApiRequest) -> Metadata:
    """Collect XHR/fetch requests captured in a research browser session.

    Wires in XHRInterceptor from services/web_pipeline/interceptor.py (#5136 Phase 1,
    closes #5138).  Injects the interception script if not already present, then
    collects whatever the page has captured so far.
    """
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    manager = get_research_browser_manager()
    session = manager.get_session(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.page is None:
        raise HTTPException(status_code=400, detail="Browser page not initialized")

    logger.info("intercept_api_mcp: session=%s", request.session_id)

    interceptor = XHRInterceptor()
    # Inject the shim (idempotent — safe to call if already injected)
    await session.page.add_init_script(interceptor.generate_intercept_script())
    captured = await interceptor.collect_results(session.page)

    return {
        "success": True,
        "action": "intercept_api",
        "session_id": request.session_id,
        "requests": [r.to_dict() for r in captured],
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
