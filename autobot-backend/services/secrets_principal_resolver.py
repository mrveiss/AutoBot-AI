# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Build :class:`PrincipalFacts` from the membership tables (#10088 / Task 2.3 part 2).

The DB half of the secrets RBAC layer: turns an authenticated ``user_id`` plus
their RBAC permission set into the :class:`PrincipalFacts` that
``services.secrets_authz`` (part 1, pure) reasons over. Kept thin — three
membership queries plus a permission filter — so the policy stays where the
unit tests are.

``permissions`` is passed in (the router fetches it once via
``RBACMiddleware.get_user_permissions``) rather than fetched here, so the
resolver has no Redis/middleware dependency and is straightforward to test.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from services.secrets_authz import PrincipalFacts
from user_management.models.role import Role, UserRole
from user_management.models.team import TeamMembership
from user_management.models.user import User

#: Permission name that marks an instance administrator (grants system vault + any user vault).
ADMIN_PERMISSION = "admin:access"
_SECRETS_PREFIX = "secrets:"


def _company_role(value: str) -> MembershipRole | None:
    try:
        return MembershipRole(value)
    except ValueError:
        return None


async def resolve_principal_facts(session: AsyncSession, user_id: uuid.UUID, permissions: set[str]) -> PrincipalFacts:
    """Assemble the principal's vault-access facts from RBAC + membership tables.

    A caller that **exists but is deactivated/soft-deleted** resolves to inactive facts that
    reach no vault — residual access from a still-valid session is denied (#10346). An absent
    ``user_id`` (a non-User principal) keeps its existing permission-only behaviour.
    """
    is_active = (await session.execute(select(User.is_active).where(User.id == user_id))).scalar_one_or_none()
    if is_active is False:
        return PrincipalFacts(user_id=str(user_id), active=False)

    is_admin = ADMIN_PERMISSION in permissions
    granted = frozenset(p for p in permissions if p.startswith(_SECRETS_PREFIX))

    team_rows = await session.execute(select(TeamMembership.team_id).where(TeamMembership.user_id == user_id))
    team_ids = frozenset(str(t) for t in team_rows.scalars())

    role_rows = await session.execute(
        select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    )
    role_names = frozenset(role_rows.scalars())

    company_rows = await session.execute(
        select(LLCCompanyMembership.company_id, LLCCompanyMembership.role).where(
            LLCCompanyMembership.user_id == user_id
        )
    )
    company_roles: dict[str, MembershipRole] = {}
    for company_id, role_value in company_rows.all():
        role = _company_role(role_value)
        if role is not None:
            company_roles[str(company_id)] = role

    return PrincipalFacts(
        user_id=str(user_id),
        is_admin=is_admin,
        team_ids=team_ids,
        role_names=role_names,
        company_roles=company_roles,
        granted_permissions=granted,
    )
