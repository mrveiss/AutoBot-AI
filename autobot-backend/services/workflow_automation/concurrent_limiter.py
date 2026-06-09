# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Concurrent Workflow Execution Limiter.

Issue #2159: Prevents OOM by capping the number of simultaneously running
workflows and providing configurable overflow handling (reject/queue/drop-oldest).
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Deque, Dict

from autobot_shared.ssot_config import config

_ACQUIRE_TIMEOUT_SECONDS = float(config.concurrent_limiter_timeout)
_EVICTION_POLL_SECONDS = 5.0  # max time to wait for oldest entry to vacate before dropping it

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import TimingConstants

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Overflow policy
# ---------------------------------------------------------------------------


class OverflowPolicy(Enum):
    """
    Behaviour when max_concurrent workflows are already running.

    REJECT     — raise ConcurrencyLimitError immediately (HTTP 429 pattern).
    QUEUE      — hold the request in a FIFO queue until a slot opens.
    DROP_OLDEST — cancel the oldest running workflow to make room for the new one.
    """

    REJECT = "reject"
    QUEUE = "queue"
    DROP_OLDEST = "drop_oldest"


# ---------------------------------------------------------------------------
# Queued entry (used by QUEUE policy)
# ---------------------------------------------------------------------------


@dataclass
class _QueuedEntry:
    """Pending workflow waiting for a concurrency slot."""

    workflow_id: str
    ready_event: asyncio.Event = field(default_factory=asyncio.Event)


# ---------------------------------------------------------------------------
# ConcurrentWorkflowLimiter
# ---------------------------------------------------------------------------


class ConcurrentWorkflowLimiter:
    """
    Enforces a maximum number of concurrently-running workflows.

    Issue #2159: System-level guard against workflow-driven OOM.

    Three overflow policies:
    - REJECT: immediately reject excess workflows (default).
    - QUEUE: hold them in a FIFO queue.
    - DROP_OLDEST: forcibly cancel the oldest active workflow to accept the new one.

    Usage::

        limiter = ConcurrentWorkflowLimiter(max_concurrent=3)

        # Acquire a slot before starting execution
        await limiter.acquire("wf-123")

        # When workflow finishes (always in try/finally)
        await limiter.release("wf-123")
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        overflow_policy: OverflowPolicy = OverflowPolicy.REJECT,
        cancel_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._max_concurrent = max_concurrent
        self._overflow_policy = overflow_policy
        self._cancel_callback: Callable[[str], Awaitable[None]] | None = cancel_callback
        self._running: Dict[str, float] = {}  # workflow_id → start timestamp
        self._queue: Deque[_QueuedEntry] = deque()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def running_count(self) -> int:
        """Number of currently running workflows."""
        return len(self._running)

    @property
    def queued_count(self) -> int:
        """Number of workflows waiting in queue."""
        return len(self._queue)

    async def acquire(self, workflow_id: str) -> None:
        """
        Claim a concurrency slot for *workflow_id*.

        Behaviour depends on overflow_policy when capacity is full:
        - REJECT: raises ConcurrencyLimitError immediately.
        - QUEUE: awaits until a slot opens (FIFO order preserved).
        - DROP_OLDEST: cancels oldest running workflow first.
        """
        if workflow_id in self._running:
            logger.warning("ConcurrentWorkflowLimiter: workflow %s already running", workflow_id)
            return

        if self.running_count < self._max_concurrent:
            self._running[workflow_id] = time.time()
            logger.debug(
                "ConcurrentWorkflowLimiter: acquired slot for %s (%d/%d)",
                workflow_id,
                self.running_count,
                self._max_concurrent,
            )
            return

        # Capacity full — apply overflow policy
        await self._handle_overflow(workflow_id)

    async def release(self, workflow_id: str) -> None:
        """
        Release the concurrency slot held by *workflow_id*.

        If workflows are waiting in queue the next one is promoted.
        """
        if workflow_id not in self._running:
            logger.debug(
                "ConcurrentWorkflowLimiter: release called for unknown workflow %s",
                workflow_id,
            )
            return

        del self._running[workflow_id]
        logger.debug(
            "ConcurrentWorkflowLimiter: released slot for %s (%d/%d remaining)",
            workflow_id,
            self.running_count,
            self._max_concurrent,
        )
        await self._promote_queued()

    def status(self) -> Dict:
        """Return a snapshot of limiter state for monitoring/health endpoints."""
        return {
            "max_concurrent": self._max_concurrent,
            "running_count": self.running_count,
            "queued_count": self.queued_count,
            "overflow_policy": self._overflow_policy.value,
            "running_workflow_ids": list(self._running.keys()),
        }

    def register_cancel_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """
        Register the async callback invoked when DROP_OLDEST evicts a workflow.

        Issue #2573: Allows late binding of the cancellation handler so the
        limiter can be constructed before the manager is available.

        Args:
            callback: ``async def callback(workflow_id: str) -> None`` — must
                stop the given workflow and eventually call ``release()``.
        """
        self._cancel_callback = callback
        logger.debug("ConcurrentWorkflowLimiter: cancel callback registered")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _handle_overflow(self, workflow_id: str) -> None:
        """Dispatch to the configured overflow handler."""
        if self._overflow_policy == OverflowPolicy.REJECT:
            self._reject(workflow_id)
        elif self._overflow_policy == OverflowPolicy.QUEUE:
            await self._enqueue(workflow_id)
        elif self._overflow_policy == OverflowPolicy.DROP_OLDEST:
            await self._drop_oldest_and_acquire(workflow_id)

    def _reject(self, workflow_id: str) -> None:
        """Raise immediately — caller should return HTTP 429."""
        logger.warning(
            "ConcurrentWorkflowLimiter: rejecting workflow %s (limit=%d)",
            workflow_id,
            self._max_concurrent,
        )
        raise ConcurrencyLimitError(workflow_id, self._max_concurrent)

    async def _enqueue(self, workflow_id: str) -> None:
        """Block until a slot opens, then claim it.

        Timeout controlled by AUTOBOT_CONCURRENT_LIMITER_TIMEOUT env var
        (default 300 s).
        """
        entry = _QueuedEntry(workflow_id=workflow_id)
        self._queue.append(entry)
        logger.info(
            "ConcurrentWorkflowLimiter: workflow %s queued (position %d)",
            workflow_id,
            len(self._queue),
        )
        try:
            await asyncio.wait_for(entry.ready_event.wait(), timeout=_ACQUIRE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self._queue.remove(entry)
            raise ConcurrencyLimitError(workflow_id, self._max_concurrent)
        self._running[workflow_id] = time.time()

    async def _drop_oldest_and_acquire(self, workflow_id: str) -> None:
        """Cancel the oldest running workflow then claim its slot.

        Issue #2573: Requires a cancellation callback registered via
        ``register_cancel_callback`` or the *cancel_callback* constructor
        parameter.  The callback is responsible for stopping the evicted
        workflow; ``release()`` will be called by the normal workflow teardown
        path, freeing the slot.

        Raises:
            ConcurrencyLimitError: If no cancel callback has been registered.
        """
        if self._cancel_callback is None:
            raise ConcurrencyLimitError(workflow_id, self._max_concurrent)

        oldest_id = self._find_oldest_workflow_id()
        if oldest_id is None:
            # Edge case: slot became free between the capacity check and here.
            self._running[workflow_id] = time.time()
            return

        logger.warning(
            "ConcurrentWorkflowLimiter: DROP_OLDEST evicting %s to make room for %s",
            oldest_id,
            workflow_id,
        )
        await self._cancel_callback(oldest_id)

        # The callback must ultimately call release(), which removes oldest_id
        # from _running.  Poll briefly (up to 5 s) to confirm the slot opened.
        deadline = time.monotonic() + _EVICTION_POLL_SECONDS
        while oldest_id in self._running and time.monotonic() < deadline:
            await asyncio.sleep(TimingConstants.STREAMING_CHUNK_DELAY)

        if oldest_id in self._running:
            logger.error(
                "ConcurrentWorkflowLimiter: evicted workflow %s still running after " "5 s; forcing slot removal",
                oldest_id,
            )
            del self._running[oldest_id]

        self._running[workflow_id] = time.time()
        logger.info(
            "ConcurrentWorkflowLimiter: DROP_OLDEST complete — %s now running (%d/%d)",
            workflow_id,
            self.running_count,
            self._max_concurrent,
        )

    def _find_oldest_workflow_id(self) -> str | None:
        """Return the workflow_id with the earliest start timestamp, or None."""
        if not self._running:
            return None
        return min(self._running, key=lambda wid: self._running[wid])

    async def _promote_queued(self) -> None:
        """Wake the next waiting workflow if there is capacity.

        Only promote one entry per available slot to avoid over-promotion
        (the awakened coroutine adds itself to _running asynchronously).
        """
        if self._queue and self.running_count < self._max_concurrent:
            entry = self._queue.popleft()
            entry.ready_event.set()


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class ConcurrencyLimitError(Exception):
    """Raised when max_concurrent is reached and the workflow is rejected.

    This occurs when the policy is REJECT, or when DROP_OLDEST is configured
    but no cancel callback has been registered (Issue #2573).
    """

    def __init__(self, workflow_id: str, limit: int) -> None:
        self.workflow_id = workflow_id
        self.limit = limit
        super().__init__(f"Concurrency limit {limit} reached — workflow '{workflow_id}' rejected")


# ---------------------------------------------------------------------------
# Module-level singleton (shared across all routes in one process)
# ---------------------------------------------------------------------------

_limiter: ConcurrentWorkflowLimiter | None = None


def get_concurrent_limiter(
    max_concurrent: int = 3,
    overflow_policy: OverflowPolicy = OverflowPolicy.REJECT,
    cancel_callback: Callable[[str], Awaitable[None]] | None = None,
) -> ConcurrentWorkflowLimiter:
    """
    Return the process-level ConcurrentWorkflowLimiter, creating it on first call.

    Issue #2159: Singleton so all routes share the same concurrency counter.
    Issue #2573: *cancel_callback* is forwarded on construction only (first call).
    For late binding use ``limiter.register_cancel_callback(cb)`` instead.
    Parameters are only used on first call (when the singleton is created).
    """
    global _limiter
    if _limiter is None:
        _limiter = ConcurrentWorkflowLimiter(
            max_concurrent=max_concurrent,
            overflow_policy=overflow_policy,
            cancel_callback=cancel_callback,
        )
    return _limiter
