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
each server's credential into extra_headers, the egress guard for remote
servers, and cpu/memory/nofile rlimits (#3229) for stdio servers.

Wired into services/mcp_dispatch.py's existing RBAC-gated dispatch (#11542,
owner decision on #16458): every external tool is merged into
MCPDispatcher's tool cache carrying Permission.MCP_EXTERNAL as its
required_permission, so the same gate and the same BEFORE_TOOL_EXECUTE hook
built-in tools go through also cover these — no bypass. On top of that
coarse gate, call_tool() here checks the owning server's own
MCPServerConfig.allowed_roles before ever connecting — narrower, per-server
RBAC that MCPDispatcher's single shared permission cannot express.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from knowledge.connectors.base import instance_host_egress
from services.mcp_aggregation import discover_and_resolve
from services.mcp_external_servers import MCPServerConfig, get_mcp_external_server_store
from services.mcp_isolation_config import BridgePolicy, policy_for
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
    allowed_roles: list[str]
    resource_policy: BridgePolicy | None = None


@dataclass
class _ConnectSettings:
    """Per-server connection settings resolved once in list_tools(), reused for every tool."""

    guard_egress: bool | None
    extra_headers: dict[str, str]
    resource_policy: BridgePolicy | None
    allowed_roles: list[str]


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

    async def list_tools(self, reserved_names: frozenset[str] = frozenset()) -> list[MCPToolDefinition]:
        """Discover tools from every enabled server, renamed for collision-safety.

        Unreachable servers are logged and skipped (services.mcp_aggregation);
        this never raises for a single bad server.

        ``reserved_names`` (#16458 review): the caller's own internal tool
        names, so a server-advertised name matching one of them is prefixed
        with its server_id exactly like colliding with another external
        server -- an external server cannot shadow a built-in tool's name.
        """
        self._registry = {}
        servers = await self._enabled_servers()
        if not servers:
            return []

        connect_settings: dict[str, _ConnectSettings] = {}
        for server in servers:
            uri = server.to_server_uri()
            if server.transport == "stdio":
                # #3229: an admin-configured external stdio command gets the
                # same cpu/memory/nofile rlimits as an internal isolated
                # bridge — policy_for() has no per-server_id override
                # declared, so this resolves to the global defaults.
                connect_settings[uri] = _ConnectSettings(None, {}, policy_for(server.server_id), server.allowed_roles)
            else:
                headers = await resolve_extra_headers_for_server(server)
                connect_settings[uri] = _ConnectSettings(instance_host_egress(), headers, None, server.allowed_roles)

        MCPClient = _get_mcp_client_class()

        def _client_factory(uri: str):
            settings = connect_settings[uri]
            return MCPClient(
                uri,
                guard_egress=settings.guard_egress,
                extra_headers=settings.extra_headers,
                resource_policy=settings.resource_policy,
            )

        resolved = await discover_and_resolve(
            [s.to_server_uri() for s in servers], _client_factory, reserved_names=reserved_names
        )

        tools: list[MCPToolDefinition] = []
        for r in resolved:
            settings = connect_settings[r.server_uri]
            self._registry[r.public_name] = _ExternalToolEntry(
                server_uri=r.server_uri,
                original_name=r.original_name,
                guard_egress=settings.guard_egress,
                extra_headers=settings.extra_headers,
                allowed_roles=settings.allowed_roles,
                resource_policy=settings.resource_policy,
            )
            tools.append(r.tool.model_copy(update={"name": r.public_name}))
        return tools

    def has_tool(self, name: str) -> bool:
        """Return True when *name* is in the routing registry from the last list_tools() call."""
        return name in self._registry

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        role: str = "user",
        user_id: str | None = None,
    ) -> ExternalToolCallResult:
        """Route a chat tool call to its owning external server. Always audit-logged.

        ``role`` is checked against the owning server's own
        ``MCPServerConfig.allowed_roles`` (#11542, owner decision on #16458)
        — narrower, per-server RBAC on top of the coarse
        ``Permission.MCP_EXTERNAL`` gate ``MCPDispatcher.dispatch()`` already
        enforced before this method is ever reached. A role not on the list
        is refused here, without ever connecting to the server.
        """
        entry = self._registry.get(name)
        if entry is None:
            return ExternalToolCallResult(success=False, error=f"Unknown external MCP tool '{name}'")

        if role not in entry.allowed_roles:
            logger.warning("mcp_external_bridge.call_tool role=%s denied for tool=%s", role, name)
            await _audit_log(
                "mcp.external_server.tool_call",
                result="denied",
                user_id=user_id,
                resource=name,
                details={"server_uri": entry.server_uri, "role": role, "allowed_roles": entry.allowed_roles},
            )
            return ExternalToolCallResult(success=False, error=f"role '{role}' is not permitted to call '{name}'")

        MCPClient = _get_mcp_client_class()
        try:
            async with MCPClient(
                entry.server_uri,
                guard_egress=entry.guard_egress,
                extra_headers=entry.extra_headers,
                resource_policy=entry.resource_policy,
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
