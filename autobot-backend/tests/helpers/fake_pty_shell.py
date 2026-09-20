# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fake interactive shell in a PTY, faithful to what the PTY command runner relies on (#17074, #17078).

Each line the shell reads is echoed, run and followed by the next prompt; a
multi-line command is echoed with its continuations behind PS2 (``> ``); a line
typed ahead of a running command waits until it returns; Ctrl+C is not a line;
and the transcript is addressed by absolute offset like ``SimplePTY``'s.
"""

import time

PROMPT = "user@host:~$ "


class FakeShell:
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


class FakeManager:
    """simple_pty_manager, recording what the executor asks of it."""

    def __init__(self, shell):
        self.shell, self.created, self.closed = shell, [], []

    def get_session(self, session_id):
        return self.shell

    def create_session(self, session_id, initial_cwd=None):
        self.created.append(session_id)
        self.shell = FakeShell()
        return self.shell

    def close_session(self, session_id):
        self.closed.append(session_id)
        self.shell.alive = False
