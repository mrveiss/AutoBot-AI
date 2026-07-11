# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11552: pinpoint why CEO-chat board tool calls don't execute live.

Drives the deployed parse+dispatch chain deterministically with a realistic
board-LLM output (including the missing closing '>' this model emits), asserting:
  1. _parse_tool_calls extracts a `create_task` call (the #11545 path), and
  2. _handle_llc_tool dispatches it company-scoped from ctx.context (#11552).

If (1) fails → the parser/output is the break; if (2) fails → the dispatch/
context is. Imports the real ToolHandlerMixin; skips where the heavy
chat_workflow chain can't load (runs in CI).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _mixin_instance():
    try:
        from chat_workflow.tool_handler import ToolHandlerMixin
    except ImportError as exc:
        pytest.skip(f"chat_workflow not importable here: {exc}")

    class _M(ToolHandlerMixin):
        pass

    return _M()


# Exact shape this chat model emits live: prose, then a tool call whose closing
# tag omits the '>' (`</TOOL_CALL` + newline + more prose).
_BOARD_OUTPUT = (
    "Creating the high priority task.\n\n"
    "<TOOL_CALL name=\"create_task\" "
    "params='{\"title\":\"Write the Q3 financial report\",\"priority\":\"high\"}'>"
    "Create task</TOOL_CALL\n\nHigh priority task created."
)


def test_parse_extracts_create_task_from_board_output():
    m = _mixin_instance()
    calls = m._parse_tool_calls(_BOARD_OUTPUT, is_first_iteration=False)
    names = [c.get("name") for c in calls]
    assert "create_task" in names, f"parser did not extract create_task from board output: {names}"
    call = next(c for c in calls if c["name"] == "create_task")
    assert call["params"].get("title") == "Write the Q3 financial report"


@pytest.mark.asyncio
async def test_handle_llc_tool_dispatches_company_scoped():
    m = _mixin_instance()
    ctx = SimpleNamespace(context={"company_id": "co-1", "user_id": "u-1"}, consecutive_invalid_tool_calls=0)
    tool_call = {"name": "create_task", "params": {"title": "X", "priority": "high"}}
    exec_results: list = []
    with patch(
        "chat_workflow.tool_handler.dispatch_llc_tool",
        new=AsyncMock(return_value={"status": "success", "entity_type": "work_item", "entity_id": "wi-1"}),
    ) as disp:
        msgs = [msg async for msg in m._handle_llc_tool("create_task", tool_call, exec_results, ctx)]
    disp.assert_awaited_once()
    args = disp.await_args.args
    # dispatch_llc_tool(tool_name, params, company_id, user_id)
    assert args[0] == "create_task"
    assert args[2] == "co-1"  # company_id from ctx.context, not params
    assert any(getattr(x, "type", "") == "command_output" for x in msgs)
    assert exec_results and exec_results[-1]["status"] == "success"
