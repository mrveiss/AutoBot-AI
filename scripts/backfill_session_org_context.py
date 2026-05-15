# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backfill existing chat sessions with org_id from PostgreSQL user records.

Issue #684: Link chat sessions to user, organization, and teams hierarchy.

This script:
1. Scans all session JSON files in data/chats/
2. Reads the 'owner' username from each session's metadata
3. Looks up the user in PostgreSQL to get their org_id
4. Updates the session JSON metadata with org_id
5. Creates Redis indices (org_sessions, session_context)

Usage:
    cd autobot-user-backend
    python ../scripts/backfill_session_org_context.py [--dry-run]
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def _lookup_user_org(username: str, user_cache: dict) -> str | None:
    """Look up a user's org_id from PostgreSQL.

    Helper for backfill_sessions (#684).
    """
    if username in user_cache:
        return user_cache[username]

    try:
        from user_management.database import db_session_context
        from user_management.services.user_service import UserService

        async with db_session_context() as session:
            svc = UserService(session)
            user = await svc.get_user_by_username(username)
            org_id = str(user.org_id) if user and user.org_id else None
            user_cache[username] = org_id
            return org_id
    except Exception as e:
        logger.warning("DB lookup failed for %s: %s", username, e)
        user_cache[username] = None
        return None


async def _update_redis_indices(session_id: str, username: str, org_id: str) -> None:
    """Store org session index and context in Redis.

    Helper for backfill_sessions (#684).
    """
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = await get_redis_client(async_client=True, database="main")

        # Org session set
        org_key = f"org_chat_sessions:{org_id}"
        await redis.sadd(org_key, session_id)
        await redis.expire(org_key, 2592000)

        # Session context hash
        ctx_key = f"chat_session_context:{session_id}"
        await redis.hset(ctx_key, mapping={"org_id": org_id})
        await redis.expire(ctx_key, 86400)

        # Ensure user session set exists
        user_key = f"user_chat_sessions:{username}"
        await redis.sadd(user_key, session_id)
        await redis.expire(user_key, 2592000)

    except Exception as e:
        logger.warning("Redis update failed for %s: %s", session_id, e)


def _extract_session_id(filename: str) -> str:
    """Extract session ID from chat filename (#684)."""
    if filename.endswith("_chat.json"):
        return filename.replace("_chat.json", "")
    return filename.replace("chat_", "").replace(".json", "")


async def _process_session_file(filepath: Path, user_cache: dict, dry_run: bool) -> str:
    """Process a single session file for backfill.

    Returns: "updated", "skipped", or "error".

    Helper for backfill_sessions (#684).
    """
    data = json.loads(filepath.read_text(encoding="utf-8"))
    metadata = data.get("metadata", {})
    owner = metadata.get("owner") or metadata.get("username")

    if metadata.get("org_id") or not owner:
        return "skipped"

    org_id = await _lookup_user_org(owner, user_cache)
    if not org_id:
        return "skipped"

    session_id = _extract_session_id(filepath.name)

    if dry_run:
        logger.info(
            "[DRY RUN] Would update %s: org_id=%s",
            session_id[:16],
            org_id,
        )
        return "updated"

    metadata["org_id"] = org_id
    data["metadata"] = metadata
    filepath.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    await _update_redis_indices(session_id, owner, org_id)
    logger.info(
        "Updated %s: owner=%s, org_id=%s",
        session_id[:16],
        owner,
        org_id,
    )
    return "updated"


async def backfill_sessions(dry_run: bool = False) -> None:
    """Scan session files and backfill org_id metadata."""
    chats_dir = Path("data/chats")
    if not chats_dir.exists():
        logger.error("Chats directory not found: %s", chats_dir)
        return

    files = [
        f
        for f in chats_dir.iterdir()
        if f.name.endswith("_chat.json") or f.name.startswith("chat_")
    ]
    logger.info("Found %d session files to process", len(files))

    user_cache: dict[str, str | None] = {}
    counts = {"updated": 0, "skipped": 0, "error": 0}

    for filepath in files:
        try:
            result = await _process_session_file(filepath, user_cache, dry_run)
            counts[result] += 1
        except Exception as e:
            counts["error"] += 1
            logger.error("Error processing %s: %s", filepath.name, e)

    logger.info(
        "Backfill complete: %d updated, %d skipped, %d errors",
        counts["updated"],
        counts["skipped"],
        counts["error"],
    )


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        logger.info("Running in DRY RUN mode")

    # Add backend to path
    backend_dir = os.path.join(os.path.dirname(__file__), "..", "autobot-user-backend")
    sys.path.insert(0, os.path.abspath(backend_dir))

    asyncio.run(backfill_sessions(dry_run=dry_run))
