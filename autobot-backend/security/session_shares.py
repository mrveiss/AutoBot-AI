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
import math
import time

from sqlalchemy import delete, exists, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from autobot_shared.coordination.work_claims import ClaimConflictError, work_claim
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.store_authority import system_of_record
from models.session_share import SessionShare, SessionShareAdoption

SYSTEM_OF_RECORD = system_of_record("session_shares")

logger = get_logger(__name__)

SESSION_KEY = "session:shared_with:%s"
USER_KEY = "user:shared_sessions:%s"
_SESSION_KEY_PATTERN = SESSION_KEY % "*"
_USER_KEY_PATTERN = USER_KEY % "*"
#: ``shared_by`` recorded for a share that predates the table and was copied out of Redis.
ADOPTED_SHARER = "migrated-from-redis"
#: Name of the durable completion row (``chat_session_share_adoption``): the record that adoption finished.
ADOPTION_NAME = "redis_shares"
#: Redis cache (no TTL) of that durable row; losing it is harmless, the row is what stops a re-adoption.
ADOPTED_KEY = "session_shares:adopted"
#: The adoption lease is a work claim (#16653), not a private Redis lock.
ADOPT_CLAIM_SCOPE = "config:session_shares/adoption"
ADOPT_CLAIM_AGENT = "session-share-adoption"
#: How long one worker may hold the adoption lock, and how long another waits for the marker.
ADOPT_LOCK_TTL_MS = env_int_clamped("AUTOBOT_SESSION_SHARE_ADOPT_LOCK_TTL_MS", 60_000, 1000, 600_000)
ADOPT_WAIT_SECONDS = env_int_clamped("AUTOBOT_SESSION_SHARE_ADOPT_WAIT_SECONDS", 30, 0, 600)
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


async def durable_add_unless_adopted(session_id: str, user_ids: list[str]) -> None:
    """Adoption's insert: one statement per row that writes only while no completion row exists.

    The check and the insert are a single SQL statement, so a superseded adopter (lease expired, or it read
    its members before an unshare) cannot re-create a share once adoption has been recorded as complete.
    """
    async with _factory()() as db:
        insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
        done = exists().where(SessionShareAdoption.name == ADOPTION_NAME)
        for user_id in user_ids:
            row = select(literal(session_id), literal(user_id), literal(ADOPTED_SHARER)).where(~done)
            stmt = insert(SessionShare).from_select(["session_id", "user_id", "shared_by"], row)
            await db.execute(stmt.on_conflict_do_nothing(index_elements=["session_id", "user_id"]))
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


async def durable_adopted() -> bool:
    """True once the completion row is in the system of record."""
    async with _factory()() as db:
        row = await db.execute(select(SessionShareAdoption.name).where(SessionShareAdoption.name == ADOPTION_NAME))
        return row.first() is not None


async def durable_mark_adopted() -> None:
    """Record, durably and idempotently, that adoption finished."""
    async with _factory()() as db:
        insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
        await db.execute(
            insert(SessionShareAdoption).values(name=ADOPTION_NAME).on_conflict_do_nothing(index_elements=["name"])
        )
        await db.commit()


async def _is_adopted(redis) -> bool:
    """The durable row decides; the Redis marker is only a cache of it, re-written when it was lost."""
    if await redis.exists(ADOPTED_KEY):
        return True
    if not await durable_adopted():
        return False
    await redis.set(ADOPTED_KEY, "1")
    return True


async def _project(redis, key: str, members: list[str]) -> None:
    """Write a projection set with no TTL; clearing any TTL a pre-#18890 key still carries."""
    if members:
        await redis.sadd(key, *members)
        await redis.persist(key)


async def project_share(redis, session_id: str, user_ids: list[str]) -> None:
    """Write-through of a share into both Redis sets, leaving each set complete.

    A set that is absent is created from the table (every participant of the chat, every chat of the user),
    never from just this write's delta, or the read path would trust a partial set and deny the rest.
    """
    key = SESSION_KEY % session_id
    known = [] if await redis.exists(key) else await durable_participants(session_id)
    await _project(redis, key, list(user_ids) + known)
    for user_id in user_ids:
        user_key = USER_KEY % user_id
        owned = [] if await redis.exists(user_key) else await durable_sessions_for(user_id)
        await _project(redis, user_key, [session_id] + owned)


async def drop_projection(redis, session_id: str, user_id: str) -> None:
    """Remove one participant from both Redis sets."""
    await redis.srem(SESSION_KEY % session_id, user_id)
    await redis.srem(USER_KEY % user_id, session_id)


async def remove_share(redis, session_id: str, user_id: str) -> bool:
    """Unshare: the table (system of record) first, then the projection.

    If the table write raises, nothing changed anywhere and the caller is told the share was NOT removed;
    clearing Redis first would let the next read-miss rebuild restore the participant from the surviving row.
    Once the row is gone no rebuild can restore the participant, and a rebuild that was already in flight
    reconciles itself against the table (the re-read at the end of ``rebuild_*_projection``).
    """
    await ensure_adopted(redis)
    removed = await durable_remove(session_id, user_id)
    await drop_projection(redis, session_id, user_id)
    return removed


async def _adopt_from_session_keys(redis) -> int:
    copied = 0
    async for raw in redis.scan_iter(match=_SESSION_KEY_PATTERN, count=500):
        session_id = _text(raw).split(":", 2)[2]
        members = [_text(m) for m in await redis.smembers(raw)]
        await durable_add_unless_adopted(session_id, members)
        await redis.persist(_text(raw))
        copied += len(members)
    return copied


async def _adopt_from_user_keys(redis) -> int:
    """Shares whose session-side key already expired but whose user-side key is still there; clears every TTL."""
    copied = 0
    async for raw in redis.scan_iter(match=_USER_KEY_PATTERN, count=500):
        user_id = _text(raw).split(":", 2)[2]
        sessions = [_text(m) for m in await redis.smembers(raw)]
        for session_id in sessions:
            await durable_add_unless_adopted(session_id, [user_id])
        await redis.persist(_text(raw))
        copied += len(sessions)
    return copied


async def adopt_redis_shares(redis) -> int:
    """Copy pre-#18890 Redis-only shares into the table and drop their TTLs; at most once, across workers.

    Inserts only the rows that are missing, so it never rewrites ``shared_by`` or overrides the table. A
    work claim (``ADOPT_CLAIM_SCOPE``, lease ``ADOPT_LOCK_TTL_MS``) keeps one worker at it; completion is the durable
    ``chat_session_share_adoption`` row, cached as ``ADOPTED_KEY`` in Redis. Once the row is set nothing is
    adopted again, whatever Redis holds. The legacy keys are NOT deleted afterwards: they share their names
    with the projection keys this module maintains, so the durable row alone marks them as already imported.
    A worker that loses the lock waits for completion and raises if it never appears, because an unshare must
    not run ahead of adoption.
    """
    if await _is_adopted(redis):
        return 0
    try:
        async with work_claim(
            ADOPT_CLAIM_SCOPE,
            agent_id=ADOPT_CLAIM_AGENT,
            intent="adopt pre-table Redis chat shares",
            ttl_s=math.ceil(ADOPT_LOCK_TTL_MS / 1000),
        ):
            copied = await _adopt_once(redis)
    except ClaimConflictError:
        return await _await_marker(redis)
    if copied:
        logger.info("Adopted %d Redis-only chat shares into the durable table (#18890)", copied)
    return copied


async def _adopt_once(redis) -> int:
    """The body of adoption, under the claim. A holder whose lease lapsed is fenced by the table itself:
    ``durable_add_unless_adopted`` writes nothing once the completion row exists."""
    if await _is_adopted(redis):  # another worker finished between the check before the claim and the claim
        return 0
    copied = await _adopt_from_session_keys(redis) + await _adopt_from_user_keys(redis)
    await durable_mark_adopted()
    await redis.set(ADOPTED_KEY, "1")
    return copied


async def _await_marker(redis) -> int:
    deadline = time.monotonic() + ADOPT_WAIT_SECONDS
    while time.monotonic() < deadline:
        if await _is_adopted(redis):
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
    current = await durable_participants(session_id)
    for user_id in set(members) - set(current):  # unshared while this rebuild was publishing
        await drop_projection(redis, session_id, user_id)
    return current


async def rebuild_user_projection(redis, user_id: str) -> list[str]:
    """Repopulate a user's shared-sessions set from the table (read-miss rebuild)."""
    await ensure_adopted(redis)
    sessions = await durable_sessions_for(user_id)
    await _project(redis, USER_KEY % user_id, sessions)
    current = await durable_sessions_for(user_id)
    for session_id in set(sessions) - set(current):  # unshared while this rebuild was publishing
        await drop_projection(redis, session_id, user_id)
    return current


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
