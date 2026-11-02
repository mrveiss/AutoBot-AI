# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What "next" means for a work item, stated once (#15905).

Two callers need the backlog's ordering: `BacklogService.list`, which shows a
human the queue, and `checkout_next`, which hands an agent the top of it. They
must agree — an agent working items in a different order from the one an owner
reordered is a silent disagreement about priority, with the reorder appearing to
have done nothing.

The first version of `checkout_next` copied `_PRIORITY_RANK` out of `backlog.py`
rather than sharing it. Two literals expressing one rule is exactly the defect
#15912 had just removed from the pricing tables, and it would have drifted the
same way: a priority added to the enum, ranked in one copy.

This module also exists because `work_item_service.py` sits **at** its
grandfathered ceiling of 1,100 lines (#14236) — the exemption freezes the size
it was granted for and does not license more. Extraction is the answer to that,
not a raised ceiling, and the extraction that was already justified on its own
terms is the one to make.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, List, Optional

from sqlalchemy import and_, case, nulls_last, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ..models.enums import WorkItemPriority, WorkItemStatus
from ..models.work_item import LLCWorkItem

logger = logging.getLogger(__name__)

#: How many ranked candidates :func:`checkout_next` will try before giving up.
#: One is not enough: losing the race on the single top item would report "no
#: work" while a queue of eligible items sat behind it.
CHECKOUT_CANDIDATES = 10

#: Priority, as an orderable rank. `WorkItemPriority` is a string enum, so
#: sorting it alphabetically would put `critical` after `low`.
PRIORITY_RANK = case(
    (LLCWorkItem.priority == WorkItemPriority.CRITICAL.value, 1),
    (LLCWorkItem.priority == WorkItemPriority.HIGH.value, 2),
    (LLCWorkItem.priority == WorkItemPriority.MEDIUM.value, 3),
    (LLCWorkItem.priority == WorkItemPriority.LOW.value, 4),
    else_=5,
)


def backlog_order() -> List[Any]:
    """The backlog's ordering, as `order_by` arguments.

    Explicit `backlog_position` first, then priority rank, then age. This is what
    makes a `bulk_reorder` write immediately observable to both the list view and
    the next agent to ask for work.

    **The `nulls_last` is currently dead, and the comment it replaces was wrong.**
    That comment said NULLS LAST lets items never reordered keep their natural
    priority/age ordering. `backlog_position` is `nullable=False` with
    `server_default="0"` and `bulk_reorder` assigns `0..n-1`, so no row is ever
    NULL: un-reordered items sit at 0 and therefore sort AHEAD of anything
    reordered to position >= 1. `nulls_last` is retained because it costs nothing
    and becomes correct the moment the column takes a sentinel, but it is not
    doing the work the old wording claimed. Tracked as #15963 -- the fix is a
    sentinel plus a data migration, and existing `0` rows are ambiguous between
    "untouched" and "reordered to first", which no migration can separate.
    """
    return [nulls_last(LLCWorkItem.backlog_position.asc()), PRIORITY_RANK, LLCWorkItem.created_at.asc()]


def claimable_by(agent_uuid: uuid.UUID) -> ColumnElement[bool]:
    """Assignment predicate: unassigned, or already this agent's.

    "Unassigned" requires BOTH assignee columns to be null. Testing only
    `assignee_agent_id` let an agent claim an item assigned to a USER
    (CWE-863) — and `checkout` writes `assignee_type = agent` for whatever it
    claims, so the row came out naming an agent and a user at once, with the
    type agreeing with only one of them. `checkout` now also clears
    `assignee_user_id`, which keeps a row consistent; this predicate is what
    stops the claim happening at all.

    Split out of the `checkout_next` SELECT so the rule can be compiled and
    asserted on directly — the behavioural path needs Postgres and skips
    without it, and a security regression test that skips is not a test.
    """
    return or_(
        and_(
            LLCWorkItem.assignee_agent_id.is_(None),
            LLCWorkItem.assignee_user_id.is_(None),
        ),
        LLCWorkItem.assignee_agent_id == agent_uuid,
    )


def eligible_for(agent_id: str, company_id: str) -> List[ColumnElement[bool]]:
    """What makes a work item claimable by *agent_id* right now, as WHERE clauses.

    This company's, ``ready``, unclaimed, and either unassigned or already this
    agent's. ``backlog`` is excluded deliberately -- an item nobody has readied
    is not work an agent should pick up on its own.

    Split out of :func:`checkout_next` for #17726, which needs to ask "is there
    anything to do?" without claiming anything. The alternative was a second
    copy of these four clauses, and a second copy is the drift this module's own
    header records happening once already: two expressions of one rule, one of
    which quietly stops matching what the other does. There is now exactly one
    answer to "may this agent work on this item", and both callers read it.
    """
    return [
        LLCWorkItem.company_id == uuid.UUID(company_id),
        LLCWorkItem.status == WorkItemStatus.READY.value,
        LLCWorkItem.checkout_run_id.is_(None),
        claimable_by(uuid.UUID(agent_id)),
    ]


async def has_pending_work(session: AsyncSession, agent_id: str, company_id: str) -> bool:
    """Whether :func:`checkout_next` would have anything to offer (#17726).

    Bounded by construction: ``LIMIT 1`` over the same predicate and the same
    ordering, selecting the id rather than the entity, so it cannot become the
    expensive call in a poll loop no matter how long the backlog grows.

    It answers "would a checkout find something", not "will the next checkout
    succeed" -- another agent can take the item in between. That race is
    harmless here and already handled where it matters: ``checkout_next`` walks
    ``CHECKOUT_CANDIDATES`` candidates precisely because losing one is normal.
    A false ``True`` costs one wake that finds nothing, which is the behaviour
    that existed before this function. A false ``False`` would drop work, and
    that is why the predicate is shared rather than restated.
    """
    result = await session.execute(
        select(LLCWorkItem.id).where(*eligible_for(agent_id, company_id)).order_by(*backlog_order()).limit(1)
    )
    return result.first() is not None


async def checkout_next(
    session: AsyncSession,
    service: Any,
    agent_id: str,
    company_id: str,
    run_id: Optional[str] = None,
    work_intent: Optional[str] = None,
) -> Optional[LLCWorkItem]:
    """Claim the highest-ranked item this agent may work on, or ``None``.

    Selection here, the claim itself via ``service.checkout`` — the atomicity,
    the Redis fence and the ``SELECT FOR UPDATE`` stay in one place rather than
    being reimplemented.

    ``agent_id`` is the agent's ``agent_org_nodes.id`` **as a UUID string**, not
    its slug: ``checkout`` writes ``assignee_agent_id = uuid.UUID(agent_id)``
    against a UUID column. The agent-facing route resolves the slug before
    calling, so the poor error (`ValueError` from `uuid.UUID`) happens nowhere.

    Eligible means: this company's, ``ready``, unclaimed, and either unassigned
    or assigned to this agent. ``backlog`` is excluded deliberately — an item
    nobody has readied is not work an agent should pick up on its own, and
    `WorkItemStatus` distinguishes the two precisely so that call can be made.

    ``None`` when nothing is eligible: an ordinary answer, not an error. An
    agent asking for work when there is none is the common case.
    """
    from .work_item_service import CheckoutConflict

    # In SQL, not in Python after the fact. The LIMIT must apply to ELIGIBLE
    # rows: filtering afterwards meant ten items assigned to other agents
    # returned "no work" while eligible items sat below them, and the bound
    # silently became "how many of the top ten are mine" rather than "how many
    # claims will I attempt". `eligible_for` keeps that in the WHERE clause.
    eligible = (
        select(LLCWorkItem)
        .where(*eligible_for(agent_id, company_id))
        .order_by(*backlog_order())
        .limit(CHECKOUT_CANDIDATES)
    )
    for item in (await session.execute(eligible)).scalars().all():
        try:
            return await service.checkout(
                session,
                work_item_id=str(item.id),
                agent_id=agent_id,
                run_id=run_id,
                work_intent=work_intent,
            )
        except CheckoutConflict:
            # Taken between the SELECT and the fence. Try the next candidate:
            # the caller wants work, not this particular item.
            logger.debug("checkout_next: %s taken by another agent, trying the next", item.id)
            continue
    return None
