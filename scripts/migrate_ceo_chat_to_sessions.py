#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Forward data migration: legacy CEO-chat threads/messages (Postgres) -> the
chat_history session store (#12009).

``llc_ceo_chat_threads`` / ``llc_ceo_chat_messages`` predate the CEO-chat
retirement (#11870, which deleted the ORM models/service/API routes but left
the tables and their data in place). This is a ONE-TIME, REVIEWABLE data
migration script -- it does NOT run automatically as part of any deploy,
CI, or self-update path. An operator runs it manually once, reviews the
output, and re-runs it again only if needed (it is idempotent):

    cd autobot-backend
    python ../scripts/migrate_ceo_chat_to_sessions.py --dry-run
    python ../scripts/migrate_ceo_chat_to_sessions.py

This follows the established repo convention for one-time data migrations
that touch the chat_history session store -- see
``scripts/backfill_session_org_context.py`` (same directory, same
``--dry-run`` flag, same "manually invoked, not wired into code-sync"
shape). No alembic schema change is involved; the source tables are never
written to.

Design (#12009, owner-approved):
- Each thread becomes one normal user chat_history session, scoped via
  ``metadata.owner`` (the resolved username) exactly like a session created
  through ``POST /chat/sessions`` -- see ``api/chat_sessions.py``.
- Each message becomes one chat_history message; ``author_type`` "human"
  (board/user message) -> role "user", "system" (LLM/service reply) ->
  role "assistant" -- mapping per the comment on the now-deleted
  ``llc/models/ceo_chat.py::LLCCeoChatMessage.author_type``.
- Idempotent: ``session_id`` is deterministic (``ceochat-{thread_id}``); a
  pre-existing session with that ID is skipped, never duplicated.
- Non-destructive: this script only SELECTs from ``llc_ceo_chat_*`` tables;
  it never DROPs/ALTERs/TRUNCATEs/UPDATEs/DELETEs them.
- Ownerless threads (``created_by_user_id IS NULL``, or the referenced user
  no longer exists) are SKIPPED with a WARNING -- never dropped, never
  attached to the wrong user.

Verification: after the run, ``sessions_created + skipped_existing +
skipped_ownerless + errors`` must equal ``thread_count`` (every thread is
accounted for exactly once), and ``messages_added`` must equal
``messages_expected`` -- the sum of message counts for threads that were
migrated *this run* (skipped/pre-existing threads are not re-counted, so
this holds on both a fresh run and an idempotent re-run).

Note: ``ChatHistoryManager.create_session()`` accepts a ``metadata`` kwarg
but does not persist it to the session file (only to the in-memory return
value and the optional Memory Graph entity) -- ``update_session_metadata()``
is the documented follow-up call already used elsewhere
(``api/chat_sessions_thinking.py``) to actually write session metadata to
disk. This script calls both, in that order, so migrated sessions carry a
real ``metadata.owner`` on disk. The underlying gap in ``create_session()``
is filed separately (see PR description) since it affects all session
creation, not just this migration.

Use --dry-run to preview counts without writing anything.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent / "autobot-backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import text  # noqa: E402

from autobot_shared.logging_manager import get_logger  # noqa: E402

logger = get_logger(__name__)

AUTHOR_TYPE_ROLE = {"human": "user", "system": "assistant"}
DEFAULT_ROLE = "user"
SESSION_ID_PREFIX = "ceochat-"

_THREADS_SQL = text("""
    SELECT id, company_id, title, resolved_entity_type, resolved_entity_id,
           created_by_user_id, created_at, updated_at
    FROM llc_ceo_chat_threads
    ORDER BY created_at
    """)

_MESSAGES_SQL = text("""
    SELECT id, thread_id, author_type, author_user_id, body, created_at
    FROM llc_ceo_chat_messages
    ORDER BY thread_id, created_at
    """)

_USERNAME_SQL = text("SELECT username FROM users WHERE id = :user_id")


def _role_for_author_type(author_type: str) -> str:
    """Map llc_ceo_chat_messages.author_type to a chat_history sender role.

    "human" (board/user message) -> "user"; "system" (LLM/service reply) ->
    "assistant". Any other value is unexpected -- logged and defaulted to
    "user" rather than dropping the message (#12009 req 3).
    """
    role = AUTHOR_TYPE_ROLE.get(author_type)
    if role is None:
        logger.warning("Unknown ceo_chat author_type %r; defaulting to role 'user'", author_type)
        return DEFAULT_ROLE
    return role


def session_id_for_thread(thread_id: Any) -> str:
    """Deterministic session_id so re-runs are idempotent (#12009 req 1)."""
    return f"{SESSION_ID_PREFIX}{thread_id}"


def _build_session_metadata(thread: dict, username: str) -> dict:
    """Build chat_history session metadata for a migrated thread (#12009 req 2)."""
    resolved_entity_id = thread["resolved_entity_id"]
    return {
        "owner": username,
        "username": username,
        "company_id": str(thread["company_id"]),
        "resolved_entity_type": thread["resolved_entity_type"],
        "resolved_entity_id": str(resolved_entity_id) if resolved_entity_id else None,
        "migrated_from": "ceo_chat",
        "source_thread_id": str(thread["id"]),
        "created_at": thread["created_at"].isoformat() if thread["created_at"] else None,
        "updated_at": thread["updated_at"].isoformat() if thread["updated_at"] else None,
    }


def _build_migrated_message(msg: dict) -> dict:
    """Build a chat_history message dict for a migrated ceo_chat message.

    Mirrors the shape produced by ``MessagesMixin._build_message_dict``
    (chat_history/messages.py) so the migrated message is indistinguishable
    from one added through the normal API -- except the timestamp is the
    ORIGINAL message time, not "now": ``add_message()``/
    ``add_messages_batch()`` never expose a timestamp override, so the dict
    is built here and passed straight to ``add_messages_batch()`` (#12009
    req 3).
    """
    role = _role_for_author_type(msg["author_type"])
    message: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "sender": role,
        "text": msg["body"],
        "messageType": "default",
        "metadata": {"source_message_id": str(msg["id"]), "migrated_from": "ceo_chat"},
        "timestamp": msg["created_at"].strftime("%Y-%m-%d %H:%M:%S") if msg["created_at"] else "",
        "sources": [],
    }
    if msg["author_user_id"]:
        message["authorId"] = str(msg["author_user_id"])
    return message


async def _fetch_threads(db_session) -> list[dict]:
    """Read all ceo_chat threads (read-only; source table is never written)."""
    result = await db_session.execute(_THREADS_SQL)
    return [dict(row._mapping) for row in result]


async def _fetch_messages_by_thread(db_session) -> dict[Any, list[dict]]:
    """Read all ceo_chat messages, grouped by thread_id, ordered by created_at."""
    result = await db_session.execute(_MESSAGES_SQL)
    by_thread: dict[Any, list[dict]] = {}
    for row in result:
        msg = dict(row._mapping)
        by_thread.setdefault(msg["thread_id"], []).append(msg)
    return by_thread


async def _resolve_username(db_session, user_id: Any, cache: dict[Any, str | None]) -> str | None:
    """Resolve created_by_user_id -> username, cached per migration run."""
    if user_id is None:
        return None
    if user_id in cache:
        return cache[user_id]
    result = await db_session.execute(_USERNAME_SQL, {"user_id": user_id})
    row = result.first()
    username = row[0] if row else None
    if username is None:
        logger.warning("ceo_chat created_by_user_id %s does not resolve to a user", user_id)
    cache[user_id] = username
    return username


async def _migrate_thread(
    manager,
    thread: dict,
    messages: list[dict],
    username: str | None,
    dry_run: bool,
) -> tuple[str, int]:
    """Migrate one thread; returns (outcome, messages_added) (#12009 req 4)."""
    if not username:
        logger.warning(
            "Skipping ceo_chat thread %s: no resolvable owner (created_by_user_id=%s)",
            thread["id"],
            thread["created_by_user_id"],
        )
        return "skipped_ownerless", 0

    session_id = session_id_for_thread(thread["id"])
    if await manager.get_session(session_id) is not None:
        logger.info("Skipping ceo_chat thread %s: session %s already exists", thread["id"], session_id)
        return "skipped_existing", 0

    if dry_run:
        _log_dry_run(session_id, thread["id"], username, len(messages))
        return "created", len(messages)

    await _write_session(manager, session_id, thread, messages, username)
    return "created", len(messages)


def _log_dry_run(session_id: str, thread_id: Any, username: str, message_count: int) -> None:
    """Log what a dry-run would have created, without writing anything."""
    logger.info(
        "[DRY RUN] Would create session %s for thread %s (owner=%s, %d messages)",
        session_id,
        thread_id,
        username,
        message_count,
    )


async def _write_session(manager, session_id: str, thread: dict, messages: list[dict], username: str) -> None:
    """Create the session, persist owner metadata, and batch-add messages."""
    metadata = _build_session_metadata(thread, username)
    await manager.create_session(session_id=session_id, title=thread["title"], metadata=metadata)
    # create_session() does not persist `metadata` to the session file --
    # update_session_metadata() is the documented follow-up call (see module
    # docstring) that actually writes it to disk.
    await manager.update_session_metadata(session_id, metadata)

    built_messages = [_build_migrated_message(m) for m in messages]
    if built_messages:
        await manager.add_messages_batch(session_id, built_messages)

    logger.info(
        "Migrated ceo_chat thread %s -> session %s (owner=%s, %d messages)",
        thread["id"],
        session_id,
        username,
        len(built_messages),
    )


_OUTCOME_TO_COUNT_KEY = {
    "created": "sessions_created",
    "skipped_existing": "skipped_existing",
    "skipped_ownerless": "skipped_ownerless",
}


def _verify_counts(counts: dict[str, int]) -> None:
    """Assert every thread was accounted for exactly once (#12009 req 5)."""
    accounted = counts["sessions_created"] + counts["skipped_existing"] + counts["skipped_ownerless"] + counts["errors"]
    if accounted != counts["thread_count"]:
        raise AssertionError(f"Thread accounting mismatch: {accounted} accounted vs {counts['thread_count']} total")
    if counts["messages_added"] != counts["messages_expected"]:
        raise AssertionError(
            f"Message count mismatch: {counts['messages_added']} added vs "
            f"{counts['messages_expected']} expected for migrated threads"
        )


async def run_migration(dry_run: bool = False) -> dict[str, int]:
    """Run the full ceo_chat -> chat_history migration and return summary counts."""
    from chat_history import ChatHistoryManager
    from user_management.database import db_session_context

    manager = ChatHistoryManager()
    counts = {k: 0 for k in ("thread_count", "message_count", "messages_expected", "messages_added")}
    counts.update({k: 0 for k in _OUTCOME_TO_COUNT_KEY.values()})
    counts["errors"] = 0

    async with db_session_context() as db_session:
        threads = await _fetch_threads(db_session)
        messages_by_thread = await _fetch_messages_by_thread(db_session)
        counts["thread_count"] = len(threads)
        counts["message_count"] = sum(len(v) for v in messages_by_thread.values())

        user_cache: dict[Any, str | None] = {}
        for thread in threads:
            thread_messages = messages_by_thread.get(thread["id"], [])
            await _process_one_thread(manager, db_session, thread, thread_messages, user_cache, dry_run, counts)

    _verify_counts(counts)
    logger.info("CEO-chat migration summary: %s", counts)
    return counts


async def _process_one_thread(
    manager,
    db_session,
    thread: dict,
    thread_messages: list[dict],
    user_cache: dict[Any, str | None],
    dry_run: bool,
    counts: dict[str, int],
) -> None:
    """Resolve owner, migrate one thread, and fold the outcome into `counts`."""
    try:
        username = await _resolve_username(db_session, thread["created_by_user_id"], user_cache)
        outcome, added = await _migrate_thread(manager, thread, thread_messages, username, dry_run)
        counts[_OUTCOME_TO_COUNT_KEY[outcome]] += 1
        counts["messages_added"] += added
        if outcome == "created":
            counts["messages_expected"] += len(thread_messages)
    except Exception:
        logger.exception("Error migrating ceo_chat thread %s", thread["id"])
        counts["errors"] += 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Forward-migrate legacy ceo_chat threads/messages into chat_history sessions (#12009)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing anything")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("Running in DRY RUN mode -- no sessions or messages will be written")

    counts = asyncio.run(run_migration(dry_run=args.dry_run))
    logger.info("Done. %s", counts)


if __name__ == "__main__":
    main()
