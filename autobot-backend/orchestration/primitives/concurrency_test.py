# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for bounded_gather primitive."""

import asyncio

import pytest

from orchestration.primitives.concurrency import bounded_gather


@pytest.mark.asyncio
async def test_bounded_gather_respects_max_parallel() -> None:
    """At most max_parallel coroutines should run concurrently."""
    max_parallel = 2
    concurrency_counter = 0
    peak_concurrency = 0

    async def task(_: int) -> int:
        nonlocal concurrency_counter, peak_concurrency
        concurrency_counter += 1
        peak_concurrency = max(peak_concurrency, concurrency_counter)
        await asyncio.sleep(0.01)
        concurrency_counter -= 1
        return _

    coros = [task(i) for i in range(10)]
    await bounded_gather(coros, max_parallel)

    assert peak_concurrency <= max_parallel


@pytest.mark.asyncio
async def test_bounded_gather_returns_results_in_order() -> None:
    """Results must be ordered by input position regardless of completion order."""
    delays = [0.05, 0.01, 0.03, 0.00, 0.02]

    async def task(idx: int, delay: float) -> int:
        await asyncio.sleep(delay)
        return idx

    coros = [task(i, d) for i, d in enumerate(delays)]
    results = await bounded_gather(coros, max_parallel=len(delays))

    assert results == list(range(len(delays)))


@pytest.mark.asyncio
async def test_bounded_gather_captures_exceptions_by_default() -> None:
    """With default return_exceptions=True, exceptions are returned in-place."""
    sentinel = ValueError("boom")

    async def good() -> str:
        return "ok"

    async def bad() -> str:
        raise sentinel

    results = await bounded_gather([good(), bad(), good()], max_parallel=3)

    assert results[0] == "ok"
    assert results[1] is sentinel
    assert results[2] == "ok"


@pytest.mark.asyncio
async def test_bounded_gather_empty_list() -> None:
    """Empty input should return an empty list without error."""
    results = await bounded_gather([], max_parallel=4)
    assert results == []


@pytest.mark.asyncio
async def test_bounded_gather_return_exceptions_false_propagates() -> None:
    """With return_exceptions=False, the first exception bubbles out."""

    async def good() -> str:
        return "ok"

    async def bad() -> str:
        raise RuntimeError("propagated")

    with pytest.raises(RuntimeError, match="propagated"):
        await bounded_gather([good(), bad()], max_parallel=2, return_exceptions=False)
