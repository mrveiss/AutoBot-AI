# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run one command in an interactive PTY shell and read back its output and exit code.

Shared by the agent-terminal executor (#17074) and the overseer's step executor
(#17078); neither polls chat history for its own output any more.

The command is typed together with a UUID-marked ``echo '<marker>'$?`` line. An
interactive shell runs that line only after the command returns, so the
marker's appearance in the PTY's transcript (``SimplePTY.read_transcript``) is
the completion signal and ``$?`` is the command's own exit code, from the same
shell. The UUID makes the marker unforgeable by anything the command prints.

A command's output is the transcript between its echoed lines and the marker
line, so it is attributed by position (#17079). Two consequences are handled
here on purpose:

- bash prints job-control status notices ("[1]+  Done  sleep 1") just before a
  prompt, whichever command is running; they are removed from the output. A
  launch line ("[1] 4242") is kept -- it is the output of the command that
  started the job.
- text a person types into the shared shell while an agent command runs stays
  part of that command's output: the shell is shared by design, and nothing in
  the transcript says who typed.
"""

import asyncio
import re
import time
import uuid
from typing import Awaitable, Callable

from constants.threshold_constants import TimingConstants
from utils.encoding_utils import strip_ansi_codes

#: Return code reported for a command cancelled on timeout, as timeout(1) reports it.
TIMED_OUT_RETURN_CODE = 124

#: Prefixed to output whose start the transcript cap had already dropped.
TRUNCATED_NOTE = "[earlier output dropped: it exceeded the terminal transcript]\n"

#: A few of the PTY reader thread's 10 ms poll cycles: output already on the wire at
#: the deadline gets this long to be read before the command is called timed out.
READER_GRACE_S = 0.05

#: A bash job-control status notice, printed before a prompt for whichever job changed.
_JOB_NOTICE = re.compile(r"^\[\d+\][+-]?\s+(Done|Exit \d+|Stopped|Killed|Terminated|Running)\b")


def new_marker() -> str:
    """A marker no command output can reproduce."""
    return f"__EXIT_CODE_{uuid.uuid4()}__:"


def typed_input(command: str, marker: str) -> str:
    """What to type: the command, then the marker line the shell runs once it returns."""
    return f"{command}\necho '{marker}'$?\n"


def find_exit_code(transcript: str, marker: str) -> int | None:
    """The exit code printed after *marker*, or None if it has not appeared yet."""
    match = re.search(rf"{re.escape(marker)}(\d+)", strip_ansi_codes(transcript))
    return int(match.group(1)) if match else None


def command_output(transcript: str, marker: str, echoed_lines: int) -> str:
    """The output after the *echoed_lines* lines the shell echoed back, before the first marker line.

    A multi-line command is echoed one line per line, continuations behind the
    PS2 prompt, so the echo spans as many lines as the command does.
    """
    kept = []
    for line in strip_ansi_codes(transcript).replace("\r", "").split("\n")[echoed_lines:]:
        if marker in line:  # the prompt that echoes the marker line, or the marker's own output
            break
        if not _JOB_NOTICE.match(line):
            kept.append(line)
    return "\n".join(kept).strip()


def output_since(pty, start: int, command: str, marker: str) -> str:
    """The command's output, noting it when the transcript cap already dropped its beginning."""
    offset, transcript = pty.read_transcript(start)
    if offset > start:
        return TRUNCATED_NOTE + command_output(transcript, marker, echoed_lines=0)
    return command_output(transcript, marker, echoed_lines=command.count("\n") + 1)


def _scan_for_exit_code(pty, cursor: int, marker: str) -> tuple[int, int | None]:
    """Search only output past *cursor*, plus overlap for a marker split across reads."""
    offset, text = pty.read_transcript(max(cursor - len(marker) - 16, 0))
    return offset + len(text), find_exit_code(text, marker)


async def await_exit_code(
    pty, start: int, marker: str, timeout: float, on_timeout: Callable[[], Awaitable[None]]
) -> tuple[int | None, bool]:
    """Watch the transcript from *start* until the marker appears, the shell ends, or *timeout*.

    Each poll reads only output it has not scanned yet. At the deadline,
    *on_timeout* runs (it should interrupt the command) and nothing else is
    written or read from a new shell.

    Returns:
        (exit code, timed out) -- the code is None if the shell ended first or on timeout
    """
    deadline = time.monotonic() + timeout
    cursor, poll_interval = start, TimingConstants.MICRO_DELAY / 2
    while time.monotonic() < deadline:
        cursor, return_code = _scan_for_exit_code(pty, cursor, marker)
        if return_code is not None or not pty.is_alive():
            return return_code, False
        await asyncio.sleep(min(poll_interval, max(deadline - time.monotonic(), 0)))
        poll_interval = min(poll_interval * 1.5, 1.0)
    await asyncio.sleep(READER_GRACE_S)
    _, return_code = _scan_for_exit_code(pty, cursor, marker)
    if return_code is not None:
        return return_code, False
    await on_timeout()
    return None, True
