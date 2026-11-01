# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A TTL cache whose expensive refresh runs one at a time (#20250)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class RefreshUnavailable(Exception):
    """No answer within the limit. A caller must treat the answer as unknown, never as empty."""


class SingleFlightCache(Generic[T]):
    """One refresh in flight, whoever asks; callers during it get the last result if there is one.

    A TTL alone does not bound the cost: until the first refresh finishes, every caller starts its own.
    Every waiter shares the in-flight task, so each waits one limit at most, and a refresh past the limit
    is left running, never restarted: its thread cannot be cancelled, so a restart would add another.
    """

    def __init__(self, ttl_seconds: float, refresh_timeout: float) -> None:
        self._ttl = ttl_seconds
        self._refresh_timeout = refresh_timeout
        self._generation = 0
        self._task: asyncio.Task | None = None
        self._value: T | None = None
        self._has_value = False
        self._refreshed_at: float | None = None

    def _fresh(self) -> bool:
        return self._refreshed_at is not None and time.monotonic() - self._refreshed_at < self._ttl

    def _running(self) -> bool:
        return self._task is not None and not self._task.done()

    def invalidate(self) -> None:
        """The next caller refreshes; callers during that refresh still get the last result."""
        self._refreshed_at = None
        self._generation += 1

    async def _refresh(self, refresh: Callable[[], Awaitable[T]]) -> T:
        started, generation = time.monotonic(), self._generation
        value = await refresh()
        self._value, self._has_value = value, True
        if generation == self._generation:  # invalidated meanwhile: this result may predate the change
            self._refreshed_at = started
        return value

    async def _finished_within_limit(self) -> bool:
        done, _ = await asyncio.wait({self._task}, timeout=self._refresh_timeout)
        return bool(done)

    def _start(self, refresh: Callable[[], Awaitable[T]]) -> None:
        self._task = asyncio.create_task(self._refresh(refresh))
        # Nobody may be waiting when a refresh past the limit finally fails.
        self._task.add_done_callback(lambda task: task.cancelled() or task.exception())

    async def get(self, refresh: Callable[[], Awaitable[T]], force: bool = False) -> T:
        """The cached value, refreshed if stale. Raises RefreshUnavailable when it cannot say.

        ``force`` means a result from after this call: it waits out a running refresh, starts its own,
        and never takes an older value. A refresh's own exception reaches its waiters unchanged.
        """
        if force:
            return await self._get_forced(refresh)
        if self._fresh() or (self._running() and self._has_value):
            return self._value
        if not self._running():
            self._start(refresh)
        if await self._finished_within_limit():
            return self._task.result()
        logger.warning("refresh exceeded %ss", self._refresh_timeout)
        if self._has_value:
            return self._value
        raise RefreshUnavailable(f"no result within {self._refresh_timeout}s")

    async def get_or_unknown(self, refresh: Callable[[], Awaitable[T]], empty: T) -> tuple[T, bool]:
        """(the value, False), or (*empty*, True) when there is no answer: a reader must see which."""
        try:
            return await self.get(refresh), False
        except RefreshUnavailable:
            return empty, True

    async def _get_forced(self, refresh: Callable[[], Awaitable[T]]) -> T:
        if self._running() and not await self._finished_within_limit():
            raise RefreshUnavailable(f"a refresh is still running after {self._refresh_timeout}s")
        self._start(refresh)
        if await self._finished_within_limit():
            return self._task.result()
        raise RefreshUnavailable(f"no result within {self._refresh_timeout}s")
