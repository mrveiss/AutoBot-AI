# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Concurrent callers run one refresh, not one each (#20250)."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


def _load():
    """By path, past the conftest's services stub."""
    path = Path(__file__).resolve().parent / "single_flight_cache.py"
    spec = importlib.util.spec_from_file_location("single_flight_cache_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_module = _load()
SingleFlightCache = _module.SingleFlightCache


class _Refresh:
    def __init__(self) -> None:
        self.calls = 0
        self.release = asyncio.Event()

    async def __call__(self) -> str:
        self.calls += 1
        await self.release.wait()
        return f"v{self.calls}"


@pytest.mark.asyncio
async def test_callers_before_any_result_share_one_refresh() -> None:
    cache, refresh = SingleFlightCache(60, 30), _Refresh()
    callers = [asyncio.create_task(cache.get(refresh)) for _ in range(5)]
    await asyncio.sleep(0)
    refresh.release.set()
    assert await asyncio.gather(*callers) == ["v1"] * 5
    assert refresh.calls == 1


@pytest.mark.asyncio
async def test_a_caller_during_a_refresh_gets_the_last_result_without_waiting() -> None:
    cache, refresh = SingleFlightCache(60, 30), _Refresh()
    refresh.release.set()
    await cache.get(refresh)
    cache.invalidate()
    refresh.release.clear()
    running = asyncio.create_task(cache.get(refresh))
    await asyncio.sleep(0)
    assert await asyncio.wait_for(cache.get(refresh), 1) == "v1"
    refresh.release.set()
    assert await running == "v2"
    assert refresh.calls == 2


@pytest.mark.asyncio
async def test_a_fresh_value_is_not_refreshed_and_an_expired_one_is() -> None:
    cache, refresh = SingleFlightCache(60, 30), _Refresh()
    refresh.release.set()
    await cache.get(refresh)
    await cache.get(refresh)
    assert refresh.calls == 1
    expired = SingleFlightCache(0, 30)
    await expired.get(refresh)
    await expired.get(refresh)
    assert refresh.calls == 3


@pytest.mark.asyncio
async def test_force_waits_its_turn_and_refreshes_again() -> None:
    cache, refresh = SingleFlightCache(60, 30), _Refresh()
    refresh.release.set()
    await cache.get(refresh)
    assert await cache.get(refresh, force=True) == "v2"


@pytest.mark.asyncio
async def test_a_failed_refresh_raises_and_the_next_caller_retries() -> None:
    cache = SingleFlightCache(60, 30)

    async def boom() -> str:
        raise OSError

    with pytest.raises(OSError):
        await cache.get(boom)
    refresh = _Refresh()
    refresh.release.set()
    assert await cache.get(refresh) == "v1"


async def _hangs() -> str:
    await asyncio.Event().wait()
    return "never"


@pytest.mark.asyncio
async def test_many_first_callers_share_one_refresh_and_one_limit() -> None:
    cache, calls = SingleFlightCache(60, 0.05), []

    async def hangs() -> str:
        calls.append(1)
        return await _hangs()

    started = asyncio.get_running_loop().time()
    results = await asyncio.gather(*(cache.get(hangs) for _ in range(8)), return_exceptions=True)
    assert all(isinstance(r, _module.RefreshUnavailable) for r in results)
    assert len(calls) == 1, "a refresh past the limit is never restarted"
    assert asyncio.get_running_loop().time() - started < 1, "waiters do not queue one limit each"


@pytest.mark.asyncio
async def test_a_hung_refresh_after_a_result_serves_that_result_without_starting_another() -> None:
    cache, refresh = SingleFlightCache(60, 0.01), _Refresh()
    refresh.release.set()
    assert await cache.get(refresh) == "v1"
    cache.invalidate()
    assert await asyncio.wait_for(cache.get(_hangs), 2) == "v1"
    assert await cache.get(refresh) == "v1"
    assert refresh.calls == 1


@pytest.mark.asyncio
async def test_force_never_takes_an_older_value_when_the_refresh_hangs() -> None:
    cache, refresh = SingleFlightCache(60, 0.01), _Refresh()
    refresh.release.set()
    assert await cache.get(refresh) == "v1"
    with pytest.raises(_module.RefreshUnavailable):
        await cache.get(_hangs, force=True)


@pytest.mark.asyncio
async def test_force_while_a_refresh_hangs_says_unknown_and_starts_nothing() -> None:
    cache, refresh = SingleFlightCache(60, 0.01), _Refresh()
    with pytest.raises(_module.RefreshUnavailable):
        await cache.get(_hangs)
    with pytest.raises(_module.RefreshUnavailable):
        await cache.get(refresh, force=True)
    assert refresh.calls == 0


@pytest.mark.asyncio
async def test_a_timeout_raised_inside_the_refresh_is_not_read_as_the_limit() -> None:
    cache = SingleFlightCache(60, 30)

    async def inner_timeout() -> str:
        raise TimeoutError("from the refresh itself")

    with pytest.raises(TimeoutError, match="from the refresh itself"):
        await cache.get(inner_timeout)


@pytest.mark.asyncio
async def test_an_invalidate_during_a_refresh_is_not_overwritten_by_its_result() -> None:
    cache, refresh = SingleFlightCache(60, 30), _Refresh()
    running = asyncio.create_task(cache.get(refresh))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    cache.invalidate()
    refresh.release.set()
    assert await running == "v1"
    assert await cache.get(refresh) == "v2", "the result from before the invalidate must not read as fresh"


@pytest.mark.asyncio
async def test_a_reader_can_tell_no_answer_from_an_empty_answer() -> None:
    cache = SingleFlightCache(60, 0.01)
    assert await cache.get_or_unknown(_hangs, []) == ([], True)

    async def empty() -> list:
        return []

    assert await SingleFlightCache(60, 30).get_or_unknown(empty, ["unused"]) == ([], False)


@pytest.mark.asyncio
async def test_a_stuck_refresh_reads_as_unknown_even_with_a_cached_value() -> None:
    cache, refresh = SingleFlightCache(60, 0.01), _Refresh()
    refresh.release.set()
    assert await cache.get_or_unknown(refresh, []) == ("v1", False)
    cache.invalidate()
    assert await asyncio.wait_for(cache.get_or_unknown(_hangs, []), 2) == ("v1", True)


@pytest.mark.asyncio
async def test_two_forced_callers_on_one_refresh_start_one_more_not_two() -> None:
    cache, refresh = SingleFlightCache(60, 30), _Refresh()
    first = asyncio.create_task(cache.get(refresh))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    forced = [asyncio.create_task(cache.get(refresh, force=True)) for _ in range(2)]
    await asyncio.sleep(0)
    refresh.release.set()
    await first
    assert await asyncio.gather(*forced) == ["v2", "v2"]
    assert refresh.calls == 2
