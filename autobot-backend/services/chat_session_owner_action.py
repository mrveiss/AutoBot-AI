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
    for entry in await manager.list_sessions():
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


async def active_user_id(session: "AsyncSession", username: str) -> str | None:
    """The id of the active user *username*, or None: an owner must be someone who exists."""
    query = select(User.id).filter_by(username=username, is_active=True, deleted_at=None)
    found = (await session.execute(query)).scalars().first()
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


async def _write_owner(manager, validator, session_id: str, owner: str, user_id: str) -> str:
    """The file record is the durable one (#14018); a Redis failure after it is reported as partial, not hidden."""
    if not await manager.update_session_metadata(
        session_id, build_owner_metadata({"username": owner, "user_id": user_id})
    ):
        raise ValueError(f"session {session_id} could not be updated")
    try:
        written = await validator.set_session_owner(session_id, owner)
    except Exception as exc:
        logger.warning("Session %s has its owner on file; its Redis record failed: %s", session_id, type(exc).__name__)
        return "partial"
    return "success" if written else "partial"


async def _claim_in_redis(validator, session_id: str, owner: str) -> bool:
    """Atomically take an unowned session; True if *owner* holds it afterwards.

    set_session_owner reads then writes, so two writers can both see no owner; here Redis decides.
    A Redis failure raises: "could not check" must not read as "free".
    """
    key = validator._get_ownership_key(session_id)
    if await validator.redis.set(key, owner, nx=True, ex=validator.ownership_ttl):
        return True
    return await validator.get_session_owner(session_id) == owner


async def _owner_elsewhere(manager, validator, session_id: str, owner: str) -> str | None:
    """Who holds the session if not *owner*. Otherwise *owner* now holds it in Redis.

    The ownership gate may have granted an owner that is only in Redis. The claim is atomic, so
    a grant made while this runs loses to it or wins over it, never both.
    """
    on_file = await manager.get_session_owner(session_id)
    if on_file:
        return on_file
    if await _claim_in_redis(validator, session_id, owner):
        return None
    return await validator.get_session_owner(session_id)


async def execute_owner_assign(approval: "Approval", session: "AsyncSession") -> None:
    """Write the owner an approved proposal named, unless the session has gained one since, on file or in Redis."""
    ctx = approval.context or {}
    session_id, owner = ctx.get("session_id"), ctx.get("owner")
    if not session_id or not owner:
        raise ValueError(f"approval {approval.id} needs a session and an owner")
    self_approved = await is_self_approval(approval, session)
    user_id = await active_user_id(session, owner)
    if user_id is None:
        raise ValueError(f"{owner} is not an active user")
    manager = ChatHistoryManager()
    validator = SessionOwnershipValidator(await get_redis_client(async_client=True, database="main"))
    held_before = await validator.get_session_owner(session_id)
    existing = await _owner_elsewhere(manager, validator, session_id, owner)
    if existing:
        await _comment(approval, session, f"Session {session_id} already belongs to {existing}; nothing changed.")
        await _audit(approval, session_id, "denied", stage="skipped", existing_owner=existing)
        return
    await _audit(approval, session_id, "success", stage="started", owner=owner, self_approval=self_approved)
    try:
        outcome = await _write_owner(manager, validator, session_id, owner, user_id)
    except ValueError:
        if held_before is None:  # our claim alone would let them in with the proposal failed
            await validator.redis.delete(validator._get_ownership_key(session_id))
        raise
    note = " (self-approved)" if self_approved else ""
    tail = "" if outcome == "success" else " Its owner is on file, but the Redis record was not written."
    await _comment(approval, session, f"Session {session_id} now belongs to {owner}{note}.{tail}")
    await _audit(
        approval,
        session_id,
        "success" if outcome == "success" else "error",
        stage=outcome,
        owner=owner,
        self_approval=self_approved,
    )


def register_owner_assign_action() -> None:
    """Idempotent: re-registering just replaces the same key with an equal handler."""
    register_post_approval_action(ACTION, execute_owner_assign, proposed_by=PROPOSED_BY, server_only=True)


__all__ = [
    "ACTION",
    "PROPOSED_BY",
    "active_user_id",
    "execute_owner_assign",
    "ownerless_report",
    "session_is_ownerless",
    "register_owner_assign_action",
]
