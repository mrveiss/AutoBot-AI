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
import time
import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_utils import delete_if_value
from autobot_shared.store_authority import system_of_record
from models.session_share import SessionShare

SYSTEM_OF_RECORD = system_of_record("session_shares")

logger = get_logger(__name__)

SESSION_KEY = "session:shared_with:%s"
USER_KEY = "user:shared_sessions:%s"
_SESSION_KEY_PATTERN = SESSION_KEY % "*"
_USER_KEY_PATTERN = USER_KEY % "*"
#: ``shared_by`` recorded for a share that predates the table and was copied out of Redis.
ADOPTED_SHARER = "migrated-from-redis"
#: Set (no TTL) once every pre-table Redis share is in the table; adoption never runs again after it.
ADOPTED_KEY = "session_shares:adopted"
ADOPT_LOCK_KEY = "session_shares:adopt_lock"
#: How long one worker may hold the adoption lock, and how long another waits for the marker.
ADOPT_LOCK_TTL_MS = env_int("AUTOBOT_SESSION_SHARE_ADOPT_LOCK_TTL_MS", 60_000)
ADOPT_WAIT_SECONDS = env_int("AUTOBOT_SESSION_SHARE_ADOPT_WAIT_SECONDS", 30)
_ADOPT_POLL_SECONDS = 0.2

#: ``reason`` values of the ownership result that mean "this caller owns the chat" (or has no ownership to
#: check). ``org_admin`` (read access), ``shared_access`` (a participant) and ``log_only_mode`` (the check
#: failed and was let through to be logged) are deliberately absent: managing shares fails closed.
OWNER_REASONS = frozenset({"owner_match", "legacy_migration", "auth_disabled", "enforcement_disabled"})


def _factory():
    from user_management.database import get_async_session_factory

    return get_async_session_factory()


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else value


async def durable_add(session_id: str, user_ids: list[str], shared_by: str) -> None:
    """Record participants in the system of record; an existing row is left untouched (ON CONFLICT DO NOTHING)."""
    if not user_ids:
        return
    async with _factory()() as db:
        insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
        rows = [{"session_id": session_id, "user_id": u, "shared_by": shared_by} for u in user_ids]
        await db.execute(
            insert(SessionShare).values(rows).on_conflict_do_nothing(index_elements=["session_id", "user_id"])
        )
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


async def remove_share(redis, session_id: str, user_id: str) -> bool:
    """Unshare, failing closed: Redis is cleared BEFORE the table, and again after it.

    A failure at any step raises with access already gone from the projection, so a 500 never leaves the
    participant able to read. The second clear removes what a concurrent read-miss rebuilt from the row
    that was still there.
    """
    await ensure_adopted(redis)
    await drop_projection(redis, session_id, user_id)
    removed = await durable_remove(session_id, user_id)
    await drop_projection(redis, session_id, user_id)
    return removed


async def _adopt_from_session_keys(redis) -> int:
    copied = 0
    async for raw in redis.scan_iter(match=_SESSION_KEY_PATTERN, count=500):
        session_id = _text(raw).split(":", 2)[2]
        members = [_text(m) for m in await redis.smembers(raw)]
        await durable_add(session_id, members, ADOPTED_SHARER)
        await _project(redis, _text(raw), members)
        copied += len(members)
    return copied


async def _adopt_from_user_keys(redis) -> int:
    """Shares whose session-side key already expired but whose user-side key is still there; clears every TTL."""
    copied = 0
    async for raw in redis.scan_iter(match=_USER_KEY_PATTERN, count=500):
        user_id = _text(raw).split(":", 2)[2]
        sessions = [_text(m) for m in await redis.smembers(raw)]
        for session_id in sessions:
            await durable_add(session_id, [user_id], ADOPTED_SHARER)
            await _project(redis, SESSION_KEY % session_id, [user_id])
        await _project(redis, _text(raw), sessions)
        copied += len(sessions)
    return copied


async def adopt_redis_shares(redis) -> int:
    """Copy pre-#18890 Redis-only shares into the table and drop their TTLs; at most once, across workers.

    Inserts only the rows that are missing, so it never rewrites ``shared_by`` or overrides the table. A
    ``SET NX`` lock (``ADOPT_LOCK_TTL_MS``) keeps one worker at it; completion is the ``ADOPTED_KEY`` marker in
    Redis, which is never expired. A worker that loses the lock waits for the marker and raises if it never
    appears, because an unshare must not run ahead of adoption.
    """
    if await redis.exists(ADOPTED_KEY):
        return 0
    token = uuid.uuid4().hex
    if not await redis.set(ADOPT_LOCK_KEY, token, nx=True, px=ADOPT_LOCK_TTL_MS):
        return await _await_marker(redis)
    try:
        copied = await _adopt_from_session_keys(redis) + await _adopt_from_user_keys(redis)
        await redis.set(ADOPTED_KEY, "1")
    finally:
        await delete_if_value(redis, ADOPT_LOCK_KEY, token)
    if copied:
        logger.info("Adopted %d Redis-only chat shares into the durable table (#18890)", copied)
    return copied


async def _await_marker(redis) -> int:
    deadline = time.monotonic() + ADOPT_WAIT_SECONDS
    while time.monotonic() < deadline:
        if await redis.exists(ADOPTED_KEY):
            return 0
        await asyncio.sleep(_ADOPT_POLL_SECONDS)
    raise TimeoutError("chat share adoption by another worker did not finish")


async def ensure_adopted(redis) -> None:
    """Lazy fallback for the startup adoption: a no-op once the marker is set."""
    await adopt_redis_shares(redis)


async def rebuild_session_projection(redis, session_id: str) -> list[str]:
    """Repopulate a chat's Redis sets from the table (read-miss rebuild)."""
    await ensure_adopted(redis)
    members = await durable_participants(session_id)
    await project_share(redis, session_id, members)
    return members


async def rebuild_user_projection(redis, user_id: str) -> list[str]:
    """Repopulate a user's shared-sessions set from the table (read-miss rebuild)."""
    await ensure_adopted(redis)
    sessions = await durable_sessions_for(user_id)
    await _project(redis, USER_KEY % user_id, sessions)
    return sessions


def audit_actor(request, user_data: dict | None) -> dict:
    """Who acted, for the audit record: the user's UUID and the client IP, as the other session audits record them."""
    user_data = user_data or {}
    client = getattr(request, "client", None)
    return {
        "user_id": str(user_data.get("user_id", "unknown")),
        "username": user_data.get("username", "unknown"),
        "ip": client.host if client else "unknown",
    }


def audit(action: str, actor: dict, session_id: str, participants: list[str]) -> None:
    """Share/unshare audit record through ``audit_record``, the logger session create/delete/export use."""
    from services.audit.audit import AuditAction, audit_record

    try:
        audit_record(
            user_id=actor["user_id"],
            action=AuditAction.SESSION_SHARE if action == "share" else AuditAction.SESSION_UNSHARE,
            resource_type="chat_session",
            resource_id=session_id,
            ip_address=actor["ip"],
            session_id=session_id,
            metadata={"participants": participants, "username": actor["username"]},
            outcome="success",
        )
    except Exception as e:
        logger.error("Failed to write %s audit record: %s", action, e)
