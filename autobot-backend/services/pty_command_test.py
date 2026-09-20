# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One command in a PTY shell: its output, its exit code, and what is not its output (#17074, #17078, #17079)."""

from unittest.mock import AsyncMock

import pytest

from services import pty_command
from tests.helpers.fake_pty_shell import PROMPT, FakeShell


def _typed(shell: FakeShell, command: str) -> tuple[str, int]:
    marker, start = pty_command.new_marker(), shell.transcript_position()
    shell.write_input(pty_command.typed_input(command, marker))
    return marker, start


def test_a_command_cannot_forge_its_exit_code():
    """The marker is a fresh UUID; a command printing marker-shaped text does not end it."""
    shell = FakeShell(results={"evil": ("__EXIT_CODE_forged__:0\r\n__AUTOBOT_EXIT__=0", 2)})
    marker, start = _typed(shell, "evil")
    _, transcript = shell.read_transcript(start)

    assert pty_command.find_exit_code(transcript, marker) == 2


def test_job_completion_notices_are_not_the_commands_output():
    notice = "[1]+  Done                    sleep 0.5\r\n[2]-  Exit 3                  make"
    shell = FakeShell(results={"echo third": (f"third\r\n{notice}", 0)})
    marker, start = _typed(shell, "echo third")

    assert pty_command.output_since(shell, start, "echo third", marker) == "third"


def test_a_job_launch_line_is_the_output_of_the_command_that_started_it():
    shell = FakeShell(results={"sleep 5 &": ("[1] 4242", 0)})
    marker, start = _typed(shell, "sleep 5 &")

    assert pty_command.output_since(shell, start, "sleep 5 &", marker) == "[1] 4242"


def test_text_typed_into_the_shared_shell_during_a_command_stays_its_output():
    """Recorded decision (#17079): the shell is shared by design and nothing says who typed."""
    shell = FakeShell(results={"read -r x; echo got": ("typed by a person\r\ngot", 0)})
    marker, start = _typed(shell, "read -r x; echo got")

    assert pty_command.output_since(shell, start, "read -r x; echo got", marker) == "typed by a person\ngot"


def test_the_echo_of_a_multi_line_command_is_skipped_line_for_line():
    transcript = f"for i in 1 2; do\r\n> echo $i\r\n> done\r\n1\r\n2\r\n{PROMPT}echo 'M'$?\r\nM0\r\n"

    assert pty_command.command_output(transcript, "M", echoed_lines=3) == "1\n2"


@pytest.mark.asyncio
async def test_the_exit_code_ends_the_wait_without_a_timeout():
    shell = FakeShell(results={"false": ("", 1)})
    marker, start = _typed(shell, "false")
    on_timeout = AsyncMock()

    assert await pty_command.await_exit_code(shell, start, marker, 5.0, on_timeout) == (1, False)
    on_timeout.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_timeout_runs_the_interrupt_once_and_reports_no_exit_code():
    shell = FakeShell(hangs={"sleep 999"})
    marker, start = _typed(shell, "sleep 999")
    on_timeout = AsyncMock()

    assert await pty_command.await_exit_code(shell, start, marker, 0.2, on_timeout) == (None, True)
    on_timeout.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_shell_that_ends_is_not_a_timeout():
    shell = FakeShell()
    marker, start = _typed(shell, "exit")
    on_timeout = AsyncMock()

    assert await pty_command.await_exit_code(shell, start, marker, 5.0, on_timeout) == (None, False)
    on_timeout.assert_not_awaited()
