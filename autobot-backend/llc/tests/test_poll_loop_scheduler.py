# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for PollLoopScheduler base class (GH#9842)."""

import asyncio
from unittest.mock import patch

import pytest

from llc.scheduler.base import PollLoopScheduler


# ---------------------------------------------------------------------------
# Test double — concrete subclass with a controllable tick
# ---------------------------------------------------------------------------


class _CountingScheduler(PollLoopScheduler):
    """Minimal subclass that counts tick invocations."""

    _task_name = "test-counting-scheduler"

    def __init__(self, poll_interval: float = 9999.0) -> None:
        super().__init__(poll_interval)
        self.tick_count = 0

    async def _tick(self) -> None:
        self.tick_count += 1


class _ErrorScheduler(PollLoopScheduler):
    """Subclass whose tick always raises a non-Cancelled exception."""

    _task_name = "test-error-scheduler"

    def __init__(self, poll_interval: float = 9999.0) -> None:
        super().__init__(poll_interval)
        self.tick_count = 0

    async def _tick(self) -> None:
        self.tick_count += 1
        raise RuntimeError("tick exploded")


# ---------------------------------------------------------------------------
# Lifecycle: start / stop idempotency
# ---------------------------------------------------------------------------


def test_start_creates_task_and_sets_running() -> None:
    """start() creates the asyncio task and sets _running=True."""

    async def _run() -> None:
        sched = _CountingScheduler()
        assert not sched.is_running
        sched.start()
        assert sched._running is True
        assert sched._task is not None
        assert not sched._task.done()
        sched.stop()

    asyncio.get_event_loop().run_until_complete(_run())


def test_start_idempotent() -> None:
    """Calling start() twice does not create a second task."""

    async def _run() -> None:
        sched = _CountingScheduler()
        sched.start()
        task_first = sched._task
        sched.start()  # second call — must be a no-op
        assert sched._task is task_first
        sched.stop()

    asyncio.get_event_loop().run_until_complete(_run())


def test_stop_clears_running_flag_and_cancels() -> None:
    """stop() sets _running=False and cancels the task."""

    async def _run() -> None:
        sched = _CountingScheduler()
        sched.start()
        assert sched._running is True
        sched.stop()
        assert sched._running is False
        # Give the event loop a chance to deliver the cancellation
        await asyncio.sleep(0)

    asyncio.get_event_loop().run_until_complete(_run())


def test_stop_before_start_is_safe() -> None:
    """stop() on a never-started scheduler does not raise."""
    sched = _CountingScheduler()
    sched.stop()  # must not raise


def test_is_running_false_after_stop() -> None:
    """is_running is False after stop() even if the task hasn't exited yet."""

    async def _run() -> None:
        sched = _CountingScheduler()
        sched.start()
        sched.stop()
        # _running=False → is_running must be False regardless of task state
        assert not sched.is_running

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Task naming
# ---------------------------------------------------------------------------


def test_task_name_uses_class_variable() -> None:
    """The asyncio task gets the name from _task_name."""

    async def _run() -> None:
        sched = _CountingScheduler()
        sched.start()
        assert sched._task is not None
        assert sched._task.get_name() == "test-counting-scheduler"
        sched.stop()

    asyncio.get_event_loop().run_until_complete(_run())


def test_task_name_falls_back_to_class_name_when_empty() -> None:
    """When _task_name is empty the task name is the class name."""

    class _Unnamed(PollLoopScheduler):
        _task_name = ""  # empty → fall back

        async def _tick(self) -> None:
            pass

    async def _run() -> None:
        sched = _Unnamed(poll_interval=9999.0)
        sched.start()
        assert sched._task is not None
        assert sched._task.get_name() == "_Unnamed"
        sched.stop()

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Tick exception survival
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tick_exception_does_not_kill_loop() -> None:
    """When _tick() raises, the loop continues (exception is caught and logged)."""
    sched = _ErrorScheduler(poll_interval=0.0)
    with patch("llc.scheduler.base.logger") as mock_log:
        sched.start()
        # Allow a couple of iterations — if the loop were killed by the first
        # exception, tick_count would stay at 1.
        await asyncio.sleep(0.05)
        sched.stop()
        await asyncio.sleep(0)  # let cancellation propagate

    assert sched.tick_count >= 2, "loop must survive tick exceptions"
    assert mock_log.exception.called, "exception must be logged"


@pytest.mark.asyncio
async def test_tick_exception_logs_class_name() -> None:
    """The exception log message includes the concrete class name."""
    sched = _ErrorScheduler(poll_interval=0.0)
    with patch("llc.scheduler.base.logger") as mock_log:
        sched.start()
        await asyncio.sleep(0.05)
        sched.stop()
        await asyncio.sleep(0)

    # The format string contains the class name
    call_args = mock_log.exception.call_args
    assert "_ErrorScheduler" in call_args[0][0] % (call_args[0][1],)


# ---------------------------------------------------------------------------
# Cancellation (CancelledError breaks the loop cleanly)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancellation_breaks_loop_cleanly() -> None:
    """Cancelling the task does not produce an unhandled CancelledError."""
    sched = _CountingScheduler(poll_interval=9999.0)
    sched.start()
    assert sched._task is not None
    sched._task.cancel()
    # Must not raise — CancelledError is caught inside _loop
    await asyncio.gather(sched._task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Default _tick raises NotImplementedError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_tick_raises_not_implemented() -> None:
    """Calling _tick() directly on the base raises NotImplementedError."""
    sched = PollLoopScheduler(poll_interval=9999.0)
    with pytest.raises(NotImplementedError):
        await sched._tick()
