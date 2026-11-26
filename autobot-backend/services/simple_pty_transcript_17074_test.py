# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A PTY keeps a readable transcript without taking output from its WebSocket (#17074).

The agent command executor reads a command's output from this transcript. The
output queue stays the terminal WebSocket's alone, so reading the transcript
must never consume it.
"""

import services.simple_pty as simple_pty_module
from services.simple_pty import SimplePTY


class _FakeOs:
    """``simple_pty``'s ``os`` with the two fd calls faked: the swap is on the module attribute only, so the real
    ``os.close`` / ``os.set_blocking`` stay untouched for pytest, asyncio and every other thread (#17074)."""

    close = staticmethod(lambda fd: None)
    set_blocking = staticmethod(lambda fd, flag: None)

    def __getattr__(self, name):
        import os

        return getattr(os, name)


def test_the_transcript_is_addressed_by_absolute_offset():
    pty = SimplePTY("t-1")
    pty._append_transcript("abc")
    pty._append_transcript("def")

    assert pty.transcript_position() == 6
    assert [pty.read_transcript(since) for since in (0, 2, 6)] == [(0, "abcdef"), (2, "cdef"), (6, "")]


def test_the_oldest_output_is_dropped_past_the_cap_and_offsets_stay_absolute(monkeypatch):
    monkeypatch.setattr(simple_pty_module, "_TRANSCRIPT_MAX_CHARS", 5)
    pty = SimplePTY("t-1")
    for chunk in ("abc", "def", "ghi"):
        pty._append_transcript(chunk)

    assert pty.transcript_position() == 9
    assert pty.read_transcript(0) == (6, "ghi"), "an offset past the one asked for says output was dropped"
    assert pty.read_transcript(7) == (7, "hi")


def test_the_read_loop_feeds_the_transcript_and_still_feeds_the_queue(monkeypatch):
    events = iter([("output", "hello", False), ("eof", "", True)])
    monkeypatch.setattr(simple_pty_module, "poll_readable", lambda fd, timeout_ms: True)
    monkeypatch.setattr(simple_pty_module, "_read_pty_data", lambda fd: next(events))
    pty = SimplePTY("t-1")
    pty.running, pty.master_fd = True, 99

    pty._read_loop()

    assert pty.read_transcript(0) == (0, "hello")
    assert pty.get_output() == ("output", "hello"), "the WebSocket's queue still gets every output event"
    pty.read_transcript(0)
    assert pty.get_output() == ("eof", "")


def test_the_shell_gets_the_sbin_dirs_and_pipefail_22251_22252(monkeypatch):
    """The env handed to the spawned shell carries /usr/sbin and /sbin; the shell runs with pipefail."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("PATH", "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin")
    popen = MagicMock()
    monkeypatch.setattr(simple_pty_module.subprocess, "Popen", popen)
    monkeypatch.setattr(simple_pty_module, "os", _FakeOs())
    pty = SimplePTY("t-1", pipefail=True)
    pty.master_fd = 0
    pty._spawn_bash_process(5, simple_pty_module.with_sbin_on_path(dict(simple_pty_module.os.environ)), "/")

    env_dirs = popen.call_args.kwargs["env"]["PATH"].split(":")
    assert {"/usr/local/sbin", "/usr/sbin", "/sbin"} <= set(env_dirs)
    assert env_dirs[:4] == ["/opt/venv/bin", "/usr/local/bin", "/usr/bin", "/bin"]  # existing order kept
    assert popen.call_args.args[0][-2:] == ["-o", "pipefail"]


def test_an_interactive_shell_does_not_get_pipefail_22252(monkeypatch):
    """Only the agent-command path asks for pipefail; a user's shell keeps `cmd | head` at exit 0."""
    from unittest.mock import MagicMock

    popen = MagicMock()
    monkeypatch.setattr(simple_pty_module.subprocess, "Popen", popen)
    monkeypatch.setattr(simple_pty_module, "os", _FakeOs())
    pty = SimplePTY("t-2")
    pty._spawn_bash_process(5, {}, "/")

    assert "pipefail" not in popen.call_args.args[0]
