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
