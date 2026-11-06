# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-session Redis lease that serialises chat-file read-modify-write (#20862).

Every writer of a ``<session>_chat.json`` (save, metadata, owner and rename writes) reads the
file, changes it and writes it back. Two workers doing that at once lose one change, so each
takes this lease first, re-reads the file under it and applies only its own delta.

Built on :class:`autobot_shared.leader_lease.LeaderLease` (SET NX acquire, compare-and-extend
heartbeat, compare-and-delete release). On top of it:

* a per-session ``asyncio.Lock`` is only a fair local queue in front of the Redis lease;
* a contended writer waits up to ``AUTOBOT_CHAT_LEASE_WAIT_S`` and then raises
  :class:`SessionLeaseTimeout` naming the holder; it is never fail-fast, never last-writer-wins
  and never written unlocked;
* a fencing generation (``INCR`` per acquire, floored by the generation stored in the file) is
  written into the file; a write carrying a generation lower than the file's is rejected with
  :class:`StaleGenerationError`;
* the lease is re-entrant inside one task, so a locked save that calls another locked write
  does not deadlock.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import socket
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator, Dict

from autobot_shared.env_registry import REGISTRY, env
from autobot_shared.env_utils import env_float_clamped, env_int_clamped
from autobot_shared.error_boundaries.types import PassThroughError
from autobot_shared.leader_lease import LeaderLease
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import decode_redis_value

logger = get_logger(__name__)


def _registered_range(name: str) -> tuple[Any, Any, Any]:
    """The registry's default and (min, max) for *name*, so the registered range is the one enforced."""
    spec = REGISTRY[name]
    low, high = spec.range or (None, None)
    return spec.default, low, high


def _ttl_ms() -> int:
    default, low, high = _registered_range("AUTOBOT_CHAT_LEASE_TTL_MS")
    return env_int_clamped("AUTOBOT_CHAT_LEASE_TTL_MS", default, low, high)


def _seconds(name: str) -> float:
    default, low, high = _registered_range(name)
    return env_float_clamped(name, default, low, high)


# Defaults and ranges live in autobot_shared/env_registry_chat_lease.py; a malformed value falls back to the
# default and an out-of-range one is clamped (with a warning), so neither crashes the import.
CHAT_LEASE_TTL_MS: int = _ttl_ms()
CHAT_LEASE_WAIT_S: float = _seconds("AUTOBOT_CHAT_LEASE_WAIT_S")
CHAT_LEASE_POLL_S: float = _seconds("AUTOBOT_CHAT_LEASE_POLL_S")
CHAT_LEASE_DATABASE: str = env("AUTOBOT_CHAT_LEASE_REDIS_DB")
#: Lease keys and their fencing counters live under different prefixes, so no session id can make one the other.
CHAT_LEASE_KEY_PREFIX: str = env("AUTOBOT_CHAT_LEASE_KEY_PREFIX")
CHAT_LEASE_GENERATION_PREFIX: str = env("AUTOBOT_CHAT_LEASE_GENERATION_KEY_PREFIX")

#: Key in the chat file that carries the generation of the lease that last wrote it.
GENERATION_FIELD = "write_generation"

# INCR with a floor: a counter that was flushed or evicted restarts above the file's generation.
_GENERATION_LUA = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local floor = tonumber(ARGV[1])
if current < floor then redis.call('SET', KEYS[1], floor) end
return redis.call('INCR', KEYS[1])
"""


class SessionLeaseError(PassThroughError, RuntimeError):
    """Base class for chat-session lease failures.

    A ``PassThroughError``: ``with_error_handling`` re-raises it so the app-wide handler answers it.
    """


class SessionLeaseTimeout(SessionLeaseError):
    """The lease stayed held by another writer for the whole bounded wait."""

    def __init__(self, session_id: str, holder: str, waited_s: float) -> None:
        self.session_id = session_id
        self.holder = holder
        super().__init__(
            "chat session %s is held by %s; waited %.1fs for it to finish" % (session_id, holder, waited_s)
        )


class ChatFileUnreadable(SessionLeaseError):
    """A chat file exists but cannot be read or decoded, so nothing is written over it."""

    def __init__(self, session_id: str, cause: BaseException) -> None:
        self.session_id = session_id
        super().__init__(
            "chat session %s has a file that cannot be read (%s); not overwriting it" % (session_id, cause)
        )


class SessionLeaseLost(SessionLeaseError):
    """The lease could not be confirmed just before a write, so nothing was written."""


class StaleGenerationError(SessionLeaseError):
    """A write carried a fencing generation lower than the one already in the file."""

    def __init__(self, session_id: str, write_generation: int, file_generation: int) -> None:
        self.write_generation = write_generation
        self.file_generation = file_generation
        super().__init__(
            "write to chat session %s rejected: generation %d is older than the file's %d"
            % (session_id, write_generation, file_generation)
        )


_held: contextvars.ContextVar[Dict[str, "SessionLease"]] = contextvars.ContextVar("chat_session_leases")
_local_locks: Dict[str, asyncio.Lock] = {}
_local_waiters: Dict[str, int] = {}
_local_holder: Dict[str, str] = {}


async def _lease_client(database: str) -> Any:
    """Redis client for the lease keys (module-level so tests can bind a fake).

    An unknown AUTOBOT_CHAT_LEASE_REDIS_DB is a lease failure the caller can tell apart, not a bare
    KeyError that a broad ``except`` further up would read as "the write failed".
    """
    try:
        return await get_async_redis_client(database=database)
    except KeyError as exc:
        raise SessionLeaseError("chat lease Redis database %r is not a known database" % database) from exc


def file_generation(chat_data: Dict[str, Any]) -> int:
    """The fencing generation recorded in a chat file's data (0 for a file never written under a lease)."""
    try:
        return int(chat_data.get(GENERATION_FIELD) or 0)
    except (TypeError, ValueError):
        return 0


class SessionLease:
    """One writer's hold on a session's chat file, with its fencing generation."""

    def __init__(self, session_id: str, operation: str) -> None:
        self.session_id = session_id
        self.operation = operation
        self.key = CHAT_LEASE_KEY_PREFIX + session_id
        self.generation_key = CHAT_LEASE_GENERATION_PREFIX + session_id
        self.owner: asyncio.Task | None = asyncio.current_task()
        self.generation = 0
        holder = "%s-%d:%s:%s" % (socket.gethostname(), os.getpid(), operation, uuid.uuid4().hex[:8])
        self._lease = LeaderLease(
            self.key,
            database=CHAT_LEASE_DATABASE,
            ttl_ms=CHAT_LEASE_TTL_MS,
            refresh_s=CHAT_LEASE_TTL_MS / 3000.0,
            poll_s=CHAT_LEASE_POLL_S,
            worker_id=holder,
            label="chat session %s" % session_id,
            client_factory=_lease_client,
        )
        self._heartbeat: asyncio.Task | None = None
        self._lost = False

    async def holder(self) -> str:
        """Who holds the lease now, as recorded in the lease value."""
        try:
            redis = await _lease_client(CHAT_LEASE_DATABASE)
            value = decode_redis_value(await redis.get(self.key)) if redis is not None else None
        except Exception as exc:
            logger.warning("Could not read the holder of %s: %s", self.key, exc)
            return "unknown (lease store unreadable)"
        return value or "unknown (lease store unreachable or lease just released)"

    async def acquire(self) -> None:
        """Take the lease, polling until it is free. The caller bounds the wait (see session_lease)."""
        while await self._lease.hold_or_refresh() is not True:
            await asyncio.sleep(CHAT_LEASE_POLL_S)
        self._heartbeat = asyncio.create_task(self._beat())

    def _mark_lost(self) -> None:
        """Record, once and for good, that this writer no longer holds the lease."""
        if not self._lost:
            self._lost = True
            logger.warning("Lost the lease on chat session %s (operation %s)", self.session_id, self.operation)

    async def _beat(self) -> None:
        """Keep the lease alive while the holder works; a refresh that finds another owner ends it."""
        while True:
            await asyncio.sleep(self._lease.refresh_s)
            if await self._lease.hold_or_refresh() is False:
                self._mark_lost()
                return

    async def verify(self) -> None:
        """Confirm the lease is still ours (extending it); raise SessionLeaseLost when it is not.

        A lease once lost stays lost: it is never re-acquired mid-operation.
        """
        state = None if self._lost else await self._lease.hold_or_refresh()
        if state is False:
            self._mark_lost()
        if state is not True:
            raise SessionLeaseLost(
                "lease on chat session %s could not be confirmed before the write; held by %s"
                % (self.session_id, await self.holder())
            )

    async def begin(self, current_file_generation: int) -> None:
        """Allocate this lease's fencing generation, above both the counter and the file's."""
        if self.generation:
            return
        redis = await _lease_client(CHAT_LEASE_DATABASE)
        if redis is None:
            raise SessionLeaseLost("lease store unreachable for chat session %s" % self.session_id)
        floor = int(current_file_generation)
        self.generation = int(await redis.eval(_GENERATION_LUA, 1, self.generation_key, floor))

    async def fence(self, chat_data: Dict[str, Any], on_disk_generation: int) -> None:
        """Confirm the lease, reject a stale write, and stamp this lease's generation into *chat_data*."""
        await self.verify()
        if on_disk_generation > self.generation:
            raise StaleGenerationError(self.session_id, self.generation, on_disk_generation)
        chat_data[GENERATION_FIELD] = self.generation

    async def release(self) -> None:
        """Stop the heartbeat and drop the lease if still ours."""
        if self._heartbeat is not None:
            self._heartbeat.cancel()
            await asyncio.gather(self._heartbeat, return_exceptions=True)
            self._heartbeat = None
        await self._lease.release()


@asynccontextmanager
async def _local_turn(session_id: str, operation: str) -> AsyncIterator[None]:
    """Fair in-worker queue in front of the Redis lease; the caller's timeout bounds the wait."""
    lock = _local_locks.setdefault(session_id, asyncio.Lock())
    _local_waiters[session_id] = _local_waiters.get(session_id, 0) + 1
    try:
        async with lock:
            _local_holder[session_id] = operation
            try:
                yield
            finally:
                _local_holder.pop(session_id, None)
    finally:
        _local_waiters[session_id] -= 1
        if not _local_waiters[session_id]:
            _local_waiters.pop(session_id, None)
            _local_locks.pop(session_id, None)


async def _enter(stack: AsyncExitStack, session_id: str, operation: str) -> SessionLease:
    """Queue locally, then take the Redis lease, all inside ONE bound of CHAT_LEASE_WAIT_S."""
    lease = SessionLease(session_id, operation)
    queued = False
    try:
        async with asyncio.timeout(CHAT_LEASE_WAIT_S):
            await stack.enter_async_context(_local_turn(session_id, operation))
            queued = True
            stack.push_async_callback(lease.release)  # a no-op until acquired, so a cancel mid-acquire leaks nothing
            await lease.acquire()
    except TimeoutError:
        # still in the local queue: the holder is another task here; otherwise it is whoever holds the Redis key
        holder = (None if queued else _local_holder.get(session_id)) or await lease.holder()
        raise SessionLeaseTimeout(session_id, holder, CHAT_LEASE_WAIT_S) from None
    return lease


@asynccontextmanager
async def session_lease(session_id: str, operation: str) -> AsyncIterator[SessionLease]:
    """Hold the session's write lease for the block, waiting at most CHAT_LEASE_WAIT_S in total.

    Re-entrant within the task that holds it. A task spawned inside the block inherits the held lease
    through its copied context but is not its owner, so it queues for the lease like any other writer.
    """
    held = _held.get({})
    current = held.get(session_id)
    if current is not None and current.owner is asyncio.current_task():
        yield current
        return
    async with AsyncExitStack() as stack:
        lease = await _enter(stack, session_id, operation)
        token = _held.set({**held, session_id: lease})
        try:
            yield lease
        finally:
            _held.reset(token)


__all__ = [
    "CHAT_LEASE_TTL_MS",
    "CHAT_LEASE_WAIT_S",
    "ChatFileUnreadable",
    "GENERATION_FIELD",
    "SessionLease",
    "SessionLeaseError",
    "SessionLeaseLost",
    "SessionLeaseTimeout",
    "StaleGenerationError",
    "file_generation",
    "session_lease",
]
