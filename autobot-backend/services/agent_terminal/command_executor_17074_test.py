# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An agent command finishes when it finishes, and a timed-out one is never a success (#17074).

The executor used to poll chat history for ``sender == "terminal"`` while agent
output is saved as ``agent_terminal`` after the command returns, so every
command waited out its timeout. On timeout it SIGKILLed the PTY and then wrote
its exit-code marker, which recreated a blank shell and reported that shell's
``EXIT_CODE: 0``. These tests drive the executor against a shell that behaves
like the real one: each line it reads is echoed, run, and followed by the next
prompt, and a line typed ahead waits until the running command returns.
"""

import time

import pytest

import services.simple_pty as simple_pty_module
from services.agent_terminal import command_executor as executor_module
from services.agent_terminal.command_executor import TIMED_OUT_RETURN_CODE, TRUNCATED_NOTE, CommandExecutor
from services.agent_terminal.models import AgentTerminalSession
from services.command_approval_manager import AgentRole
from tests.helpers.fake_pty_shell import FakeManager, FakeShell


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(executor_module.TimingConstants, "SERVICE_STARTUP_DELAY", 0)

    async def _run(shell, command, timeout=30.0):
        manager = FakeManager(shell)
        monkeypatch.setattr(simple_pty_module, "simple_pty_manager", manager)
        session = AgentTerminalSession(
            session_id="s-1", agent_id="agent-1", agent_role=AgentRole.CHAT_AGENT, pty_session_id="pty-1"
        )
        started = time.monotonic()
        result = await CommandExecutor().execute_in_pty(session, command, timeout=timeout)
        return result, manager, time.monotonic() - started

    return _run


@pytest.mark.asyncio
async def test_a_fast_command_returns_as_soon_as_it_finishes(run):
    shell = FakeShell(results={"ls": ("a.txt\r\nb.txt", 0)})

    result, _, elapsed = await run(shell, "ls", timeout=30.0)

    assert elapsed < 2.0, f"waited {elapsed:.2f}s for a command that had already finished"
    assert result == {"status": "success", "stdout": "a.txt\nb.txt", "stderr": "", "return_code": 0}


@pytest.mark.asyncio
async def test_the_exit_code_is_the_commands_own(run):
    result, _, _ = await run(FakeShell(results={"false": ("", 1)}), "false")

    assert (result["status"], result["return_code"]) == ("error", 1)


@pytest.mark.asyncio
async def test_output_already_on_screen_is_not_the_commands_output(run):
    shell = FakeShell(results={"pwd": ("/home/user", 0)}, history="earlier secret output\r\n")

    result, _, _ = await run(shell, "pwd")

    assert result["stdout"] == "/home/user"


@pytest.mark.asyncio
async def test_a_timed_out_command_is_reported_as_timed_out_never_as_success(run):
    """The negative control: the old path killed the shell, wrote its marker into a new one, and got 0."""
    shell = FakeShell(hangs={"sleep 999"})

    result, manager, _ = await run(shell, "sleep 999", timeout=0.3)

    assert result["status"] == "timeout"
    assert result["return_code"] == TIMED_OUT_RETURN_CODE != 0
    assert manager.closed == ["pty-1"], "the stuck command is still cancelled"
    assert manager.created == [], "no shell is recreated for a cancelled command"
    assert shell.writes[-1] == "\x03", "nothing is written to the PTY after the cancel"
    assert not any("__EXIT_CODE_" in write for write in shell.writes[1:])


@pytest.mark.asyncio
async def test_the_default_timeout_comes_from_the_environment_backed_constant(run, monkeypatch):
    monkeypatch.setattr(executor_module, "AGENT_COMMAND_TIMEOUT_S", 0.2)
    session_shell = FakeShell(hangs={"sleep 999"})
    manager = FakeManager(session_shell)
    monkeypatch.setattr(simple_pty_module, "simple_pty_manager", manager)
    session = AgentTerminalSession(
        session_id="s-1", agent_id="agent-1", agent_role=AgentRole.CHAT_AGENT, pty_session_id="pty-1"
    )

    result = await CommandExecutor().execute_in_pty(session, "sleep 999")

    assert result["status"] == "timeout" and "0.2s" in result["stderr"]


@pytest.mark.asyncio
async def test_a_shell_that_exits_is_an_error_not_a_timeout(run):
    result, manager, elapsed = await run(FakeShell(), "exit", timeout=30.0)

    assert result["status"] == "error" and "shell ended" in result["stderr"]
    assert elapsed < 2.0 and manager.created == []


@pytest.mark.asyncio
async def test_a_stale_shell_is_recreated_before_the_command_not_after(run):
    stale = FakeShell()
    stale.alive = False

    result, manager, _ = await run(stale, "true")

    assert manager.created == ["pty-1"]
    assert result["status"] == "success" and stale.writes == []


@pytest.mark.asyncio
async def test_a_multi_line_command_echo_is_not_its_output(run):
    """bash echoes each continuation line behind PS2 ('> '); none of that is output (#17074 review)."""
    loop = "for i in 1 2; do\necho $i\ndone"

    result, _, _ = await run(FakeShell(results={loop: ("1\r\n2", 0)}), loop)

    assert result["stdout"] == "1\n2"


@pytest.mark.asyncio
async def test_output_the_transcript_cap_already_dropped_is_marked_not_passed_off_as_whole(run):
    shell = FakeShell(results={"make": ("building everything\r\nall done", 0)}, drops_output=True)

    result, _, _ = await run(shell, "make")

    assert result["stdout"].startswith(TRUNCATED_NOTE)
    assert result["stdout"].endswith("all done") and result["return_code"] == 0


@pytest.mark.asyncio
async def test_a_command_finishing_at_the_deadline_reports_its_exit_code_not_a_timeout(run):
    """Output already on the wire at the deadline gets one more read before the cancel (#17074 review)."""
    shell = FakeShell(results={"slow": ("done", 3)}, finishes_after=("slow", 0.32))

    result, manager, _ = await run(shell, "slow", timeout=0.3)

    assert (result["status"], result["return_code"], result["stdout"]) == ("error", 3, "done")
    assert manager.closed == [], "a finished command is not cancelled"
