# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Realtime MCP Bridge — surfaces MCP tools as OpenAI Realtime function tools.

Issue #7343 (full bridge), #7344 (voice bundle filtering).

This module provides:
- list_realtime_tools(): discovers all MCP tools via MCPClient, translates each
  tool's inputSchema into an OpenAI Realtime function-tool entry, and applies
  voice bundle + RBAC filtering before returning to the frontend.
- call_tool(): routes incoming Realtime tool calls back through MCPClient and
  returns a RealtimeToolResult with is_error semantics so the model can
  self-correct verbally on failure.

Multi-server support: when MCP_SERVER_URIS is configured (comma-separated),
each server gets a stable server_id (slugified from the URI). Tool names are
prefixed as "{server_id}__{name}" when two or more servers expose a tool with
the same name, ensuring deterministic collision resolution. Single-server
deployments retain bare names for backwards compatibility.

Audit log entries are written for every tools/call via the existing audit
pipeline (correlate on operation "voice.realtime.tool_call").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)


def _get_mcp_client_class():
    """Lazy import MCPClient to avoid pulling in the skills package init at module load."""
    from skills.sync.mcp_client import MCPClient  # noqa: PLC0415
    return MCPClient


def _get_filter_tools_for_bundle():
    """Lazy import to avoid circular import at module init time."""
    from api.redis_mcp.rbac import filter_tools_for_bundle  # noqa: PLC0415
    return filter_tools_for_bundle


async def _audit_log(*args, **kwargs):
    """Lazy-import audit_log to avoid pulling in Redis at module init time."""
    from services.audit_logger import audit_log  # noqa: PLC0415
    return await audit_log(*args, **kwargs)

# ---------------------------------------------------------------------------
# Realtime schema types
# ---------------------------------------------------------------------------


@dataclass
class RealtimeTool:
    """OpenAI Realtime function-tool schema entry."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    type: str = "function"


@dataclass
class RealtimeToolResult:
    """Result from a Realtime tool call."""

    content: str
    is_error: bool = False


# ---------------------------------------------------------------------------
# Internal routing registry entry
# ---------------------------------------------------------------------------

@dataclass
class _ToolEntry:
    """Maps a public (possibly-prefixed) Realtime name back to its origin."""

    server_id: str
    server_uri: str | None  # None → in-process _TOOLS dict
    original_name: str


# ---------------------------------------------------------------------------
# Schema translation helpers
# ---------------------------------------------------------------------------

_REALTIME_FALLBACK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
}


def _translate_property(prop: Any) -> dict[str, Any]:
    """Recursively convert an MCPPropertyDefinition (or raw dict) to a plain JSON-Schema dict."""
    if prop is None:
        return {}
    if isinstance(prop, dict):
        raw = prop
    else:
        # Pydantic model — dump to dict
        raw = prop.model_dump(exclude_none=True)

    out: dict[str, Any] = {}

    if "type" in raw:
        out["type"] = raw["type"]

    if "description" in raw and raw["description"]:
        out["description"] = raw["description"]

    if "default" in raw and raw["default"] is not None:
        out["default"] = raw["default"]

    if "enum" in raw and raw["enum"]:
        out["enum"] = raw["enum"]

    # Recursive: array items
    if "items" in raw and raw["items"] is not None:
        out["items"] = _translate_property(raw["items"])

    # Recursive: object properties
    if "properties" in raw and raw["properties"]:
        out["properties"] = {k: _translate_property(v) for k, v in raw["properties"].items()}

    if "required" in raw and raw["required"]:
        out["required"] = raw["required"]

    # additionalProperties — preserve explicit false/true
    if "additionalProperties" in raw:
        out["additionalProperties"] = raw["additionalProperties"]

    return out


def _translate_input_schema(input_schema: Any) -> dict[str, Any]:
    """Convert MCPInputSchema (or raw dict) to an OpenAI Realtime parameters object.

    Falls back to {type:object, additionalProperties:true} when the schema is
    absent or unparseable so the Realtime model can still attempt the call.
    """
    if input_schema is None:
        return dict(_REALTIME_FALLBACK_SCHEMA)

    if isinstance(input_schema, dict):
        raw = input_schema
    else:
        try:
            raw = input_schema.model_dump(exclude_none=True)
        except Exception:
            return dict(_REALTIME_FALLBACK_SCHEMA)

    if not raw:
        return dict(_REALTIME_FALLBACK_SCHEMA)

    out: dict[str, Any] = {"type": raw.get("type", "object")}

    props_raw = raw.get("properties") or {}
    if props_raw:
        out["properties"] = {k: _translate_property(v) for k, v in props_raw.items()}

    required = raw.get("required") or []
    if required:
        out["required"] = required

    # additionalProperties defaults to False (stricter validation in Realtime)
    out["additionalProperties"] = raw.get("additionalProperties", False)

    return out


# ---------------------------------------------------------------------------
# Server-ID helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _server_id_from_uri(uri: str) -> str:
    """Return a stable, lowercase slug for *uri* suitable as a name prefix."""
    # Strip scheme
    slug = re.sub(r"^[a-z]+://", "", uri.lower())
    # Strip path components beyond the host:port
    slug = slug.split("/")[0]
    return _SLUG_RE.sub("_", slug).strip("_") or "mcp"


# ---------------------------------------------------------------------------
# Main bridge
# ---------------------------------------------------------------------------


class RealtimeMCPBridge:
    """Bridge between AutoBot MCP tools and OpenAI Realtime function-tool format.

    Discovery flow:
      1. Enumerate configured MCP server URIs from ``mcp_server_uris`` config.
      2. For each server, open an MCPClient connection and call discover_tools().
      3. Unreachable servers are logged and skipped (best-effort).
      4. When no external servers are configured, fall back to the in-process
         ``mcp.autobot_server._TOOLS`` dict (zero-dependency baseline).
      5. Name collisions across servers are resolved by prefixing with server_id.
      6. Voice bundle + RBAC filtering is applied before returning.

    Routing:
      call_tool() looks up the routing registry built during _discover_tools() to
      find which server owns the tool and opens a fresh MCPClient for the call.
    """

    def __init__(
        self,
        is_admin: bool = False,
        server_uris: list[str] | None = None,
    ) -> None:
        self._is_admin = is_admin
        self._bundle = getattr(config, "voice_toolset_bundle", "voice_safe")
        disabled_raw = getattr(config, "voice_disabled_tools", "")
        self._disabled = [t.strip() for t in disabled_raw.split(",") if t.strip()]

        # Routing registry populated during _discover_tools()
        self._registry: dict[str, _ToolEntry] = {}

        # Server URIs — prefer explicit arg, then config, then empty (in-process)
        if server_uris is not None:
            self._server_uris = server_uris
        else:
            raw = getattr(config, "mcp_server_uris", "") or ""
            self._server_uris = [u.strip() for u in raw.split(",") if u.strip()]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def list_realtime_tools(self) -> list[RealtimeTool]:
        """Return Realtime-shaped tool schemas filtered by the active bundle.

        The frontend uses this list to populate the ``session.update`` tools
        array before opening a Realtime session.
        """
        all_tools = await self._discover_tools()
        filter_tools_for_bundle = _get_filter_tools_for_bundle()
        allowed_names = filter_tools_for_bundle(
            [t.name for t in all_tools],
            bundle=self._bundle,
            is_admin=self._is_admin,
            disabled_tools=self._disabled,
        )
        allowed_set = set(allowed_names)
        filtered = [t for t in all_tools if t.name in allowed_set]
        logger.info(
            "realtime_mcp_bridge list bundle=%s is_admin=%s discovered=%d filtered=%d",
            self._bundle,
            self._is_admin,
            len(all_tools),
            len(filtered),
        )
        return filtered

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> RealtimeToolResult:
        """Route a Realtime tool call through MCPClient and return the result.

        Errors from the transport surface as ``is_error=True`` with the
        original message in ``content`` so the model can self-correct verbally.
        An audit log entry is written for every invocation.  Per-session
        telemetry is emitted via VoiceRealtimeTelemetry when session_id is set
        (GH#7421).
        """
        import time

        entry = self._registry.get(name)

        audit_details: dict[str, Any] = {
            "tool": name,
            "has_entry": entry is not None,
            "server_id": entry.server_id if entry else None,
        }

        if entry is None:
            logger.warning("realtime_mcp_bridge.call_tool unknown tool=%s", name)
            await _audit_log(
                "voice.realtime.tool_call",
                result="failed",
                user_id=user_id,
                session_id=session_id,
                resource=name,
                details={**audit_details, "error": "unknown_tool"},
            )
            return RealtimeToolResult(
                content=f"Unknown tool '{name}'. No MCP server registered this tool.",
                is_error=True,
            )

        start = time.monotonic()
        try:
            raw_result = await self._call_via_transport(entry, arguments)
            content = self._format_result(raw_result)
            latency_s = time.monotonic() - start
            await _audit_log(
                "voice.realtime.tool_call",
                result="success",
                user_id=user_id,
                session_id=session_id,
                resource=name,
                details=audit_details,
            )
            if session_id:
                try:
                    from services.voice_realtime_telemetry import get_voice_realtime_telemetry
                    await get_voice_realtime_telemetry().record_tool_call(
                        session_id=session_id, tool=name, latency_s=latency_s, outcome="success",
                    )
                except Exception as _te:
                    logger.debug("voice_realtime telemetry emit failed: %s", _te)
            return RealtimeToolResult(content=content, is_error=False)

        except Exception as exc:  # noqa: BLE001
            latency_s = time.monotonic() - start
            logger.warning(
                "realtime_mcp_bridge.call_tool error tool=%s (%s): %s",
                name, type(exc).__name__, exc,
            )
            await _audit_log(
                "voice.realtime.tool_call",
                result="error",
                user_id=user_id,
                session_id=session_id,
                resource=name,
                details={**audit_details, "error": str(exc)},
            )
            if session_id:
                try:
                    from services.voice_realtime_telemetry import get_voice_realtime_telemetry
                    await get_voice_realtime_telemetry().record_tool_call(
                        session_id=session_id, tool=name, latency_s=latency_s, outcome="error",
                    )
                except Exception as _te:
                    logger.debug("voice_realtime telemetry emit failed: %s", _te)
            return RealtimeToolResult(content=str(exc), is_error=True)

    # ------------------------------------------------------------------
    # Discovery internals
    # ------------------------------------------------------------------

    async def _discover_tools(self) -> list[RealtimeTool]:
        """Enumerate MCP tools from all configured servers and build the routing registry.

        When no external server URIs are configured, falls back to in-process
        _TOOLS dict from mcp.autobot_server.
        """
        self._registry = {}

        if not self._server_uris:
            return self._discover_inprocess()

        # Multi-server: collect per-server tool lists
        server_tool_lists: list[tuple[str, str, list[Any]]] = []
        for uri in self._server_uris:
            sid = _server_id_from_uri(uri)
            try:
                MCPClient = _get_mcp_client_class()
                async with MCPClient(uri) as client:
                    tools = await client.discover_tools()
                server_tool_lists.append((sid, uri, tools))
                logger.info(
                    "realtime_mcp_bridge discovered server=%s tools=%d", sid, len(tools)
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "realtime_mcp_bridge skipping unreachable server %s: %s", uri, exc
                )

        return self._build_registry(server_tool_lists)

    def _discover_inprocess(self) -> list[RealtimeTool]:
        """Discover tools from the in-process AutoBot MCP server dict (zero-dependency baseline)."""
        from mcp.autobot_server import _TOOLS  # noqa: PLC0415

        result: list[RealtimeTool] = []
        for name, meta in _TOOLS.items():
            rt = RealtimeTool(
                name=name,
                description=meta.get("description", ""),
                parameters=_translate_input_schema(meta.get("inputSchema")),
            )
            result.append(rt)
            self._registry[name] = _ToolEntry(
                server_id="autobot",
                server_uri=None,
                original_name=name,
            )
        logger.info("realtime_mcp_bridge in-process tools=%d", len(result))
        return result

    def _build_registry(
        self, server_tool_lists: list[tuple[str, str, list[Any]]]
    ) -> list[RealtimeTool]:
        """Resolve name collisions and build the routing registry.

        A tool name that appears on exactly one server keeps its bare name.
        A tool name that appears on two or more servers is prefixed as
        "{server_id}__{original_name}" on every server to ensure determinism.
        """
        # Count how many servers expose each original tool name
        name_count: dict[str, int] = {}
        for _sid, _uri, tools in server_tool_lists:
            for tool in tools:
                name_count[tool.name] = name_count.get(tool.name, 0) + 1

        result: list[RealtimeTool] = []
        for sid, uri, tools in server_tool_lists:
            for tool in tools:
                original_name = tool.name
                if name_count[original_name] > 1:
                    public_name = f"{sid}__{original_name}"
                else:
                    public_name = original_name

                rt = RealtimeTool(
                    name=public_name,
                    description=tool.description,
                    parameters=_translate_input_schema(
                        getattr(tool, "input_schema", None)
                    ),
                )
                result.append(rt)
                self._registry[public_name] = _ToolEntry(
                    server_id=sid,
                    server_uri=uri,
                    original_name=original_name,
                )

        return result

    # ------------------------------------------------------------------
    # Transport routing
    # ------------------------------------------------------------------

    async def _call_via_transport(
        self, entry: _ToolEntry, arguments: dict[str, Any]
    ) -> Any:
        """Invoke the tool via MCPClient transport or in-process handler."""
        if entry.server_uri is None:
            return await self._call_inprocess(entry.original_name, arguments)

        MCPClient = _get_mcp_client_class()
        async with MCPClient(entry.server_uri) as client:
            return await client.call_tool(entry.original_name, arguments)

    @staticmethod
    async def _call_inprocess(name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool via the in-process AutoBotMCPServer handler."""
        from mcp.autobot_server import AutoBotMCPServer  # noqa: PLC0415

        server = AutoBotMCPServer()
        if hasattr(server, "handle_tool_call"):
            return await server.handle_tool_call(name, arguments)

        # Fallback: direct dispatch via _TOOLS handler map
        from mcp.autobot_server import _TOOLS  # noqa: PLC0415

        if name not in _TOOLS:
            raise RuntimeError(f"Tool not found: {name}")
        handler = _TOOLS[name].get("handler")
        if handler is None:
            raise RuntimeError(f"Tool '{name}' has no handler")
        return await handler(arguments)

    @staticmethod
    def _format_result(raw: Any) -> str:
        """Serialise a raw MCP result to the string content for Realtime."""
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            if "content" in raw:
                parts = []
                for item in raw.get("content", []):
                    if isinstance(item, dict) and "text" in item:
                        parts.append(item["text"])
                    else:
                        parts.append(str(item))
                return "\n".join(parts) if parts else ""
        import json  # noqa: PLC0415

        try:
            return json.dumps(raw)
        except (TypeError, ValueError):
            return str(raw)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


async def get_realtime_bridge(
    is_admin: bool = False,
    server_uris: list[str] | None = None,
) -> RealtimeMCPBridge:
    """Return a configured RealtimeMCPBridge for the current session."""
    return RealtimeMCPBridge(is_admin=is_admin, server_uris=server_uris)
