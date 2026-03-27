# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dynamic MCP tool dispatch service for agent runtime (#2513).

Bridges the MCP registry to the tool handler so that agents can call any
registered MCP tool without hardcoded routing in _dispatch_tool_call().

Architecture:
  _dispatch_tool_call() (tool_handler.py)
        |
        v
  MCPDispatcher.dispatch(tool_name, arguments)
        |
        v
  MCP bridge endpoint  (e.g. /api/filesystem/mcp/<tool_name>)

The dispatcher loads tool metadata from the registry on first use and
caches it locally.  Cache can be refreshed explicitly via refresh_tool_cache().
"""

import logging
from typing import Optional

import aiohttp
from constants.network_constants import NetworkConstants

from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)


class MCPDispatcher:
    """Routes unknown tool calls to registered MCP bridges via the registry.

    Caches tool metadata fetched from the registry so that repeated tool
    calls do not incur extra HTTP round-trips for discovery.
    """

    def __init__(self) -> None:
        """Initialize dispatcher with empty tool cache."""
        self._tool_cache: dict[str, dict] = {}
        self._cache_loaded = False

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    async def refresh_tool_cache(self) -> int:
        """Fetch all tools from the MCP registry and populate the local cache.

        Makes a single HTTP request to /api/mcp/tools which aggregates all
        bridges.  Returns the number of tools cached.
        """
        backend_url = (
            f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
        )
        try:
            http_client = get_http_client()
            async with await http_client.get(
                f"{backend_url}/api/mcp/tools",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status != 200:
                    logger.warning(
                        "MCPDispatcher: registry returned %s when refreshing tools",
                        response.status,
                    )
                    return 0
                data = await response.json()
                tools = data.get("tools", [])
                self._tool_cache = {tool["name"]: tool for tool in tools}
                self._cache_loaded = True
                logger.info(
                    "MCPDispatcher: cached %d tools from registry",
                    len(self._tool_cache),
                )
                return len(self._tool_cache)
        except aiohttp.ClientError as exc:
            logger.warning("MCPDispatcher: HTTP error refreshing tool cache: %s", exc)
            return 0
        except Exception as exc:
            logger.warning("MCPDispatcher: failed to refresh tool cache: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Tool lookup
    # ------------------------------------------------------------------

    def find_tool(self, tool_name: str) -> Optional[dict]:
        """Return the cached tool entry for tool_name, or None if not found."""
        return self._tool_cache.get(tool_name)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, tool_name: str, arguments: dict) -> dict:
        """Dispatch a tool call to its registered MCP bridge.

        Loads the tool cache on first call if it has not been populated yet.

        Args:
            tool_name: Tool name from the LLM tool call.
            arguments: Tool arguments dict.

        Returns:
            Dict with keys: success (bool), result (str | dict), bridge (str | None).
        """
        if not self._cache_loaded:
            await self.refresh_tool_cache()

        tool = self.find_tool(tool_name)
        if not tool:
            return {
                "success": False,
                "result": f"Unknown tool: {tool_name}",
                "bridge": None,
            }

        bridge = tool.get("bridge", "unknown")
        endpoint = tool.get("endpoint", "")
        return await self._call_bridge(tool_name, bridge, endpoint, arguments)

    async def _call_bridge(
        self, tool_name: str, bridge: str, endpoint: str, arguments: dict
    ) -> dict:
        """Execute the HTTP call to the MCP bridge endpoint.

        Args:
            tool_name: Name of the tool being called.
            bridge: Bridge identifier (for logging/result metadata).
            endpoint: Full URL path of the tool's bridge endpoint.
            arguments: Arguments to pass to the bridge.

        Returns:
            Dict with keys: success, result, bridge.
        """
        try:
            http_client = get_http_client()
            async with await http_client.post(
                endpoint,
                json={"arguments": arguments},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "result": result, "bridge": bridge}
                text = await response.text()
                logger.error(
                    "MCPDispatcher: bridge %s returned %s for tool %s: %s",
                    bridge,
                    response.status,
                    tool_name,
                    text[:200],
                )
                return {
                    "success": False,
                    "result": f"Bridge {bridge} returned {response.status}: {text[:200]}",
                    "bridge": bridge,
                }
        except aiohttp.ClientError as exc:
            logger.error(
                "MCPDispatcher: HTTP error calling %s via %s: %s",
                tool_name,
                bridge,
                exc,
            )
            return {
                "success": False,
                "result": f"Bridge call failed: {exc}",
                "bridge": bridge,
            }
        except Exception as exc:
            logger.error(
                "MCPDispatcher: unexpected error calling %s via %s: %s",
                tool_name,
                bridge,
                exc,
            )
            return {
                "success": False,
                "result": f"Bridge call failed: {exc}",
                "bridge": bridge,
            }

    # ------------------------------------------------------------------
    # Tool definition export
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> list[dict]:
        """Return tool definitions in LLM-injectable format.

        Each entry contains name, description (prefixed with bridge name),
        and parameters (from the tool's input_schema).

        Returns:
            List of tool definition dicts.
        """
        return [
            {
                "name": tool["name"],
                "description": f"[{tool['bridge']}] {tool['description']}",
                "parameters": tool.get("input_schema", {}),
            }
            for tool in self._tool_cache.values()
        ]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_dispatcher: Optional[MCPDispatcher] = None


def get_mcp_dispatcher() -> MCPDispatcher:
    """Return the singleton MCPDispatcher instance (created on first call)."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = MCPDispatcher()
    return _dispatcher
