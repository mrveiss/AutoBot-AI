# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11552: does _dispatch_tool_call actually ROUTE create_task to the LLC
handler (through the enforcement guards), or is it blocked/misrouted before
_handle_llc_tool? The earlier chain test called _handle_llc_tool directly and
bypassed the guards + routing — this closes that gap.

Imports the real ToolHandlerMixin; skips where the heavy chain can't load.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _mixin():
    try:
        from chat_workflow.tool_handler import ToolHandlerMixin
    except ImportError as exc:
        pytest.skip(f"chat_workflow not importable here: {exc}")

    class _M(ToolHandlerMixin):
        pass

    return _M()


def _ctx():
    # Mirrors a CEO-chat iteration context: company scope, no approval gates.
    return SimpleNamespace(
        context={"company_id": "co-1", "user_id": "u-1"},
        consecutive_invalid_tool_calls=0,
        requires_approval_before=None,
        work_item_id=None,
        agent_context=None,
    )


@pytest.mark.asyncio
async def test_dispatch_routes_create_task_to_llc_handler():
    m = _mixin()
    tool_call = {"name": "create_task", "params": {"title": "Write Q3 report", "priority": "high"}}
    exec_results: list = []
    with patch(
        "chat_workflow.tool_handler.dispatch_llc_tool",
        new=AsyncMock(return_value={"status": "success", "entity_type": "work_item", "entity_id": "wi-1"}),
    ) as disp:
        msgs = [
            msg
            async for msg in m._dispatch_tool_call(
                tool_call,
                "sess-1",
                "term-1",
                "http://x/api/generate",
                "model",
                exec_results,
                [],
                ctx=_ctx(),
                role="user",
            )
        ]
    # The routing must reach the LLC branch and dispatch (not be blocked by a
    # guard, and not fall through to MCP/unknown).
    disp.assert_awaited_once()
    assert disp.await_args.args[0] == "create_task"
    assert disp.await_args.args[2] == "co-1"  # company_id from ctx.context
    assert exec_results and exec_results[-1].get("status") == "success"
    assert not any(getattr(x, "type", "") == "approval_required" for x in msgs)
