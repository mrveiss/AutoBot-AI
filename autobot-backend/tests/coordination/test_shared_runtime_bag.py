# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for SharedRuntimeBag — Redis-backed cross-worker constraint envelope.

Issue #6630: Tests cover get/set, CAS conflict + retry, TTL expiry, and
pub/sub fanout, using a fake in-memory Redis to avoid real network deps.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.coordination.shared_runtime_bag import (
    ChangeEvent,
    SharedRuntimeBag,
    _changes_channel,
    _value_key,
)


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


class _FakePipeline:
    """Minimal async context manager simulating aioredis pipeline with WATCH."""

    def __init__(self, store: dict, fail_once: bool = False) -> None:
        self._store = store
        self._fail_once = fail_once
        self._failed = False
        self._commands: list[tuple[str, Any]] = []
        self._watched: list[str] = []
        self._in_multi = False

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def watch(self, *keys: str) -> None:
        self._watched.extend(keys)

    async def get(self, key: str) -> bytes | None:
        v = self._store.get(key)
        return v.encode() if isinstance(v, str) else v

    def multi(self) -> None:
        self._in_multi = True

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._commands.append(("set", key, value, ex))

    async def execute(self) -> list[Any]:
        from redis.exceptions import WatchError

        if self._fail_once and not self._failed:
            self._failed = True
            raise WatchError()
        results = []
        for cmd in self._commands:
            if cmd[0] == "set":
                self._store[cmd[1]] = cmd[2]
            results.append(True)
        self._commands.clear()
        return results

    async def reset(self) -> None:
        self._commands.clear()
        self._in_multi = False


class _FakeRedis:
    """In-memory Redis stub covering get/set/delete/keys/publish and pipeline."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._published: list[tuple[str, str]] = []
        self._ttls: dict[str, int | None] = {}

    async def get(self, key: str) -> bytes | None:
        v = self._store.get(key)
        return v.encode() if isinstance(v, str) else None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value
        self._ttls[key] = ex

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._ttls.pop(key, None)

    async def keys(self, pattern: str) -> list[bytes]:
        # Simple prefix matching (strips the trailing * glob)
        prefix = pattern.rstrip("*")
        return [k.encode() for k in self._store if k.startswith(prefix)]

    async def publish(self, channel: str, message: str) -> None:
        self._published.append((channel, message))

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self._store)

    def pipeline_fail_once(self) -> _FakePipeline:
        return _FakePipeline(self._store, fail_once=True)

    def pubsub(self) -> "_FakePubSub":
        return _FakePubSub(self._published)


class _FakePubSub:
    """Yields pre-seeded messages from _published list."""

    def __init__(self, published: list[tuple[str, str]]) -> None:
        self._published = published
        self._channel: str | None = None

    async def subscribe(self, channel: str) -> None:
        self._channel = channel

    async def unsubscribe(self, channel: str) -> None:
        pass

    async def aclose(self) -> None:
        pass

    async def listen(self) -> AsyncIterator[dict]:
        for ch, msg in self._published:
            if ch == self._channel:
                yield {"type": "message", "data": msg.encode()}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis() -> _FakeRedis:
    return _FakeRedis()


@pytest.fixture
def bag(fake_redis: _FakeRedis) -> SharedRuntimeBag[int]:
    b: SharedRuntimeBag[int] = SharedRuntimeBag("test_ns", int, default_ttl_s=60)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        yield b


# ---------------------------------------------------------------------------
# get / set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_none_when_absent(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        assert await bag.get("missing") is None


@pytest.mark.asyncio
async def test_set_and_get_roundtrip(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        await bag.set("counter", 42)
        assert await bag.get("counter") == 42


@pytest.mark.asyncio
async def test_set_stores_with_ttl(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int, default_ttl_s=300)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        await bag.set("k", 1)
        assert fake_redis._ttls[_value_key("ns", "k")] == 300


@pytest.mark.asyncio
async def test_set_accepts_custom_ttl(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        await bag.set("k", 5, ttl_s=30)
        assert fake_redis._ttls[_value_key("ns", "k")] == 30


@pytest.mark.asyncio
async def test_set_publishes_change_event(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        await bag.set("k", 99)
    assert len(fake_redis._published) == 1
    ch, msg = fake_redis._published[0]
    assert ch == _changes_channel("ns")
    payload = json.loads(msg)
    assert payload["key"] == "k"
    assert payload["operation"] == "set"
    assert payload["value"] == 99


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_key(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        await bag.set("k", 1)
        await bag.delete("k")
        assert await bag.get("k") is None


@pytest.mark.asyncio
async def test_delete_publishes_change_event(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        await bag.set("k", 1)
        fake_redis._published.clear()
        await bag.delete("k")
    assert len(fake_redis._published) == 1
    payload = json.loads(fake_redis._published[0][1])
    assert payload["operation"] == "delete"
    assert payload["value"] is None


# ---------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keys_returns_bare_names(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        await bag.set("a", 1)
        await bag.set("b", 2)
        result = await bag.keys()
    assert sorted(result) == ["a", "b"]


# ---------------------------------------------------------------------------
# CAS / update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_increments_value(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        await bag.set("counter", 10)
        result = await bag.update("counter", lambda v: v + 5)
    assert result == 15


@pytest.mark.asyncio
async def test_update_raises_on_missing_key(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        with pytest.raises(KeyError):
            await bag.update("absent", lambda v: v)


@pytest.mark.asyncio
async def test_update_retries_on_watch_error(fake_redis: _FakeRedis) -> None:
    """Verify that a WatchError on the first attempt triggers a retry."""
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    # Seed the key directly in fake_redis store (bypassing publish)
    fake_redis._store[_value_key("ns", "counter")] = "10"

    call_count = 0
    original_pipeline = _FakePipeline

    class _FailOncePipeline(_FakePipeline):
        def __init__(self, store: dict) -> None:
            super().__init__(store, fail_once=True)

    # Patch pipeline to fail on first execute
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        # Override pipeline to inject a fail-once pipe
        fake_redis._pipeline_factory = _FailOncePipeline
        original_pipe = fake_redis.pipeline

        def _patched_pipeline(transaction: bool = True) -> _FakePipeline:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _FailOncePipeline(fake_redis._store)
            return _FakePipeline(fake_redis._store)

        fake_redis.pipeline = _patched_pipeline
        result = await bag.update("counter", lambda v: v + 1, retries=3)
    assert result == 11


@pytest.mark.asyncio
async def test_update_raises_after_max_retries(fake_redis: _FakeRedis) -> None:
    from redis.exceptions import WatchError

    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    fake_redis._store[_value_key("ns", "counter")] = "5"

    class _AlwaysFailPipeline(_FakePipeline):
        async def execute(self) -> list[Any]:
            raise WatchError()

    def _always_fail(transaction: bool = True) -> _FakePipeline:
        return _AlwaysFailPipeline(fake_redis._store, fail_once=False)

    fake_redis.pipeline = _always_fail
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        with pytest.raises(RuntimeError, match="CAS failed"):
            await bag.update("counter", lambda v: v + 1, retries=2)


# ---------------------------------------------------------------------------
# pub/sub subscribe_changes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_changes_yields_set_events(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    channel = _changes_channel("ns")
    # Pre-seed a published message
    payload = json.dumps(
        {"key": "k", "operation": "set", "value": 7, "timestamp": "2026-01-01T00:00:00"}
    )
    fake_redis._published.append((channel, payload))

    events = []
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        async for event in bag.subscribe_changes():
            events.append(event)
            break  # stop after first event

    assert len(events) == 1
    assert events[0].key == "k"
    assert events[0].operation == "set"
    assert events[0].value == 7


@pytest.mark.asyncio
async def test_subscribe_changes_yields_delete_events(fake_redis: _FakeRedis) -> None:
    bag: SharedRuntimeBag[int] = SharedRuntimeBag("ns", int)
    channel = _changes_channel("ns")
    payload = json.dumps(
        {"key": "k", "operation": "delete", "value": None, "timestamp": "2026-01-01T00:00:00"}
    )
    fake_redis._published.append((channel, payload))

    events = []
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        async for event in bag.subscribe_changes():
            events.append(event)
            break

    assert len(events) == 1
    assert events[0].operation == "delete"
    assert events[0].value is None


# ---------------------------------------------------------------------------
# Pydantic model as value_type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pydantic_model_roundtrip(fake_redis: _FakeRedis) -> None:
    from pydantic import BaseModel

    class Budget(BaseModel):
        limit: int
        used: int

    bag: SharedRuntimeBag[Budget] = SharedRuntimeBag("budgets", Budget)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        await bag.set("agent-1", Budget(limit=1000, used=250))
        result = await bag.get("agent-1")
    assert isinstance(result, Budget)
    assert result.limit == 1000
    assert result.used == 250


# ---------------------------------------------------------------------------
# Namespace isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_namespace_isolation(fake_redis: _FakeRedis) -> None:
    """Two bags with different namespaces must not share keys."""
    bag_a: SharedRuntimeBag[int] = SharedRuntimeBag("alpha", int)
    bag_b: SharedRuntimeBag[int] = SharedRuntimeBag("beta", int)
    with patch(
        "autobot_shared.coordination.shared_runtime_bag.get_async_redis_client",
        return_value=fake_redis,
    ):
        await bag_a.set("x", 1)
        assert await bag_b.get("x") is None
