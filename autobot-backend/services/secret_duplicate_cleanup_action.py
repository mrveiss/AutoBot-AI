# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Executes an APPROVED proposal to remove the losing copies of a duplicated secret (#17850, #17038).

Several envelope secrets can share one ``(owner_vault, name)``. Each copy is verified against its target
(``services/secret_duplicates.py``); when exactly one works, a person is asked to approve removing the others::

    {"action": "secret_duplicate_cleanup", "survivor_id": "...", "removal_ids": ["..."], "secret_ids": ["..."],
     "verified_ids": [...], "reason": "one_verified", "group_digest": "..."}

Ids only: no name, no value, ever. A proposal with ``survivor_id`` null is a case for a person (none or several
copies verified, or no verifier exists): approving it acknowledges it and removes NOTHING, because the approval
carries no choice. The person keeps the copy they choose through the secrets delete route; the migration
(``20261120_117``) stays blocked until the duplicates are gone.

At execution the group is checked again from the database -- every named id must still exist and still share
one ``(owner_vault, name)`` with the survivor, and the survivor must still verify -- so an approval removes only
what a person reviewed. Each removal goes through the ONE guarded delete (``api/secrets_guarded_delete``): a copy
with dependents is refused, kept, and said so. A durable audit entry is written BEFORE each delete, and the
delete does not run when it cannot be written (#17038 rule 3).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from models.approval import ApprovalComment
from models.secret import Secret
from services.approval_execution import register_post_approval_action
from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "secret_duplicate_cleanup"

#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "services.secret_duplicate_proposals"


def _ids(context: dict, key: str) -> list[uuid.UUID]:
    return [uuid.UUID(str(v)) for v in context.get(key) or []]


async def _comment(approval: "Approval", session: "AsyncSession", body: str) -> None:
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()


async def _group_rows(session: "AsyncSession", ids: list[uuid.UUID]) -> list[Secret]:
    return list((await session.execute(select(Secret).where(Secret.id.in_(ids)))).scalars())


def _same_group(rows: list[Secret], ids: list[uuid.UUID]) -> bool:
    """Every named id exists and all share one ``(owner_vault, name)``."""
    return len(rows) == len(set(ids)) and len({(r.owner_vault, r.name) for r in rows}) == 1


async def _survivor_still_works(session: "AsyncSession", survivor: Secret) -> bool:
    from services.envelope_secrets_service import EnvelopeSecretsService
    from services.secret_duplicates import SecretDuplicateGroup, Verdict, verify_copy

    group = SecretDuplicateGroup(survivor.owner_vault, survivor.name, (survivor.id,))
    return await verify_copy(session, EnvelopeSecretsService(), group, survivor.id) is Verdict.VERIFIED


async def _audit(approval: "Approval", result: str, secret_id: uuid.UUID, survivor_id: str, **extra: str) -> bool:
    """One durable audit entry; ids and the outcome only. False when it could not be committed."""
    return await audit_log(
        AuditAction.SECRET_DUPLICATE_CLEANUP.value,
        result=result,
        user_id=approval.decided_by_user,
        resource=f"secret:{secret_id}",
        details={"approval_id": str(approval.id), "survivor_id": survivor_id, **extra},
        durable=True,
    )


async def _guarded_remove(session: "AsyncSession", secret_id: uuid.UUID) -> None:
    """Delete one copy through the ONE guarded delete; a copy with dependents is refused (409), never confirmed."""
    from api.secrets_guarded_delete import guarded_delete
    from services.envelope_secrets_service import EnvelopeSecretsService
    from services.secret_dependency_service import SecretDependencyService

    service = EnvelopeSecretsService()
    await guarded_delete(
        session,
        secret_id,
        dependents=lambda: SecretDependencyService().what_depends_on(session, secret_id=secret_id),
        delete=lambda: service.delete(session, secret_id=secret_id),
    )
    await session.commit()


async def _remove_one(approval: "Approval", session: "AsyncSession", secret_id: uuid.UUID, survivor_id: str) -> str:
    """Audit, guarded-delete, audit. Returns the outcome word for the approval comment."""
    if not await _audit(approval, "attempted", secret_id, survivor_id):
        return "kept (the audit entry could not be written)"
    try:
        await _guarded_remove(session, secret_id)
    except Exception as exc:  # a copy with dependents (409) or a lock timeout: kept, and the reviewer is told
        await _audit(approval, "failed", secret_id, survivor_id, error=type(exc).__name__)
        return f"kept ({type(exc).__name__})"
    await _audit(approval, "success", secret_id, survivor_id)
    return "removed"


async def execute_secret_duplicate_cleanup(approval: "Approval", session: "AsyncSession") -> None:
    """Remove the losing copies an approved gate named, and record what happened."""
    context = approval.context or {}
    survivor_id = context.get("survivor_id")
    if not survivor_id:
        await _comment(approval, session, "No copy was removed: a person must choose which copy to keep.")
        return
    removals = _ids(context, "removal_ids")
    rows = await _group_rows(session, [uuid.UUID(survivor_id), *removals])
    if not removals or not _same_group(rows, [uuid.UUID(survivor_id), *removals]):
        raise ValueError(f"approval {approval.id}: the named copies no longer form one duplicate group")
    survivor = next(r for r in rows if str(r.id) == survivor_id)
    if not await _survivor_still_works(session, survivor):
        raise ValueError(f"approval {approval.id}: the surviving copy no longer verifies; nothing was removed")
    outcomes = [f"{sid}: {await _remove_one(approval, session, sid, survivor_id)}" for sid in removals]
    await _comment(approval, session, "Secret duplicate cleanup (survivor " + survivor_id + "): " + "; ".join(outcomes))


def register_secret_duplicate_cleanup_action() -> None:
    """Idempotent. Server-only and admin-only: removing stored credentials is an admin's decision (#20046)."""
    register_post_approval_action(
        ACTION, execute_secret_duplicate_cleanup, proposed_by=PROPOSED_BY, server_only=True, admin_only=True
    )


__all__ = ["ACTION", "PROPOSED_BY", "execute_secret_duplicate_cleanup", "register_secret_duplicate_cleanup_action"]
