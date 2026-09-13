# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared multi-server MCP aggregation: discovery, collision-prefixing, graceful skip.

Extracted from services/realtime_mcp_bridge.py (#7343/#7344) so the voice bridge
and the external MCP server bridge (#11542) consume one implementation instead
of two. A tool name that appears on exactly one server keeps its bare name; a
name that appears on two or more servers is prefixed "{server_id}__{name}" on
every server that exposes it, for deterministic collision resolution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, AsyncContextManager, Callable, Sequence

from autobot_shared.logging_manager import get_logger
from type_defs.mcp import MCPToolDefinition

logger = get_logger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# A client factory takes a server URI and returns an async-context-manager
# object exposing `discover_tools() -> list[MCPToolDefinition]` (MCPClient's shape).
ClientFactory = Callable[[str], AsyncContextManager[Any]]


def server_id_from_uri(uri: str) -> str:
    """Return a stable, lowercase slug for *uri* suitable as a name prefix."""
    slug = re.sub(r"^[a-z]+://", "", uri.lower())
    slug = slug.split("/")[0]
    return _SLUG_RE.sub("_", slug).strip("_") or "mcp"


@dataclass(frozen=True)
class ServerToolList:
    """Tools discovered from one reachable server."""

    server_id: str
    server_uri: str
    tools: list[MCPToolDefinition]


async def discover_tools_multi_server(
    server_uris: Sequence[str],
    client_factory: ClientFactory,
) -> list[ServerToolList]:
    """Discover tools from every server URI, skipping unreachable servers.

    Opens `client_factory(uri)` as an async context manager per server and
    calls `discover_tools()` on it. A server that raises on connect or
    discovery is logged and omitted — it never aborts the other servers.
    """
    results: list[ServerToolList] = []
    for uri in server_uris:
        sid = server_id_from_uri(uri)
        try:
            async with client_factory(uri) as client:
                tools = await client.discover_tools()
            results.append(ServerToolList(server_id=sid, server_uri=uri, tools=tools))
            logger.info("mcp_aggregation: discovered server=%s tools=%d", sid, len(tools))
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp_aggregation: skipping unreachable server %s: %s", uri, exc)
    return results


@dataclass(frozen=True)
class ResolvedTool:
    """One tool with its collision-resolved public name and routing origin."""

    public_name: str
    server_id: str
    server_uri: str
    original_name: str
    tool: MCPToolDefinition


def resolve_name_collisions(
    server_tool_lists: Sequence[ServerToolList],
    reserved_names: frozenset[str] = frozenset(),
) -> list[ResolvedTool]:
    """Prefix a tool's name with its server_id when 2+ servers expose that name.

    ``reserved_names`` (#16458 review) forces the same prefixing for a name
    that collides with something outside ``server_tool_lists`` entirely --
    the voice bridge (services/realtime_mcp_bridge.py) passes nothing, so its
    behaviour here is unchanged; the external MCP bridge (#11542) passes the
    internal tool registry's names, so an admin-configured external server
    cannot advertise a built-in tool's name and have calls to it silently
    routed there instead -- a name that looks internal but isn't must be
    visibly external, not merely happen to still resolve correctly today.
    """
    name_count: dict[str, int] = {}
    for stl in server_tool_lists:
        for tool in stl.tools:
            name_count[tool.name] = name_count.get(tool.name, 0) + 1

    resolved: list[ResolvedTool] = []
    for stl in server_tool_lists:
        for tool in stl.tools:
            needs_prefix = name_count[tool.name] > 1 or tool.name in reserved_names
            public_name = f"{stl.server_id}__{tool.name}" if needs_prefix else tool.name
            resolved.append(
                ResolvedTool(
                    public_name=public_name,
                    server_id=stl.server_id,
                    server_uri=stl.server_uri,
                    original_name=tool.name,
                    tool=tool,
                )
            )
    return resolved


async def discover_and_resolve(
    server_uris: Sequence[str],
    client_factory: ClientFactory,
    reserved_names: frozenset[str] = frozenset(),
) -> list[ResolvedTool]:
    """Convenience wrapper: discover across all servers, then resolve name collisions."""
    server_tool_lists = await discover_tools_multi_server(server_uris, client_factory)
    return resolve_name_collisions(server_tool_lists, reserved_names)
