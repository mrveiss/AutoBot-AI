# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""MCP server skill repo sync (Phase 3).

Connects to a remote MCP HTTP server, lists its tools,
and wraps each as a local skill package.
"""
import asyncio
import logging
from typing import Any, Dict, List

import aiohttp
from skills.models import SkillState
from skills.sync.base_sync import BaseRepoSync

logger = logging.getLogger(__name__)

_SKILL_MD_TEMPLATE = """\
---
name: {name}
version: 1.0.0
description: {description}
tools: {tools}
category: remote-mcp
---

# {name}

Remote MCP tool from {server_url}.

## Available Tools
{tool_list}
"""


class MCPClientSync(BaseRepoSync):
    """Sync skills from a remote MCP server by calling tools/list."""

    def __init__(self, server_url: str) -> None:
        """Initialize with the MCP HTTP server URL."""
        self.server_url = server_url

    async def discover(self) -> List[Dict[str, Any]]:
        """Connect to MCP server, list tools, wrap as skill packages."""
        try:
            tools = await self._fetch_tools()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error("MCP sync failed for %s: %s", self.server_url, exc)
            return []
        return [self._tool_to_package(tool) for tool in tools]

    async def _fetch_tools(self) -> List[Dict[str, Any]]:
        """Fetch tool list from remote MCP server via HTTP RPC."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.server_url}/rpc",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history, status=resp.status
                    )
                data = await resp.json()
                return data.get("result", {}).get("tools", [])

    def _tool_to_package(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a remote MCP tool descriptor to a local skill package dict."""
        name = tool.get("name", "unknown")
        desc = tool.get("description", "")
        # Escape braces so str.format() does not choke on tool names/descriptions
        # that contain literal '{' or '}' characters from MCP server responses.
        safe_name = name.replace("{", "{{").replace("}", "}}")
        safe_desc = desc.replace("{", "{{").replace("}", "}}")
        skill_md = _SKILL_MD_TEMPLATE.format(
            name=safe_name,
            description=safe_desc,
            tools=[safe_name],
            server_url=self.server_url,
            tool_list=f"- {safe_name}: {safe_desc}",
        )
        return {
            "name": name,
            "version": "1.0.0",
            "state": SkillState.INSTALLED,
            "skill_md": skill_md,
            "skill_py": None,
            "manifest": {"name": name, "tools": [name], "remote_mcp": self.server_url},
        }
