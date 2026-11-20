# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Durable participant set of a shared chat, with its Redis projection (#18890).

The system of record is the ``chat_session_shares`` table (``models/session_share.py``). The Redis sets
``session:shared_with:<session>`` and ``user:shared_sessions:<user>`` are projections: they carry NO TTL (a
share lasts until the owner unshares it) and are rebuilt from the table on a read-miss.

Its own module because ``security/session_ownership.py`` is at its recorded size ceiling.
"""

import asyncio

from sqlalchemy import delete, select

from autobot_shared.logging_manager import get_logger
from autobot_shared.store_authority import system_of_record
from models.session_share import SessionShare

SYSTEM_OF_RECORD = system_of_record("session_shares")

logger = get_logger(__name__)

SESSION_KEY = "session:shared_with:%s"
USER_KEY = "user:shared_sessions:%s"
_SESSION_KEY_PATTERN = SESSION_KEY % "*"
#: ``shared_by`` recorded for a share that predates the table and was copied out of Redis.
ADOPTED_SHARER = "migrated-from-redis"

_adopt_lock = asyncio.Lock()
_adopted = False


def _factory():
    from user_management.database import get_async_session_factory

    return get_async_session_factory()


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else value


async def durable_add(session_id: str, user_ids: list[str], shared_by: str) -> None:
    """Record participants in the system of record (idempotent per participant)."""
    async with _factory()() as db:
        for user_id in user_ids:
            await db.merge(SessionShare(session_id=session_id, user_id=user_id, shared_by=shared_by))
        await db.commit()


async def durable_remove(session_id: str, user_id: str) -> bool:
    """Delete one participant; True when a row existed."""
    async with _factory()() as db:
        result = await db.execute(
            delete(SessionShare).where(SessionShare.session_id == session_id, SessionShare.user_id == user_id)
        )
        await db.commit()
        return bool(result.rowcount)


async def durable_participants(session_id: str) -> list[str]:
    """Everyone the chat is shared with, from the system of record."""
    async with _factory()() as db:
        rows = await db.execute(select(SessionShare.user_id).where(SessionShare.session_id == session_id))
        return list(rows.scalars().all())


async def durable_sessions_for(user_id: str) -> list[str]:
    """Every chat shared with *user_id*, from the system of record."""
    async with _factory()() as db:
        rows = await db.execute(select(SessionShare.session_id).where(SessionShare.user_id == user_id))
        return list(rows.scalars().all())


async def _project(redis, key: str, members: list[str]) -> None:
    """Write a projection set with no TTL; clearing any TTL a pre-#18890 key still carries."""
    if members:
        await redis.sadd(key, *members)
        await redis.persist(key)


async def project_share(redis, session_id: str, user_ids: list[str]) -> None:
    """Write-through of a share into both Redis sets."""
    await _project(redis, SESSION_KEY % session_id, list(user_ids))
    for user_id in user_ids:
        await _project(redis, USER_KEY % user_id, [session_id])


async def drop_projection(redis, session_id: str, user_id: str) -> None:
    """Remove one participant from both Redis sets."""
    await redis.srem(SESSION_KEY % session_id, user_id)
    await redis.srem(USER_KEY % user_id, session_id)


async def adopt_redis_shares(redis) -> int:
    """Copy shares that exist only in Redis (pre-#18890 installs) into the table, once per process.

    Idempotent: ``durable_add`` merges. The flag is set only after every set was copied, so a failure is
    retried on the next call rather than skipped.
    """
    global _adopted
    if _adopted:
        return 0
    async with _adopt_lock:
        if _adopted:
            return 0
        copied = 0
        async for raw in redis.scan_iter(match=_SESSION_KEY_PATTERN, count=500):
            session_id = _text(raw).split(":", 2)[2]
            members = [_text(m) for m in await redis.smembers(raw)]
            if members:
                await durable_add(session_id, members, ADOPTED_SHARER)
                await project_share(redis, session_id, members)
                copied += len(members)
        _adopted = True
        if copied:
            logger.info("Adopted %d Redis-only chat shares into the durable table (#18890)", copied)
        return copied


async def rebuild_session_projection(redis, session_id: str) -> list[str]:
    """Repopulate a chat's Redis sets from the table (read-miss rebuild)."""
    await adopt_redis_shares(redis)
    members = await durable_participants(session_id)
    await project_share(redis, session_id, members)
    return members


async def rebuild_user_projection(redis, user_id: str) -> list[str]:
    """Repopulate a user's shared-sessions set from the table (read-miss rebuild)."""
    await adopt_redis_shares(redis)
    sessions = await durable_sessions_for(user_id)
    await _project(redis, USER_KEY % user_id, sessions)
    return sessions


def audit(action: str, actor: str, session_id: str, participants: list[str]) -> None:
    """Share/unshare audit record through ``audit_record``, the logger session create/delete/export use."""
    from services.audit.audit import AuditAction, audit_record

    try:
        audit_record(
            user_id=actor,
            action=AuditAction.SESSION_SHARE if action == "share" else AuditAction.SESSION_UNSHARE,
            resource_type="chat_session",
            resource_id=session_id,
            session_id=session_id,
            metadata={"participants": participants},
            outcome="success",
        )
    except Exception as e:
        logger.error("Failed to write %s audit record: %s", action, e)
