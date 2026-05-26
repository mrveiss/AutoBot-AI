# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Realtime MCP Bridge — surfaces MCP tools as OpenAI Realtime function tools.

Issue #7343 (full bridge), #7344 (voice bundle filtering).

This module provides:
- list_realtime_tools(): returns Realtime-shaped schemas filtered by the active
  voice bundle and the caller's RBAC role.
- call_tool(): routes tool calls back through MCPClient (stub — wired in #7343).

Bundle filtering (#7344) happens BEFORE schemas are returned to the frontend so
the model never sees tools it isn't allowed to call in its voice context.
"""

from dataclasses import dataclass, field
from typing import Any

from api.redis_mcp.rbac import filter_tools_for_bundle
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)


@dataclass
class RealtimeTool:
    """OpenAI Realtime function-tool schema."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    type: str = "function"


@dataclass
class RealtimeToolResult:
    """Result from a Realtime tool call."""

    content: str
    is_error: bool = False


class RealtimeMCPBridge:
    """Bridge between AutoBot MCP tools and OpenAI Realtime function-tool format.

    Bundle filtering is applied in list_realtime_tools() so the model only
    sees the tools permitted by the active voice context.

    Full MCP transport wiring is deferred to #7343.
    """

    def __init__(self, is_admin: bool = False) -> None:
        self._is_admin = is_admin
        self._bundle = config.voice_toolset_bundle
        self._disabled = [t.strip() for t in config.voice_disabled_tools.split(",") if t.strip()]

    async def list_realtime_tools(self) -> list[RealtimeTool]:
        """Return Realtime-shaped tool schemas filtered by the active bundle.

        Applies voice bundle + RBAC filtering before returning. The frontend
        uses this list to populate session.update tools.
        """
        all_tools = await self._discover_tools()
        allowed_names = filter_tools_for_bundle(
            [t.name for t in all_tools],
            bundle=self._bundle,
            is_admin=self._is_admin,
            disabled_tools=self._disabled,
        )
        allowed_set = set(allowed_names)
        filtered = [t for t in all_tools if t.name in allowed_set]
        logger.info(
            "realtime_mcp_bridge bundle=%s is_admin=%s tools=%d",
            self._bundle,
            self._is_admin,
            len(filtered),
        )
        return filtered

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        session_id: str | None = None,
    ) -> RealtimeToolResult:
        """Route a Realtime tool call back through MCPClient.

        Emits per-tool Prometheus metrics (Issue #7421).
        Full transport wiring deferred to #7343.
        """
        import time

        start = time.monotonic()
        # Stub: full wiring in #7343
        logger.warning("realtime_mcp_bridge.call_tool not yet wired: tool=%s", name)
        result = RealtimeToolResult(
            content=f"Tool '{name}' transport not yet wired (#7343)",
            is_error=True,
        )
        latency_s = time.monotonic() - start

        # Issue #7421: emit per-tool metrics; record_tool_call handles Prometheus + Redis
        outcome = "error" if result.is_error else "success"
        if session_id:
            try:
                from services.voice_realtime_telemetry import get_voice_realtime_telemetry
                await get_voice_realtime_telemetry().record_tool_call(
                    session_id=session_id,
                    tool=name,
                    latency_s=latency_s,
                    outcome=outcome,
                )
            except Exception as exc:  # metrics must never break the tool call path
                logger.debug("voice_realtime metrics emit failed: %s", exc)

        return result

    async def _discover_tools(self) -> list[RealtimeTool]:
        """Enumerate available MCP tools.

        Stub: full discovery via MCPClient deferred to #7343.
        Returns the AutoBot MCP server tool list as a baseline.
        """
        from mcp.autobot_server import _TOOLS

        result = []
        for name, meta in _TOOLS.items():
            result.append(
                RealtimeTool(
                    name=name,
                    description=meta.get("description", ""),
                    parameters=meta.get("inputSchema", {}),
                )
            )
        return result


async def get_realtime_bridge(is_admin: bool = False) -> RealtimeMCPBridge:
    """Return a configured RealtimeMCPBridge for the current session."""
    return RealtimeMCPBridge(is_admin=is_admin)
