# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A non-blocking write loses input in two silent ways; neither may happen (#17381).

`master_fd` is non-blocking (`os.set_blocking(..., False)` in `_spawn`), so one
`os.write` expresses two outcomes a single call cannot:

* it may write FEWER bytes than handed to it -- the old code discarded the
  return value, so the remainder of a large paste vanished, at a byte boundary
  that can split a multi-byte UTF-8 character;
* it may raise `BlockingIOError` meaning "buffer full, not now" -- the old code
  let that reach a broad `except Exception` which logged and `break`, ending the
  write thread for the life of the session. The read loop keeps streaming
  output, so the terminal looks healthy while accepting no input at all.

These tests run against a REAL non-blocking pipe rather than a patched
`os.write`. A fake can only reproduce the semantics someone believed; a pipe
whose buffer is genuinely full produces the real short write and the real
`EAGAIN`, and it cannot drift from what the kernel actually does. It also avoids
patching a global that pytest itself writes through.

Mutation to check these are not vacuous: replace `_write_all`'s body with a
single `os.write(fd, data)`. The short-write test then loses the tail and the
backpressure test raises `BlockingIOError` -- both fail.
"""

import os
import threading
import time

import pytest

from services.simple_pty import SimplePTY

#: Comfortably larger than any pipe buffer (Linux default is 64 KiB), so a
#: single write CANNOT complete and the retry path is genuinely exercised.
_PAYLOAD_BYTES = 1024 * 1024


@pytest.fixture
def pipe_pty():
    """A PTY whose descriptor is a real non-blocking pipe."""
    read_fd, write_fd = os.pipe()
    os.set_blocking(write_fd, False)
    pty = SimplePTY(session_id="write-all-17381")
    pty.master_fd = write_fd
    pty.running = True
    yield pty, read_fd, write_fd
    for fd in (read_fd, write_fd):
        try:
            os.close(fd)
        except OSError:
            pass


def _drain(read_fd: int, expected: int, sink: list, start_delay: float = 0.05) -> threading.Thread:
    """Read *expected* bytes, after a pause that guarantees the writer blocks first."""

    def run() -> None:
        time.sleep(start_delay)
        got = b""
        while len(got) < expected:
            chunk = os.read(read_fd, 65536)
            if not chunk:
                break
            got += chunk
        sink.append(got)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def test_every_byte_of_a_large_write_arrives(pipe_pty):
    """The short-write defect: a paste bigger than the buffer must not be truncated.

    This test also caught a second bug, in the fix itself. `_write_all` first
    bounded its retrying by TOTAL elapsed time, which passes every small-input
    test and truncates exactly the large write the method exists to deliver -- a
    1 MiB payload needs many buffer-fills and blew the budget. The bound is now
    time since last PROGRESS. Keep the payload well above any pipe buffer or
    this test stops distinguishing the two.
    """
    pty, read_fd, _ = pipe_pty
    payload = os.urandom(_PAYLOAD_BYTES)
    sink: list = []
    reader = _drain(read_fd, len(payload), sink)

    pty._write_all(payload)
    reader.join(timeout=10.0)

    assert sink, "reader produced nothing"
    assert len(sink[0]) == len(payload), (
        f"delivered {len(sink[0])} of {len(payload)} bytes -- os.write returns how many "
        "bytes it took, and discarding that number truncates the write"
    )
    assert sink[0] == payload, "bytes arrived corrupted or out of order"


def test_a_full_buffer_is_backpressure_not_failure(pipe_pty):
    """EAGAIN means 'not now'. Treating it as fatal kills the session's input."""
    pty, read_fd, write_fd = pipe_pty

    # Fill the buffer so the very first write inside _write_all raises EAGAIN.
    with pytest.raises(BlockingIOError):
        while True:
            os.write(write_fd, b"\xff" * 4096)

    payload = b"typed input after the buffer filled\n"
    sink: list = []
    reader = _drain(read_fd, 1, sink, start_delay=0.1)

    # Returning at all IS the assertion. The old code let BlockingIOError reach
    # the write loop's broad `except Exception`, which logged and `break` -- so
    # against the unfixed version this call raises and the test fails here.
    # Asserting on what the reader collected would be weaker, not stronger: it
    # drains the 0xff padding first, so a truthy sink proves nothing about the
    # payload.
    pty._write_all(payload)
    reader.join(timeout=10.0)


def test_a_multibyte_character_survives_a_split_write(pipe_pty):
    """A short write can land mid-sequence; the result must still decode."""
    pty, read_fd, _ = pipe_pty
    text = "→ ünïcödé ✓ " * 40000  # multi-byte throughout, larger than the buffer
    payload = text.encode("utf-8")
    sink: list = []
    reader = _drain(read_fd, len(payload), sink)

    pty._write_all(payload)
    reader.join(timeout=10.0)

    assert sink, "reader produced nothing"
    assert sink[0].decode("utf-8") == text, (
        "a partial write split a multi-byte sequence and the remainder was lost " "or reassembled wrongly"
    )


def test_retrying_is_bounded_rather_than_forever(pipe_pty, monkeypatch):
    """A child that never drains must not park the writer indefinitely."""
    pty, _, write_fd = pipe_pty
    monkeypatch.setattr("services.simple_pty._WRITE_STALL_BUDGET_S", 0.3)

    with pytest.raises(BlockingIOError):
        while True:
            os.write(write_fd, b"\xff" * 4096)

    started = time.monotonic()
    with pytest.raises(BlockingIOError):
        pty._write_all(b"nobody is reading this")
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, f"retried for {elapsed:.1f}s against a 0.3s budget -- the bound is not applied"


def test_a_descriptor_closed_mid_write_is_not_an_error(pipe_pty):
    """cleanup() may land between iterations; the loop's own conditions handle it."""
    pty, _, _ = pipe_pty
    pty.master_fd = None
    pty._write_all(b"anything")  # must return quietly, not raise
