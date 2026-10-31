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
- An admin may change ``admin``, ``member``, ``guest`` and ``lead``, never an ``owner``.
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
from .authz import GRANTING_ROLES, NotAuthorisedError, require_company_admin

_OWNER = MembershipRole.OWNER.value


def grantable_roles(actor_role: Optional[str], *, platform_admin: bool) -> list[str]:
    """The roles the actor may grant or revoke, as :func:`authorize_member_change` decides them.

    For a client to reflect, not to enforce: the server re-checks every change. Uses the same
    rules, so the two cannot drift. ``MembershipRole`` is owner, admin, member, guest and lead.
    """
    everyone = [role.value for role in MembershipRole]
    if platform_admin or actor_role == _OWNER:
        return everyone
    if actor_role in GRANTING_ROLES:
        return [role for role in everyone if role != _OWNER]
    return []


class LastOwnerError(Exception):
    """The change would leave the company with no owner."""


def _role_value(role: Optional[object]) -> Optional[str]:
    return role.value if isinstance(role, MembershipRole) else role


async def _owner_count(session: AsyncSession, company_id: uuid.UUID) -> int:
    """The owners. :func:`lock_company_members` already holds their rows."""
    rows = await session.execute(
        select(LLCCompanyMembership.id).where(
            LLCCompanyMembership.company_id == company_id, LLCCompanyMembership.role == MembershipRole.OWNER
        )
    )
    return len(rows.all())


async def lock_company_members(session: AsyncSession, company_id: uuid.UUID) -> None:
    """Serialize this company's membership changes, before any role is read.

    Without it a role read here can be stale by the time it is acted on, so an admin could demote
    someone just made owner. The fixed order keeps two owners demoting each other from deadlocking.
    """
    await session.execute(
        select(LLCCompanyMembership.id)
        .where(LLCCompanyMembership.company_id == company_id)
        .order_by(LLCCompanyMembership.id)
        .with_for_update()
    )


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
    The caller holds :func:`lock_company_members`, taken before it read *current_role*.
    """
    if platform_admin:
        return
    current, new = _role_value(current_role), _role_value(new_role)
    actor_role = await require_company_admin(session, company_id, actor_user_id, for_update=True)
    if _OWNER in (current, new) and actor_role != _OWNER:
        raise NotAuthorisedError(f"role {actor_role!r} may not grant or revoke owner in company {company_id}")
    if current == _OWNER and new != _OWNER and await _owner_count(session, company_id) <= 1:
        raise LastOwnerError(f"company {company_id} would be left with no owner")
