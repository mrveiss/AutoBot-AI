# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Concurrent Workflow Execution Limiter.

Issue #2159: Prevents OOM by capping the number of simultaneously running
workflows and providing configurable overflow handling (reject/queue/drop-oldest).
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, Optional

logger = logging.getLogger(__name__)


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
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._max_concurrent = max_concurrent
        self._overflow_policy = overflow_policy
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
            logger.warning(
                "ConcurrentWorkflowLimiter: workflow %s already running", workflow_id
            )
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
        """Block until a slot opens, then claim it. Timeout after 300s."""
        entry = _QueuedEntry(workflow_id=workflow_id)
        self._queue.append(entry)
        logger.info(
            "ConcurrentWorkflowLimiter: workflow %s queued (position %d)",
            workflow_id,
            len(self._queue),
        )
        try:
            await asyncio.wait_for(entry.ready_event.wait(), timeout=300.0)
        except asyncio.TimeoutError:
            self._queue.remove(entry)
            raise ConcurrencyLimitError(workflow_id, self._max_concurrent)
        self._running[workflow_id] = time.time()

    async def _drop_oldest_and_acquire(self, workflow_id: str) -> None:
        """Cancel the oldest running workflow and claim its slot.

        Requires a cancellation callback to actually stop the evicted workflow.
        Until that callback mechanism exists, this policy is not safe to use.
        """
        raise NotImplementedError(
            "DROP_OLDEST policy requires a cancellation callback to stop the evicted "
            "workflow. Use REJECT or QUEUE until this is implemented."
        )

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
    """Raised when max_concurrent is reached and policy is REJECT."""

    def __init__(self, workflow_id: str, limit: int) -> None:
        self.workflow_id = workflow_id
        self.limit = limit
        super().__init__(
            f"Concurrency limit {limit} reached — workflow '{workflow_id}' rejected"
        )


# ---------------------------------------------------------------------------
# Module-level singleton (shared across all routes in one process)
# ---------------------------------------------------------------------------

_limiter: Optional[ConcurrentWorkflowLimiter] = None


def get_concurrent_limiter(
    max_concurrent: int = 3,
    overflow_policy: OverflowPolicy = OverflowPolicy.REJECT,
) -> ConcurrentWorkflowLimiter:
    """
    Return the process-level ConcurrentWorkflowLimiter, creating it on first call.

    Issue #2159: Singleton so all routes share the same concurrency counter.
    Parameters are only used on first call (when the singleton is created).
    """
    global _limiter
    if _limiter is None:
        _limiter = ConcurrentWorkflowLimiter(
            max_concurrent=max_concurrent,
            overflow_policy=overflow_policy,
        )
    return _limiter
