# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PollLoopScheduler — shared poll-loop scaffolding for LLC schedulers (GH#9842).

Provides start/stop/is_running lifecycle management and the ``_loop`` coroutine
that drives periodic execution.  Subclasses implement only ``_tick()`` — the
per-poll unit of work.

Error handling contract (preserved from the three concrete schedulers):
  - ``asyncio.CancelledError`` breaks the loop (not re-raised; task exits cleanly).
  - All other exceptions are caught, logged via ``logger.exception()``, and the
    loop continues after the sleep.  This matches BudgetWatchdog, LivenessMonitor,
    and SessionCheckpointer exactly.
  - The sleep always runs, even when an exception occurs.

stop() semantics (preserved):
  - Sets ``_running = False`` first.
  - Cancels the task if it exists and is not already done.
  - Does NOT await the task (matches all three concrete schedulers).
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


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

    @property
    def is_running(self) -> bool:
        """True if the polling task is running and not yet done."""
        return self._running and self._task is not None and not self._task.done()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background polling loop (idempotent)."""
        if self._running:
            return
        self._running = True
        task_name = self._task_name or type(self).__name__
        self._task = asyncio.create_task(self._loop(), name=task_name)

    def stop(self) -> None:
        """Stop the background polling loop.

        Sets ``_running = False`` and cancels the task.  Does not await
        the task — callers that need a clean drain must do so themselves.
        """
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Drive periodic calls to ``_tick()``.

        Catches and logs all exceptions from ``_tick()`` so that a single
        failing tick does not kill the loop.  ``asyncio.CancelledError``
        breaks the loop cleanly.  The sleep always runs after each tick
        (or after an exception), matching the original concrete schedulers.
        """
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("%s._tick() failed", type(self).__name__)
            await asyncio.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    # Hook for subclasses
    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        """Per-poll unit of work.  Subclasses must override this method."""
        raise NotImplementedError(f"{type(self).__name__} must implement _tick()")
