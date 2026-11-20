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
carries no choice. That is also the path for a secret type with no verifier, which a proposal can never name a
survivor for. The person keeps the copy they choose through the secrets delete route (``DELETE /api/secrets/<id>``);
the migration (``20261120_117``) stays blocked until the duplicates are gone.

At execution the group is checked again from the database -- every named id must still exist, still share one
``(owner_vault, name)`` with the survivor and carry the rotation ``version`` it was probed at (a copy rotated since
is refused and needs a new proposal), and the survivor must still verify -- so an approval removes only what a
person reviewed. Each removal re-locks the survivor in its own transaction and is refused if the survivor is gone.
Each removal goes through the ONE guarded delete (``api/secrets_guarded_delete``): a copy with dependents is
refused, kept, and said so. A durable audit entry is written BEFORE each delete, and the
delete does not run when it cannot be written (#17038 rule 3).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
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


@dataclass(frozen=True)
class _Review:
    """What the approval said, read once into plain values.

    A rollback inside the guarded delete expires the ORM ``Approval``; reading an attribute of an expired object in
    async code raises. Everything the audit and the comments need is therefore copied out up front.
    """

    approval_id: str
    decider: str | None
    survivor_id: uuid.UUID
    survivor_version: int
    removals: list[uuid.UUID]
    versions: dict[str, int]


def _ids(context: dict, key: str) -> list[uuid.UUID]:
    return [uuid.UUID(str(v)) for v in context.get(key) or []]


async def _comment(approval: "Approval", session: "AsyncSession", body: str) -> None:
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()


async def _group_rows(session: "AsyncSession", ids: list[uuid.UUID]) -> list[Secret]:
    return list((await session.execute(select(Secret).where(Secret.id.in_(ids)))).scalars())


def _unchanged_group(rows: list[Secret], review: _Review) -> bool:
    """Every named id exists, all share one ``(owner_vault, name)``, and none was rotated since it was probed."""
    ids = [review.survivor_id, *review.removals]
    if len(rows) != len(set(ids)) or len({(r.owner_vault, r.name) for r in rows}) != 1:
        return False
    return all(str(r.id) in review.versions and r.version == review.versions[str(r.id)] for r in rows)


async def _survivor_still_works(session: "AsyncSession", survivor: Secret) -> bool:
    from services.envelope_secrets_service import EnvelopeSecretsService
    from services.secret_duplicates import SecretDuplicateGroup, Verdict, verify_copy

    group = SecretDuplicateGroup(survivor.owner_vault, survivor.name, (survivor.id,))
    return await verify_copy(session, EnvelopeSecretsService(), group, survivor.id) is Verdict.VERIFIED


async def _audit(review: _Review, result: str, secret_id: uuid.UUID, **extra: str) -> bool:
    """One durable audit entry; ids and the outcome only. False when it could not be committed."""
    return await audit_log(
        AuditAction.SECRET_DUPLICATE_CLEANUP.value,
        result=result,
        user_id=review.decider,
        resource=f"secret:{secret_id}",
        details={"approval_id": review.approval_id, "survivor_id": str(review.survivor_id), **extra},
        durable=True,
    )


async def _hold_survivor(session: "AsyncSession", review: _Review) -> None:
    """Lock the survivor row and require it to be there, unrotated: a removal never outlives its survivor.

    Runs inside each removal's own transaction (after the removal row's lock), so a concurrent delete of the survivor
    either committed first -- the removal is refused -- or waits until this removal commits (#17850).
    """
    row = (
        await session.execute(select(Secret).where(Secret.id == review.survivor_id).with_for_update())
    ).scalar_one_or_none()
    if row is None or row.version != review.survivor_version:
        raise ValueError("the surviving copy is gone or changed; nothing more is removed")


async def _guarded_remove(session: "AsyncSession", secret_id: uuid.UUID, review: _Review) -> None:
    """Delete one copy through the ONE guarded delete; a copy with dependents is refused (409), never confirmed."""
    from api.secrets_guarded_delete import guarded_delete
    from services.envelope_secrets_service import EnvelopeSecretsService
    from services.secret_dependency_service import SecretDependencyService

    service = EnvelopeSecretsService()

    async def delete() -> None:
        await _hold_survivor(session, review)
        await service.delete(session, secret_id=secret_id)

    deps = lambda: SecretDependencyService().what_depends_on(session, secret_id=secret_id)  # noqa: E731
    await guarded_delete(session, secret_id, dependents=deps, delete=delete)
    await session.commit()


async def _remove_one(approval: "Approval", session: "AsyncSession", secret_id: uuid.UUID, review: _Review) -> str:
    """Audit, guarded-delete, audit. Returns the outcome word for the approval comment."""
    if not await _audit(review, "attempted", secret_id):
        return "kept (the audit entry could not be written)"
    try:
        await _guarded_remove(session, secret_id, review)
    except Exception as exc:  # a copy with dependents (409), a changed survivor or a lock timeout: kept, and said so
        await session.refresh(approval)  # the guarded delete's rollback expired it; later steps read it
        await _audit(review, "failed", secret_id, error=type(exc).__name__)
        return f"kept ({type(exc).__name__})"
    await _audit(review, "success", secret_id)
    return "removed"


async def _review_of(approval: "Approval", session: "AsyncSession") -> _Review:
    """Parse and re-check the approved context against the database; raises (recorded durably) if it cannot stand."""
    context = approval.context or {}
    survivor_id, removals = uuid.UUID(context["survivor_id"]), _ids(context, "removal_ids")
    versions = {str(k): int(v) for k, v in (context.get("versions") or {}).items()}
    rows = await _group_rows(session, [survivor_id, *removals])
    review = _Review(
        str(approval.id), approval.decided_by_user, survivor_id, versions.get(str(survivor_id), -1), removals, versions
    )
    if not removals or not _unchanged_group(rows, review):
        raise ValueError(f"approval {approval.id}: the named copies changed since they were probed; propose again")
    survivor = next(r for r in rows if r.id == survivor_id)
    if not await _survivor_still_works(session, survivor):
        raise ValueError(f"approval {approval.id}: the surviving copy no longer verifies; nothing was removed")
    return review


async def execute_secret_duplicate_cleanup(approval: "Approval", session: "AsyncSession") -> None:
    """Remove the losing copies an approved gate named, and record what happened."""
    if not (approval.context or {}).get("survivor_id"):
        await _comment(approval, session, "No copy was removed: a person must choose which copy to keep.")
        return
    review = await _review_of(approval, session)
    outcomes = [f"{sid}: {await _remove_one(approval, session, sid, review)}" for sid in review.removals]
    await _comment(
        approval, session, f"Secret duplicate cleanup (survivor {review.survivor_id}): " + "; ".join(outcomes)
    )


def register_secret_duplicate_cleanup_action() -> None:
    """Idempotent. Server-only and admin-only: removing stored credentials is an admin's decision (#20046)."""
    register_post_approval_action(
        ACTION, execute_secret_duplicate_cleanup, proposed_by=PROPOSED_BY, server_only=True, admin_only=True
    )


__all__ = ["ACTION", "PROPOSED_BY", "execute_secret_duplicate_cleanup", "register_secret_duplicate_cleanup_action"]
