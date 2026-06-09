# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bounded-concurrency gather primitive.

See docs/developer/PRIMITIVES.md for the full inventory and #5059/#5060
for the extraction-first methodology.
"""

import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


async def bounded_gather(
    coros: list[Awaitable[T]],
    max_parallel: int,
    *,
    return_exceptions: bool = True,
) -> list[T | BaseException]:
    """Run up to max_parallel coroutines concurrently; return all results.

    Wraps each coroutine in a semaphore-guarded task and delegates to
    asyncio.gather. Centralizes the bounded-concurrency pattern so fixes
    (timeouts, cancellation behavior, metrics) land in one place.
    """
    sem = asyncio.Semaphore(max_parallel)

    async def _guarded(coro: Awaitable[T]) -> T:
        async with sem:
            return await coro

    return list(await asyncio.gather(*(_guarded(c) for c in coros), return_exceptions=return_exceptions))
