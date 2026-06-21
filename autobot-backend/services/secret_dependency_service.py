# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Register + query what depends on a secret (#10088 Task 8.2 / 8.4 what-depends-on).

The dependency counterpart to ``secrets_access_audit`` (who-has-access). Records that a
service / agent / workflow consumes a secret, so a secret's blast radius — the
rotation/revocation impact list — is one indexed lookup. Pure metadata; no decryption.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.secret_dependency import DEPENDENT_KINDS, SecretDependency


class SecretDependencyService:
    """CRUD + queries over ``secret_dependencies``. Caller owns the transaction."""

    async def register(
        self,
        session: AsyncSession,
        *,
        secret_id: uuid.UUID,
        dependent_kind: str,
        dependent_id: str,
        company_id: uuid.UUID | None = None,
        created_by: uuid.UUID | None = None,
    ) -> SecretDependency:
        """Idempotently record that ``dependent_kind:dependent_id`` depends on *secret_id*."""
        if dependent_kind not in DEPENDENT_KINDS:
            raise ValueError(f"unknown dependent_kind {dependent_kind!r}; expected one of {DEPENDENT_KINDS}")
        existing = (
            await session.execute(
                select(SecretDependency).where(
                    SecretDependency.secret_id == secret_id,
                    SecretDependency.dependent_kind == dependent_kind,
                    SecretDependency.dependent_id == dependent_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        dep = SecretDependency(
            secret_id=secret_id,
            dependent_kind=dependent_kind,
            dependent_id=dependent_id,
            company_id=company_id,
            created_by=created_by,
        )
        session.add(dep)
        await session.flush()
        return dep

    async def what_depends_on(self, session: AsyncSession, *, secret_id: uuid.UUID) -> list[SecretDependency]:
        """Every consumer of *secret_id* — the rotation/revocation impact list."""
        rows = await session.execute(
            select(SecretDependency)
            .where(SecretDependency.secret_id == secret_id)
            .order_by(SecretDependency.dependent_kind, SecretDependency.dependent_id)
        )
        return list(rows.scalars())

    async def secrets_for_dependent(
        self, session: AsyncSession, *, dependent_kind: str, dependent_id: str
    ) -> list[uuid.UUID]:
        """The secret ids a given consumer depends on."""
        rows = await session.execute(
            select(SecretDependency.secret_id).where(
                SecretDependency.dependent_kind == dependent_kind,
                SecretDependency.dependent_id == dependent_id,
            )
        )
        return list(rows.scalars())

    async def unregister(
        self, session: AsyncSession, *, secret_id: uuid.UUID, dependent_kind: str, dependent_id: str
    ) -> int:
        """Drop one dependency row. Returns the number removed (0 or 1)."""
        result = await session.execute(
            delete(SecretDependency).where(
                SecretDependency.secret_id == secret_id,
                SecretDependency.dependent_kind == dependent_kind,
                SecretDependency.dependent_id == dependent_id,
            )
        )
        return result.rowcount or 0
