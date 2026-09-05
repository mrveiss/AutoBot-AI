# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading and writing the reporting hierarchy (#15763).

Three things live here: resolving one subject's manager, walking upward a
bounded number of steps, and deriving the downward view.

**Only explicit lines are stored.** An absent row means "reports to the CEO",
and the CEO's absent row means "reports to an owner"; an owner terminates. The
defaults resolve here at read time and are never written — a materialised
default is a second copy of a fact the rule already fixes, and it goes stale the
moment the CEO changes, leaving a chart where everyone reports to the previous
one and every row is individually valid.

**"Manages" is derived.** It is the same relation read from the other end, so
it is a query for who names me, never a stored list. Two stores of one fact can
disagree and nothing in a schema makes the disagreement visible.

**The walk is bounded and cycle-guarded.** #15765 needs two levels and no more;
an unbounded walk over a graph that can contain a cycle does not terminate, and
a cycle is reachable here because a reporting line is a plain row that nothing
stops from pointing back into its own chain.

**The CEO step is a seam, not an omission.** No company designates a CEO yet
(#15770), so `_resolve_ceo` returns None and the chain ends after the explicit
edges with :class:`ChainEnd.NO_CEO`. That is the state every company is in
today, and it is reported rather than hidden: a chart that silently stops at the
last explicit edge looks identical to a correctly-rooted one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.activity import ActorType
from ..models.enums import MembershipRole, RoleHolderType
from ..models.membership import LLCCompanyMembership
from ..models.reporting_line import LLCReportingLine
from .authz import require_company_admin
from .base import LLCServiceBase

#: #15765 needs the subject's manager and that manager's manager. The bound is
#: on the walk, not on the organisation: two hops from the subject, whichever
#: kind of edge each hop uses.
DEFAULT_MAX_DEPTH = 2

#: Subjects and managers this service accepts. ``CONTACT`` is excluded: a
#: contact is a person a company deals with, not a member of its hierarchy
#: (#13938), so a contact has no reporting line in either direction. The column
#: shape can express one if that ever changes.
_PLACEABLE = frozenset({RoleHolderType.USER.value, RoleHolderType.AGENT.value})


class ChainEnd(str, Enum):
    """Why an upward walk stopped. Distinguishing these is the point.

    A walk that ran out of explicit edges with no CEO to fall back on looks
    exactly like one that reached the top, unless the reason is carried.
    """

    OWNER = "owner"
    DEPTH = "depth"
    CYCLE = "cycle"
    NO_CEO = "no_ceo"


@dataclass(frozen=True)
class Holder:
    """One end of a reporting edge: a person or an agent."""

    type: str
    id: uuid.UUID


@dataclass(frozen=True)
class Chain:
    """An upward walk: who was reached, in order, and why it stopped."""

    managers: Tuple[Holder, ...]
    ended: ChainEnd


class ReportingLineService(LLCServiceBase):
    """Resolve, walk and record reporting lines."""

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    async def explicit_manager(
        self, session: AsyncSession, company_id: uuid.UUID, subject: Holder
    ) -> Optional[Holder]:
        """The stored manager for one subject, or None when none is recorded.

        None means "no explicit line", which is not the same as "no manager" —
        the caller applies the default chain.
        """
        column = (
            LLCReportingLine.subject_user_id
            if subject.type == RoleHolderType.USER.value
            else LLCReportingLine.subject_agent_id
        )
        result = await session.execute(
            select(LLCReportingLine).where(
                LLCReportingLine.company_id == company_id,
                LLCReportingLine.subject_type == subject.type,
                column == subject.id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None or row.manager_id is None:
            return None
        return Holder(type=row.manager_type, id=row.manager_id)

    async def direct_reports(
        self, session: AsyncSession, company_id: uuid.UUID, manager: Holder
    ) -> List[Holder]:
        """Who names this holder as their manager — derived, never stored."""
        column = (
            LLCReportingLine.manager_user_id
            if manager.type == RoleHolderType.USER.value
            else LLCReportingLine.manager_agent_id
        )
        result = await session.execute(
            select(LLCReportingLine).where(
                LLCReportingLine.company_id == company_id,
                LLCReportingLine.manager_type == manager.type,
                column == manager.id,
            )
        )
        reports = []
        for row in result.scalars():
            if row.subject_id is not None:
                reports.append(Holder(type=row.subject_type, id=row.subject_id))
        return reports

    async def _owners(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> List[Holder]:
        """Every owner of the company. Peers with identical standing (#15763)."""
        result = await session.execute(
            select(LLCCompanyMembership.user_id).where(
                LLCCompanyMembership.company_id == company_id,
                LLCCompanyMembership.role == MembershipRole.OWNER.value,
            )
        )
        return [
            Holder(type=RoleHolderType.USER.value, id=row) for row in result.scalars()
        ]

    async def _resolve_ceo(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> Optional[Holder]:
        """The company's CEO, or None while no company designates one.

        The seam for #15770. Returning None is the truthful answer today, not a
        placeholder: nothing in the schema designates a CEO, so the middle step
        of the default chain has no target and the walk reports ``NO_CEO``.
        """
        return None

    async def chain_up(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        subject: Holder,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> Chain:
        """Walk upward from ``subject``, at most ``max_depth`` hops.

        Follows explicit lines first, then the default chain: CEO, then owners.
        Owners terminate — theirs is the absent line that means "top", and
        without that exception the rule makes each of them report to the CEO
        who reports to them.
        """
        managers: List[Holder] = []
        seen = {(subject.type, subject.id)}
        current = subject

        for _ in range(max_depth):
            nxt = await self.explicit_manager(session, company_id, current)
            if nxt is None:
                return await self._default_step(
                    session, company_id, current, managers, max_depth
                )
            key = (nxt.type, nxt.id)
            if key in seen:
                # A row pointing back into its own chain. Stopping here rather
                # than looping is the whole reason the walk carries `seen`.
                return Chain(tuple(managers), ChainEnd.CYCLE)
            seen.add(key)
            managers.append(nxt)
            current = nxt

        return Chain(tuple(managers), ChainEnd.DEPTH)

    async def _default_step(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        current: Holder,
        managers: List[Holder],
        max_depth: int,
    ) -> Chain:
        """Apply the default chain once the explicit edges run out."""
        if await self._is_owner(session, company_id, current):
            return Chain(tuple(managers), ChainEnd.OWNER)

        ceo = await self._resolve_ceo(session, company_id)
        if ceo is None:
            return Chain(tuple(managers), ChainEnd.NO_CEO)

        if (ceo.type, ceo.id) != (current.type, current.id) and len(
            managers
        ) < max_depth:
            managers.append(ceo)

        # Owners sit above the CEO, all of them, as equals. They are appended
        # together rather than picked between: there is no primary owner and
        # none should be inferred.
        if len(managers) < max_depth:
            for owner in await self._owners(session, company_id):
                if (owner.type, owner.id) != (current.type, current.id):
                    managers.append(owner)
        return Chain(tuple(managers), ChainEnd.OWNER)

    async def _is_owner(
        self, session: AsyncSession, company_id: uuid.UUID, holder: Holder
    ) -> bool:
        if holder.type != RoleHolderType.USER.value:
            return False
        result = await session.execute(
            select(LLCCompanyMembership.id).where(
                LLCCompanyMembership.company_id == company_id,
                LLCCompanyMembership.user_id == holder.id,
                LLCCompanyMembership.role == MembershipRole.OWNER.value,
            )
        )
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    @staticmethod
    def _require_placeable(holder: Holder, role: str) -> None:
        if holder.type not in _PLACEABLE:
            raise ValueError(f"{role} must be a user or an agent, not {holder.type!r}")
        if holder.id is None:
            raise ValueError(f"{role} id is required")

    async def _would_cycle(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        subject: Holder,
        manager: Holder,
    ) -> bool:
        """True when pointing ``subject`` at ``manager`` closes a loop.

        Walks up from the proposed manager along **explicit** edges only, which
        is what a cycle can be made of — the defaults cannot form one, because
        owners terminate.

        Deliberately unbounded, unlike :meth:`chain_up`. The read walk stops at
        two hops because that is all authority needs; a cycle can be closed
        anywhere in the chain, and a depth-limited check would miss one formed
        three levels up and let the row through. The visited set is what makes
        an unbounded walk safe here — including against a cycle that already
        exists in the data.
        """
        seen = {(manager.type, manager.id)}
        current: Optional[Holder] = manager
        while current is not None:
            if (current.type, current.id) == (subject.type, subject.id):
                return True
            current = await self.explicit_manager(session, company_id, current)
            if current is None:
                return False
            key = (current.type, current.id)
            if key in seen:
                # Pre-existing loop, unrelated to this edge. Report it as a
                # cycle rather than spinning: refusing the write is right, and
                # so is not hanging.
                return True
            seen.add(key)
        return False

    async def set_line(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        subject: Holder,
        manager: Holder,
        actor_user_id: uuid.UUID,
    ) -> LLCReportingLine:
        """Record who a subject reports to, replacing any existing line.

        The caller is expected to have passed the route's authority gate
        (``admin.reporting_line.write``, #15765). This method does **not**
        assume it ran: ``require_company_admin`` is applied here as a floor —
        narrower than the eventual gate and never wider — so a second caller
        reaching this method is not silently unguarded. Any such caller still
        needs its own explicit decision.
        """
        if company_id is None:
            raise ValueError("company_id is required")
        self._require_placeable(subject, "subject")
        self._require_placeable(manager, "manager")

        if (subject.type, subject.id) == (manager.type, manager.id):
            raise ValueError("a subject cannot report to itself")

        await require_company_admin(session, company_id, actor_user_id)

        if await self._would_cycle(session, company_id, subject, manager):
            raise ValueError("that reporting line would create a cycle")

        # Replace rather than accumulate: line management is single-valued, and
        # the partial unique index would reject a second row anyway. Deleting
        # first keeps the failure a clear replacement instead of a constraint
        # violation the caller has to interpret.
        await self._clear(session, company_id, subject)

        row = LLCReportingLine(
            company_id=company_id,
            subject_type=subject.type,
            subject_user_id=subject.id
            if subject.type == RoleHolderType.USER.value
            else None,
            subject_agent_id=subject.id
            if subject.type == RoleHolderType.AGENT.value
            else None,
            manager_type=manager.type,
            manager_user_id=manager.id
            if manager.type == RoleHolderType.USER.value
            else None,
            manager_agent_id=manager.id
            if manager.type == RoleHolderType.AGENT.value
            else None,
        )
        session.add(row)
        await session.flush()
        await self._record(
            session,
            row,
            "reporting_line.set",
            actor_user_id,
            {
                "subject": f"{subject.type}:{subject.id}",
                "manager": f"{manager.type}:{manager.id}",
            },
        )
        return row

    async def clear_line(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        subject: Holder,
        actor_user_id: uuid.UUID,
    ) -> bool:
        """Remove a subject's explicit line, returning them to the default chain.

        Clearing is not orphaning: with no row the subject reports to the CEO,
        so this restores the default rather than detaching anyone.
        """
        self._require_placeable(subject, "subject")
        await require_company_admin(session, company_id, actor_user_id)
        removed = await self._clear(session, company_id, subject)
        if removed and self.activity_log:
            await self.activity_log.record(
                session=session,
                company_id=str(company_id),
                actor_type=ActorType.USER,
                actor_id=str(actor_user_id),
                event_type="reporting_line.cleared",
                entity_type="llc_reporting_line",
                entity_id=f"{subject.type}:{subject.id}",
                after={"subject": f"{subject.type}:{subject.id}"},
            )
        return removed

    async def _clear(
        self, session: AsyncSession, company_id: uuid.UUID, subject: Holder
    ) -> bool:
        column = (
            LLCReportingLine.subject_user_id
            if subject.type == RoleHolderType.USER.value
            else LLCReportingLine.subject_agent_id
        )
        result = await session.execute(
            sa_delete(LLCReportingLine).where(
                LLCReportingLine.company_id == company_id,
                LLCReportingLine.subject_type == subject.type,
                column == subject.id,
            )
        )
        return bool(result.rowcount)

    async def _record(
        self,
        session: AsyncSession,
        row: LLCReportingLine,
        event_type: str,
        actor: Optional[uuid.UUID],
        after: dict,
    ) -> None:
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(row.company_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=str(actor) if actor else None,
            event_type=event_type,
            entity_type="llc_reporting_line",
            entity_id=str(row.id),
            after=after,
        )
