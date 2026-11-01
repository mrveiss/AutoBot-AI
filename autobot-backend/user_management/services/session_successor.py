# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A removed user's chat sessions go to a successor, never to nobody (#20029).

Called from ``UserService.reassign_sessions`` when a user is deleted or deactivated. Each session is handed to
the active human ``llc.services.successor.resolve_successor`` names; a person in no company, or a company that
names nobody, falls to an active platform admin; with no admin either the removal is refused, so a session is
never left owned by an account that can no longer act.

**Which company.** A chat session carries a ``company_id`` only when it is a company's agent conversation
(``metadata.company_id``, #12685); an ordinary session has none. So the order tried for a session is: its own
company when the user is a member of it, then the user's other memberships, earliest joined first and the lowest
company id on a tie. The first company that names a successor wins.

**Metadata only.** The owner fields are written through ``update_session_metadata`` (a merge) with the record
``build_owner_metadata`` builds for every other ownership write, and the Redis ownership key through
``set_session_owner(force=True)``. Messages and every other field are not touched.

**Plan first, write after.** Every successor is resolved before the first write, so a refusal changes nothing.
The writes are across two stores and the database transaction, which cannot roll them back together; a write
that fails raises, aborting the removal, and re-running it finishes the rest (it only handles sessions still
owned by the user).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.user_service_errors import SessionReassignError
from chat_history.file_io import run_in_chat_io_executor
from chat_history.session_listing import _extract_chat_id_from_filename
from llc.models.membership import LLCCompanyMembership
from llc.services.successor import resolve_successor
from security.session_ownership import SessionOwnershipValidator, build_owner_metadata
from services.audit.audit import emit_security
from services.audit.taxonomy import AuditAction
from user_management.models.user import User

logger = get_logger(__name__)

SOURCE_SUCCESSOR = "successor"
SOURCE_ADMIN = "admin_fallback"
RESOURCE_TYPE = "chat_session"


@dataclass(frozen=True)
class Handover:
    """One session and who takes it, with the reason that person was chosen."""

    session_id: str
    successor_id: uuid.UUID
    source: str
    company_id: Optional[uuid.UUID] = None


async def owned_sessions(manager: Any, username: str) -> list[tuple[str, Optional[str]]]:
    """``(session_id, company_id)`` for every stored session whose owner is *username*.

    Reads the session files (the durable owner record, ``metadata.owner`` or the older ``username``). A file
    that cannot be read is logged and skipped: its owner cannot be known, so it is not this user's to move.
    """
    names = await run_in_chat_io_executor(os.listdir, manager._get_chats_directory())
    found: list[tuple[str, Optional[str]]] = []
    for name in sorted(names):
        sid = _extract_chat_id_from_filename(name)
        if not sid:
            continue
        try:
            data = await manager.load_full_session(sid) or {}
        except Exception as exc:
            logger.warning("Session %s... unreadable while looking for %s's sessions: %s", sid[:8], username, exc)
            continue
        meta = data.get("metadata") or {}
        if (meta.get("owner") or meta.get("username")) == username:
            found.append((sid, meta.get("company_id") or None))
    return found


async def member_companies(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """The user's companies, earliest joined first, the lowest id on a tie."""
    rows = await db.execute(
        select(LLCCompanyMembership.company_id)
        .where(LLCCompanyMembership.user_id == user_id)
        .order_by(LLCCompanyMembership.created_at, LLCCompanyMembership.company_id)
    )
    return list(rows.scalars().all())


def company_order(session_company: Optional[str], companies: list[uuid.UUID]) -> list[uuid.UUID]:
    """The session's own company first when the user belongs to it, then the rest in membership order."""
    own = [c for c in companies if str(c) == str(session_company)]
    return own + [c for c in companies if c not in own]


async def admin_fallback(db: AsyncSession, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """The earliest-created active platform admin other than *user_id*, or None."""
    stmt = (
        select(User.id)
        .where(User.id != user_id, User.deleted_at.is_(None))
        .filter_by(is_active=True, is_platform_admin=True)
        .order_by(User.created_at, User.id)
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def plan_handovers(
    db: AsyncSession, user_id: uuid.UUID, owned: list[tuple[str, Optional[str]]]
) -> list[Handover]:
    """Resolve a successor for every session, or raise ``SessionReassignError`` when one has none."""
    companies = await member_companies(db, user_id)
    named: dict[uuid.UUID, Optional[uuid.UUID]] = {}
    plan: list[Handover] = []
    for sid, session_company in owned:
        chosen = None
        for company in company_order(session_company, companies):
            if company not in named:
                named[company] = await resolve_successor(db, company, user_id)
            if named[company] is not None:
                chosen = Handover(sid, named[company], SOURCE_SUCCESSOR, company)
                break
        plan.append(chosen or await _admin_handover(db, user_id, sid))
    return plan


async def _admin_handover(db: AsyncSession, user_id: uuid.UUID, session_id: str) -> Handover:
    """The admin fallback for one session; no admin at all refuses the removal."""
    admin = await admin_fallback(db, user_id)
    if admin is None:
        raise SessionReassignError(
            "This user owns chat sessions and no successor or active administrator exists to receive them"
        )
    return Handover(session_id, admin, SOURCE_ADMIN)


async def usernames_of(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """``id -> username`` for the successors."""
    rows = await db.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {uid: name for uid, name in rows.all()}


async def write_owner(manager: Any, validator: Any, session_id: str, successor_id: uuid.UUID, username: str) -> None:
    """Hand one session to *username* in both owner stores; raises ``SessionReassignError`` if either refuses."""
    meta = build_owner_metadata({"username": username, "user_id": str(successor_id)})
    if not await manager.update_session_metadata(session_id, meta):
        raise SessionReassignError(f"Session {session_id} could not be handed over: its file was not updated")
    if not await validator.set_session_owner(session_id, username, force=True):
        raise SessionReassignError(f"Session {session_id} could not be handed over: its ownership key was not set")


def audit_handover(actor: str, user_id: uuid.UUID, h: Handover, outcome: str = "success") -> None:
    """One audit record per session: from whom, to whom, and why that person."""
    emit_security(
        AuditAction.SESSION_REASSIGN,
        actor,
        resource_type=RESOURCE_TYPE,
        resource_id=h.session_id,
        outcome=outcome,
        metadata={
            "from_user_id": str(user_id),
            "to_user_id": str(h.successor_id),
            "source": h.source,
            "company_id": str(h.company_id) if h.company_id else None,
        },
    )


async def _apply(
    manager: Any, validator: Any, actor: str, user_id: uuid.UUID, plan: list[Handover], names: dict
) -> int:
    """Write the plan; each session's audit record says how it went."""
    for h in plan:
        try:
            await write_owner(manager, validator, h.session_id, h.successor_id, names[h.successor_id])
        except SessionReassignError:
            audit_handover(actor, user_id, h, outcome="failed")
            raise
        audit_handover(actor, user_id, h)
    return len(plan)


async def reassign_user_sessions(
    db: AsyncSession, user_id: uuid.UUID, actor: str, manager: Any = None, validator: Any = None
) -> dict[str, int]:
    """Hand every session *user_id* owns to a successor; returns ``{"sessions_reassigned": n}``."""
    user = await db.get(User, user_id)
    if user is None:
        return {"sessions_reassigned": 0}
    manager = manager or _default_manager()
    owned = await owned_sessions(manager, user.username)
    if not owned:
        return {"sessions_reassigned": 0}
    try:
        plan = await plan_handovers(db, user_id, owned)
    except SessionReassignError:
        emit_security(
            AuditAction.SESSION_REASSIGN, actor, resource_type="user", resource_id=str(user_id), outcome="denied"
        )
        raise
    names = await usernames_of(db, {h.successor_id for h in plan})
    validator = validator or await _default_validator()
    return {"sessions_reassigned": await _apply(manager, validator, actor, user_id, plan, names)}


def _default_manager() -> Any:
    from chat_history import ChatHistoryManager  # noqa: PLC0415 - heavy import, only on a removal

    return ChatHistoryManager()


async def _default_validator() -> Any:
    from autobot_shared.redis_client import get_redis_client  # noqa: PLC0415

    redis = await get_redis_client(async_client=True, database="main")
    return SessionOwnershipValidator(redis)
