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
from services.agent_terminal.command_executor import TIMED_OUT_RETURN_CODE, CommandExecutor
from services.agent_terminal.models import AgentTerminalSession
from services.command_approval_manager import AgentRole

PROMPT = "user@host:~$ "


class _Shell:
    """A PTY running an interactive shell, as far as the executor can tell."""

    def __init__(self, results=None, hangs=(), history=""):
        self.results = results or {}  # command -> (output, exit code)
        self.hangs = set(hangs)  # commands that never return
        self.transcript = history + PROMPT
        self.writes = []
        self.alive = True
        self.busy = False
        self.last_code = 0

    def transcript_position(self):
        return len(self.transcript)

    def read_transcript(self, since):
        return self.transcript[since:]

    def is_alive(self):
        return self.alive

    def write_input(self, text):
        self.writes.append(text)
        for line in text.split("\n")[:-1]:
            if self.alive and not self.busy:  # a typed-ahead line waits for the running command
                self._run(line)
        return True

    def _run(self, line):
        self.transcript += f"{line}\r\n"
        if line in self.hangs:
            self.busy = True
        elif line == "exit":
            self.alive = False
        elif line.startswith("echo '__EXIT_CODE_"):
            marker = line[len("echo '") : line.index("'$?")]
            self.transcript += f"{marker}{self.last_code}\r\n{PROMPT}"
        else:
            output, self.last_code = self.results.get(line, ("", 0))
            self.transcript += (f"{output}\r\n" if output else "") + PROMPT


class _Manager:
    """simple_pty_manager, recording what the executor asks of it."""

    def __init__(self, shell):
        self.shell, self.created, self.closed = shell, [], []

    def get_session(self, session_id):
        return self.shell

    def create_session(self, session_id, initial_cwd=None):
        self.created.append(session_id)
        self.shell = _Shell()
        return self.shell

    def close_session(self, session_id):
        self.closed.append(session_id)
        self.shell.alive = False


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(executor_module.TimingConstants, "SERVICE_STARTUP_DELAY", 0)

    async def _run(shell, command, timeout=30.0):
        manager = _Manager(shell)
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
    shell = _Shell(results={"ls": ("a.txt\r\nb.txt", 0)})

    result, _, elapsed = await run(shell, "ls", timeout=30.0)

    assert elapsed < 2.0, f"waited {elapsed:.2f}s for a command that had already finished"
    assert result == {"status": "success", "stdout": "a.txt\nb.txt", "stderr": "", "return_code": 0}


@pytest.mark.asyncio
async def test_the_exit_code_is_the_commands_own(run):
    result, _, _ = await run(_Shell(results={"false": ("", 1)}), "false")

    assert (result["status"], result["return_code"]) == ("error", 1)


@pytest.mark.asyncio
async def test_output_already_on_screen_is_not_the_commands_output(run):
    shell = _Shell(results={"pwd": ("/home/user", 0)}, history="earlier secret output\r\n")

    result, _, _ = await run(shell, "pwd")

    assert result["stdout"] == "/home/user"


@pytest.mark.asyncio
async def test_a_timed_out_command_is_reported_as_timed_out_never_as_success(run):
    """The negative control: the old path killed the shell, wrote its marker into a new one, and got 0."""
    shell = _Shell(hangs={"sleep 999"})

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
    session_shell = _Shell(hangs={"sleep 999"})
    manager = _Manager(session_shell)
    monkeypatch.setattr(simple_pty_module, "simple_pty_manager", manager)
    session = AgentTerminalSession(
        session_id="s-1", agent_id="agent-1", agent_role=AgentRole.CHAT_AGENT, pty_session_id="pty-1"
    )

    result = await CommandExecutor().execute_in_pty(session, "sleep 999")

    assert result["status"] == "timeout" and "0.2s" in result["stderr"]


@pytest.mark.asyncio
async def test_a_shell_that_exits_is_an_error_not_a_timeout(run):
    result, manager, elapsed = await run(_Shell(), "exit", timeout=30.0)

    assert result["status"] == "error" and "shell ended" in result["stderr"]
    assert elapsed < 2.0 and manager.created == []


@pytest.mark.asyncio
async def test_a_stale_shell_is_recreated_before_the_command_not_after(run):
    stale = _Shell()
    stale.alive = False

    result, manager, _ = await run(stale, "true")

    assert manager.created == ["pty-1"]
    assert result["status"] == "success" and stale.writes == []
