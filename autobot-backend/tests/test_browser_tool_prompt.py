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


def test_no_browser_tool_name_is_hand_written_in_the_prompt_files():
    for name in _CHAT_PROMPTS:
        text = (_PROMPT_DIR / "chat" / f"{name}.md").read_text(encoding="utf-8")
        section = text.split("### Browser Tools (Web Browsing)", 1)[1].split("**When to use browser tools:**", 1)[0]
        assert "{{ browser_tools_section }}" in section
        for tool in tool_catalogue.BROWSER_PROMPT_TOOLS:
            assert not re.search(rf"\b{tool}\b", section.replace("{{ browser_tools_section }}", "")), tool


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
