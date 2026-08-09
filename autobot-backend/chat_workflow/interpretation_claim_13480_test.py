# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""An approved command must be interpreted exactly once (#13480).

Two paths interpreted the same result, and **both persist**:

* the approve path — `interpret_terminal_command` (non-streaming) →
  `_save_to_chat_history`, one `terminal_interpretation` message
  (`llm_handler.py:1079`, the only occurrence of that type in the codebase);
* the chat turn — `_handle_approved_command` streams `WorkflowMessage` chunks,
  and `_build_workflow_message_batch` (`manager.py:3010`) persists **every**
  message a turn produces.

So an approved command with a watcher cost two LLM calls and put two
explanations of one command in the conversation.

The fix is a claim the polling turn holds. The dangerous half is releasing it:
if the claim outlives the poller, the approve path keeps skipping while nobody
is listening, and a late approval produces no interpretation at all — silently
re-breaking #13479 in the exact case it exists for. Hence a `finally`, and hence
the tests below covering timeout, early close and exception, not just the happy
path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


def _handler(service):
    from chat_workflow.tool_handler import ToolHandlerMixin

    class _Handler(ToolHandlerMixin):
        pass

    h = _Handler()
    h.terminal_tool = MagicMock()
    h.terminal_tool.agent_terminal_service = service
    h.terminal_tool.get_session_info = AsyncMock(return_value=None)
    return h


def _service():
    service = MagicMock()
    service.set_live_turn_interpreting = AsyncMock()
    return service


def _claims(service):
    """(session_id, live) for every claim call, in order."""
    return [c.args for c in service.set_live_turn_interpreting.call_args_list]


# --- the session marker -----------------------------------------------------


async def test_an_unmarked_approval_is_interpreted_by_the_approve_path():
    """The safe default: absent marker means the approve path owns it.

    Believing a turn is present when it has gone is the failure that leaves
    nobody interpreting, so the default must lean the other way.
    """
    from services.agent_terminal.models import AgentTerminalSession
    from services.command_approval_manager import AgentRole

    s = AgentTerminalSession(session_id="s1", agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id="c1")
    s.pending_approval = {"command": "ls -la"}

    assert s.has_live_turn_interpreting() is False


async def test_marking_a_session_with_no_pending_approval_is_a_no_op():
    """Creating the dict here would fabricate an approval nobody requested."""
    from services.agent_terminal.models import AgentTerminalSession
    from services.command_approval_manager import AgentRole

    s = AgentTerminalSession(session_id="s1", agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id="c1")
    s.set_live_turn_interpreting(True)

    assert s.pending_approval is None
    assert s.has_live_turn_interpreting() is False


async def test_the_marker_round_trips_on_a_pending_approval():
    from services.agent_terminal.models import AgentTerminalSession
    from services.command_approval_manager import AgentRole

    s = AgentTerminalSession(session_id="s1", agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id="c1")
    s.pending_approval = {"command": "ls -la"}

    s.set_live_turn_interpreting(True)
    assert s.has_live_turn_interpreting() is True
    s.set_live_turn_interpreting(False)
    assert s.has_live_turn_interpreting() is False


# --- claim lifecycle around the poller --------------------------------------


async def test_the_turn_claims_interpretation_while_polling():
    service = _service()
    handler = _handler(service)

    async for _ in handler._poll_for_approval("term-1", "ls -la", max_wait_time=0.02, poll_interval=0.01):
        pass

    assert ("term-1", True) in _claims(service), "the polling turn never claimed interpretation"


async def test_the_claim_is_released_when_the_poll_times_out():
    """The regression that would silently re-break #13479."""
    service = _service()
    handler = _handler(service)

    async for _ in handler._poll_for_approval("term-1", "ls -la", max_wait_time=0.02, poll_interval=0.01):
        pass

    assert _claims(service)[-1] == ("term-1", False), (
        "a timed-out poller left its claim set — the approve path would keep "
        "skipping while nobody is listening, so a late approval produces nothing"
    )


async def test_the_claim_is_released_when_the_consumer_stops_early():
    """`_handle_pending_approval` breaks out as soon as a decision lands.

    Closing a generator raises GeneratorExit at the suspension point, so only a
    `finally` releases here — code placed after the loop never runs.
    """
    service = _service()
    handler = _handler(service)

    gen = handler._poll_for_approval("term-1", "ls -la", max_wait_time=5, poll_interval=0.01)
    await gen.__anext__()
    await gen.aclose()

    assert _claims(service)[-1] == ("term-1", False), "an early-closed poller leaked its claim"


async def test_the_claim_is_released_even_if_claiming_never_worked():
    """A service without the method must not break the turn or leak state."""
    service = MagicMock(spec=[])  # no set_live_turn_interpreting
    handler = _handler(service)

    async for _ in handler._poll_for_approval("term-1", "ls -la", max_wait_time=0.02, poll_interval=0.01):
        pass  # must simply not raise


async def test_a_failing_claim_does_not_fail_the_turn():
    """Losing the claim costs a duplicate interpretation, not the user's turn."""
    service = _service()
    service.set_live_turn_interpreting = AsyncMock(side_effect=RuntimeError("redis down"))
    handler = _handler(service)

    async for _ in handler._poll_for_approval("term-1", "ls -la", max_wait_time=0.02, poll_interval=0.01):
        pass  # must not raise


# --- the approve path's half ------------------------------------------------


async def test_the_approve_path_skips_when_a_turn_holds_the_claim():
    from services.agent_terminal.service import AgentTerminalService

    svc = AgentTerminalService.__new__(AgentTerminalService)
    svc.chat_workflow_manager = MagicMock()
    svc.chat_workflow_manager.interpret_terminal_command = AsyncMock()

    session = MagicMock()
    session.has_live_turn_interpreting.return_value = True

    await svc._interpret_approved_command(session, "ls -la", {"stdout": "x"})

    svc.chat_workflow_manager.interpret_terminal_command.assert_not_awaited()


async def test_the_approve_path_interprets_when_no_turn_holds_the_claim():
    """The late-approval case — this is what #13479 depends on."""
    from services.agent_terminal.service import AgentTerminalService

    svc = AgentTerminalService.__new__(AgentTerminalService)
    svc.chat_workflow_manager = MagicMock()
    svc.chat_workflow_manager.interpret_terminal_command = AsyncMock()

    session = MagicMock()
    session.has_live_turn_interpreting.return_value = False
    session.has_conversation.return_value = True
    session.conversation_id = "conv-1"

    await svc._interpret_approved_command(session, "ls -la", {"stdout": "x", "return_code": 0})

    svc.chat_workflow_manager.interpret_terminal_command.assert_awaited_once()
