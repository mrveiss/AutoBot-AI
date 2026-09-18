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

PROMPT = "user@host:~$ "


class _Shell:
    """A PTY running an interactive shell, as far as the executor can tell."""

    def __init__(self, results=None, hangs=(), history="", finishes_after=None, drops_output=False):
        self.results = results or {}  # command -> (output, exit code); a multi-line command is one key
        self.hangs = set(hangs)  # commands that never return
        self.finishes_after = finishes_after  # (command, seconds): returns only after that long
        self.drops_output = drops_output  # the transcript cap drops the start of the next command
        self.transcript = history + PROMPT
        self.base = 0  # absolute offset of the oldest output still held
        self.pending = None  # (due time, command) of a slow command still running
        self.queued = None  # the marker line typed ahead of a running command
        self.writes = []
        self.alive = True
        self.busy = False
        self.last_code = 0

    def transcript_position(self):
        return len(self.transcript)

    def read_transcript(self, since):
        if self.pending and time.monotonic() >= self.pending[0]:
            self._finish(*self.pending[1:])
        offset = max(since, self.base)
        return offset, self.transcript[offset:]

    def is_alive(self):
        return self.alive

    def write_input(self, text):
        self.writes.append(text)
        rest = text
        while rest:
            whole = next((c for c in self.results if "\n" in c and rest.startswith(c + "\n")), None)
            line = whole or rest.split("\n", 1)[0]
            rest = rest[len(line) + 1 :]
            if self.alive and not self.busy:  # a typed-ahead line waits for the running command
                self._run(line)
            elif self.busy and line.startswith("echo '__EXIT_CODE_"):
                self.queued = line
        return True

    def _run(self, line):
        first, *continuations = line.split("\n")  # bash echoes continuations behind PS2
        self.transcript += f"{first}\r\n" + "".join(f"> {more}\r\n" for more in continuations)
        if self.drops_output:  # once: the cap drops up to a few characters into this command's output
            self.base, self.drops_output = len(self.transcript) + 3, False
        if self.finishes_after and line == self.finishes_after[0]:
            self.busy = True
            self.pending = (time.monotonic() + self.finishes_after[1], line)
        elif line in self.hangs:
            self.busy = True
        elif line == "exit":
            self.alive = False
        elif line.startswith("echo '__EXIT_CODE_"):
            marker = line[len("echo '") : line.index("'$?")]
            self.transcript += f"{marker}{self.last_code}\r\n{PROMPT}"
        else:
            output, self.last_code = self.results.get(line, ("", 0))
            self.transcript += (f"{output}\r\n" if output else "") + PROMPT

    def _finish(self, line):
        """A slow command returns; the marker typed ahead of it runs now."""
        self.pending, self.busy = None, False
        output, self.last_code = self.results.get(line, ("", 0))
        self.transcript += (f"{output}\r\n" if output else "") + PROMPT
        self._run(self.queued)


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


@pytest.mark.asyncio
async def test_a_multi_line_command_echo_is_not_its_output(run):
    """bash echoes each continuation line behind PS2 ('> '); none of that is output (#17074 review)."""
    loop = "for i in 1 2; do\necho $i\ndone"

    result, _, _ = await run(_Shell(results={loop: ("1\r\n2", 0)}), loop)

    assert result["stdout"] == "1\n2"


@pytest.mark.asyncio
async def test_output_the_transcript_cap_already_dropped_is_marked_not_passed_off_as_whole(run):
    shell = _Shell(results={"make": ("building everything\r\nall done", 0)}, drops_output=True)

    result, _, _ = await run(shell, "make")

    assert result["stdout"].startswith(TRUNCATED_NOTE)
    assert result["stdout"].endswith("all done") and result["return_code"] == 0


@pytest.mark.asyncio
async def test_a_command_finishing_at_the_deadline_reports_its_exit_code_not_a_timeout(run):
    """Output already on the wire at the deadline gets one more read before the cancel (#17074 review)."""
    shell = _Shell(results={"slow": ("done", 3)}, finishes_after=("slow", 0.32))

    result, manager, _ = await run(shell, "slow", timeout=0.3)

    assert (result["status"], result["return_code"], result["stdout"]) == ("error", 3, "done")
    assert manager.closed == [], "a finished command is not cancelled"
