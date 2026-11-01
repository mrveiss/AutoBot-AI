# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A TTL cache whose expensive refresh runs one at a time (#20250)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class SingleFlightCache(Generic[T]):
    """Callers during a refresh get the last result; only before any result exists do they wait.

    A TTL alone does not bound the cost: until the first refresh finishes, every caller starts its own.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._value: T | None = None
        self._has_value = False
        self._refreshed_at: float | None = None

    def _fresh(self) -> bool:
        return self._refreshed_at is not None and time.monotonic() - self._refreshed_at < self._ttl

    def invalidate(self) -> None:
        """The next caller refreshes; callers during that refresh still get the last result."""
        self._refreshed_at = None

    async def get(self, refresh: Callable[[], Awaitable[T]], force: bool = False) -> T:
        """The cached value, refreshed if stale. ``force`` waits its turn and always refreshes."""
        if not force and (self._fresh() or (self._lock.locked() and self._has_value)):
            return self._value
        async with self._lock:
            if not force and self._fresh():  # a refresh finished while this caller waited
                return self._value
            started = time.monotonic()
            self._value = await refresh()
            self._has_value = True
            self._refreshed_at = started
            return self._value
