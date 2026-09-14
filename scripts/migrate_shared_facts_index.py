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
4. Delete the legacy `user:shared_facts:{user_id}` key.

Idempotent: a second run finds no legacy keys left and does nothing.

Usage:
    cd autobot-backend
    python ../scripts/migrate_shared_facts_index.py [--dry-run]
"""

import asyncio
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_LEGACY_PREFIX = "user:shared_facts:"


async def _migrate_one_user(redis, user_id: str, legacy_key: str, dry_run: bool) -> tuple[int, int]:
    """Migrate one legacy `user:shared_facts:{user_id}` set. Returns (facts_migrated, visibility_fixed)."""
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

    if not dry_run:
        await redis.delete(legacy_key)

    return migrated, visibility_fixed


async def migrate(dry_run: bool = False) -> dict:
    """Migrate every legacy shared-facts index. Returns a summary dict."""
    from autobot_shared.redis_client import get_async_redis_client

    redis = await get_async_redis_client(database="knowledge")

    legacy_keys = []
    async for key in redis.scan_iter(match=f"{_LEGACY_PREFIX}*"):
        legacy_keys.append(key.decode("utf-8") if isinstance(key, bytes) else key)

    total_facts = 0
    total_visibility_fixed = 0
    for legacy_key in legacy_keys:
        user_id = legacy_key[len(_LEGACY_PREFIX) :]
        facts, visibility_fixed = await _migrate_one_user(redis, user_id, legacy_key, dry_run)
        total_facts += facts
        total_visibility_fixed += visibility_fixed
        logger.info(
            "%s user %s: %d fact(s) migrated, %d visibility fix(es)",
            "[dry-run] " if dry_run else "",
            user_id,
            facts,
            visibility_fixed,
        )

    summary = {
        "users_migrated": len(legacy_keys),
        "facts_migrated": total_facts,
        "visibility_fixed": total_visibility_fixed,
        "dry_run": dry_run,
    }
    logger.info("Migration complete: %s", summary)
    return summary


if __name__ == "__main__":
    asyncio.run(migrate(dry_run="--dry-run" in sys.argv))
