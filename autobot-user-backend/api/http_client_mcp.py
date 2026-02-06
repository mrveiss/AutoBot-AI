# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
HTTP Client MCP Bridge
Exposes HTTP client operations as MCP tools for LLM agents
Enables secure HTTP requests to external APIs and services

Provides comprehensive HTTP capabilities:
- Standard methods (GET, POST, PUT, DELETE, PATCH)
- Custom headers support
- JSON and form data handling
- Response parsing and validation
- Timeout management

Security Model:
- Domain whitelist enforcement (configurable)
- Header validation (block sensitive headers)
- Request size limits
- Rate limiting for API requests
- Comprehensive audit logging
- SSL/TLS verification

Issue #49 - Additional MCP Bridges (Browser, HTTP, Database, Git)
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.type_defs.common import JSONObject, Metadata
from constants.network_constants import NetworkConstants
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.http_client import get_http_client
from utils.template_loader import load_mcp_tools, mcp_tools_exist

logger = logging.getLogger(__name__)
router = APIRouter(tags=["http_client_mcp", "mcp"])

# Performance optimization: O(1) lookup for allowed HTTP schemes (Issue #326)
ALLOWED_HTTP_SCHEMES = {"http", "https"}

# Issue #380: Module-level tuple for URL scheme validation
_VALID_URL_SCHEMES = ("http://", "https://")

# Security Configuration

# Domain whitelist - configurable list of allowed domains
# Note: Subdomains must be explicitly listed for security
ALLOWED_DOMAINS = [
    # Local development
    NetworkConstants.LOCALHOST_NAME,
    NetworkConstants.LOCALHOST_IP,
    # AutoBot infrastructure
    NetworkConstants.MAIN_MACHINE_IP,  # Main machine
    NetworkConstants.FRONTEND_VM_IP,  # Frontend VM
    NetworkConstants.NPU_WORKER_VM_IP,  # NPU Worker VM
    NetworkConstants.REDIS_VM_IP,  # Redis VM
    NetworkConstants.AI_STACK_VM_IP,  # AI Stack VM
    NetworkConstants.BROWSER_VM_IP,  # Browser VM
    # Common APIs (extend as needed)
    "api.github.com",
    "raw.githubusercontent.com",
    "httpbin.org",  # Testing
    "jsonplaceholder.typicode.com",  # Testing
]

# Explicitly allowed parent domains for subdomain matching
# Only these specific root domains allow subdomain access
ALLOWED_PARENT_DOMAINS = [
    "github.com",  # Allows *.github.com
    "githubusercontent.com",  # Allows *.githubusercontent.com
]

# Headers that should never be sent (security risk)
BLOCKED_HEADERS = [
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-csrf-token",
    "x-xsrf-token",
]

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 120
request_counter = {"count": 0, "reset_time": datetime.now(timezone.utc)}
_rate_limit_lock = asyncio.Lock()

# Request limits
MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_RESPONSE_SIZE = 50 * 1024 * 1024  # 50 MB
DEFAULT_TIMEOUT = 30  # seconds
MAX_TIMEOUT = 120  # seconds


def _try_parse_json(body: Optional[str]) -> Optional[JSONObject]:
    """Attempt to parse body as JSON. (Issue #315 - extracted to reduce nesting)"""
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        logger.debug("Response body is not JSON, keeping as text")
        return None


def _build_request_kwargs(
    url: str,
    headers: Dict[str, str],
    timeout: int,
    params: Optional[Dict[str, str]] = None,
    json_body: Optional[JSONObject] = None,
    form_data: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Build request kwargs dictionary for aiohttp session.request.

    Issue #665: Extracted from execute_http_request to reduce function length.

    Args:
        url: Target URL
        headers: Request headers
        timeout: Timeout in seconds
        params: Optional query parameters
        json_body: Optional JSON body
        form_data: Optional form data

    Returns:
        Dictionary of kwargs for session.request
    """
    request_kwargs = {
        "url": url,
        "headers": headers,
        "timeout": aiohttp.ClientTimeout(total=timeout),
        "ssl": True,  # Enforce SSL verification
    }

    if params:
        request_kwargs["params"] = params
    if json_body:
        request_kwargs["json"] = json_body
    if form_data:
        request_kwargs["data"] = form_data

    return request_kwargs


def _build_http_response(
    response,
    method: str,
    body: Optional[str],
    json_response: Optional[JSONObject],
) -> JSONObject:
    """
    Build standardized HTTP response dictionary.

    Issue #665: Extracted from execute_http_request to reduce function length.

    Args:
        response: aiohttp response object
        method: HTTP method used
        body: Response body text
        json_response: Parsed JSON body (if applicable)

    Returns:
        Standardized response dictionary
    """
    return {
        "success": True,
        "status_code": response.status,
        "headers": dict(response.headers),
        "body": json_response if json_response else body,
        "is_json": json_response is not None,
        "url": str(response.url),
        "method": method,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _read_response_body_chunked(response, chunk_size: int = 8192) -> str:
    """Read response body in chunks with size limit enforcement. (Issue #315 - extracted)"""
    chunks = []
    total_size = 0

    async for chunk in response.content.iter_chunked(chunk_size):
        total_size += len(chunk)
        if total_size > MAX_RESPONSE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Response exceeded size limit during streaming:"
                    f"{total_size} bytes (max: {MAX_RESPONSE_SIZE})"
                ),
            )
        chunks.append(chunk)

    # Decode response body
    body_bytes = b"".join(chunks)
    try:
        return body_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return body_bytes.decode("latin-1")


def is_domain_allowed(url: str) -> bool:
    """
    Validate URL domain against whitelist

    Security measures:
    - Extract and validate domain
    - Check against allowed list
    - Block private/internal networks (except AutoBot VMs)
    """
    try:
        parsed = urlparse(url)

        # Require HTTP/HTTPS
        if parsed.scheme not in ALLOWED_HTTP_SCHEMES:
            logger.warning("Blocked non-HTTP scheme: %s", parsed.scheme)
            return False

        # Get domain (hostname)
        domain = parsed.hostname
        if not domain:
            logger.warning("Could not parse domain from URL: %s", url)
            return False

        # Check exact match
        if domain in ALLOWED_DOMAINS:
            return True

        # Check subdomain match ONLY for explicitly allowed parent domains
        # This prevents overly permissive subdomain matching (security fix)
        for parent_domain in ALLOWED_PARENT_DOMAINS:
            if domain == parent_domain or domain.endswith(f".{parent_domain}"):
                return True

        logger.warning("Domain not in whitelist: %s", domain)
        return False

    except Exception as e:
        logger.error("Domain validation error for %s: %s", url, e)
        return False


def validate_headers(headers: Dict[str, str]) -> bool:
    """
    Validate request headers for security

    Security measures:
    - Block sensitive authentication headers
    - Block cookie manipulation
    - Prevent CSRF token exposure
    """
    if not headers:
        return True

    for key in headers:
        if key.lower() in BLOCKED_HEADERS:
            logger.warning("Blocked sensitive header: %s", key)
            return False

    return True


async def check_rate_limit() -> bool:
    """
    Enforce rate limiting for HTTP requests

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


# Pydantic Models


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: JSONObject


class HTTPRequestBase(BaseModel):
    """Base model for HTTP requests"""

    url: str = Field(..., description="Target URL for the request")
    headers: Optional[Dict[str, str]] = Field(
        default=None, description="Optional HTTP headers"
    )
    timeout: Optional[int] = Field(
        default=DEFAULT_TIMEOUT,
        ge=1,
        le=MAX_TIMEOUT,
        description=f"Request timeout in seconds (1-{MAX_TIMEOUT})",
    )

    @field_validator("url")
    @classmethod
    def validate_url_format(cls, v):
        """Ensure URL is properly formatted"""
        if not v.startswith(_VALID_URL_SCHEMES):  # Issue #380
            raise ValueError("URL must start with http:// or https://")
        return v


class HTTPGetRequest(HTTPRequestBase):
    """GET request model"""

    params: Optional[Dict[str, str]] = Field(
        default=None, description="Query parameters"
    )


class HTTPPostRequest(HTTPRequestBase):
    """POST request model"""

    json_body: Optional[JSONObject] = Field(
        default=None, description="JSON request body"
    )
    form_data: Optional[Dict[str, str]] = Field(
        default=None, description="Form data (mutually exclusive with json_body)"
    )


class HTTPPutRequest(HTTPRequestBase):
    """PUT request model"""

    json_body: Optional[JSONObject] = Field(
        default=None, description="JSON request body"
    )


class HTTPPatchRequest(HTTPRequestBase):
    """PATCH request model"""

    json_body: Optional[JSONObject] = Field(
        default=None, description="JSON request body for partial update"
    )


class HTTPDeleteRequest(HTTPRequestBase):
    """DELETE request model"""


class HTTPHeadRequest(HTTPRequestBase):
    """HEAD request model"""


# MCP Tool Definitions


def _get_http_read_tools() -> List[MCPTool]:
    """
    Get MCP tools for HTTP read operations (GET, HEAD).

    Issue #281: Extracted from get_http_client_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.

    Returns:
        List of MCPTool definitions for read operations
    """
    return [
        MCPTool(
            name="http_get",
            description=(
                "Perform HTTP GET request to retrieve data from a URL. Supports query parameters and"
                "custom headers. Rate limited to 120 requests/minute."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Target URL (must be in allowed domains)",
                    },
                    "headers": {
                        "type": "object",
                        "description": (
                            "Optional HTTP headers (sensitive headers blocked)"
                        ),
                        "additionalProperties": {"type": "string"},
                    },
                    "params": {
                        "type": "object",
                        "description": "Optional query parameters",
                        "additionalProperties": {"type": "string"},
                    },
                    "timeout": {
                        "type": "integer",
                        "description": (
                            f"Request timeout in seconds (default: {DEFAULT_TIMEOUT}, max: {MAX_TIMEOUT})"
                        ),
                        "minimum": 1,
                        "maximum": MAX_TIMEOUT,
                    },
                },
                "required": ["url"],
            },
        ),
        MCPTool(
            name="http_head",
            description=(
                "Perform HTTP HEAD request to retrieve headers only (no body). Useful for"
                "checking resource existence or metadata."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Target URL to check",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers",
                        "additionalProperties": {"type": "string"},
                    },
                    "timeout": {
                        "type": "integer",
                        "description": f"Request timeout (default: {DEFAULT_TIMEOUT}s)",
                    },
                },
                "required": ["url"],
            },
        ),
    ]


def _build_url_property() -> dict:
    """Build common URL property schema. Issue #484: Extracted for DRY."""
    return {"type": "string", "description": "Target URL (must be in allowed domains)"}


def _build_headers_property() -> dict:
    """Build common headers property schema. Issue #484: Extracted for DRY."""
    return {
        "type": "object",
        "description": "Optional HTTP headers",
        "additionalProperties": {"type": "string"},
    }


def _build_timeout_property() -> dict:
    """Build common timeout property schema. Issue #484: Extracted for DRY."""
    return {
        "type": "integer",
        "description": f"Request timeout (default: {DEFAULT_TIMEOUT}s)",
        "minimum": 1,
        "maximum": MAX_TIMEOUT,
    }


def _build_json_body_property(desc: str = "JSON request body") -> dict:
    """Build JSON body property schema. Issue #484: Extracted for DRY."""
    return {"type": "object", "description": desc}


def _get_http_post_tool() -> MCPTool:
    """Build HTTP POST tool definition. Issue #484: Extracted from _get_http_write_tools."""
    return MCPTool(
        name="http_post",
        description=(
            "Perform HTTP POST request to send data to a URL. "
            "Supports JSON body or form data. Rate limited to 120 requests/minute."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": _build_url_property(),
                "headers": _build_headers_property(),
                "json_body": _build_json_body_property(),
                "form_data": {
                    "type": "object",
                    "description": "Form data (mutually exclusive with json_body)",
                    "additionalProperties": {"type": "string"},
                },
                "timeout": _build_timeout_property(),
            },
            "required": ["url"],
        },
    )


def _get_http_put_tool() -> MCPTool:
    """Build HTTP PUT tool definition. Issue #484: Extracted from _get_http_write_tools."""
    return MCPTool(
        name="http_put",
        description=(
            "Perform HTTP PUT request to update/replace resource. "
            "Typically used for complete resource replacement. Rate limited."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": _build_url_property(),
                "headers": _build_headers_property(),
                "json_body": _build_json_body_property(
                    "JSON request body for replacement"
                ),
                "timeout": _build_timeout_property(),
            },
            "required": ["url"],
        },
    )


def _get_http_patch_tool() -> MCPTool:
    """Build HTTP PATCH tool definition. Issue #484: Extracted from _get_http_write_tools."""
    return MCPTool(
        name="http_patch",
        description=(
            "Perform HTTP PATCH request for partial resource update. "
            "More efficient than PUT for small changes. Rate limited."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": _build_url_property(),
                "headers": _build_headers_property(),
                "json_body": _build_json_body_property(
                    "JSON body with fields to update"
                ),
                "timeout": _build_timeout_property(),
            },
            "required": ["url"],
        },
    )


def _get_http_delete_tool() -> MCPTool:
    """Build HTTP DELETE tool definition. Issue #484: Extracted from _get_http_write_tools."""
    return MCPTool(
        name="http_delete",
        description=(
            "Perform HTTP DELETE request to remove a resource. "
            "Use with caution as this is destructive. Rate limited."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL of resource to delete",
                },
                "headers": _build_headers_property(),
                "timeout": _build_timeout_property(),
            },
            "required": ["url"],
        },
    )


def _get_http_write_tools() -> List[MCPTool]:
    """
    Get MCP tools for HTTP write operations (POST, PUT, PATCH, DELETE).

    Issue #281: Extracted from get_http_client_mcp_tools to reduce function length.
    Issue #484: Further refactored - each tool definition extracted to helper function.

    Returns:
        List of MCPTool definitions for write operations
    """
    return [
        _get_http_post_tool(),
        _get_http_put_tool(),
        _get_http_patch_tool(),
        _get_http_delete_tool(),
    ]


def _load_tools_from_yaml() -> List[MCPTool]:
    """
    Load MCP tools from YAML file with placeholder substitution.

    Issue #515: Externalized MCP tool definitions to data/mcp_tools/http_client_tools.yaml

    Returns:
        List of MCPTool objects loaded from YAML
    """
    config = {
        "DEFAULT_TIMEOUT": DEFAULT_TIMEOUT,
        "MAX_TIMEOUT": MAX_TIMEOUT,
    }

    tool_dicts = load_mcp_tools("http_client_tools", config=config)
    return [MCPTool(**tool) for tool in tool_dicts]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_http_client_mcp_tools",
    error_code_prefix="HTTP_MCP",
)
@router.get("/mcp/tools")
async def get_http_client_mcp_tools() -> List[MCPTool]:
    """
    Return all available HTTP Client MCP tools

    This endpoint follows the MCP specification for tool discovery.
    Issue #515: Tools now loaded from YAML with Python fallback.
    """
    # Issue #515: Try loading from YAML first, fallback to Python definitions
    if mcp_tools_exist("http_client_tools"):
        try:
            return _load_tools_from_yaml()
        except Exception as e:
            logger.warning("Failed to load MCP tools from YAML, using fallback: %s", e)

    # Issue #281: Fallback to extracted helpers for tool definitions by category
    tools = []
    tools.extend(_get_http_read_tools())
    tools.extend(_get_http_write_tools())
    return tools


# Tool Implementations


async def execute_http_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    json_body: Optional[JSONObject] = None,
    form_data: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> JSONObject:
    """
    Execute HTTP request with security controls.

    Issue #665: Refactored to use _build_request_kwargs and _build_http_response helpers.

    This is the core HTTP execution layer with:
    - Timeout management
    - Response size limits
    - Comprehensive error handling
    """
    try:
        # Prepare headers with default User-Agent
        request_headers = headers or {}
        if "User-Agent" not in request_headers:
            request_headers["User-Agent"] = "AutoBot-HTTP-Client/1.0"

        # Build request kwargs (Issue #665: uses extracted helper)
        http_client = get_http_client()
        session = await http_client.get_session()
        request_kwargs = _build_request_kwargs(
            url, request_headers, timeout, params, json_body, form_data
        )

        # Execute the request
        async with session.request(method, **request_kwargs) as response:
            # Check response size before reading (if Content-Length provided)
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_RESPONSE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"Response too large: {content_length} bytes (max: {MAX_RESPONSE_SIZE})",
                )

            # Read response body (Issue #315 - uses helper)
            body = (
                None
                if method.upper() == "HEAD"
                else await _read_response_body_chunked(response)
            )
            json_response = _try_parse_json(body)

            # Build response (Issue #665: uses extracted helper)
            return _build_http_response(response, method, body, json_response)

    except asyncio.TimeoutError:
        logger.error("HTTP request timed out after %s seconds: %s", timeout, url)
        raise HTTPException(
            status_code=504, detail=f"Request timed out after {timeout} seconds"
        )
    except aiohttp.ClientError as e:
        logger.error("HTTP client error: %s", e)
        raise HTTPException(status_code=502, detail=f"HTTP request failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="http_get_mcp",
    error_code_prefix="HTTP_CLIENT_MCP",
)
@router.post("/mcp/get")
async def http_get_mcp(request: HTTPGetRequest) -> JSONObject:
    """
    Execute HTTP GET request

    Security controls:
    - Domain whitelist validation
    - Header filtering
    - Rate limiting
    - Timeout enforcement
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_domain_allowed(request.url):
        raise HTTPException(status_code=403, detail="Domain not in allowed whitelist")

    if request.headers and not validate_headers(request.headers):
        raise HTTPException(status_code=400, detail="Request contains blocked headers")

    # Log the operation
    logger.info("HTTP GET request: %s", request.url)

    # Execute request
    result = await execute_http_request(
        method="GET",
        url=request.url,
        headers=request.headers,
        params=request.params,
        timeout=request.timeout or DEFAULT_TIMEOUT,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="http_post_mcp",
    error_code_prefix="HTTP_CLIENT_MCP",
)
@router.post("/mcp/post")
async def http_post_mcp(request: HTTPPostRequest) -> JSONObject:
    """
    Execute HTTP POST request

    Security controls:
    - Domain whitelist validation
    - Header filtering
    - Request body size validation
    - Rate limiting
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_domain_allowed(request.url):
        raise HTTPException(status_code=403, detail="Domain not in allowed whitelist")

    if request.headers and not validate_headers(request.headers):
        raise HTTPException(status_code=400, detail="Request contains blocked headers")

    # Validate mutual exclusivity
    if request.json_body and request.form_data:
        raise HTTPException(
            status_code=400,
            detail="Cannot specify both json_body and form_data",
        )

    # Check body size
    if request.json_body:
        body_size = len(json.dumps(request.json_body).encode("utf-8"))
        if body_size > MAX_REQUEST_BODY_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Request body too large: {body_size} bytes (max: {MAX_REQUEST_BODY_SIZE})",
            )

    # Log the operation
    logger.info("HTTP POST request: %s", request.url)

    # Execute request
    result = await execute_http_request(
        method="POST",
        url=request.url,
        headers=request.headers,
        json_body=request.json_body,
        form_data=request.form_data,
        timeout=request.timeout or DEFAULT_TIMEOUT,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="http_put_mcp",
    error_code_prefix="HTTP_CLIENT_MCP",
)
@router.post("/mcp/put")
async def http_put_mcp(request: HTTPPutRequest) -> JSONObject:
    """
    Execute HTTP PUT request

    Security controls:
    - Domain whitelist validation
    - Header filtering
    - Request body size validation
    - Rate limiting
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_domain_allowed(request.url):
        raise HTTPException(status_code=403, detail="Domain not in allowed whitelist")

    if request.headers and not validate_headers(request.headers):
        raise HTTPException(status_code=400, detail="Request contains blocked headers")

    # Check body size
    if request.json_body:
        body_size = len(json.dumps(request.json_body).encode("utf-8"))
        if body_size > MAX_REQUEST_BODY_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Request body too large: {body_size} bytes",
            )

    # Log the operation
    logger.info("HTTP PUT request: %s", request.url)

    # Execute request
    result = await execute_http_request(
        method="PUT",
        url=request.url,
        headers=request.headers,
        json_body=request.json_body,
        timeout=request.timeout or DEFAULT_TIMEOUT,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="http_patch_mcp",
    error_code_prefix="HTTP_CLIENT_MCP",
)
@router.post("/mcp/patch")
async def http_patch_mcp(request: HTTPPatchRequest) -> JSONObject:
    """
    Execute HTTP PATCH request

    Security controls:
    - Domain whitelist validation
    - Header filtering
    - Request body size validation
    - Rate limiting
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_domain_allowed(request.url):
        raise HTTPException(status_code=403, detail="Domain not in allowed whitelist")

    if request.headers and not validate_headers(request.headers):
        raise HTTPException(status_code=400, detail="Request contains blocked headers")

    # Check body size
    if request.json_body:
        body_size = len(json.dumps(request.json_body).encode("utf-8"))
        if body_size > MAX_REQUEST_BODY_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Request body too large: {body_size} bytes",
            )

    # Log the operation
    logger.info("HTTP PATCH request: %s", request.url)

    # Execute request
    result = await execute_http_request(
        method="PATCH",
        url=request.url,
        headers=request.headers,
        json_body=request.json_body,
        timeout=request.timeout or DEFAULT_TIMEOUT,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="http_delete_mcp",
    error_code_prefix="HTTP_CLIENT_MCP",
)
@router.post("/mcp/delete")
async def http_delete_mcp(request: HTTPDeleteRequest) -> JSONObject:
    """
    Execute HTTP DELETE request

    Security controls:
    - Domain whitelist validation
    - Header filtering
    - Rate limiting
    - Warning log for destructive operation
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_domain_allowed(request.url):
        raise HTTPException(status_code=403, detail="Domain not in allowed whitelist")

    if request.headers and not validate_headers(request.headers):
        raise HTTPException(status_code=400, detail="Request contains blocked headers")

    # Log the operation with warning (destructive)
    logger.warning("HTTP DELETE request (destructive): %s", request.url)

    # Execute request
    result = await execute_http_request(
        method="DELETE",
        url=request.url,
        headers=request.headers,
        timeout=request.timeout or DEFAULT_TIMEOUT,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="http_head_mcp",
    error_code_prefix="HTTP_CLIENT_MCP",
)
@router.post("/mcp/head")
async def http_head_mcp(request: HTTPHeadRequest) -> JSONObject:
    """
    Execute HTTP HEAD request

    Returns headers only (no body). Useful for:
    - Checking if resource exists
    - Getting content-length without downloading
    - Retrieving metadata
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_domain_allowed(request.url):
        raise HTTPException(status_code=403, detail="Domain not in allowed whitelist")

    if request.headers and not validate_headers(request.headers):
        raise HTTPException(status_code=400, detail="Request contains blocked headers")

    # Log the operation
    logger.info("HTTP HEAD request: %s", request.url)

    # Execute request
    result = await execute_http_request(
        method="HEAD",
        url=request.url,
        headers=request.headers,
        timeout=request.timeout or DEFAULT_TIMEOUT,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_http_client_mcp_status",
    error_code_prefix="HTTP_MCP",
)
@router.get("/mcp/status")
async def get_http_client_mcp_status() -> Metadata:
    """
    Get HTTP Client MCP service status

    Returns:
    - Service health
    - Rate limit status
    - Configuration info
    """

    async with _rate_limit_lock:
        current_rate = request_counter["count"]
        time_until_reset = max(
            0,
            60
            - (
                datetime.now(timezone.utc) - request_counter["reset_time"]
            ).total_seconds(),
        )

    return {
        "status": "operational",
        "service": "http_client_mcp",
        "rate_limit": {
            "current": current_rate,
            "max": MAX_REQUESTS_PER_MINUTE,
            "reset_in_seconds": round(time_until_reset, 1),
        },
        "configuration": {
            "allowed_domains_count": len(ALLOWED_DOMAINS),
            "blocked_headers_count": len(BLOCKED_HEADERS),
            "max_request_body_size_mb": MAX_REQUEST_BODY_SIZE / (1024 * 1024),
            "max_response_size_mb": MAX_RESPONSE_SIZE / (1024 * 1024),
            "default_timeout_seconds": DEFAULT_TIMEOUT,
            "max_timeout_seconds": MAX_TIMEOUT,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
