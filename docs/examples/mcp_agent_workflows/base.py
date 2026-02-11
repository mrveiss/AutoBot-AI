"""
Shared Base Module for MCP Agent Workflows

Provides reusable utilities for all MCP workflow examples:
- MCP tool calling with error handling
- Configuration management
- Logging utilities
- Common patterns

Issue: #48 - LangChain Agent Integration Examples for MCP Tools
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

# Import NetworkConstants to avoid hardcoding
try:
    from utils.network_constants import NetworkConstants

    AUTOBOT_BACKEND_URL = (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
    )
except ImportError:
    # Fallback for standalone usage - use environment variable
    AUTOBOT_BACKEND_URL = os.getenv("AUTOBOT_BACKEND_URL", "http://172.16.168.20:8001")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class MCPToolError(Exception):
    """Exception raised when MCP tool call fails"""

    def __init__(self, bridge: str, tool: str, status: int, message: str):
        self.bridge = bridge
        self.tool = tool
        self.status = status
        self.message = message
        super().__init__(f"MCP {bridge}/{tool} failed ({status}): {message}")


class MCPClient:
    """
    Reusable MCP client for calling AutoBot MCP tools.

    Features:
    - Configurable backend URL
    - Automatic retry with exponential backoff
    - Timeout handling
    - Comprehensive error handling
    - Request/response logging
    """

    def __init__(
        self,
        backend_url: Optional[str] = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        log_requests: bool = True,
    ):
        """
        Initialize MCP client.

        Args:
            backend_url: AutoBot backend URL (default: from NetworkConstants or env)
            timeout_seconds: Request timeout in seconds
            max_retries: Maximum retry attempts for server errors
            log_requests: Whether to log request/response details
        """
        self.backend_url = backend_url or AUTOBOT_BACKEND_URL
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.max_retries = max_retries
        self.log_requests = log_requests

        logger.info(f"MCPClient initialized with backend: {self.backend_url}")

    def _raise_client_error(self, bridge, tool, status, text):
        """Raise MCPToolError for non-retryable client error codes.

        Helper for call_tool (#825).
        """
        error_map = {
            400: f"Validation error: {text}",
            403: "Access denied",
            404: f"Tool not found: {tool}",
            422: f"Invalid request: {text}",
        }
        msg = error_map.get(status, f"Unexpected response: {text}")
        raise MCPToolError(bridge, tool, status, msg)

    async def _retry_or_raise(self, bridge, tool, attempt, label, msg):
        """Retry with backoff or raise MCPToolError on final attempt.

        Helper for call_tool (#825).
        """
        if attempt < self.max_retries - 1:
            wait_time = 2**attempt
            logger.warning(
                f"{label}, retrying in {wait_time}s... " f"(attempt {attempt + 1})"
            )
            await asyncio.sleep(wait_time)
            return
        raise MCPToolError(bridge, tool, 0, msg)

    async def _execute_request(self, url, params, bridge, tool, attempt):
        """Execute a single HTTP POST to the MCP tool endpoint.

        Helper for call_tool (#825).

        Returns:
            Parsed result dict on success, None if should retry.
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=params, timeout=self.timeout) as response:
                response_text = await response.text()

                if response.status == 200:
                    result = json.loads(response_text)
                    if self.log_requests:
                        logger.debug(f"  Response: {str(result)[:200]}...")
                    return result

                if response.status in (400, 403, 404, 422):
                    self._raise_client_error(
                        bridge, tool, response.status, response_text
                    )

                if response.status >= 500:
                    if attempt < self.max_retries - 1:
                        wait_time = 2**attempt
                        logger.warning(
                            f"Server error {response.status}, "
                            f"retrying in {wait_time}s... "
                            f"(attempt {attempt + 1})"
                        )
                        await asyncio.sleep(wait_time)
                        return None

                    raise MCPToolError(
                        bridge,
                        tool,
                        response.status,
                        f"Server error: {response_text}",
                    )

                raise MCPToolError(
                    bridge,
                    tool,
                    response.status,
                    f"Unexpected response: {response_text}",
                )

    async def call_tool(
        self, bridge_name: str, tool_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call an AutoBot MCP tool via HTTP API.

        Args:
            bridge_name: MCP bridge name
            tool_name: Tool name within the bridge
            params: Tool parameters (default: empty dict)

        Returns:
            Tool execution result as dictionary

        Raises:
            MCPToolError: When tool call fails after retries
        """
        bridge = bridge_name.replace("_mcp", "")
        url = f"{self.backend_url}/api/{bridge}/mcp/{tool_name}"
        params = params or {}

        if self.log_requests:
            logger.debug(f"Calling MCP tool: {bridge}/{tool_name}")
            logger.debug(f"  URL: {url}")
            logger.debug(f"  Params: {json.dumps(params)[:200]}")

        for attempt in range(self.max_retries):
            try:
                result = await self._execute_request(
                    url, params, bridge, tool_name, attempt
                )
                if result is not None:
                    return result
            except asyncio.TimeoutError:
                await self._retry_or_raise(
                    bridge,
                    tool_name,
                    attempt,
                    "Request timeout",
                    f"Timed out after {self.timeout.total}s",
                )
            except aiohttp.ClientError as e:
                await self._retry_or_raise(
                    bridge,
                    tool_name,
                    attempt,
                    "Connection error",
                    f"Connection error: {str(e)}",
                )
            except json.JSONDecodeError as e:
                raise MCPToolError(
                    bridge, tool_name, 0, f"Invalid JSON response: {str(e)}"
                )

        raise MCPToolError(bridge, tool_name, 0, "Max retries exceeded")

    async def call_tool_safe(
        self, bridge_name: str, tool_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call MCP tool with error handling - returns error dict instead of raising.

        Args:
            bridge_name: MCP bridge name
            tool_name: Tool name
            params: Tool parameters

        Returns:
            Tool result or error dictionary with 'error' and 'message' keys
        """
        try:
            return await self.call_tool(bridge_name, tool_name, params)
        except MCPToolError as e:
            return {"error": e.status, "message": str(e)}
        except Exception as e:
            return {"error": "unexpected", "message": str(e)}


# Create default global client instance
default_client = MCPClient()


async def call_mcp_tool(
    bridge_name: str, tool_name: str, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convenience function to call MCP tool using default client.

    Args:
        bridge_name: MCP bridge name (e.g., 'filesystem_mcp')
        tool_name: Tool name within the bridge
        params: Tool parameters

    Returns:
        Tool execution result
    """
    return await default_client.call_tool(bridge_name, tool_name, params)


async def call_mcp_tool_safe(
    bridge_name: str, tool_name: str, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convenience function to call MCP tool safely (returns error dict on failure).

    Args:
        bridge_name: MCP bridge name
        tool_name: Tool name
        params: Tool parameters

    Returns:
        Tool result or error dictionary
    """
    return await default_client.call_tool_safe(bridge_name, tool_name, params)


def format_timestamp() -> str:
    """Get current timestamp in standard format"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_iso_timestamp() -> str:
    """Get current timestamp in ISO format"""
    return datetime.now().isoformat()


def generate_session_id(prefix: str = "session") -> str:
    """Generate unique session ID"""
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


async def ensure_directory_exists(path: str) -> bool:
    """
    Ensure directory exists using filesystem MCP.

    Args:
        path: Directory path to create

    Returns:
        True if directory exists or was created, False on error
    """
    try:
        await call_mcp_tool("filesystem_mcp", "create_directory", {"path": path})
        return True
    except MCPToolError:
        # Directory may already exist
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {path}: {e}")
        return False


async def write_file_safe(path: str, content: str) -> bool:
    """
    Write file safely using filesystem MCP.

    Args:
        path: File path
        content: File content

    Returns:
        True on success, False on failure
    """
    try:
        await call_mcp_tool(
            "filesystem_mcp", "write_file", {"path": path, "content": content}
        )
        logger.info(f"File written: {path}")
        return True
    except MCPToolError as e:
        logger.error(f"Failed to write file {path}: {e}")
        return False


async def read_file_safe(path: str) -> Optional[str]:
    """
    Read file safely using filesystem MCP.

    Args:
        path: File path

    Returns:
        File content or None on failure
    """
    try:
        result = await call_mcp_tool("filesystem_mcp", "read_text_file", {"path": path})
        return result.get("content", "")
    except MCPToolError as e:
        logger.error(f"Failed to read file {path}: {e}")
        return None


class WorkflowResult:
    """Container for workflow execution results"""

    def __init__(self, name: str):
        self.name = name
        self.start_time = format_iso_timestamp()
        self.end_time: Optional[str] = None
        self.steps: List[Dict[str, Any]] = []
        self.success = True
        self.error: Optional[str] = None

    def add_step(
        self, step_name: str, status: str, data: Any = None, error: str = None
    ):
        """Add step result to workflow"""
        step = {
            "step": step_name,
            "status": status,
            "timestamp": format_iso_timestamp(),
        }
        if data is not None:
            step["data"] = data
        if error is not None:
            step["error"] = error
            self.success = False
        self.steps.append(step)

    def complete(self):
        """Mark workflow as complete"""
        self.end_time = format_iso_timestamp()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "workflow": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "success": self.success,
            "error": self.error,
            "steps": self.steps,
            "total_steps": len(self.steps),
            "successful_steps": sum(1 for s in self.steps if s["status"] == "success"),
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent, default=str)


__all__ = [
    "MCPClient",
    "MCPToolError",
    "call_mcp_tool",
    "call_mcp_tool_safe",
    "default_client",
    "AUTOBOT_BACKEND_URL",
    "logger",
    "format_timestamp",
    "format_iso_timestamp",
    "generate_session_id",
    "ensure_directory_exists",
    "write_file_safe",
    "read_file_safe",
    "WorkflowResult",
]
