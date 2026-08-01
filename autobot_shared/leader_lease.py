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
from typing import Awaitable, Callable, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

# Compare-and-extend in a single round-trip. A plain GET->PEXPIRE pair can be
# split by a pause between the two calls, letting an expired leader extend a key
# another worker has already taken.
_REFRESH_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
else
    return 0
end
"""

# Lease lifetime, and how often the holder renews it. Refresh must stay well
# under the TTL so a slow cycle does not drop a lease that is still held.
DEFAULT_TTL_MS = 30_000
DEFAULT_REFRESH_S = 10
DEFAULT_POLL_S = 15

Hook = Callable[[], Awaitable[None] | None]


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
    ) -> None:
        self.key = key
        self.database = database
        self.ttl_ms = ttl_ms
        self.refresh_s = refresh_s
        self.poll_s = poll_s
        self.worker_id = worker_id or "%s-%d" % (socket.gethostname(), os.getpid())
        self.label = label or key
        self._is_leader = False

    @property
    def is_leader(self) -> bool:
        """Whether this worker currently holds the lease."""
        return self._is_leader

    async def try_acquire_or_refresh(self) -> bool:
        """Take the lease with SET NX, or atomically extend one already held."""
        redis = await get_async_redis_client(database=self.database)
        if redis is None:
            return False
        try:
            if self._is_leader:
                held = await redis.eval(_REFRESH_LUA, 1, self.key, self.worker_id, str(self.ttl_ms))
                return bool(held)
            acquired = await redis.set(self.key, self.worker_id, nx=True, px=self.ttl_ms)
            return acquired is not None
        except Exception as exc:
            logger.warning("Leader election Redis error for %s: %s", self.label, exc)
            return False

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

        Best-effort: deletes only when the key still carries this worker's id,
        so a lease that already expired and was retaken is never deleted.
        """
        if not self._is_leader:
            return
        self._is_leader = False
        redis = await get_async_redis_client(database=self.database)
        if redis is None:
            return
        try:
            current = await redis.get(self.key)
            if _decode(current) == self.worker_id:
                await redis.delete(self.key)
        except Exception as exc:
            logger.warning("Failed to release leader lease %s: %s", self.label, exc)


def _decode(val: object) -> str:
    """Decode bytes to str; pass through str. Redis may return either."""
    return val.decode() if isinstance(val, bytes) else (val or "")  # type: ignore[return-value]


async def _call(hook: Hook | None) -> None:
    """Invoke a hook that may be sync or async."""
    if hook is None:
        return
    result = hook()
    if asyncio.iscoroutine(result):
        await result


__all__ = ["LeaderLease", "DEFAULT_TTL_MS", "DEFAULT_REFRESH_S", "DEFAULT_POLL_S"]
