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

The fix is a claim the polling turn holds, now one compare-and-set token in
Redis (#21202, `services.agent_terminal.interpretation_turn`) rather than a flag
in one worker's copy of the session. The dangerous half is releasing it: if the
token outlives the poller, the worker that ran the command waits for a turn that
has gone. Hence a `finally`, and hence the tests below covering timeout, early
close and exception, not just the happy path. The two-worker ordering tests live
in `services/agent_terminal/closed_and_interpretation_21202_test.py`.
"""

from __future__ import annotations

import asyncio
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
    service.begin_interpreting_turn = AsyncMock(return_value="tok-1")
    service.take_turn_interpretation = AsyncMock(return_value=True)
    service.end_interpreting_turn = AsyncMock()
    return service


async def _poll(handler, **kwargs):
    kwargs.setdefault("max_wait_time", 0.02)
    kwargs.setdefault("poll_interval", 0.01)
    return [r async for r in handler._poll_for_approval("term-1", "ls -la", **kwargs)]


async def test_the_turn_registers_while_polling():
    service = _service()
    await asyncio.wait_for(_poll(_handler(service)), timeout=5)
    service.begin_interpreting_turn.assert_awaited_once_with("term-1")


async def test_the_token_is_released_when_the_poll_times_out():
    """The regression that would silently re-break #13479."""
    service = _service()
    await asyncio.wait_for(_poll(_handler(service)), timeout=5)
    service.end_interpreting_turn.assert_awaited_once_with("term-1", "tok-1")


async def test_the_token_is_released_when_the_consumer_stops_early():
    """`_handle_pending_approval` breaks out as soon as a decision lands.

    Closing a generator raises GeneratorExit at the suspension point, so only a `finally` releases here.
    """
    service = _service()
    gen = _handler(service)._poll_for_approval("term-1", "ls -la", max_wait_time=0.05, poll_interval=0.01)
    await asyncio.wait_for(gen.__anext__(), timeout=5)
    await gen.aclose()
    service.end_interpreting_turn.assert_awaited_once_with("term-1", "tok-1")


async def test_a_service_without_the_methods_does_not_break_the_turn():
    service = MagicMock(spec=[])
    await asyncio.wait_for(_poll(_handler(service)), timeout=5)  # must simply not raise


async def test_a_failing_registration_does_not_fail_the_turn():
    service = _service()
    service.begin_interpreting_turn = AsyncMock(side_effect=RuntimeError("redis down"))
    await asyncio.wait_for(_poll(_handler(service)), timeout=5)
    service.end_interpreting_turn.assert_not_awaited()  # there is no token to release


async def _finish_with(handler, service, owned: bool):
    service.take_turn_interpretation = AsyncMock(return_value=owned)
    result = {"status": "success", "stdout": "x"}
    handler._check_approval_completion = MagicMock(return_value=(result, {"s": 1}, True))
    handler.terminal_tool.get_session_info = AsyncMock(return_value={"pending_approval": None})
    await asyncio.wait_for(_poll(handler, max_wait_time=5), timeout=5)
    return result


async def test_a_turn_that_wins_the_swap_interprets():
    service = _service()
    result = await _finish_with(_handler(service), service, owned=True)
    service.take_turn_interpretation.assert_awaited_once_with("term-1", "tok-1")
    assert "interpretation_owned_elsewhere" not in result


async def test_a_turn_that_loses_the_swap_marks_the_result_interpreted_elsewhere():
    service = _service()
    result = await _finish_with(_handler(service), service, owned=False)
    assert result["interpretation_owned_elsewhere"] is True


async def test_the_approved_command_handler_skips_interpretation_when_the_swap_was_lost():
    handler = _handler(_service())
    handler._interpret_command_results = MagicMock()
    out = [
        m
        async for m in handler._handle_approved_command(
            "ls", "h", {"status": "success", "interpretation_owned_elsewhere": True}, "ep", "model"
        )
    ]
    handler._interpret_command_results.assert_not_called()
    assert out[-1][1] == ""


async def test_the_approved_command_handler_interprets_when_it_won():
    handler = _handler(_service())

    async def _chunks(*_a, **_k):
        yield MagicMock(content="done")

    handler._interpret_command_results = MagicMock(side_effect=_chunks)
    out = [m async for m in handler._handle_approved_command("ls", "h", {"status": "success"}, "ep", "model")]
    handler._interpret_command_results.assert_called_once()
    assert out[-1][1] == "done"
