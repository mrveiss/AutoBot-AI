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


class SingleFlightCache(Generic[T]):
    """Callers during a refresh get the last result; only before any result exists do they wait.

    A TTL alone does not bound the cost: until the first refresh finishes, every caller starts its own.
    """

    def __init__(self, ttl_seconds: float, refresh_timeout: float, fallback: T) -> None:
        self._ttl = ttl_seconds
        self._refresh_timeout = refresh_timeout
        self._fallback = fallback
        self._generation = 0
        self._lock = asyncio.Lock()
        self._value: T | None = None
        self._has_value = False
        self._refreshed_at: float | None = None

    def _fresh(self) -> bool:
        return self._refreshed_at is not None and time.monotonic() - self._refreshed_at < self._ttl

    def invalidate(self) -> None:
        """The next caller refreshes; callers during that refresh still get the last result."""
        self._refreshed_at = None
        self._generation += 1

    async def get(self, refresh: Callable[[], Awaitable[T]], force: bool = False) -> T:
        """The cached value, refreshed if stale. ``force`` waits its turn and always refreshes."""
        if not force and (self._fresh() or (self._lock.locked() and self._has_value)):
            return self._value
        async with self._lock:
            if not force and self._fresh():  # a refresh finished while this caller waited
                return self._value
            started, generation = time.monotonic(), self._generation
            try:
                value = await asyncio.wait_for(refresh(), self._refresh_timeout)
            except TimeoutError:
                # A hung refresh must not hold every waiter forever. Not marked fresh: the next caller retries.
                logger.warning("refresh exceeded %ss; serving the last result", self._refresh_timeout)
                return self._value if self._has_value else self._fallback
            self._value, self._has_value = value, True
            if generation == self._generation:  # invalidated meanwhile: this result may predate the change
                self._refreshed_at = started
            return value
