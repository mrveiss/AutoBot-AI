# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#7469: regression tests for run_or_schedule defensive re-entrancy helper."""

from __future__ import annotations

import asyncio
import threading

import pytest

from autobot_shared.async_compat import run_or_schedule

# ---------------------------------------------------------------------------
# Sync-entry path: no event loop running
# ---------------------------------------------------------------------------


class TestSyncEntry:
    def test_returns_coro_result_when_no_loop_running(self):
        async def echo(value: int) -> int:
            return value * 2

        assert run_or_schedule(echo(21)) == 42

    def test_propagates_exception_from_coro(self) -> None:
        async def failing() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            run_or_schedule(failing())

    def test_runs_io_bound_coro(self):
        # Confirm asyncio.run actually drives the loop (sleep would hang
        # if there was no scheduler).
        async def sleep_and_return() -> str:
            await asyncio.sleep(0.001)
            return "ok"

        assert run_or_schedule(sleep_and_return()) == "ok"


# ---------------------------------------------------------------------------
# In-loop path: caller is inside a running event loop
# ---------------------------------------------------------------------------


class TestInLoopEntry:
    @pytest.mark.asyncio
    async def test_returns_coro_result_from_async_context(self):
        # The original re-entrancy crash: asyncio.run(coro) from inside
        # an async function raises RuntimeError. run_or_schedule must
        # detour through a thread pool and succeed.
        async def echo(value: int) -> int:
            return value + 100

        # Calling the SYNC helper from an ASYNC test function exercises
        # the "running loop detected" branch. We can't await it (it's
        # sync) — that's the point of the helper.
        result = run_or_schedule(echo(1))
        assert result == 101

    @pytest.mark.asyncio
    async def test_propagates_exception_through_threadpool(self) -> None:
        async def failing() -> None:
            raise RuntimeError("inner")

        with pytest.raises(RuntimeError, match="inner"):
            run_or_schedule(failing())

    @pytest.mark.asyncio
    async def test_threadpool_path_runs_io_bound_coro(self):
        async def sleep_and_return() -> str:
            await asyncio.sleep(0.001)
            return "from-thread"

        result = run_or_schedule(sleep_and_return())
        assert result == "from-thread"


# ---------------------------------------------------------------------------
# Concurrency: multiple sync entries in parallel threads
# ---------------------------------------------------------------------------


class TestConcurrent:
    def test_independent_calls_in_separate_threads_dont_interfere(self):
        # Each thread has no running loop → each takes the sync-entry
        # path. Confirm they all complete cleanly without sharing state.
        results: list[int] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        async def compute(i: int) -> int:
            await asyncio.sleep(0.001)
            return i * i

        def worker(i: int) -> None:
            try:
                value = run_or_schedule(compute(i))
                with lock:
                    results.append(value)
            except BaseException as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert sorted(results) == [0, 1, 4, 9, 16, 25, 36, 49]
