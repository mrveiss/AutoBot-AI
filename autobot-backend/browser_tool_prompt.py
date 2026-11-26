# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE browser tool list the chat prompts and the tool-name reminder render (#21772).

The browser section of ``system_prompt.md`` / ``system_prompt_simple.md`` and the
"use ONLY these tool names" reminder in ``chat_workflow/manager.py`` were three
hand-written lists that drifted (none named ``extract_content``, ``scrape_url`` or
``extract_structured_data``). The set of names comes from
``autobot_shared.tool_catalogue.BROWSER_PROMPT_TOOLS``; the one-line wording
(``BROWSER_PROMPT_WORDING``) is declared beside it, and this module only renders both.
A catalogue tool without wording is still listed (name only), so adding a tool never needs a prompt edit.
"""

from markupsafe import Markup

from autobot_shared import tool_catalogue
from web_search_schema import WEB_SEARCH_SCHEMA

READ_RULE = (
    "To READ information from a page, use `extract_content` (the page you are on) or `scrape_url` "
    "(any URL). Never guess a CSS selector to read content; `get_text` / `get_attribute` are only for a "
    "selector you were given or already saw. Use selectors or menu numbers to INTERACT (click, fill, select)."
)


def browser_tool_names() -> "tuple[str, ...]":
    """Every browser tool the chat role may call, straight from the catalogue."""
    return tuple(tool_catalogue.BROWSER_PROMPT_TOOLS)


def _line(name: str) -> str:
    params, text = tool_catalogue.BROWSER_PROMPT_WORDING.get(name, ("{...}", "browser tool"))
    return f"- `{name}` {params}: {text}"


def render_browser_tools_section() -> str:
    """Markdown for the "Browser Tools" section body of both chat system prompts."""
    lines = "\n".join(_line(n) for n in browser_tool_names())
    example = (
        '<TOOL_CALL name="navigate" params=\'{"url":"https://example.com"}\'>Navigate to example.com</TOOL_CALL>\n'
        '<TOOL_CALL name="fill" params=\'{"selector":"input#search","value":"query"}\'>Fill search box</TOOL_CALL>'
    )
    return (
        "You can browse the web. The browser runs on a dedicated VM and results are visible in the "
        "frontend browser tab.\n\n"
        f"Call format (examples):\n```\n{example}\n```\n\n"
        f"Tools:\n{lines}\n\n**Reading vs interacting:** {READ_RULE}"
    )


def render_tool_name_reminder_lines() -> str:
    """The browser lines of the "You MUST use ONLY the following tool names" reminder."""
    return "".join(
        f"- {n}: {tool_catalogue.BROWSER_PROMPT_WORDING.get(n, ('', 'browser tool'))[1]}\n"
        for n in browser_tool_names()
    )


def render_parameter_lines(schema: dict) -> str:
    """One ``- `name` (required|optional, type): description`` line per property of a tool's JSON *schema* (#21877).

    The chat prompts render the ``web_search`` parameter list from the tool's own schema, so a parameter the
    handler honours (``fetch_full``) can never be missing from what the model is told.
    """
    required = set(schema.get("required", ()))
    lines = []
    for name, spec in schema.get("properties", {}).items():
        kind = "required" if name in required else "optional"
        description = str(spec.get("description", "")).strip()
        lines.append(f"- `{name}` ({kind}, {spec.get('type', 'any')})" + (f": {description}" if description else ""))
    return "\n".join(lines)


def render_browser_flow_example() -> str:
    """The "go to a site and take a screenshot" example for the simple prompt, built from catalogue tools (#21772)."""
    names = set(tool_catalogue.BROWSER_PROMPT_TOOLS)
    steps = [
        (n, p, d)
        for n, p, d in (
            ("navigate", '{"url":"https://example.com"}', "Navigate to example.com"),
            ("screenshot", "{}", "Capture page"),
        )
        if n in names
    ]
    blocks = [f"```\n<TOOL_CALL name=\"{n}\" params='{p}'>{d}</TOOL_CALL>\n```" for n, p, d in steps]
    return "\nAfter navigation result:\n".join(blocks)


def template_vars() -> "dict[str, str]":
    """Jinja variables every prompt template can use (merged by ``PromptManager.get``)."""
    # Markup: the Jinja env autoescapes plain strings, which would entity-encode the TOOL_CALL examples.
    return {
        "browser_tools_section": Markup(render_browser_tools_section()),  # nosec B704  # repo-generated text
        "browser_flow_example": Markup(render_browser_flow_example()),  # nosec B704
        "web_search_parameters": Markup(render_parameter_lines(WEB_SEARCH_SCHEMA)),  # nosec B704
    }
