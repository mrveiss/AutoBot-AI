# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE guarded secret delete: lock the row, check dependents, delete (#21039).

System of record: Postgres. ``secrets`` and ``secret_dependencies`` are two tables of one
database, and ``secret_dependencies.secret_id`` is a foreign key onto ``secrets.id``. So the
check and the delete share a transaction, and the secret row is the lock that serializes them.

``SELECT ... FOR UPDATE`` on the secret row conflicts with the ``FOR KEY SHARE`` lock the
foreign key takes when a dependent is registered. A registration in flight therefore either
commits before the lock is granted (the listing that follows sees it and refuses) or waits
until the delete commits (and then fails the foreign key, because the secret is gone). A
dependent is never deleted by the cascade without the confirmation the listing asks for.

Every vault-secret delete route calls :func:`guarded_delete`: ``DELETE /api/secrets/{id}``
(``secrets_system_vault.delete_system_vault_secret``) and the envelope user and service
deletes (``envelope_secrets_delete.audited_delete``). The bulk chat delete
(``DELETE /api/secrets/chat/{chat_id}``) deletes only the legacy file store's rows, which
the vault never holds and so no dependent can reference.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.secret import Secret


def refuse_dependents(deps) -> None:
    """409 with the dependents listed when anything still consumes the secret (#20557).

    The ONE shape of that refusal: the main delete, the envelope user delete and the
    envelope service delete all raise it from here (#20640).
    """
    if deps:
        dependents = [{"dependent_kind": d.dependent_kind, "dependent_id": d.dependent_id} for d in deps]
        raise HTTPException(
            status_code=409,
            detail={"code": "secret_has_dependents", "message": "Dependents use this secret", "dependents": dependents},
        )


async def lock_secret_row(session: AsyncSession, secret_id: uuid.UUID) -> None:
    """Hold the secret row ``FOR UPDATE`` until the transaction ends.

    The result is not read: an absent row is reported by the dependents listing or the delete
    that follows (not found), exactly as before.
    """
    await session.execute(select(Secret.id).where(Secret.id == secret_id).with_for_update())


async def guarded_delete(
    session: AsyncSession,
    secret_id: uuid.UUID,
    *,
    dependents: Callable[[], Awaitable[list]] | None,
    delete: Callable[[], Awaitable[None]],
) -> None:
    """Lock the secret, refuse (409) while ``dependents()`` lists any, then ``delete()``.

    ``dependents=None`` skips the listing (a human has seen it and confirmed); the lock is
    still taken. The caller commits after this returns, which releases the lock, and rolls
    back on any exception, so a refusal leaves the secret and its dependents untouched.
    """
    await lock_secret_row(session, secret_id)
    if dependents is not None:
        refuse_dependents(await dependents())
    await delete()
