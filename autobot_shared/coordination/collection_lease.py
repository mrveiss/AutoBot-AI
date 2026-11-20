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
* The delete does not wait and fails closed. A live writer, an unreachable Redis or an expired lease all mean
  "did not run" -- an approved cleanup must never remove more than the human approved.
* A lease is renewed while its block runs, so a write longer than the TTL keeps its claim.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from autobot_shared.coordination.work_claims import ClaimConflict, ClaimMode
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


class Lease:
    """A held claim, renewed in the background until :meth:`stop`; ``lost`` is set if a renew failed."""

    def __init__(self, name: str, mode: ClaimMode, ttl_s: int) -> None:
        self.name, self.mode, self.ttl_s = name, mode, ttl_s
        self.scope, self.task_id = collection_scope(name), f"{mode.value}-{uuid.uuid4().hex}"
        self.lost = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._renew_loop, name="chroma-lease-renew", daemon=True)

    def try_take(self) -> ClaimConflict | None:
        got = try_acquire_sync(
            self.scope, agent_id=_AGENT, task_id=self.task_id, mode=self.mode, intent="chroma", ttl_s=self.ttl_s
        )
        return got if isinstance(got, ClaimConflict) else None

    def still_held(self) -> bool:
        """Renew now; False means the claim had already lapsed and nothing may be done under it."""
        try:
            held = renew_sync(self.scope, agent_id=_AGENT, task_id=self.task_id, ttl_s=self.ttl_s)
        except Exception as exc:  # noqa: BLE001 -- an unreadable registry is "not held"
            logger.error("chroma lease %s: renew failed: %s", self.scope, exc)
            held = False
        self.lost = self.lost or not held
        return held

    def _renew_loop(self) -> None:
        while not self._stop.wait(self.ttl_s / 3):
            if not self.still_held():
                logger.error("chroma lease %s lapsed while its holder was still running", self.scope)
                return

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            release_sync(self.scope, agent_id=_AGENT, task_id=self.task_id)
        except Exception as exc:  # noqa: BLE001 -- the TTL frees it; a failed release must not mask the work's result
            logger.warning("chroma lease %s: release failed, it will expire: %s", self.scope, exc)


@contextmanager
def write_lease(name: str) -> Iterator[Lease]:
    """Hold *name* for writing (shared with other writers); wait for a delete, then raise.

    Raises:
        CollectionLeaseUnavailable: a delete held the collection for the whole wait.
        ClaimUnavailable: the registry is unreachable -- no write is made without the lease.
    """
    lease = Lease(name, ClaimMode.SHARED, WRITE_LEASE_TTL_S)
    deadline = time.monotonic() + WRITE_LEASE_WAIT_S
    while (conflict := lease.try_take()) is not None:
        if time.monotonic() >= deadline:
            raise CollectionLeaseUnavailable(
                name, f"write waited {WRITE_LEASE_WAIT_S}s for a delete: {conflict}", conflict
            )
        time.sleep(LEASE_POLL_MS / 1000)
    lease.start()
    try:
        yield lease
    finally:
        lease.stop()


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
