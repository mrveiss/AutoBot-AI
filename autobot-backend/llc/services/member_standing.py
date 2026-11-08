# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the members list tells a client besides the members (#20073, #13956).

``person_is_active`` and :func:`member_people` describe the people; :func:`viewer_standing` describes
the caller. The standing is computed here from the verified tenant context, never from request data,
so a client can only reflect it. The server still refuses a change the caller may not make.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.models.user import User

from .authz import membership_role
from .membership_policy import grantable_roles


def person_is_active(is_active: Optional[bool], deleted_at: Optional[Any]) -> bool:
    """Whether a person may still be given work (#13956).

    Both the members picker and the org chart ask this, and they must not diverge -- so neither
    computes it inline. Deliberately *not* a filter: the org chart is where a company reads its own
    structure, and dropping someone who has left rewrites that structure silently. The answer is
    rendered, not applied: the surfaces show the person and mark them, and the picker refuses them
    as an assignee.

    A user row that is missing entirely (outer join miss) is inactive: nothing is known about them,
    and "unknown" must never read as "available".
    """
    if deleted_at is not None:
        return False
    # `None` reaches here from an outer-join miss, not from a real column value.
    return bool(is_active)


async def member_people(
    session: AsyncSession, user_ids: Sequence[uuid.UUID]
) -> Tuple[Dict[uuid.UUID, str], Dict[uuid.UUID, bool]]:
    """``(display names, may be given work)`` by user id, for the users that still have a row.

    ``User.full_name`` is a hybrid property, so the canonical "display_name, else username" rule
    is selected in SQL (#13957); a returned row always has the NOT NULL ``username`` to fall back to.
    """
    if not user_ids:
        return {}, {}
    rows = (
        await session.execute(
            select(User.id, User.full_name, User.is_active, User.deleted_at).where(User.id.in_(user_ids))
        )
    ).all()
    return (
        {uid: name for uid, name, _ia, _da in rows},
        {uid: person_is_active(ia, da) for uid, _name, ia, da in rows},
    )


async def viewer_standing(
    session: AsyncSession, company_id: uuid.UUID, viewer_id: Optional[uuid.UUID], *, platform_admin: bool
) -> Dict[str, Any]:
    """The caller's own role here and the roles they may grant or revoke.

    ``viewer_role`` is ``None`` for a caller with no membership (a platform admin in a company it
    does not belong to). ``viewer_grantable_roles`` is what :mod:`membership_policy` would allow.
    """
    role = None if viewer_id is None else await membership_role(session, company_id, viewer_id, for_update=False)
    return {
        "viewer_role": role,
        "viewer_grantable_roles": grantable_roles(role, platform_admin=platform_admin),
    }
