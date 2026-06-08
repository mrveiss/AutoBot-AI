# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""MCP server skill repo sync (Phase 3).

Connects to a remote MCP server (stdio, SSE, or HTTP), lists its tools,
and wraps each as a local skill package.  Delegates to :class:`MCPClient`
for transport-agnostic communication (#3103).
"""

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from skills.models import SkillState
from skills.sync.base_sync import BaseRepoSync
from skills.sync.mcp_client import MCPClient

logger = get_logger(__name__)

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
    """Sync skills from a remote MCP server by calling tools/list.

    Supports all MCP transports (stdio, SSE, HTTP) via :class:`MCPClient`.
    """

    def __init__(self, server_url: str) -> None:
        """Initialize with the MCP server URI.

        Args:
            server_url: Any URI accepted by :func:`create_transport` --
                ``http://``, ``https://``, ``sse://``, or ``stdio://``.
        """
        self.server_url = server_url

    async def discover(self) -> List[Dict[str, Any]]:
        """Connect to MCP server, list tools, wrap as skill packages."""
        try:
            async with MCPClient(self.server_url) as client:
                tools = await client.discover_tools()
        except Exception:
            logger.exception("MCP sync failed for %s", self.server_url)
            return []
        return [self._tool_to_package(tool) for tool in tools]

    def _tool_to_package(self, tool: Any) -> Dict[str, Any]:
        """Convert an MCPToolDefinition to a local skill package dict."""
        name = getattr(tool, "name", "unknown")
        desc = getattr(tool, "description", "")
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
