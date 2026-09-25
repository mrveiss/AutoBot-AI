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
from dataclasses import dataclass, field
from typing import Any, AsyncContextManager, Callable, Sequence

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.redaction import redact_provider_error
from skills.sync.mcp_client import RejectedTool
from type_defs.mcp import MCPToolDefinition

logger = get_logger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# A client factory takes a server URI and returns an async-context-manager object
# exposing `discover_tools_detailed() -> ToolDiscovery` (MCPClient's shape, #17467).
#
# Required rather than probed. The first version of #17467 used
# `getattr(client, "discover_tools_detailed", None)` to stay compatible with
# older clients -- and an `AsyncMock` auto-creates every attribute, so the probe
# answered "yes" for every test double and returned mocks where tools were
# expected. A capability probe that cannot say no is not a probe. The contract is
# stated here instead, and doubles implement it.
ClientFactory = Callable[[str], AsyncContextManager[Any]]


def server_id_from_uri(uri: str) -> str:
    """Return a stable, lowercase slug for *uri* suitable as a name prefix."""
    slug = re.sub(r"^[a-z]+://", "", uri.lower())
    slug = slug.split("/")[0]
    return _SLUG_RE.sub("_", slug).strip("_") or "mcp"


#: Exception types that mean OUR bug, not the server's state (#17439, #17467).
#: A `KeyError` from our own code is not an unreachable server, and laundering
#: one into the other is how a programming error becomes an operational metric.
_OUR_BUG = (AttributeError, KeyError, TypeError, NameError, ImportError, IndexError)


@dataclass(frozen=True)
class ServerToolList:
    """Tools discovered from one reachable server, and the ones it advertised that we refused."""

    server_id: str
    server_uri: str
    tools: list[MCPToolDefinition]
    rejected: list[RejectedTool] = field(default_factory=list)


@dataclass(frozen=True)
class ServerDiscoveryFailure:
    """A server that yielded no tool list, and which kind of failure it was (#17467).

    `kind` is `"transport"` when we could not talk to the server and `"schema"`
    when it answered and its payload was the problem. The old code logged the
    word "unreachable" for both, so an operator was actively misinformed that a
    reachable server was down.
    """

    server_id: str
    server_uri: str
    kind: str
    reason: str


@dataclass(frozen=True)
class MultiServerDiscovery:
    """Every server's outcome: the ones that answered, and the ones that did not."""

    servers: list[ServerToolList] = field(default_factory=list)
    failures: list[ServerDiscoveryFailure] = field(default_factory=list)


async def discover_tools_multi_server_detailed(
    server_uris: Sequence[str],
    client_factory: ClientFactory,
) -> MultiServerDiscovery:
    """Discover tools from every server URI, recording why any server yielded none (#17467).

    Three outcomes per server, and they were previously one:

    * answered, tools accepted -- and any tool it advertised that we refused is
      carried on the `ServerToolList` rather than dropped to a log line;
    * answered, payload unusable -- recorded as `kind="schema"`;
    * could not be reached -- recorded as `kind="transport"`.

    The old code logged *"skipping unreachable server"* for all three, so an
    operator debugging a reachable server with a bad schema was sent to look at
    the network.

    A programming error is re-raised rather than recorded. `_OUR_BUG` types mean
    a defect here, and absorbing one as a server-side failure is exactly the
    laundering #17439 found: an undeclared name came back as "Redis
    unavailable" and fed a circuit breaker. A bug in this loop affects every
    server, so failing loudly is also the more useful behaviour.
    """
    outcome = MultiServerDiscovery()
    for uri in server_uris:
        sid = server_id_from_uri(uri)
        try:
            async with client_factory(uri) as client:
                discovery = await client.discover_tools_detailed()
                tools, rejected = discovery.accepted, list(discovery.rejected)
            outcome.servers.append(ServerToolList(server_id=sid, server_uri=uri, tools=tools, rejected=rejected))
            logger.info(
                "mcp_aggregation: discovered server=%s tools=%d rejected=%d",
                sid,
                len(tools),
                len(rejected),
            )
        except _OUR_BUG:
            logger.exception("mcp_aggregation: internal error discovering server=%s — not a server fault", sid)
            raise
        except Exception as exc:  # noqa: BLE001
            kind = "schema" if _is_schema_failure(exc) else "transport"
            reason = redact_provider_error(exc)
            outcome.failures.append(ServerDiscoveryFailure(server_id=sid, server_uri=uri, kind=kind, reason=reason))
            logger.warning("mcp_aggregation: server=%s yielded no tools (%s): %s", sid, kind, reason)
    return outcome


def _is_schema_failure(exc: BaseException) -> bool:
    """Whether *exc* means the server answered and its payload was wrong.

    Matched on the exception's own class name rather than by importing pydantic
    here: the validation error may arrive from any layer that parses the
    payload, and this module has no reason to depend on the validator in use.
    """
    return "ValidationError" in type(exc).__name__


async def discover_tools_multi_server(
    server_uris: Sequence[str],
    client_factory: ClientFactory,
) -> list[ServerToolList]:
    """The servers that answered — see the `_detailed` form for why the others did not.

    Kept so existing callers are unchanged, and implemented over the same pass
    rather than duplicating the loop: one truth, two views.
    """
    return (await discover_tools_multi_server_detailed(server_uris, client_factory)).servers


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
