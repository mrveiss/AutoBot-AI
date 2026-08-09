# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

Cache TTL and RBAC filtering added in #2598.
"""

import time
import uuid

import aiohttp

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Role, is_admin_role
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from constants.network_constants import NetworkConstants

logger = get_logger(__name__)

# #13228 stage 2: role -> the permission *values* it holds, built once. The shadow
# runs on every dispatch and rebuilding a 50+ element set per call is needless.
_ROLE_PERMISSION_VALUES: "dict[Role, frozenset[str]]" = {
    role: frozenset(p.value for p in perms) for role, perms in ROLE_PERMISSIONS.items()
}

# #13265: minimum run-JWT scopes per isolated bridge. resolve_mode() forces
# SUBPROCESS for filesystem_mcp, browser_mcp and vnc_mcp regardless of config,
# so these are the bridges whose workers validate a run JWT. Unlisted bridges
# get the safest scope, matching services/run_jwt._FALLBACK_SCOPES.
_BRIDGE_RUN_JWT_SCOPES: dict[str, list[str]] = {
    "filesystem_mcp": ["mcp:filesystem"],
    "browser_mcp": ["mcp:web_fetch"],
    "vnc_mcp": ["task:read"],
}
_DEFAULT_BRIDGE_SCOPES: list[str] = ["task:read"]


class MCPDispatcher:
    """Routes unknown tool calls to registered MCP bridges via the registry.

    Caches tool metadata fetched from the registry so that repeated tool
    calls do not incur extra HTTP round-trips for discovery.

    Cache refreshes automatically after CACHE_TTL_SECONDS (#2598).
    Tools matching _ADMIN_ONLY_TOOLS patterns require role="admin" (#2598).
    """

    CACHE_TTL_SECONDS: int = 60

    # Tool name substrings that require admin role (#2598)
    _ADMIN_ONLY_TOOLS: frozenset = frozenset(
        {
            "client_list",
            "slowlog",
            "config_set",
            "config_rewrite",
            "debug",
            "flushdb",
            "flushall",
        }
    )

    def __init__(self) -> None:
        """Initialize dispatcher with empty tool cache."""
        self._tool_cache: dict[str, dict] = {}
        self._cache_loaded = False
        self._cache_timestamp: float = 0.0
        # #13228 stage 2: (tool, role, reason) triples already reported, so the
        # shadow log stays an inventory rather than a per-call stream.
        self._rbac_shadow_seen: "set[tuple[str, str, str]]" = set()

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    async def _ensure_cache_fresh(self) -> None:
        """Refresh the tool cache if it is empty or older than CACHE_TTL_SECONDS (#2598)."""
        age = time.monotonic() - self._cache_timestamp
        if not self._cache_loaded or age > self.CACHE_TTL_SECONDS:
            await self.refresh_tool_cache()

    async def refresh_tool_cache(self) -> int:
        """Fetch all tools from the MCP registry and populate the local cache.

        Makes a single HTTP request to /api/mcp/tools which aggregates all
        bridges.  Returns the number of tools cached.
        """
        backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
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
                self._cache_timestamp = time.monotonic()
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

    def find_tool(self, tool_name: str) -> dict | None:
        """Return the cached tool entry for tool_name, or None if not found."""
        return self._tool_cache.get(tool_name)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _is_admin_only(self, tool_name: str) -> bool:
        """Return True if tool_name matches any admin-only pattern (#2598)."""
        return any(pattern in tool_name for pattern in self._ADMIN_ONLY_TOOLS)

    def _would_deny(self, tool_name: str, role: str) -> str | None:
        """Return why RBAC *would* refuse this call, or None (#13228 stage 2).

        Reports only; the caller does not act on it. The declaration landed in
        stage 1 and the enforcement flip is stage 3, so this exists to answer the
        one question the flip needs answered first: **which working calls would
        it break?** The issue's own risk note predicts default-deny "will surface
        tools that were silently reachable" — this turns that prediction into a
        list before it costs anyone a broken agent run.

        Two distinct outcomes, kept distinct because they need different fixes:
        an undeclared tool needs a declaration; a declared one the role lacks
        needs a grant (or is the guard working as intended).
        """
        if not self._tool_cache:
            # An empty cache means the registry never answered, not that every
            # tool is undeclared (refresh_tool_cache swallows failures and
            # returns 0). Reporting "undeclared" here would fill the inventory
            # with an infrastructure outage dressed as a policy gap — and if
            # stage 3 enforced on that same signal, a registry blip would deny
            # every MCP call. No cache, no verdict.
            return None

        entry = self._tool_cache.get(tool_name)
        declared = entry.get("required_permission") if isinstance(entry, dict) else None
        if declared is None:
            return "undeclared"

        # superadmin is administrative but is not a Role enum member (see
        # ADMIN_ROLES in autobot_shared.auth.permissions), so resolving it
        # through Role() would report the most privileged role in the system as
        # denied on every tool. is_admin_role is the canonical, case-insensitive
        # answer and is what the legacy gate below already uses.
        if is_admin_role(role):
            return None
        try:
            held = _ROLE_PERMISSION_VALUES[Role(str(role or "").lower())]
        except (ValueError, KeyError):
            # An unrecognised role string is itself worth surfacing rather than
            # silently treating as permitted.
            return f"unknown-role:{role}"
        return None if declared in held else f"missing:{declared}"

    def _log_rbac_shadow(self, tool_name: str, role: str) -> None:
        """Log what canonical RBAC would have decided, without deciding (#13228).

        Deduplicated on ``(tool, role, reason)``. The deliverable is the *set* of
        disagreements, so repeating one per call would multiply the volume without
        adding a fact — an agent loop touching one undeclared tool would otherwise
        emit a warning per iteration.
        """
        reason = self._would_deny(tool_name, role)
        if reason is None:
            return
        seen_key = (tool_name, role, reason)
        if seen_key in self._rbac_shadow_seen:
            return
        self._rbac_shadow_seen.add(seen_key)
        logger.warning(
            "MCPDispatcher[rbac-shadow]: role=%s tool=%s would be denied (%s) — " "not enforced yet, see #13228",
            role,
            tool_name,
            reason,
        )

    async def dispatch(
        self,
        tool_name: str,
        arguments: dict,
        role: str = "user",
        session_id: str | None = None,
    ) -> dict:
        """Dispatch a tool call to its registered MCP bridge.

        Refreshes the tool cache if stale (TTL-based, #2598).
        Rejects admin-only tools when role != "admin" (#2598).

        Issue #3232: emits agent.tool.call before dispatch and
        agent.tool.result after, with sensitive argument redaction.

        Args:
            tool_name: Tool name from the LLM tool call.
            arguments: Tool arguments dict.
            role: Caller role — "admin" or "user" (default).

        Returns:
            Dict with keys: success (bool), result (str | dict), bridge (str | None).
        """
        from chat_workflow.cot_events import emit_tool_call, emit_tool_result

        await self._ensure_cache_fresh()

        # #13228 stage 2: record the canonical-RBAC verdict alongside the legacy
        # blocklist without acting on it. The blocklist below still decides.
        self._log_rbac_shadow(tool_name, role)

        if not is_admin_role(role) and self._is_admin_only(tool_name):
            logger.warning(
                "MCPDispatcher: role=%s denied access to admin-only tool %s",
                role,
                tool_name,
            )
            return {
                "success": False,
                "result": f"Tool {tool_name} requires admin role",
                "bridge": None,
            }

        tool = self.find_tool(tool_name)
        if not tool:
            return {
                "success": False,
                "result": f"Unknown tool: {tool_name}",
                "bridge": None,
            }

        bridge = tool.get("bridge", "unknown")
        endpoint = tool.get("endpoint", "")

        # Issue #3232: emit CoT events around bridge call.
        _cot_start = emit_tool_call(tool_name, arguments, session_id=session_id)
        result = await self._call_bridge(tool_name, bridge, endpoint, arguments)
        emit_tool_result(
            tool_name,
            result.get("result", ""),
            _cot_start,
            success=result.get("success", False),
            bridge=bridge,
            session_id=session_id,
        )
        return result

    @staticmethod
    def _mint_bridge_jwt(bridge: str, tool_name: str) -> str | None:
        """Mint a short-lived run JWT scoped to *bridge* (#13265).

        Returns None when no signing secret is configured. That is not silent:
        it is logged, and the worker then rejects the call itself with a
        -32001 whenever MCP_RUN_JWT_ENFORCE is on. Failing to mint must not
        crash dispatch for deployments that run with enforcement off.
        """
        from services.run_jwt import mint_run_jwt

        scopes = _BRIDGE_RUN_JWT_SCOPES.get(bridge, _DEFAULT_BRIDGE_SCOPES)
        try:
            return mint_run_jwt(
                run_id=str(uuid.uuid4()),
                task_id=f"mcp:{tool_name}",
                agent_id=f"mcp_dispatch:{bridge}",
                tenant_id="default",
                scope=scopes,
            )
        except (RuntimeError, ValueError) as exc:
            logger.warning(
                "MCPDispatcher: could not mint run JWT for bridge %s tool %s: %s "
                "— isolated call will be rejected if MCP_RUN_JWT_ENFORCE is set",
                bridge,
                tool_name,
                exc,
            )
            return None

    async def _call_bridge(self, tool_name: str, bridge: str, endpoint: str, arguments: dict) -> dict:
        """Execute a tool call against an MCP bridge.

        Routes through an isolated subprocess worker when the bridge policy
        requires it (#3229); otherwise falls back to the in-process HTTP path.

        Args:
            tool_name: Name of the tool being called.
            bridge: Bridge identifier (for logging/result metadata).
            endpoint: Full URL path of the tool's bridge endpoint.
            arguments: Arguments to pass to the bridge.

        Returns:
            Dict with keys: success, result, bridge.
        """
        # Issue #3229: isolated-worker routing.
        from services.mcp_isolated_runtime import get_isolated_registry

        isolated = await get_isolated_registry().get_or_create(bridge)
        if isolated is not None:
            # #13265: the worker validates a run JWT when MCP_RUN_JWT_ENFORCE=1.
            # It cannot read one from its environment (_WORKER_ENV_ALLOW scrubs
            # MCP_RUN_JWT by design), so it must be passed per request.
            return await isolated.call_tool(tool_name, arguments, run_jwt=self._mint_bridge_jwt(bridge, tool_name))

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

    def get_tool_definitions(self, role: str = "user") -> list[dict]:
        """Return tool definitions in LLM-injectable format.

        Admin-only tools are excluded when role != "admin" (#2598).
        Each entry contains name, description (prefixed with bridge name),
        and parameters (from the tool's input_schema).

        Args:
            role: Caller role — "admin" or "user" (default).

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
            if is_admin_role(role) or not self._is_admin_only(tool["name"])
        ]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_dispatcher: MCPDispatcher | None = None


def get_mcp_dispatcher() -> MCPDispatcher:
    """Return the singleton MCPDispatcher instance (created on first call)."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = MCPDispatcher()
    return _dispatcher
