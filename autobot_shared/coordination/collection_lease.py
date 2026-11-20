# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The per-collection write lease: many writers OR one deleter (#20992, #17038).

Chroma has no compare-and-delete, so "delete it if it is empty" is only safe if no write can land
between the count and the delete. Every writer to a collection takes a SHARED claim on
``kb:chroma/<name>`` for the length of its write; the approved empty-collection delete takes the
EXCLUSIVE claim, counts, and deletes only at zero. This is the ``work_claims`` registry, not a second one
(``docs/developer/AGENT_COORDINATION.md``): Redis-backed, so it holds across workers and processes, and it
expires, so a crashed holder frees the collection.

* Writers WAIT (bounded by :data:`WRITE_LEASE_WAIT_S`) while a delete holds the collection, then raise
  :class:`CollectionLeaseUnavailable`. A delete holds for one count and one delete, so a wait is short; failing
  at once would turn an admin cleanup into spurious write errors. A write is never dropped silently: it lands
  or it raises.
* Writers FAIL OPEN: when Redis is unreachable (``ClaimUnavailable`` or a connection error) the write proceeds
  without the lease and a warning names the collection (never data). Losing the lease while Redis is UP is a
  real conflict and raises: the write is confirmed against the registry just before the Chroma call.
* The delete FAILS CLOSED and does not wait. A live writer, an unreachable Redis or an expired lease all mean
  "did not run" -- an approved cleanup must never remove more than the human approved. Because the delete
  never runs without its lease, no delete can race a write during an outage.
* A lease is renewed while its block outlives a third of its TTL (a timer armed at that point, so a
  millisecond write spawns no thread), so a write longer than the TTL keeps its claim.
* A writer's wait is a blocking poll: never make it on the event-loop thread. Run the write in
  ``asyncio.to_thread``; a wait that would block a running loop raises instead of sleeping.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from redis.exceptions import RedisError

from autobot_shared.coordination.work_claims import ClaimConflict, ClaimMode, ClaimUnavailable
from autobot_shared.coordination.work_claims_sync import release_sync, renew_sync, try_acquire_sync
from autobot_shared.env_utils import env_int_clamped

logger = logging.getLogger(__name__)

#: How long a lease survives without a renew; the holder renews at a third of it.
WRITE_LEASE_TTL_S = env_int_clamped("AUTOBOT_CHROMA_WRITE_LEASE_TTL_S", 60, min_v=10, max_v=600)
DELETE_LEASE_TTL_S = env_int_clamped("AUTOBOT_CHROMA_DELETE_LEASE_TTL_S", 60, min_v=10, max_v=600)
#: How long a writer waits for a delete to finish before it raises.
WRITE_LEASE_WAIT_S = env_int_clamped("AUTOBOT_CHROMA_WRITE_LEASE_WAIT_S", 30, min_v=1, max_v=600)
LEASE_POLL_MS = env_int_clamped("AUTOBOT_CHROMA_LEASE_POLL_MS", 50, min_v=5, max_v=5000)

_AGENT = "chroma-collection-lease"


class CollectionLeaseUnavailable(RuntimeError):
    """The lease was not (or is no longer) held: nothing was written or deleted under it."""

    def __init__(self, name: str, reason: str, conflict: ClaimConflict | None = None) -> None:
        super().__init__(f"chroma collection {name!r}: {reason}")
        self.name, self.conflict = name, conflict


def collection_scope(name: str) -> str:
    """The registry scope for a collection; one per name, so leases on different collections never meet."""
    return f"kb:chroma/{name}"


#: What "Redis is down" looks like to a writer: the registry's own refusal or a connection-level failure.
_OUTAGE = (ClaimUnavailable, RedisError, OSError)


#: A lease is renewed every ``ttl / RENEW_DIVISOR`` seconds while its block is still running.
RENEW_DIVISOR = 3


class _Renewer:
    """One lazily started daemon thread that renews every live lease when it falls due.

    A write that finishes inside a third of the TTL registers and deregisters without ever being renewed, and
    the thread is started once per process, on the first lease -- not once per write.
    """

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._due: dict[Lease, float] = {}
        self._thread: threading.Thread | None = None

    def add(self, lease: Lease) -> None:
        with self._cv:
            if lease._stopped:
                return
            self._due[lease] = time.monotonic() + lease.ttl_s / RENEW_DIVISOR
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="chroma-lease-renew", daemon=True)
                self._thread.start()
            self._cv.notify()

    def remove(self, lease: Lease) -> None:
        with self._cv:
            self._due.pop(lease, None)

    def _take_due(self) -> list[Lease]:
        with self._cv:
            while True:
                now = time.monotonic()
                ready = [lease for lease, due in self._due.items() if due <= now]
                if ready:
                    for lease in ready:
                        del self._due[lease]
                    return ready
                self._cv.wait(min(self._due.values()) - now if self._due else None)

    def _run(self) -> None:
        while True:
            for lease in self._take_due():
                lease.renew_due()
                if not lease._lapsed:
                    self.add(lease)


_RENEWER = _Renewer()


class Lease:
    """A held claim, renewed by the shared renewer once its block outlives a third of the TTL.

    ``lost`` is set if a renew found the claim gone.

    ``held`` is False for a writer that failed open (registry unreachable): it owns nothing to renew or release.
    """

    def __init__(self, name: str, mode: ClaimMode, ttl_s: int) -> None:
        self.name, self.mode, self.ttl_s = name, mode, ttl_s
        self.scope, self.task_id = collection_scope(name), f"{mode.value}-{uuid.uuid4().hex}"
        self.lost = False
        self.held = True
        self._stopped = False
        self._lapsed = False

    def try_take(self) -> ClaimConflict | None:
        got = try_acquire_sync(
            self.scope, agent_id=_AGENT, task_id=self.task_id, mode=self.mode, intent="chroma", ttl_s=self.ttl_s
        )
        return got if isinstance(got, ClaimConflict) else None

    def renew(self) -> bool | None:
        """Renew now: True held, False the claim had lapsed (a real loss), None the registry is unreachable."""
        try:
            held = renew_sync(self.scope, agent_id=_AGENT, task_id=self.task_id, ttl_s=self.ttl_s)
        except Exception as exc:  # noqa: BLE001 -- an unreadable registry is "unknown", never "held"
            logger.error("chroma lease %s: renew failed: %s", self.scope, exc)
            return None
        self.lost = self.lost or not held
        return held

    def still_held(self) -> bool:
        """True only when the registry confirmed the claim; unreachable counts as not held (the delete's rule)."""
        return self.renew() is True

    def ensure_held(self) -> None:
        """Confirm the lease just before a Chroma write; a lease lost while Redis is up raises, an outage fails open."""
        if not self.held:
            return
        verdict = self.renew()
        if verdict is False:
            raise CollectionLeaseUnavailable(self.name, "the write lease lapsed before the write; nothing written")
        if verdict is None:
            logger.warning("chroma collection %r: lease registry unreachable, writing without confirming it", self.name)

    def start(self) -> None:
        """Register for renewal; nothing renews until the block has outlived a third of the TTL."""
        _RENEWER.add(self)

    def renew_due(self) -> None:
        """One scheduled renew; the renewer re-registers the lease only while the registry still holds it."""
        if self._stopped:
            return
        if not self.still_held():
            logger.error("chroma lease %s lapsed while its holder was still running", self.scope)
            self._lapsed = True

    def stop(self) -> None:
        self._stopped = True
        _RENEWER.remove(self)
        if not self.held:
            return
        try:
            release_sync(self.scope, agent_id=_AGENT, task_id=self.task_id)
        except Exception as exc:  # noqa: BLE001 -- the TTL frees it; a failed release must not mask the work's result
            logger.warning("chroma lease %s: release failed, it will expire: %s", self.scope, exc)


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _wait_for_delete(lease: Lease) -> None:
    """Poll until no delete holds the collection; raises after the wait, or at once on a running event loop."""
    deadline = time.monotonic() + WRITE_LEASE_WAIT_S
    while (conflict := lease.try_take()) is not None:
        if _on_event_loop():
            raise CollectionLeaseUnavailable(
                lease.name, f"a delete holds it and a sync write on the event loop must not wait: {conflict}", conflict
            )
        if time.monotonic() >= deadline:
            raise CollectionLeaseUnavailable(
                lease.name, f"write waited {WRITE_LEASE_WAIT_S}s for a delete: {conflict}", conflict
            )
        time.sleep(LEASE_POLL_MS / 1000)


@contextmanager
def write_lease(name: str) -> Iterator[Lease]:
    """Hold *name* for writing (shared with other writers); wait for a delete, then raise.

    Raises:
        CollectionLeaseUnavailable: a delete held the collection for the whole wait, or (called inside the
            block) the lease had lapsed while the registry was up.

    Fails open: an unreachable registry yields an unheld lease and the write proceeds, with a warning.
    """
    lease = Lease(name, ClaimMode.SHARED, WRITE_LEASE_TTL_S)
    try:
        _wait_for_delete(lease)
    except _OUTAGE as exc:
        logger.warning("chroma collection %r: lease registry unreachable (%s); writing without the lease", name, exc)
        lease.held = False
    if not lease.held:
        yield lease
        return
    lease.start()
    try:
        yield lease
    finally:
        lease.stop()
        if lease.lost:
            logger.error("chroma collection %r: the write lease was lost while the write ran", name)


@contextmanager
def delete_lease(name: str) -> Iterator[Lease]:
    """Hold *name* exclusively, or raise at once: a live writer, or an unreachable registry, means "did not run"."""
    lease = Lease(name, ClaimMode.EXCLUSIVE, DELETE_LEASE_TTL_S)
    if (conflict := lease.try_take()) is not None:
        raise CollectionLeaseUnavailable(name, f"a write is in progress: {conflict}", conflict)
    lease.start()
    try:
        yield lease
    finally:
        lease.stop()
