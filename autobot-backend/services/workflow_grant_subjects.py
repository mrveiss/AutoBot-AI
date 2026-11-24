# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflow grant subjects are user ids; username-keyed rows are rewritten only after approval (#22180, #17038).

The per-workflow ACL keys its subject on the canonical principal id. A grant row still keyed by a username
matches no principal, so it grants nothing (fail closed) until a human approves its mapping to a user id.
``plan_remap`` reads the rows and maps each to an id through the users table; rows that cannot be mapped are
reported and left alone. ``apply_remap`` is reachable only from the post-approval handler: it re-checks every
row (same id, same old subject, the name still naming the same account) before it rewrites ``user_id``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from autobot_shared.logging_manager import get_logger
from models.workflow_permission import WorkflowPermission
from services.approval_execution import register_post_approval_action
from services.audit.taxonomy import AuditAction
from services.kb_cleanup_proposals import record_cleanup_outcome, require_context
from user_management.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "workflow_grant_subject_remap"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "api.workflow_permissions"
#: One proposal covers the whole table, so a pending one is looked up by this scope.
SCOPE = "workflow_permissions"


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


async def known_user_ids(session: "AsyncSession", candidates: set[str]) -> set[str]:
    """The members of *candidates* that are the id of a user row (any state: an id is never reused)."""
    parsed = {c: u for c in candidates if (u := _as_uuid(c)) is not None}
    if not parsed:
        return set()
    found = (await session.execute(select(User.id).where(User.id.in_(set(parsed.values()))))).scalars().all()
    existing = {str(f) for f in found}
    return {c for c, u in parsed.items() if str(u) in existing}


def _usable_user():
    """The filter a grant target must pass: an active, not-deleted account."""
    return (User.is_active.is_(True), User.deleted_at.is_(None))


async def usernames_to_ids(session: "AsyncSession", usernames: set[str]) -> dict[str, str]:
    """One query: name -> id for active, not-deleted users. A name held by several rows is left out (ambiguous)."""
    if not usernames:
        return {}
    query = select(User.username, User.id).where(User.username.in_(usernames), *_usable_user())
    seen: dict[str, list[str]] = {}
    for name, found in (await session.execute(query)).all():
        seen.setdefault(name, []).append(str(found))
    return {name: ids[0] for name, ids in seen.items() if len(ids) == 1}


async def username_to_id(session: "AsyncSession", username: str) -> str | None:
    """The id of the one active, not-deleted user named *username*, or None."""
    return (await usernames_to_ids(session, {username})).get(username)


async def usable_grant_target_id(session: "AsyncSession", candidate: uuid.UUID) -> str | None:
    """*candidate* as a string when it is the id of an active, not-deleted user, else None."""
    query = select(User.id).where(User.id == candidate, *_usable_user())
    return str(candidate) if (await session.execute(query)).scalars().first() is not None else None


async def resolve_user_ref(session: "AsyncSession", ref: str) -> str | None:
    """Resolve a grant target given as a user id or a username to the id, or None.

    Both paths accept only an active, not-deleted account. An id-shaped value is looked up as an id only, so a
    username can never shadow another user's id.
    """
    ref = (ref or "").strip()
    if not ref:
        return None
    if (as_id := _as_uuid(ref)) is not None:
        return await usable_grant_target_id(session, as_id)
    return await username_to_id(session, ref)


async def plan_remap(session: "AsyncSession") -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """(mappings, unmapped) for every grant row whose subject is not a known user id. Read only."""
    rows = (await session.execute(select(WorkflowPermission))).scalars().all()
    known = await known_user_ids(session, {r.user_id for r in rows})
    stale = sorted((r for r in rows if r.user_id not in known), key=lambda r: (r.workflow_id, r.user_id))
    ids = await usernames_to_ids(session, {r.user_id for r in stale})
    mappings: list[dict[str, str]] = []
    unmapped: list[dict[str, str]] = []
    for row in stale:
        entry = {"permission_id": str(row.id), "workflow_id": row.workflow_id, "old": row.user_id}
        if (new := ids.get(row.user_id)) is None:
            unmapped.append(entry)
        else:
            mappings.append({**entry, "new": new})
    return mappings, unmapped


#: Not a failure: the row already carries the proposed subject (an applied proposal replayed).
_APPLIED = "already applied"


async def _recheck(session: "AsyncSession", item: dict[str, Any]) -> str | None:
    """Why *item* must not be applied now (``_APPLIED`` when it already is), or None when it still holds."""
    row = await session.get(WorkflowPermission, uuid.UUID(item["permission_id"]))
    if row is not None and row.user_id == item["new"] and row.workflow_id == item["workflow_id"]:
        return _APPLIED
    if row is None or row.user_id != item["old"] or row.workflow_id != item["workflow_id"]:
        return "the row no longer matches the proposal"
    if await username_to_id(session, item["old"]) != item["new"]:
        return "the name no longer identifies the proposed account"
    clash = select(WorkflowPermission.id).where(
        WorkflowPermission.workflow_id == item["workflow_id"], WorkflowPermission.user_id == item["new"]
    )
    if (await session.execute(clash)).first() is not None:
        return "that user already holds a grant on the workflow"
    return None


async def _apply_one(session: "AsyncSession", item: dict[str, Any]) -> str | None:
    """Rewrite one re-checked row; None on success, ``_APPLIED`` for a replay, else why it was left untouched."""
    try:
        if (why := await _recheck(session, item)) is not None:
            return why
        stmt = (
            update(WorkflowPermission)
            .where(WorkflowPermission.id == uuid.UUID(item["permission_id"]), WorkflowPermission.user_id == item["old"])
            .values(user_id=item["new"])
        )
        done = (await session.execute(stmt)).rowcount == 1
        await session.commit()
        return None if done else "the row changed while it was being rewritten"
    except (IntegrityError, ValueError, KeyError) as exc:
        await session.rollback()
        logger.warning("Grant remap row %s was not applied: %s", item.get("permission_id"), type(exc).__name__)
        return "the row could not be rewritten"


async def apply_remap(session: "AsyncSession", mappings: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
    """Apply the approved mappings; (rewritten now, already applied, one reason line per row left untouched)."""
    rewritten, already, skipped = 0, 0, []
    for item in mappings:
        why = await _apply_one(session, item)
        if why is None:
            rewritten += 1
        elif why == _APPLIED:
            already += 1
        else:
            skipped.append(f"{item.get('workflow_id')}:{item.get('old')}: {why}")
    return rewritten, already, skipped


async def execute_grant_remap(approval: "Approval", session: "AsyncSession") -> None:
    """Rewrite the grant subjects an approved gate named, and record what happened."""
    (mappings,) = require_context(approval, "mappings")
    rewritten, already, skipped = await apply_remap(session, mappings)
    done = not skipped
    await record_cleanup_outcome(
        approval,
        session,
        operation=AuditAction.WORKFLOW_GRANT_REMAP.value,
        done=done,
        resource=SCOPE,
        summary=f"Grant subject rewrite ({rewritten} of {len(mappings)} rows rewritten, {already} already applied)",
        reason="; ".join(skipped) or None,
    )


def register_grant_remap_action() -> None:
    """Idempotent. Server-only and admin-decided: this approves rewriting stored access-control rows."""
    register_post_approval_action(
        ACTION, execute_grant_remap, proposed_by=PROPOSED_BY, server_only=True, admin_only=True
    )
