# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cancelling a turn stops the terminal command it was waiting on (#17273).

The agent's shell is a long-lived PTY that outlives any task. When a chat turn
was cancelled the executor stopped polling for the command's exit code and left
the command running in the shell -- a stop button that stopped nothing the user
could see. The executor now sends Ctrl+C to the PTY on cancellation.
"""

import asyncio

import pytest

import services.simple_pty as simple_pty_module
from services.agent_terminal.command_executor import CommandExecutor
from services.agent_terminal.models import AgentTerminalSession
from services.command_approval_manager import AgentRole
from tests.helpers.fake_pty_shell import FakeManager, FakeShell


async def _start(monkeypatch, shell):
    monkeypatch.setattr(simple_pty_module, "simple_pty_manager", FakeManager(shell))
    session = AgentTerminalSession(
        session_id="s-1", agent_id="agent-1", agent_role=AgentRole.CHAT_AGENT, pty_session_id="pty-1"
    )
    task = asyncio.ensure_future(CommandExecutor().execute_in_pty(session, "sleep 999", timeout=30.0))
    while not any("sleep 999" in w for w in shell.writes):
        await asyncio.sleep(0.01)
    return task


@pytest.mark.asyncio
async def test_cancelling_the_wait_interrupts_the_running_command(monkeypatch):
    shell = FakeShell(hangs={"sleep 999"})
    task = await _start(monkeypatch, shell)
    assert "\x03" not in shell.writes

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "\x03" in shell.writes, "the command must receive Ctrl+C, not be left running in the shell"


@pytest.mark.asyncio
async def test_a_command_that_finishes_is_not_interrupted(monkeypatch):
    shell = FakeShell(results={"sleep 999": ("done", 0)})
    task = await _start(monkeypatch, shell)

    result = await task

    assert result["status"] == "success"
    assert "\x03" not in shell.writes
