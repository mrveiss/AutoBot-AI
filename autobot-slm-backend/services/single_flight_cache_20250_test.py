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


SingleFlightCache = _load().SingleFlightCache


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
    cache, refresh = SingleFlightCache(60, 30, fallback=None), _Refresh()
    callers = [asyncio.create_task(cache.get(refresh)) for _ in range(5)]
    await asyncio.sleep(0)
    refresh.release.set()
    assert await asyncio.gather(*callers) == ["v1"] * 5
    assert refresh.calls == 1


@pytest.mark.asyncio
async def test_a_caller_during_a_refresh_gets_the_last_result_without_waiting() -> None:
    cache, refresh = SingleFlightCache(60, 30, fallback=None), _Refresh()
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
    cache, refresh = SingleFlightCache(60, 30, fallback=None), _Refresh()
    refresh.release.set()
    await cache.get(refresh)
    await cache.get(refresh)
    assert refresh.calls == 1
    expired = SingleFlightCache(0, 30, fallback=None)
    await expired.get(refresh)
    await expired.get(refresh)
    assert refresh.calls == 3


@pytest.mark.asyncio
async def test_force_waits_its_turn_and_refreshes_again() -> None:
    cache, refresh = SingleFlightCache(60, 30, fallback=None), _Refresh()
    refresh.release.set()
    await cache.get(refresh)
    assert await cache.get(refresh, force=True) == "v2"


@pytest.mark.asyncio
async def test_a_failed_refresh_raises_and_the_next_caller_retries() -> None:
    cache = SingleFlightCache(60, 30, fallback=None)

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
async def test_a_hung_refresh_before_any_result_gives_the_fallback_and_frees_waiters() -> None:
    cache = SingleFlightCache(60, 0.01, fallback="nothing yet")
    results = await asyncio.wait_for(asyncio.gather(cache.get(_hangs), cache.get(_hangs)), 2)
    assert results == ["nothing yet", "nothing yet"]


@pytest.mark.asyncio
async def test_a_hung_refresh_after_a_result_gives_that_result_and_the_next_caller_retries() -> None:
    cache, refresh = SingleFlightCache(60, 0.01, fallback=None), _Refresh()
    refresh.release.set()
    assert await cache.get(refresh) == "v1"
    cache.invalidate()
    assert await asyncio.wait_for(cache.get(_hangs), 2) == "v1"
    assert await cache.get(refresh) == "v2"


@pytest.mark.asyncio
async def test_an_invalidate_during_a_refresh_is_not_overwritten_by_its_result() -> None:
    cache, refresh = SingleFlightCache(60, 30, fallback=None), _Refresh()
    running = asyncio.create_task(cache.get(refresh))
    await asyncio.sleep(0)
    cache.invalidate()
    refresh.release.set()
    assert await running == "v1"
    assert await cache.get(refresh) == "v2", "the result from before the invalidate must not read as fresh"
