# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The notification router's single-instance lock has an owner, and every started worker keeps contesting it (#21456).

The lock used to hold the constant ``"1"``, ``stop()`` deleted whatever was there, and nothing ever took the lock
again once it was lost or skipped at boot. Each worker now runs a hold loop: it renews the lock while it holds it
and contests it while it does not, and routing runs exactly while the lock is held. Tests drive ``_hold_step``
directly (the loop's body) against a real Lua engine (fakeredis[lua]); only two use the loop itself.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from autobot_shared.redis_utils import MS_PER_SECOND
from llc.notifications import router as router_module
from llc.notifications.router import _ROUTER_LOCK_KEY, _ROUTER_LOCK_TTL, LLCNotificationRouter

_SHORT_PTTL_MS = 5000  # well under a renewal, so an extension is visible
_FOREIGN = "other-host-1:deadbeef"


@pytest.fixture
def redis(monkeypatch):  # noqa: ANN001, ANN201
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(router_module, "get_async_redis_client", AsyncMock(return_value=client))
    return client


class _Publisher:
    async def publish(self, **_kwargs):  # noqa: ANN003, ANN201
        return None


async def _idle() -> None:
    await asyncio.sleep(30)


@asynccontextmanager
async def _worker():  # noqa: ANN201
    """A router whose subscribe loop idles and whose hold loop is far away; stopped on exit, so nothing leaks."""
    router = LLCNotificationRouter(publisher=_Publisher())
    router._subscribe_loop = _idle  # type: ignore[method-assign]
    try:
        yield router
    finally:
        await router.stop()


def _routing(router: LLCNotificationRouter) -> bool:
    return router._task is not None and not router._task.done()


def _token(router: LLCNotificationRouter) -> str:
    return router._lease.worker_id


async def test_a_worker_that_skipped_at_boot_takes_over_once_the_holders_key_is_gone(redis) -> None:  # noqa: ANN001
    """Before: nothing ever retried after the boot-time skip, so the cluster had no router until a restart."""
    async with _worker() as holder, _worker() as skipped:
        await holder.start()
        await skipped.start()
        assert _routing(holder) and not _routing(skipped)
        await redis.delete(_ROUTER_LOCK_KEY)
        await skipped._hold_step()
        assert _routing(skipped)
        assert await redis.get(_ROUTER_LOCK_KEY) == _token(skipped)


async def test_a_worker_that_lost_the_lock_stops_routing_and_later_takes_it_again(redis) -> None:  # noqa: ANN001
    async with _worker() as router:
        await router.start()
        await redis.set(_ROUTER_LOCK_KEY, _FOREIGN)
        await router._hold_step()
        assert not _routing(router)
        assert await redis.get(_ROUTER_LOCK_KEY) == _FOREIGN
        await redis.delete(_ROUTER_LOCK_KEY)
        await router._hold_step()
        assert _routing(router)
        assert await redis.get(_ROUTER_LOCK_KEY) == _token(router)


async def test_two_workers_never_both_hold_the_lock(redis) -> None:  # noqa: ANN001
    async with _worker() as first, _worker() as second:
        await first.start()
        await second.start()
        for _ in range(3):
            await first._hold_step()
            await second._hold_step()
            assert _routing(first) != _routing(second)
        await first.stop()
        await second._hold_step()
        assert _routing(second) and not _routing(first)


async def test_the_hold_loop_itself_renews_and_takes_over(redis, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(router_module, "_HOLD_INTERVAL", 0.05)
    async with _worker() as router:
        await router.start()
        await redis.delete(_ROUTER_LOCK_KEY)
        await asyncio.sleep(0.5)
        assert _routing(router)
        assert await redis.get(_ROUTER_LOCK_KEY) == _token(router)


async def test_the_lock_is_held_with_the_configured_lifetime_and_renewed_by_its_owner(redis) -> None:  # noqa: ANN001
    async with _worker() as router:
        await router.start()
        await redis.pexpire(_ROUTER_LOCK_KEY, _SHORT_PTTL_MS)
        await router._hold_step()
        assert _SHORT_PTTL_MS < await redis.pttl(_ROUTER_LOCK_KEY) <= _ROUTER_LOCK_TTL * MS_PER_SECOND


async def test_stop_while_holding_releases_the_lock_and_leaks_no_task(redis) -> None:  # noqa: ANN001
    async with _worker() as router:
        await router.start()
        routing, hold = router._task, router._hold_task
        await router.stop()
        assert routing.done() and hold.done()
        assert await redis.get(_ROUTER_LOCK_KEY) is None


async def test_stop_while_not_holding_leaves_the_holders_key_and_leaks_no_task(redis) -> None:  # noqa: ANN001
    async with _worker() as holder, _worker() as skipped:
        await holder.start()
        await skipped.start()
        hold = skipped._hold_task
        await skipped.stop()
        assert hold.done() and not _routing(skipped)
        assert await redis.get(_ROUTER_LOCK_KEY) == _token(holder)


async def test_stop_after_the_lock_was_lost_keeps_the_new_holders_key(redis) -> None:  # noqa: ANN001
    async with _worker() as router:
        await router.start()
        await redis.set(_ROUTER_LOCK_KEY, _FOREIGN)
        await router._hold_step()
        await router.stop()
        assert await redis.get(_ROUTER_LOCK_KEY) == _FOREIGN


async def test_an_old_constant_lock_is_not_taken_or_deleted_and_is_taken_after_it_lapses(redis) -> None:  # noqa: ANN001
    """Rolling restart: an old worker's lock holds ``1`` and old code never renews it."""
    await redis.set(_ROUTER_LOCK_KEY, "1")
    async with _worker() as router:
        await router.start()
        assert not _routing(router)
        await router.stop()
        assert await redis.get(_ROUTER_LOCK_KEY) == "1"
        await redis.delete(_ROUTER_LOCK_KEY)
        await router.start()
        assert _routing(router)


async def test_a_lock_an_old_worker_deleted_is_taken_again_by_its_owner(redis) -> None:  # noqa: ANN001
    """Old code's stop() deleted the key unconditionally; the new worker notices and takes it again."""
    async with _worker() as router:
        await router.start()
        await redis.delete(_ROUTER_LOCK_KEY)
        await router._hold_step()
        assert not _routing(router)
        await router._hold_step()
        assert _routing(router)


async def test_a_redis_error_keeps_routing_until_a_whole_ttl_passes_without_a_confirmation(  # noqa: ANN001
    redis, monkeypatch
) -> None:
    async with _worker() as router:
        await router.start()
        monkeypatch.setattr(router_module, "get_async_redis_client", AsyncMock(side_effect=ConnectionError("down")))
        await router._hold_step()
        assert _routing(router)
        router._last_held -= _ROUTER_LOCK_TTL
        await router._hold_step()
        assert not _routing(router)


async def test_a_redis_call_that_hangs_is_bounded_by_the_hold_interval(redis, monkeypatch) -> None:  # noqa: ANN001
    async def hang(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        await asyncio.sleep(30)

    monkeypatch.setattr(router_module, "_HOLD_INTERVAL", 0.05)
    monkeypatch.setattr(redis, "set", hang)
    async with _worker() as router:
        await asyncio.wait_for(router.start(), timeout=5)
        assert not _routing(router)


async def test_no_redis_does_not_route_without_the_lock(monkeypatch) -> None:  # noqa: ANN001
    """Routing needs Redis; an unlocked worker would route beside the holder once Redis returned."""
    monkeypatch.setattr(router_module, "get_async_redis_client", AsyncMock(return_value=None))
    async with _worker() as router:
        await router.start()
        assert not _routing(router)


async def test_a_redis_error_in_stop_is_logged_and_does_not_raise(redis, monkeypatch, caplog) -> None:  # noqa: ANN001
    async with _worker() as router:
        await router.start()
        monkeypatch.setattr(router_module, "get_async_redis_client", AsyncMock(side_effect=ConnectionError("down")))
        with caplog.at_level(logging.WARNING):
            await router.stop()
        assert "Failed to release leader lease" in caplog.text
