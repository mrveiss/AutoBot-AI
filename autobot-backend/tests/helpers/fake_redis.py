# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared in-memory Redis fakes for unit tests.

Classes
-------
Sync
  SyncHashFakeRedis        — hset / hgetall / delete / expire

Async
  AsyncSimpleFakeRedis     — get / set / delete  (string keys; ``_store`` dict)
  AsyncHashFakeRedis       — hset / hget / hgetall / hdel  (hash fields; ``_store`` dict)
  AsyncFullFakeRedis       — hashes + sorted sets + strings + pipeline
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class SyncHashFakeRedis:
    """Sync in-memory stub with hash + expire ops.

    Used by tests that drive synchronous Redis callers (e.g.
    WorkflowCheckpointManager in error_handler_test.py).
    ``expire_calls`` records ``(key, ttl)`` pairs so tests can assert TTLs.
    """

    def __init__(self) -> None:
        self._hashes: Dict[str, Dict[str, str]] = {}
        self.expire_calls: list = []

    def hset(self, key: str, field: str, value: str) -> None:
        """Store *field* under *key*."""
        self._hashes.setdefault(key, {})[field] = value

    def expire(self, key: str, ttl: int) -> None:
        """Record an expire() call (does not actually expire keys)."""
        self.expire_calls.append((key, ttl))

    def hgetall(self, key: str) -> Dict[str, str]:
        """Return all fields for *key* as a plain dict."""
        return dict(self._hashes.get(key, {}))

    def delete(self, key: str) -> None:
        """Remove *key* entirely."""
        self._hashes.pop(key, None)


# ---------------------------------------------------------------------------
# Async — simple string ops
# ---------------------------------------------------------------------------


class AsyncSimpleFakeRedis:
    """Async in-memory stub: get / set / delete on plain string keys.

    ``_store`` is the backing dict; tests may inspect or seed it directly.
    Suitable for services that use only the basic key-value Redis surface
    (e.g. OrgKnowledgeConfigService tests).
    """

    def __init__(self) -> None:
        self._store: Dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        """Return the value for *key*, or ``None``."""
        return self._store.get(key)

    async def set(self, key: str, value: str) -> bool:
        """Store *value* under *key*."""
        self._store[key] = value
        return True

    async def delete(self, key: str) -> int:
        """Remove *key*; return 1 if it existed, else 0."""
        return 1 if self._store.pop(key, None) is not None else 0


# ---------------------------------------------------------------------------
# Async — hash ops
# ---------------------------------------------------------------------------


class AsyncHashFakeRedis:
    """Async in-memory stub that supports Redis hash-field operations.

    ``_store`` is ``Dict[str, Dict[str, bytes]]`` — outer key is the hash
    name, inner dict maps field names to byte values.  Tests may seed or
    inspect ``_store`` directly for setup / assertion.

    Suitable for tests that interact with Redis hashes (e.g. knowledge_boards).
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, bytes]] = {}

    async def hset(self, name: str, key: str, value: str) -> int:
        """Set *key* field in hash *name*; return 1 if new, 0 if updated."""
        bucket = self._store.setdefault(name, {})
        existed = key in bucket
        bucket[key] = value.encode("utf-8") if isinstance(value, str) else value
        return 0 if existed else 1

    async def hget(self, name: str, key: str) -> bytes | None:
        """Return the bytes value for *key* in hash *name*, or ``None``."""
        return self._store.get(name, {}).get(key)

    async def hgetall(self, name: str) -> Dict[bytes, bytes]:
        """Return all fields of hash *name* with bytes keys and values."""
        raw = self._store.get(name, {})
        return {
            (k.encode("utf-8") if isinstance(k, str) else k): (v if isinstance(v, bytes) else v.encode("utf-8"))
            for k, v in raw.items()
        }

    async def hdel(self, name: str, key: str) -> int:
        """Delete *key* from hash *name*; return 1 if it existed, else 0."""
        bucket = self._store.get(name, {})
        if key in bucket:
            del bucket[key]
            return 1
        return 0


# ---------------------------------------------------------------------------
# Async — full surface (hashes + sorted sets + strings + pipeline)
# ---------------------------------------------------------------------------


class _Pipeline:
    """Accumulates Redis commands and replays them on ``execute()``.

    Used internally by :class:`AsyncFullFakeRedis`.
    """

    def __init__(self, redis: "AsyncFullFakeRedis") -> None:
        self._redis = redis
        self._ops: List[Tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def _op(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self

        return _op

    async def execute(self) -> List[Any]:
        """Replay all buffered commands and return their results."""
        out: List[Any] = []
        for name, args, kwargs in self._ops:
            method = getattr(self._redis, name)
            result = method(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            out.append(result)
        return out


class AsyncFullFakeRedis:
    """Async in-memory stub with hashes, sorted sets, strings, and pipeline.

    Provides the full surface needed by complex queue/state-machine tests
    (e.g. DocumentSyncQueue).  ``zsets`` is a public attribute so tests can
    seed or inspect sorted-set contents directly.

    Note: ``hset`` accepts both ``mapping=`` and keyword-arg forms to match
    redis-py's flexible calling convention.
    """

    def __init__(self) -> None:
        self._hashes: Dict[str, Dict[str, str]] = {}
        self.zsets: Dict[str, Dict[str, float]] = {}
        self._strings: Dict[str, str] = {}

    # -- string ops --

    async def get(self, key: str) -> str | None:
        """Return the string value for *key*, or ``None``."""
        return self._strings.get(key)

    async def set(self, key: str, value: str) -> bool:
        """Store *value* under *key* in the string store."""
        self._strings[key] = str(value)
        return True

    async def delete(self, *keys: str) -> int:
        """Remove one or more keys from hashes, zsets, and strings."""
        removed = 0
        for k in keys:
            for store in (self._hashes, self.zsets, self._strings):
                if k in store:
                    del store[k]
                    removed += 1
        return removed

    # -- hash ops --

    async def hset(
        self,
        key: str,
        mapping: Dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> int:
        """Set one or more hash fields; accepts ``mapping=`` or keyword args."""
        payload = mapping or kwargs
        bucket = self._hashes.setdefault(key, {})
        added = 0
        for k, v in payload.items():
            if k not in bucket:
                added += 1
            bucket[k] = str(v)
        return added

    async def hgetall(self, key: str) -> Dict[str, str]:
        """Return all fields of *key* as plain strings."""
        return dict(self._hashes.get(key, {}))

    # -- pipeline --

    def pipeline(self) -> _Pipeline:
        """Return a buffered pipeline that replays on ``execute()``."""
        return _Pipeline(self)

    # -- sorted set ops --

    async def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        """Add members with scores; return number of new members added."""
        bucket = self.zsets.setdefault(key, {})
        added = 0
        for m, score in mapping.items():
            if m not in bucket:
                added += 1
            bucket[m] = float(score)
        return added

    async def zrem(self, key: str, *members: str) -> int:
        """Remove *members* from sorted set *key*."""
        bucket = self.zsets.get(key, {})
        removed = 0
        for m in members:
            if m in bucket:
                del bucket[m]
                removed += 1
        return removed

    async def zrange(self, key: str, start: int, stop: int) -> List[str]:
        """Return members in ascending score order; ``stop=-1`` means last."""
        bucket = self.zsets.get(key, {})
        ordered = sorted(bucket.items(), key=lambda kv: kv[1])
        if stop == -1:
            stop = len(ordered) - 1
        return [k for k, _ in ordered[start : stop + 1]]

    async def zrevrange(self, key: str, start: int, stop: int) -> List[str]:
        """Return members in descending score order; ``stop=-1`` means last."""
        bucket = self.zsets.get(key, {})
        ordered = sorted(bucket.items(), key=lambda kv: kv[1], reverse=True)
        if stop == -1:
            stop = len(ordered) - 1
        return [k for k, _ in ordered[start : stop + 1]]

    async def zrangebyscore(self, key: str, min: float, max: float, **kwargs: Any) -> List[str]:
        """Return members whose score is between *min* and *max* (inclusive)."""
        bucket = self.zsets.get(key, {})
        lo = float("-inf") if min == "-inf" else float(min)
        hi = float("inf") if max == "+inf" else float(max)
        return sorted(
            (m for m, s in bucket.items() if lo <= s <= hi),
            key=lambda m: bucket[m],
        )

    async def zcard(self, key: str) -> int:
        """Return the number of members in sorted set *key*."""
        return len(self.zsets.get(key, {}))
