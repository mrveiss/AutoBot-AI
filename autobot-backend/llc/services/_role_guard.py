# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The "role must exist in this company" check, in one place (#18557).

Four role-scoped services (``role_assignment``, ``role_credential``,
``role_tool``, ``role_workflow``) and ``company_os.loaders`` each carried a copy
of this query. They now delegate here, so the tenant-scoping predicate
(``Role.org_id == company_id``, the orphan-reference fix of #14222) cannot
drift between them.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.models.role import Role


async def role_exists_in_company(session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> bool:
    """True when ``role_id`` names a role owned by ``company_id`` (never a role of another company)."""
    result = await session.execute(select(Role.id).where(Role.id == role_id, Role.org_id == company_id))
    return result.scalar_one_or_none() is not None


async def ensure_role_in_company(session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> None:
    """The role must exist *in this company*, else ``ValueError``.

    Without this an assignment could name a role from another company, or
    one that never existed — the orphan-reference shape fixed in #14222.
    Company OS (``company_os.loaders``) raises its own error type from the
    same :func:`role_exists_in_company` query.
    """
    if not await role_exists_in_company(session, company_id, role_id):
        raise ValueError(f"role {role_id} does not exist in company {company_id}")
