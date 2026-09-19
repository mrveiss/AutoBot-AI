# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migrate the legacy `user:shared_facts:*` sharing index to the canonical one.

Issue #16709: `_share_single_fact` used to write a second, incompatible
sharing index (`user:shared_facts:{user_id}`) that `KnowledgeOwnership`
(`set_owner`/`share_fact`/`check_access`/`get_shared_facts`) never read, and
never flipped a shared fact's `visibility` to SHARED. That bug is fixed in
`knowledge/facts.py`; this script carries over the facts that were shared
through the old, broken path with no data loss:

1. Scan every `user:shared_facts:{user_id}` set.
2. For each (user_id, fact_id): read the fact's metadata. If `user_id` is
   already in `shared_with` (true by construction of the old write path) and
   `visibility` is still PRIVATE, promote it to SHARED -- the same rule
   `KnowledgeOwnership.share_fact` applies to a newly-shared fact.
3. Add the fact to the canonical `user:kb:shared:{user_id}` index.
4. Rename the legacy `user:shared_facts:{user_id}` key to a timestamped
   backup key (`<legacy_key>:migrated:<utc-ts>`, no TTL) instead of deleting
   it -- a removal that is witnessed and reversible, per the owner's rule
   that stored-data cleanup always leaves a durable, undoable trail.
5. Write one audit-log entry per user (facts moved, visibility fixed, the
   backup key's name) so the migration has a durable record beyond stdout.

Idempotent: a second run finds no legacy keys left (they are backup keys
now, outside `_LEGACY_PREFIX`) and does nothing.

This rewrites stored user data, so it is never run automatically -- a human
runs it, reviews the dry-run summary, and only then re-runs it with --apply.
Defaults to a dry-run preview; nothing is written unless --apply is given.

Usage:
    cd autobot-backend
    python ../scripts/migrate_shared_facts_index.py           # preview only
    python ../scripts/migrate_shared_facts_index.py --apply   # writes changes
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_LEGACY_PREFIX = "user:shared_facts:"
_BACKUP_MARKER = ":migrated:"


def _backup_key_for(legacy_key: str, now: datetime) -> str:
    """The timestamped backup name a legacy key is renamed to, never deleted (#16709)."""
    return f"{legacy_key}{_BACKUP_MARKER}{now.strftime('%Y%m%dT%H%M%SZ')}"


async def _migrate_one_user(redis, user_id: str, legacy_key: str, dry_run: bool, now: datetime) -> tuple[int, int, str]:
    """Migrate one legacy `user:shared_facts:{user_id}` set.

    Returns (facts_migrated, visibility_fixed, backup_key) -- backup_key is
    the name the legacy key was (or, in a dry run, would be) renamed to.
    """
    raw_ids = await redis.smembers(legacy_key)
    fact_ids = [fid.decode("utf-8") if isinstance(fid, bytes) else fid for fid in (raw_ids or [])]

    migrated = 0
    visibility_fixed = 0
    for fact_id in fact_ids:
        fact_key = f"fact:{fact_id}"
        raw = await redis.hget(fact_key, "metadata")
        if not raw:
            logger.warning("Legacy share references missing fact %s (user %s) -- skipping", fact_id, user_id)
            continue

        raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        metadata = json.loads(raw_str) if isinstance(raw_str, str) else raw_str

        shared_with = set(metadata.get("shared_with", []))
        shared_with.add(user_id)  # true by construction of the old write path; make it explicit
        metadata["shared_with"] = list(shared_with)

        if metadata.get("visibility") == "private":
            metadata["visibility"] = "shared"
            visibility_fixed += 1

        if not dry_run:
            await redis.hset(fact_key, "metadata", json.dumps(metadata))
            await redis.sadd(f"user:kb:shared:{user_id}", fact_id)
        migrated += 1

    backup_key = _backup_key_for(legacy_key, now)
    if not dry_run:
        # Renamed, never deleted: a removal that is witnessed and reversible.
        # RENAME does not add or change a TTL, so the backup key inherits the
        # legacy key's usual no-expiry lifetime.
        await redis.rename(legacy_key, backup_key)

    return migrated, visibility_fixed, backup_key


async def migrate(dry_run: bool = True) -> dict:
    """Migrate every legacy shared-facts index. Returns a summary dict."""
    from autobot_shared.redis_client import get_async_redis_client
    from services.audit_logger import audit_log

    redis = await get_async_redis_client(database="knowledge")
    now = datetime.now(tz=timezone.utc)

    legacy_keys = []
    async for key in redis.scan_iter(match=f"{_LEGACY_PREFIX}*"):
        key = key.decode("utf-8") if isinstance(key, bytes) else key
        if _BACKUP_MARKER in key:
            continue  # an already-migrated backup key, not a live legacy set (#16709)
        legacy_keys.append(key)

    total_facts = 0
    total_visibility_fixed = 0
    for legacy_key in legacy_keys:
        user_id = legacy_key[len(_LEGACY_PREFIX) :]
        facts, visibility_fixed, backup_key = await _migrate_one_user(redis, user_id, legacy_key, dry_run, now)
        total_facts += facts
        total_visibility_fixed += visibility_fixed
        logger.info(
            "%suser %s: %d fact(s) migrated, %d visibility fix(es), legacy key -> %s",
            "[dry-run] would rename -- " if dry_run else "",
            user_id,
            facts,
            visibility_fixed,
            backup_key,
        )
        if not dry_run:
            # Durable record beyond stdout (#16709): who, what moved, and
            # where the pre-migration data is recoverable from.
            await audit_log(
                "kb.migrate_shared_facts",
                result="success",
                user_id=user_id,
                resource=legacy_key,
                details={
                    "facts_migrated": facts,
                    "visibility_fixed": visibility_fixed,
                    "backup_key": backup_key,
                },
            )

    summary = {
        "users_migrated": len(legacy_keys),
        "facts_migrated": total_facts,
        "visibility_fixed": total_visibility_fixed,
        "dry_run": dry_run,
    }
    logger.info("Migration complete: %s", summary)
    return summary


def _cli_dry_run(argv: list[str]) -> bool:
    """Preview-only unless --apply is given explicitly (#16709).

    This rewrites stored user data, and the owner's cleanup rule requires a
    human to see the dry-run summary before anything is written -- never run
    this unattended. A pure function so the default direction is testable
    without invoking the CLI entry point itself.
    """
    return "--apply" not in argv


if __name__ == "__main__":
    asyncio.run(migrate(dry_run=_cli_dry_run(sys.argv)))
