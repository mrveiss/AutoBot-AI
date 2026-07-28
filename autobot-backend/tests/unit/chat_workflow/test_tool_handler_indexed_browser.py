# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Indexed interactive-element browser tools (#11537).

click_index/fill_index/select_index/hover_index let the chat LLM act on a
numbered element from the page's element menu instead of inventing a CSS
selector. These tests prove:

  (a) _handle_browser_tool resolves the tool call to the browser worker with
      the index intact and threads session_id (#11539 parity).
  (b) the numbered interactive-element "state block" is appended to browser
      tool results (task 4) so the model always sees a current menu.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow.tool_handler import BROWSER_TOOL_NAMES, ToolHandlerMixin

_PAGE_STATE = {
    "url": "https://example.com/form",
    "title": "Example Form",
    "scroll": {"x": 0, "y": 0, "maxX": 0, "maxY": 400},
    "elements": [
        {"index": 0, "role": "textbox", "name": "Email", "tag": "input", "selector": "xpath=/html/body/input[1]"},
        {"index": 1, "role": "button", "name": "Submit", "tag": "button", "selector": "xpath=/html/body/button[1]"},
    ],
}


def _handler() -> ToolHandlerMixin:
    return ToolHandlerMixin.__new__(ToolHandlerMixin)  # no __init__ side effects needed


async def _drive_browser_tool(tool_call: dict, mock_send: AsyncMock, session_id: str = "conversation-A"):
    handler = _handler()
    execution_results: list = []
    with (
        patch("api.browser_mcp.send_to_browser_vm", mock_send),
        patch("chat_workflow.tool_handler._emit_before_tool_execute", AsyncMock(return_value=True)),
        patch("chat_workflow.tool_handler._emit_after_tool_execute", AsyncMock(side_effect=lambda *a, **k: a[1])),
    ):
        async for _msg in handler._handle_browser_tool(tool_call, execution_results, session_id=session_id):
            pass
    return execution_results


def test_indexed_tool_names_are_registered_as_browser_tools() -> None:
    for name in ("click_index", "fill_index", "select_index", "hover_index", "browser_state"):
        assert name in BROWSER_TOOL_NAMES


@pytest.mark.asyncio
async def test_click_index_resolves_index_and_threads_session_id() -> None:
    """(a) click_index dispatch forwards the index untouched and the caller's
    session_id — resolution to a concrete element happens server-side in the
    browser worker (autobot-browser-worker/element-index.js)."""
    tool_call = {"name": "click_index", "params": {"index": 1}, "description": "click submit"}
    mock_send = AsyncMock(
        return_value={
            "success": True,
            "action": "click_index",
            "result": {
                "success": True,
                "index": 1,
                "resolved": _PAGE_STATE["elements"][1],
                "page_state": _PAGE_STATE,
            },
        }
    )

    execution_results = await _drive_browser_tool(tool_call, mock_send, session_id="conversation-A")

    mock_send.assert_awaited_once()
    args, kwargs = mock_send.call_args
    assert args[0] == "click_index"
    assert args[1] == {"index": 1}
    assert kwargs["session_id"] == "conversation-A"
    assert execution_results[0]["status"] == "success"
    assert "Clicked element [1]" in execution_results[0]["output"]
    assert "Submit" in execution_results[0]["output"]


@pytest.mark.asyncio
async def test_fill_index_resolves_index_and_threads_session_id() -> None:
    """(a) fill_index parity with click_index — index + value forwarded, session_id threaded."""
    tool_call = {"name": "fill_index", "params": {"index": 0, "value": "user@example.com"}, "description": "fill email"}
    mock_send = AsyncMock(
        return_value={
            "success": True,
            "action": "fill_index",
            "result": {
                "success": True,
                "index": 0,
                "resolved": _PAGE_STATE["elements"][0],
                "page_state": _PAGE_STATE,
            },
        }
    )

    execution_results = await _drive_browser_tool(tool_call, mock_send, session_id="conversation-B")

    args, kwargs = mock_send.call_args
    assert args[0] == "fill_index"
    assert args[1] == {"index": 0, "value": "user@example.com"}
    assert kwargs["session_id"] == "conversation-B"
    assert "Filled element [0]" in execution_results[0]["output"]
    assert "Email" in execution_results[0]["output"]


@pytest.mark.asyncio
async def test_click_index_out_of_range_surfaces_as_tool_error() -> None:
    """The browser worker rejects an out-of-range index; the failure must
    still be recorded (not silently dropped) for the model to self-correct."""
    tool_call = {"name": "click_index", "params": {"index": 99}, "description": "click ghost element"}
    mock_send = AsyncMock(side_effect=Exception("Browser VM error: 400 - Index 99 out of range (2 elements)"))

    execution_results = await _drive_browser_tool(tool_call, mock_send)

    assert execution_results[0]["status"] == "error"


@pytest.mark.asyncio
async def test_browser_state_tool_returns_numbered_menu() -> None:
    """browser_state lets the model explicitly request the current menu."""
    tool_call = {"name": "browser_state", "params": {}, "description": "get page state"}
    mock_send = AsyncMock(return_value={"success": True, "action": "browser_state", "result": _PAGE_STATE})

    execution_results = await _drive_browser_tool(tool_call, mock_send)

    assert execution_results[0]["status"] == "success"
    assert "2 interactive element" in execution_results[0]["output"]


class TestFormatBrowserResultAppendsStateBlock:
    """(b) the indexed-element block is appended to browser tool results (task 4)."""

    def test_state_block_appended_to_click_result(self) -> None:
        handler = _handler()
        result = {
            "success": True,
            "result": {"success": True, "page_state": _PAGE_STATE},
        }
        text = handler._format_browser_result("click", {"index": 1}, result)

        assert "Interactive elements (2):" in text
        assert '[0] textbox "Email"' in text
        assert '[1] button "Submit"' in text

    def test_no_state_block_when_page_state_absent(self) -> None:
        handler = _handler()
        result = {"success": True, "result": {"title": "x", "url": "https://example.com"}}
        text = handler._format_browser_result("navigate", {"url": "https://example.com"}, result)

        assert "Interactive elements" not in text

    def test_no_state_block_when_elements_empty(self) -> None:
        handler = _handler()
        empty_state = {**_PAGE_STATE, "elements": []}
        result = {"success": True, "result": {"success": True, "page_state": empty_state}}
        text = handler._format_browser_result("click", {"selector": "#go"}, result)

        assert "Interactive elements" not in text

    def test_browser_state_result_renders_full_menu(self) -> None:
        handler = _handler()
        result = {"success": True, "result": _PAGE_STATE}
        text = handler._format_browser_result("browser_state", {}, result)

        assert "Page state: https://example.com/form" in text
        assert '[0] textbox "Email"' in text
        assert '[1] button "Submit"' in text

    def test_state_block_respects_prompt_element_cap(self) -> None:
        handler = _handler()
        many_elements = [
            {"index": i, "role": "button", "name": f"btn{i}", "tag": "button", "selector": f"xpath=/x[{i}]"}
            for i in range(50)
        ]
        page_state = {**_PAGE_STATE, "elements": many_elements}
        result = {"success": True, "result": {"success": True, "page_state": page_state}}
        text = handler._format_browser_result("click_index", {"index": 0}, result)

        assert "Interactive elements (50):" in text
        assert "btn29" in text  # within default cap (30)
        assert "btn49" not in text  # beyond default cap — never blows the prompt
