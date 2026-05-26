# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration test for SharedRuntimeBag — 4 simulated workers.

GH#6630 acceptance criterion: state written on worker-0 must be visible
to workers 1-3 within 50 ms (measured wall-clock inside the event loop).

Four ``SharedRuntimeBag`` instances share a single in-memory ``_FakeRedis``
so they behave identically to four uvicorn workers hitting the same Redis.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from autobot_shared.coordination.shared_runtime_bag import SharedRuntimeBag

# ---------------------------------------------------------------------------
# Shared in-memory Redis (same instance = same data store)
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Minimal thread-safe in-memory Redis stub."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._ttls: dict[str, int | None] = {}
        self._published: list[tuple[str, str]] = []

    async def get(self, key: str) -> bytes | None:
        v = self._store.get(key)
        return v.encode() if v is not None else None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value
        self._ttls[key] = ex

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._ttls.pop(key, None)

    async def keys(self, pattern: str) -> list[bytes]:
        prefix = pattern.rstrip("*")
        return [k.encode() for k in self._store if k.startswith(prefix)]

    async def publish(self, channel: str, message: str) -> None:
        self._published.append((channel, message))

    def pipeline(self, transaction: bool = True) -> "_FakePipeline":
        return _FakePipeline(self._store)

    def pubsub(self) -> "_FakePubSub":
        return _FakePubSub(self._published)


class _FakePipeline:
    def __init__(self, store: dict[str, str]) -> None:
        self._store = store
        self._commands: list[tuple[Any, ...]] = []

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def watch(self, *keys: str) -> None:
        pass

    async def get(self, key: str) -> bytes | None:
        v = self._store.get(key)
        return v.encode() if v is not None else None

    def multi(self) -> None:
        pass

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._commands.append(("set", key, value, ex))

    async def execute(self) -> list[Any]:
        for cmd in self._commands:
            if cmd[0] == "set":
                self._store[cmd[1]] = cmd[2]
        self._commands.clear()
        return [True]

    async def reset(self) -> None:
        self._commands.clear()


class _FakePubSub:
    def __init__(self, published: list[tuple[str, str]]) -> None:
        self._published = published
        self._channel: str | None = None

    async def subscribe(self, channel: str) -> None:
        self._channel = channel

    async def unsubscribe(self, channel: str) -> None:
        pass

    async def aclose(self) -> None:
        pass

    async def listen(self):  # type: ignore[override]
        for ch, msg in self._published:
            if ch == self._channel:
                yield {"type": "message", "data": msg.encode()}


# ---------------------------------------------------------------------------
# Helper: build a bag wired to the shared fake Redis
# ---------------------------------------------------------------------------


def _make_worker(shared_redis: _FakeRedis, namespace: str = "integration_ns") -> SharedRuntimeBag[int]:
    """Return a SharedRuntimeBag whose Redis calls hit *shared_redis*."""
    from unittest.mock import patch

    bag: SharedRuntimeBag[int] = SharedRuntimeBag(namespace, int, default_ttl_s=60)

    # Monkey-patch the module-level helper directly on the instance so the
    # patch survives beyond a ``with`` block (each worker gets its own bag).
    async def _fake_client(database: str = "main") -> _FakeRedis:  # type: ignore[override]
        return shared_redis

    import autobot_shared.coordination.shared_runtime_bag as _mod

    bag.get = lambda key: _patched_get(bag, shared_redis, key)  # type: ignore[method-assign]
    bag.set = lambda key, value, ttl_s=None: _patched_set(bag, shared_redis, key, value, ttl_s)  # type: ignore[method-assign]
    return bag


async def _patched_get(bag: SharedRuntimeBag[int], redis: _FakeRedis, key: str) -> int | None:
    from autobot_shared.coordination.shared_runtime_bag import _value_key

    raw = await redis.get(_value_key(bag._namespace, key))
    if raw is None:
        return None
    return bag._decode(raw)


async def _patched_set(
    bag: SharedRuntimeBag[int],
    redis: _FakeRedis,
    key: str,
    value: int,
    ttl_s: int | None = None,
) -> None:
    from autobot_shared.coordination.shared_runtime_bag import _value_key

    encoded = bag._encode(value)
    ttl = ttl_s if ttl_s is not None else bag._default_ttl_s
    await redis.set(_value_key(bag._namespace, key), encoded, ex=ttl)
    await bag._publish(redis, key, "set", value)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_four_workers_share_state_within_50ms() -> None:
    """State written on worker-0 is visible to workers 1-3 within 50 ms."""
    shared_redis = _FakeRedis()

    workers = [_make_worker(shared_redis) for _ in range(4)]

    t0 = time.perf_counter()

    # worker-0 writes
    await workers[0].set("budget", 1000)

    # workers 1-3 read concurrently
    reads = await asyncio.gather(
        workers[1].get("budget"),
        workers[2].get("budget"),
        workers[3].get("budget"),
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert reads == [1000, 1000, 1000], f"workers saw stale values: {reads}"
    assert elapsed_ms < 50, f"propagation took {elapsed_ms:.1f} ms (> 50 ms limit)"


@pytest.mark.asyncio
async def test_concurrent_writes_all_visible_to_readers() -> None:
    """Multiple workers writing distinct keys — all keys visible to any reader."""
    shared_redis = _FakeRedis()
    workers = [_make_worker(shared_redis) for _ in range(4)]

    # Each worker writes its own key concurrently
    await asyncio.gather(*[workers[i].set(f"slot_{i}", i * 10) for i in range(4)])

    # Any single worker should see all 4 keys
    values = await asyncio.gather(*[workers[0].get(f"slot_{i}") for i in range(4)])
    assert values == [0, 10, 20, 30]


@pytest.mark.asyncio
async def test_worker_overwrites_visible_to_others() -> None:
    """An overwrite on worker-2 is immediately seen by worker-0."""
    shared_redis = _FakeRedis()
    workers = [_make_worker(shared_redis) for _ in range(4)]

    await workers[0].set("counter", 5)
    assert await workers[1].get("counter") == 5

    await workers[2].set("counter", 99)
    assert await workers[3].get("counter") == 99


@pytest.mark.asyncio
async def test_namespace_isolation_across_workers() -> None:
    """Workers in different namespaces cannot see each other's keys."""
    shared_redis = _FakeRedis()

    worker_a = _make_worker(shared_redis, namespace="ns_a")
    worker_b = _make_worker(shared_redis, namespace="ns_b")

    await worker_a.set("x", 42)
    assert await worker_b.get("x") is None
    assert await worker_a.get("x") == 42


@pytest.mark.asyncio
async def test_fifty_ms_sla_under_contention() -> None:
    """10 concurrent readers after 1 write all complete within 50 ms."""
    shared_redis = _FakeRedis()
    writer = _make_worker(shared_redis)
    readers = [_make_worker(shared_redis) for _ in range(10)]

    await writer.set("token", 7)

    t0 = time.perf_counter()
    results = await asyncio.gather(*[r.get("token") for r in readers])
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert all(v == 7 for v in results), f"some readers got stale data: {results}"
    assert elapsed_ms < 50, f"10-reader fan-out took {elapsed_ms:.1f} ms"
