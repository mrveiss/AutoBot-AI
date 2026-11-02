# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Acquire, release and reclaim an agent workspace (#16818).

``LLCWorkspaceLease`` recorded what a workspace *is*; nothing took one, handed one
back, or took one away. This module is the domain operation the model was waiting
for, and #16817's sweep is its first caller.

Three things it keeps apart on purpose:

**Release is not reclaim.** A release is the system working -- a run ended and gave
its workspace back. A reclaim is the system recovering -- a deadline passed with
nobody there to hand anything back. Both write ``released_at``; only the reason
distinguishes them, which is why ``release_reason`` is never optional here even
though the column allows NULL.

**Freeing the slot is not removing the directory.** Reclaiming a lease returns
capacity immediately (AC5). Disposing of the directory requires evidence that the
work reached the remote, and lives in ``workspace_disposal`` (AC7). Keeping them in
one step would mean either the cap stays blocked whenever evidence is missing, or a
directory gets removed to satisfy the cap. The first re-creates the deadlock this
issue is about; the second is how work gets lost.

**Capacity is counted, not configured separately.** ``LLC_WORKSPACE_CAP`` bounds the
number of *live* leases, and expired ones stop counting the moment they are reclaimed
-- so the ceiling is a consequence of leases rather than a second limit that can
disagree with them (AC5).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.env_utils import env_int
from llc.models.workspace_lease import LLCWorkspaceLease

logger = logging.getLogger(__name__)

#: How long a workspace is leased for before it can be reclaimed without its holder.
#: Four hours is under the six-hour run-stall timeout on purpose: a run that stalls is
#: marked STALLED first and releases its lease through that path, so the deadline here
#: is the backstop for a holder that vanished without any run at all.
LEASE_TTL_SECONDS = env_int("LLC_WORKSPACE_LEASE_TTL_SECONDS", 4 * 60 * 60)

#: The ceiling the fleet hit on 2026-09-16. It bounds live leases, not directories:
#: a directory whose lease was reclaimed no longer occupies one of these.
WORKSPACE_CAP = env_int("LLC_WORKSPACE_CAP", 15)

RECLAIM_REASON = "lease expired: reclaimed by the workspace sweep (#16818)"


class WorkspaceLeaseHeld(RuntimeError):
    """Raised when a path already carries a live lease."""


class WorkspaceCapacityExhausted(RuntimeError):
    """Raised when every workspace slot is held by a lease that has not expired.

    Distinct from ``WorkspaceLeaseHeld``: that one means *this* directory is busy,
    this one means the fleet is full. On 2026-09-16 the two were indistinguishable
    because neither existed -- the cap simply refused, and the reason had to be
    reconstructed by hand from a shell script's output.
    """


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


def live_lease_select(now: Optional[datetime] = None):
    """Leases that are held and not yet past their deadline."""
    return select(LLCWorkspaceLease).where(
        LLCWorkspaceLease.released_at.is_(None),
        LLCWorkspaceLease.expires_at > _now(now),
    )


def expired_lease_select(now: Optional[datetime] = None):
    """Leases still held whose deadline has passed, locked for a reclaim.

    ``SKIP LOCKED`` for the same reason the stalled-run sweep takes it: two beat
    workers overlapping would otherwise both reclaim the same lease and write the
    release twice. Here the second write is not merely redundant -- a reclaim is
    what authorises disposal, so a double reclaim can authorise disposing of a
    directory a second lease has already been granted on.
    """
    return (
        select(LLCWorkspaceLease)
        .where(
            LLCWorkspaceLease.released_at.is_(None),
            LLCWorkspaceLease.expires_at <= _now(now),
        )
        .with_for_update(skip_locked=True)
    )


async def live_lease_count(
    session: AsyncSession, company_id: Optional[UUID] = None, now: Optional[datetime] = None
) -> int:
    """How many workspace slots are currently held."""
    query = (
        select(func.count())
        .select_from(LLCWorkspaceLease)
        .where(
            LLCWorkspaceLease.released_at.is_(None),
            LLCWorkspaceLease.expires_at > _now(now),
        )
    )
    if company_id is not None:
        query = query.where(LLCWorkspaceLease.company_id == company_id)
    return int((await session.execute(query)).scalar_one())


async def lease_for_path(session: AsyncSession, path: str) -> Optional[LLCWorkspaceLease]:
    """The lease currently held on *path*, or None.

    Only unreleased rows: a released lease is history, and treating history as a
    holder is what would make a path un-leasable for ever.
    """
    result = await session.execute(
        select(LLCWorkspaceLease).where(
            LLCWorkspaceLease.path == path,
            LLCWorkspaceLease.released_at.is_(None),
        )
    )
    return result.scalars().first()


async def acquire_lease(
    session: AsyncSession,
    *,
    company_id: UUID,
    path: str,
    owner: str,
    purpose: str,
    heartbeat_run_id: Optional[UUID] = None,
    branch: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    now: Optional[datetime] = None,
) -> LLCWorkspaceLease:
    """Take a lease on *path* for *owner*, reclaiming anything expired first.

    Reclaiming before counting is what makes the ceiling self-clearing: the exact
    situation that blocked the release-pipeline fix -- every slot held by leases
    whose holders were gone -- now resolves itself on the next acquire rather than
    waiting for a person to run a script.
    """
    moment = _now(now)
    await reclaim_expired(session, now=moment)

    held = await lease_for_path(session, path)
    if held is not None and held.is_live(moment):
        raise WorkspaceLeaseHeld(f"{path} is leased to {held.owner!r} until {held.expires_at.isoformat()}")

    if await live_lease_count(session, now=moment) >= WORKSPACE_CAP:
        raise WorkspaceCapacityExhausted(
            f"all {WORKSPACE_CAP} workspace slots are held by live leases; "
            "none has expired, so none can be reclaimed"
        )

    lease = LLCWorkspaceLease(
        company_id=company_id,
        path=path,
        owner=owner,
        purpose=purpose,
        heartbeat_run_id=heartbeat_run_id,
        branch=branch,
        acquired_at=moment,
        expires_at=moment + timedelta(seconds=ttl_seconds or LEASE_TTL_SECONDS),
    )
    session.add(lease)
    await session.flush()
    logger.info("#16818: workspace %s leased to %s for %s until %s", path, owner, purpose, lease.expires_at)
    return lease


def release_lease(lease: LLCWorkspaceLease, reason: str, now: Optional[datetime] = None) -> LLCWorkspaceLease:
    """Hand *lease* back, recording why.

    Idempotent: a lease already released keeps its original reason and timestamp. A
    second release would otherwise rewrite a clean handback as a reclaim purely
    because a sweep ran afterwards, and the audit trail would then describe a
    recovery that never happened.
    """
    if lease.released_at is not None:
        return lease
    lease.released_at = _now(now)
    lease.release_reason = reason
    return lease


async def release_for_run(
    session: AsyncSession, heartbeat_run_id: UUID, reason: str, now: Optional[datetime] = None
) -> list[LLCWorkspaceLease]:
    """Release every lease a run holds. The sweep's half of #16817's AC2."""
    result = await session.execute(
        select(LLCWorkspaceLease).where(
            LLCWorkspaceLease.heartbeat_run_id == heartbeat_run_id,
            LLCWorkspaceLease.released_at.is_(None),
        )
    )
    leases = list(result.scalars().all())
    for lease in leases:
        release_lease(lease, reason, now=now)
    if leases:
        logger.info("#16818: released %d workspace lease(s) held by run %s", len(leases), heartbeat_run_id)
    return leases


async def reclaim_expired(session: AsyncSession, now: Optional[datetime] = None) -> Sequence[LLCWorkspaceLease]:
    """Reclaim every lease past its deadline, returning what was taken back.

    The returned leases are the disposal candidates -- reclaimed, so their slot is
    free, but their directory untouched until ``workspace_disposal`` establishes the
    work reached the remote.
    """
    result = await session.execute(expired_lease_select(now))
    reclaimed = []
    for lease in result.scalars().all():
        # The WHERE clause already excludes live leases. This repeats it in Python on
        # purpose: reclaiming a live lease hands a working agent's directory to someone
        # else, and the only thing standing between that and a mistyped filter is one
        # clause in one query. A second check costs nothing per sweep and makes the
        # property assertable without a database.
        if lease.is_live(_now(now)):
            logger.error("#16818: refusing to reclaim live lease on %s held by %s", lease.path, lease.owner)
            continue
        reclaimed.append(lease)
        release_lease(lease, RECLAIM_REASON, now=now)
        logger.warning(
            "#16818: reclaimed workspace %s from %s (expired %s, purpose %r)",
            lease.path,
            lease.owner,
            lease.expires_at,
            lease.purpose,
        )
    return reclaimed


__all__ = [
    "LEASE_TTL_SECONDS",
    "RECLAIM_REASON",
    "WORKSPACE_CAP",
    "WorkspaceCapacityExhausted",
    "WorkspaceLeaseHeld",
    "acquire_lease",
    "expired_lease_select",
    "lease_for_path",
    "live_lease_count",
    "live_lease_select",
    "reclaim_expired",
    "release_lease",
    "release_for_run",
]
