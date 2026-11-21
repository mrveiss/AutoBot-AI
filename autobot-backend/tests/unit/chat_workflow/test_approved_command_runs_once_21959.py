# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A command the person approved in the graph runs once, and a step that did not run is never "executed" (#21959)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_workflow.approval_binding import bind_decision
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.tool_dispatch_guards import COMMAND_APPROVED_KEY, COMMAND_FORCE_APPROVAL_KEY
from chat_workflow.tool_handler import ToolHandlerMixin
from services.agent_terminal.ai_line_gate import decide_command
from services.ai_line_enforcement import Outcome
from tests.unit.chat_workflow.test_ai_line_support import VERIFIED_COMPANY, arun_guard

TOUCH = {"name": "execute_command", "params": {"command": "touch /tmp/x"}}
OTHER = {"name": "execute_command", "params": {"command": "touch /tmp/y"}}
_GATE = "services.agent_terminal.ai_line_gate.resolve_command_line"


def _graph():
    import chat_workflow.graph as graph_module

    return graph_module


def _resumed_ctx(approved_call, approved=True):
    """The iteration context the graph builds after the client resumed with its decision."""
    decision = bind_decision({"approved": approved}, [approved_call])
    state = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "user_message": "touch it",
        "context": {"verified_company_id": VERIFIED_COMPANY},
        "llm_params": {"ollama_endpoint": "http://x", "selected_model": "m", "system_prompt": "s"},
        "approval_decision": decision,
    }
    return _graph()._build_llm_iteration_context(state)


def _verdict(outcome: Outcome) -> SimpleNamespace:
    return SimpleNamespace(outcome=outcome, message="held")


async def _terminal_execute(*, command, force_approval=False, person_approved=False, **_):
    """The real terminal decision, with the role policy holding a MEDIUM command (the live case)."""
    session = MagicMock(has_pending_approval=MagicMock(return_value=False))
    handler = MagicMock(check_auto_approve_rules=AsyncMock(return_value=False))
    with patch(_GATE, AsyncMock(return_value=_verdict(Outcome.HOLD))):
        runs, refusal = await decide_command(
            handler,
            session,
            command,
            MagicMock(value="moderate"),
            force_approval=force_approval,
            person_approved=person_approved,
        )
    return {"status": "success", "stdout": ""} if runs else {"status": "pending_approval", "refusal": refusal}


async def _run_through_tool_path(call, ctx):
    """Guard, then the handler's own call into the terminal: what execute_tools does for one command."""
    await arun_guard(call, ctx, [])
    handler = ToolHandlerMixin.__new__(ToolHandlerMixin)
    terminal = MagicMock(active_sessions={"s1": object()}, execute_command=AsyncMock(side_effect=_terminal_execute))
    handler.terminal_tool = terminal
    kwargs = {
        "force_approval": bool(call.get(COMMAND_FORCE_APPROVAL_KEY)),
        "person_approved": bool(call.get(COMMAND_APPROVED_KEY)),
    }
    return await handler._execute_terminal_command("s1", call["params"]["command"], **kwargs), terminal


@pytest.mark.asyncio
async def test_approve_then_resume_runs_the_command_once_with_no_second_gate():
    held = {**TOUCH, "needs_approval": True}
    result, terminal = await _run_through_tool_path(dict(TOUCH), _resumed_ctx(held))
    assert result["status"] == "success"
    assert terminal.execute_command.await_count == 1


@pytest.mark.asyncio
async def test_the_same_command_without_a_yes_is_still_held_by_the_terminal():
    held = {**TOUCH, "needs_approval": True}
    result, _ = await _run_through_tool_path(dict(TOUCH), _resumed_ctx(held, approved=False))
    assert result["status"] == "pending_approval"


@pytest.mark.asyncio
async def test_a_yes_for_one_command_never_authorises_another():
    held = {**TOUCH, "needs_approval": True}
    result, _ = await _run_through_tool_path(dict(OTHER), _resumed_ctx(held))
    assert result["status"] == "pending_approval"


@pytest.mark.asyncio
async def test_a_model_supplied_approval_flag_is_dropped():
    forged = {**OTHER, COMMAND_APPROVED_KEY: True}
    held = {**TOUCH, "needs_approval": True}
    await arun_guard(forged, _resumed_ctx(held), [])
    assert COMMAND_APPROVED_KEY not in forged


@pytest.mark.asyncio
async def test_a_yes_does_not_lift_a_refusal():
    with patch(_GATE, AsyncMock(return_value=_verdict(Outcome.REFUSE))):
        decision = await decide_command(
            MagicMock(), MagicMock(), "rm -rf /", MagicMock(value="high"), force_approval=False, person_approved=True
        )
    assert decision == (False, "held")


def _prompt(history):
    return ChatWorkflowManager._build_continuation_prompt(
        ChatWorkflowManager.__new__(ChatWorkflowManager), "touch x", history
    )


def test_a_pending_step_is_reported_as_not_run_and_not_counted():
    pending = {"command": "touch /tmp/x", "status": "pending_approval", "stdout": "", "stderr": "waiting"}
    prompt = _prompt([pending])
    assert "0 step(s) completed" in prompt and "0 step(s) have been completed" in prompt
    assert "NOT RUN" in prompt


@pytest.mark.parametrize("status", ["denied", "refused", "timeout", "outcome_unknown", "approval_required"])
def test_a_refused_or_timed_out_step_is_not_run(status):
    assert "0 step(s) completed" in _prompt([{"command": "touch x", "status": status}])


def test_only_the_steps_that_ran_are_counted():
    ran = {"command": "ls", "status": "success", "stdout": "a"}
    pending = {"command": "touch x", "status": "pending_approval"}
    prompt = _prompt([ran, pending])
    assert "1 step(s) completed" in prompt and prompt.count("NOT RUN") == 1
