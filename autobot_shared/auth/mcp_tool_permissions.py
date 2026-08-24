# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical permission required by each MCP tool (#13228).

MCP tool access was governed by ``MCPDispatcher._ADMIN_ONLY_TOOLS`` — a frozenset
of **seven Redis command substrings**. Everything else on all eleven bridges was
reachable by ``role="user"``, and the same list gated what was advertised to the
LLM. A newly added destructive tool was exposed unless somebody remembered to
edit that frozenset.

This module replaces the guesswork with a declaration, resolved at the one place
every tool passes through on both consumer paths — ``mcp_registry._build_tool_entry``
— so ``dispatch()`` and ``get_tool_definitions()`` read the same answer.

Two levels, and the order matters:

1. ``TOOL_PERMISSIONS`` — an exact tool name wins outright. This is where a
   destructive tool declares a stronger grant than its bridge's baseline.
2. ``BRIDGE_DEFAULT_PERMISSIONS`` — the baseline for a bridge, chosen as its
   **least**-privileged operation. A tool added tomorrow inherits read-level
   access rather than whatever the blocklist happened to miss.

A tool on an unknown bridge with no exact entry resolves to ``None``, which is
what the enforcement stage (#13228 step 5) refuses. Absence is a denial, not a
default-allow — that inversion is the point of the issue.

**This module only describes. It enforces nothing on its own.** Stage 1 attaches
the resolved value to the registry entry so it can be inspected and logged;
``dispatch()`` still applies the old rule until the fallout inventory is in.
"""

from typing import Dict, Optional

from autobot_shared.auth.permissions import Permission

# Baseline per bridge — deliberately the least-privileged operation the bridge
# offers, so an undeclared future tool under-grants rather than over-grants.
BRIDGE_DEFAULT_PERMISSIONS: Dict[str, Permission] = {
    "browser_mcp": Permission.MCP_BROWSER_READ,
    "database_mcp": Permission.MCP_DATABASE_READ,
    "filesystem_mcp": Permission.FILES_VIEW,
    "git_mcp": Permission.MCP_GIT_READ,
    "http_client_mcp": Permission.MCP_HTTP_READ,
    "knowledge_mcp": Permission.KNOWLEDGE_READ,
    "prometheus_mcp": Permission.MCP_METRICS_READ,
    # #13228: missed on the first pass, which made all 25 redis tools resolve to
    # "undeclared" — including the seven the blocklist already knew about.
    "redis_mcp": Permission.MCP_DATABASE_READ,
    "sequential_thinking_mcp": Permission.AGENT_EXECUTE,
    "structured_thinking_mcp": Permission.AGENT_EXECUTE,
    "vnc_mcp": Permission.MCP_DESKTOP_READ,
}

# Exact tool names that need more than their bridge's baseline. Everything here
# either changes state, leaves the machine, or reads something the baseline
# grant does not cover.
TOOL_PERMISSIONS: Dict[str, Permission] = {
    # --- browser: observation is the baseline; driving the page is not ---
    "click": Permission.MCP_BROWSER_CONTROL,
    "click_index": Permission.MCP_BROWSER_CONTROL,
    "fill": Permission.MCP_BROWSER_CONTROL,
    "fill_index": Permission.MCP_BROWSER_CONTROL,
    "hover": Permission.MCP_BROWSER_CONTROL,
    "hover_index": Permission.MCP_BROWSER_CONTROL,
    # `evaluate` runs caller-supplied JavaScript in the page — the strongest
    # thing this bridge can do, and it read as an ordinary user tool before.
    "evaluate": Permission.MCP_BROWSER_CONTROL,
    "intercept_requests": Permission.MCP_BROWSER_CONTROL,
    # --- database: reads are the baseline; anything that can mutate is not ---
    "database_execute": Permission.MCP_DATABASE_WRITE,
    # --- http: a GET/HEAD is a read; the rest send a body or change state ---
    "http_post": Permission.MCP_HTTP_WRITE,
    "http_put": Permission.MCP_HTTP_WRITE,
    "http_patch": Permission.MCP_HTTP_WRITE,
    "http_delete": Permission.MCP_HTTP_WRITE,
    # --- filesystem: FILES_VIEW is the baseline; these write or destroy ---
    "edit_file": Permission.FILES_UPLOAD,
    "write_file": Permission.FILES_UPLOAD,
    "create_directory": Permission.FILES_UPLOAD,
    "move_file": Permission.FILES_UPLOAD,
    "delete_file": Permission.FILES_DELETE,
    # --- knowledge: reading is the baseline; ingesting is a write ---
    "add_to_knowledge_base": Permission.KNOWLEDGE_WRITE,
    "crawl_site": Permission.KNOWLEDGE_WRITE,
    # Found by test_state_changing_tools_carry_an_explicit_declaration on its
    # first run: mcp_crawl registers a WebCrawlerConnector and ingests, so
    # inheriting KNOWLEDGE_READ would have under-granted it.
    "mcp_crawl": Permission.KNOWLEDGE_WRITE,
    "map_site": Permission.KNOWLEDGE_WRITE,
    # --- desktop/vnc: observing is the baseline; driving input is not ---
    "desktop_mouse_click": Permission.MCP_DESKTOP_CONTROL,
    "desktop_keyboard_type": Permission.MCP_DESKTOP_CONTROL,
    "desktop_control_status": Permission.MCP_DESKTOP_CONTROL,
    # --- redis: reads are the baseline; these mutate or expose the server ---
    #
    # These keys are the tools' real names. The blocklist they replace matched by
    # *substring* ("client_list" in "redis_client_list"), which hid the mismatch:
    # exact lookup here found nothing, so every redis tool read as undeclared.
    "redis_set": Permission.MCP_DATABASE_WRITE,
    "redis_delete": Permission.MCP_DATABASE_WRITE,
    "redis_hset": Permission.MCP_DATABASE_WRITE,
    "redis_lpush": Permission.MCP_DATABASE_WRITE,
    "redis_rpush": Permission.MCP_DATABASE_WRITE,
    "redis_xadd": Permission.MCP_DATABASE_WRITE,
    "redis_vector_create_index": Permission.MCP_DATABASE_WRITE,
    "redis_client_list": Permission.MCP_MANAGE,
    "redis_slowlog": Permission.MCP_MANAGE,
    # Declared explicitly to state that it is a *read*: the mutating-verb guard
    # reads "type" in `redis_type` as the input-driving verb from
    # `desktop_keyboard_type`. It returns a key's type and changes nothing.
    "redis_type": Permission.MCP_DATABASE_READ,
    # The remaining blocklist patterns — config_set, config_rewrite, debug,
    # flushdb, flushall — name no tool the redis bridge currently registers, so
    # the old gate protected nothing. Declared anyway: if any of them is ever
    # added, it arrives admin-only instead of arriving undeclared.
    "config_set": Permission.MCP_MANAGE,
    "config_rewrite": Permission.MCP_MANAGE,
    "debug": Permission.MCP_MANAGE,
    "flushdb": Permission.MCP_MANAGE,
    "flushall": Permission.MCP_MANAGE,
}


def required_permission(tool_name: str, bridge_name: str = "") -> Optional[Permission]:
    """Return the permission *tool_name* requires, or ``None`` if undeclared.

    ``None`` means "no declaration exists", which the enforcement stage treats as
    a refusal. It is deliberately not a permissive fallback: the whole defect in
    #13228 is that an undeclared tool was reachable.
    """
    exact = TOOL_PERMISSIONS.get(tool_name)
    if exact is not None:
        return exact
    return BRIDGE_DEFAULT_PERMISSIONS.get(bridge_name)


__all__ = [
    "BRIDGE_DEFAULT_PERMISSIONS",
    "TOOL_PERMISSIONS",
    "required_permission",
]
