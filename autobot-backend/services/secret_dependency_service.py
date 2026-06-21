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
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    ) -> SecretDependency | None:
        """Record that ``dependent_kind:dependent_id`` depends on *secret_id*.

        Idempotent and concurrency-safe: a same-key insert hits ``ON CONFLICT DO NOTHING``
        on the ``(secret_id, dependent_kind, dependent_id)`` unique constraint rather than
        raising, and the existing-or-new row is returned (``None`` only if a concurrent
        ``unregister`` deleted it between the insert and the read-back).
        """
        if dependent_kind not in DEPENDENT_KINDS:
            raise ValueError(f"unknown dependent_kind {dependent_kind!r}; expected one of {DEPENDENT_KINDS}")
        await session.execute(
            pg_insert(SecretDependency)
            .values(
                id=uuid.uuid4(),
                secret_id=secret_id,
                dependent_kind=dependent_kind,
                dependent_id=dependent_id,
                company_id=company_id,
                created_by=created_by,
            )
            .on_conflict_do_nothing(constraint="uq_secret_dependencies_secret_dependent")
        )
        await session.flush()
        return (
            await session.execute(
                select(SecretDependency).where(
                    SecretDependency.secret_id == secret_id,
                    SecretDependency.dependent_kind == dependent_kind,
                    SecretDependency.dependent_id == dependent_id,
                )
            )
        ).scalar_one_or_none()

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
