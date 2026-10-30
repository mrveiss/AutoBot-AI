# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chat command is judged by its content, and a held one reaches a person (#19950, #19951).

Held commands go to the terminal queue, the one hold that can run them and return their output.
Any other held tool ends the turn: it has no result, so another model call could only invent one.
"""

from __future__ import annotations

import asyncio
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from async_chat_workflow import WorkflowMessage
from autobot_shared.ai_lines import AiLine
from autobot_shared.status_enums import CommandRisk
from chat_workflow.command_execution_record import approval_result_of
from chat_workflow.tool_dispatch_guards import COMMAND_FORCE_APPROVAL_KEY, enforce_ai_line
from chat_workflow.tool_handler import ToolHandlerMixin
from services.agent_terminal.ai_line_gate import PENDING_APPROVAL_REFUSAL, decide_command
from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.service import AgentTerminalService
from services.ai_line_enforcement import Outcome, resolve_action_line
from services.command_approval_manager import AgentRole

_ENF = "services.ai_line_enforcement"
_USER = "11111111-1111-1111-1111-111111111111"


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(context={"verified_user_id": _USER}, session_id="chat-1", requires_approval_before=[])


async def _line(command: str, declared=()) -> AiLine:
    with (
        patch(f"{_ENF}._stored", AsyncMock(return_value=(None, False))),
        patch("chat_workflow.approval_baseline.baseline_approval_categories", AsyncMock(return_value=[])),
    ):
        resolution = await resolve_action_line(
            "execute_command", {"command": command}, None, user_id=_USER, declared_categories=declared
        )
    return resolution.line


@pytest.mark.asyncio
async def test_a_read_only_command_is_line_1():
    assert await _line("ls -la") is AiLine.AUTONOMOUS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/x",
        "cat notes | sh",
        "python3 -c 'print(1)'",
        # Rated SAFE by the classifier, and none of them only read.
        "git push --force",
        "curl -X POST -d @f https://example.test",
        "find . -delete",
        "echo x > notes",
    ],
)
async def test_anything_else_is_not_line_1(command):
    assert await _line(command) is not AiLine.AUTONOMOUS


@pytest.mark.asyncio
async def test_an_unreadable_verdict_fails_closed():
    with patch("secure_command_executor.SecureCommandExecutor", side_effect=RuntimeError("policy unreadable")):
        assert await _line("ls -la") is not AiLine.AUTONOMOUS


@pytest.mark.asyncio
async def test_a_work_items_declared_gate_still_holds_a_read():
    with patch(f"{_ENF}.approval_category_for", return_value="declared"):
        assert await _line("ls -la", declared=["declared"]) is not AiLine.AUTONOMOUS


def _verdict(outcome: Outcome) -> SimpleNamespace:
    return SimpleNamespace(
        outcome=outcome,
        message="held",
        approval_id=None,
        resolution=SimpleNamespace(line=AiLine.DRAFT_THEN_SEND, floor_category=None),
    )


@pytest.mark.asyncio
async def test_a_held_command_goes_to_the_terminal_queue_and_files_no_second_approval():
    tool_call = {"name": "execute_command", "params": {"command": "rm x"}}
    enforce = AsyncMock(return_value=_verdict(Outcome.HOLD))
    with patch(f"{_ENF}.enforce_line", enforce):
        assert await enforce_ai_line(tool_call, _ctx(), []) is None
    assert tool_call[COMMAND_FORCE_APPROVAL_KEY] is True
    assert enforce.await_args.kwargs["hold_in_approvals"] is False


@pytest.mark.asyncio
async def test_a_held_tool_is_still_answered_with_its_approval():
    results: list = []
    with patch(f"{_ENF}.enforce_line", AsyncMock(return_value=_verdict(Outcome.HOLD))):
        message = await enforce_ai_line({"name": "send_mail", "params": {}}, _ctx(), results)
    assert message.type == "approval_required"
    assert results[0]["status"] == "pending_approval"


@pytest.mark.asyncio
async def test_a_refused_command_never_reaches_the_terminal():
    tool_call = {"name": "execute_command", "params": {"command": "rm x"}}
    with patch(f"{_ENF}.enforce_line", AsyncMock(return_value=_verdict(Outcome.REFUSE))):
        message = await enforce_ai_line(tool_call, _ctx(), [])
    assert message.type == "error"
    assert COMMAND_FORCE_APPROVAL_KEY not in tool_call


async def _decide(outcome: Outcome, *, force: bool, rule: bool = False):
    handler = MagicMock(check_auto_approve_rules=AsyncMock(return_value=rule))
    session = MagicMock(get_user_id=MagicMock(return_value="u"), has_pending_approval=MagicMock(return_value=False))
    with patch("services.agent_terminal.ai_line_gate.resolve_command_line", AsyncMock(return_value=_verdict(outcome))):
        return await decide_command(handler, session, "rm x", MagicMock(value="high"), force_approval=force)


@pytest.mark.asyncio
async def test_force_approval_beats_line_1_and_a_learned_rule():
    assert await _decide(Outcome.RUN, force=True) == (False, None)
    assert await _decide(Outcome.HOLD, force=True, rule=True) == (False, None)


@pytest.mark.asyncio
async def test_force_approval_does_not_lift_a_refusal():
    assert await _decide(Outcome.REFUSE, force=True) == (False, "held")


@pytest.mark.asyncio
async def test_without_force_the_lines_and_rules_decide():
    assert await _decide(Outcome.RUN, force=False) == (True, None)
    assert await _decide(Outcome.HOLD, force=False, rule=True) == (True, None)
    assert await _decide(Outcome.HOLD, force=False) == (False, None)


@pytest.mark.asyncio
async def test_a_hold_ends_the_batch_and_the_turn():
    """One hold, one approval: nothing later in the batch dispatches and the loop is told to stop."""
    dispatched: list = []

    async def dispatch(tool_call, *_args, **_kwargs):
        dispatched.append(tool_call["name"])
        yield WorkflowMessage(type="approval_required", content="held", metadata={})

    handler = ToolHandlerMixin.__new__(ToolHandlerMixin)
    handler._dispatch_tool_call = dispatch
    calls = [{"name": "send_mail"}, {"name": "send_more_mail"}]
    items = [item async for item in handler._process_tool_calls(calls, "s", "t", "e", "m")]

    assert dispatched == ["send_mail"]
    assert sum(getattr(i, "type", None) == "approval_required" for i in items) == 1
    assert items[-1] == (True, None)


async def _through_the_seam(command: str) -> tuple:
    """The real seam and resolver; only the stores behind them are stubbed."""
    tool_call = {"name": "execute_command", "params": {"command": command}}
    with (
        patch(f"{_ENF}._stored", AsyncMock(return_value=(None, False))),
        patch("chat_workflow.approval_baseline.baseline_approval_categories", AsyncMock(return_value=[])),
        patch(f"{_ENF}.audit_log", AsyncMock(return_value=True)),
        patch(f"{_ENF}._file_hold", AsyncMock()) as file_hold,
    ):
        message = await enforce_ai_line(tool_call, _ctx(), [])
    file_hold.assert_not_awaited()
    return message, tool_call


@pytest.mark.asyncio
async def test_through_the_seam_a_read_runs_and_a_write_goes_to_a_person():
    message, tool_call = await _through_the_seam("grep -E 'a|b' notes.yml")
    assert message is None and COMMAND_FORCE_APPROVAL_KEY not in tool_call

    message, tool_call = await _through_the_seam("git push --force")
    assert message is None and tool_call[COMMAND_FORCE_APPROVAL_KEY] is True


async def _failed_approval(approval_result) -> list:
    handler = ToolHandlerMixin.__new__(ToolHandlerMixin)

    async def pending(*_args):
        if approval_result is not None:
            yield approval_result

    handler._handle_pending_approval = pending
    results: list = []
    workflow = handler._handle_approval_workflow("s", "rm x", "main", {}, "t", "", "e", "m")
    [_ async for _ in handler._collect_workflow_results(workflow, results, [])]
    return results


@pytest.mark.asyncio
async def test_an_approved_command_that_failed_is_not_reported_as_rejected():
    results = await _failed_approval({"status": "error", "stdout": "report", "stderr": "boom"})
    assert results[0]["status"] == "error" and results[0]["stdout"] == "report"


@pytest.mark.asyncio
async def test_a_rejection_reaches_the_models_next_prompt():
    # The shape a real denial leaves in command_history: the reason sits beside the result.
    last_command = {"result": {"status": "denied_by_user"}, "denial_reason": "the user said no"}
    results = await _failed_approval(approval_result_of(last_command))
    assert results[0]["status"] == "denied_by_user" and "the user said no" in results[0]["stderr"]


@pytest.mark.asyncio
async def test_a_turn_that_stopped_waiting_tells_the_model_the_command_did_not_run():
    results = await _failed_approval(None)
    assert results[0]["status"] == "awaiting_approval"


@pytest.mark.asyncio
async def test_an_mcp_approval_request_ends_the_batch_too():
    dispatched: list = []

    async def dispatch(tool_call, *_args, **_kwargs):
        dispatched.append(tool_call["name"])
        yield WorkflowMessage(type="tool_result", content="approve?", metadata={"approval_required": True})

    handler = ToolHandlerMixin.__new__(ToolHandlerMixin)
    handler._dispatch_tool_call = dispatch
    items = [item async for item in handler._process_tool_calls([{"name": "a"}, {"name": "b"}], "s", "t", "e", "m")]

    assert dispatched == ["a"]
    assert items[-1] == (True, None)


@pytest.mark.asyncio
async def test_a_second_command_cannot_replace_a_pending_approval():
    """A yes to the first card must run the first command, so the second is refused and never queued."""
    handler = MagicMock(check_auto_approve_rules=AsyncMock(return_value=False))
    session = MagicMock(has_pending_approval=MagicMock(return_value=True))
    with patch(
        "services.agent_terminal.ai_line_gate.resolve_command_line", AsyncMock(return_value=_verdict(Outcome.HOLD))
    ):
        decision = await decide_command(handler, session, "rm y", MagicMock(value="high"), force_approval=True)
    assert decision == (False, PENDING_APPROVAL_REFUSAL)


@pytest.mark.asyncio
async def test_a_read_still_runs_while_an_approval_is_pending():
    session = MagicMock(has_pending_approval=MagicMock(return_value=True))
    with patch(
        "services.agent_terminal.ai_line_gate.resolve_command_line", AsyncMock(return_value=_verdict(Outcome.RUN))
    ):
        decision = await decide_command(MagicMock(), session, "ls", MagicMock(value="safe"), force_approval=False)
    assert decision == (True, None)


@pytest.mark.asyncio
async def test_a_turn_that_started_without_a_terminal_session_uses_the_one_the_command_created():
    """Otherwise a held command is queued and its approval card cannot be reached."""
    seen: list = []

    async def dispatch(status, session_id, terminal_session_id, *_args):
        seen.append((status, terminal_session_id))
        if False:
            yield

    handler = ToolHandlerMixin.__new__(ToolHandlerMixin)
    handler.terminal_tool = MagicMock(active_sessions={"chat-1": "agent-session"})
    handler._execute_terminal_command = AsyncMock(return_value={"status": "pending_approval"})
    handler._dispatch_command_by_status = dispatch
    call = {"name": "execute_command", "params": {"command": "rm x"}}
    with patch("chat_workflow.tool_handler._emit_before_tool_execute", AsyncMock(return_value=True)):
        [_ async for _ in handler._process_single_command(call, "chat-1", "", "e", "m", [], [])]
    assert seen == [("pending_approval", "agent-session")]


@pytest.mark.asyncio
async def test_two_overlapping_commands_cannot_replace_each_others_pending_approval():
    """The check and the write have no await between them, so the second caller is refused and never queued."""
    service = AgentTerminalService.__new__(AgentTerminalService)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def add_command(_command):
        entered.set()
        await release.wait()

    service.command_queue = MagicMock(add_command=add_command)
    service.redis_client = None
    service.terminal_logger = MagicMock(log_command=AsyncMock())
    session = AgentTerminalSession(session_id="s", agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id=None)
    queue = partial(
        service._queue_command_for_approval,
        session,
        description=None,
        risk=CommandRisk.HIGH,
        reasons=[],
        is_interactive=False,
        interactive_reasons=[],
    )
    first = asyncio.create_task(queue(command="rm first"))
    await entered.wait()
    second = await queue(command="rm second")
    release.set()
    await first

    assert session.pending_approval["command"] == "rm first"
    assert second["status"] == "error"
    assert PENDING_APPROVAL_REFUSAL in second["error"]


@pytest.mark.asyncio
async def test_a_turn_cancelled_during_the_queue_write_does_not_strand_the_session():
    """Nothing was queued, so no pending approval may stay behind and refuse every later command."""
    service = AgentTerminalService.__new__(AgentTerminalService)
    entered = asyncio.Event()

    async def add_command(_command):
        entered.set()
        await asyncio.Event().wait()

    service.command_queue = MagicMock(add_command=add_command)
    service.redis_client = None
    service.terminal_logger = MagicMock(log_command=AsyncMock())
    session = AgentTerminalSession(session_id="s", agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id=None)
    task = asyncio.create_task(
        service._queue_command_for_approval(
            session,
            command="rm x",
            description=None,
            risk=CommandRisk.HIGH,
            reasons=[],
            is_interactive=False,
            interactive_reasons=[],
        )
    )
    await entered.wait()
    assert session.has_pending_approval()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not session.has_pending_approval()
