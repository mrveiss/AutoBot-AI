# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Celery-beat sweep: reclaim workspace leases, and *propose* disposal (#16818, #17038).

The counterpart to the stalled-run sweep. That one closes out runs whose agent stopped
reporting; this one takes back workspaces whose holder stopped existing -- the case that
deadlocked the fleet on 2026-09-16, when three merged worktrees were held by a session
that was gone and nothing could release any of them.

**Nothing is removed unattended** (owner ruling, 2026-09-28, #17038). An earlier version
of this sweep deleted directories itself once it had proved the work was on a remote. The
proof was sound and the automation was not: an agent removing data on its own leaves a
``logger.info`` in a worker as its only record, which is not a paper trail. So the sweep
now proposes and a human disposes.

Three passes, in this order:

1. **Reclaim.** Every lease past its deadline is handed back, with a reason. This frees
   capacity immediately and unconditionally -- it is a database write about a lease, and
   no directory is touched, so nothing here needs approval.
2. **Execute what was already approved.** An approved proposal's paths are disposed of,
   and **landedness is proved again at this moment**, not trusted from the proposal. A
   proposal approved hours ago describes a directory as it was hours ago; someone may have
   worked in it since. The approval authorises the disposal, it does not vouch for the
   evidence.
3. **Propose.** Newly reclaimed workspaces that pass the landedness check become one
   pending approval carrying the evidence for each path.

Freeing the slot is still separate from removing the directory, and now doubly so: the
slot comes back on the sweep's own authority, the directory waits for a person.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from celery import shared_task
from sqlalchemy import select

from autobot_shared.env_utils import env_float_clamped
from llc.models.enums import ApprovalStatus, ApprovalType
from llc.services.approval import ApprovalService
from llc.services.workspace_disposal import DisposalVerdict, dispose_workspace, work_landed
from llc.services.workspace_lease import lease_for_path, reclaim_expired
from models.approval import Approval
from user_management.database import get_async_session_factory
from utils.celery_reliability import (
    CELERY_MAX_RETRIES,
    CELERY_RETRY_BACKOFF_MAX,
    CELERY_TRANSIENT_ERRORS,
    DeadLetterTask,
)

logger = logging.getLogger(__name__)

#: Marks a proposal this sweep raised, so it can find its own back without matching on a
#: title string. ``ApprovalType.DESTRUCTIVE_ACTION`` is the gate; this narrows it.
PROPOSAL_KIND = "workspace_disposal"

#: The requester recorded on the proposal. ``requested_by_agent`` is a String column
#: documented for "a plain string for a platform-general requester" -- there is no agent
#: here, and inventing a UUID to fill the field would be a fabricated identifier.
SWEEP_REQUESTER = "llc-workspace-lease-sweep"

#: How many approved proposals one sweep will act on. Bounded so a backlog of approvals
#: cannot turn one beat tick into an unbounded run of git operations -- applied AFTER the
#: executed ones are filtered out, never as a SQL LIMIT. See :func:`_approved_proposals`.
MAX_EXECUTIONS_PER_SWEEP = 20

#: How long an approval stays executable, in DAYS (#17738).
#:
#: The no-LIMIT design above has a consequence its own docstring does not draw:
#: an executed proposal keeps ``status = APPROVED``, so it matches this query for
#: ever -- and the sweep therefore re-reads its entire approval history every
#: hour, growing without bound. A time predicate bounds the read WITHOUT
#: reintroducing the trap a row LIMIT creates, because it does not fill with
#: executed rows; they age out of it.
#:
#: It also fixes a correctness problem the growth was hiding. A disposal approved
#: months ago and never executed would still be executed today, against a
#: workspace whose branch and landedness have moved on since a human looked. An
#: approval is a decision about a state of the world, and this is how long that
#: decision is assumed to still describe it.

#: Ids named in the aged-out warning before it is summarised. A warning long
#: enough to truncate a log line is a warning that gets scrolled past; the
#: COUNT is the actionable part and is always exact.
MAX_AGED_OUT_IDS_LOGGED = 20

EXECUTION_WINDOW_DAYS = env_float_clamped("AUTOBOT_LLC_DISPOSAL_EXECUTION_WINDOW_DAYS", 7.0, min_v=1.0)


@shared_task(
    name="llc.scheduler.workspace_lease_sweep.run_workspace_lease_sweep",
    bind=True,
    base=DeadLetterTask,
    autoretry_for=CELERY_TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    retry_backoff_max=CELERY_RETRY_BACKOFF_MAX,
    max_retries=CELERY_MAX_RETRIES,
)
def run_workspace_lease_sweep(self: object) -> dict:  # type: ignore[type-arg]
    """Celery entry point. Returns the counts so a run is legible from the result."""
    return asyncio.run(_async_sweep())


def _is_sweep_proposal(approval: Any) -> bool:
    context = approval.context or {}
    return context.get("kind") == PROPOSAL_KIND and not context.get("executed_at")


def _window_start() -> datetime:
    """The oldest ``decided_at`` this sweep will still act on (#17738).

    Aged-out approvals are **skipped, not marked**. ``ApprovalStatus.EXPIRED``
    exists in the vocabulary and is written by nothing in this repository, and an
    unattended sweep transitioning an approval's recorded status would be exactly
    the unattended state change this PR exists to remove -- "the sweep proposes, a
    human approves, nothing is removed unattended" applies to the approval record
    as much as to the workspace.

    So the record is left as a human left it, re-approvable, and the count of
    skipped ones is logged rather than silently dropped: a proposal that stopped
    being executed without anyone deciding so is exactly the invisible outcome
    this sweep's design is built against.
    """
    return datetime.now(tz=timezone.utc) - timedelta(days=EXECUTION_WINDOW_DAYS)


async def _approved_proposals(session) -> list[Approval]:
    """Approved disposal proposals this sweep raised and has not yet acted on.

    **There is deliberately no LIMIT on this query.** An executed proposal keeps
    ``status = APPROVED`` -- execution is recorded in ``context["executed_at"]``, because
    the approval vocabulary is six values shared by every gate and inventing a seventh to
    fix a query would change all of them. So executed rows go on matching every SQL
    predicate here for ever.

    A ``LIMIT`` ahead of the Python filter is therefore the one thing this must not do:
    once ``MAX_EXECUTIONS_PER_SWEEP`` executed proposals exist, the limit fills entirely
    with them, the filter drops all of them, and no approved disposal is ever executed
    again -- reporting ``disposed 0, refused 0``, which is what a sweep with nothing to do
    reports. *Cannot see the work* and *there is no work* would be identical, in the sweep
    written to stop exactly that.

    The bound belongs after the filter, where ``MAX_EXECUTIONS_PER_SWEEP`` does the job its
    own comment describes: capping git operations per tick, not rows per query. The set
    fetched is narrow -- approved proposals raised by this sweep -- and ordering by
    ``decided_at`` makes which ones get acted on deterministic rather than whatever the
    planner returned first.
    """
    result = await session.execute(
        select(Approval)
        .where(
            Approval.approval_type == ApprovalType.DESTRUCTIVE_ACTION.value,
            Approval.status == ApprovalStatus.APPROVED.value,
            Approval.requested_by_agent == SWEEP_REQUESTER,
            # #17738: bounds the read AND the staleness. Not a row LIMIT -- see above
            # for why that breaks; a window does not fill with executed rows.
            Approval.decided_at >= _window_start(),
        )
        .order_by(Approval.decided_at)
    )
    pending = [a for a in result.scalars().all() if _is_sweep_proposal(a)]
    await _log_aged_out(session)
    return pending[:MAX_EXECUTIONS_PER_SWEEP]


async def _log_aged_out(session) -> int:
    """Count approved proposals that fell out of the window, so they are not silent.

    :func:`_window_start` states that aged-out approvals are "skipped, not marked" and
    that "the count of skipped ones is logged rather than silently dropped". The window
    predicate alone cannot honour that: it filters in SQL, so the sweep never sees the
    rows and there is nothing left to count. This is the other half -- without it the
    docstring describes a log that does not exist, and a proposal that stopped being
    executed without anyone deciding so is exactly the invisible outcome it names.

    A SQL ``COUNT`` cannot stand in here either: sweep proposals are identified by
    :func:`_is_sweep_proposal`, a Python predicate over the payload, so the rows have to
    be fetched and filtered the same way the live query filters them.

    BOUNDED FROM BOTH SIDES, and the lower bound is not only about cost (#17725 review).
    An executed proposal keeps ``status == APPROVED``, so "everything older than the
    cutoff" is the whole approval history and grows without limit -- an hourly sweep
    would read all of it to report nothing. It also never stops reporting: a proposal
    that aged out in March would be named in every sweep thereafter, which is a warning
    nobody can act on and everybody learns to skip. One window of lookback reports each
    aged-out proposal while the fact is still news, and reads a bounded slice to do it.
    """
    cutoff = _window_start()
    result = await session.execute(
        select(Approval).where(
            Approval.approval_type == ApprovalType.DESTRUCTIVE_ACTION.value,
            Approval.status == ApprovalStatus.APPROVED.value,
            Approval.requested_by_agent == SWEEP_REQUESTER,
            Approval.decided_at < cutoff,
            Approval.decided_at >= cutoff - timedelta(days=EXECUTION_WINDOW_DAYS),
        )
    )
    aged = [a for a in result.scalars().all() if _is_sweep_proposal(a)]
    if aged:
        named = sorted(str(a.id) for a in aged)[:MAX_AGED_OUT_IDS_LOGGED]
        logger.warning(
            "#17738: %s approved disposal proposal(s) aged out of the %s-day window in the "
            "window before it and will not be executed; they remain APPROVED and "
            "re-approvable: %s%s",
            len(aged),
            EXECUTION_WINDOW_DAYS,
            ", ".join(named),
            "" if len(aged) <= MAX_AGED_OUT_IDS_LOGGED else f" (+{len(aged) - MAX_AGED_OUT_IDS_LOGGED} more)",
        )
    return len(aged)


async def _execute_approved(session) -> tuple[int, int]:
    """Dispose of approved paths, re-proving landedness. Returns (disposed, refused)."""
    disposed = refused = 0
    for approval in await _approved_proposals(session):
        outcomes = []
        for entry in (approval.context or {}).get("workspaces", []):
            path, branch = entry.get("path"), entry.get("branch")
            # Landedness is re-proved below, but an approval can sit for days and a
            # path freed at proposal time may have been leased again since. Disposing
            # then deletes a workspace somebody is currently working in. #17038 exists
            # so a destructive act is not carried out on a stale judgement, and the
            # judgement being re-proved was only ever about the git state (#17725 review).
            held = await lease_for_path(session, path)
            if held is not None and held.is_live(datetime.now(timezone.utc)):
                refused += 1
                detail = f"a live lease was taken after approval (owner={held.owner})"
                logger.warning("#16818: approved disposal of %s refused at execution -- %s", path, detail)
                outcomes.append({"path": path, "verdict": "lease_held", "detail": detail})
                continue
            check = await dispose_workspace(path, branch)
            if check.verdict is DisposalVerdict.LANDED:
                disposed += 1
            else:
                refused += 1
                logger.warning("#16818: approved disposal of %s refused at execution -- %s", path, check.detail)
            outcomes.append({"path": path, "verdict": check.verdict.value, "detail": check.detail})
        # Written back so the decision, the evidence and what actually happened live on
        # one record. A re-proof that refuses is part of the trail, not a silent skip.
        approval.context = {
            **(approval.context or {}),
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "execution_outcomes": outcomes,
        }
    return disposed, refused


async def _propose(session, candidates: list[tuple[str, str | None, Any]]) -> tuple[int, Any]:
    """Raise one proposal for the workspaces that currently look disposable.

    Returns ``(count, approval)``. The approval is handed back rather than discarded
    because ``request_approval`` only adds and flushes the row -- publishing
    ``llc:approval_requested`` is a separate call its own docstring says to make AFTER
    the transaction commits, so it cannot happen in here. A human approval is the only
    path to disposal, so an unpublished proposal is one no subscriber ever learns about:
    the sweep would propose into silence and report success. ``None`` when nothing was
    proposed.
    """
    proposed = []
    for path, branch, company_id in candidates:
        check = await work_landed(path, branch)
        if check.verdict is not DisposalVerdict.LANDED:
            logger.info("#16818: keeping workspace %s -- %s (%s)", path, check.detail, check.verdict.value)
            continue
        proposed.append({"path": path, "branch": branch, "evidence": check.detail, "company_id": str(company_id)})

    if not proposed:
        return 0, None

    approval = await ApprovalService().request_approval(
        session,
        company_id=proposed_company(proposed),
        gate_type=ApprovalType.DESTRUCTIVE_ACTION,
        payload={
            "kind": PROPOSAL_KIND,
            "summary": f"Dispose of {len(proposed)} reclaimed agent workspace(s) whose work is on a remote",
            "workspaces": proposed,
            "proposed_at": datetime.now(timezone.utc).isoformat(),
        },
        requested_by=SWEEP_REQUESTER,
    )
    return len(proposed), approval


def proposed_company(proposed: list[dict]) -> uuid.UUID | None:
    """The company a proposal is filed under, when they all share one.

    Leases are per company; a sweep run can span several. Rather than guess an owner for
    a mixed batch, a mixed batch is filed with no company and reaches the platform-level
    queue -- ``company_id`` is nullable for exactly this case. Guessing would put one
    company's directories in front of another company's reviewer.
    """
    ids = {entry["company_id"] for entry in proposed}
    return uuid.UUID(ids.pop()) if len(ids) == 1 else None


async def _async_sweep() -> dict:
    """Reclaim expired leases, act on approved proposals, propose the newly reclaimed."""
    factory = get_async_session_factory()
    async with factory() as session:
        reclaimed = await reclaim_expired(session)
        candidates = [(lease.path, lease.branch, lease.company_id) for lease in reclaimed]
        disposed, refused = await _execute_approved(session)
        proposed, approval = await _propose(session, candidates)
        await session.commit()
        if approval is not None:
            # After the commit, per publish_requested's own contract. Subscribers to
            # llc:approval_requested are the only route a human hears about a proposal.
            await ApprovalService().publish_requested(approval)

    # Every number reported, including the zeros: a sweep that found nothing and a sweep
    # that did not run must not look the same in the logs.
    logger.info(
        "#16818: workspace sweep reclaimed %d lease(s), disposed %d, refused %d, proposed %d for approval",
        len(candidates),
        disposed,
        refused,
        proposed,
    )
    return {"reclaimed": len(candidates), "disposed": disposed, "refused": refused, "proposed": proposed}


__all__ = ["run_workspace_lease_sweep"]
