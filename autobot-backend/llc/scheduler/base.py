# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PollLoopScheduler — shared poll-loop scaffolding for LLC schedulers (GH#9842).

Provides start/stop/is_running lifecycle management and the ``_loop`` coroutine
that drives periodic execution.  Subclasses implement only ``_tick()`` — the
per-poll unit of work.

Error handling contract:
  - ``asyncio.CancelledError`` is re-raised, never swallowed, so the task ends
    as *cancelled* and every awaiting caller is released immediately.
  - All other exceptions are caught, logged via ``logger.exception()``, and the
    loop continues after the sleep.  This matches BudgetWatchdog, LivenessMonitor,
    and SessionCheckpointer exactly.
  - The inter-poll wait always runs, even when an exception occurs.

Shutdown contract (#13085):
  - The inter-poll wait is an ``asyncio.Event`` wait bounded by the poll
    interval, NOT a bare ``asyncio.sleep(poll_interval)``.  A bare sleep made
    shutdown latency equal to a whole poll interval (300 s for BudgetWatchdog,
    a 6-hour cadence elsewhere) whenever the cancellation never reached the
    sleep — the loop would keep the event loop alive for a full interval after
    ``stop()`` had already been called.
  - ``_tick()`` runs third-party async DB/Redis code that can consume a
    ``CancelledError`` and re-raise its own error type.  The loop therefore
    re-checks ``asyncio.current_task().cancelling()`` after a tick failure and
    honours the pending cancellation instead of starting another poll interval.
  - ``stop()`` stays synchronous (fire-and-forget) for existing callers;
    ``aclose()`` is the awaitable drain that shutdown paths must use.
  - That drain is bounded (#13203).  A tick can absorb the cancellation and
    park again, so an unbounded drain would trade a re-armed poll interval for
    a graceful shutdown that never finishes at all.

stop() semantics:
  - Sets ``_running = False`` and signals the stop event first.
  - Cancels the task if it exists and is not already done.
  - Does NOT await the task — use ``aclose()`` when the caller needs the task
    to be fully finished before it proceeds.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def honour_pending_cancellation() -> None:
    """Re-raise a cancellation that the surrounding ``except`` arm masked (#13085).

    SQLAlchemy/asyncpg/redis-py all catch ``BaseException`` internally and
    surface their own error type, so a ``CancelledError`` delivered into an
    awaited call can reach an ``except Exception`` arm as, say, an
    ``InterfaceError``.  ``Task.cancelling()`` still records the pending cancel,
    so a periodic loop must honour it here rather than starting another poll
    interval — that masking is what let a cancelled background loop keep an
    event loop alive for a whole interval (300 s, or 6 h for the community
    clusterer) after shutdown had already asked it to stop.

    Call this once per iteration of any ``while``-loop that sleeps between
    iterations — not only from its ``except Exception`` arm (#13203).  A tick
    that catches the driver's error itself returns *normally*, so a guard
    reached only on failure never runs on that path.  It is a no-op when no
    cancel is pending.
    """
    current = asyncio.current_task()
    if current is not None and current.cancelling():
        raise asyncio.CancelledError from None


class PollLoopScheduler:
    """Base class for asyncio poll-loop schedulers.

    Subclasses must:
      - Call ``super().__init__(poll_interval)`` (or assign ``self._poll_interval``
        directly before calling ``start()``).
      - Implement ``async def _tick(self) -> None`` with the per-poll logic.
      - Use their own module-level ``logger`` for per-tick log messages — the
        base class only logs lifecycle events using its own logger.

    The ``_task_name`` class variable controls the asyncio task name and defaults
    to the concrete class name.  Override at the class level to keep the exact
    task names that existed before extraction.
    """

    _task_name: str = ""  # set per subclass; falls back to class name if empty

    def __init__(self, poll_interval: float) -> None:
        self._poll_interval = poll_interval
        self._running: bool = False
        self._task: Optional[asyncio.Task[None]] = None
        # Signalled by stop(); makes the inter-poll wait end immediately instead
        # of running out the full poll interval (#13085).  asyncio.Event binds
        # no event loop at construction, so building a scheduler outside a
        # running loop stays valid.
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        """True if the polling task is running and not yet done."""
        return self._running and self._task is not None and not self._task.done()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the background polling loop (idempotent).

        Returns True when the task was created by this call, False on a
        redundant start — so subclasses can log "started" exactly once.
        """
        if self._running:
            return False
        self._running = True
        self._stop_event.clear()
        task_name = self._task_name or type(self).__name__
        self._task = asyncio.create_task(self._loop(), name=task_name)
        return True

    def stop(self) -> None:
        """Stop the background polling loop (synchronous, fire-and-forget).

        Sets ``_running = False``, signals the stop event so an in-progress
        inter-poll wait ends at once, and cancels the task.  Does not await
        the task — callers that need the task fully finished before they
        continue must use :meth:`aclose`.
        """
        self._running = False
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()

    async def aclose(self, timeout: float = 5.0) -> None:
        """Stop the loop and await the task's exit — the shutdown drain (#13085).

        ``stop()`` only *requests* cancellation.  Without this drain the poll
        task can still be mid-``_tick()`` (holding an open AsyncSession) when
        the caller tears down the database engine and the event loop, which
        leaves the interval sleep to be paid by whoever closes the loop.
        Idempotent, and safe on a scheduler that was never started.

        The drain is bounded (#13203).  ``_tick()`` drives drivers that catch
        ``BaseException`` while unwinding, so a tick can consume the
        cancellation and park again — a cancel surfacing as an ``InterfaceError``
        whose handler then awaits ``session.rollback()`` on a dead connection
        never returns.  Shutdown awaits ``cleanup_services()`` straight from
        the lifespan generator, so an unbounded drain there skips every later
        teardown step and turns a clean restart into a kill.  On timeout the
        stuck task is left behind and shutdown proceeds, which is exactly how
        the fire-and-forget ``stop()`` behaved before the drain existed.

        ``asyncio.shield`` is load-bearing, not decorative: ``wait_for``
        cancels the awaitable it is waiting on, and cancelling a bare
        ``gather()`` merely re-cancels the child and keeps waiting for it — so
        an unshielded drain still blocks forever on a tick that masks every
        cancellation.  Shielding lets the timeout fire regardless.
        """
        self.stop()
        task = self._task
        if task is None:
            return
        drain = asyncio.gather(task, return_exceptions=True)
        try:
            await asyncio.wait_for(asyncio.shield(drain), timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "%s: poll task did not drain within %.1fs; continuing shutdown without it",
                type(self).__name__,
                timeout,
            )

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Drive periodic calls to ``_tick()``.

        Catches and logs all exceptions from ``_tick()`` so that a single
        failing tick does not kill the loop.  ``asyncio.CancelledError`` is
        re-raised so the task ends as cancelled.  The inter-poll wait always
        runs after a tick (or after an exception) and ends early on ``stop()``.

        ``honour_pending_cancellation()`` runs once per iteration rather than
        only after a tick failure (#13203).  Every concrete ``_tick()`` catches
        its own errors and returns normally, so on the dominant path a masked
        cancellation never reaches the ``except Exception`` arm below — a guard
        placed only there never fires and the loop re-arms a whole interval.

        A failure in the inter-poll wait ends the loop instead of escaping the
        task unretrieved (#13203).  The wait is the loop's only pacing and such
        a failure is permanent for the instance — an ``asyncio.Event`` reused
        under a second event loop raises ``RuntimeError`` on every ``wait()`` —
        so continuing would spin the CPU with no delay between ticks.
        """
        try:
            while self._running:
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Attribute tick failures to the subclass's module logger so
                    # per-module log-level filtering keeps working as it did
                    # before the extraction; the base logger only carries
                    # lifecycle events.
                    logging.getLogger(type(self).__module__).exception("%s._tick() failed", type(self).__name__)
                honour_pending_cancellation()
                try:
                    await self._wait_between_polls()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("%s: inter-poll wait failed, stopping the loop", type(self).__name__)
                    break
        finally:
            # Identity-guarded so an outgoing task that has not yet processed
            # its cancellation cannot clear the flag of a loop that stop()/
            # start() has already replaced in the meantime (#13203).
            if self._task is asyncio.current_task():
                self._running = False

    async def _wait_between_polls(self) -> None:
        """Wait one poll interval, returning as soon as ``stop()`` is signalled."""
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
        except asyncio.TimeoutError:
            pass  # interval elapsed with no stop request — run the next tick

    # ------------------------------------------------------------------
    # Hook for subclasses
    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        """Per-poll unit of work.  Subclasses must override this method."""
        raise NotImplementedError(f"{type(self).__name__} must implement _tick()")
