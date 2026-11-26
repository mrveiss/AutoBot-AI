# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An auto-approved command's interpretation never blocks or fails its result (#21938)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.async_compat import pending_background_tasks
from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.service import AgentTerminalService
from services.command_approval_manager import AgentRole

pytestmark = pytest.mark.asyncio

RESULT = {"status": "success", "stdout": "6.1.0", "stderr": "", "return_code": 0}


def _service(interpret) -> AgentTerminalService:
    service = AgentTerminalService.__new__(AgentTerminalService)
    service.chat_workflow_manager = MagicMock()
    service.chat_workflow_manager._get_last_user_message = AsyncMock(return_value="the question")
    service.chat_workflow_manager.interpret_terminal_command = interpret
    return service


def _session() -> AgentTerminalSession:
    return AgentTerminalSession(
        session_id="t1",
        agent_id="a",
        agent_role=AgentRole.CHAT_AGENT,
        conversation_id="c1",
    )


async def _drain() -> None:
    while pending_background_tasks():
        await asyncio.sleep(0)


async def test_a_hanging_interpretation_does_not_hold_the_tool_result():
    release = asyncio.Event()
    started = asyncio.Event()

    async def hanging(**_kw):
        started.set()
        await release.wait()

    service = _service(hanging)
    service._interpret_command_result(_session(), "uname -r", RESULT)  # returns at once: it is not a coroutine
    await asyncio.wait_for(started.wait(), 5)
    assert not release.is_set()
    release.set()
    await asyncio.wait_for(_drain(), 5)


async def test_a_timing_out_interpreter_fails_neither_the_command_nor_the_turn():
    async def timing_out(**_kw):
        raise TimeoutError("Timeout on reading data from socket")

    service = _service(timing_out)
    service._interpret_command_result(_session(), "uname -r", RESULT)
    await asyncio.wait_for(_drain(), 5)  # the failure was logged in the task; nothing propagated


async def test_the_interpretation_is_stored_against_the_message_it_answers_not_a_later_one():
    interpret = AsyncMock()
    service = _service(interpret)
    service.chat_workflow_manager._get_last_user_message = AsyncMock(side_effect=["first question", "later question"])
    service._interpret_command_result(_session(), "uname -r", RESULT)
    await asyncio.wait_for(_drain(), 5)
    assert interpret.await_args.kwargs["user_message"] == "first question"
