# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for PollLoopScheduler base class (GH#9842)."""

import asyncio
import logging

import pytest

from llc.scheduler.base import PollLoopScheduler

# ---------------------------------------------------------------------------
# Test double — concrete subclass with a controllable tick
# ---------------------------------------------------------------------------


# #13113: these sync tests drive coroutines with asyncio.run(). The legacy
# asyncio.get_event_loop().run_until_complete() raised "There is no current event
# loop" whenever the test ran before any async test on its xdist worker, because
# pytest-asyncio's auto mode owns the loop lifecycle and leaves none set.


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


class _MaskingCancelScheduler(PollLoopScheduler):
    """Subclass whose tick masks CancelledError behind a driver-style error.

    Models what SQLAlchemy/asyncpg/redis-py do: they catch BaseException while
    unwinding and surface their own exception type, so the cancellation lands in
    ``_loop``'s ``except Exception`` arm instead of its ``except CancelledError``
    arm (#13085).
    """

    _task_name = "test-masking-cancel-scheduler"

    def __init__(self, poll_interval: float = 9999.0) -> None:
        super().__init__(poll_interval)
        self.tick_count = 0
        self.tick_entered = asyncio.Event()

    async def _tick(self) -> None:
        self.tick_count += 1
        self.tick_entered.set()
        try:
            await asyncio.sleep(9999.0)
        except asyncio.CancelledError:
            raise RuntimeError("driver masked the cancellation") from None


class _SwallowingCancelScheduler(PollLoopScheduler):
    """Subclass whose tick masks a CancelledError and then returns *normally*.

    This is the dominant shape in production and the one #13085's first fix
    missed (#13203): every concrete scheduler wraps its own work in
    ``except Exception`` — ``liveness_monitor._check_once``,
    ``liveness_monitor._cancel_adapter``, ``session_checkpointer._check_once``,
    ``budget_watchdog._hard_stop_agent`` — so a cancellation the driver
    surfaced as its own error type is consumed *inside* ``_tick`` and never
    reaches ``_loop``'s ``except Exception`` arm at all.  A guard placed only
    in that arm therefore never fires, and the loop re-arms a full interval.

    ``_MaskingCancelScheduler`` above re-raises, so it only ever exercised the
    already-covered path.
    """

    _task_name = "test-swallowing-cancel-scheduler"

    def __init__(self, poll_interval: float = 9999.0) -> None:
        super().__init__(poll_interval)
        self.tick_count = 0
        self.tick_entered = asyncio.Event()

    async def _tick(self) -> None:
        self.tick_count += 1
        self.tick_entered.set()
        try:
            await asyncio.sleep(9999.0)
        except asyncio.CancelledError:
            pass  # driver consumed it; the tick reports success to _loop


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

    asyncio.run(_run())


def test_start_idempotent() -> None:
    """Calling start() twice does not create a second task."""

    async def _run() -> None:
        sched = _CountingScheduler()
        sched.start()
        task_first = sched._task
        sched.start()  # second call — must be a no-op
        assert sched._task is task_first
        sched.stop()

    asyncio.run(_run())


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

    asyncio.run(_run())


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

    asyncio.run(_run())


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

    asyncio.run(_run())


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

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tick exception survival
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tick_exception_does_not_kill_loop(caplog: pytest.LogCaptureFixture) -> None:
    """When _tick() raises, the loop continues (exception is caught and logged)."""
    sched = _ErrorScheduler(poll_interval=0.0)
    with caplog.at_level(logging.ERROR, logger=_ErrorScheduler.__module__):
        sched.start()
        # Allow a couple of iterations — if the loop were killed by the first
        # exception, tick_count would stay at 1.
        await asyncio.sleep(0.05)
        sched.stop()
        await asyncio.sleep(0)  # let cancellation propagate

    assert sched.tick_count >= 2, "loop must survive tick exceptions"
    assert any("_tick() failed" in r.message for r in caplog.records), "exception must be logged"


@pytest.mark.asyncio
async def test_tick_exception_logs_class_name(caplog: pytest.LogCaptureFixture) -> None:
    """Tick failures log the concrete class name under the subclass's module logger."""
    sched = _ErrorScheduler(poll_interval=0.0)
    with caplog.at_level(logging.ERROR, logger=_ErrorScheduler.__module__):
        sched.start()
        await asyncio.sleep(0.05)
        sched.stop()
        await asyncio.sleep(0)

    failures = [r for r in caplog.records if "_tick() failed" in r.message]
    assert failures, "exception must be logged"
    # Attributed to the subclass's module logger, naming the concrete class
    assert failures[0].name == _ErrorScheduler.__module__
    assert "_ErrorScheduler" in failures[0].message


# ---------------------------------------------------------------------------
# Cancellation (CancelledError breaks the loop cleanly)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancellation_breaks_loop_cleanly() -> None:
    """A bare cancel ends the loop and leaves the scheduler restartable (#13203).

    ``_loop`` re-raises ``CancelledError`` rather than catching it, so the
    cancellation is delivered to whoever collects the task instead of vanishing.
    Its ``finally`` then clears ``_running``: before #13203 a bare
    ``task.cancel()`` left ``_running=True`` on a finished task, which made
    ``is_running`` False *and* made ``start()`` refuse to create a replacement —
    the scheduler was silently un-restartable.

    The yield before the cancel is required, not incidental: a coroutine
    cancelled before its first step never enters its body, so no ``finally``
    can run.  ``stop()``/``aclose()`` clear ``_running`` themselves, so the only
    path that depends on the ``finally`` is a bare cancel of a loop that is
    already running — which is the case exercised here.
    """
    sched = _CountingScheduler(poll_interval=9999.0)
    sched.start()
    assert sched._task is not None
    task = sched._task
    await asyncio.sleep(0)  # let _loop enter its body and reach the inter-poll wait
    task.cancel()
    # Collected by the caller — must not surface as an unhandled exception.
    results = await asyncio.gather(task, return_exceptions=True)

    assert isinstance(results[0], asyncio.CancelledError)
    assert task.cancelled()
    assert sched._running is False, "_loop must clear _running on exit"
    assert sched.start() is True, "a cancelled scheduler must be restartable"
    await sched.aclose()


@pytest.mark.asyncio
async def test_cancellation_marks_the_task_cancelled() -> None:
    """_loop re-raises CancelledError so the task ends in the cancelled state.

    Swallowing it made the task finish "successfully", which hides a shutdown
    that never actually completed from anything inspecting the task (#13085).
    """
    sched = _CountingScheduler(poll_interval=9999.0)
    sched.start()
    assert sched._task is not None
    await asyncio.sleep(0)  # let the loop reach its inter-poll wait
    sched._task.cancel()
    await asyncio.gather(sched._task, return_exceptions=True)

    assert sched._task.cancelled()


# ---------------------------------------------------------------------------
# Shutdown latency (#13085) — stop() must not cost a whole poll interval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_event_ends_the_interval_wait_immediately() -> None:
    """stop() releases an in-flight inter-poll wait without task cancellation.

    Isolated from cancel() on purpose: no task is started, so the only thing
    that can end the wait is the stop event.  A bare asyncio.sleep() would keep
    the waiter pending for the full 9999 s interval.
    """
    sched = _CountingScheduler(poll_interval=9999.0)
    waiter = asyncio.create_task(sched._wait_between_polls())
    await asyncio.sleep(0)  # let the waiter register on the event

    sched.stop()  # no task exists → only the stop event can release the waiter

    await asyncio.wait_for(waiter, timeout=1.0)


@pytest.mark.asyncio
async def test_masked_cancellation_does_not_start_another_interval() -> None:
    """A tick that masks CancelledError must not buy the loop a fresh interval.

    Real drivers (SQLAlchemy/asyncpg/redis-py) catch BaseException and re-raise
    their own error type, so the cancellation reaches ``except Exception``.
    Before #13085 the loop then slept out a whole poll interval — 300 s for
    BudgetWatchdog — keeping the event loop alive long after shutdown.
    """
    sched = _MaskingCancelScheduler(poll_interval=9999.0)
    sched.start()
    assert sched._task is not None
    await asyncio.wait_for(sched.tick_entered.wait(), timeout=1.0)

    sched._task.cancel()

    # Must settle promptly; a re-armed 9999 s wait would blow the timeout.
    await asyncio.wait_for(asyncio.gather(sched._task, return_exceptions=True), timeout=1.0)
    assert sched._task.done()
    assert sched.tick_count == 1, "the loop must not have started a second tick"


@pytest.mark.asyncio
async def test_swallowed_cancellation_does_not_start_another_interval() -> None:
    """A tick that *swallows* the masked cancel must not buy a fresh interval.

    #13085's first fix ran the guard only in ``_loop``'s ``except Exception``
    arm, so it fired only when the masked error escaped ``_tick()``.  Every
    concrete scheduler consumes its own errors and returns normally, so on the
    real path the guard never ran and the loop re-armed a whole poll interval —
    60 s (LivenessMonitor), 300 s (BudgetWatchdog), 30 s (SessionCheckpointer).
    Running it once per iteration is what closes that gap (#13203).
    """
    sched = _SwallowingCancelScheduler(poll_interval=9999.0)
    sched.start()
    assert sched._task is not None
    await asyncio.wait_for(sched.tick_entered.wait(), timeout=1.0)

    sched._task.cancel()  # not via stop(): _stop_event stays clear, _running stays True

    # A re-armed 9999 s inter-poll wait would blow this timeout.
    await asyncio.wait_for(asyncio.gather(sched._task, return_exceptions=True), timeout=1.0)
    assert sched._task.cancelled(), "the honoured cancel must end the task as cancelled"
    assert sched.tick_count == 1, "the loop must not have started a second tick"


# ---------------------------------------------------------------------------
# aclose() — the awaitable shutdown drain (#13085)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aclose_awaits_the_task_to_completion() -> None:
    """aclose() returns only once the poll task has actually finished."""
    sched = _CountingScheduler(poll_interval=9999.0)
    sched.start()
    task = sched._task
    assert task is not None

    await asyncio.wait_for(sched.aclose(), timeout=1.0)

    assert task.done()
    assert not sched.is_running


@pytest.mark.asyncio
async def test_aclose_is_safe_before_start_and_idempotent() -> None:
    """aclose() on a never-started scheduler is a no-op, and repeats are safe."""
    sched = _CountingScheduler(poll_interval=9999.0)
    await sched.aclose()  # never started — must not raise

    sched.start()
    await sched.aclose()
    await sched.aclose()  # second drain — must not raise
    assert not sched.is_running


class _UncancellableScheduler(PollLoopScheduler):
    """Tick that masks *every* cancellation, so the task can never be drained.

    Models the concrete hang in #13203: a cancel surfaces as an ``InterfaceError``
    and the handler awaits ``session.rollback()`` on a dead connection with no
    command timeout, which never returns.
    """

    _task_name = "test-uncancellable-scheduler"

    def __init__(self, poll_interval: float = 9999.0) -> None:
        super().__init__(poll_interval)
        self.tick_entered = asyncio.Event()
        # Cleared by the test once it has its evidence, so the task is always
        # reapable — a permanently uncancellable task would wedge the suite's
        # own loop teardown, which is the very failure mode under test.
        self.mask_cancellation = True

    async def _tick(self) -> None:
        self.tick_entered.set()
        while True:
            try:
                await asyncio.sleep(9999.0)
            except asyncio.CancelledError:
                if not self.mask_cancellation:
                    raise
                continue  # driver consumed it and retried on the dead connection


@pytest.mark.asyncio
async def test_aclose_is_bounded_when_the_task_cannot_be_drained(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """aclose() must give up rather than wedge graceful shutdown forever (#13203).

    cleanup_services() is awaited straight from the lifespan generator and
    uvicorn awaits that with no timeout of its own, so an unbounded drain here
    skips every remaining teardown step (database close, Redis close) and turns
    a clean restart into a kill.  Timing out degrades to how the fire-and-forget
    stop() behaved before the drain existed.
    """
    sched = _UncancellableScheduler(poll_interval=9999.0)
    sched.start()
    task = sched._task
    assert task is not None
    await asyncio.wait_for(sched.tick_entered.wait(), timeout=1.0)

    with caplog.at_level(logging.WARNING, logger=PollLoopScheduler.__module__):
        # Bounded by aclose()'s own timeout; the outer guard only proves the
        # test itself cannot hang the suite if that bound ever regresses.
        await asyncio.wait_for(sched.aclose(timeout=0.2), timeout=3.0)

    assert not task.done(), "the stuck task is deliberately left behind"
    assert any("did not drain" in r.message for r in caplog.records), "the give-up must be logged"

    # Reap it now that the evidence is collected.
    sched.mask_cancellation = False
    task.cancel()
    await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1.0)


@pytest.mark.asyncio
async def test_restart_after_aclose_clears_the_stop_event() -> None:
    """start() re-arms the stop event so a restarted loop is not born stopped."""
    sched = _CountingScheduler(poll_interval=0.0)
    sched.start()
    await sched.aclose()

    sched.start()
    await asyncio.sleep(0.05)
    ticks_after_restart = sched.tick_count
    await sched.aclose()

    assert ticks_after_restart >= 2, "restarted loop must keep ticking"


# ---------------------------------------------------------------------------
# Default _tick raises NotImplementedError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_tick_raises_not_implemented() -> None:
    """Calling _tick() directly on the base raises NotImplementedError."""
    sched = PollLoopScheduler(poll_interval=9999.0)
    with pytest.raises(NotImplementedError):
        await sched._tick()
