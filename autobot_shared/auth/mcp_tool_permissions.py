# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical permission required by each MCP tool (#13228, #14494).

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
   **least**-privileged operation. It exists as defense-in-depth for a tool
   nobody has declared yet — never as the mechanism that decides one *should*
   stay undeclared. ``tools/lint/check_mcp_tool_permission_coverage.py`` (a
   required check, #14494) fails the moment a real bridge registers a tool with
   no exact entry here, which is what makes falling through to this baseline a
   CI-time event rather than a silent grant.

**#14523 (stage 3) — deny-by-default at runtime, closing the gap #14521's
security review found in #14494.** Before this, ``required_permission()``
default-allowed in both branches it could return: a tool absent from
``TOOL_PERMISSIONS`` on a *known* bridge fell through to
``BRIDGE_DEFAULT_PERMISSIONS`` (a real, grantable read permission, not a
denial), and a tool on an *unknown* bridge resolved to ``None``, which
``PermissionEnforcementExtension`` treated as "legacy — allow through" with no
check at all. Both branches now return ``None`` for any tool absent from
``TOOL_PERMISSIONS``, known bridge or not, and
``PermissionEnforcementExtension.on_before_tool_execute`` refuses on ``None``
instead of waving it through (see that module).

This was safe to flip only because #14494 already proved the precondition:
every tool the eleven governed bridges register carries an exact
``TOOL_PERMISSIONS`` entry (measured independently at #14523 time: 104 live
tools, 0 undeclared, 0 name collisions across bridges — see
``tools/lint/check_mcp_tool_permission_coverage.py``, still the required
check that keeps it true). ``BRIDGE_DEFAULT_PERMISSIONS`` no longer grants
anything at runtime; it stays as the registry ``test_every_bridge_has_a_default``
checks a new bridge into before any of its tools can be declared, and as the
source for the coverage checker's per-bridge discovery floors.

**#14494 — every tool this system knows about carries an exact entry below.**
The under-grant guard used to infer "mutating" from a hand-written verb list
(``write``, ``delete``, ``click`` …) matched against a tool's *name*; a
differently-named mutating tool (``select``, and — found by this pass —
``intercept_api`` and ``desktop_special_key``) inherited its bridge's read-level
default and nothing failed. There is no verb list anymore: every tool a bridge
registers today is declared here explicitly, so classification is a property of
the tool, not a guess from its name. ``_DECLARED_AHEAD_OF_TIME`` below is the
only sanctioned exception, and only for a tool that does not exist yet.

**This module only describes; it does not execute a check itself.** Stage 1
attached the resolved value to the registry entry so it could be inspected and
logged. ``PermissionEnforcementExtension`` (stage 3, #14523) is what turns the
``None`` this module now returns for an undeclared tool into an actual refusal;
``MCPDispatcher.dispatch()`` also acts on the same canonical resolution (via
``_would_deny``) rather than the retired ``_ADMIN_ONLY_TOOLS`` substring list.
"""

from typing import Dict, Optional

from autobot_shared.auth.permissions import Permission

# The twelve bridges this system governs (#14586 added manual_mcp), and the
# least-privileged operation each offers. #14523: no longer consulted by
# ``required_permission()`` as a runtime fallback grant — an undeclared tool
# is refused regardless of bridge. Retained as the registry
# ``test_every_bridge_has_a_default`` requires a new bridge to join before
# any of its tools can be declared, and as the source for the coverage
# checker's per-bridge discovery floors
# (``tools/lint/check_mcp_tool_permission_coverage.py``).
BRIDGE_DEFAULT_PERMISSIONS: Dict[str, Permission] = {
    "browser_mcp": Permission.MCP_BROWSER_READ,
    "database_mcp": Permission.MCP_DATABASE_READ,
    "filesystem_mcp": Permission.FILES_VIEW,
    "git_mcp": Permission.MCP_GIT_READ,
    "http_client_mcp": Permission.MCP_HTTP_READ,
    "knowledge_mcp": Permission.KNOWLEDGE_READ,
    # #14586: the twelfth bridge -- man page / doc-index lookup is read-only,
    # so MCP_READ (held by every role above READONLY) is the correct baseline.
    "manual_mcp": Permission.MCP_READ,
    "prometheus_mcp": Permission.MCP_METRICS_READ,
    # #13228: missed on the first pass, which made all 25 redis tools resolve to
    # "undeclared" — including the seven the blocklist already knew about.
    "redis_mcp": Permission.MCP_DATABASE_READ,
    "sequential_thinking_mcp": Permission.AGENT_EXECUTE,
    "structured_thinking_mcp": Permission.AGENT_EXECUTE,
    "vnc_mcp": Permission.MCP_DESKTOP_READ,
}

# Tool names declared ahead of a tool actually existing. Each is a real gap in
# the old seven-substring blocklist — a pattern like "flushall" that matched no
# tool the bridge registers today — kept declared so that if the tool is ever
# added it arrives at its intended permission instead of arriving undeclared.
#
# `tools/lint/check_mcp_tool_permission_coverage.py` treats every OTHER
# `TOOL_PERMISSIONS` entry as required to name a tool some bridge currently
# registers — that is what catches a declaration stranded by a rename (#14494
# found exactly one: `intercept_requests`, for a tool renamed `intercept_api`
# with nothing left pointing at the live name). This set is the only exemption
# from that reverse check, and it is asserted against the live scan in
# `mcp_tool_permissions_test.py` so a rename or removal cannot silently turn a
# "not yet built" declaration into a second stranded one.
_DECLARED_AHEAD_OF_TIME: Dict[str, str] = {
    "config_set": "redis_mcp",
    "config_rewrite": "redis_mcp",
    "debug": "redis_mcp",
    "flushdb": "redis_mcp",
    "flushall": "redis_mcp",
    # filesystem_mcp registers no `delete_file` tool today; declared ahead of
    # time so a future one arrives at FILES_DELETE rather than undeclared.
    "delete_file": "filesystem_mcp",
}

# Exact tool names that need more than their bridge's baseline. Everything here
# either changes state, leaves the machine, or reads something the baseline
# grant does not cover.
TOOL_PERMISSIONS: Dict[str, Permission] = {
    # --- browser: observation is the baseline; driving the page is not ---
    "browser_state": Permission.MCP_BROWSER_READ,
    "click": Permission.MCP_BROWSER_CONTROL,
    "click_index": Permission.MCP_BROWSER_CONTROL,
    "fill": Permission.MCP_BROWSER_CONTROL,
    "fill_index": Permission.MCP_BROWSER_CONTROL,
    "get_attribute": Permission.MCP_BROWSER_READ,
    "get_text": Permission.MCP_BROWSER_READ,
    "hover": Permission.MCP_BROWSER_CONTROL,
    "hover_index": Permission.MCP_BROWSER_CONTROL,
    # #14469: `select` changes a dropdown's value same as click/fill do — its
    # name carried none of the mutating verbs the retired name-matching guard
    # scanned for, so it inherited the bridge's read-level default silently.
    "select": Permission.MCP_BROWSER_CONTROL,
    "select_index": Permission.MCP_BROWSER_CONTROL,
    # `evaluate` runs caller-supplied JavaScript in the page — the strongest
    # thing this bridge can do, and it read as an ordinary user tool before.
    "evaluate": Permission.MCP_BROWSER_CONTROL,
    # #14494: the tool is `intercept_api`, not `intercept_requests` — the name
    # this entry carried until this pass. `intercept_api` injects an interceptor
    # script into the page on every navigation (`page.add_init_script`, the same
    # category of action as `evaluate`), and the stale name meant the live tool
    # had never actually been declared: it inherited MCP_BROWSER_READ.
    "intercept_api": Permission.MCP_BROWSER_CONTROL,
    "navigate": Permission.MCP_BROWSER_READ,
    "page_snapshot": Permission.MCP_BROWSER_READ,
    "screenshot": Permission.MCP_BROWSER_READ,
    "wait_for_selector": Permission.MCP_BROWSER_READ,
    # --- database: reads are the baseline; anything that can mutate is not ---
    "database_describe_schema": Permission.MCP_DATABASE_READ,
    "database_execute": Permission.MCP_DATABASE_WRITE,
    "database_list_databases": Permission.MCP_DATABASE_READ,
    "database_list_tables": Permission.MCP_DATABASE_READ,
    "database_query": Permission.MCP_DATABASE_READ,
    "database_statistics": Permission.MCP_DATABASE_READ,
    # --- http: a GET/HEAD is a read; the rest send a body or change state ---
    "http_delete": Permission.MCP_HTTP_WRITE,
    "http_get": Permission.MCP_HTTP_READ,
    "http_head": Permission.MCP_HTTP_READ,
    "http_patch": Permission.MCP_HTTP_WRITE,
    "http_post": Permission.MCP_HTTP_WRITE,
    "http_put": Permission.MCP_HTTP_WRITE,
    # --- filesystem: FILES_VIEW is the baseline; these write or destroy ---
    "create_directory": Permission.FILES_UPLOAD,
    "directory_tree": Permission.FILES_VIEW,
    "edit_file": Permission.FILES_UPLOAD,
    "get_file_info": Permission.FILES_VIEW,
    "list_allowed_directories": Permission.FILES_VIEW,
    "list_directory": Permission.FILES_VIEW,
    "list_directory_with_sizes": Permission.FILES_VIEW,
    "move_file": Permission.FILES_UPLOAD,
    "read_media_file": Permission.FILES_VIEW,
    "read_multiple_files": Permission.FILES_VIEW,
    "read_text_file": Permission.FILES_VIEW,
    "search_files": Permission.FILES_VIEW,
    "write_file": Permission.FILES_UPLOAD,
    # --- git: every registered tool reads the repository; nothing mutates it ---
    "git_blame": Permission.MCP_GIT_READ,
    "git_branch": Permission.MCP_GIT_READ,
    "git_diff": Permission.MCP_GIT_READ,
    "git_log": Permission.MCP_GIT_READ,
    "git_show": Permission.MCP_GIT_READ,
    "git_status": Permission.MCP_GIT_READ,
    # --- knowledge: reading is the baseline; ingesting is a write ---
    "add_to_knowledge_base": Permission.KNOWLEDGE_WRITE,
    "crawl_site": Permission.KNOWLEDGE_WRITE,
    "extract_structured_data": Permission.KNOWLEDGE_READ,
    "get_knowledge_stats": Permission.KNOWLEDGE_READ,
    "langchain_qa_chain": Permission.KNOWLEDGE_READ,
    # #14536: map_site only enumerates URLs (sitemap.xml parse, or a BFS crawl
    # that reads links without fetching bodies for ingestion — see
    # web_fetch/site_mapper.py). It never calls the knowledge-base write path
    # crawl_site does, so it takes the read grant tool_policy.py already treats
    # it as auto-approvable under.
    "map_site": Permission.KNOWLEDGE_READ,
    # Found by the guard's first run against the real bridges (#13228): mcp_crawl
    # registers a WebCrawlerConnector and ingests, so inheriting KNOWLEDGE_READ
    # would have under-granted it.
    "mcp_crawl": Permission.KNOWLEDGE_WRITE,
    # #14494: `operation` can be "flush", "reindex" or "backup" as well as
    # "info" — a single tool whose worst-case action can empty the vector store,
    # currently undeclared and therefore reachable with mere KNOWLEDGE_READ.
    "redis_vector_operations": Permission.KNOWLEDGE_MANAGE,
    "scrape_url": Permission.KNOWLEDGE_READ,
    "search_knowledge_base": Permission.KNOWLEDGE_READ,
    "summarize_knowledge_topic": Permission.KNOWLEDGE_READ,
    "vector_similarity_search": Permission.KNOWLEDGE_READ,
    # --- prometheus: every registered tool is a metrics/health read ---
    "get_service_health": Permission.MCP_METRICS_READ,
    "get_system_metrics": Permission.MCP_METRICS_READ,
    "get_vm_metrics": Permission.MCP_METRICS_READ,
    "list_available_metrics": Permission.MCP_METRICS_READ,
    "query_metric": Permission.MCP_METRICS_READ,
    "query_range": Permission.MCP_METRICS_READ,
    # --- desktop/vnc: observing is the baseline; driving input is not ---
    "check_vnc_status": Permission.MCP_DESKTOP_READ,
    "desktop_control_status": Permission.MCP_DESKTOP_CONTROL,
    "desktop_keyboard_type": Permission.MCP_DESKTOP_CONTROL,
    "desktop_mouse_click": Permission.MCP_DESKTOP_CONTROL,
    "desktop_observe_state": Permission.MCP_DESKTOP_READ,
    "desktop_screenshot": Permission.MCP_DESKTOP_READ,
    # #14494: sends key combinations (Return, Escape, ctrl+c, alt+tab …) to the
    # desktop — the same category as desktop_keyboard_type — and was undeclared,
    # so it inherited MCP_DESKTOP_READ.
    "desktop_special_key": Permission.MCP_DESKTOP_CONTROL,
    "get_browser_vnc_context": Permission.MCP_DESKTOP_READ,
    "observe_vnc_activity": Permission.MCP_DESKTOP_READ,
    # --- redis: reads are the baseline; these mutate or expose the server ---
    #
    # These keys are the tools' real names. The blocklist they replaced matched
    # by *substring* ("client_list" in "redis_client_list"), which hid the
    # mismatch: exact lookup here found nothing, so every redis tool read as
    # undeclared.
    "redis_client_list": Permission.MCP_MANAGE,
    "redis_dbsize": Permission.MCP_DATABASE_READ,
    "redis_delete": Permission.MCP_DATABASE_WRITE,
    "redis_get": Permission.MCP_DATABASE_READ,
    "redis_hget": Permission.MCP_DATABASE_READ,
    "redis_hgetall": Permission.MCP_DATABASE_READ,
    "redis_hset": Permission.MCP_DATABASE_WRITE,
    "redis_hybrid_search": Permission.MCP_DATABASE_READ,
    "redis_lpush": Permission.MCP_DATABASE_WRITE,
    "redis_lrange": Permission.MCP_DATABASE_READ,
    "redis_memory_stats": Permission.MCP_DATABASE_READ,
    "redis_rpush": Permission.MCP_DATABASE_WRITE,
    "redis_scan_keys": Permission.MCP_DATABASE_READ,
    "redis_server_info": Permission.MCP_DATABASE_READ,
    "redis_set": Permission.MCP_DATABASE_WRITE,
    "redis_slowlog": Permission.MCP_MANAGE,
    "redis_stream_health": Permission.MCP_DATABASE_READ,
    "redis_ttl": Permission.MCP_DATABASE_READ,
    # Declared explicitly to state that it is a *read*: the retired name-matching
    # guard read "type" in `redis_type` as the input-driving verb from
    # `desktop_keyboard_type`. It returns a key's type and changes nothing.
    "redis_type": Permission.MCP_DATABASE_READ,
    "redis_vector_create_index": Permission.MCP_DATABASE_WRITE,
    "redis_vector_index_info": Permission.MCP_DATABASE_READ,
    "redis_vector_search": Permission.MCP_DATABASE_READ,
    "redis_xadd": Permission.MCP_DATABASE_WRITE,
    "redis_xrange": Permission.MCP_DATABASE_READ,
    "redis_zrange": Permission.MCP_DATABASE_READ,
    # The blocklist patterns with no live tool today. See
    # `_DECLARED_AHEAD_OF_TIME` above — this bridge's baseline is already the
    # weakest tier, so admin-only is the correct grant if any of them ships.
    "config_set": Permission.MCP_MANAGE,
    "config_rewrite": Permission.MCP_MANAGE,
    "debug": Permission.MCP_MANAGE,
    "flushdb": Permission.MCP_MANAGE,
    "flushall": Permission.MCP_MANAGE,
    # --- filesystem: declared ahead of a tool that does not exist yet ---
    "delete_file": Permission.FILES_DELETE,
    # --- sequential/structured thinking: single-tier bridges (#14494) ---
    # Neither bridge exposes a stronger grant than AGENT_EXECUTE, so an
    # undeclared tool here cannot under-grant relative to its default — these
    # entries exist so the coverage guard has an exact answer for every real
    # tool, not because the value differs from the baseline.
    "sequential_thinking": Permission.AGENT_EXECUTE,
    "clear_history": Permission.AGENT_EXECUTE,
    "generate_summary": Permission.AGENT_EXECUTE,
    "process_thought": Permission.AGENT_EXECUTE,
    # --- manual: single-tier, read-only bridge (#14586) ---
    # All three tools read local man pages / a cached doc index via a fixed
    # argument-list subprocess (no shell=True) -- nothing here writes state or
    # leaves the host, so none needs more than the bridge's own baseline.
    # Declared explicitly (not left to the default) so the coverage guard has
    # an exact entry for every live tool, matching every other governed bridge.
    "lookup_man_page": Permission.MCP_READ,
    "search_man_pages": Permission.MCP_READ,
    "get_doc_index": Permission.MCP_READ,
}


def required_permission(tool_name: str, bridge_name: str = "") -> Optional[Permission]:
    """Return the permission *tool_name* requires, or ``None`` if undeclared (#14523).

    Deny-by-default: an exact ``TOOL_PERMISSIONS`` entry is the only way a tool
    resolves to a permission. Everything else returns ``None`` — a tool on one
    of the twelve governed bridges with no exact entry included, not only a
    tool on a bridge this module has never heard of. Before #14523 the known-
    bridge case fell through to ``BRIDGE_DEFAULT_PERMISSIONS`` and granted a
    real read permission instead of refusing; that fallback is retired here.
    ``PermissionEnforcementExtension.on_before_tool_execute`` refuses on
    ``None`` rather than treating it as a legacy allow — see that module.

    *bridge_name* is kept for call-site symmetry with callers that already
    know a tool's bridge (``mcp_registry._build_tool_entry``,
    ``_handle_browser_tool``); it no longer changes what this function
    returns. #14494's required check is what keeps the precondition this
    relies on true: every tool a governed bridge registers today carries an
    exact entry, so nothing that was reachable before #14523 loses its grant.
    """
    return TOOL_PERMISSIONS.get(tool_name)


__all__ = [
    "BRIDGE_DEFAULT_PERMISSIONS",
    "TOOL_PERMISSIONS",
    "required_permission",
]
