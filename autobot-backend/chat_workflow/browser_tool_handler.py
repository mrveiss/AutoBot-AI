# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Browser tool dispatch and result formatting for ``chat_workflow.tool_handler``.

Extracted from ``tool_handler`` (#14469) to offset that PR's own additions and
keep the module under its file-size ceiling — the same move #14497 made for
the seam guards in ``tool_dispatch_guards.py``. None of these functions touch
instance state beyond calling one another, so this module carries no state of
its own; ``ToolHandlerMixin`` keeps thin delegating methods (same names, minus
the leading underscore here) so the ``_dispatch_tool_call`` call sites and
existing test monkey-patches (``handler._handle_browser_tool = ...``,
``ToolHandlerMixin._validate_browser_params``) are unaffected.

``handle_browser_tool`` preserves the deny-before-call contract: the
BEFORE_TOOL_EXECUTE hook's ``should_execute`` verdict is checked and the
generator ``return``s before ``send_to_browser_vm`` (the guarded call) ever
runs.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from async_chat_workflow import WorkflowMessage
from autobot_shared.auth.mcp_tool_permissions import required_permission
from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from chat_workflow.llm_handler import (
    _emit_after_tool_execute,
    _emit_before_tool_execute,
    _emit_tool_error,
)

logger = get_logger(__name__)

# Issue #11537: how many numbered elements to render in the LLM-visible state
# block per browser tool result (the browser-worker itself caps the raw list
# via BROWSER_STATE_MAX_ELEMENTS; this bounds the prompt-text rendering).
BROWSER_STATE_PROMPT_MAX_ELEMENTS = env_int("AUTOBOT_BROWSER_STATE_PROMPT_MAX_ELEMENTS", default=30)

# Issue #11537: text formatters for the four indexed-element tool results,
# keyed by tool name so format_browser_action_text stays a flat dispatch.
_INDEXED_ELEMENT_TOOL_TEXT: dict[str, Any] = {
    "click_index": lambda params, inner: (
        f"Clicked element [{params.get('index')}]: "
        f"{(inner.get('resolved') or {}).get('name') or (inner.get('resolved') or {}).get('role', 'element')}"
    ),
    "fill_index": lambda params, inner: (
        f"Filled element [{params.get('index')}] "
        f"({(inner.get('resolved') or {}).get('name') or (inner.get('resolved') or {}).get('role', 'element')}) "
        "with value"
    ),
    "select_index": lambda params, inner: (f"Selected '{params.get('value', '')}' in element [{params.get('index')}]"),
    "hover_index": lambda params, inner: f"Hovered over element [{params.get('index')}]",
}


async def validate_browser_params(tool_name: str, params: dict[str, Any]) -> str | None:
    """Validate browser tool params. Returns a user-friendly block notice or None.

    #1368 / #10914: a disallowed URL or unsafe script is an *expected* policy
    outcome, so the returned text reads as a friendly notice (rendered as a
    normal assistant message, not a scary error banner — see handle_browser_tool).

    #13236 step 5: ``is_url_allowed`` became async when it stopped matching
    URL prefixes with a regex and started resolving the host, so this is
    async too. The caller already awaits inside an async method.
    """
    from api.browser_mcp import is_script_safe, is_url_allowed

    if tool_name == "navigate" and not await is_url_allowed(params.get("url", "")):
        url = params.get("url", "")
        return f"I can't open that link ({url}) — it isn't on the list of sites I'm allowed to browse."
    if tool_name == "evaluate" and not is_script_safe(params.get("script", "")):
        return "I can't run that browser action — it was blocked by the security policy."
    return None


async def handle_browser_tool(
    tool_call: dict[str, Any],
    execution_results: list[dict[str, Any]],
    session_id: str = "",
    role: str = "user",
) -> AsyncIterator[WorkflowMessage]:
    """Execute a browser tool call via browser_mcp. Issue #1368.

    Routes navigate/click/screenshot/etc. to the Browser VM through
    the existing browser_mcp.send_to_browser_vm() function.
    Issue #4261: Wires BEFORE/AFTER_TOOL_EXECUTE and TOOL_ERROR hooks.
    Issue #14469: declares this call's required permission via the same
    ``required_permission()`` table the ``browser_mcp`` MCP bridge uses —
    this is the non-registry path for the identical tool names, so it
    reuses that classification (read baseline, MCP_BROWSER_CONTROL for
    anything that drives the page) instead of a second, disconnected one.

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
        validation_error = await validate_browser_params(tool_name, params)
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

        # Issue #4261/#14469: Wire BEFORE_TOOL_EXECUTE hook for browser tools,
        # declaring the permission this specific action requires.
        tool_permission = required_permission(tool_name, bridge_name="browser_mcp")
        should_execute = await _emit_before_tool_execute(
            tool_name,
            params,
            session_id,
            tool_permission=tool_permission.value if tool_permission else None,
            user_role=role,
        )
        if not should_execute:
            logger.info(
                "[Issue #4261] Browser tool execution cancelled by hook: %s",
                tool_name,
            )
            cancellation_metadata = {"tool": tool_name, "cancelled_by_hook": True}
            if tool_permission is not None:
                cancellation_metadata["reason"] = "permission_denied"
            yield WorkflowMessage(
                type="error",
                content=f"Browser tool execution cancelled: {tool_name}",
                metadata=cancellation_metadata,
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

        yield record_browser_success(tool_name, params, result, execution_results)

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


def record_browser_success(
    tool_name: str,
    params: dict[str, Any],
    result: dict[str, Any],
    execution_results: list[dict[str, Any]],
) -> "WorkflowMessage":
    """Record a successful browser tool execution and return its WorkflowMessage. Issue #2735.

    Extracted from handle_browser_tool to keep parent under 65 lines.
    Issue #11538: also carries the raw screenshot (if any) into
    execution_results so the vision-in-the-loop continuation can find it.
    """
    summary = format_browser_result(tool_name, params, result)
    entry: dict[str, Any] = {"tool": tool_name, "status": "success", "output": summary}
    base64_image = extract_browser_image(result)
    if base64_image:
        entry["base64_image"] = base64_image
    execution_results.append(entry)
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


def extract_browser_image(result: dict[str, Any]) -> str | None:
    """Pull the base64 PNG out of a browser tool result, if present. Issue #11538.

    Only the ``screenshot`` action returns image bytes today; kept
    tool-name-agnostic (checks common keys) so a future browser/VNC
    action that starts returning images is picked up automatically.
    """
    inner = result.get("result", result)
    return inner.get("image") or inner.get("screenshot")


def format_page_state_block(page_state: dict[str, Any] | None) -> str:
    """Render the numbered interactive-element menu for LLM consumption. Issue #11537.

    OpenManus-style: the model picks click_index/fill_index targets from
    this menu instead of guessing a CSS selector. Appended to every
    browser tool result so the menu is always current (task 4).
    """
    if not page_state:
        return ""
    elements = page_state.get("elements") or []
    if not elements:
        return ""
    lines = [f"\nInteractive elements ({len(elements)}):"]
    for el in elements[:BROWSER_STATE_PROMPT_MAX_ELEMENTS]:
        role = el.get("role", el.get("tag", "element"))
        name = (el.get("name") or "").strip()
        label = f' "{name}"' if name else ""
        lines.append(f"  [{el.get('index')}] {role}{label}")
    return "\n".join(lines)


def format_browser_result(
    tool_name: str,
    params: dict[str, Any],
    result: dict[str, Any],
) -> str:
    """Format browser tool result as text for LLM context. Issue #1368.

    Browser VM returns: {"success": bool, "action": str, "result": {...}}
    The inner 'result' dict contains tool-specific data. Issue #11537:
    appends the numbered interactive-element menu when present.
    """
    inner = result.get("result", result)
    summary = format_browser_action_text(tool_name, params, inner, result)
    # browser_state's payload *is* the page state; every other action
    # carries it nested under "page_state" (attached post-action).
    page_state = inner if tool_name == "browser_state" else inner.get("page_state")
    state_block = format_page_state_block(page_state)
    return summary + state_block if state_block else summary


def format_browser_action_text(
    tool_name: str,
    params: dict[str, Any],
    inner: dict[str, Any],
    result: dict[str, Any],
) -> str:
    """Build the tool-specific summary line for format_browser_result. Issue #1368/#11537."""
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
            # #12757: browser page text is untrusted third-party content —
            # sanitize and put it behind a trust boundary before it lands in
            # the agent's context as if it were operator input.
            from knowledge.query_sanitizer import sanitize_and_wrap_web_content

            return "Text content: " + sanitize_and_wrap_web_content(text[:2000], params.get("url", ""))
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

    if tool_name in _INDEXED_ELEMENT_TOOL_TEXT:
        return _INDEXED_ELEMENT_TOOL_TEXT[tool_name](params, inner)

    if tool_name == "browser_state":
        elements = inner.get("elements") or []
        return f"Page state: {inner.get('url', '')} — {len(elements)} interactive element(s)"

    return json.dumps(result, default=str)[:1000]
