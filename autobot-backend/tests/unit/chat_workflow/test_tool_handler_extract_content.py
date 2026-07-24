# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the extract_content builtin in chat_workflow/tool_handler.py.

Issue #11540: goal-directed extraction from the browser session's *current*
live page (post-login/post-click), as opposed to WEB_RESEARCH_TOOL_NAMES'
extract_structured_data which always re-fetches a URL from scratch. Exercises
the real prod dispatch seam (_dispatch_tool_call -> _builtin_route ->
_handle_extract_content_tool), offline: the browser VM and LLM calls are
mocked, never a real browser/network hop.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_LIVE_HTML = "<html><head><title>Checkout</title></head><body><p>Order #A1B2C3</p></body></html>"


def test_extract_content_schema_registered() -> None:
    """EXTRACT_CONTENT_SCHEMA is present in _BUILTIN_TOOL_SCHEMAS and requires 'goal'."""
    from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS, EXTRACT_CONTENT_SCHEMA

    assert "extract_content" in _BUILTIN_TOOL_SCHEMAS
    assert _BUILTIN_TOOL_SCHEMAS["extract_content"] is EXTRACT_CONTENT_SCHEMA
    assert "goal" in EXTRACT_CONTENT_SCHEMA.get("required", [])


def test_extract_content_in_uniform_builtin_tools() -> None:
    """extract_content shares the uniform builtin dispatch gate (GH#11489)."""
    from chat_workflow.tool_handler import _UNIFORM_BUILTIN_TOOLS, LIVE_PAGE_EXTRACT_TOOL_NAMES

    assert "extract_content" in LIVE_PAGE_EXTRACT_TOOL_NAMES
    assert "extract_content" in _UNIFORM_BUILTIN_TOOLS


@pytest.mark.asyncio
async def test_exec_extract_content_returns_goal_relevant_answer() -> None:
    """_exec_extract_content reads the live DOM (not a re-fetch) and answers the goal."""
    from chat_workflow.tool_handler import ToolHandlerMixin

    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)

    vm_response = {
        "success": True,
        "action": "evaluate",
        "result": {
            "result": {"url": "https://shop.example.com/checkout", "title": "Checkout", "html": _LIVE_HTML},
            "page_state": {},
        },
    }

    with (
        patch(
            "api.browser_mcp.send_to_browser_vm",
            new_callable=AsyncMock,
            return_value=vm_response,
        ) as mock_vm,
        patch(
            "llm_shared.structured_ops.extract",
            new_callable=AsyncMock,
            return_value={"answer": "Order #A1B2C3"},
        ) as mock_extract,
    ):
        output = await mixin._exec_extract_content({"goal": "the order confirmation number"}, session_id="sess-1")

    # Browser VM was asked to read the live page, not to navigate/re-fetch a URL.
    mock_vm.assert_awaited_once()
    assert mock_vm.await_args.args[0] == "evaluate"
    assert mock_vm.await_args.kwargs["session_id"] == "sess-1"

    # LLM sub-call ran against the live-page markdown with a goal-described schema.
    mock_extract.assert_awaited_once()
    schema_arg = mock_extract.await_args.args[1]
    assert schema_arg["properties"]["answer"]["description"] == "the order confirmation number"

    assert "Order #A1B2C3" in output
    assert "https://shop.example.com/checkout" in output


@pytest.mark.asyncio
async def test_exec_extract_content_no_live_page_content() -> None:
    """Empty live page (no navigation yet) returns a friendly notice, not a crash."""
    from chat_workflow.tool_handler import ToolHandlerMixin

    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
    vm_response = {"success": True, "action": "evaluate", "result": {"result": {"url": "", "html": ""}}}

    with patch("api.browser_mcp.send_to_browser_vm", new_callable=AsyncMock, return_value=vm_response):
        output = await mixin._exec_extract_content({"goal": "anything"}, session_id="sess-1")

    assert "navigate to a page first" in output


@pytest.mark.asyncio
async def test_exec_extract_content_requires_goal() -> None:
    """A missing/blank goal is rejected before any browser VM call."""
    from chat_workflow.tool_handler import ToolHandlerMixin

    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)

    with patch("api.browser_mcp.send_to_browser_vm", new_callable=AsyncMock) as mock_vm:
        output = await mixin._exec_extract_content({"goal": "   "}, session_id="sess-1")

    mock_vm.assert_not_awaited()
    assert "requires a 'goal'" in output


# ---------------------------------------------------------------------------
# Chat dispatch verification — the real prod seam (_dispatch_tool_call)
# ---------------------------------------------------------------------------

_DISPATCH_ARGS = {
    "session_id": "sess-ec",
    "terminal_session_id": "term-ec",
    "ollama_endpoint": "http://127.0.0.1:11434",
    "selected_model": "test-model",
}


def _dispatch_mixin():
    """ToolHandlerMixin with governance gates quieted (covered by own suites)."""
    from chat_workflow.tool_handler import ToolHandlerMixin

    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
    mixin._enforce_forbidden_work = lambda *a, **k: None
    mixin._enforce_config_protection = lambda *a, **k: None
    mixin._enforce_fact_forcing = lambda *a, **k: None
    mixin._enforce_work_item_approval = lambda *a, **k: None
    return mixin


async def _drain_dispatch(mixin, tool_call: dict, execution_results: list) -> list:
    return [
        msg
        async for msg in mixin._dispatch_tool_call(
            tool_call,
            execution_results=execution_results,
            additional_response_parts=[],
            **_DISPATCH_ARGS,
        )
    ]


@pytest.mark.asyncio
async def test_dispatch_extract_content_returns_goal_relevant_content() -> None:
    """extract_content, routed through the real _dispatch_tool_call seam, is
    registered/dispatchable and yields goal-relevant content in the expected
    tool-result shape (#11540)."""
    mixin = _dispatch_mixin()

    vm_response = {
        "success": True,
        "action": "evaluate",
        "result": {
            "result": {"url": "https://shop.example.com/checkout", "title": "Checkout", "html": _LIVE_HTML},
        },
    }

    execution_results: list = []
    with (
        patch("api.browser_mcp.send_to_browser_vm", new_callable=AsyncMock, return_value=vm_response),
        patch(
            "llm_shared.structured_ops.extract",
            new_callable=AsyncMock,
            return_value={"answer": "Order #A1B2C3"},
        ),
    ):
        messages = await _drain_dispatch(
            mixin,
            {"name": "extract_content", "params": {"goal": "the order confirmation number"}},
            execution_results,
        )

    outputs = [m for m in messages if getattr(m, "type", "") == "command_output"]
    assert outputs, f"no command_output yielded; got: {[getattr(m, 'type', m) for m in messages]}"
    assert "Order #A1B2C3" in outputs[0].content
    assert execution_results[-1] == {
        "tool": "extract_content",
        "status": "success",
        "output": outputs[0].content,
    }


@pytest.mark.asyncio
async def test_dispatch_extract_content_schema_validation_rejects_missing_goal() -> None:
    """Issue #4529 schema validation runs before the handler — a missing 'goal'
    is a schema_error, not a browser VM call."""
    mixin = _dispatch_mixin()
    execution_results: list = []

    with patch("api.browser_mcp.send_to_browser_vm", new_callable=AsyncMock) as mock_vm:
        messages = await _drain_dispatch(
            mixin,
            {"name": "extract_content", "params": {}},
            execution_results,
        )

    mock_vm.assert_not_awaited()
    assert execution_results[-1]["status"] == "schema_error"
    assert any(getattr(m, "type", "") == "tool_result" for m in messages)


@pytest.mark.asyncio
async def test_dispatch_extract_content_firewall_blocked() -> None:
    """A content-firewall block surfaces as a success-shaped notice (mirrors extract_url)."""
    mixin = _dispatch_mixin()

    vm_response = {
        "success": True,
        "action": "evaluate",
        "result": {"result": {"url": "https://x", "html": "<p>x</p>"}},
    }
    blocked_verdict = MagicMock(blocked=True, risk=MagicMock(value="critical"), content="")

    execution_results: list = []
    with (
        patch("api.browser_mcp.send_to_browser_vm", new_callable=AsyncMock, return_value=vm_response),
        patch("security.content_firewall.get_content_firewall") as mock_fw,
    ):
        mock_fw.return_value.inspect = AsyncMock(return_value=blocked_verdict)
        messages = await _drain_dispatch(
            mixin,
            {"name": "extract_content", "params": {"goal": "anything"}},
            execution_results,
        )

    outputs = [m for m in messages if getattr(m, "type", "") == "command_output"]
    assert outputs
    assert "blocked by content firewall" in outputs[0].content
