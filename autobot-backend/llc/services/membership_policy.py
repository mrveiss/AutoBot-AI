# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who may grant or revoke a company membership role (#19654).

Maintainer decisions on #19634: no lockouts, superadmin accounts exist, the owner
is always in control, and a superadmin can assign ``owner`` and ``admin``.

- A platform admin may make any change, in a company it is not a member of,
  including one with no owner left.
- An owner may change any role.
- An admin may change ``admin``, ``member`` and ``viewer``, never an ``owner``.
- Anyone else may change nothing.
- The last owner cannot be removed or demoted, except by a platform admin.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MembershipRole
from ..models.membership import LLCCompanyMembership
from .authz import NotAuthorisedError, require_company_admin

_OWNER = MembershipRole.OWNER.value


class LastOwnerError(Exception):
    """The change would leave the company with no owner."""


def _role_value(role: Optional[object]) -> Optional[str]:
    return role.value if isinstance(role, MembershipRole) else role


async def _owner_count(session: AsyncSession, company_id: uuid.UUID) -> int:
    """The owners, row-locked so two concurrent demotions cannot each see the other still there."""
    rows = await session.execute(
        select(LLCCompanyMembership.id)
        .where(LLCCompanyMembership.company_id == company_id, LLCCompanyMembership.role == MembershipRole.OWNER)
        .with_for_update()
    )
    return len(rows.all())


async def authorize_member_change(
    session: AsyncSession,
    company_id: uuid.UUID,
    actor_user_id: Optional[uuid.UUID],
    *,
    platform_admin: bool,
    current_role: Optional[object],
    new_role: Optional[object],
) -> None:
    """Raise unless the actor may move a member from *current_role* to *new_role*.

    ``None`` means no membership: *current_role* for an add, *new_role* for a removal.
    *platform_admin* comes from the verified tenant context, never from request data.
    """
    if platform_admin:
        return
    current, new = _role_value(current_role), _role_value(new_role)
    actor_role = await require_company_admin(session, company_id, actor_user_id, for_update=True)
    if _OWNER in (current, new) and actor_role != _OWNER:
        raise NotAuthorisedError(f"role {actor_role!r} may not grant or revoke owner in company {company_id}")
    if current == _OWNER and new != _OWNER and await _owner_count(session, company_id) <= 1:
        raise LastOwnerError(f"company {company_id} would be left with no owner")
