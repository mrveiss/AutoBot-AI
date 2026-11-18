# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE browser tool list the chat prompts and the tool-name reminder render (#21772).

The browser section of ``system_prompt.md`` / ``system_prompt_simple.md`` and the
"use ONLY these tool names" reminder in ``chat_workflow/manager.py`` were three
hand-written lists that drifted (none named ``extract_content``, ``scrape_url`` or
``extract_structured_data``). The set of names comes from
``autobot_shared.tool_catalogue.BROWSER_PROMPT_TOOLS``; this module only adds the
one-line wording. A catalogue tool without wording is still listed (name only), so
adding a tool to the catalogue never needs a prompt edit.
"""

from autobot_shared import tool_catalogue

#: tool name -> (params hint, one-line description). Wording only; membership is the catalogue's.
_WORDING: "dict[str, tuple[str, str]]" = {
    "navigate": ('{"url": ...}', "go to a URL"),
    "screenshot": ("{}", "capture the current page"),
    "click": ('{"selector": ...}', "click an element by CSS selector"),
    "fill": ('{"selector": ..., "value": ...}', "type into an input by CSS selector"),
    "select": ('{"selector": ..., "value": ...}', "choose an option in a dropdown"),
    "hover": ('{"selector": ...}', "hover over an element"),
    "evaluate": ('{"script": ...}', "run JavaScript on the page"),
    "get_text": ('{"selector": ...}', "text of ONE element you already know the selector of"),
    "get_attribute": ('{"selector": ..., "attribute": ...}', "an attribute of an element"),
    "wait_for_selector": ('{"selector": ...}', "wait for an element to appear"),
    "browser_state": ("{}", "URL, title and a numbered menu of the page's interactive elements"),
    "click_index": ('{"index": N}', "click an element by its menu number"),
    "fill_index": ('{"index": N, "value": ...}', "fill an element by its menu number"),
    "select_index": ('{"index": N, "value": ...}', "select an option by its menu number"),
    "hover_index": ('{"index": N}', "hover an element by its menu number"),
    "extract_content": ('{"goal": ...}', "READ the live page you are on, guided by a goal (no selector needed)"),
    "scrape_url": ('{"url": ...}', "fetch a URL and read it as markdown without driving the browser"),
    "extract_structured_data": ('{"url": ..., "schema": {...}}', "fetch a URL and return data matching a JSON schema"),
}

READ_RULE = (
    "To READ information from a page, use `extract_content` (the page you are on) or `scrape_url` "
    "(any URL). Never guess a CSS selector to read content; use selectors or menu numbers only to "
    "INTERACT (click, fill, select)."
)


def browser_tool_names() -> "tuple[str, ...]":
    """Every browser tool the chat role may call, straight from the catalogue."""
    return tuple(tool_catalogue.BROWSER_PROMPT_TOOLS)


def _line(name: str) -> str:
    params, text = _WORDING.get(name, ("{...}", "browser tool"))
    return f"- `{name}` {params}: {text}"


def render_browser_tools_section() -> str:
    """Markdown for the "Browser Tools" section body of both chat system prompts."""
    lines = "\n".join(_line(n) for n in browser_tool_names())
    example = '<TOOL_CALL name="navigate" params=\'{"url":"https://example.com"}\'>Navigate to example.com</TOOL_CALL>'
    return (
        "You can browse the web. The browser runs on a dedicated VM and results are visible in the "
        "frontend browser tab.\n\n"
        f"Call format:\n```\n{example}\n```\n\n"
        f"Tools:\n{lines}\n\n**Reading vs interacting:** {READ_RULE}"
    )


def render_tool_name_reminder_lines() -> str:
    """The browser lines of the "You MUST use ONLY the following tool names" reminder."""
    return "".join(f"- {n}: {_WORDING.get(n, ('', 'browser tool'))[1]}\n" for n in browser_tool_names())


def template_vars() -> "dict[str, str]":
    """Jinja variables every prompt template can use (merged by ``PromptManager.get``)."""
    return {"browser_tools_section": render_browser_tools_section()}
