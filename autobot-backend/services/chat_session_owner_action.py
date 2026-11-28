# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Give an ownerless chat session an owner only through an approved proposal (#20030, #17038).

An ownerless session is a defect (#20025), and who should own one is a person's decision: it is never
inferred from whoever reads first. An admin names the owner in a proposal, a human approves it, and only
then is the owner written, with a comment on the approval and an audit entry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from chat_history import ChatHistoryManager
from models.approval import ApprovalComment
from security.session_owner_errors import SessionOwnerUnreadable
from security.session_ownership import SessionOwnershipValidator, build_owner_metadata
from services.approval_execution import register_post_approval_action
from services.approval_four_eyes import is_self_approval
from services.audit_logger import audit_log
from user_management.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

#: The ``context["action"]`` value a proposal names to route here.
ACTION = "chat_session_owner_assign"
#: The production module that PROPOSES this action (#17315).
PROPOSED_BY = "api.admin_ownerless_chat_sessions"


async def ownerless_report(manager) -> tuple[list[str], list[str]]:
    """Read only: session ids with no recorded owner, and those whose owner could not be read.

    An unreadable owner is not "no owner", so it is listed apart and cannot be proposed (#14033).
    """
    ownerless: list[str] = []
    unreadable: list[str] = []
    for entry in await manager.list_session_ids():
        session_id = entry["chatId"]
        try:
            if not await manager.get_session_owner(session_id):
                ownerless.append(session_id)
        except SessionOwnerUnreadable as exc:
            logger.warning("Could not read the owner of session %s: %s", session_id, exc)
            unreadable.append(session_id)
    return ownerless, unreadable


async def session_is_ownerless(manager, session_id: str) -> bool:
    """One session's answer, for a proposal: the full report reads every session on disk.

    A session whose id is invalid or whose owner cannot be read is not ownerless (#14033).
    """
    try:
        return await manager.session_exists(session_id) and not await manager.get_session_owner(session_id)
    except (ValueError, SessionOwnerUnreadable):
        return False


async def active_user_id(session: "AsyncSession", username: str, lock: bool = False) -> str | None:
    """The id of the active user *username*, or None: an owner must be someone who exists.

    *lock* takes the row ``FOR UPDATE`` until the transaction ends, as user removal does
    (``session_successor``): a removal then waits for the assignment, or the assignment sees it.
    """
    query = select(User.id).filter_by(username=username, is_active=True, deleted_at=None)
    found = (await session.execute(query.with_for_update() if lock else query)).scalars().first()
    return str(found) if found else None


async def _audit(approval: "Approval", session_id: str, result: str, **details: object) -> None:
    await audit_log(
        "session.owner_assign",
        result=result,
        user_id=approval.decided_by_user,
        resource=session_id,
        details={"approval_id": str(approval.id), **details},
    )


async def _comment(approval: "Approval", session: "AsyncSession", body: str) -> None:
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=body))
    await session.commit()


async def _write_owner(manager, session_id: str, owner: str, user_id: str) -> None:
    """The file record is the durable one (#14018); the Redis record was taken by the claim before it."""
    if not await manager.update_session_metadata(
        session_id, build_owner_metadata({"username": owner, "user_id": user_id})
    ):
        raise ValueError(f"session {session_id} could not be updated")


async def _claim(validator, session_id: str, owner: str) -> str | None:
    """Take the unowned session in Redis for *owner*: None if it holds it now, else who holds it.

    ``set_session_owner`` is the one atomic first-writer path, shared with the ordinary grant. A claim
    refused while nobody holds the key afterwards (it expired in between) is an error: nothing is written.
    """
    if await validator.set_session_owner(session_id, owner):
        return None
    holder = await validator.get_session_owner(session_id)
    if holder is None:
        raise ValueError(f"session {session_id} could not be claimed; nothing was written")
    return holder


async def _owner_elsewhere(manager, validator, session_id: str, owner: str) -> str | None:
    """Who holds the session if not *owner*. Otherwise *owner* now holds it in Redis.

    The ownership gate may have granted an owner that is only in Redis. The claim is atomic, so
    a grant made while this runs loses to it or wins over it, never both.
    """
    on_file = await manager.get_session_owner(session_id)
    if on_file:
        return on_file
    return await _claim(validator, session_id, owner)


async def _release_claim(validator, session_id: str, owner: str) -> None:
    try:
        await validator.redis.delete(validator._get_ownership_key(session_id))
        await validator.redis.srem(validator._get_user_sessions_key(owner), session_id)
    except Exception as exc:  # the failure that brought us here is the one to raise
        logger.warning("Could not release the claim on session %s: %s", session_id, type(exc).__name__)


async def _attempt(approval: "Approval", manager, validator, claimed: bool, user_id: str, self_approved: bool) -> None:
    """Audit, then write the owner. A claim this run alone took is dropped on ANY failure, cancellation included.

    Our claim alone would let the owner in with the proposal failed, and a cancelled request would
    otherwise leave it until the TTL (24 hours) expired.
    """
    ctx = approval.context
    session_id, owner = ctx["session_id"], ctx["owner"]
    try:
        await _audit(approval, session_id, "attempted", stage="started", owner=owner, self_approval=self_approved)
        await _write_owner(manager, session_id, owner, user_id)
    except BaseException:
        if claimed:
            await _release_claim(validator, session_id, owner)
        raise


async def _review_owner_assign(approval: "Approval", session: "AsyncSession") -> bool:
    """The four-eyes check, run before the decision commits (as every four-eyes action does) and again here."""
    return await is_self_approval(approval, session, what="the owner assignment")


async def execute_owner_assign(approval: "Approval", session: "AsyncSession") -> None:
    """Write the owner an approved proposal named, unless the session has gained one since, on file or in Redis."""
    ctx = approval.context or {}
    session_id, owner = ctx.get("session_id"), ctx.get("owner")
    if not session_id or not owner:
        raise ValueError(f"approval {approval.id} needs a session and an owner")
    self_approved = await _review_owner_assign(approval, session)
    user_id = await active_user_id(session, owner, lock=True)
    if user_id is None:
        raise ValueError(f"{owner} is not an active user")
    if user_id != ctx.get("owner_id"):
        raise ValueError(f"{owner} no longer names the account that was proposed")
    manager = ChatHistoryManager()
    validator = SessionOwnershipValidator(await get_redis_client(async_client=True, database="main"))
    held_before = await validator.get_session_owner(session_id)
    existing = await _owner_elsewhere(manager, validator, session_id, owner)
    if existing:
        await _comment(approval, session, f"Session {session_id} already belongs to {existing}; nothing changed.")
        await _audit(approval, session_id, "denied", stage="skipped", existing_owner=existing)
        return
    await _attempt(approval, manager, validator, held_before is None, user_id, self_approved)
    note = " (self-approved)" if self_approved else ""
    await _comment(approval, session, f"Session {session_id} now belongs to {owner}{note}.")
    await _audit(approval, session_id, "success", stage="success", owner=owner, self_approval=self_approved)


def register_owner_assign_action() -> None:
    """Idempotent: re-registering just replaces the same key with an equal handler."""
    register_post_approval_action(
        ACTION, execute_owner_assign, proposed_by=PROPOSED_BY, server_only=True, review=_review_owner_assign
    )


__all__ = [
    "ACTION",
    "PROPOSED_BY",
    "active_user_id",
    "execute_owner_assign",
    "ownerless_report",
    "session_is_ownerless",
    "register_owner_assign_action",
]
