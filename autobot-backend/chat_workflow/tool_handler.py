# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tool and command handling for chat workflow.

Handles terminal tool initialization, command execution, tool call parsing,
and approval workflows.
"""

from __future__ import annotations

import ast
import asyncio
import html
import json
import re
import uuid
from typing import TYPE_CHECKING, Any, AsyncIterator

from async_chat_workflow import WorkflowMessage
from autobot_shared.auth.mcp_tool_permissions import required_permission
from autobot_shared.auth.permissions import Permission
from autobot_shared.env_utils import env_flag, env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.tool_catalogue import APPROVAL_CATEGORY_TOOLS, match_tool_name
from chat_workflow.browser_tool_handler import (
    extract_browser_image,
    format_browser_action_text,
    format_browser_result,
    format_page_state_block,
    handle_browser_tool,
    record_browser_success,
    validate_browser_params,
)
from chat_workflow.compose_tool_handler import (
    build_compose_dispatch,
    compose_auto_approvable,
    compose_gate_refusal_msg,
    compose_gate_request_msg,
    compose_result_message,
    compose_shim_snapshot,
    execute_compose,
    guard_compose,
    persist_compose_approval,
    poll_compose_approval,
    reject_delegated_compose,
)
from chat_workflow.tool_call_grammar import TOOL_CALL_PATTERN
from chat_workflow.tool_dispatch_guards import (
    enforce_config_protection,
    enforce_fact_forcing,
    enforce_forbidden_work,
    enforce_pre_action_verifier,
    enforce_repetition,
    enforce_work_item_approval,
)
from chat_workflow.tool_permission_gate import permission_denial
from llc.agent_tools import LLC_TOOL_NAMES, LLC_TOOL_SCHEMAS, LLCToolError, dispatch_llc_tool
from tools.code_interpreter import CODE_INTERPRETER_SCHEMA
from utils.errors import RepairableException

if TYPE_CHECKING:
    from .models import LLMIterationContext

# Import hook emitters (Issue #4261)
from chat_workflow.llm_handler import (
    _emit_after_tool_execute,
    _emit_before_tool_execute,
    _emit_tool_error,
)
from chat_workflow.session_handler import (
    _emit_approval_received,
    _emit_approval_required,
)

logger = get_logger(__name__)

# GH#11568: compose tool feature flag. The auto-approve/poll-interval tuning
# constants and CODEEXEC_READONLY_TOOLS moved to compose_tool_handler.py
# (#14491) with the functions that are their only readers.
CODEEXEC_ENABLED: bool = env_flag("AUTOBOT_CODEEXEC_ENABLED", default=False)
CODEEXEC_MAX_SCRIPT_RETRIES: int = env_int("AUTOBOT_CODEEXEC_MAX_SCRIPT_RETRIES", default=1)

# Issue #4482: Default retry count for schema self-correction loop.
_DEFAULT_SCHEMA_RETRIES = 3


def _format_schema_validation_errors(errors: list) -> str:
    """Format jsonschema ValidationError list into a concise field-level message.

    Args:
        errors: List of jsonschema.ValidationError instances.

    Returns:
        Human-readable error string listing each field and its problem.
    """
    lines = []
    for err in errors:
        field = ".".join(str(p) for p in err.absolute_path) or "<root>"
        lines.append(f"  - {field}: {err.message}")
    return "Tool argument validation failed:\n" + "\n".join(lines)


def validate_tool_arguments(tool_name: str, arguments: dict, schema: dict) -> dict | None:
    """Validate *arguments* against *schema* using jsonschema.

    Issue #4482: Central validation helper used by the schema self-correction
    retry loop.  Returns None on success, or a structured error dict on failure
    so the caller can feed it back to the model as a tool_result.

    Args:
        tool_name: Name of the tool (for context in the error message).
        arguments: The argument dict provided by the LLM.
        schema: JSON Schema dict (typically the tool's ``input_schema``).

    Returns:
        None when valid, or ``{"error": "...", "schema_validation_failed": True}``
        when invalid.
    """
    try:
        import jsonschema

        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(arguments), key=lambda e: list(e.path))
        if errors:
            msg = _format_schema_validation_errors(errors)
            logger.info(
                "[Issue #4482] Schema validation failed for tool %s: %s",
                tool_name,
                msg,
            )
            return {"error": msg, "schema_validation_failed": True, "tool": tool_name}
        return None
    except Exception as exc:
        # If jsonschema itself fails (e.g. bad schema), log and continue without
        # blocking execution — a broken schema should not prevent tool dispatch.
        logger.warning("[Issue #4482] Could not run schema validation for %s: %s", tool_name, exc)
        return None


# Issue #4726: Named schema constants — one per tool, single source of truth.
# Browser tools and web_search have no dedicated tools/ module; constants are
# defined here alongside BROWSER_TOOL_NAMES so they stay co-located with the
# routing logic.  execute_command is also defined here for the same reason.
EXECUTE_COMMAND_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "command": {"type": "string"},
        "host": {"type": "string"},
    },
    "required": ["command"],
}

READ_SPILLED_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "anchor": {
            "type": "string",
            "description": (
                "The anchor from a spilled tool result's note, e.g. " "'autobot:spill:<run>:<tool>:<digest>'."
            ),
        },
        "offset": {
            "type": "integer",
            "description": "Character offset to read from. Page forward while the reply reports has_more.",
        },
        "limit": {
            "type": "integer",
            "description": ("Characters to return. Capped server-side — a window, not the whole artifact."),
        },
    },
    "required": ["anchor"],
}

#: What to tell the model when an anchor does not resolve, by reason.
#: Module-level rather than rebuilt per call.
_SPILL_MISS_ADVICE: dict[str, str] = {
    # Bad offset/limit — the model can fix this itself, so mirror the
    # self-correction hint the schema gate gives.
    "invalid_window": "offset and limit must be integers. Retry this anchor with valid values.",
    # No run is bound to this context: an anchor cannot resolve here at all,
    # and a different anchor would fare no better.
    "no_run_bound": "No run is bound to this context, so no spilled output is readable. Do not retry.",
    # The artifact is genuinely gone or never existed.
    "not_found": "Do not retry this anchor.",
}

#: The default, for a miss whose cause the reader could not determine.
#:
#: `read_spilled` swallows every exception into `None`, and a cross-run refusal
#: returns `None` too, so an unknown reason covers a truncated artifact mid-write
#: (spill_if_oversized writes with a bare write_text, no temp+rename, to a
#: content-addressed path a re-spill rewrites), a transient OSError, a
#: PermissionError, and a run-scope refusal. In every one of those the output is
#: still on disk. Telling the model "do not retry" there is a permanent verdict
#: on a cause nobody established — the shape this whole issue is about.
_SPILL_MISS_UNKNOWN_ADVICE = (
    "The read did not report why it failed. This may be transient — retrying once is reasonable."
)

WEB_SEARCH_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "fetch_full": {
            "type": "boolean",
            "description": (
                "When true, fetches the full markdown of each result page "
                "in addition to returning search snippets. Default false."
            ),
        },
        "max_pages": {
            "type": "integer",
            "description": (
                "Maximum number of search results to return. Applies to both "
                "snippet mode (fetch_full=false) and full-fetch mode "
                "(fetch_full=true). Default 5 (#7479)."
            ),
            "minimum": 1,
            "maximum": 10,
        },
    },
    "required": ["query"],
}

# Issue #7509: Web research tool schemas — scrape, crawl, map, extract.
# Agents have admin-grade power: no server-side caps on depth/pages/robots.
SCRAPE_URL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Absolute URL to fetch and convert to markdown."},
        "render": {
            "type": "string",
            "enum": ["auto", "fast", "playwright"],
            "default": "auto",
            "description": "Render mode: auto (Jina+BS4+Playwright), fast (Jina+BS4), playwright (JS render).",
        },
        "preview": {
            "type": "boolean",
            "default": False,
            "description": (
                "Return only the page's character count and a short leading snippet "
                "instead of the full body. Use to judge relevance cheaply, then re-call "
                "with preview=false to expand the page you actually need."
            ),
        },
    },
    "required": ["url"],
}

CRAWL_SITE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "seed_urls": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Starting URLs for the BFS crawl.",
        },
        "max_depth": {
            "type": "integer",
            "default": 1,
            "description": "Link-hop depth (1 = seed URLs only, 2 = seeds + 1 hop).",
        },
        "max_pages": {
            "type": "integer",
            "default": 100,
            "description": "Hard cap on total pages fetched across all seeds.",
        },
        "respect_robots": {
            "type": "boolean",
            "default": True,
            "description": "Honour robots.txt. Set false to override.",
        },
        "ingest": {
            "type": "boolean",
            "default": False,
            "description": "Write successful pages to the knowledge base.",
        },
        "same_origin": {
            "type": "boolean",
            "default": True,
            "description": "Restrict crawl to same scheme+host per seed.",
        },
        "preview": {
            "type": "boolean",
            "default": True,
            "description": (
                "Render each crawled page as its character count plus a short leading "
                "snippet rather than a large body dump. Leave on to survey many pages "
                "cheaply, then expand a specific one with scrape_url."
            ),
        },
    },
    "required": ["seed_urls"],
}

MAP_SITE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "description": "Domain to map (bare or with scheme, e.g. 'example.com').",
        },
        "max_urls": {
            "type": "integer",
            "default": 500,
            "description": "Hard cap on returned URLs.",
        },
        "respect_robots": {
            "type": "boolean",
            "default": True,
            "description": "Honour robots.txt during crawl fallback.",
        },
    },
    "required": ["domain"],
}

CONTENT_REACH_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "enum": ["web_search", "web_page", "youtube", "reddit", "social"],
            "description": "Which content source chain to use.",
        },
        "query": {
            "type": "string",
            "description": "Search query (web_search, reddit, youtube search).",
        },
        "url": {
            "type": "string",
            "description": "Target URL (web_page, youtube, reddit, social).",
        },
        "limit": {
            "type": "integer",
            "default": 5,
            "description": "Max results for search sources.",
        },
    },
    "required": ["source"],
}

EXTRACT_STRUCTURED_DATA_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Absolute URL to fetch."},
        "schema": {
            "type": "object",
            "description": "JSON Schema (draft 2020-12) describing the desired output.",
        },
        "render": {
            "type": "string",
            "enum": ["auto", "fast", "playwright"],
            "default": "auto",
            "description": "Render mode.",
        },
    },
    "required": ["url", "schema"],
}

# Issue #11540: goal-directed extraction from the *current* live page (the
# session already sitting behind a login / mid-form, reached via navigate +
# click_index/fill_index) — unlike extract_structured_data above, which
# always re-fetches the URL from scratch and so can never see that state.
EXTRACT_CONTENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "goal": {
            "type": "string",
            "description": (
                "What to extract from the current live page, e.g. 'the order "
                "confirmation number' or 'all product prices listed here'. "
                "Extraction is goal-directed — not a raw page dump."
            ),
        },
    },
    "required": ["goal"],
}

# Issue #11540: hardcoded, read-only JS for extract_content's live-page
# snapshot — plain property reads (no assignment), so it can never match a
# BLOCKED_JS_PATTERNS entry (those all target writes: ``.innerHTML =``,
# ``window.location =``, cookie/storage access, etc.). Passed straight to the
# browser VM's existing ``evaluate`` action, not a new browser primitive.
_EXTRACT_CONTENT_SNAPSHOT_SCRIPT = (
    "({url: window.location.href, title: document.title, html: document.documentElement.outerHTML})"
)

# Browser tool schemas — co-located with BROWSER_TOOL_NAMES (Issue #4726).
NAVIGATE_SCHEMA: dict = {
    "type": "object",
    "properties": {"url": {"type": "string"}},
    "required": ["url"],
}

CLICK_SCHEMA: dict = {
    "type": "object",
    "properties": {"selector": {"type": "string"}},
    "required": ["selector"],
}

FILL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "selector": {"type": "string"},
        "value": {"type": "string"},
    },
    "required": ["selector", "value"],
}

SELECT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "selector": {"type": "string"},
        "value": {"type": "string"},
    },
    "required": ["selector", "value"],
}

HOVER_SCHEMA: dict = {
    "type": "object",
    "properties": {"selector": {"type": "string"}},
    "required": ["selector"],
}

SCREENSHOT_SCHEMA: dict = {
    "type": "object",
    "properties": {},
}

EVALUATE_SCHEMA: dict = {
    "type": "object",
    "properties": {"script": {"type": "string"}},
    "required": ["script"],
}

GET_TEXT_SCHEMA: dict = {
    "type": "object",
    "properties": {"selector": {"type": "string"}},
    "required": ["selector"],
}

GET_ATTRIBUTE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "selector": {"type": "string"},
        "attribute": {"type": "string"},
    },
    "required": ["selector", "attribute"],
}

WAIT_FOR_SELECTOR_SCHEMA: dict = {
    "type": "object",
    "properties": {"selector": {"type": "string"}},
    "required": ["selector"],
}

# Issue #11537: indexed interactive-element schemas. OpenManus numbers every
# interactive element on the page so the model clicks/fills by index instead
# of inventing a CSS selector — the index below is resolved to a concrete
# element server-side (autobot-browser-worker/element-index.js).
#
# `expected_element_count` (optional, from a prior browser_state's
# `element_count`) is the stale-index guard: if the live element count no
# longer matches, the worker rejects the call instead of silently acting on
# whatever now sits at that index (review #11538 MINOR 3).
_EXPECTED_ELEMENT_COUNT_FIELD = {
    "type": "integer",
    "description": (
        "Optional: element_count from the browser_state call this index was chosen against. "
        "If the live page's element count no longer matches, the action is rejected instead of "
        "silently acting on the wrong element — re-fetch browser_state and retry."
    ),
}

CLICK_INDEX_SCHEMA: dict = {
    "type": "object",
    "description": "Click an interactive element by its numbered index from the page's element menu.",
    "properties": {
        "index": {"type": "integer", "description": "Element index from the numbered element menu."},
        "timeout": {"type": "integer", "description": "Timeout in milliseconds", "default": 10000},
        "expected_element_count": _EXPECTED_ELEMENT_COUNT_FIELD,
    },
    "required": ["index"],
}

FILL_INDEX_SCHEMA: dict = {
    "type": "object",
    "description": "Fill an interactive element by its numbered index from the page's element menu.",
    "properties": {
        "index": {"type": "integer", "description": "Element index from the numbered element menu."},
        "value": {"type": "string", "description": "Value to fill into the element."},
        "timeout": {"type": "integer", "description": "Timeout in milliseconds", "default": 10000},
        "expected_element_count": _EXPECTED_ELEMENT_COUNT_FIELD,
    },
    "required": ["index", "value"],
}

SELECT_INDEX_SCHEMA: dict = {
    "type": "object",
    "description": "Select a dropdown option on an element identified by its numbered index.",
    "properties": {
        "index": {"type": "integer", "description": "Element index from the numbered element menu."},
        "value": {"type": "string", "description": "Value to select."},
        "expected_element_count": _EXPECTED_ELEMENT_COUNT_FIELD,
    },
    "required": ["index", "value"],
}

HOVER_INDEX_SCHEMA: dict = {
    "type": "object",
    "description": "Hover over an interactive element by its numbered index.",
    "properties": {
        "index": {"type": "integer", "description": "Element index from the numbered element menu."},
        "expected_element_count": _EXPECTED_ELEMENT_COUNT_FIELD,
    },
    "required": ["index"],
}

BROWSER_STATE_SCHEMA: dict = {
    "type": "object",
    "description": (
        "Get the current page state: URL, title, scroll info, and a numbered menu "
        "of interactive elements for use with click_index/fill_index/select_index/hover_index."
    ),
    "properties": {},
}

# Issue #4529: JSON Schema definitions for built-in tools dispatched directly
# (not via MCP).  Used by _validate_builtin_tool_arguments() so every dispatch
# path passes through validate_tool_arguments() before execution.
# Issue #4726: inline dicts replaced with named constants above; schema content
# is unchanged.
_BUILTIN_TOOL_SCHEMAS: dict[str, dict] = {
    "execute_command": EXECUTE_COMMAND_SCHEMA,
    "read_spilled_output": READ_SPILLED_OUTPUT_SCHEMA,
    "web_search": WEB_SEARCH_SCHEMA,
    "navigate": NAVIGATE_SCHEMA,
    "click": CLICK_SCHEMA,
    "fill": FILL_SCHEMA,
    "select": SELECT_SCHEMA,
    "hover": HOVER_SCHEMA,
    "screenshot": SCREENSHOT_SCHEMA,
    "evaluate": EVALUATE_SCHEMA,
    "get_text": GET_TEXT_SCHEMA,
    "get_attribute": GET_ATTRIBUTE_SCHEMA,
    "wait_for_selector": WAIT_FOR_SELECTOR_SCHEMA,
    # Issue #11537: indexed interactive-element actions.
    "click_index": CLICK_INDEX_SCHEMA,
    "fill_index": FILL_INDEX_SCHEMA,
    "select_index": SELECT_INDEX_SCHEMA,
    "hover_index": HOVER_INDEX_SCHEMA,
    "browser_state": BROWSER_STATE_SCHEMA,
    # Imported from tools.code_interpreter — single source of truth for the schema.
    # Issue #4561: was missing, causing code_interpreter args to bypass validation
    # (Issue #4562).  All future built-in tool schemas should follow this pattern:
    # define the schema constant in the tool module and import it here.
    "code_interpreter": CODE_INTERPRETER_SCHEMA["parameters"],
    # Issue #7509: Web research tools — direct internal dispatch via web_fetch package.
    "scrape_url": SCRAPE_URL_SCHEMA,
    "crawl_site": CRAWL_SITE_SCHEMA,
    "map_site": MAP_SITE_SCHEMA,
    "extract_structured_data": EXTRACT_STRUCTURED_DATA_SCHEMA,
    # Issue #11540: goal-directed extraction from the current live page.
    "extract_content": EXTRACT_CONTENT_SCHEMA,
    # #10932: Unified content_reach gateway (5 source chains).
    "content_reach": CONTENT_REACH_SCHEMA,
    # #11501: LLC board/CEO-chat work-object tools (create_task, update_goal,
    # request_approval, record_decision). Company-scoped; dispatched to the
    # existing llc/services. Merged below so they validate like any built-in.
    **LLC_TOOL_SCHEMAS,
}

# GH#11568: compose tool — sandboxed Python script with injectable RPC shims.
COMPOSE_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "program": {
            "type": "string",
            "description": (
                "Python program to execute. Import autobot_tools and call tool " "functions as async coroutines."
            ),
        },
        "description": {
            "type": "string",
            "description": "Human-readable description of what this program does.",
        },
    },
    "required": ["program"],
}

if CODEEXEC_ENABLED:
    _BUILTIN_TOOL_SCHEMAS["compose"] = COMPOSE_TOOL_SCHEMA


def _validate_builtin_tool_arguments(tool_name: str, tool_call: dict[str, Any]) -> WorkflowMessage | None:
    """Validate params for a direct-dispatch built-in tool. Issue #4529.

    Built-in tools use the ``params`` key (not ``arguments`` like MCP tools).
    Returns a WorkflowMessage error if validation fails, or None on success.
    The error message mirrors the pattern used in ``_try_mcp_dispatch()`` so
    the agent loop can feed it back as a tool_result for self-correction.
    """
    schema = _BUILTIN_TOOL_SCHEMAS.get(tool_name)
    if not schema:
        return None  # No schema defined — skip validation

    params = tool_call.get("params", {})
    schema_error = validate_tool_arguments(tool_name, params, schema)
    if schema_error is None:
        return None

    logger.info(
        "[Issue #4529] Schema validation failed for built-in tool %s: %s",
        tool_name,
        schema_error["error"],
    )
    return WorkflowMessage(
        type="tool_result",
        content=schema_error["error"],
        metadata={
            "tool_name": tool_name,
            "schema_validation_failed": True,
            "self_correction_hint": (
                f"Fix the argument errors above and retry '{tool_name}' " f"with corrected arguments."
            ),
        },
    )


# Issue #1368: Browser tool names that route to browser_mcp handlers.
# Exported (no leading underscore) so ToolRegistry can derive its list from this
# single source of truth rather than maintaining a duplicate. Issue #2609.
BROWSER_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "navigate",
        "click",
        "fill",
        "select",
        "hover",
        "screenshot",
        "evaluate",
        "get_text",
        "get_attribute",
        "wait_for_selector",
        # Issue #11537: indexed interactive-element actions.
        "click_index",
        "fill_index",
        "select_index",
        "hover_index",
        "browser_state",
    }
)

# Issue #7509: web research tools — direct internal dispatch via web_fetch.
WEB_RESEARCH_TOOL_NAMES: frozenset[str] = frozenset({"scrape_url", "crawl_site", "map_site", "extract_structured_data"})

# Issue #11540: goal-directed extraction from the browser session's *current*
# page — reads whatever the live DOM already shows, never re-fetches a URL.
LIVE_PAGE_EXTRACT_TOOL_NAMES: frozenset[str] = frozenset({"extract_content"})

# GH#11489: builtin tools sharing the uniform dispatch gate (invalid-call
# counter reset → Issue #4529 schema validation → handler). ``_builtin_route``
# maps each name to its handler, so adding a tool here needs no new branch at
# the ``_dispatch_tool_call`` seam.
_UNIFORM_BUILTIN_TOOLS: frozenset[str] = (
    BROWSER_TOOL_NAMES
    | WEB_RESEARCH_TOOL_NAMES
    | LIVE_PAGE_EXTRACT_TOOL_NAMES
    # #13919: read_spilled_output is dispatchable unconditionally, so a run that
    # spilled before AUTOBOT_TOOL_OUTPUT_SPILL was turned off can still resolve
    # its anchors — `read_spilled_window` does not consult the flag.
    #
    # This DOES leak into prompt content, contrary to an earlier version of this
    # comment: `_build_unknown_tool_error` derives `known_tools` from this set,
    # so a model that fumbles any tool name is told this one exists even with the
    # feature off. Accepted deliberately — the alternative is a flag-dependent
    # membership set, which would make routing depend on import-time env state
    # and is a worse trade than one extra name in an error hint. With the flag
    # off nothing spills, so following the hint reports not-found.
    | frozenset({"web_search", "execute_command", "read_spilled_output"})
)

# GH#11160: maps a declared approval category (a work item's
# ``requires_approval_before`` entry) to the tools that constitute that action. A
# tool is approval-gated only when the work item declared its category; names
# match by exact or prefix (e.g. ``deploy`` gates ``deploy_service``).
# GH#11206: sourced from the canonical tool catalogue (SSOT).
_APPROVAL_CATEGORY_TOOLS: dict[str, tuple[str, ...]] = APPROVAL_CATEGORY_TOOLS


def _approval_category_for(tool_name: str, declared: list[str]) -> str | None:
    """Return the declared category that gates *tool_name*, else None (GH#11160).

    GH#11206: uses the canonical ``match_tool_name`` with word-boundary matching
    (so ``deploy`` gates ``deploy_service`` but not ``deployment_status``). A false
    positive only ever adds an approval hold — the fail-safe direction — never a bypass.
    """
    for category in declared:
        if match_tool_name(tool_name, _APPROVAL_CATEGORY_TOOLS.get(category, ()), word_boundary=True):
            return category
    return None


# Issue #11693: the tool-call grammar (parse pattern + close-variant
# tolerance for #11545/#11552) is now the single canonical source of truth
# in tool_call_grammar.py, shared with chat_workflow/manager.py. Kept as a
# module-level alias here for backwards-compatible imports.
_TOOL_CALL_PATTERN = TOOL_CALL_PATTERN

# Issue #260: Security tool detection pattern for auto-parsing
_SECURITY_TOOL_PATTERN = re.compile(r"(nmap|nikto|gobuster|ffuf|masscan|nuclei|searchsploit)\b", re.IGNORECASE)

# Issue #665: Error classification patterns for _classify_command_error
# Format: (pattern_list, message_template, suggestion)
# pattern_list contains strings to check in combined error/stderr
_REPAIRABLE_ERROR_PATTERNS = (
    (
        ["no such file or directory", "file not found"],
        "File not found: {error}",
        "Create the file first, or check if the path exists using 'ls'",
    ),
    (
        ["permission denied", "access denied"],
        "Permission denied: {error}",
        "Try using sudo, or execute from a different directory with proper permissions",
    ),
    (
        ["command not found", "not recognized"],
        "Command not found: {cmd_name}",
        "Install the package that provides '{cmd_name}', or use an alternative command",
    ),
    (
        ["timeout", "timed out"],
        "Command timed out: {command}",
        "Break the operation into smaller steps, or increase the timeout",
    ),
    (
        ["connection refused", "network unreachable"],
        "Connection error: {error}",
        "Check network connectivity, verify the target host is running, and retry",
    ),
    (
        ["syntax error", "unexpected token"],
        "Syntax error in command: {error}",
        "Check the command syntax and escape special characters properly",
    ),
    (
        ["is a directory", "not a directory"],
        "Directory error: {error}",
        "Use the correct path type (file vs directory) for this operation",
    ),
    (
        ["no space left", "disk full"],
        "Disk space error: {error}",
        "Free up disk space by removing unnecessary files, then retry",
    ),
)

# Critical error patterns that should NOT be repairable
_CRITICAL_ERROR_PATTERNS = ["out of memory", "cannot allocate"]


def _parse_tool_args(raw: str) -> dict:
    """Parse tool call JSON args with a safe literal-parser fallback. (#4483)

    LLMs occasionally produce near-valid JSON with trailing commas, single
    quotes, or Python boolean/None literals that json.loads() rejects.
    ast.literal_eval is safe: it only accepts Python literal structures and
    raises ValueError/SyntaxError on anything else.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            result = ast.literal_eval(raw)  # noqa: S307 - literals only, safe
            if isinstance(result, dict):
                logger.warning("Tool args parsed via ast.literal_eval fallback" " — LLM produced near-valid JSON")
                return result
        except (ValueError, SyntaxError):
            pass
        raise


def _detect_and_store_security_output(command: str, output: str, session_id: str) -> None:
    """
    Detect security tool output and auto-parse findings.

    Issue #260: Automatically parses output from security tools (nmap, nikto, etc.)
    and stores findings in active assessments.

    Args:
        command: The executed command
        output: Command output
        session_id: Chat session ID
    """
    try:
        if not _SECURITY_TOOL_PATTERN.search(command):
            return

        from services.security_tool_parsers import parse_tool_output
        from services.security_workflow_manager import get_security_workflow_manager

        parsed = parse_tool_output(output)
        if not parsed or not parsed.get("hosts"):
            return

        workflow_mgr = get_security_workflow_manager()
        active_assessments = workflow_mgr.list_active_assessments()
        if not active_assessments:
            logger.debug(
                "Security tool detected but no active assessment for session %s",
                session_id,
            )
            return

        assessment_id = active_assessments[0].get("id")
        host_count = len(parsed.get("hosts", []))
        vuln_count = sum(len(h.get("vulnerabilities", [])) for h in parsed["hosts"])

        workflow_mgr.record_action(
            assessment_id=assessment_id,
            action_type="tool_execution",
            action_data={"command": command, "parsed_summary": parsed.get("summary")},
        )

        logger.info(
            "Auto-parsed %s output: %d hosts, %d vulns for assessment %s",
            _SECURITY_TOOL_PATTERN.search(command).group(1),
            host_count,
            vuln_count,
            assessment_id,
        )
    except Exception as e:
        logger.debug("Failed to auto-parse security output: %s", e)


def _match_repairable_error(combined: str, command: str, error: str) -> RepairableException | None:
    """Match error against repairable patterns (Issue #665: extracted helper).

    Args:
        combined: Lowercase combined error and stderr text
        command: The original command that failed
        error: Original error message

    Returns:
        RepairableException if a pattern matches, None otherwise
    """
    from utils.errors import RepairableException

    cmd_name = command.split()[0] if command else "command"
    format_vars = {"error": error, "cmd_name": cmd_name, "command": command}

    for patterns, message_template, suggestion in _REPAIRABLE_ERROR_PATTERNS:
        if any(p in combined for p in patterns):
            return RepairableException(
                message=message_template.format(**format_vars),
                suggestion=suggestion.format(**format_vars),
            )
    return None


def _record_failed_step(
    execution_results: list[dict[str, Any]] | None,
    command: str,
    result: dict[str, Any],
    error: str,
    stderr: str,
) -> None:
    """Record a failed command as a step the model can read (#14141).

    Without this a failing command was **absent** from the continuation prompt
    entirely: `_handle_command_error` never touched `execution_results`, and the
    `additional_response_parts` entry it does append is created locally in
    `execute_tool_calls` and never yielded. The model saw the steps before the
    failure, then nothing — no status, no output, no sign a command had run.

    `stdout` matters most here. The motivating case is a test runner writing its
    report to stdout and exiting non-zero, so the report is the one thing worth
    carrying and was the one thing being dropped.
    """
    if execution_results is None:
        return
    execution_results.append(
        {
            "command": command,
            "stdout": result.get("stdout", ""),
            "stderr": stderr,
            "return_code": result.get("return_code", 1),
            "status": "error",
            "error": error,
        }
    )


def _create_execution_result(command: str, host: str, result: dict[str, Any], approved: bool = False) -> dict[str, Any]:
    """Create standardized execution result record (Issue #315: extracted).

    Args:
        command: The command that was executed
        host: Target host
        result: Execution result dict
        approved: Whether user approved the command

    Returns:
        Standardized execution result dict for continuation loop
    """
    # #14141: `status` is derived from the exit code, not hardcoded. It used to
    # be the literal "success" regardless of `return_code`, and this dict feeds
    # `_format_execution_step`, which prints `- Status: {status}` straight into
    # the model's continuation prompt. So a command that failed was reported to
    # the model as having succeeded, with stderr as the only hint — and a test
    # runner writes its failure report to *stdout*, so the model saw a
    # full-looking report under "success" and no signal that the suite failed.
    #
    # Reachability, so nobody mistakes this for the protection: both call sites
    # are gated on ``status == "success"`` upstream (`_handle_approved_command`
    # at the approval branch, `_handle_successful_command` in
    # `_dispatch_command_by_status`), so this mapping cannot currently observe a
    # non-zero code. It is kept as a correct restatement of the invariant for
    # the day a caller stops gating -- not deleted, because a dict feeding the
    # model's prompt with a hardcoded "success" is exactly the defect that got
    # filed. The single *reachable* decision is
    # `command_executor._build_pty_result`, which every layer here propagates
    # rather than re-derives; that is where the invariant is asserted.
    return_code = result.get("return_code", 0)
    return {
        "command": command,
        "host": host,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "return_code": return_code,
        "status": _status_for_return_code(return_code),
        "approved": approved,
    }


def _status_for_return_code(return_code: Any) -> str:
    """Map an exit code to the status the model is shown (#14141).

    Only an exit code that is *known* to be 0 reports success. `None` — the
    shape an execution path produces when it never captured one — and anything
    unparseable both report ``error``, because "we do not know whether that
    worked" is far closer to failure than to success as far as the next turn is
    concerned. Reporting an unknown outcome as success is the defect this
    function exists to remove, and defaulting it would reintroduce it.
    """
    try:
        return "success" if int(return_code) == 0 else "error"
    except (TypeError, ValueError):
        logger.warning("[#14141] unusable return_code %r — reporting the step as error, not success", return_code)
        return "error"


def _build_mcp_approval_message(
    tool_name: str,
    bridge: str,
    raw_result: dict,
    execution_results: list[dict[str, Any]],
) -> WorkflowMessage:
    """Build a WorkflowMessage for MCP bridge approval requests (Issue #2622)."""
    approval_msg = raw_result.get("message", "This operation requires approval.")
    execution_results.append(
        {
            "tool": tool_name,
            "bridge": bridge,
            "result": approval_msg,
            "status": "approval_required",
        }
    )
    logger.info(
        "[Issue #2622] MCP approval required: tool=%s bridge=%s",
        tool_name,
        bridge,
    )
    return WorkflowMessage(
        type="tool_result",
        content=(
            f"[{bridge}] **Approval required:** {approval_msg}\n"
            "Ask the user to confirm, then retry with `approved: true` "
            "in the arguments."
        ),
        metadata={
            "tool_name": tool_name,
            "bridge": bridge,
            "mcp_dispatch": True,
            "approval_required": True,
        },
    )


async def _try_mcp_dispatch(
    tool_name: str,
    tool_call: dict[str, Any],
    execution_results: list[dict[str, Any]],
    role: str = "user",
    session_id: str = "",
    max_schema_retries: int = _DEFAULT_SCHEMA_RETRIES,
) -> WorkflowMessage | None:
    """Attempt to dispatch tool_name via the MCP registry. Issue #2513.

    Issue #4482: Validates arguments against the tool's input_schema before
    dispatch.  On failure the error is returned as a structured WorkflowMessage
    so the agent loop can feed it back as a tool_result and self-correct.
    The caller may retry up to *max_schema_retries* times (default 3).

    Args:
        tool_name: Name of the tool to dispatch.
        tool_call: Raw tool call dict from the LLM.
        execution_results: Accumulator list for execution results.
        role: Caller RBAC role forwarded to the dispatcher (#2629).
        session_id: Session identifier for hook invocation (#4261).
        max_schema_retries: Max allowed retries for schema self-correction (#4482).

    Returns a WorkflowMessage on success, or None if the tool is not found
    in the registry (so the caller can fall through to the unknown-tool error).
    """
    from services.mcp_dispatch import get_mcp_dispatcher

    dispatcher = get_mcp_dispatcher()
    if not dispatcher._cache_loaded:
        await dispatcher.refresh_tool_cache()

    tool = dispatcher.find_tool(tool_name)
    if tool is None:
        return None

    arguments = tool_call.get("arguments", {})

    # Issue #4482: Validate arguments against the tool's input_schema before
    # dispatching.  Return a structured error WorkflowMessage so the agent
    # loop can feed it back as a tool_result and retry.  The retry counter is
    # owned by the caller (agent loop); here we just surface the error clearly.
    input_schema = tool.get("input_schema", {})
    if input_schema:
        schema_error = validate_tool_arguments(tool_name, arguments, input_schema)
        if schema_error is not None:
            retries_left = max_schema_retries - tool_call.get("_schema_retry_count", 0)
            logger.info(
                "[Issue #4482] Schema validation error for %s (retries_left=%d): %s",
                tool_name,
                retries_left,
                schema_error["error"],
            )
            execution_results.append(
                {
                    "tool": tool_name,
                    "status": "schema_error",
                    "error": schema_error["error"],
                    "schema_validation_failed": True,
                    "retries_left": retries_left,
                }
            )
            return WorkflowMessage(
                type="tool_result",
                content=schema_error["error"],
                metadata={
                    "tool_name": tool_name,
                    "schema_validation_failed": True,
                    "retries_left": retries_left,
                    "self_correction_hint": (
                        f"Fix the argument errors above and retry '{tool_name}' "
                        f"with corrected arguments. {retries_left} attempt(s) remaining."
                    ),
                },
            )

    # Issue #4261: Wire BEFORE_TOOL_EXECUTE hook for MCP tools
    # Issue #14420: forward the tool's declared permission requirement
    # (#13228 stage 1, resolved onto the registry entry as
    # `required_permission`) and the caller's RBAC role so
    # PermissionEnforcementExtension has something real to decide against.
    should_execute = await _emit_before_tool_execute(
        tool_name,
        arguments,
        session_id,
        tool_permission=tool.get("required_permission"),
        user_role=role,
    )
    if not should_execute:
        logger.info(
            "[Issue #4261] Tool execution cancelled by BEFORE_TOOL_EXECUTE hook: %s",
            tool_name,
        )
        cancellation_metadata = {"tool_name": tool_name, "cancelled_by_hook": True}
        # Issue #14420 (review): the agent loop cannot otherwise tell a
        # permission denial from any other hook veto and may retry the same
        # call forever. A declared permission requirement is the only signal
        # available at this call site without deeper hook introspection - the
        # PermissionError detail itself correctly stays server-side.
        if tool.get("required_permission") is not None:
            cancellation_metadata["reason"] = "permission_denied"
        return WorkflowMessage(
            type="error",
            content=f"Tool execution cancelled: {tool_name}",
            metadata=cancellation_metadata,
        )

    try:
        mcp_result = await dispatcher.dispatch(tool_name, arguments, role=role)
        bridge = mcp_result.get("bridge", "unknown")
        success = mcp_result.get("success", False)
        raw_result = mcp_result.get("result", "")

        # Issue #2622: Detect approval_required from MCP bridges
        if isinstance(raw_result, dict) and raw_result.get("status") == "approval_required":
            return _build_mcp_approval_message(tool_name, bridge, raw_result, execution_results)

        result_text = str(raw_result)

        # Issue #4261: Wire AFTER_TOOL_EXECUTE hook to allow result modification
        result_text = await _emit_after_tool_execute(tool_name, result_text, session_id, {})

        execution_results.append(
            {
                "tool": tool_name,
                "bridge": bridge,
                "result": result_text,
                "status": "success" if success else "error",
            }
        )
        msg_type = "tool_result" if success else "error"
        logger.info(
            "[Issue #2513] MCP dispatch: tool=%s bridge=%s success=%s",
            tool_name,
            bridge,
            success,
        )
        return WorkflowMessage(
            type=msg_type,
            content=f"[{bridge}] {result_text}",
            metadata={"tool_name": tool_name, "bridge": bridge, "mcp_dispatch": True},
        )

    except Exception as e:
        # Issue #4261: Wire TOOL_ERROR hook to allow error handling/logging
        await _emit_tool_error(tool_name, e, session_id, {})
        logger.error(
            "[Issue #2513] MCP dispatch error for tool %s: %s",
            tool_name,
            e,
            exc_info=True,
        )
        raise


async def _fetch_single_page(entry: dict) -> dict:
    """Fetch full markdown for one search result entry. Issue #7404.

    Attaches ``markdown`` and ``fetch_error`` fields to the entry dict.
    On robots-policy block: markdown=None, fetch_error="robots_blocked".
    On any other failure: markdown=None, fetch_error=<error_code>.
    On success: markdown=<str>, fetch_error=None.
    Never raises — per-URL failures must not abort the whole fan-out.
    """
    from web_fetch import RenderMode, WebFetcher

    url = entry.get("url", "")
    if not url:
        return {**entry, "markdown": None, "fetch_error": "no_url"}
    try:
        result = await WebFetcher.fetch(url, render=RenderMode.AUTO)
        if result.success:
            return {**entry, "markdown": result.markdown, "fetch_error": None}
        error_code = result.error_code or "unknown"
        logger.debug("[Issue #7404] Fetch failed for %s: %s", url, error_code)
        return {**entry, "markdown": None, "fetch_error": error_code}
    except Exception as exc:
        logger.warning("[Issue #7404] Unexpected fetch error for %s: %s", url, exc)
        return {**entry, "markdown": None, "fetch_error": "unknown"}


async def _fetch_pages_concurrent(entries: list[dict], max_pages: int) -> list[dict]:
    """Fan out _fetch_single_page for up to max_pages entries. Issue #7404.

    Uses asyncio.gather so all fetches run concurrently. Individual failures
    are captured inside _fetch_single_page — this function always returns a
    full list of the same length as entries[:max_pages].
    """
    capped = entries[:max_pages]
    return list(await asyncio.gather(*(_fetch_single_page(e) for e in capped)))


def _format_full_search_results(query: str, entries: list[dict]) -> str:
    """Format enriched search entries (with markdown) into a human-readable string.

    Issue #7404. Entries that failed to fetch include a fetch_error note instead
    of the markdown body. The overall call always succeeds (partial failures OK).
    """
    lines = [f'Web search results for "{query}" (full page content):\n']
    for i, entry in enumerate(entries, 1):
        title = entry.get("title", "No title")
        url = entry.get("url", "")
        snippet = entry.get("snippet", entry.get("description", ""))
        lines.append(f"{i}. **{title}**\n   {url}\n   {snippet}")
        markdown = entry.get("markdown")
        fetch_error = entry.get("fetch_error")
        if markdown:
            lines.append(f"\n   --- Full page ---\n{markdown[:4000]}\n   --- End ---\n")
        elif fetch_error:
            lines.append(f"\n   [Page fetch failed: {fetch_error}]\n")
        else:
            lines.append("")
    return "\n".join(lines)


def _search_unavailable_message(query: str) -> str:
    """Actionable message when every search backend yields nothing (#11665).

    Flows straight into LLM context, so it stays one sentence and names the
    exact configuration that unlocks topic search instead of a silent "".
    """
    return (
        f'Web search for "{query}" returned no results because no search backend is available — '
        "configure SEARXNG_INSTANCE_URL or BRAVE_SEARCH_API_KEY (or make a Playwright browser "
        "reachable) to enable topic search."
    )


# #12758: default snippet length for preview mode. Long enough for the agent to
# judge relevance, short enough that scanning N pages costs far less than N full
# bodies. Expand with preview=false (crawl) or scrape_url (single page).
PREVIEW_SNIPPET_CHARS = 400


def _page_preview(markdown: str, limit: int = PREVIEW_SNIPPET_CHARS) -> str:
    """Render a page as charCount + a whitespace-collapsed leading snippet (#12758).

    Collapsing whitespace matters: raw markdown from a scraped page is mostly
    blank lines and list padding, so an uncollapsed slice of the same length
    carries a fraction of the actual text.
    """
    text = " ".join((markdown or "").split())
    snippet = text[:limit]
    truncated = "…" if len(text) > limit else ""
    return f"({len(markdown or '')} chars) {snippet}{truncated}"


def _format_crawl_results(seed_urls: list, results: list, preview: bool = True) -> str:
    """Format BFS crawl FetchResults into a markdown index. Issue #7509.

    In preview mode (#12758, the default) each successful page renders as its
    char count plus a collapsed leading snippet, so multi-page research does not
    pay for N full bodies; ``preview=False`` restores the first-2000-chars dump.
    Failed pages appear as a single-line error note.
    """
    seed_str = ", ".join(seed_urls[:3])
    if len(seed_urls) > 3:
        seed_str += f" (+{len(seed_urls) - 3} more)"
    successes = [r for r in results if r.success]
    header = f"## Crawled {len(successes)} pages from {seed_str}\n\n"
    lines = [header]
    for r in results:
        if r.success:
            body = _page_preview(r.markdown) if preview else (r.markdown or "")[:2000]
            lines.append(f"### {r.url}\n\n{body}\n\n---\n")
        else:
            lines.append(f"- **FAILED** {r.url} — {r.error_code}\n")
    return "".join(lines)


def _format_map_results(site_result) -> str:
    """Format SiteMapResult into a markdown URL list grouped by depth. Issue #7509."""
    total = len(site_result.entries)
    header = f"## Mapped {total} URLs from {site_result.domain} (source: {site_result.source})\n\n"
    lines = [header]
    by_depth: dict = {}
    for entry in site_result.entries:
        by_depth.setdefault(entry.depth, []).append(entry.url)
    for depth in sorted(by_depth.keys()):
        urls = by_depth[depth]
        lines.append(f"### Depth {depth} ({len(urls)} URLs)\n\n")
        for url in urls:
            lines.append(f"- {url}\n")
        lines.append("\n")
    return "".join(lines)


class ToolHandlerMixin:
    """Mixin for tool and command handling."""

    def _init_terminal_tool(self):
        """Initialize terminal tool for command execution."""
        try:
            import api.agent_terminal as agent_terminal_api
            from tools.terminal_tool import TerminalTool

            # CRITICAL: Access the global singleton instance directly
            # This ensures sessions created here are visible to the approval API
            if agent_terminal_api._agent_terminal_service_instance is None:
                from services.agent_terminal import AgentTerminalService

                # Pass self to prevent circular initialization loop
                agent_terminal_api._agent_terminal_service_instance = AgentTerminalService(chat_workflow_manager=self)
                logger.info("Initialized global AgentTerminalService singleton")

            agent_service = agent_terminal_api._agent_terminal_service_instance
            self.terminal_tool = TerminalTool(agent_terminal_service=agent_service)
            logger.info("Terminal tool initialized successfully with singleton service")
        except Exception as e:
            logger.error("Failed to initialize terminal tool: %s", e)
            self.terminal_tool = None

    def _parse_tool_calls(self, text: str, is_first_iteration: bool = False) -> list[dict[str, Any]]:
        """
        Parse tool calls from LLM response using XML-style markers.

        Issue #620: Refactored to use helper functions.
        Issue #650: Fixed regex to handle nested JSON in params.
        Issue #716: Enforces single tool call per iteration and plan-first execution.

        Args:
            text: LLM response text
            is_first_iteration: Whether this is the first iteration

        Returns:
            List containing at most ONE tool call dictionary (single-step execution)
        """
        logger.debug(
            "[_parse_tool_calls] Searching for TOOL_CALL markers in text of length %d",
            len(text),
        )
        text = html.unescape(text)
        has_tool_call, has_planning = self._detect_tool_call_markers(text)

        if self._should_defer_for_planning(is_first_iteration, has_planning, has_tool_call):
            return []

        tool_calls, match_count = self._extract_tool_calls_from_text(text)
        self._log_parsing_result(
            tool_calls,
            match_count,
            has_tool_call,
            is_first_iteration,
            has_planning,
            text,
        )
        return tool_calls

    def _detect_tool_call_markers(self, text: str) -> tuple[bool, bool]:
        """Detect presence of tool call and planning markers. Issue #620."""
        has_tool_call = ("<TOOL_CALL" in text) or ("<tool_call" in text)
        has_planning = "[PLANNING]" in text or "[planning]" in text.lower()
        logger.debug(
            "[_parse_tool_calls] has_tool_call=%s, has_planning=%s",
            has_tool_call,
            has_planning,
        )
        return has_tool_call, has_planning

    def _should_defer_for_planning(self, is_first_iteration: bool, has_planning: bool, has_tool_call: bool) -> bool:
        """Check if execution should be deferred to show plan first. Issue #716, #620."""
        if is_first_iteration and has_planning and has_tool_call:
            logger.info(
                "[Issue #716] Plan-first execution: First iteration with planning block detected. "
                "Deferring tool execution to show plan first."
            )
            return True
        return False

    def _extract_tool_calls_from_text(self, text: str) -> tuple[list[dict[str, Any]], int]:
        """Extract tool calls using regex pattern. Issue #650, #620."""
        tool_calls = []
        match_count = 0
        for match in _TOOL_CALL_PATTERN.finditer(text):
            match_count += 1
            tool_name = match.group(1)
            params_str = match.group(3)
            description = match.group(4).strip()
            try:
                params = _parse_tool_args(params_str)
                tool_calls.append({"name": tool_name, "params": params, "description": description})
                logger.debug(
                    "[_parse_tool_calls] Found TOOL_CALL #%d: name=%s",
                    match_count,
                    tool_name,
                )
                # Issue #716: Only process ONE execute_command per iteration
                if tool_name == "execute_command":
                    logger.info("[Issue #716] Single-step execution enforced: returning first execute_command")
                    break
            except json.JSONDecodeError as e:
                logger.error("Failed to parse tool call params: %s", e)
                logger.error(
                    "Params string (first 200 of %d chars): %s",
                    len(params_str),
                    params_str[:200],
                )
        return tool_calls, match_count

    def _log_parsing_result(
        self,
        tool_calls: list,
        match_count: int,
        has_tool_call: bool,
        is_first_iteration: bool,
        has_planning: bool,
        text: str,
    ) -> None:
        """Log parsing results and warnings. Issue #650, #620."""
        logger.info(
            "[_parse_tool_calls] Total matches: %d, returning: %d",
            match_count,
            len(tool_calls),
        )
        if not tool_calls and has_tool_call and not (is_first_iteration and has_planning):
            logger.warning(
                "[Issue #650] TOOL_CALL tag found but regex didn't match! Snippet: %s",
                text[:500],
            )

    async def _execute_terminal_command(
        self, session_id: str, command: str, host: str = "main", description: str = ""
    ) -> dict[str, Any]:
        """
        Execute terminal command via terminal tool.

        Args:
            session_id: Chat session ID
            command: Command to execute
            host: Target host
            description: Command description

        Returns:
            Execution result
        """
        if not self.terminal_tool:
            return {"status": "error", "error": "Terminal tool not available"}

        # Ensure terminal session exists for this conversation
        if not self.terminal_tool.active_sessions.get(session_id):
            # Create session
            session_result = await self.terminal_tool.create_session(
                agent_id=f"chat_agent_{session_id}",
                conversation_id=session_id,
                agent_role="chat_agent",
                host=host,
            )

            if session_result.get("status") != "success":
                return session_result

        # Execute command
        result = await self.terminal_tool.execute_command(
            conversation_id=session_id, command=command, description=description
        )

        return result

    async def _persist_approval_request(
        self, approval_msg: WorkflowMessage, session_id: str, terminal_session_id: str
    ) -> None:
        """Persist approval request to chat history (Issue #332 - extracted helper)."""
        try:
            from chat_history import ChatHistoryManager

            chat_mgr = ChatHistoryManager()
            await chat_mgr.add_message(
                sender="assistant",
                text=approval_msg.content,
                message_type="command_approval_request",
                raw_data=approval_msg.metadata,
                session_id=session_id,
            )
            logger.info(
                "✅ Persisted approval request immediately: session=%s, terminal=%s",
                session_id,
                terminal_session_id,
            )
        except Exception as persist_error:
            logger.error(
                "Failed to persist approval request immediately: %s",
                persist_error,
                exc_info=True,
            )

    def _check_empty_command_history(self, elapsed_time: float) -> tuple:
        """Handle empty command history case. Issue #620."""
        logger.warning(
            "pending_approval is None but no command history. " "Breaking after %.1fs to prevent infinite loop.",
            elapsed_time,
        )
        return None, None, True

    def _check_command_mismatch(
        self,
        command: str,
        last_command: dict[str, Any],
        elapsed_time: float,
        max_wait_time: float,
    ) -> tuple | None:
        """Check for command mismatch in history. Issue #620."""
        if last_command.get("command") == command:
            return None  # Command matched, continue processing

        if elapsed_time > max_wait_time - 3590:
            logger.warning(
                "Timeout: pending_approval is None but command not found. "
                "Expected: '%s', Last: '%s'. Breaking after %.1fs.",
                command,
                last_command.get("command"),
                elapsed_time,
            )
            return None, None, True
        return None, None, False

    def _build_approval_status_msg(self, last_command: dict[str, Any]) -> dict[str, Any]:
        """Build approval status message from command history. Issue #620."""
        approval_status = "approved" if last_command.get("approved_by") else "denied"
        comment = last_command.get("approval_comment") or last_command.get("denial_reason")
        return {"approval_status": approval_status, "approval_comment": comment}

    def _check_approval_completion(
        self,
        session_info: dict[str, Any],
        command: str,
        elapsed_time: float,
        max_wait_time: float,
    ) -> tuple:
        """Check if approval is complete. Issue #620.

        Returns: (approval_result, status_msg, should_break)
        """
        if not session_info or session_info.get("pending_approval") is not None:
            return None, None, False

        command_history = session_info.get("command_history", [])
        if not command_history:
            return self._check_empty_command_history(elapsed_time)

        last_command = command_history[-1]
        mismatch_result = self._check_command_mismatch(command, last_command, elapsed_time, max_wait_time)
        if mismatch_result is not None:
            return mismatch_result

        approval_result = last_command.get("result", {})
        logger.info(
            "Completion detected! Command: %s, Status: %s, Approved by: %s",
            command,
            approval_result.get("status"),
            last_command.get("approved_by"),
        )
        return approval_result, self._build_approval_status_msg(last_command), True

    def _build_approval_request_message(
        self,
        session_id: str,
        command: str,
        result: dict[str, Any],
        terminal_session_id: str,
        description: str,
    ) -> WorkflowMessage:
        """Build the approval request WorkflowMessage."""
        return WorkflowMessage(
            type="command_approval_request",
            content=result.get("approval_ui_message", "Command requires approval"),
            metadata={
                "command": command,
                "risk_level": result.get("risk"),
                "reasons": result.get("reasons", []),
                "description": description,
                "requires_approval": True,
                "terminal_session_id": terminal_session_id,
                "conversation_id": session_id,
            },
        )

    def _build_waiting_message(self, command: str, result: dict[str, Any]) -> WorkflowMessage:
        """Build the waiting for approval WorkflowMessage."""
        return WorkflowMessage(
            type="response",
            content=(
                f"\n\n⏳ Waiting for your approval to execute: `{command}`\n"
                f"Risk level: {result.get('risk')}\n"
                f"Reasons: {', '.join(result.get('reasons', []))}\n"
            ),
            metadata={"message_type": "approval_waiting", "command": command},
        )

    def _log_polling_status(self, poll_count: int, session_info: dict[str, Any] | None, elapsed_time: float) -> None:
        """Log periodic polling status updates. Issue #620."""
        if poll_count % 20 != 0:
            return
        pending = session_info.get("pending_approval") is not None if session_info else "NO SESSION"
        logger.info(
            "Still waiting for approval... (elapsed: %.1fs, pending: %s)",
            elapsed_time,
            pending,
        )

    async def _poll_for_approval(
        self,
        terminal_session_id: str,
        command: str,
        max_wait_time: int = 3600,
        poll_interval: float = 0.5,
    ):
        """Poll for approval status until approved/denied or timeout. Issue #620.

        Yields:
            Tuple of (approval_result, status_msg) when found, None on timeout
        """
        elapsed_time = 0
        poll_count = 0

        # #13480: claim interpretation for this turn. The approve path skips its
        # own interpretation while this is set, so the same command is not
        # interpreted twice — two LLM calls, two persisted interpretations.
        await self._claim_interpretation(terminal_session_id, True)

        try:
            while elapsed_time < max_wait_time:
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval
                poll_count += 1

                try:
                    session_info = await self.terminal_tool.get_session_info(terminal_session_id)
                    self._log_polling_status(poll_count, session_info, elapsed_time)

                    result_data, status_msg, should_break = self._check_approval_completion(
                        session_info, command, elapsed_time, max_wait_time
                    )
                    if should_break:
                        yield (result_data, status_msg)
                        return
                except Exception as check_error:
                    logger.error("Error checking approval status: %s", check_error)

            yield (None, None)
        finally:
            # Load-bearing, and the reason this is a `finally` rather than a line
            # after the loop: the claim MUST be released on every exit — timeout,
            # decision, an exception, or the consumer closing this generator
            # early (GeneratorExit runs finally). A leaked claim means the approve
            # path keeps skipping while no turn is listening, so a late approval
            # produces no interpretation at all — silently re-breaking #13479 in
            # exactly the case it was filed for.
            await self._claim_interpretation(terminal_session_id, False)

    async def _claim_interpretation(self, terminal_session_id: str, live: bool) -> None:
        """Mark/unmark this turn as the interpreter for a pending approval (#13480).

        Never raises: failing to claim only costs a duplicate interpretation,
        and failing to release is already guarded by the approve path treating an
        absent marker as "interpret". Neither is worth failing the turn over.
        """
        service = getattr(self.terminal_tool, "agent_terminal_service", None)
        if service is None or not hasattr(service, "set_live_turn_interpreting"):
            return
        try:
            await service.set_live_turn_interpreting(terminal_session_id, live)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not %s interpretation claim: %s", "set" if live else "release", exc)

    async def _handle_pending_approval(
        self,
        session_id: str,
        command: str,
        result: dict[str, Any],
        terminal_session_id: str,
        description: str,
    ):
        """
        Handle command approval workflow with polling.

        Yields:
            WorkflowMessage for approval request and status updates
        Returns:
            Approval result dict or None if timeout
        """
        approval_msg = self._build_approval_request_message(
            session_id, command, result, terminal_session_id, description
        )
        yield approval_msg

        # Issue #4264: Fire APPROVAL_REQUIRED hook when approval is requested
        approval_id = terminal_session_id
        await _emit_approval_required(
            request_id=approval_id,
            action=command,
            session_id=session_id,
            context={
                "command": command,
                "risk_level": result.get("risk"),
                "reasons": result.get("reasons", []),
                "description": description,
            },
        )

        await self._persist_approval_request(approval_msg, session_id, terminal_session_id)
        yield self._build_waiting_message(command, result)

        logger.info("🔍 [APPROVAL POLLING] Waiting for approval of command: %s", command)
        logger.info(
            "🔍 [APPROVAL POLLING] Chat session: %s, Terminal session: %s",
            session_id,
            terminal_session_id,
        )

        async for poll_result in self._poll_for_approval(terminal_session_id, command):
            approval_result, status_msg = poll_result
            if approval_result:
                # Issue #4264: Fire APPROVAL_RECEIVED hook when approval decision is made
                was_approved = approval_result.get("status") == "success"
                await _emit_approval_received(
                    request_id=approval_id,
                    approved=was_approved,
                    session_id=session_id,
                    context={
                        "command": command,
                        "approval_status": approval_result.get("status"),
                        "approval_comment": approval_result.get("approval_comment", ""),
                    },
                )

                yield WorkflowMessage(
                    type="metadata_update",
                    content="",
                    metadata={
                        "message_type": "approval_status_update",
                        "terminal_session_id": terminal_session_id,
                        "command": command,
                        **status_msg,
                    },
                )
            yield approval_result

    async def _handle_approved_command(
        self,
        command: str,
        host: str,
        approval_result: dict[str, Any],
        ollama_endpoint: str,
        selected_model: str,
        session_id: str = "",
    ):
        """Issue #665: Extracted from _handle_approval_workflow to reduce function length.

        Handle successful command approval - execute and interpret results.

        Yields:
            WorkflowMessage for execution status
            Tuple of (exec_result, additional_text) as final item
        """
        exec_result = _create_execution_result(command, host, approval_result, approved=True)
        additional_text = ""

        yield WorkflowMessage(
            type="response",
            content="\n\n✅ Command approved and executed! Interpreting results...\n\n",
            metadata={
                "message_type": "command_executed",
                "command": command,
                "executed": True,
                "approved": True,
            },
        )

        async for interp_chunk in self._interpret_command_results(
            command,
            approval_result.get("stdout", ""),
            approval_result.get("stderr", ""),
            approval_result.get("return_code", 0),
            ollama_endpoint,
            selected_model,
            streaming=True,
        ):
            yield interp_chunk
            if hasattr(interp_chunk, "content"):
                additional_text += interp_chunk.content

        if session_id and approval_result.get("stdout"):
            asyncio.create_task(
                asyncio.to_thread(
                    _detect_and_store_security_output,
                    command,
                    approval_result["stdout"],
                    session_id,
                )
            )

        yield (exec_result, additional_text)

    def _handle_approval_failure(
        self, command: str, approval_result: dict[str, Any] | None
    ) -> tuple[WorkflowMessage, str]:
        """Issue #665: Extracted from _handle_approval_workflow to reduce function length.

        Handle approval denial, or this turn giving up on waiting for a decision.

        #13481: those two are NOT the same outcome and used to be reported
        identically, as ``type="error"``. A denial is a real, final failure. The
        no-decision case is not a failure at all — the approval is still pending
        and still executable:

        * the poll timing out does not clear it (``clear_pending_and_resume()``
          runs only on the approve/deny paths);
        * ``AgentTerminalService._approve_command_internal`` executes on approve
          with no coroutine waiting, so approving later still runs the command.

        So ``Approval timeout for command: ls -la`` claimed a command had failed
        when it had neither failed nor run, and the user could still make it run.
        That wording is what made the reported behaviour unreadable.

        Returns:
            Tuple of (WorkflowMessage, additional_text)
        """
        if approval_result:
            error = approval_result.get("error") or "Command was denied or failed"
            return (
                WorkflowMessage(
                    type="error",
                    content=f"Command execution failed: {error}",
                    metadata={"command": command, "error": True},
                ),
                f"\n\n❌ {error}",
            )

        still_pending = (
            f"Still waiting on your approval for: `{command}`\n"
            "This turn stopped waiting, but the request is still open — "
            "approving it will run the command."
        )
        return (
            WorkflowMessage(
                type="response",
                content=still_pending,
                metadata={
                    "command": command,
                    "message_type": "approval_still_pending",
                    # #13481: kept so existing consumers keying on it keep working,
                    # but it now means "this turn stopped waiting", not "expired".
                    "timeout": True,
                    "approval_still_actionable": True,
                },
            ),
            f"\n\n⏳ {still_pending}",
        )

    async def _handle_approval_workflow(
        self,
        session_id: str,
        command: str,
        host: str,
        result: dict[str, Any],
        terminal_session_id: str,
        description: str,
        ollama_endpoint: str,
        selected_model: str,
    ):
        """Handle command requiring approval (Issue #315: extracted).

        Yields:
            WorkflowMessage for approval stages
            Tuple of (exec_result, additional_text) as final item
        """
        approval_result = None
        async for approval_msg in self._handle_pending_approval(
            session_id, command, result, terminal_session_id, description
        ):
            if isinstance(approval_msg, dict):
                approval_result = approval_msg
            else:
                yield approval_msg

        if approval_result and approval_result.get("status") == "success":
            async for msg in self._handle_approved_command(
                command,
                host,
                approval_result,
                ollama_endpoint,
                selected_model,
                session_id,
            ):
                yield msg
        else:
            error_msg, additional_text = self._handle_approval_failure(command, approval_result)
            yield error_msg
            yield (None, additional_text)

    async def _handle_direct_execution(
        self,
        command: str,
        host: str,
        result: dict[str, Any],
        ollama_endpoint: str,
        selected_model: str,
        session_id: str = "",
    ):
        """Handle direct command execution without approval (Issue #315: extracted).

        Yields:
            WorkflowMessage for interpretation
            Tuple of (exec_result, additional_text) as final item
        """
        exec_result = _create_execution_result(command, host, result, approved=False)

        interpretation = ""
        async for msg in self._interpret_command_results(
            command,
            result.get("stdout", ""),
            result.get("stderr", ""),
            result.get("return_code", 0),
            ollama_endpoint,
            selected_model,
            streaming=False,
        ):
            if hasattr(msg, "content"):
                interpretation += msg.content
            yield msg

        if session_id and result.get("stdout"):
            asyncio.create_task(
                asyncio.to_thread(
                    _detect_and_store_security_output,
                    command,
                    result["stdout"],
                    session_id,
                )
            )

        # Issue #651: Removed duplicate WorkflowMessage yield - interpretation was already
        # yielded in the loop above. Only yield the tuple for the continuation loop.
        yield (exec_result, f"\n\n{interpretation}")

    async def _collect_workflow_results(self, workflow_gen, execution_results: list, additional_response_parts: list):
        """Collect results from workflow generator (Issue #315: extracted).

        Args:
            workflow_gen: Async generator from workflow handler
            execution_results: list to append exec results to
            additional_response_parts: list to append text parts to

        Yields:
            WorkflowMessage items from the generator
        """
        async for msg in workflow_gen:
            if isinstance(msg, tuple):
                exec_result, add_text = msg
                if exec_result:
                    execution_results.append(exec_result)
                additional_response_parts.append(add_text)
            elif msg is not None:
                # Issue #680: Only yield non-None WorkflowMessage objects
                yield msg

    async def _handle_pending_approval_command(
        self,
        session_id: str,
        terminal_session_id: str,
        command: str,
        host: str,
        result: dict[str, Any],
        description: str,
        ollama_endpoint: str,
        selected_model: str,
        execution_results: list,
        additional_response_parts: list,
    ):
        """Handle command requiring approval workflow. Issue #620."""
        if not terminal_session_id:
            logger.error("No terminal session found for conversation %s", session_id)
            yield WorkflowMessage(
                type="error",
                content="Terminal session error - cannot request approval",
                metadata={"error": True},
            )
            return

        workflow_gen = self._handle_approval_workflow(
            session_id,
            command,
            host,
            result,
            terminal_session_id,
            description,
            ollama_endpoint,
            selected_model,
        )
        async for msg in self._collect_workflow_results(workflow_gen, execution_results, additional_response_parts):
            yield msg

    async def _handle_successful_command(
        self,
        command: str,
        host: str,
        result: dict[str, Any],
        ollama_endpoint: str,
        selected_model: str,
        execution_results: list,
        additional_response_parts: list,
        session_id: str = "",
    ):
        """Handle successful direct command execution. Issue #620."""
        workflow_gen = self._handle_direct_execution(command, host, result, ollama_endpoint, selected_model, session_id)
        async for msg in self._collect_workflow_results(workflow_gen, execution_results, additional_response_parts):
            yield msg

    def _extract_command_params(self, tool_call: dict[str, Any]) -> tuple[str, str, str]:
        """Extract command parameters from tool call dict. Issue #620."""
        command = tool_call["params"].get("command")
        host = tool_call["params"].get("host", "main")
        description = tool_call.get("description", "")
        return command, host, description

    async def _dispatch_command_by_status(
        self,
        status: str,
        session_id: str,
        terminal_session_id: str,
        command: str,
        host: str,
        result: dict[str, Any],
        description: str,
        ollama_endpoint: str,
        selected_model: str,
        execution_results: list,
        additional_response_parts: list,
    ):
        """Dispatch command handling based on execution status. Issue #620."""
        if status == "pending_approval":
            async for msg in self._handle_pending_approval_command(
                session_id,
                terminal_session_id,
                command,
                host,
                result,
                description,
                ollama_endpoint,
                selected_model,
                execution_results,
                additional_response_parts,
            ):
                yield msg
        elif status == "success":
            async for msg in self._handle_successful_command(
                command,
                host,
                result,
                ollama_endpoint,
                selected_model,
                execution_results,
                additional_response_parts,
                session_id,
            ):
                yield msg
        elif status == "error":
            async for msg in self._handle_command_error(
                command, result, additional_response_parts, session_id, execution_results
            ):
                yield msg

    async def _process_single_command(
        self,
        tool_call: dict[str, Any],
        session_id: str,
        terminal_session_id: str,
        ollama_endpoint: str,
        selected_model: str,
        execution_results: list,
        additional_response_parts: list,
        role: str = "user",
    ):
        """Process a single execute_command tool call. Issue #620.

        Issue #655: Wraps common errors as RepairableException for retry.
        Issue #4261: Wires BEFORE/AFTER_TOOL_EXECUTE and TOOL_ERROR hooks.
        Issue #14469: forwards the caller's RBAC role and the tool's declared
        `Permission.SHELL_EXECUTE` requirement so PermissionEnforcementExtension
        (#14420) has something to deny against — this call site previously
        omitted both, so every role reached the shell unconditionally.

        Yields:
            WorkflowMessage items
        """
        command, host, description = self._extract_command_params(tool_call)
        logger.info("[ChatWorkflowManager] Executing command: %s on %s", command, host)

        # Issue #4261/#14469: Wire BEFORE_TOOL_EXECUTE hook for execute_command,
        # declaring the shell-execution permission it requires.
        params = {"command": command, "host": host}
        should_execute = await _emit_before_tool_execute(
            "execute_command",
            params,
            session_id,
            tool_permission=Permission.SHELL_EXECUTE.value,
            user_role=role,
        )
        if not should_execute:
            logger.info(
                "[Issue #4261] Execute command cancelled by BEFORE_TOOL_EXECUTE hook: %s on %s",
                command,
                host,
            )
            yield WorkflowMessage(
                type="error",
                content=f"Command execution cancelled: {command}",
                metadata={
                    "command": command,
                    "host": host,
                    "cancelled_by_hook": True,
                    "reason": "permission_denied",
                },
            )
            return

        try:
            result = await self._execute_terminal_command(
                session_id=session_id, command=command, host=host, description=description
            )

            # Issue #4261: Wire AFTER_TOOL_EXECUTE hook for execute_command on success
            if result.get("status") == "success":
                stdout = result.get("stdout", "")
                stdout = await _emit_after_tool_execute("execute_command", stdout, session_id, {})

            async for msg in self._dispatch_command_by_status(
                result.get("status"),
                session_id,
                terminal_session_id,
                command,
                host,
                result,
                description,
                ollama_endpoint,
                selected_model,
                execution_results,
                additional_response_parts,
            ):
                yield msg

        except Exception as e:
            # Issue #4261: Wire TOOL_ERROR hook for execute_command
            await _emit_tool_error("execute_command", e, session_id, {})
            logger.error("[ChatWorkflowManager] Command execution error: %s", e, exc_info=True)
            raise

    async def _handle_command_error(
        self,
        command: str,
        result: dict[str, Any],
        additional_response_parts: list,
        session_id: str = "",
        execution_results: list[dict[str, Any]] | None = None,
    ):
        """Handle command execution error (Issue #665: extracted helper).

        Classifies error as repairable or critical and yields appropriate message.
        Issue #4262: Emit REPAIRABLE_ERROR and CRITICAL_ERROR hooks.

        Args:
            command: The command that failed
            result: Execution result dict with error/stderr
            additional_response_parts: list to append context to
            session_id: Session identifier for hook context

        Yields:
            WorkflowMessage with error details
        """
        from chat_workflow.llm_handler import _emit_critical_error, _emit_repairable_error

        # #14148: `.get(key, default)` does NOT apply the default when the key
        # exists holding None — and `terminal_tool._format_execution_result`
        # constructs exactly that. `or` coalesces both shapes.
        error = result.get("error") or "Unknown error"
        stderr = result.get("stderr", "")

        _record_failed_step(execution_results, command, result, error, stderr)

        repairable_error = self._classify_command_error(command, error, stderr)

        if repairable_error:
            logger.info(
                "[Issue #655] Repairable error for command '%s': %s",
                command,
                repairable_error.message,
            )
            # Emit REPAIRABLE_ERROR hook
            await _emit_repairable_error(
                Exception(repairable_error.message),
                session_id,
                {"command": command, "suggestion": repairable_error.suggestion},
            )
            additional_response_parts.append(f"\n\n{repairable_error.to_llm_context()}")
            yield WorkflowMessage(
                type="error",
                content=repairable_error.to_llm_context(),
                metadata={
                    "command": command,
                    "error": True,
                    "repairable": True,
                    "suggestion": repairable_error.suggestion,
                },
            )
        else:
            # Emit CRITICAL_ERROR hook for non-repairable errors
            await _emit_critical_error(Exception(error), session_id, {"command": command})
            additional_response_parts.append(f"\n\n❌ Command execution failed: {error}")
            yield WorkflowMessage(
                type="error",
                content=f"Command failed: {error}",
                metadata={"command": command, "error": True, "repairable": False},
            )

    def _classify_command_error(self, command: str, error: str, stderr: str) -> RepairableException | None:
        """
        Classify command execution error as repairable or critical.

        Issue #655: Analyzes error message and stderr to determine if LLM
        can potentially fix the issue by trying a different approach.
        Issue #665: Refactored to use _match_repairable_error helper and
        module-level pattern constants for maintainability.

        Args:
            command: The command that failed
            error: Error message
            stderr: Standard error output

        Returns:
            RepairableException if error is recoverable, None if critical
        """
        # #14148: a classifier crashing the turn is never the right answer to an
        # unexpected value. `None` reached here through a `.get()` default that
        # did not apply, and the bare `raise` upstream propagated the
        # AttributeError out of the tool-call generator.
        combined = f"{str(error or '').lower()} {str(stderr or '').lower()}"

        # Check for critical (non-repairable) errors first
        if any(p in combined for p in _CRITICAL_ERROR_PATTERNS):
            logger.warning("[Issue #655] Critical error (out of memory): %s", error)
            return None

        # Check against repairable error patterns
        result = _match_repairable_error(combined, command, error)
        if result:
            return result

        # Default: treat as repairable with generic suggestion
        return RepairableException(
            message=f"Command failed: {error}",
            suggestion="Check the error details and try an alternative approach",
        )

    def _handle_respond_tool(self, tool_call: dict[str, Any]) -> tuple[WorkflowMessage, bool, str]:
        """
        Handle the 'respond' tool for explicit task completion.

        Issue #665: Extracted from _process_tool_calls for single responsibility.
        Issue #654: Original respond tool handling logic.
        #14529: ungated by decision — see chat_workflow/tool_permission_gate.

        Returns:
            Tuple of (message, break_loop_requested, respond_content)
        """
        params = tool_call.get("params", {})
        respond_content = params.get("text", params.get("content", ""))
        break_loop_requested = params.get("break_loop", True)

        logger.info(
            "[Issue #654] Respond tool invoked: break_loop=%s, content_len=%d",
            break_loop_requested,
            len(respond_content),
        )

        message = WorkflowMessage(
            type="response",
            content=respond_content,
            metadata={
                "message_type": "respond_tool",
                "break_loop": break_loop_requested,
                "explicit_completion": True,
            },
        )

        return message, break_loop_requested, respond_content

    async def _handle_delegate_tool(
        self,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
        ctx: "LLMIterationContext" | None = None,
        session_id: str = "",
        role: str = "user",
    ):
        """Handle the 'delegate' tool (Issue #657; GH#11207 execution).

        When ``AUTOBOT_DELEGATION_ENABLED`` is off (default) this keeps the original
        record-only behaviour — no change to the live chat path. When on, it runs
        the subtask as a governed subagent (its ``forbidden_work`` constrains it) via
        the selected engine and returns the result. Yields WorkflowMessage(s).

        #14529: gated on AGENT_EXECUTE, ABOVE the DELEGATION_ENABLED check
        on purpose — below it, the permission would depend on a feature flag.
        """
        from chat_workflow.delegation import (
            DELEGATION_ENABLED,
            MAX_DELEGATIONS_PER_TURN,
            run_delegated_subtask,
        )

        params = tool_call.get("params", {})
        task = params.get("task", "")
        reason = params.get("reason", "Task delegation")

        denial = await permission_denial(
            "delegate", params, session_id, Permission.AGENT_EXECUTE.value, role, execution_results
        )
        if denial is not None:
            yield denial
            return

        if not DELEGATION_ENABLED:
            logger.info("[Issue #657] Delegate tool invoked (record-only): task=%s, reason=%s", task[:100], reason)
            execution_results.append(
                {
                    "tool": "delegate",
                    "task": task,
                    "reason": reason,
                    "wait_for_result": params.get("wait_for_result", True),
                    "status": "pending_delegation",
                }
            )
            yield WorkflowMessage(
                type="delegation",
                content=f"Delegating subtask: {task[:100]}...",
                metadata={"message_type": "delegate_tool", "reason": reason, "task": task},
            )
            return

        # GH#11266: enforce per-turn delegation fan-out limit.
        ctx_dict = (getattr(ctx, "context", None) or {}) if ctx else {}
        delegations_this_turn: int = ctx_dict.get("delegations_this_turn", 0)
        if delegations_this_turn >= MAX_DELEGATIONS_PER_TURN:
            error = f"per-turn delegation limit ({MAX_DELEGATIONS_PER_TURN}) reached"
            logger.warning("[GH#11266] %s", error)
            execution_results.append({"tool": "delegate", "task": task, "status": "error", "error": error})
            yield WorkflowMessage(
                type="error",
                content=f"Delegation blocked: {error}",
                metadata={"message_type": "delegate_tool", "error": True},
            )
            return
        if ctx is not None and ctx.context is not None:
            ctx.context["delegations_this_turn"] = delegations_this_turn + 1

        agent_type = params.get("agent_type", "research_agent")
        engine = params.get("engine", "claude_code")
        depth = int(ctx_dict.get("delegation_depth", 0))
        parent_agent_id = ctx.agent_context.agent_id if ctx and ctx.agent_context else None
        from chat_workflow.session_role import DEFAULT_AUTH_ROLE  # noqa: PLC0415

        try:
            result = await run_delegated_subtask(
                task,
                agent_type=agent_type,
                depth=depth,
                engine=engine,
                parent_agent_id=parent_agent_id,
                auth_role=ctx.auth_role if ctx is not None else DEFAULT_AUTH_ROLE,
            )
            execution_results.append(
                {
                    "tool": "delegate",
                    "task": task,
                    "agent_type": agent_type,
                    "engine": engine,
                    "status": "completed",
                    "result": result,
                }
            )
            yield WorkflowMessage(
                type="delegation",
                content=f"Subagent ({agent_type}) completed: {result[:200]}",
                metadata={"message_type": "delegate_tool", "agent_type": agent_type, "engine": engine},
            )
        except Exception as exc:
            logger.warning("[GH#11207] Delegation failed: %s", exc)
            execution_results.append({"tool": "delegate", "task": task, "status": "error", "error": str(exc)})
            yield WorkflowMessage(
                type="error",
                content=f"Delegation failed: {exc}",
                metadata={"message_type": "delegate_tool", "error": True},
            )

    # #14469: the browser-tool handling below moved to browser_tool_handler.py
    # to bring this file under its file-size ceiling (see that module's
    # docstring for the extraction rationale — none of them touched `self`
    # beyond calling one another). These stay as thin delegating methods, not
    # a straight `= module.func` rebind, so existing test monkey-patches
    # (`handler._handle_browser_tool = ...`, `ToolHandlerMixin._validate_browser_params`)
    # and the `_dispatch_tool_call` call sites are unaffected.
    async def _validate_browser_params(self, tool_name: str, params: dict[str, Any]) -> str | None:
        """Validate browser tool params. Returns a user-friendly block notice or None.

        See ``browser_tool_handler.validate_browser_params`` for the full behavior.
        """
        return await validate_browser_params(tool_name, params)

    async def _handle_browser_tool(
        self,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
        session_id: str = "",
        role: str = "user",
    ):
        """Execute a browser tool call via browser_mcp. Issue #1368.

        See ``browser_tool_handler.handle_browser_tool`` for the full behavior.

        Yields:
            WorkflowMessage for browser tool execution stages
        """
        async for msg in handle_browser_tool(tool_call, execution_results, session_id, role):
            yield msg

    def _record_browser_success(
        self,
        tool_name: str,
        params: dict[str, Any],
        result: dict[str, Any],
        execution_results: list[dict[str, Any]],
    ) -> "WorkflowMessage":
        """Record a successful browser tool execution and return its WorkflowMessage. Issue #2735.

        See ``browser_tool_handler.record_browser_success`` for the full behavior.
        """
        return record_browser_success(tool_name, params, result, execution_results)

    def _extract_browser_image(self, result: dict[str, Any]) -> str | None:
        """Pull the base64 PNG out of a browser tool result, if present. Issue #11538.

        See ``browser_tool_handler.extract_browser_image`` for the full behavior.
        """
        return extract_browser_image(result)

    def _format_page_state_block(self, page_state: dict[str, Any] | None) -> str:
        """Render the numbered interactive-element menu for LLM consumption. Issue #11537.

        See ``browser_tool_handler.format_page_state_block`` for the full behavior.
        """
        return format_page_state_block(page_state)

    def _format_browser_result(
        self,
        tool_name: str,
        params: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        """Format browser tool result as text for LLM context. Issue #1368.

        See ``browser_tool_handler.format_browser_result`` for the full behavior.
        """
        return format_browser_result(tool_name, params, result)

    def _format_browser_action_text(
        self,
        tool_name: str,
        params: dict[str, Any],
        inner: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        """Build the tool-specific summary line for _format_browser_result. Issue #1368/#11537.

        See ``browser_tool_handler.format_browser_action_text`` for the full behavior.
        """
        return format_browser_action_text(tool_name, params, inner, result)

    async def _handle_web_search_tool(
        self,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
        session_id: str = "",
        role: str = "user",
    ):
        """Execute a web search via browser VM. Issue #2306.

        Abstracts the multi-step browser flow (navigate → fill → click → get_text)
        into a single tool call so small models don't need to orchestrate it.
        Issue #4261: Wires BEFORE/AFTER_TOOL_EXECUTE and TOOL_ERROR hooks.
        Issue #14469: declares the same ``MCP_BROWSER_READ`` baseline the
        ``browser_mcp`` bridge grants an undeclared tool — this abstracts
        read-only browser navigation (search + read results), never drives
        arbitrary page state, so it does not need ``MCP_BROWSER_CONTROL``.

        Yields:
            WorkflowMessage for search execution stages
        """
        params = tool_call.get("params", {})
        query = params.get("query", "").strip()
        fetch_full: bool = bool(params.get("fetch_full", False))
        max_pages: int = min(max(int(params.get("max_pages", 5)), 1), 10)
        description = tool_call.get("description", f"Web search: {query}")

        if not query:
            error_msg = 'Error: web_search requires a "query" parameter'
            execution_results.append({"tool": "web_search", "status": "error", "error": error_msg})
            yield WorkflowMessage(
                type="error",
                content=error_msg,
                metadata={"tool": "web_search", "error": True},
            )
            return

        logger.info("[Issue #2306] Web search: query=%s fetch_full=%s max_pages=%d", query, fetch_full, max_pages)

        yield WorkflowMessage(
            type="tool_execution",
            content=f"Searching the web: {description}",
            metadata={"tool": "web_search", "query": query},
        )

        # Issue #4261/#14469: Wire BEFORE_TOOL_EXECUTE hook for web_search,
        # declaring the browser-read permission it requires.
        # #14529: folded onto the shared gate; also gains the execution_results record.
        denial = await permission_denial(
            "web_search", params, session_id, Permission.MCP_BROWSER_READ.value, role, execution_results
        )
        if denial is not None:
            yield denial
            return

        try:
            if fetch_full:
                results = await self._execute_web_search_full(query, max_pages, session_id)
            else:
                # #7479: snippet path now honors max_pages too (was hardcoded
                # to 5, ignoring caller's choice — confusingly inconsistent
                # with fetch_full mode).
                results = await self._execute_web_search(query, max_pages, session_id)

            # Issue #4261: Wire AFTER_TOOL_EXECUTE hook for web_search
            results = await _emit_after_tool_execute("web_search", results, session_id, {})

            execution_results.append({"tool": "web_search", "status": "success", "output": results})
            yield WorkflowMessage(
                type="command_output",
                content=results,
                metadata={
                    "tool": "web_search",
                    "query": query,
                    "status": "success",
                    "fetch_full": fetch_full,
                },
            )
        except Exception as e:
            # Issue #4261: Wire TOOL_ERROR hook for web_search
            await _emit_tool_error("web_search", e, session_id, {})
            logger.error("[Issue #2306] Web search failed: %s", e)
            execution_results.append({"tool": "web_search", "status": "error", "error": "Web search failed"})
            yield WorkflowMessage(
                type="error",
                content="Web search failed",
                metadata={"tool": "web_search", "error": True},
            )

    # ------------------------------------------------------------------
    # Issue #7509: Web research tool handlers
    # ------------------------------------------------------------------

    async def _handle_web_research_tool(
        self,
        tool_name: str,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
        session_id: str = "",
        role: str = "user",
    ):
        """Dispatch one of the 4 web research tools. Issue #7509.

        Routes to _exec_scrape_url, _exec_crawl_site, _exec_map_site, or
        _exec_extract_structured_data based on tool_name.  Yields WorkflowMessages
        for execution stages and final output.

        #14491: this builtin dispatch path never called BEFORE_TOOL_EXECUTE at
        all, so the KNOWLEDGE_READ/KNOWLEDGE_WRITE declarations these same
        tool names already carry in ``mcp_tool_permissions.TOOL_PERMISSIONS``
        (for the separate MCP-registry path) were never consulted here.
        ``crawl_site``/``map_site`` can ingest into the knowledge base
        (``ingest=True``); reusing the existing declaration rather than
        inventing a second one.
        """
        params = tool_call.get("params", {})
        logger.info("[Issue #7509] Web research tool: %s params=%s", tool_name, list(params.keys()))

        # #14491: reuses the exact TOOL_PERMISSIONS entry already declared for
        # this tool name on the MCP-registry path — no bridge_name here (this
        # is the builtin path), so only the exact-name lookup can hit.
        declared_permission = required_permission(tool_name)
        perm = declared_permission.value if declared_permission else None
        denial = await permission_denial(tool_name, params, session_id, perm, role, execution_results)
        if denial is not None:
            yield denial
            return

        yield WorkflowMessage(
            type="tool_execution",
            content=f"Executing {tool_name}...",
            metadata={"tool": tool_name},
        )

        _handlers = {
            "scrape_url": self._exec_scrape_url,
            "crawl_site": self._exec_crawl_site,
            "map_site": self._exec_map_site,
            "extract_structured_data": self._exec_extract_structured_data,
        }
        try:
            result = await _handlers[tool_name](params)
            execution_results.append({"tool": tool_name, "status": "success", "output": result})
            yield WorkflowMessage(
                type="command_output",
                content=result,
                metadata={"tool": tool_name, "status": "success"},
            )
        except Exception as exc:
            logger.error("[Issue #7509] %s failed: %s", tool_name, exc)
            execution_results.append({"tool": tool_name, "status": "error", "error": str(exc)})
            yield WorkflowMessage(
                type="error",
                content=f"{tool_name} failed: {exc}",
                metadata={"tool": tool_name, "error": True},
            )

    async def _handle_llc_tool(
        self, tool_name, tool_call, execution_results, ctx, session_id: str = "", role: str = "user"
    ):
        """Dispatch an LLC work-object tool company-scoped (#11501).

        company_id comes from the chat request context (set by the CEO-chat
        endpoint, T2). A missing/invalid context surfaces as a tool error the
        LLM can react to, rather than a crash.

        #14491: every LLC tool mutates company-scoped work objects
        (``dispatch_llc_tool`` has no RBAC check of its own — only the
        company/tenant scoping above and the cross-tenant IDOR guard inside
        ``_update_goal``) and this was the highest-risk of the seven branches
        never reaching ``BEFORE_TOOL_EXECUTE`` at all. ``Permission.WORKFLOW_CREATE``
        is the closest existing declaration: it is the permission this system
        already uses for "create/mutate a unit of work", held by
        admin/operator/editor and withheld from analyst/user/readonly — the
        same tier a company board operation should require. Denial returns
        before ``dispatch_llc_tool`` is ever awaited.
        """
        params = tool_call.get("params", {}) or {}
        _cctx = ctx.context if ctx is not None and ctx.context else {}
        company_id = _cctx.get("company_id")
        # #11501 review: actor for audit/authz comes from the authenticated chat
        # context, never from LLM-supplied params.
        user_id = _cctx.get("user_id")

        denial = await permission_denial(
            tool_name, params, session_id, Permission.WORKFLOW_CREATE.value, role, execution_results
        )
        if denial is not None:
            yield denial
            return

        try:
            result = await dispatch_llc_tool(tool_name, params, company_id, user_id)
            # #14284: `output` must stay a str — the offload adapter
            # (spill_execution_results) type-guards on str before it looks at a
            # key, so a raw dict here silently defeated it. Serialise at the
            # producer, matching every other handler's envelope.
            output_text = json.dumps(result, default=str, ensure_ascii=False)
            execution_results.append({"tool": tool_name, "status": "success", "output": output_text})
            entity = result.get("entity_type", "item")
            entity_id = result.get("entity_id")
            summary = f"Done ({entity})" + (f" [{entity_id}]" if entity_id else "")
            yield WorkflowMessage(
                type="command_output",
                content=summary,
                metadata={"tool": tool_name, "status": "success", "result": result},
            )
        except LLCToolError as exc:
            execution_results.append({"tool": tool_name, "status": "error", "error": str(exc)})
            yield WorkflowMessage(
                type="error",
                content=f"{tool_name}: {exc}",
                metadata={"tool": tool_name, "error": True},
            )
        except Exception as exc:  # noqa: BLE001 — surface any service error to the LLM, don't crash the turn
            logger.error("[#11501] LLC tool %s failed: %s", tool_name, exc)
            execution_results.append({"tool": tool_name, "status": "error", "error": str(exc)})
            yield WorkflowMessage(
                type="error",
                content=f"{tool_name} failed: {exc}",
                metadata={"tool": tool_name, "error": True},
            )

    async def _exec_scrape_url(self, params: dict) -> str:
        """Fetch a URL and return markdown content. Issue #7509."""
        from knowledge.query_sanitizer import sanitize_and_wrap_web_content
        from web_fetch import RenderMode, WebFetcher

        url = params.get("url", "").strip()
        render_str = params.get("render", "auto")
        render = RenderMode(render_str)
        result = await WebFetcher.fetch(url, render=render)
        if not result.success:
            return f"## Fetch failed\n\nURL: {url}\nError: {result.error_code}"
        title = f"# {result.title}\n\n" if result.title else ""
        header = f"## Scraped: {url} (status {result.status_code}, source: {result.source})\n\n"
        if bool(params.get("preview", False)):
            # #12758: preview-before-expand — charCount + snippet only. Re-call
            # without preview to pay for the full body.
            body = sanitize_and_wrap_web_content(_page_preview(result.markdown or ""), url)
            return header + title + body + "\n\n*(preview — re-run with preview=false for the full page)*"
        # #12757: page body is third-party text — sanitize it and put it behind a
        # trust boundary before it can reach the LLM. Our own header stays
        # OUTSIDE the boundary so the page cannot forge it.
        body = sanitize_and_wrap_web_content(result.markdown or "*(no content)*", url)
        return header + title + body

    async def _exec_crawl_site(self, params: dict) -> str:
        """BFS crawl seed URLs and return a markdown index. Issue #7509."""
        from knowledge.connectors.models import ConnectorConfig
        from knowledge.connectors.web_crawler import WebCrawlerConnector
        from knowledge.query_sanitizer import sanitize_and_wrap_web_content

        seed_urls: list = params.get("seed_urls", [])
        max_depth: int = int(params.get("max_depth", 1))
        max_pages: int = int(params.get("max_pages", 100))
        respect_robots: bool = bool(params.get("respect_robots", True))
        ingest: bool = bool(params.get("ingest", False))
        same_origin: bool = bool(params.get("same_origin", True))

        cfg = ConnectorConfig(
            connector_id="agent_crawl",
            connector_type="web_crawler",
            name="agent_crawl",
            config={"urls": seed_urls, "max_depth": max_depth, "max_pages": max_pages},
        )
        connector = WebCrawlerConnector(cfg)
        results = await connector.crawl(
            seed_urls=seed_urls,
            max_depth=max_depth,
            max_pages=max_pages,
            respect_robots=respect_robots,
            ingest=ingest,
            same_origin=same_origin,
        )
        # #12757: crawled page text is untrusted third-party content.
        # #12758: preview by default — expand one page via scrape_url.
        return sanitize_and_wrap_web_content(
            _format_crawl_results(seed_urls, results, preview=bool(params.get("preview", True))),
            ", ".join(seed_urls),
        )

    async def _exec_map_site(self, params: dict) -> str:
        """Discover URLs for a domain via sitemap or BFS. Issue #7509."""
        from knowledge.query_sanitizer import sanitize_and_wrap_web_content
        from web_fetch.site_mapper import SiteMapper

        domain = params.get("domain", "").strip()
        max_urls: int = int(params.get("max_urls", 500))
        respect_robots: bool = bool(params.get("respect_robots", True))
        site_result = await SiteMapper.map_site(domain, max_urls=max_urls, respect_robots=respect_robots)
        # #12757: discovered URLs/titles are attacker-controlled strings too.
        return sanitize_and_wrap_web_content(_format_map_results(site_result), domain)

    async def _exec_extract_structured_data(self, params: dict) -> str:
        """Extract structured data from a URL using JSON Schema + LLM. Issue #7509."""
        import json

        from web_fetch.extractors import extract_url

        url = params.get("url", "").strip()
        schema = params.get("schema", {})
        render = params.get("render", "auto")
        result = await extract_url(url=url, schema=schema, render=render)
        json_str = json.dumps(result["data"], indent=2, ensure_ascii=False)
        return f"## Extracted data from {url}\n\n```json\n{json_str}\n```"

    # ------------------------------------------------------------------
    # Issue #11540: goal-directed extraction from the *current* live page
    # ------------------------------------------------------------------

    async def _handle_extract_content_tool(
        self,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
        session_id: str = "",
        role: str = "user",
    ):
        """Dispatch the extract_content builtin. Issue #11540.

        Unlike WEB_RESEARCH_TOOL_NAMES (always re-fetches a URL), this reads
        whatever page the browser session is already on — post-login,
        post-click, post-form-fill — so it works behind auth walls a fresh
        fetch could never reach.

        #14529: gated on MCP_BROWSER_READ — the hook never fired here at all.
        """
        params = tool_call.get("params", {})
        goal = params.get("goal", "")
        logger.info("[Issue #11540] extract_content: goal=%s", goal[:100])

        denial = await permission_denial(
            "extract_content", params, session_id, Permission.MCP_BROWSER_READ.value, role, execution_results
        )
        if denial is not None:
            yield denial
            return

        yield WorkflowMessage(
            type="tool_execution",
            content=f"Extracting from the live page: {goal[:100]}",
            metadata={"tool": "extract_content"},
        )

        try:
            result = await self._exec_extract_content(params, session_id)
            execution_results.append({"tool": "extract_content", "status": "success", "output": result})
            yield WorkflowMessage(
                type="command_output",
                content=result,
                metadata={"tool": "extract_content", "status": "success"},
            )
        except Exception as exc:
            logger.error("[Issue #11540] extract_content failed: %s", exc)
            execution_results.append({"tool": "extract_content", "status": "error", "error": str(exc)})
            yield WorkflowMessage(
                type="error",
                content=f"extract_content failed: {exc}",
                metadata={"tool": "extract_content", "error": True},
            )

    async def _handle_read_spilled_output(
        self,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
    ):
        """Re-read a window of a tool result that was spilled out of context (#13919).
        #14529: ungated by decision — see chat_workflow/tool_permission_gate.

        #13692 writes oversized tool output aside and leaves a bounded excerpt
        plus an anchor, and the excerpt's note tells the model to call this tool.
        #13754 made it dispatchable through ``ToolRegistry.execute_tool`` — which
        has no production callers, so at this seam, the one every real tool call
        funnels through, the instruction still named something unreachable. An
        agent following it landed in ``_build_unknown_tool_error`` and burned its
        invalid-call budget.

        The run is bound server-side by the agent loop, never taken from
        arguments: the anchor carries its owning run id in plaintext, so a
        ``task_id`` parameter would let any holder of an anchor read the run it
        came from by echoing the id back.

        Yields:
            WorkflowMessage for the read result.
        """
        params = tool_call.get("params", {})
        anchor = str(params.get("anchor", ""))

        try:
            from agent_loop.tool_output_spill import read_spilled_window

            # Off the event loop. read_spilled reads and json-parses the WHOLE
            # artifact (up to SPILL_MAX_ARTIFACT_CHARS, 5,000,000) before
            # slicing out at most 8,000 chars, so paging a large artifact means
            # re-reading and re-parsing it once per call. The write side already
            # took this decision — spill_results_async exists because a blocking
            # write_text stalls every other coroutine in the process.
            window = await asyncio.to_thread(
                read_spilled_window, anchor, offset=params.get("offset", 0), limit=params.get("limit")
            )
        except Exception as exc:
            logger.error("[#13919] read_spilled_output failed: %s", exc)
            execution_results.append({"tool": "read_spilled_output", "status": "error", "error": str(exc)})
            yield WorkflowMessage(
                type="error",
                content=f"read_spilled_output failed: {exc}",
                metadata={"tool": "read_spilled_output", "error": True},
            )
            return

        if not window.get("found"):
            # The miss reasons need different responses. Flattening them into
            # "do not retry" tells a model to abandon an anchor over a
            # self-correctable argument error, or over a transient one.
            reason = window.get("reason", "unknown")
            advice = _SPILL_MISS_ADVICE.get(reason, _SPILL_MISS_UNKNOWN_ADVICE)
            execution_results.append({"tool": "read_spilled_output", "status": reason, "anchor": anchor})
            yield WorkflowMessage(
                type="command_output",
                content=f"No spilled output for anchor {anchor!r} ({reason}). {advice}",
                metadata={"tool": "read_spilled_output", "status": reason},
            )
            return

        execution_results.append({"tool": "read_spilled_output", "status": "success", "output": window["content"]})
        yield WorkflowMessage(
            type="command_output",
            content=window["content"],
            metadata={
                "tool": "read_spilled_output",
                "status": "success",
                "offset": window["offset"],
                "total_chars": window["total_chars"],
                "has_more": window["has_more"],
            },
        )

    async def _capture_live_page_snapshot(self, session_id: str) -> tuple[str, str]:
        """Read (html, url) off the browser session's *current* page. Issue #11540.

        Reuses the existing browser VM ``evaluate`` action — the same one
        ``evaluate`` tool calls use — with a hardcoded, read-only script (no
        assignment, so ``is_script_safe()`` is a non-issue). No re-fetch: this
        sees whatever page the session already reached via navigate/clicks.
        """
        from api.browser_mcp import DEFAULT_BROWSER_SESSION_ID, send_to_browser_vm

        vm_response = await send_to_browser_vm(
            "evaluate",
            {"script": _EXTRACT_CONTENT_SNAPSHOT_SCRIPT},
            session_id=session_id or DEFAULT_BROWSER_SESSION_ID,
        )
        inner = vm_response.get("result", vm_response)
        page = inner.get("result") or {}
        return page.get("html", ""), page.get("url", "")

    async def _answer_goal_from_markdown(self, markdown: str, url: str, goal: str) -> str:
        """Run the goal-directed LLM sub-extraction over already-fetched markdown. Issue #11540.

        Reuses the same schema-driven LLM sub-call ``extract_structured_data``
        uses (``llm_shared.structured_ops.extract``, #11520) with a single
        free-text ``answer`` field described by the goal instead of a full
        JSON Schema, and the same content-firewall gate ``extract_url()``
        applies (#10552) before any web content reaches the LLM. ``extract()``
        auto-chunks input over ``AUTOBOT_EXTRACT_CHUNK_THRESHOLD`` chars — the
        context-budget-aware cap in place of OpenManus's fixed 2000-char clip.
        """
        from llm_shared.structured_ops import extract
        from security.content_firewall import ContentSource, get_content_firewall

        fw_verdict = await get_content_firewall().inspect(
            markdown, source=ContentSource.WEB, context_label=url or "live_page"
        )
        if fw_verdict.blocked:
            return f"extract_content blocked by content firewall (risk={fw_verdict.risk.value})"

        answer_schema = {
            "type": "object",
            "properties": {"answer": {"type": "string", "description": goal}},
            "required": ["answer"],
        }
        data = await extract(fw_verdict.content, answer_schema)
        answer = data.get("answer", "") if isinstance(data, dict) else str(data)
        header = f"## Extracted from live page{f': {url}' if url else ''}\n\nGoal: {goal}\n\n"
        return header + (answer or "*(nothing relevant found)*")

    async def _exec_extract_content(self, params: dict, session_id: str = "") -> str:
        """Goal-directed extraction from the browser session's live page. Issue #11540.

        Orchestrates the two halves above: capture the live DOM snapshot,
        then run the goal-directed LLM sub-extraction over it.
        """
        from web_fetch.extractors import extract_markdown

        goal = (params.get("goal") or "").strip()
        if not goal:
            return "extract_content requires a 'goal' describing what to extract."

        html_content, url = await self._capture_live_page_snapshot(session_id)
        if not html_content:
            return "extract_content: no live page content — navigate to a page first."

        _title, markdown = extract_markdown(html_content)
        return await self._answer_goal_from_markdown(markdown, url, goal)

    async def _execute_web_search(self, query: str, max_pages: int = 5, session_id: str = "") -> str:
        """Run a web search and return formatted results. Issue #2306.

        Tries the existing Playwright search service first (structured results),
        then falls back to browser VM DuckDuckGo navigation.

        ``max_pages`` (#7479) — caller-requested result count. Threaded into
        ``_web_search_via_playwright`` so the snippet path returns the same
        number of results that the fetch_full path would.

        ``session_id`` (#11539) — threaded into the browser-VM fallback so it
        reuses this conversation's isolated browser context.
        """
        # Primary: use existing search_web_embedded (Rule 2: reuse existing code)
        try:
            result = await self._web_search_via_playwright(query, max_results=max_pages)
            if result:
                return result
        except Exception as e:
            logger.debug("[Issue #2306] Playwright search unavailable: %s", e)

        # Fallback: browser VM with DuckDuckGo HTML
        return await self._web_search_final_fallback(query, session_id)

    async def _execute_web_search_full(self, query: str, max_pages: int, session_id: str = "") -> str:
        """Search + full-page fetch mode. Issue #7404.

        Gets structured entries from Playwright, fans out WebFetcher.fetch
        concurrently for each URL, attaches markdown (or fetch_error) per entry.
        Always returns 200 — per-URL failures are surfaced in fetch_error field.

        On empty entries (Playwright unavailable or zero results) we fall back
        directly to ``_web_search_via_browser_vm`` rather than re-routing
        through ``_execute_web_search``. The latter would re-issue a Playwright
        call via ``_web_search_via_playwright`` — wasteful when
        ``_web_search_structured_entries`` already determined Playwright
        unavailable (#7478).

        ``session_id`` (#11539) — threaded into the browser-VM fallback.
        """
        entries = await self._web_search_structured_entries(query, max_pages)
        if not entries:
            return await self._web_search_final_fallback(query, session_id)
        enriched = await _fetch_pages_concurrent(entries, max_pages)
        return _format_full_search_results(query, enriched)

    async def _web_search_structured_entries(self, query: str, max_pages: int) -> list[dict]:
        """Return raw search result entries [{title, url, snippet}]. Issue #7404.

        Routes through the pluggable search-provider registry first (#9022
        SearXNG / #9023 Brave, credential-gated with graceful fallback). When no
        provider is configured (or all fail) it falls back to the Playwright
        search backend. Returns [] when every backend is unavailable.
        """
        provider_entries = await self._web_search_via_registry(query, max_pages)
        if provider_entries:
            return provider_entries
        try:
            from services.playwright_service import search_web_embedded

            result = await search_web_embedded(query, max_results=max_pages)
            if not result.get("success", False):
                return []
            return result.get("results", [])[:max_pages]
        except Exception as exc:
            logger.debug("[Issue #7404] Playwright structured search unavailable: %s", exc)
            return []

    async def _web_search_via_registry(self, query: str, max_pages: int) -> list[dict]:
        """Search via the provider registry. Returns [] when none configured. #9022/#9023."""
        try:
            from agent_loop.search import registry_search

            results = await registry_search(query, count=max_pages)
            return [r.to_dict() for r in results]
        except Exception as exc:
            logger.debug("[#9022/#9023] Search provider registry unavailable: %s", exc)
            return []

    async def _web_search_via_playwright(self, query: str, max_results: int = 5) -> str:
        """Search via the provider registry / Playwright service. Issue #2306.

        ``max_results`` (#7479): caller-requested result count. Now sourced from
        ``_web_search_structured_entries`` so a configured search provider
        (#9022 SearXNG / #9023 Brave) is used first, with graceful fallback to
        the Playwright backend. Returns formatted text or empty string.
        """
        entries = await self._web_search_structured_entries(query, max_results)
        if not entries:
            return ""

        lines = [f'Web search results for "{query}":\n']
        for i, entry in enumerate(entries[:max_results], 1):
            title = entry.get("title", "No title")
            url = entry.get("url", "")
            snippet = entry.get("snippet", entry.get("description", ""))
            lines.append(f"{i}. **{title}**\n   {url}\n   {snippet}\n")
        return "\n".join(lines)

    async def _web_search_final_fallback(self, query: str, session_id: str = "") -> str:
        """Browser-VM last resort with actionable guidance instead of silence (#11665).

        When the registry and Playwright yielded nothing and even the browser
        VM is unreachable (or returns nothing), the model used to receive ""
        or a generic "Web search failed" — now it gets one sentence naming the
        configuration that unlocks topic search.
        """
        try:
            result = await self._web_search_via_browser_vm(query, session_id)
            if result:
                return result
        except Exception as exc:
            logger.debug("[#11665] Browser VM search fallback unavailable: %s", exc)
        return _search_unavailable_message(query)

    async def _web_search_via_browser_vm(self, query: str, session_id: str = "") -> str:
        """Fallback: search via browser VM DuckDuckGo HTML page. Issue #2306."""
        from urllib.parse import (  # stdlib — lazy to match surrounding pattern
            quote_plus,
        )

        from api.browser_mcp import (  # lazy to avoid circular import
            DEFAULT_BROWSER_SESSION_ID,
            send_to_browser_vm,
        )

        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        # #11539: route through this conversation's isolated browser context.
        vm_session_id = session_id or DEFAULT_BROWSER_SESSION_ID

        nav_result = await send_to_browser_vm("navigate", {"url": search_url}, session_id=vm_session_id)
        if not nav_result.get("success", True):
            raise RuntimeError(f"Failed to navigate to search page: {nav_result.get('error', 'unknown')}")

        # Try results div first, then fall back to body
        for selector in ("div.results", "body"):
            text_result = await send_to_browser_vm(
                "get_text",
                {"selector": selector},
                session_id=vm_session_id,
            )
            inner = text_result.get("result", text_result)
            raw_text = inner.get("text", "")
            if raw_text:
                max_len = 3000
                truncated = raw_text[:max_len]
                if len(raw_text) > max_len:
                    truncated += "\n\n... [results truncated]"
                return f'Web search results for "{query}":\n\n{truncated}'

        return f"No search results found for: {query}"

    def _build_execution_summary(self, execution_results: list[dict[str, Any]]) -> WorkflowMessage:
        """Build execution summary message from results. Issue #620."""
        return WorkflowMessage(
            type="execution_summary",
            content="",
            metadata={
                "execution_results": execution_results,
                "total_commands": len(execution_results),
                "successful_commands": sum(1 for r in execution_results if r.get("status") == "success"),
            },
        )

    def _build_unknown_tool_error(
        self,
        tool_name: str,
        ctx: "LLMIterationContext" | None,
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage:
        """Build error message for an unknown tool call (#2305, #2310)."""
        # GH#11489: derive from the routing SSOT so the hint never drifts.
        known_tools = sorted({"respond", "delegate"} | _UNIFORM_BUILTIN_TOOLS)
        if ctx is not None:
            ctx.consecutive_invalid_tool_calls += 1
        consecutive = ctx.consecutive_invalid_tool_calls if ctx is not None else 0
        error_msg = f'Error: Tool "{tool_name}" not found. Available tools: {", ".join(known_tools)}'
        logger.warning(
            "[Issue #2305] Unknown tool call reported to agent: %s (consecutive_invalid=%d)",
            tool_name,
            consecutive,
        )
        execution_results.append({"tool": tool_name, "status": "error", "error": error_msg})
        return WorkflowMessage(
            type="error",
            content=error_msg,
            metadata={"message_type": "unknown_tool", "tool_name": tool_name},
        )

    # #14495: the six seam enforcers below moved to tool_dispatch_guards.py to
    # bring this file under its file-size ceiling (see that module's docstring
    # for the extraction rationale — none of them touched `self`). These stay
    # as thin delegating methods, not a straight `= module.func` rebind, so
    # existing test monkey-patches (`mixin._enforce_forbidden_work = ...`) and
    # the `_dispatch_tool_call` call sites are unaffected.
    def _enforce_forbidden_work(
        self,
        tool_call: dict[str, Any],
        ctx: "LLMIterationContext" | None,
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage | None:
        """Hard-block a tool the acting agent's forbidden_work manifest forbids (GH#11145).

        See ``tool_dispatch_guards.enforce_forbidden_work`` for the full behavior.
        """
        return enforce_forbidden_work(tool_call, ctx, execution_results)

    def _enforce_config_protection(
        self,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage | None:
        """Block a write that would weaken a linter/formatter config (GH#11177).

        See ``tool_dispatch_guards.enforce_config_protection`` for the full behavior.
        """
        return enforce_config_protection(tool_call, execution_results)

    def _enforce_fact_forcing(
        self,
        tool_call: dict[str, Any],
        ctx: "LLMIterationContext" | None,
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage | None:
        """Block the first edit to an existing, uninvestigated file (GH#11178).

        See ``tool_dispatch_guards.enforce_fact_forcing`` for the full behavior.
        """
        return enforce_fact_forcing(tool_call, ctx, execution_results)

    async def _enforce_pre_action_verifier(
        self,
        tool_call: dict[str, Any],
        ctx: "LLMIterationContext" | None,
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage | None:
        """Run the adversarial pre-action verifier on a sensitive tool call (#14031).

        See ``tool_dispatch_guards.enforce_pre_action_verifier`` for the full behavior.
        """
        return await enforce_pre_action_verifier(tool_call, ctx, execution_results)

    def _enforce_repetition(
        self,
        tool_call: dict[str, Any],
        ctx: "LLMIterationContext" | None,
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage | None:
        """Halt a looping or stagnating agent at the live seam (#13590).

        See ``tool_dispatch_guards.enforce_repetition`` for the full behavior.
        """
        return enforce_repetition(tool_call, ctx, execution_results)

    def _enforce_work_item_approval(
        self,
        tool_call: dict[str, Any],
        ctx: "LLMIterationContext" | None,
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage | None:
        """Hold a tool the work item declared as approval-gated (GH#11160).

        See ``tool_dispatch_guards.enforce_work_item_approval`` for the full behavior.
        """
        return enforce_work_item_approval(tool_call, ctx, execution_results)

    async def _dispatch_tool_call(
        self,
        tool_call: dict[str, Any],
        session_id: str,
        terminal_session_id: str,
        ollama_endpoint: str,
        selected_model: str,
        execution_results: list[dict[str, Any]],
        additional_response_parts: list[str],
        ctx: "LLMIterationContext" | None = None,
        role: str = "user",
    ):
        """Route a tool call to the appropriate handler. Issue #620/#2310/#2629.

        Yields WorkflowMessage for execution stages, or (break_loop, respond_content) tuple
        for the respond tool. Uniform builtins (GH#11489: browser, web_search, web
        research, execute_command) share one gate and route via ``_builtin_route``;
        everything else falls through to MCP/unknown handling.
        """
        tool_name = tool_call["name"]

        # GH#11145: enforce the acting agent's forbidden_work manifest at the single
        # production dispatch seam — before any tool-specific branch. Every tool call
        # funnels through here, so this is the one place the capability boundary is
        # applied. No-ops for the plain chat agent (no profile → empty manifest);
        # bites profile-bound agents (e.g. a delegated research_agent cannot run bash).
        forbidden_msg = self._enforce_forbidden_work(tool_call, ctx, execution_results)
        if forbidden_msg is not None:
            yield forbidden_msg
            return

        # GH#11177: block writes that would weaken a linter/formatter config at the
        # same production seam — steer the agent to fix the code, not the gate.
        config_msg = self._enforce_config_protection(tool_call, execution_results)
        if config_msg is not None:
            yield config_msg
            return

        # GH#11178: fact-forcing — record reads/greps and block the first edit to
        # an existing file not yet investigated this turn, at the same seam.
        fact_msg = self._enforce_fact_forcing(tool_call, ctx, execution_results)
        if fact_msg is not None:
            yield fact_msg
            return

        # #14031: adversarial pre-action verifier — an independent, differently
        # prompted model tries to REFUTE a sensitive action before it executes.
        # Runs before the approval hold below so a HARD_BLOCK verdict short-circuits
        # without ever reaching the human approval step, matching the original
        # AgentLoop._check_approvals ordering.
        verifier_msg = await self._enforce_pre_action_verifier(tool_call, ctx, execution_results)
        if verifier_msg is not None:
            yield verifier_msg
            return

        # GH#11160: hold a tool the work item declared as approval-gated
        # (requires_approval_before) pending approval, at the same seam.
        approval_msg = self._enforce_work_item_approval(tool_call, ctx, execution_results)
        if approval_msg is not None:
            yield approval_msg
            return

        # #13590: halt a stagnating agent — same tool, same args, same result —
        # at the profile's max_identical_tool_calls. Placed last of the
        # enforcers so a call blocked for a *policy* reason above is not also
        # counted as repetition; those blocks are the agent being stopped, not
        # the agent looping.
        repetition_msg = self._enforce_repetition(tool_call, ctx, execution_results)
        if repetition_msg is not None:
            yield repetition_msg
            return

        # GH#11568: sandboxed Python composition tool (main-chat only).
        if tool_name == "compose" and CODEEXEC_ENABLED:
            if ctx is not None:
                ctx.consecutive_invalid_tool_calls = 0
            async for msg in self._handle_compose_tool(tool_call, session_id, execution_results, ctx):
                yield msg
            return

        if tool_name == "respond":
            if ctx is not None:
                ctx.consecutive_invalid_tool_calls = 0
            msg, break_loop, respond_content = self._handle_respond_tool(tool_call)
            yield msg
            yield (break_loop, respond_content)
            return

        if tool_name == "delegate":
            if ctx is not None:
                ctx.consecutive_invalid_tool_calls = 0
            async for msg in self._handle_delegate_tool(
                tool_call, execution_results, ctx, session_id=session_id, role=role
            ):
                yield msg
            return

        # #11501: LLC board/CEO-chat work-object tools — company-scoped dispatch
        # to the existing llc/services. Handled here (not via _builtin_route)
        # because the handler needs ctx.context["company_id"], which the uniform
        # route does not receive.
        if tool_name in LLC_TOOL_NAMES:
            if ctx is not None:
                ctx.consecutive_invalid_tool_calls = 0
            validation_msg = _validate_builtin_tool_arguments(tool_name, tool_call)
            if validation_msg is not None:
                execution_results.append(
                    {
                        "tool": tool_name,
                        "status": "schema_error",
                        "error": validation_msg.content,
                        "schema_validation_failed": True,
                    }
                )
                yield validation_msg
                return
            # #14491: forward session_id/role so _handle_llc_tool can declare
            # Permission.WORKFLOW_CREATE at BEFORE_TOOL_EXECUTE — this branch
            # never reached the hook before.
            async for msg in self._handle_llc_tool(tool_name, tool_call, execution_results, ctx, session_id, role):
                yield msg
            return

        # GH#11489: every uniform builtin (browser #1368, web_search #2306, web
        # research #7509, execute_command) passes one shared gate — invalid-call
        # counter reset, then Issue #4529 schema validation — before its handler.
        if tool_name in _UNIFORM_BUILTIN_TOOLS:
            if ctx is not None:
                ctx.consecutive_invalid_tool_calls = 0
            validation_msg = _validate_builtin_tool_arguments(tool_name, tool_call)
            if validation_msg is not None:
                execution_results.append(
                    {
                        "tool": tool_name,
                        "status": "schema_error",
                        "error": validation_msg.content,
                        "schema_validation_failed": True,
                    }
                )
                yield validation_msg
                return
            async for msg in self._builtin_route(
                tool_name,
                tool_call,
                session_id,
                terminal_session_id,
                ollama_endpoint,
                selected_model,
                execution_results,
                additional_response_parts,
                role=role,
            ):
                yield msg
            return

        async for msg in self._dispatch_mcp_or_unknown(tool_name, tool_call, execution_results, ctx, role, session_id):
            yield msg

    def _builtin_route(
        self,
        tool_name: str,
        tool_call: dict[str, Any],
        session_id: str,
        terminal_session_id: str,
        ollama_endpoint: str,
        selected_model: str,
        execution_results: list[dict[str, Any]],
        additional_response_parts: list[str],
        role: str = "user",
    ) -> AsyncIterator[Any]:
        """Return the handler async-generator for a uniform builtin tool (GH#11489).

        Membership SSOT is ``_UNIFORM_BUILTIN_TOOLS``; the caller has already run
        the shared gate. Adding a builtin that follows the standard gate takes a
        schema entry plus one row here — no new branch at the dispatch seam.

        Issue #14469/#14491/#14529: ``role`` is forwarded to every handler
        that declares a ``tool_permission`` — browser, web_search,
        execute_command, web research, and now live-page-extract.
        ``read_spilled_output`` stays undeclared by decision, not by omission;
        the reasoning is on the handler itself.
        """
        if tool_name in BROWSER_TOOL_NAMES:  # Issue #1368: route to browser VM
            return self._handle_browser_tool(tool_call, execution_results, session_id, role=role)
        if tool_name == "web_search":  # Issue #2306: multi-step browser flow
            return self._handle_web_search_tool(tool_call, execution_results, session_id, role=role)
        if tool_name in WEB_RESEARCH_TOOL_NAMES:  # Issue #7509
            return self._handle_web_research_tool(tool_name, tool_call, execution_results, session_id, role=role)
        if tool_name in LIVE_PAGE_EXTRACT_TOOL_NAMES:  # Issue #11540
            return self._handle_extract_content_tool(tool_call, execution_results, session_id, role=role)
        if tool_name == "read_spilled_output":  # #13919: the excerpt's note names this
            return self._handle_read_spilled_output(tool_call, execution_results)
        if tool_name == "execute_command":
            return self._dispatch_execute_command(
                tool_call,
                session_id,
                terminal_session_id,
                ollama_endpoint,
                selected_model,
                execution_results,
                additional_response_parts,
                role=role,
            )
        # A member of _UNIFORM_BUILTIN_TOOLS without a route row is a wiring bug —
        # fail loudly rather than falling through to a high-blast-radius handler.
        raise ValueError(f"_builtin_route: no route for {tool_name!r}; add a row alongside _UNIFORM_BUILTIN_TOOLS")

    async def _dispatch_mcp_or_unknown(
        self,
        tool_name: str,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
        ctx: "LLMIterationContext" | None,
        role: str,
        session_id: str = "",
    ):
        """Try MCP dispatch; yield unknown-tool error if not registered. Issue #2513/#2629.

        Extracted from _dispatch_tool_call (#2735) to keep parent under 65 lines.
        Issue #4261: Added session_id for hook invocation.
        """
        # Issue #2513: Check MCP registry before reporting unknown tool.
        # Issue #2629: Forward RBAC role so admin-only tools are enforced.
        mcp_result = await _try_mcp_dispatch(tool_name, tool_call, execution_results, role=role, session_id=session_id)
        if mcp_result is not None:
            yield mcp_result
            return

        # Issue #2305/#2310: Report unknown tool and track consecutive failures.
        yield self._build_unknown_tool_error(tool_name, ctx, execution_results)

    async def _dispatch_execute_command(
        self,
        tool_call: dict[str, Any],
        session_id: str,
        terminal_session_id: str,
        ollama_endpoint: str,
        selected_model: str,
        execution_results: list[dict[str, Any]],
        additional_response_parts: list[str],
        role: str = "user",
    ):
        """Delegate execute_command tool call to _process_single_command. Issue #2735.

        Extracted from _dispatch_tool_call to keep parent under 65 lines.
        Issue #14469: forwards `role` — see _process_single_command.
        """
        async for msg in self._process_single_command(
            tool_call,
            session_id,
            terminal_session_id,
            ollama_endpoint,
            selected_model,
            execution_results,
            additional_response_parts,
            role=role,
        ):
            yield msg

    # ------------------------------------------------------------------ #
    # GH#11568: compose tool handlers                                     #
    # ------------------------------------------------------------------ #
    #
    # Bodies moved to compose_tool_handler.py (#14491) to offset that PR's
    # additions and keep this module under its file-size ceiling. These stay
    # as thin delegating methods (same names) rather than a straight rebind
    # because test_code_exec.py replaces several of them wholesale with a
    # mock (``handler._persist_compose_approval = AsyncMock(...)``) and
    # ``_handle_compose_tool`` below must keep dispatching through
    # ``self.<method>`` for that to still take effect.

    def _guard_compose(self, program: str, agent_id: "str | None") -> "WorkflowMessage | None":
        """Run AST guard; return error WorkflowMessage on violation, else None.

        See ``compose_tool_handler.guard_compose`` for the full behavior.
        """
        return guard_compose(program, agent_id)

    @staticmethod
    def _compose_auto_approvable(shim_snapshot: list[str]) -> bool:
        """Auto-approve only when the flag is on AND all shims are read-only (design §3.1).

        See ``compose_tool_handler.compose_auto_approvable`` for the full behavior.
        """
        return compose_auto_approvable(shim_snapshot)

    async def _approve_compose(self, program: str, shim_snapshot: list[str], session_id: str) -> "str | None":
        """Return an approval id requiring a gate, or ``None`` to auto-approve (GH#11568).

        Auto-approval requires the flag AND a fully read-only shim set; any
        non-read-only shim forces the WORKFLOW_GATE even with the flag on.
        """
        if self._compose_auto_approvable(shim_snapshot):
            return None
        return await self._persist_compose_approval(program, shim_snapshot, session_id)

    async def _poll_compose_approval(self, approval_id: str) -> str:
        """Poll the WORKFLOW_GATE until decided; return its terminal status (GH#11568 MINOR-2).

        See ``compose_tool_handler.poll_compose_approval`` for the full behavior.
        """
        return await poll_compose_approval(approval_id)

    async def _persist_compose_approval(self, program: str, shim_snapshot: list[str], session_id: str) -> "str | None":
        """Persist a WORKFLOW_GATE Approval carrying program + shims + budgets (GH#11568).

        See ``compose_tool_handler.persist_compose_approval`` for the full behavior.
        """
        return await persist_compose_approval(program, shim_snapshot, session_id)

    def _build_compose_dispatch(self, session_id: str, ctx: "LLMIterationContext | None"):
        """Return an async dispatch callable routing shim calls through the seam (GH#11568).

        See ``compose_tool_handler.build_compose_dispatch`` for the full behavior.
        """
        return build_compose_dispatch(session_id, ctx, self._dispatch_tool_call)

    async def _execute_compose(
        self, program: str, agent_id: "str | None", run_id: str, session_id: str, ctx: "LLMIterationContext | None"
    ) -> "WorkflowMessage":
        """Run the script inside the sandbox via a live broker; return result msg.

        See ``compose_tool_handler.execute_compose`` for the full behavior.
        """
        return await execute_compose(program, agent_id, run_id, session_id, ctx, self._dispatch_tool_call)

    def _compose_result_message(self, result: Any, run_id: str) -> "WorkflowMessage":
        """Build the tool_result WorkflowMessage from a SandboxResult (GH#11568).

        See ``compose_tool_handler.compose_result_message`` for the full behavior.
        """
        return compose_result_message(result, run_id)

    def _compose_shim_snapshot(self, agent_id: "str | None") -> list[str]:
        """Injectable-tool snapshot for this agent (allowlist ∩ allowed − forbidden).

        See ``compose_tool_handler.compose_shim_snapshot`` for the full behavior.
        """
        return compose_shim_snapshot(agent_id)

    def _reject_delegated_compose(self, agent_id: "str | None") -> "WorkflowMessage | None":
        """Main-chat-only: reject compose for any profile-bound (delegated) agent (GH#11568).

        See ``compose_tool_handler.reject_delegated_compose`` for the full behavior.
        """
        return reject_delegated_compose(agent_id)

    def _compose_gate_request_msg(self, approval_id: str, shim_snapshot: list[str]) -> "WorkflowMessage":
        """Build the WORKFLOW_GATE approval-required notification (GH#11568).

        See ``compose_tool_handler.compose_gate_request_msg`` for the full behavior.
        """
        return compose_gate_request_msg(approval_id, shim_snapshot)

    def _compose_gate_refusal_msg(self, status: str) -> "WorkflowMessage":
        """Terminal refusal message for a non-approved gate (GH#11568).

        See ``compose_tool_handler.compose_gate_refusal_msg`` for the full behavior.
        """
        return compose_gate_refusal_msg(status)

    async def _handle_compose_tool(
        self,
        tool_call: dict[str, Any],
        session_id: str,
        execution_results: list[dict[str, Any]],
        ctx: "LLMIterationContext | None",
    ):
        """Handle the compose tool call (GH#11568). #14529: ungated — see tool_permission_gate."""
        program: str = tool_call.get("params", {}).get("program", "")
        agent_id: str | None = ctx.agent_context.agent_id if (ctx and ctx.agent_context) else None
        subagent_msg = self._reject_delegated_compose(agent_id)
        if subagent_msg is not None:
            yield subagent_msg
            return

        guard_msg = self._guard_compose(program, agent_id)
        if guard_msg is not None:
            execution_results.append({"tool": "compose", "status": "ast_rejected"})
            yield guard_msg
            return

        shim_snapshot = self._compose_shim_snapshot(agent_id)
        approval_id = await self._approve_compose(program, shim_snapshot, session_id)
        if approval_id is not None:
            yield self._compose_gate_request_msg(approval_id, shim_snapshot)
            status = await self._poll_compose_approval(approval_id)
            if status != "approved":
                execution_results.append({"tool": "compose", "status": "gated", "approval_status": status})
                yield self._compose_gate_refusal_msg(status)
                return

        run_id = str(uuid.uuid4())
        result_msg = await self._execute_compose(program, agent_id, run_id, session_id, ctx)
        execution_results.append({"tool": "compose", "status": "executed", "run_id": run_id})
        yield result_msg

    async def _process_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        session_id: str,
        terminal_session_id: str,
        ollama_endpoint: str,
        selected_model: str,
        ctx: "LLMIterationContext" | None = None,
    ):
        """Process all tool calls from LLM response.

        Issue #315: Refactored to use helper methods for reduced nesting.
        Issue #654: Added support for 'respond' tool with break_loop pattern.
        Issue #620: Refactored using Extract Method pattern.
        Issue #2310: Accepts optional ctx for consecutive-invalid-tool tracking.

        Yields:
            WorkflowMessage for each stage of execution
            Also yields execution_summary at end for Issue #352 continuation loop
            Finally yields (break_loop, response_content) tuple if respond tool used
        """
        execution_results = []
        additional_response_parts = []
        break_loop_requested = False
        respond_content = None

        # #13821: forward the authenticated role. #2629 wired `role` as far as
        # _dispatch_tool_call's signature and stopped here, so the `role="user"`
        # default won every call and MCPDispatcher never saw who was signed in —
        # an admin was denied the admin-only tools they are entitled to, and the
        # #13228 shadow inventory could only ever contain user rows.
        from chat_workflow.session_role import DEFAULT_AUTH_ROLE  # noqa: PLC0415

        role = ctx.auth_role if ctx is not None else DEFAULT_AUTH_ROLE

        for tool_call in tool_calls:
            async for result in self._dispatch_tool_call(
                tool_call,
                session_id,
                terminal_session_id,
                ollama_endpoint,
                selected_model,
                execution_results,
                additional_response_parts,
                ctx=ctx,
                role=role,
            ):
                if isinstance(result, tuple):
                    break_loop_requested, respond_content = result
                else:
                    yield result

        if execution_results:
            yield self._build_execution_summary(execution_results)

        yield (break_loop_requested, respond_content)
