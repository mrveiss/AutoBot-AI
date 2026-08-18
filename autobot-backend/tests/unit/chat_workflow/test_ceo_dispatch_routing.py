# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11552: does _dispatch_tool_call actually ROUTE create_task to the LLC
handler (through the enforcement guards), or is it blocked/misrouted before
_handle_llc_tool? The earlier chain test called _handle_llc_tool directly and
bypassed the guards + routing — this closes that gap.

#14491 review: this file's whole purpose — asserting through the real
_dispatch_tool_call chain rather than the handler in isolation — is exactly
what the RBAC gate must be proven against too, so PermissionEnforcementExtension
is registered on the real singleton for every test here (not just the new
denial one) rather than left absent. Before this fix, `role="user"` here
"succeeded" only because the extension was never registered — nothing about
this file exercised the gate #14491 added; a broken guard would have passed
every assertion below unchanged.

Imports the real ToolHandlerMixin; skips where the heavy chain can't load.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from middleware.builtin.permission_enforcement import PermissionEnforcementExtension
from middleware.manager import get_extension_manager, reset_extension_manager


@pytest.fixture(autouse=True)
def _real_permission_enforcement():
    """Register the real extension on the real singleton every hook call reads.

    #14491 review: without this, `_emit_before_tool_execute` invokes zero
    extensions and no-ops to "allow" regardless of role or declared
    permission — a denial test here would pass against code with the guard
    ripped out just as readily as against the real gate.
    """
    reset_extension_manager()
    get_extension_manager().register(PermissionEnforcementExtension())
    yield
    reset_extension_manager()


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


async def _dispatch_create_task(m, role: str) -> tuple[list, list]:
    tool_call = {"name": "create_task", "params": {"title": "Write Q3 report", "priority": "high"}}
    exec_results: list = []
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
            role=role,
        )
    ]
    return msgs, exec_results


@pytest.mark.asyncio
async def test_dispatch_routes_create_task_to_llc_handler():
    """Routing reaches the LLC branch and dispatches — the control case.

    #14491 review: role is "operator" (holds WORKFLOW_CREATE), not "user".
    This test's job is proving ROUTING — that create_task reaches
    _handle_llc_tool through the real guard chain rather than being blocked
    by an unrelated guard or falling through to MCP/unknown — not proving
    RBAC. Asserting a "user" role succeeds here would silently contradict
    the RBAC model #14491 added; see
    test_role_lacking_workflow_create_is_denied_through_dispatch below for
    the denial case, and test_permission_enforcement_builtin_surfaces.py's
    TestLLCToolDenial for the handler-level equivalent.
    """
    m = _mixin()
    with patch(
        "chat_workflow.tool_handler.dispatch_llc_tool",
        new=AsyncMock(return_value={"status": "success", "entity_type": "work_item", "entity_id": "wi-1"}),
    ) as disp:
        msgs, exec_results = await _dispatch_create_task(m, "operator")
    # The routing must reach the LLC branch and dispatch (not be blocked by a
    # guard, and not fall through to MCP/unknown).
    disp.assert_awaited_once()
    assert disp.await_args.args[0] == "create_task"
    assert disp.await_args.args[2] == "co-1"  # company_id from ctx.context
    assert exec_results and exec_results[-1].get("status") == "success"
    assert not any(getattr(x, "type", "") == "approval_required" for x in msgs)


@pytest.mark.asyncio
async def test_role_lacking_workflow_create_is_denied_through_dispatch():
    """#14491: `user` lacks WORKFLOW_CREATE — denial must happen at the real
    _dispatch_tool_call seam, not just inside _handle_llc_tool in isolation.

    This is the test the coordinator's review asked for: it goes through
    _dispatch_tool_call (the production entry point every tool call funnels
    through), with PermissionEnforcementExtension actually registered, and
    proves the mutating call (dispatch_llc_tool) never happens.
    """
    m = _mixin()
    with patch(
        "chat_workflow.tool_handler.dispatch_llc_tool",
        new=AsyncMock(return_value={"status": "success", "entity_type": "work_item", "entity_id": "wi-1"}),
    ) as disp:
        msgs, exec_results = await _dispatch_create_task(m, "user")

    disp.assert_not_awaited()
    assert exec_results and exec_results[-1].get("status") == "error"
    assert exec_results[-1].get("error") == "permission_denied"
    last = msgs[-1]
    assert last.type == "error"
    assert last.metadata.get("cancelled_by_hook") is True
    assert last.metadata.get("reason") == "permission_denied"
