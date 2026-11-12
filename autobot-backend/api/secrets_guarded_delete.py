# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE guarded secret delete: authorize, lock the row, check dependents, delete (#21039).

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

Order: the dependents listing is read once WITHOUT the lock -- it enforces the caller's authority
and the secret's existence -- so a caller who may not delete never holds the row. Only then is the
row locked (bounded by ``AUTOBOT_SECRET_DELETE_LOCK_TIMEOUT_MS``; a wait that long is a 503 with a
``Retry-After``, never a stuck pool connection) and the listing repeated under the lock. A
confirmation is bound to what the person was shown: the 409 carries a digest of the dependents and
the confirmed retry echoes it; a set that differs under the lock is refused again, with the new list.
Any failure rolls the transaction back before it returns, so the caller's ``denied``/``failed``
audit record is never written while the row lock is held.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import uuid
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.env_utils import env_int_clamped
from models.secret import Secret

#: Milliseconds a delete waits for the secret row lock before it gives up with a 503.
SECRET_DELETE_LOCK_TIMEOUT_MS = env_int_clamped("AUTOBOT_SECRET_DELETE_LOCK_TIMEOUT_MS", 5000, 100, 60000)

_LOCK_NOT_AVAILABLE = "55P03"  # PostgreSQL lock_not_available (a lock_timeout expiry)


def dependents_digest(deps) -> str:
    """A stable digest of the listed dependents: what a confirmation is bound to (#21039)."""
    lines = sorted(f"{d.dependent_kind}\x00{d.dependent_id}" for d in deps)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def refuse_dependents(deps) -> None:
    """409 with the dependents listed (and their digest) when anything still consumes the secret (#20557).

    The ONE shape of that refusal: the main delete, the envelope user delete and the
    envelope service delete all raise it from here (#20640). The client echoes
    ``dependents_digest`` to confirm exactly this set.
    """
    if deps:
        dependents = [{"dependent_kind": d.dependent_kind, "dependent_id": d.dependent_id} for d in deps]
        raise HTTPException(
            status_code=409,
            detail={
                "code": "secret_has_dependents",
                "message": "Dependents use this secret",
                "dependents": dependents,
                "dependents_digest": dependents_digest(deps),
            },
        )


def refuse_unless_confirmed(deps, confirmed_digest: str | None) -> None:
    """Pass when nothing depends on the secret or the caller confirmed exactly this set; else 409."""
    if not deps:
        return
    if confirmed_digest and hmac.compare_digest(confirmed_digest, dependents_digest(deps)):
        return
    refuse_dependents(deps)


def _is_lock_timeout(exc: DBAPIError) -> bool:
    orig = exc.orig
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return code == _LOCK_NOT_AVAILABLE


def _lock_timeout_refusal() -> HTTPException:
    retry = str(max(1, math.ceil(SECRET_DELETE_LOCK_TIMEOUT_MS / 1000)))
    return HTTPException(
        status_code=503,
        detail={"code": "secret_lock_timeout", "message": "The secret is busy; retry the delete shortly"},
        headers={"Retry-After": retry},
    )


async def lock_secret_row(session: AsyncSession, secret_id: uuid.UUID) -> None:
    """Hold the secret row ``FOR UPDATE`` until the transaction ends, waiting at most the timeout.

    The result is not read: an absent row is reported by the dependents listing or the delete
    that follows (not found), exactly as before. A wait past the timeout is a 503, not a hang.
    """
    try:
        await session.execute(
            text("SELECT set_config('lock_timeout', :ms, true)"), {"ms": f"{SECRET_DELETE_LOCK_TIMEOUT_MS}ms"}
        )
        await session.execute(select(Secret.id).where(Secret.id == secret_id).with_for_update())
    except DBAPIError as exc:
        if _is_lock_timeout(exc):
            raise _lock_timeout_refusal() from exc
        raise


async def guarded_delete(
    session: AsyncSession,
    secret_id: uuid.UUID,
    *,
    dependents: Callable[[], Awaitable[list]],
    delete: Callable[[], Awaitable[None]],
    confirmed_digest: str | None = None,
) -> None:
    """Authorize (unlocked listing), lock the secret, refuse (409) unless the listing is confirmed, delete.

    ``confirmed_digest`` is the ``dependents_digest`` a human was shown by an earlier 409; the
    delete proceeds past dependents only when the set listed under the lock has that digest. The
    caller commits after this returns, which releases the lock. Any exception rolls the
    transaction back first, so a refusal leaves the secret and its dependents untouched and the
    caller's audit write runs with no lock held.
    """
    try:
        await dependents()  # unlocked: enforces the caller's authority and the secret's existence
        await lock_secret_row(session, secret_id)
        refuse_unless_confirmed(await dependents(), confirmed_digest)
        await delete()
    except Exception:
        await session.rollback()
        raise
