# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The company-admin gate, in one place (#14221).

Extracted after a security review of #14324 found a privilege escalation of my
own making. Permission *granting* was carefully gated on owner/admin, but the
routes exposing role **occupancy** were not — so any member of a company could
call ``POST /llc/roles/{company_id}/{role_id}/holders``, assign themselves to a
role an admin had granted powerful permissions to, and inherit them
immediately. ``effective_permissions()`` honours any open tenure and has no way
to know who created it, so the admin-only grant path was fully bypassable.

The lesson worth keeping: a gate on *who may grant* is worthless while *who may
hold* is ungated. Both halves have to be closed, and the reason they were not is
that the check lived inside one service instead of somewhere all of them share.

Hence this module. Every company-scoped mutation routes through
:func:`require_company_admin`, so adding a new mutating service means importing
a gate rather than remembering to re-implement one — the failure mode that
produced the escalation in the first place.

Deliberately **not** on ``LLCServiceBase``: inheriting a security check makes it
invisible at the call site, and a subclass that simply never calls it looks
identical to one that does.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MembershipRole
from ..models.membership import LLCCompanyMembership

#: Membership roles permitted to change a company's roles, occupancy,
#: permissions and workflow attachments.
GRANTING_ROLES = frozenset({MembershipRole.OWNER.value, MembershipRole.ADMIN.value})


class NotAuthorisedError(Exception):
    """The actor may not perform this change in this company.

    Distinct from ``ValueError`` on purpose: "you may not do this" and "what you
    asked for makes no sense" map to different HTTP statuses, and collapsing
    them would make a 403 indistinguishable from a 400 at the route layer.
    """


async def require_company_admin(
    session: AsyncSession, company_id: uuid.UUID, actor_user_id: Optional[uuid.UUID]
) -> None:
    """Raise :class:`NotAuthorisedError` unless the actor is owner/admin **here**.

    Membership is per ``(company, user)``, so being an admin of another company
    grants nothing — the "not all users have access to all Company OS
    companies" requirement, applied to every mutating path.

    A missing actor is refused rather than treated as a trusted system call.
    An implicit "no actor means internal" would be a fail-open bypass reachable
    by any caller that simply omits the argument.
    """
    if actor_user_id is None:
        raise NotAuthorisedError("an actor is required for this change")

    result = await session.execute(
        select(LLCCompanyMembership.role).where(
            LLCCompanyMembership.company_id == company_id,
            LLCCompanyMembership.user_id == actor_user_id,
        )
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise NotAuthorisedError(f"user {actor_user_id} is not a member of company {company_id}")

    # ``.value`` explicitly, never ``str()``. The column maps to a
    # ``MembershipRole`` member and ``MembershipRole`` is a str-mixin enum, so
    # ``str(member)`` is "MembershipRole.OWNER" while ``member.value`` is
    # "owner". A defensive ``str()`` here previously denied every owner and
    # admin. ``getattr`` covers a driver that returns a raw string, and an
    # unrecognised value falls through to the refusal below — failing closed.
    name = getattr(role, "value", role)
    if name not in GRANTING_ROLES:
        raise NotAuthorisedError(
            f"membership role {name!r} may not perform this change; " f"one of {sorted(GRANTING_ROLES)} is required"
        )
