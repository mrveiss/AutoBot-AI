# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The notification router's single-instance lock has an owner (#21456).

The lock used to hold the constant ``"1"`` and ``stop()`` deleted whatever was there, so a worker whose
lock had lapsed (the TTL was never renewed) deleted the lock of the worker that took over. Each test runs
against a real Lua engine (fakeredis[lua]), the way the compare-and-delete and compare-and-expire helpers
run on a real server.
"""

from __future__ import annotations

import asyncio
import logging
import time
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from llc.notifications import router as router_module
from llc.notifications.router import _ROUTER_LOCK_KEY, _ROUTER_LOCK_TTL, LLCNotificationRouter

_SHORT_TTL_MS = 5000  # well under a renewal, so an extension is visible


@pytest.fixture
def redis(monkeypatch):  # noqa: ANN001, ANN201
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(router_module, "get_async_redis_client", AsyncMock(return_value=client))
    return client


class _Publisher:
    async def publish(self, **_kwargs):  # noqa: ANN003, ANN201
        return None


def _router() -> LLCNotificationRouter:
    return LLCNotificationRouter(publisher=_Publisher())


async def _idle() -> None:
    await asyncio.sleep(30)


async def _start(router: LLCNotificationRouter) -> None:
    """Start with the subscribe loop idle and the renew tick far away; tests drive renewals themselves."""
    router._subscribe_loop = _idle  # type: ignore[method-assign]  # an instance attribute outlives start()
    await router.start()


@pytest.fixture(autouse=True)
def _no_renew_tick(monkeypatch):  # noqa: ANN001, ANN201
    monkeypatch.setattr(router_module, "_RENEW_INTERVAL", 3600)


@pytest.mark.asyncio
async def test_stop_after_another_worker_took_the_lock_keeps_it(redis) -> None:  # noqa: ANN001
    a, b = _router(), _router()
    await _start(a)
    await redis.delete(_ROUTER_LOCK_KEY)  # A's lock lapsed ...
    await _start(b)  # ... and B took over
    assert await redis.get(_ROUTER_LOCK_KEY) == b._token

    await a.stop()

    assert await redis.get(_ROUTER_LOCK_KEY) == b._token
    await b.stop()


@pytest.mark.asyncio
async def test_stop_while_holding_releases_the_lock(redis) -> None:  # noqa: ANN001
    a = _router()
    await _start(a)
    assert await redis.get(_ROUTER_LOCK_KEY) == a._token

    await a.stop()

    assert await redis.exists(_ROUTER_LOCK_KEY) == 0


@pytest.mark.asyncio
async def test_worker_that_never_acquired_deletes_nothing(redis) -> None:  # noqa: ANN001
    a, b = _router(), _router()
    await _start(a)
    await _start(b)  # lock held by A: B skips
    assert b._task is None and b._renew_task is None

    await b.stop()

    assert await redis.get(_ROUTER_LOCK_KEY) == a._token
    await a.stop()


@pytest.mark.asyncio
async def test_owner_renewal_extends_the_ttl(redis) -> None:  # noqa: ANN001
    a = _router()
    await _start(a)
    await redis.pexpire(_ROUTER_LOCK_KEY, _SHORT_TTL_MS)

    assert await a._renew_step() is True

    assert await redis.pttl(_ROUTER_LOCK_KEY) > _SHORT_TTL_MS
    assert await redis.get(_ROUTER_LOCK_KEY) == a._token
    await a.stop()


@pytest.mark.asyncio
async def test_renewal_by_a_non_owner_fails_and_extends_nothing(redis) -> None:  # noqa: ANN001
    a = _router()
    await _start(a)
    await redis.set(_ROUTER_LOCK_KEY, "someone-else", px=_SHORT_TTL_MS)

    assert await a._renew_step() is False

    assert await redis.pttl(_ROUTER_LOCK_KEY) <= _SHORT_TTL_MS
    assert await redis.get(_ROUTER_LOCK_KEY) == "someone-else"
    await a.stop()


@pytest.mark.asyncio
async def test_lost_lock_stops_routing_and_leaves_the_new_holders_key(redis, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(router_module, "_RENEW_INTERVAL", 0.01)
    a = _router()
    await _start(a)
    routing = a._task
    await redis.set(_ROUTER_LOCK_KEY, "someone-else", ex=_ROUTER_LOCK_TTL)

    await asyncio.wait([routing, a._renew_task], timeout=2)

    assert routing.cancelled() and a._renew_task.done()
    assert a._stop_event.is_set()
    await a.stop()
    assert await redis.get(_ROUTER_LOCK_KEY) == "someone-else"


@pytest.mark.asyncio
async def test_renew_error_is_retried_until_a_whole_ttl_passes(redis, monkeypatch) -> None:  # noqa: ANN001
    a = _router()
    await _start(a)
    monkeypatch.setattr(router_module, "get_async_redis_client", AsyncMock(side_effect=ConnectionError("down")))

    assert await a._renew_step() is True  # just renewed: retry next tick
    a._last_renewed = time.monotonic() - _ROUTER_LOCK_TTL - 1
    assert await a._renew_step() is False  # a whole TTL without a renewal: presumed lost
    await a.stop()


@pytest.mark.asyncio
async def test_old_style_constant_lock_is_not_deleted_by_a_new_worker(redis) -> None:  # noqa: ANN001
    await redis.set(_ROUTER_LOCK_KEY, "1", ex=_ROUTER_LOCK_TTL)  # an old worker's lock
    a = _router()
    await _start(a)  # cannot take it
    assert a._task is None  # the old lock stands and lapses on its own TTL
    await a.stop()
    assert await redis.get(_ROUTER_LOCK_KEY) == "1"


@pytest.mark.asyncio
async def test_old_worker_overwrite_is_not_deleted_by_the_new_workers_stop(redis) -> None:  # noqa: ANN001
    a = _router()
    await _start(a)
    await redis.set(_ROUTER_LOCK_KEY, "1")  # an old worker's unconditional re-take

    await a.stop()

    assert await redis.get(_ROUTER_LOCK_KEY) == "1"


@pytest.mark.asyncio
async def test_redis_error_in_stop_is_logged_and_does_not_raise(redis, monkeypatch, caplog) -> None:  # noqa: ANN001
    a = _router()
    await _start(a)
    monkeypatch.setattr(router_module, "get_async_redis_client", AsyncMock(side_effect=ConnectionError("down")))

    with caplog.at_level(logging.WARNING, logger=router_module.logger.name):
        await a.stop()

    record = next(r for r in caplog.records if "lock release failed" in r.getMessage())
    assert record.exc_info is not None
    assert await redis.get(_ROUTER_LOCK_KEY) == a._token  # left to its TTL
    assert 0 < await redis.pttl(_ROUTER_LOCK_KEY) <= _ROUTER_LOCK_TTL * 1000


@pytest.mark.asyncio
async def test_no_redis_still_starts_without_a_lock(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(router_module, "get_async_redis_client", AsyncMock(return_value=None))
    a = _router()
    await _start(a)
    assert a._task is not None and a._renew_task is None and a._holds_lock is False
    await a.stop()
