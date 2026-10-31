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

    ``public_detail`` is the only text a route may show; the message itself can
    carry ids and roles and is for logs. Subclasses override it with a fixed text.
    """

    public_detail = "Forbidden"


async def require_company_admin(
    session: AsyncSession, company_id: uuid.UUID, actor_user_id: Optional[uuid.UUID], *, for_update: bool = False
) -> str:
    """Raise :class:`NotAuthorisedError` unless the actor is owner/admin **here**; return the role.

    Membership is per ``(company, user)``, so being an admin of another company
    grants nothing. A missing actor is refused rather than treated as a trusted
    system call: "no actor means internal" would be a fail-open bypass reachable by
    any caller that omits the argument. *for_update* locks the membership row, so
    the role cannot be revoked or changed before the caller's transaction ends.
    """
    if actor_user_id is None:
        raise NotAuthorisedError("an actor is required for this change")
    name = await membership_role(session, company_id, actor_user_id, for_update=for_update)
    if name is None:
        raise NotAuthorisedError(f"user {actor_user_id} is not a member of company {company_id}")
    if name not in GRANTING_ROLES:
        raise NotAuthorisedError(
            f"membership role {name!r} may not perform this change; " f"one of {sorted(GRANTING_ROLES)} is required"
        )
    return name


async def membership_role(
    session: AsyncSession, company_id: uuid.UUID, actor_user_id: uuid.UUID, *, for_update: bool
) -> Optional[str]:
    stmt = select(LLCCompanyMembership.role).where(
        LLCCompanyMembership.company_id == company_id,
        LLCCompanyMembership.user_id == actor_user_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    role = (await session.execute(stmt)).scalar_one_or_none()
    # ``.value`` explicitly, never ``str()``. The column maps to a
    # ``MembershipRole`` member and ``MembershipRole`` is a str-mixin enum, so
    # ``str(member)`` is "MembershipRole.OWNER" while ``member.value`` is
    # "owner". A defensive ``str()`` here previously denied every owner and
    # admin. ``getattr`` covers a driver that returns a raw string, and an
    # unrecognised value falls through to the caller's refusal -- failing closed.
    return None if role is None else getattr(role, "value", role)


async def may_attach_under(
    session: AsyncSession,
    parent_id: uuid.UUID,
    actor_user_id: Optional[uuid.UUID],
    *,
    platform_admin: bool,
    for_update: bool = False,
) -> bool:
    """Whether the actor may place a company under *parent_id* (#12233, #19634).

    The one rule for both ways a company gains a parent: ``create_company`` with a
    ``parent_org_id`` and ``CompanyService.move``. A platform admin may; anyone
    else must be owner/admin of the parent -- the :func:`require_company_admin`
    level, because a child inherits the parent's knowledge base and ancestor-chain
    visibility, so a plain member must not graft an org under it (maintainer
    decision, 2026-10-26). Callers answer ``False`` with a 404, never a 403, so a
    parent the actor cannot administer is indistinguishable from a missing one.
    *for_update* locks the deciding membership row (the move's under-lock re-check).
    """
    try:
        await require_company_admin_unless_platform(
            session, parent_id, actor_user_id, platform_admin=platform_admin, for_update=for_update
        )
    except NotAuthorisedError:
        return False
    return True


async def require_company_admin_unless_platform(
    session: AsyncSession,
    company_id: uuid.UUID,
    actor_user_id: Optional[uuid.UUID],
    *,
    platform_admin: bool,
    for_update: bool = False,
) -> None:
    """:func:`require_company_admin`, except that a platform admin passes without a membership.

    For the paths a platform admin must be able to operate on companies it does not
    belong to -- re-parenting (#19634). *platform_admin* comes from the caller's
    verified tenant context, never from request data.
    """
    if platform_admin:
        return
    await require_company_admin(session, company_id, actor_user_id, for_update=for_update)
