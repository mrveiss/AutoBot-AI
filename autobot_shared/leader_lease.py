# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis-backed leader election for multi-worker schedulers (GH#12835).

One canonical implementation of the "exactly one worker does the work" lease.
It was previously written twice — `knowledge/connectors/scheduler.py` and
`services/skill_management/skill_distillation_scheduler.py` — with the Lua
script byte-identical between the copies.

The Lua script is the security-sensitive part: it makes compare-and-extend
atomic so a GC pause or network delay cannot leave two workers both believing
they hold the lease. Two copies meant that guarantee had two places to regress,
which is why this lives in one module now.

Usage::

    lease = LeaderLease(key="connector:scheduler:leader", database="knowledge")
    await lease.run(
        on_tick=self._reconcile_schedules,
        on_acquired=lambda: logger.info("became leader"),
        on_lost=self._cancel_all_local_tasks,
    )
"""

from __future__ import annotations

import asyncio
import os
import socket
import uuid
from typing import Any, Awaitable, Callable, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import delete_if_value, expire_if_value

logger = get_logger(__name__)

# Lease lifetime, and how often the holder renews it. Refresh must stay well
# under the TTL so a slow cycle does not drop a lease that is still held.
DEFAULT_TTL_MS = 30_000
DEFAULT_REFRESH_S = 10
DEFAULT_POLL_S = 15

Hook = Callable[[], Awaitable[None] | None]


def worker_identity(*, unique: bool = False) -> str:
    """The name one worker takes a lock under: ``host-pid``; with *unique*, a random suffix names one INSTANCE.

    Used by :class:`LeaderLease` and the LLC outbound sync. Two routers in one process (tests) need *unique*, so a
    lock one took is not the other's.
    """
    identity = "%s-%d" % (socket.gethostname(), os.getpid())
    return "%s:%s" % (identity, uuid.uuid4().hex[:8]) if unique else identity


class LeaderLease:
    """A Redis lease granting one worker the right to run a job.

    Owns the key, the lease lifetime, the atomic refresh and the
    acquired/lost transitions. Callers supply only their key, their Redis
    database, and what to do while holding it.
    """

    def __init__(
        self,
        key: str,
        *,
        database: str = "main",
        ttl_ms: int = DEFAULT_TTL_MS,
        refresh_s: float = DEFAULT_REFRESH_S,
        poll_s: float = DEFAULT_POLL_S,
        worker_id: Optional[str] = None,
        label: str = "",
        client_factory: Optional[Callable[..., Awaitable[Any]]] = None,
    ) -> None:
        self.key = key
        self.database = database
        self.ttl_ms = ttl_ms
        self.refresh_s = refresh_s
        self.poll_s = poll_s
        self.worker_id = worker_id or worker_identity()
        self.label = label or key
        self._is_leader = False
        self._client_factory = client_factory

    async def _client(self) -> Any:
        """The Redis client for this lease: the injected factory, else the shared async client."""
        factory = self._client_factory or get_async_redis_client
        return await factory(database=self.database)

    @property
    def is_leader(self) -> bool:
        """Whether this worker currently holds the lease."""
        return self._is_leader

    async def _attempt(self) -> Optional[bool]:
        """SET NX, or the atomic extend of a lease already held: True held, False another owner's, None unknown."""
        try:
            redis = await self._client()
        except Exception as exc:
            if not self._is_leader:
                raise  # while contesting, a factory failure (an unknown database) reaches the caller
            logger.warning("Leader election Redis error for %s: %s", self.label, exc)
            return None  # while holding, it is "no answer" (as a failed refresh): the heartbeat carries on
        if redis is None:
            return None
        try:
            if self._is_leader:
                return await expire_if_value(redis, self.key, self.worker_id, self.ttl_ms)
            acquired = await redis.set(self.key, self.worker_id, nx=True, px=self.ttl_ms)
            return acquired is not None
        except Exception as exc:
            logger.warning("Leader election Redis error for %s: %s", self.label, exc)
            return None

    async def try_acquire_or_refresh(self) -> bool:
        """Take the lease with SET NX, or atomically extend one already held."""
        return await self._attempt() is True

    async def hold_or_refresh(self) -> Optional[bool]:
        """Like :meth:`_attempt`, and leadership follows only a definite answer (#20556).

        True: held, its TTL reset. False: another worker owns the key, so leadership ends now.
        None: Redis did not answer. Leadership is left as it was, since the key still names this
        worker until its TTL runs out; the caller decides how long to keep trying.
        """
        state = await self._attempt()
        if state is not None:
            self._is_leader = state
        return state

    async def update_leadership(
        self,
        on_acquired: Hook | None = None,
        on_lost: Hook | None = None,
    ) -> bool:
        """Acquire or refresh the lease, logging and firing hooks on a transition.

        Public so a caller with its own loop cadence — a work interval, an
        enabled/disabled gate — can reuse the election without adopting
        :meth:`run`. Returns whether the lease is held after this attempt.
        """
        won = await self.try_acquire_or_refresh()
        if won and not self._is_leader:
            self._is_leader = True
            logger.info("%s: became leader (%s)", self.label, self.worker_id)
            await _call(on_acquired)
        elif not won and self._is_leader:
            self._is_leader = False
            logger.warning("%s: lost leadership (%s)", self.label, self.worker_id)
            await _call(on_lost)
        return self._is_leader

    async def run(
        self,
        on_tick: Hook | None = None,
        on_acquired: Hook | None = None,
        on_lost: Hook | None = None,
    ) -> None:
        """Hold or contest the lease forever, running *on_tick* while leader.

        Returns only on cancellation. Any exception from a hook is logged and
        the loop continues — a failing job must not silently drop the lease and
        leave the work unowned.
        """
        while True:
            try:
                await self.update_leadership(on_acquired, on_lost)
                if self._is_leader:
                    await _call(on_tick)
                await asyncio.sleep(self.refresh_s if self._is_leader else self.poll_s)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Leader loop error for %s: %s", self.label, exc)
                await asyncio.sleep(self.poll_s)

    async def release(self) -> None:
        """Drop the lease if held, so another worker can take over immediately.

        Best-effort: deletes only when the key still carries this worker's id, in
        one atomic compare-and-delete, so a lease that expired and was retaken --
        even between a read and a delete -- is never deleted.
        """
        if not self._is_leader:
            return
        self._is_leader = False
        try:
            redis = await self._client()
            if redis is None:
                return
            await delete_if_value(redis, self.key, self.worker_id)
        except Exception as exc:
            logger.warning("Failed to release leader lease %s: %s", self.label, exc)


async def _call(hook: Hook | None) -> None:
    """Invoke a hook that may be sync or async."""
    if hook is None:
        return
    result = hook()
    if asyncio.iscoroutine(result):
        await result


__all__ = ["LeaderLease", "worker_identity", "DEFAULT_TTL_MS", "DEFAULT_REFRESH_S", "DEFAULT_POLL_S"]
