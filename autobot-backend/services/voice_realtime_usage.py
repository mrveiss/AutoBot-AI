# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Usage deltas for realtime voice sessions (#21678).

Usage is accounted as additive deltas, never as whole-record snapshots: a delta that could not be committed
(Redis down, telemetry off, a failed write) is kept pending and added with the next one, so no write failure,
consent flip or missing-key race can replace a larger total with a smaller one.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, fields
from typing import Any, Callable

from redis.exceptions import WatchError


@dataclass
class UsageDelta:
    """Usage to ADD to a session record: tokens, audio seconds and tool calls (cost derives from these)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    audio_in_s: float = 0.0
    audio_out_s: float = 0.0
    tool_calls: int = 0

    def merged(self, other: "UsageDelta") -> "UsageDelta":
        """A new delta holding both."""
        return UsageDelta(**{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)})

    def apply_to(self, record: Any) -> None:
        """Add this delta onto *record* in place."""
        for f in fields(self):
            setattr(record, f.name, getattr(record, f.name) + getattr(self, f.name))


@dataclass
class EndStep:
    """One ``session_end`` attempt: its unique *token*, the end *stamp*, and *refresh* (re-derive cost after usage).

    Called as the finish step on the first end. The token is stored in the record as ``end_token``, so a retried end
    (its EXEC raised after applying) recognises itself, while an end by another worker is told apart from it.
    """

    token: str
    stamp: Callable[[Any], None]
    refresh: Callable[[Any], None]

    def __call__(self, record: Any) -> None:
        self.stamp(record)
        record.end_token = self.token


class SessionLocks:
    """Lazily created per-session locks: updates and ends of ONE session serialise, different sessions never wait."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    def release_if_idle(self, session_id: str) -> None:
        """Forget the lock only when nobody holds it or waits on it (a dropped busy lock splits the serialisation).

        asyncio.Lock has no public waiter count; a woken waiter stays in ``_waiters`` until it has run, so the
        private attribute is the only way to see it.
        """
        lock = self._locks.get(session_id)
        if lock is not None and not lock.locked() and not getattr(lock, "_waiters", None):
            del self._locks[session_id]

    @asynccontextmanager
    async def hold(self, session_id: str):
        """Serialise on the session's lock; on exit (after releasing) forget it if idle, known session or not."""
        try:
            async with self.get(session_id):
                yield
        finally:
            self.release_if_idle(session_id)


@dataclass
class EndedSession:
    """A session that ended while Redis could not take it: kept until its final state is committed (#21678).

    ``base`` is the local record before the unflushed usage, ``delta`` that usage, ``ended`` the finished view
    (its end time, duration and reason are what gets stamped, so a late flush keeps the real end).
    """

    base: Any
    delta: UsageDelta
    ended: Any


def usage_view(record: Any, delta: UsageDelta, finish: Callable[[Any], None] | None) -> Any:
    """A copy of *record* with *delta* (and the optional finish) applied; the stored record is not touched."""
    view = type(record).from_dict(record.to_dict())
    delta.apply_to(view)
    if finish is not None:
        finish(view)
    return view


async def update_in_redis(
    redis: Any,
    *,
    key: str,
    ttl: int,
    parse: Callable[[Any], Any],
    total: UsageDelta,
    finish: Callable[[Any], None] | None,
    base: Any | None,
    attempts: int,
) -> Any | None:
    """Re-read, add *total*, SET under WATCH/MULTI; a conflicting write (another worker, or a concurrent create of a
    missing key) re-reads and re-applies. A missing key is created from *base* only while it is still absent. A record
    already ended by this very attempt (same end token) is returned unchanged; one ended by another worker keeps that
    worker's stamp and gets this usage added."""
    for _ in range(attempts):
        async with redis.pipeline(transaction=True) as pipe:
            try:
                return await _attempt(pipe, key, ttl, parse, total, finish, base)
            except WatchError:
                continue  # another write landed first: re-read its state and apply ours on top
    raise RuntimeError(f"voice_realtime: {key} contended for {attempts} attempts")


async def _attempt(pipe: Any, key: str, ttl: int, parse: Any, total: UsageDelta, finish: Any, base: Any) -> Any | None:
    await pipe.watch(key)
    raw = await pipe.get(key)
    current = parse(raw) if raw is not None else base
    if current is None:
        await pipe.unwatch()
        return None
    if finish is not None and current.ended_at:
        if getattr(current, "end_token", None) == getattr(finish, "token", None):  # our own retried end
            await pipe.unwatch()
            return current
        finish = getattr(finish, "refresh", None)  # another worker ended it: keep its stamp, add our usage
    record = usage_view(current, total, finish)
    pipe.multi()
    pipe.set(key, json.dumps(record.to_dict()), ex=ttl)
    await pipe.execute()
    return record
