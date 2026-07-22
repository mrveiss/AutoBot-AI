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
from autobot_shared.env_utils import env_flag, env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.tool_catalogue import APPROVAL_CATEGORY_TOOLS, match_tool_name
from chat_workflow.code_exec.tool_policy import CODEEXEC_READONLY_TOOLS
from chat_workflow.tool_call_grammar import TOOL_CALL_PATTERN
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

# GH#11568: compose tool feature flag and tuning constants.
CODEEXEC_ENABLED: bool = env_flag("AUTOBOT_CODEEXEC_ENABLED", default=False)
CODEEXEC_AUTOAPPROVE_READONLY: bool = env_flag("AUTOBOT_CODEEXEC_AUTOAPPROVE_READONLY", default=True)
CODEEXEC_MAX_SCRIPT_RETRIES: int = env_int("AUTOBOT_CODEEXEC_MAX_SCRIPT_RETRIES", default=1)
# GH#11568 BLOCKER-4 / GH#11662: the read-only tool set eligible for auto-approval
# (design §3.1) is CODEEXEC_READONLY_TOOLS, imported above from the single
# tool-policy classification source (readonly ⊆ injectable; sensitive excluded).
# Approval-wait polling knobs (mirrors terminal-command approval loop).
CODEEXEC_APPROVAL_WAIT_SECONDS: int = env_int("AUTOBOT_CODEEXEC_APPROVAL_WAIT_SECONDS", default=1800)
CODEEXEC_APPROVAL_POLL_SECONDS: int = env_int("AUTOBOT_CODEEXEC_APPROVAL_POLL_SECONDS", default=2)

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

# Issue #4529: JSON Schema definitions for built-in tools dispatched directly
# (not via MCP).  Used by _validate_builtin_tool_arguments() so every dispatch
# path passes through validate_tool_arguments() before execution.
# Issue #4726: inline dicts replaced with named constants above; schema content
# is unchanged.
_BUILTIN_TOOL_SCHEMAS: dict[str, dict] = {
    "execute_command": EXECUTE_COMMAND_SCHEMA,
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
    }
)

# Issue #7509: web research tools — direct internal dispatch via web_fetch.
WEB_RESEARCH_TOOL_NAMES: frozenset[str] = frozenset({"scrape_url", "crawl_site", "map_site", "extract_structured_data"})

# GH#11489: builtin tools sharing the uniform dispatch gate (invalid-call
# counter reset → Issue #4529 schema validation → handler). ``_builtin_route``
# maps each name to its handler, so adding a tool here needs no new branch at
# the ``_dispatch_tool_call`` seam.
_UNIFORM_BUILTIN_TOOLS: frozenset[str] = (
    BROWSER_TOOL_NAMES | WEB_RESEARCH_TOOL_NAMES | frozenset({"web_search", "execute_command"})
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
    return {
        "command": command,
        "host": host,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "return_code": result.get("return_code", 0),
        "status": "success",
        "approved": approved,
    }


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
    should_execute = await _emit_before_tool_execute(tool_name, arguments, session_id)
    if not should_execute:
        logger.info(
            "[Issue #4261] Tool execution cancelled by BEFORE_TOOL_EXECUTE hook: %s",
            tool_name,
        )
        return WorkflowMessage(
            type="error",
            content=f"Tool execution cancelled: {tool_name}",
            metadata={"tool_name": tool_name, "cancelled_by_hook": True},
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


def _format_crawl_results(seed_urls: list, results: list) -> str:
    """Format BFS crawl FetchResults into a markdown index. Issue #7509.

    Successful pages are rendered as `### <url> (depth N)\\n<first 2000 chars>`.
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
            preview = (r.markdown or "")[:2000]
            lines.append(f"### {r.url}\n\n{preview}\n\n---\n")
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

        Handle approval denial or timeout.

        Returns:
            Tuple of (WorkflowMessage, additional_text)
        """
        if approval_result:
            error = approval_result.get("error", "Command was denied or failed")
            return (
                WorkflowMessage(
                    type="error",
                    content=f"Command execution failed: {error}",
                    metadata={"command": command, "error": True},
                ),
                f"\n\n❌ {error}",
            )
        else:
            return (
                WorkflowMessage(
                    type="error",
                    content=f"Approval timeout for command: {command}",
                    metadata={"command": command, "timeout": True},
                ),
                f"\n\n⏱️ Approval timeout for command: {command}",
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
            async for msg in self._handle_command_error(command, result, additional_response_parts, session_id):
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
    ):
        """Process a single execute_command tool call. Issue #620.

        Issue #655: Wraps common errors as RepairableException for retry.
        Issue #4261: Wires BEFORE/AFTER_TOOL_EXECUTE and TOOL_ERROR hooks.

        Yields:
            WorkflowMessage items
        """
        command, host, description = self._extract_command_params(tool_call)
        logger.info("[ChatWorkflowManager] Executing command: %s on %s", command, host)

        # Issue #4261: Wire BEFORE_TOOL_EXECUTE hook for execute_command
        params = {"command": command, "host": host}
        should_execute = await _emit_before_tool_execute("execute_command", params, session_id)
        if not should_execute:
            logger.info(
                "[Issue #4261] Execute command cancelled by BEFORE_TOOL_EXECUTE hook: %s on %s",
                command,
                host,
            )
            yield WorkflowMessage(
                type="error",
                content=f"Command execution cancelled: {command}",
                metadata={"command": command, "host": host, "cancelled_by_hook": True},
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

        error = result.get("error", "Unknown error")
        stderr = result.get("stderr", "")
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
        combined = f"{error.lower()} {stderr.lower()}"

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
    ):
        """Handle the 'delegate' tool (Issue #657; GH#11207 execution).

        When ``AUTOBOT_DELEGATION_ENABLED`` is off (default) this keeps the original
        record-only behaviour — no change to the live chat path. When on, it runs
        the subtask as a governed subagent (its ``forbidden_work`` constrains it) via
        the selected engine and returns the result. Yields WorkflowMessage(s).
        """
        from chat_workflow.delegation import (
            DELEGATION_ENABLED,
            MAX_DELEGATIONS_PER_TURN,
            run_delegated_subtask,
        )

        params = tool_call.get("params", {})
        task = params.get("task", "")
        reason = params.get("reason", "Task delegation")

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
        try:
            result = await run_delegated_subtask(
                task,
                agent_type=agent_type,
                depth=depth,
                engine=engine,
                parent_agent_id=parent_agent_id,
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

    def _validate_browser_params(self, tool_name: str, params: dict[str, Any]) -> str | None:
        """Validate browser tool params. Returns a user-friendly block notice or None.

        #1368 / #10914: a disallowed URL or unsafe script is an *expected* policy
        outcome, so the returned text reads as a friendly notice (rendered as a
        normal assistant message, not a scary error banner — see _handle_browser_tool).
        """
        from api.browser_mcp import is_script_safe, is_url_allowed

        if tool_name == "navigate" and not is_url_allowed(params.get("url", "")):
            url = params.get("url", "")
            return f"I can't open that link ({url}) — it isn't on the list of sites I'm allowed to browse."
        if tool_name == "evaluate" and not is_script_safe(params.get("script", "")):
            return "I can't run that browser action — it was blocked by the security policy."
        return None

    async def _handle_browser_tool(
        self,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
        session_id: str = "",
    ):
        """Execute a browser tool call via browser_mcp. Issue #1368.

        Routes navigate/click/screenshot/etc. to the Browser VM through
        the existing browser_mcp.send_to_browser_vm() function.
        Issue #4261: Wires BEFORE/AFTER_TOOL_EXECUTE and TOOL_ERROR hooks.

        Yields:
            WorkflowMessage for browser tool execution stages
        """
        tool_name = tool_call["name"]
        params = tool_call.get("params", {})
        description = tool_call.get("description", f"Browser: {tool_name}")

        logger.info("[Issue #1368] Browser tool: %s params=%s", tool_name, params)

        yield WorkflowMessage(
            type="tool_execution",
            content=f"Executing browser action: {description}",
            metadata={"tool": tool_name, "params": params},
        )

        try:
            validation_error = self._validate_browser_params(tool_name, params)
            if validation_error:
                # Keep status="error" so the agent loop still knows the tool didn't run.
                execution_results.append({"tool": tool_name, "status": "error", "error": validation_error})
                # #10914: a disallowed URL / unsafe script is an expected policy block,
                # not a system failure — surface it to the user as a normal assistant
                # notice (tool_result) so the UI doesn't render a scary red "Error:" banner.
                yield WorkflowMessage(
                    type="tool_result",
                    content=validation_error,
                    metadata={"tool": tool_name, "blocked": True},
                )
                return

            # Issue #4261: Wire BEFORE_TOOL_EXECUTE hook for browser tools
            should_execute = await _emit_before_tool_execute(tool_name, params, session_id)
            if not should_execute:
                logger.info(
                    "[Issue #4261] Browser tool execution cancelled by hook: %s",
                    tool_name,
                )
                yield WorkflowMessage(
                    type="error",
                    content=f"Browser tool execution cancelled: {tool_name}",
                    metadata={"tool": tool_name, "cancelled_by_hook": True},
                )
                return

            from api.browser_mcp import DEFAULT_BROWSER_SESSION_ID, send_to_browser_vm

            # #11539: route this call to the BrowserContext dedicated to this
            # conversation so cookies/login state never bleed into another one.
            result = await send_to_browser_vm(
                tool_name,
                params,
                session_id=session_id or DEFAULT_BROWSER_SESSION_ID,
            )

            # Issue #4261: Wire AFTER_TOOL_EXECUTE hook for browser tools
            result_text = str(result)
            result_text = await _emit_after_tool_execute(tool_name, result_text, session_id, {})

            yield self._record_browser_success(tool_name, params, result, execution_results)

        except Exception as e:
            # Issue #4261: Wire TOOL_ERROR hook for browser tools
            await _emit_tool_error(tool_name, e, session_id, {})
            logger.error("[Issue #1368] Browser tool '%s' failed: %s", tool_name, e)
            execution_results.append(
                {
                    "tool": tool_name,
                    "status": "error",
                    "error": "Browser tool execution failed",
                }
            )
            yield WorkflowMessage(
                type="error",
                content=f"Browser tool '{tool_name}' execution failed",
                metadata={"tool": tool_name, "error": True},
            )

    def _record_browser_success(
        self,
        tool_name: str,
        params: dict[str, Any],
        result: dict[str, Any],
        execution_results: list[dict[str, Any]],
    ) -> "WorkflowMessage":
        """Record a successful browser tool execution and return its WorkflowMessage. Issue #2735.

        Extracted from _handle_browser_tool to keep parent under 65 lines.
        """
        summary = self._format_browser_result(tool_name, params, result)
        execution_results.append({"tool": tool_name, "status": "success", "output": summary})
        return WorkflowMessage(
            type="command_output",
            content=summary,
            metadata={
                "tool": tool_name,
                "params": params,
                "result": result,
                "status": "success",
            },
        )

    def _format_browser_result(
        self,
        tool_name: str,
        params: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        """Format browser tool result as text for LLM context. Issue #1368.

        Browser VM returns: {"success": bool, "action": str, "result": {...}}
        The inner 'result' dict contains tool-specific data.
        """
        inner = result.get("result", result)

        if tool_name == "navigate":
            url = inner.get("url", params.get("url", ""))
            title = inner.get("title", "")
            return f"Navigated to: {url}\nPage title: {title}"

        if tool_name == "screenshot":
            has_image = bool(inner.get("image") or inner.get("screenshot"))
            if has_image:
                return "Screenshot captured successfully."
            return "Screenshot failed."

        if tool_name == "get_text":
            text = inner.get("text", "")
            if text:
                return f"Text content: {text[:2000]}"
            return "No text found."

        if tool_name == "get_attribute":
            value = inner.get("value", "")
            attr = params.get("attribute", "")
            return f"Attribute '{attr}': {value}"

        if tool_name == "evaluate":
            js_result = inner.get("result", "")
            return f"JavaScript result: {js_result}"

        if tool_name == "click":
            return f"Clicked: {params.get('selector', '')}"

        if tool_name == "fill":
            sel = params.get("selector", "")
            return f"Filled '{sel}' with value"

        if tool_name == "select":
            val = params.get("value", "")
            sel = params.get("selector", "")
            return f"Selected '{val}' in {sel}"

        if tool_name == "hover":
            return f"Hovered over: {params.get('selector', '')}"

        if tool_name == "wait_for_selector":
            sel = params.get("selector", "")
            return f"Element found: {sel}"

        return json.dumps(result, default=str)[:1000]

    async def _handle_web_search_tool(
        self,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
        session_id: str = "",
    ):
        """Execute a web search via browser VM. Issue #2306.

        Abstracts the multi-step browser flow (navigate → fill → click → get_text)
        into a single tool call so small models don't need to orchestrate it.
        Issue #4261: Wires BEFORE/AFTER_TOOL_EXECUTE and TOOL_ERROR hooks.

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

        # Issue #4261: Wire BEFORE_TOOL_EXECUTE hook for web_search
        should_execute = await _emit_before_tool_execute("web_search", params, session_id)
        if not should_execute:
            logger.info("[Issue #4261] Web search cancelled by hook")
            yield WorkflowMessage(
                type="error",
                content="Web search execution cancelled",
                metadata={"tool": "web_search", "cancelled_by_hook": True},
            )
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
    ):
        """Dispatch one of the 4 web research tools. Issue #7509.

        Routes to _exec_scrape_url, _exec_crawl_site, _exec_map_site, or
        _exec_extract_structured_data based on tool_name.  Yields WorkflowMessages
        for execution stages and final output.
        """
        params = tool_call.get("params", {})
        logger.info("[Issue #7509] Web research tool: %s params=%s", tool_name, list(params.keys()))

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

    async def _handle_llc_tool(self, tool_name, tool_call, execution_results, ctx):
        """Dispatch an LLC work-object tool company-scoped (#11501).

        company_id comes from the chat request context (set by the CEO-chat
        endpoint, T2). A missing/invalid context surfaces as a tool error the
        LLM can react to, rather than a crash.
        """
        params = tool_call.get("params", {}) or {}
        _cctx = ctx.context if ctx is not None and ctx.context else {}
        company_id = _cctx.get("company_id")
        # #11501 review: actor for audit/authz comes from the authenticated chat
        # context, never from LLM-supplied params.
        user_id = _cctx.get("user_id")
        try:
            result = await dispatch_llc_tool(tool_name, params, company_id, user_id)
            execution_results.append({"tool": tool_name, "status": "success", "output": result})
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
        from web_fetch import RenderMode, WebFetcher

        url = params.get("url", "").strip()
        render_str = params.get("render", "auto")
        render = RenderMode(render_str)
        result = await WebFetcher.fetch(url, render=render)
        if not result.success:
            return f"## Fetch failed\n\nURL: {url}\nError: {result.error_code}"
        title = f"# {result.title}\n\n" if result.title else ""
        header = f"## Scraped: {url} (status {result.status_code}, source: {result.source})\n\n"
        return header + title + (result.markdown or "*(no content)*")

    async def _exec_crawl_site(self, params: dict) -> str:
        """BFS crawl seed URLs and return a markdown index. Issue #7509."""
        from knowledge.connectors.models import ConnectorConfig
        from knowledge.connectors.web_crawler import WebCrawlerConnector

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
        return _format_crawl_results(seed_urls, results)

    async def _exec_map_site(self, params: dict) -> str:
        """Discover URLs for a domain via sitemap or BFS. Issue #7509."""
        from web_fetch.site_mapper import SiteMapper

        domain = params.get("domain", "").strip()
        max_urls: int = int(params.get("max_urls", 500))
        respect_robots: bool = bool(params.get("respect_robots", True))
        site_result = await SiteMapper.map_site(domain, max_urls=max_urls, respect_robots=respect_robots)
        return _format_map_results(site_result)

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

    def _enforce_forbidden_work(
        self,
        tool_call: dict[str, Any],
        ctx: "LLMIterationContext" | None,
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage | None:
        """Hard-block a tool the acting agent's forbidden_work manifest forbids (GH#11145).

        Resolves the acting agent id from ``ctx.agent_context`` and matches the tool
        against that agent's manifest via the shared ``match_forbidden_tool`` matcher.
        Records the failure in ``execution_results`` and returns an error
        ``WorkflowMessage`` when the tool is forbidden, else ``None``. Profile-less
        agents resolve to an empty manifest and are never blocked here.
        """
        from orchestration.agent_registry import match_forbidden_tool, resolve_forbidden_tools

        agent_id = ctx.agent_context.agent_id if (ctx is not None and ctx.agent_context is not None) else None
        forbidden = resolve_forbidden_tools(agent_id)
        if not forbidden:
            return None
        tool_name = tool_call.get("name", "")
        matched = match_forbidden_tool(tool_name, forbidden)
        if matched is None:
            return None
        error = f"Tool '{tool_name}' is forbidden by agent '{agent_id}' capability manifest (matched '{matched}')"
        logger.warning(
            "[GH#11145] Blocked forbidden tool '%s' for agent '%s' (matched '%s')",
            tool_name,
            agent_id,
            matched,
        )
        execution_results.append({"tool": tool_name, "status": "error", "error": error, "forbidden_by_manifest": True})
        return WorkflowMessage(
            type="error",
            content=error,
            metadata={"tool": tool_name, "error": True, "forbidden_by_manifest": True},
        )

    def _enforce_config_protection(
        self,
        tool_call: dict[str, Any],
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage | None:
        """Block a write that would weaken a linter/formatter config (GH#11177).

        Reuses the dependency-free ``autobot_shared.config_guard`` matcher against
        the tool's target path (``params`` for built-in tools, ``arguments`` for
        MCP). Records the failure and returns an error ``WorkflowMessage`` when the
        target is a protected config, else ``None``. ``AUTOBOT_ALLOW_CONFIG_EDITS``
        opts out.
        """
        from autobot_shared.config_guard import config_edits_allowed, protected_config_for

        if config_edits_allowed():
            return None
        args = tool_call.get("params") or tool_call.get("arguments") or {}
        matched = protected_config_for(tool_call.get("name", ""), args)
        if matched is None:
            return None
        tool_name = tool_call.get("name", "")
        error = (
            f"Editing linter/formatter config '{matched}' is blocked (config-protection): "
            f"fix the code to satisfy the gate instead of weakening it. "
            f"Set AUTOBOT_ALLOW_CONFIG_EDITS=1 for an intentional change."
        )
        logger.warning("[GH#11177] Blocked config-protection write to '%s' (tool '%s')", matched, tool_name)
        execution_results.append({"tool": tool_name, "status": "error", "error": error, "config_protection": True})
        return WorkflowMessage(
            type="error",
            content=error,
            metadata={"tool": tool_name, "error": True, "config_protection": True},
        )

    def _enforce_fact_forcing(
        self,
        tool_call: dict[str, Any],
        ctx: "LLMIterationContext" | None,
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage | None:
        """Block the first edit to an existing, uninvestigated file (GH#11178).

        Records this call's read/grep target on the turn-scoped investigated set
        (``ctx.context``), then blocks an edit to an existing file not yet read
        this turn. New files are never blocked; the block self-clears once the
        agent reads the file. Off unless ``AUTOBOT_FACT_FORCING`` is set, and a
        no-op without a ``ctx`` to carry the per-turn state.
        """
        from autobot_shared.fact_forcing_guard import (
            fact_forcing_env_enabled,
            record_investigation,
            uninvestigated_edit_path,
        )

        if not fact_forcing_env_enabled() or ctx is None:
            return None
        investigated: set[str] = ctx.context.setdefault("_fact_forcing_investigated", set())
        name = tool_call.get("name", "")
        args = tool_call.get("params") or tool_call.get("arguments") or {}
        record_investigation(name, args, investigated)
        path = uninvestigated_edit_path(name, args, investigated)
        if path is None:
            return None
        error = (
            f"Editing '{path}' is blocked (fact-forcing): read the file and its "
            f"importers/call-sites first so the change is grounded, then retry."
        )
        logger.warning("[GH#11178] Blocked fact-forcing edit to '%s' (tool '%s')", path, name)
        execution_results.append({"tool": name, "status": "error", "error": error, "fact_forcing": True})
        return WorkflowMessage(
            type="error",
            content=error,
            metadata={"tool": name, "error": True, "fact_forcing": True},
        )

    def _enforce_work_item_approval(
        self,
        tool_call: dict[str, Any],
        ctx: "LLMIterationContext" | None,
        execution_results: list[dict[str, Any]],
    ) -> WorkflowMessage | None:
        """Hold a tool the work item declared as approval-gated (GH#11160).

        When the run carries a work item whose ``requires_approval_before`` names
        the action category of this tool, the action is held pending approval — the
        declared gate is honored at the production seam. No work item / no matching
        category → ``None``. Categories are resolved onto the context upstream, so
        this needs no DB round-trip.
        """
        if ctx is None or not getattr(ctx, "requires_approval_before", None):
            return None
        tool_name = tool_call.get("name", "")
        category = _approval_category_for(tool_name, ctx.requires_approval_before)
        if category is None:
            return None
        work_item_id = getattr(ctx, "work_item_id", None)
        msg = (
            f"Action '{tool_name}' requires approval before proceeding — the work item "
            f"declares '{category}' as approval-gated (requires_approval_before)."
        )
        logger.warning("[GH#11160] Held tool '%s' pending approval — declared category '%s'", tool_name, category)
        execution_results.append(
            {
                "tool": tool_name,
                "status": "pending_approval",
                "reason": msg,
                "approval_category": category,
                "work_item_id": work_item_id,
            }
        )
        return WorkflowMessage(
            type="approval_required",
            content=msg,
            metadata={
                "tool": tool_name,
                "approval_required": True,
                "category": category,
                "work_item_id": work_item_id,
            },
        )

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

        # GH#11160: hold a tool the work item declared as approval-gated
        # (requires_approval_before) pending approval, at the same seam.
        approval_msg = self._enforce_work_item_approval(tool_call, ctx, execution_results)
        if approval_msg is not None:
            yield approval_msg
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
            async for msg in self._handle_delegate_tool(tool_call, execution_results, ctx):
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
            async for msg in self._handle_llc_tool(tool_name, tool_call, execution_results, ctx):
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
    ) -> AsyncIterator[Any]:
        """Return the handler async-generator for a uniform builtin tool (GH#11489).

        Membership SSOT is ``_UNIFORM_BUILTIN_TOOLS``; the caller has already run
        the shared gate. Adding a builtin that follows the standard gate takes a
        schema entry plus one row here — no new branch at the dispatch seam.
        """
        if tool_name in BROWSER_TOOL_NAMES:  # Issue #1368: route to browser VM
            return self._handle_browser_tool(tool_call, execution_results, session_id)
        if tool_name == "web_search":  # Issue #2306: multi-step browser flow
            return self._handle_web_search_tool(tool_call, execution_results, session_id)
        if tool_name in WEB_RESEARCH_TOOL_NAMES:  # Issue #7509
            return self._handle_web_research_tool(tool_name, tool_call, execution_results, session_id)
        if tool_name == "execute_command":
            return self._dispatch_execute_command(
                tool_call,
                session_id,
                terminal_session_id,
                ollama_endpoint,
                selected_model,
                execution_results,
                additional_response_parts,
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
    ):
        """Delegate execute_command tool call to _process_single_command. Issue #2735.

        Extracted from _dispatch_tool_call to keep parent under 65 lines.
        """
        async for msg in self._process_single_command(
            tool_call,
            session_id,
            terminal_session_id,
            ollama_endpoint,
            selected_model,
            execution_results,
            additional_response_parts,
        ):
            yield msg

    # ------------------------------------------------------------------ #
    # GH#11568: compose tool handlers                                     #
    # ------------------------------------------------------------------ #

    def _guard_compose(self, program: str, agent_id: "str | None") -> "WorkflowMessage | None":
        """Run AST guard; return error WorkflowMessage on violation, else None."""
        from chat_workflow.code_exec.ast_guard import check_script
        from chat_workflow.code_exec.shim_codegen import injectable_tool_set
        from orchestration.agent_registry import resolve_forbidden_tools

        forbidden = resolve_forbidden_tools(agent_id)
        injected = frozenset(injectable_tool_set([], forbidden))
        verdict = check_script(program, frozenset(forbidden), injected_tools=injected)
        if verdict.ok:
            return None
        lines = "; ".join(f"line {v['line']}: {v['message']}" for v in verdict.violations)
        return WorkflowMessage(
            type="tool_result",
            content=f"compose script rejected by AST guard: {lines}",
            metadata={"tool_name": "compose", "ast_violations": verdict.violations},
        )

    @staticmethod
    def _compose_auto_approvable(shim_snapshot: list[str]) -> bool:
        """Auto-approve only when the flag is on AND all shims are read-only (design §3.1)."""
        return CODEEXEC_AUTOAPPROVE_READONLY and set(shim_snapshot) <= CODEEXEC_READONLY_TOOLS

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

        Mirrors the terminal-command approval loop: a bounded poll on the persisted
        gate. Returns ``approved``/``rejected``/``revision_requested``, or
        ``timeout`` when no decision lands within the wait budget.
        """
        import uuid as _uuid

        from services.approval_gate_service import ApprovalGateService
        from user_management.database import get_async_session_factory

        elapsed = 0
        session_factory = get_async_session_factory()
        while elapsed < CODEEXEC_APPROVAL_WAIT_SECONDS:
            async with session_factory() as db:
                approval = await ApprovalGateService(db).get(_uuid.UUID(approval_id))
            status = getattr(approval, "status", None)
            if status and status != "pending":
                return status
            await asyncio.sleep(CODEEXEC_APPROVAL_POLL_SECONDS)
            elapsed += CODEEXEC_APPROVAL_POLL_SECONDS
        return "timeout"

    async def _persist_compose_approval(self, program: str, shim_snapshot: list[str], session_id: str) -> "str | None":
        """Persist a WORKFLOW_GATE Approval carrying program + shims + budgets (GH#11568)."""
        from chat_workflow.code_exec.broker import CODEEXEC_MAX_TOOL_CALLS
        from models.approval import ApprovalType
        from secure_sandbox_executor import CODEEXEC_TIMEOUT_SECONDS
        from services.approval_gate_service import ApprovalGateService
        from user_management.database import get_async_session_factory

        context = {
            "program": program,
            "shim_snapshot": shim_snapshot,
            "budgets": {"max_tool_calls": CODEEXEC_MAX_TOOL_CALLS, "timeout_seconds": CODEEXEC_TIMEOUT_SECONDS},
        }
        session_factory = get_async_session_factory()
        async with session_factory() as db:
            approval = await ApprovalGateService(db).create_approval(
                title="compose script execution",
                approval_type=ApprovalType.WORKFLOW_GATE.value,
                requested_by_agent="chat_agent",
                description="Sandboxed Python compose script awaiting approval.",
                workflow_id=session_id,
                workflow_step="compose",
                context=context,
            )
            return str(approval.id)

    def _build_compose_dispatch(self, session_id: str, ctx: "LLMIterationContext | None"):
        """Return an async dispatch callable routing shim calls through the seam (GH#11568)."""

        async def _dispatch(tool: str, params: dict) -> Any:
            sub_results: list[dict[str, Any]] = []
            sub_call = {"name": tool, "params": params}
            async for _ in self._dispatch_tool_call(sub_call, session_id, session_id, "", "", sub_results, [], ctx=ctx):
                pass
            last = sub_results[-1] if sub_results else {}
            if last.get("status") == "error":
                raise RepairableException(last.get("error", "tool dispatch failed"))
            return last.get("output", last)

        return _dispatch

    async def _execute_compose(
        self, program: str, agent_id: "str | None", run_id: str, session_id: str, ctx: "LLMIterationContext | None"
    ) -> "WorkflowMessage":
        """Run the script inside the sandbox via a live broker; return result msg."""
        from chat_workflow.code_exec.broker import CodeExecBroker
        from chat_workflow.code_exec.shim_codegen import generate_shim_module, injectable_tool_set
        from orchestration.agent_registry import resolve_forbidden_tools
        from secure_sandbox_executor import CODEEXEC_TIMEOUT_SECONDS, SecureSandboxExecutor  # lazy

        forbidden = resolve_forbidden_tools(agent_id)
        tools = injectable_tool_set([], forbidden)
        shim_src = generate_shim_module(tools)
        broker = CodeExecBroker(
            self._build_compose_dispatch(session_id, ctx),
            tools,
            forbidden,
            run_id,
            f"autobot:codeexec:security:events:{run_id}",
            progress_channel=f"workflow:{session_id}",
        )
        executor = SecureSandboxExecutor()
        result = await executor.execute_with_stdio_broker(program, shim_src, broker, CODEEXEC_TIMEOUT_SECONDS, run_id)
        return self._compose_result_message(result, run_id)

    def _compose_result_message(self, result: Any, run_id: str) -> "WorkflowMessage":
        """Build the tool_result WorkflowMessage from a SandboxResult (GH#11568)."""
        if result.success:
            return WorkflowMessage(
                type="tool_result",
                content=result.stdout or "(no output)",
                metadata={"tool_name": "compose", "run_id": run_id},
            )
        content = f"compose execution failed (exit {result.exit_code}): {result.stderr or result.stdout}"
        return WorkflowMessage(
            type="tool_result",
            content=content,
            metadata={"tool_name": "compose", "run_id": run_id, "failed": True},
        )

    def _compose_shim_snapshot(self, agent_id: "str | None") -> list[str]:
        """Injectable-tool snapshot for this agent (allowlist ∩ allowed − forbidden)."""
        from chat_workflow.code_exec.shim_codegen import injectable_tool_set
        from orchestration.agent_registry import resolve_forbidden_tools

        return injectable_tool_set([], resolve_forbidden_tools(agent_id))

    def _reject_delegated_compose(self, agent_id: "str | None") -> "WorkflowMessage | None":
        """Main-chat-only: reject compose for any profile-bound (delegated) agent (GH#11568)."""
        if agent_id is None:
            return None
        return WorkflowMessage(
            type="tool_result",
            content="compose is not available for delegated subagents",
            metadata={"tool_name": "compose"},
        )

    def _compose_gate_request_msg(self, approval_id: str, shim_snapshot: list[str]) -> "WorkflowMessage":
        """Build the WORKFLOW_GATE approval-required notification (GH#11568)."""
        return WorkflowMessage(
            type="approval_required",
            content="compose script requires approval before execution",
            metadata={
                "tool": "compose",
                "approval_required": True,
                "approval_id": approval_id,
                "shim_snapshot": shim_snapshot,
            },
        )

    def _compose_gate_refusal_msg(self, status: str) -> "WorkflowMessage":
        """Terminal refusal message for a non-approved gate (GH#11568)."""
        return WorkflowMessage(
            type="tool_result",
            content=f"compose execution not approved (gate status: {status}).",
            metadata={"tool_name": "compose", "approval_status": status, "denied": True},
        )

    async def _handle_compose_tool(
        self,
        tool_call: dict[str, Any],
        session_id: str,
        execution_results: list[dict[str, Any]],
        ctx: "LLMIterationContext | None",
    ):
        """Handle the compose tool call — main chat agent only (GH#11568)."""
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
            ):
                if isinstance(result, tuple):
                    break_loop_requested, respond_content = result
                else:
                    yield result

        if execution_results:
            yield self._build_execution_summary(execution_results)

        yield (break_loop_requested, respond_content)
