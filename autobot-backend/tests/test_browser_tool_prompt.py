# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The browser tool list is generated from the catalogue, never hand-written (#21772)."""

import re
from pathlib import Path

import browser_tool_prompt
from autobot_shared import tool_catalogue
from prompt_manager import PromptManager
from web_search_schema import WEB_SEARCH_SCHEMA

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "resources" / "prompts"
_CHAT_PROMPTS = ("system_prompt", "system_prompt_simple")


def _render(name: str) -> str:
    return PromptManager(prompts_dir=str(_PROMPT_DIR)).get(f"chat.{name}")


def test_every_catalogue_browser_tool_is_in_both_rendered_prompts():
    for name in _CHAT_PROMPTS:
        rendered = _render(name)
        for tool in tool_catalogue.BROWSER_PROMPT_TOOLS:
            assert f"`{tool}`" in rendered, f"{tool} missing from rendered {name}"


def test_page_reading_tools_are_in_the_catalogue_set():
    for tool in ("extract_content", "scrape_url", "extract_structured_data", "browser_state"):
        assert tool in tool_catalogue.BROWSER_PROMPT_TOOLS


def test_read_versus_interact_rule_is_rendered():
    for name in _CHAT_PROMPTS:
        assert browser_tool_prompt.READ_RULE in _render(name)


def test_reminder_lists_every_browser_tool():
    lines = browser_tool_prompt.render_tool_name_reminder_lines()
    for tool in tool_catalogue.BROWSER_PROMPT_TOOLS:
        assert f"- {tool}:" in lines


def test_a_new_catalogue_tool_appears_everywhere_without_a_prompt_edit(monkeypatch):
    monkeypatch.setattr(
        tool_catalogue, "BROWSER_PROMPT_TOOLS", tool_catalogue.BROWSER_PROMPT_TOOLS + ("brand_new_browser_tool",)
    )
    assert "`brand_new_browser_tool`" in browser_tool_prompt.render_browser_tools_section()
    assert "- brand_new_browser_tool:" in browser_tool_prompt.render_tool_name_reminder_lines()
    assert "`brand_new_browser_tool`" in _render("system_prompt_simple")


def _hand_written_browser_tools(text: str) -> "list[str]":
    """Browser tools named as an invocation (``name="x"``) or as a backticked tool name in raw prompt *text*.

    Plain-English user intents ("click, fill forms", "a screenshot of a page") are prose, not tool lists, and are
    deliberately not matched.
    """
    return [tool for tool in tool_catalogue.BROWSER_PROMPT_TOOLS if re.search(rf'name="{tool}"|`{tool}`', text)]


def test_no_browser_tool_name_is_hand_written_anywhere_in_the_prompt_files():
    """The whole of both prompt files, not only the browser section (#21772)."""
    for name in _CHAT_PROMPTS:
        text = (_PROMPT_DIR / "chat" / f"{name}.md").read_text(encoding="utf-8")
        assert "{{ browser_tools_section }}" in text
        assert _hand_written_browser_tools(text) == [], name


def test_the_guard_sees_a_hand_written_invocation():
    assert _hand_written_browser_tools("<TOOL_CALL name=\"navigate\" params='{}'>x</TOOL_CALL>") == ["navigate"]
    assert _hand_written_browser_tools("Use `scrape_url` to read") == ["scrape_url"]


def test_the_simple_prompts_screenshot_flow_is_rendered_from_the_catalogue():
    rendered = _render("system_prompt_simple")
    assert 'name="navigate"' in rendered and 'name="screenshot"' in rendered


def test_the_flow_example_drops_a_tool_the_catalogue_no_longer_has(monkeypatch):
    monkeypatch.setattr(
        tool_catalogue,
        "BROWSER_PROMPT_TOOLS",
        tuple(t for t in tool_catalogue.BROWSER_PROMPT_TOOLS if t != "screenshot"),
    )
    assert 'name="screenshot"' not in browser_tool_prompt.render_browser_flow_example()


def test_both_prompts_list_every_web_search_parameter_the_schema_declares():
    for name in _CHAT_PROMPTS:
        rendered = _render(name)
        for param in WEB_SEARCH_SCHEMA["properties"]:
            assert f"`{param}`" in rendered, f"{param} missing from rendered {name}"
        assert "`fetch_full`" in rendered


def test_a_parameter_added_to_the_schema_reaches_both_prompts_without_a_prompt_edit(monkeypatch):
    schema = {
        **WEB_SEARCH_SCHEMA,
        "properties": {**WEB_SEARCH_SCHEMA["properties"], "brand_new_param": {"type": "string"}},
    }
    monkeypatch.setattr(browser_tool_prompt, "WEB_SEARCH_SCHEMA", schema)
    for name in _CHAT_PROMPTS:
        assert "`brand_new_param`" in _render(name)


def test_the_handler_and_the_prompt_read_one_web_search_schema():
    from chat_workflow import tool_handler

    assert tool_handler.WEB_SEARCH_SCHEMA is WEB_SEARCH_SCHEMA


def test_no_web_search_parameter_is_hand_written_in_the_prompt_files():
    for name in _CHAT_PROMPTS:
        text = (_PROMPT_DIR / "chat" / f"{name}.md").read_text(encoding="utf-8")
        assert "{{ web_search_parameters }}" in text
        assert not re.search(r"^- `(query|fetch_full|max_pages)`", text, re.M), name


def test_manager_reminder_has_no_hand_written_browser_tool():
    src = (Path(__file__).resolve().parent.parent / "chat_workflow" / "manager.py").read_text(encoding="utf-8")
    reminder = src.split("TOOL NAME CORRECTION REQUIRED", 1)[1].split("Do NOT invent new tool names", 1)[0]
    for tool in tool_catalogue.BROWSER_PROMPT_TOOLS:
        assert f'"- {tool}:' not in reminder, tool


def test_fallback_path_is_rendered_not_returned_raw():
    pm = PromptManager(prompts_dir=str(_PROMPT_DIR))
    # Case-insensitive match is the first fallback strategy.
    rendered = pm.get("CHAT.SYSTEM_PROMPT_SIMPLE")
    assert "{{ browser_tools_section }}" not in rendered
    assert "`extract_content`" in rendered


def test_section_keeps_one_fill_example():
    assert 'name="fill"' in browser_tool_prompt.render_browser_tools_section()


def test_tool_call_examples_are_not_entity_encoded():
    rendered = _render("system_prompt_simple")
    assert '<TOOL_CALL name="navigate"' in rendered
    assert "&lt;TOOL_CALL" not in rendered
