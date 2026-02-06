# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.type_defs.common import JSONObject, Metadata
from constants.network_constants import NetworkConstants
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["browser_mcp", "mcp"])

# Performance optimization: O(1) lookup for allowed URL schemes (Issue #326)
ALLOWED_URL_SCHEMES = {"http", "https"}

# Security Configuration
BROWSER_VM_URL = (
    f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}"
)

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
request_counter = {"count": 0, "reset_time": datetime.now(timezone.utc)}
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
        now = datetime.now(timezone.utc)
        elapsed = (now - request_counter["reset_time"]).total_seconds()

        # Reset counter every minute (in-place modification for thread safety)
        if elapsed >= 60:
            request_counter["count"] = 0
            request_counter["reset_time"] = now

        if request_counter["count"] >= MAX_REQUESTS_PER_MINUTE:
            logger.warning(
                f"Rate limit exceeded: {request_counter['count']} requests/min"
            )
            return False

        request_counter["count"] += 1
        return True


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: JSONObject


# Request Models


class NavigateRequest(BaseModel):
    """Request model for browser navigation"""

    url: str = Field(..., description="URL to navigate to")
    wait_until: Optional[str] = Field(
        "load", description="Wait condition: 'load', 'domcontentloaded', 'networkidle'"
    )
    timeout: Optional[int] = Field(30000, description="Timeout in milliseconds")


class ClickRequest(BaseModel):
    """Request model for clicking elements"""

    selector: str = Field(..., description="CSS selector for element to click")
    timeout: Optional[int] = Field(5000, description="Timeout in milliseconds")


class FillRequest(BaseModel):
    """Request model for filling form fields"""

    selector: str = Field(..., description="CSS selector for input field")
    value: str = Field(..., description="Value to fill")
    timeout: Optional[int] = Field(5000, description="Timeout in milliseconds")


class ScreenshotRequest(BaseModel):
    """Request model for taking screenshots"""

    selector: Optional[str] = Field(
        None, description="CSS selector for element (full page if omitted)"
    )
    full_page: Optional[bool] = Field(False, description="Capture full scrollable page")


class EvaluateRequest(BaseModel):
    """Request model for executing JavaScript"""

    script: str = Field(..., description="JavaScript code to execute")


class WaitForSelectorRequest(BaseModel):
    """Request model for waiting for elements"""

    selector: str = Field(..., description="CSS selector to wait for")
    timeout: Optional[int] = Field(30000, description="Timeout in milliseconds")
    state: Optional[str] = Field(
        "visible", description="State: 'attached', 'detached', 'visible', 'hidden'"
    )


class GetTextRequest(BaseModel):
    """Request model for extracting text content"""

    selector: str = Field(..., description="CSS selector for element")


class GetAttributeRequest(BaseModel):
    """Request model for getting element attributes"""

    selector: str = Field(..., description="CSS selector for element")
    attribute: str = Field(..., description="Attribute name to retrieve")


class SelectRequest(BaseModel):
    """Request model for selecting dropdown options"""

    selector: str = Field(..., description="CSS selector for select element")
    value: str = Field(..., description="Value to select")


class HoverRequest(BaseModel):
    """Request model for hovering over elements"""

    selector: str = Field(..., description="CSS selector for element to hover")


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


def _get_browser_extraction_tools() -> List[MCPTool]:
    """
    Get MCP tools for browser extraction operations (screenshot, get_text, evaluate).

    Issue #281: Extracted from get_browser_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.

    Returns:
        List of extraction-related browser MCP tools
    """
    return [
        MCPTool(
            name="screenshot",
            description="Capture screenshot of page or specific element",
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": (
                            "CSS selector for element (full page if omitted)"
                        ),
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full scrollable page",
                        "default": False,
                    },
                },
            },
        ),
        MCPTool(
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
        ),
        MCPTool(
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
        ),
        MCPTool(
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
        ),
    ]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_browser_mcp_tools",
    error_code_prefix="BROWSER_MCP",
)
@router.get("/mcp/tools")
async def get_browser_mcp_tools() -> List[MCPTool]:
    """Get available MCP tools for browser automation operations"""
    # Issue #281: Use extracted helpers for tool definitions by category
    tools = []
    tools.extend(_get_browser_navigation_tools())
    tools.extend(_get_browser_interaction_tools())
    tools.extend(_get_browser_extraction_tools())
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
            detail=f"Browser VM unavailable: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="navigate_mcp",
    error_code_prefix="BROWSER_MCP",
)
@router.post("/mcp/navigate")
async def navigate_mcp(request: NavigateRequest) -> Metadata:
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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="click_mcp",
    error_code_prefix="BROWSER_MCP",
)
@router.post("/mcp/click")
async def click_mcp(request: ClickRequest) -> Metadata:
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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="fill_mcp",
    error_code_prefix="BROWSER_MCP",
)
@router.post("/mcp/fill")
async def fill_mcp(request: FillRequest) -> Metadata:
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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="screenshot_mcp",
    error_code_prefix="BROWSER_MCP",
)
@router.post("/mcp/screenshot")
async def screenshot_mcp(request: ScreenshotRequest) -> Metadata:
    """Capture screenshot of page or element"""
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    logger.info(
        f"Browser screenshot: selector={request.selector}, full_page={request.full_page}"
    )

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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="evaluate_mcp",
    error_code_prefix="BROWSER_MCP",
)
@router.post("/mcp/evaluate")
async def evaluate_mcp(request: EvaluateRequest) -> Metadata:
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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="wait_for_selector_mcp",
    error_code_prefix="BROWSER_MCP",
)
@router.post("/mcp/wait_for_selector")
async def wait_for_selector_mcp(request: WaitForSelectorRequest) -> Metadata:
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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_text_mcp",
    error_code_prefix="BROWSER_MCP",
)
@router.post("/mcp/get_text")
async def get_text_mcp(request: GetTextRequest) -> Metadata:
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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_attribute_mcp",
    error_code_prefix="BROWSER_MCP",
)
@router.post("/mcp/get_attribute")
async def get_attribute_mcp(request: GetAttributeRequest) -> Metadata:
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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="select_mcp",
    error_code_prefix="BROWSER_MCP",
)
@router.post("/mcp/select")
async def select_mcp(request: SelectRequest) -> Metadata:
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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="hover_mcp",
    error_code_prefix="BROWSER_MCP",
)
@router.post("/mcp/hover")
async def hover_mcp(request: HoverRequest) -> Metadata:
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
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_browser_mcp_status",
    error_code_prefix="BROWSER_MCP",
)
@router.get("/mcp/status")
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
        "tools_available": 10,
        "timestamp": datetime.now().isoformat(),
    }
