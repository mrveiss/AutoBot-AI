# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading and setting the hourly rate of a role (#14607).

The rate is what turns a step's recorded time into money, so who may change it
is the same question as who may change what the role runs: it carries the same
company-admin gate as every other role attachment (#14221).

There is deliberately no "delete the rate" that leaves steps costed. Clearing
the rate makes every step of that role *not costable* again, which is the
honest outcome — a cost derived from a rate that no longer exists would be a
number with no basis.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.activity import ActorType
from ..models.role_rate import LLCRoleRate
from .authz import require_company_admin
from .base import LLCServiceBase

#: ISO 4217 codes are exactly three letters. Validated rather than trusted so a
#: free-text unit can never reach a figure people read as money.
CURRENCY_LENGTH = 3


class RoleRateService(LLCServiceBase):
    """The hourly cost of a role, in one company."""

    async def _record(
        self,
        session: AsyncSession,
        rate: LLCRoleRate,
        event_type: str,
        actor: Optional[str],
        after: Optional[dict],
    ) -> None:
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(rate.company_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=actor,
            event_type=event_type,
            entity_type="llc_role_rate",
            entity_id=str(rate.id),
            after=after,
        )

    async def get(
        self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID
    ) -> Optional[LLCRoleRate]:
        """The role's rate, or ``None`` when nobody has set one.

        ``None`` is not zero. A role with no rate cannot have its steps costed,
        which is a different statement from its work being free.
        """
        result = await session.execute(
            select(LLCRoleRate).where(
                LLCRoleRate.company_id == company_id,
                LLCRoleRate.role_id == role_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_rate(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        hourly_rate: Decimal,
        currency: str,
        actor_user_id: uuid.UUID,
    ) -> LLCRoleRate:
        """Set or replace the role's rate.

        Replaces rather than appends: the unique constraint allows one rate per
        role, because two would make "the rate" ambiguous and every derived
        cost would depend on which row a query happened to read.
        """
        if hourly_rate is None or Decimal(hourly_rate) < 0:
            raise ValueError("hourly_rate must be zero or positive")
        code = (currency or "").strip().upper()
        if len(code) != CURRENCY_LENGTH or not code.isalpha():
            raise ValueError("currency must be a three-letter code")

        await require_company_admin(session, company_id, actor_user_id)

        existing = await self.get(session, company_id, role_id)
        if existing is None:
            existing = LLCRoleRate(
                company_id=company_id,
                role_id=role_id,
                hourly_rate=Decimal(hourly_rate),
                currency=code,
            )
            session.add(existing)
            event = "role_rate.set"
        else:
            existing.hourly_rate = Decimal(hourly_rate)
            existing.currency = code
            event = "role_rate.changed"

        await session.flush()
        # The amount is recorded in the audit trail: a rate change moves every
        # cost figure derived from it, and "who changed it to what" is the only
        # way to explain a total that moved without any step being edited.
        await self._record(
            session,
            existing,
            event,
            str(actor_user_id),
            {"role_id": str(role_id), "hourly_rate": str(existing.hourly_rate), "currency": code},
        )
        return existing

    async def clear(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> bool:
        """Remove the rate, making the role's steps not costable again."""
        await require_company_admin(session, company_id, actor_user_id)
        existing = await self.get(session, company_id, role_id)
        if existing is None:
            return False
        await self._record(
            session, existing, "role_rate.cleared", str(actor_user_id), {"role_id": str(role_id)}
        )
        await session.execute(sa_delete(LLCRoleRate).where(LLCRoleRate.id == existing.id))
        return True
