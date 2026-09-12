# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat-tool bridge for admin-configured external MCP servers (#11542).

Mirrors services/realtime_mcp_bridge.py's shape (discover → collision-prefix
→ route calls) but for chat tools rather than OpenAI Realtime voice tools,
and sourcing its server list from services.mcp_external_servers' admin CRUD
store instead of a static config env var. Both bridges share the actual
discovery/collision/skip logic via services.mcp_aggregation — this module
adds only what differs: loading *enabled* servers from the store, resolving
each server's credential into extra_headers, and the egress guard.

Not yet wired into services/mcp_dispatch.py's existing internal-bridge
routing (MCPDispatcher) — see the PR body for the open design question on
whether external servers should route through that RBAC-gated dispatch path
or stay a parallel bridge like this one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from knowledge.connectors.base import instance_host_egress
from services.mcp_aggregation import discover_and_resolve
from services.mcp_external_servers import MCPServerConfig, get_mcp_external_server_store
from services.mcp_server_credentials import resolve_extra_headers_for_server
from type_defs.mcp import MCPToolDefinition

logger = get_logger(__name__)


@dataclass
class ExternalToolCallResult:
    """Result of routing one chat tool call to an external MCP server."""

    success: bool
    result: Any = None
    error: str | None = None


@dataclass
class _ExternalToolEntry:
    """Maps a public (possibly-prefixed) tool name back to its server and connection settings."""

    server_uri: str
    original_name: str
    guard_egress: bool | None
    extra_headers: dict[str, str]


def _get_mcp_client_class():
    """Lazy import MCPClient (mirrors realtime_mcp_bridge.py's own lazy import)."""
    from skills.sync.mcp_client import MCPClient  # noqa: PLC0415

    return MCPClient


async def _audit_log(*args, **kwargs):
    """Lazy-import audit_log to avoid pulling in Redis at module init time."""
    from services.audit_logger import audit_log  # noqa: PLC0415

    return await audit_log(*args, **kwargs)


class MCPExternalBridge:
    """Discovers tools from every enabled external MCP server and routes calls to them."""

    def __init__(self) -> None:
        self._registry: dict[str, _ExternalToolEntry] = {}

    async def _enabled_servers(self) -> list[MCPServerConfig]:
        """Return every enabled server, or [] if the store itself is unreachable.

        A store outage (e.g. Redis down) must degrade to "no external tools
        this turn," not raise — this bridge sits on the same chat tool-
        dispatch path as every built-in tool, and a store blip must not take
        those down with it.
        """
        try:
            servers = await get_mcp_external_server_store().list()
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp_external_bridge: server store unreachable: %s", exc)
            return []
        return [s for s in servers if s.enabled]

    async def list_tools(self) -> list[MCPToolDefinition]:
        """Discover tools from every enabled server, renamed for collision-safety.

        Unreachable servers are logged and skipped (services.mcp_aggregation);
        this never raises for a single bad server.
        """
        self._registry = {}
        servers = await self._enabled_servers()
        if not servers:
            return []

        connect_settings: dict[str, tuple[bool | None, dict[str, str]]] = {}
        for server in servers:
            uri = server.to_server_uri()
            if server.transport == "stdio":
                connect_settings[uri] = (None, {})
            else:
                headers = await resolve_extra_headers_for_server(server)
                connect_settings[uri] = (instance_host_egress(), headers)

        MCPClient = _get_mcp_client_class()

        def _client_factory(uri: str):
            guard_egress, extra_headers = connect_settings[uri]
            return MCPClient(uri, guard_egress=guard_egress, extra_headers=extra_headers)

        resolved = await discover_and_resolve([s.to_server_uri() for s in servers], _client_factory)

        tools: list[MCPToolDefinition] = []
        for r in resolved:
            guard_egress, extra_headers = connect_settings[r.server_uri]
            self._registry[r.public_name] = _ExternalToolEntry(
                server_uri=r.server_uri,
                original_name=r.original_name,
                guard_egress=guard_egress,
                extra_headers=extra_headers,
            )
            tools.append(r.tool.model_copy(update={"name": r.public_name}))
        return tools

    def has_tool(self, name: str) -> bool:
        """Return True when *name* is in the routing registry from the last list_tools() call."""
        return name in self._registry

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, user_id: str | None = None
    ) -> ExternalToolCallResult:
        """Route a chat tool call to its owning external server. Always audit-logged."""
        entry = self._registry.get(name)
        if entry is None:
            return ExternalToolCallResult(success=False, error=f"Unknown external MCP tool '{name}'")

        MCPClient = _get_mcp_client_class()
        try:
            async with MCPClient(
                entry.server_uri, guard_egress=entry.guard_egress, extra_headers=entry.extra_headers
            ) as client:
                result = await client.call_tool(entry.original_name, arguments)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp_external_bridge.call_tool error tool=%s: %s", name, exc)
            await _audit_log(
                "mcp.external_server.tool_call",
                result="error",
                user_id=user_id,
                resource=name,
                details={"server_uri": entry.server_uri, "error": str(exc)},
            )
            return ExternalToolCallResult(success=False, error=str(exc))

        await _audit_log(
            "mcp.external_server.tool_call",
            result="success",
            user_id=user_id,
            resource=name,
            details={"server_uri": entry.server_uri},
        )
        return ExternalToolCallResult(success=True, result=result)


get_mcp_external_bridge = lazy_singleton(MCPExternalBridge)
