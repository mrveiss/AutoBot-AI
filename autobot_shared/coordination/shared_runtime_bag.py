# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SharedRuntimeBag — Redis-backed cross-worker constraint envelope.

Issue #6630: Generalises the A2A Redis pattern (#4502) into a reusable
primitive so any subsystem needing cross-worker state uses it instead of
a module-level singleton.

Redis key layout:
  runtime_bag:{namespace}:{key}      — JSON-serialised value (with TTL)
  runtime_bag:{namespace}:changes    — pub/sub channel for change events

Serialisation: json via pydantic TypeAdapter (handles both Pydantic models
and plain Python types transparently).

Locking: optimistic via Redis WATCH/MULTI/EXEC; CAS retries on conflict.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import TypeAdapter
from redis.exceptions import WatchError

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

T = TypeVar("T")

_KEY_VALUE = "runtime_bag:{namespace}:{key}"
_KEY_CHANGES = "runtime_bag:{namespace}:changes"

_DEFAULT_TTL_S = 3600


@dataclass
class ChangeEvent:
    """Emitted on every set/delete operation for a namespace."""

    key: str
    operation: str  # "set" | "delete"
    value: Any | None  # raw decoded value, None on delete
    timestamp: str = field(default_factory=lambda: now_utc().isoformat())


def _value_key(namespace: str, key: str) -> str:
    return f"runtime_bag:{namespace}:{key}"


def _changes_channel(namespace: str) -> str:
    return f"runtime_bag:{namespace}:changes"


class SharedRuntimeBag(Generic[T]):
    """Redis-backed dict with TTL, optimistic locking, and pub/sub change notifications.

    Safe for use across multiple uvicorn workers — state written on worker A
    is immediately visible to workers B, C, D.

    Usage::

        bag: SharedRuntimeBag[int] = SharedRuntimeBag("agent_budget", int)
        await bag.set("agent-123", 1000)
        remaining = await bag.get("agent-123")

        # Atomic decrement via CAS
        async def decrement(v: int) -> int:
            return v - 1

        new_val = await bag.update("agent-123", decrement)

        # Stream changes from any worker
        async for event in bag.subscribe_changes():
            print(event.key, event.operation, event.value)
    """

    def __init__(
        self,
        namespace: str,
        value_type: type[T],
        default_ttl_s: int = _DEFAULT_TTL_S,
    ) -> None:
        self._namespace = namespace
        self._default_ttl_s = default_ttl_s
        self._adapter: TypeAdapter[T] = TypeAdapter(value_type)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def _encode(self, value: T) -> str:
        return self._adapter.dump_json(value).decode()

    def _decode(self, raw: bytes | str) -> T:
        if isinstance(raw, bytes):
            raw = raw.decode()
        return self._adapter.validate_json(raw)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, key: str) -> T | None:
        """Return the value stored under *key*, or None if absent / expired."""
        redis = await get_async_redis_client(database="main")
        if redis is None:
            raise RuntimeError(f"SharedRuntimeBag: Redis client unavailable (namespace='{self._namespace}')")
        raw = await redis.get(_value_key(self._namespace, key))
        if raw is None:
            return None
        return self._decode(raw)

    async def set(
        self,
        key: str,
        value: T,
        ttl_s: int | None = None,
    ) -> None:
        """Persist *value* under *key* with an optional TTL (defaults to namespace TTL)."""
        redis = await get_async_redis_client(database="main")
        if redis is None:
            raise RuntimeError(f"SharedRuntimeBag: Redis client unavailable (namespace='{self._namespace}')")
        encoded = self._encode(value)
        ttl = ttl_s if ttl_s is not None else self._default_ttl_s
        await redis.set(_value_key(self._namespace, key), encoded, ex=ttl)
        await self._publish(redis, key, "set", value)

    async def update(
        self,
        key: str,
        mutator: Callable[[T], T],
        retries: int = 3,
        ttl_s: int | None = None,
    ) -> T:
        """Atomically read-modify-write *key* using optimistic locking (CAS).

        Fetches the current value, applies *mutator*, and writes the result
        inside a WATCH/MULTI/EXEC block.  On concurrent modification the
        transaction is retried up to *retries* times.

        Raises:
            KeyError: if the key does not exist.
            RuntimeError: if all CAS retries are exhausted.
        """
        redis = await get_async_redis_client(database="main")
        if redis is None:
            raise RuntimeError(f"SharedRuntimeBag: Redis client unavailable (namespace='{self._namespace}')")
        rkey = _value_key(self._namespace, key)
        ttl = ttl_s if ttl_s is not None else self._default_ttl_s

        for attempt in range(retries + 1):
            async with redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(rkey)
                    raw = await pipe.get(rkey)
                    if raw is None:
                        await pipe.reset()
                        raise KeyError(key)
                    current = self._decode(raw)
                    updated = mutator(current)
                    encoded = self._encode(updated)
                    pipe.multi()
                    pipe.set(rkey, encoded, ex=ttl)
                    await pipe.execute()
                    await self._publish(redis, key, "set", updated)
                    return updated
                except Exception as exc:
                    if not isinstance(exc, WatchError):
                        raise
                    if attempt == retries:
                        raise RuntimeError(
                            f"SharedRuntimeBag.update: CAS failed after {retries} retries"
                            f" for key '{key}' in namespace '{self._namespace}'"
                        ) from exc
                    logger.debug(
                        "SharedRuntimeBag CAS conflict on '%s/%s', retry %d/%d",
                        self._namespace,
                        key,
                        attempt + 1,
                        retries,
                    )

        raise RuntimeError("unreachable")  # pragma: no cover

    async def delete(self, key: str) -> None:
        """Remove *key* from the bag and publish a delete change event."""
        redis = await get_async_redis_client(database="main")
        if redis is None:
            raise RuntimeError(f"SharedRuntimeBag: Redis client unavailable (namespace='{self._namespace}')")
        await redis.delete(_value_key(self._namespace, key))
        await self._publish(redis, key, "delete", None)

    async def keys(self, pattern: str = "*") -> list[str]:
        """Return all keys in this namespace matching *pattern*.

        The returned keys are the bare key names (namespace prefix is stripped).
        """
        redis = await get_async_redis_client(database="main")
        if redis is None:
            raise RuntimeError(f"SharedRuntimeBag: Redis client unavailable (namespace='{self._namespace}')")
        prefix = f"runtime_bag:{self._namespace}:"
        full_pattern = f"{prefix}{pattern}"
        raw_keys = await redis.keys(full_pattern)
        return [(k.decode() if isinstance(k, bytes) else k).removeprefix(prefix) for k in raw_keys]

    async def subscribe_changes(self) -> AsyncIterator[ChangeEvent]:
        """Yield ChangeEvent for every set/delete in this namespace.

        Opens a dedicated Redis pub/sub connection.  The iterator runs until
        the calling coroutine is cancelled or the generator is closed.

        Usage::

            async for event in bag.subscribe_changes():
                if event.operation == "set":
                    handle_update(event.key, event.value)
        """
        redis = await get_async_redis_client(database="main")
        if redis is None:
            raise RuntimeError(f"SharedRuntimeBag: Redis client unavailable (namespace='{self._namespace}')")
        channel = _changes_channel(self._namespace)
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    payload = json.loads(data)
                    raw_value = payload.get("value")
                    value: T | None = None
                    if raw_value is not None:
                        value = self._adapter.validate_python(raw_value)
                    yield ChangeEvent(
                        key=payload["key"],
                        operation=payload["operation"],
                        value=value,
                        timestamp=payload.get("timestamp", ""),
                    )
                except Exception as exc:
                    logger.warning(
                        "SharedRuntimeBag: failed to parse change event in '%s': %s",
                        self._namespace,
                        exc,
                    )
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()  # type: ignore[attr-defined]  # GH#7105

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _publish(
        self,
        redis: Any,
        key: str,
        operation: str,
        value: T | None,
    ) -> None:
        """Publish a change event to the namespace pub/sub channel."""
        try:
            channel = _changes_channel(self._namespace)
            raw_value = None
            if value is not None:
                raw_value = json.loads(self._encode(value))
            payload = json.dumps(
                {
                    "key": key,
                    "operation": operation,
                    "value": raw_value,
                    "timestamp": now_utc().isoformat(),
                }
            )
            await redis.publish(channel, payload)
        except Exception as exc:
            # pub/sub is best-effort — never let it break callers
            logger.warning("SharedRuntimeBag: publish failed in '%s': %s", self._namespace, exc)
