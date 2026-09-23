# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A delegated subagent must not do what its parent is held from doing (#16950).

The parent here runs under a work item that declares ``writing files`` as
approval-gated, so its own ``write_file`` is held for a human. It then calls the
``delegate`` tool. The child used to be built from the child profile alone
(``build_governed_identity({"agent_id": agent_type}, ...)``), which dropped the
parent's approval categories and work item. So the child's ``write_file`` ran
unapproved: the parent's refusal was laundered through the delegation.

The assertion is on the outcome, not a field. The real ``enforce_work_item_approval``
is asked about the context the child actually runs with. Any fix that carries the
originator's authority across the hop makes it pass, however it is represented.

``test_the_child_is_held_as_its_parent_is`` landed as a strict xfail (#16958),
reporting XFAIL on ``main`` as the proof of the gap. The commit that closed the hole
removed the marker, so it now guards the fix. The preconditions stay in their own
ordinary test, so broken setup fails outright and can never pass for the fix.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import chat_workflow
from chat_workflow import delegation
from chat_workflow.models import AgentContext
from chat_workflow.tool_dispatch_guards import enforce_work_item_approval

#: A file write, which the ``writing files`` category gates.
_WRITE = {"name": "write_file", "params": {"path": "notes.md", "content": "x"}}


def _held_parent() -> SimpleNamespace:
    """A governed parent whose work item gates file writes on human approval."""
    return SimpleNamespace(
        agent_context=AgentContext(agent_id="research_agent", session_id="s-parent"),
        requires_approval_before=["writing files"],
        work_item_id="wi-16950",
        context={},
        auth_role="user",
    )


async def _delegate_write(parent) -> tuple[list, dict]:
    """Run the real ``delegate`` handler from *parent*; return its results and the child ctx it built."""
    from chat_workflow.tool_handler import ToolHandlerMixin

    captured: dict = {}

    async def _fake_loop(ctx):
        captured["child"] = ctx
        yield (["written"], [], None)

    fake_manager = SimpleNamespace(_execute_llm_continuation_loop=_fake_loop)
    call = {"params": {"task": "write notes.md", "agent_type": "documentation_agent", "engine": "internal"}}
    results: list = []
    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
    with (
        patch.object(delegation, "DELEGATION_ENABLED", True),
        patch.object(chat_workflow, "get_chat_workflow_manager", return_value=fake_manager),
    ):
        _ = [m async for m in mixin._handle_delegate_tool(call, results, parent)]
    return results, captured


@pytest.mark.asyncio
async def test_the_parent_is_held_and_the_delegation_runs():
    """The preconditions, asserted where a failure is a real failure and never an expected one."""
    parent = _held_parent()

    assert enforce_work_item_approval(dict(_WRITE), parent, []) is not None, "the parent must be held"

    results, captured = await _delegate_write(parent)

    assert results and results[0]["status"] == "completed", results
    assert captured["child"].agent_context.agent_id == "documentation_agent"


@pytest.mark.asyncio
async def test_the_child_is_held_as_its_parent_is():
    _, captured = await _delegate_write(_held_parent())
    if "child" not in captured:
        pytest.fail("the delegation did not run, so the check below would pass or fail for the wrong reason")

    held = enforce_work_item_approval(dict(_WRITE), captured["child"], [])

    assert held is not None, "a parent held for approval delegated the write, and the child ran it unapproved"
