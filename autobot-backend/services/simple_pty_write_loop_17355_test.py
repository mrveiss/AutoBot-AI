# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The PTY write loop waits between items, and still stops on every path (#17355).

`_write_loop` used `input_queue.get_nowait()` with `except queue.Empty: continue`
and no sleep anywhere in its body, so an idle session re-entered the loop
immediately and burned 100% of a core -- one per live terminal, leak or no leak.
Its docstring said "Wait for input without timeout", which is what the loop was
meant to do and the opposite of what `get_nowait` does.

The obvious repair is the trap, and the second test here is the one that catches
it. A plain blocking `get()` looks correct against ``cleanup()``, which does put
a ``None`` sentinel -- but that ``put`` sits inside a swallowing ``try/except``
*after* ``running = False`` is already set, an abandoned session never calls
``cleanup()`` at all, and the loop's second condition (``master_fd is not None``)
is signalled by nothing. On any of those a blocking ``get()`` parks forever.
Only a BOUNDED wait re-checks the conditions regardless of what the caller did.
"""

import queue
import threading
import time

import pytest

from services.simple_pty import SimplePTY

#: Long enough that a spinning loop racks up thousands of calls, short enough to
#: keep the suite quick. The bounded loop wakes about ten times a second.
_OBSERVE_SECONDS = 0.4


class _CountingQueue:
    """An always-empty queue that records how often the loop asks it for work.

    Implements BOTH shapes on purpose: with `get_nowait` present, the
    pre-#17355 loop runs unmodified against this fixture, so the spin is
    measured rather than asserted from the source.
    """

    def __init__(self) -> None:
        self.calls = 0

    def get(self, timeout=None):
        self.calls += 1
        if timeout is None:
            # What a real blocking get() does when nothing is ever queued: it
            # does not come back. Modelled so the blocking-fix mutation can be
            # run against this same fixture rather than described in a comment.
            time.sleep(5)
        else:
            time.sleep(timeout)
        raise queue.Empty

    def get_nowait(self):
        self.calls += 1
        raise queue.Empty

    def put(self, item):
        return None


@pytest.fixture
def idle_pty():
    """A PTY whose loop can run without a real terminal behind it."""
    pty = SimplePTY(session_id="write-loop-17355")
    pty.input_queue = _CountingQueue()
    pty.master_fd = 1  # never written to: the queue never yields an item
    pty.running = True
    yield pty
    pty.running = False


def _run_loop(pty) -> threading.Thread:
    thread = threading.Thread(target=pty._write_loop, daemon=True)
    thread.start()
    return thread


def test_an_idle_write_loop_does_not_spin(idle_pty):
    """The defect, measured: a spin makes thousands of calls in a fraction of a second."""
    thread = _run_loop(idle_pty)
    time.sleep(_OBSERVE_SECONDS)
    calls = idle_pty.input_queue.calls
    idle_pty.running = False
    thread.join(timeout=2.0)

    assert calls < 50, (
        f"the write loop asked the queue {calls} times in {_OBSERVE_SECONDS}s -- it is spinning. "
        "An idle session burns a core per live terminal when this loop does not wait."
    )
    assert calls > 0, "the loop never asked the queue at all; the fixture is not exercising it"


def test_the_loop_stops_when_running_goes_false_without_a_sentinel(idle_pty):
    """The path a plain blocking `get()` would park on forever.

    cleanup() normally puts a None sentinel, but its put is inside a swallowing
    try/except and `running = False` is already set by then -- and an abandoned
    session never calls cleanup() at all. No sentinel is sent here on purpose.
    """
    thread = _run_loop(idle_pty)
    time.sleep(0.05)

    idle_pty.running = False  # deliberately NO sentinel
    thread.join(timeout=2.0)

    assert not thread.is_alive(), (
        "the write loop did not notice running=False without a sentinel. A blocking get() "
        "parks here, and nothing else in the codebase wakes it (#17355)."
    )


def test_the_loop_stops_when_the_descriptor_is_invalidated(idle_pty):
    """The loop's SECOND condition, which no sentinel ever signals."""
    thread = _run_loop(idle_pty)
    time.sleep(0.05)

    idle_pty.master_fd = None  # running stays True
    thread.join(timeout=2.0)

    assert not thread.is_alive(), (
        "the write loop did not notice master_fd going None. `while self.running and "
        "self.master_fd is not None` has two terms and a parked thread re-checks neither."
    )
