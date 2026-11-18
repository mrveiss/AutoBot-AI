# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
KB access-control epoch (#16664).

RAG results are cached per visibility scope (see ``services/rag_visibility.py``). A scope key
cannot see an access *revoked* from inside the same scope -- an unshare, or a visibility
change -- so every revocation replaces one epoch token, and the token is part of every cache key.
A bump therefore orphans every cached result at once; the entries expire on their own TTL.
The epoch is a random token, not a counter, so an eviction of the key under ``allkeys-lru`` cannot
revalidate an old entry (see ``autobot_shared.membership_epoch.new_epoch_token``).
"""

from autobot_shared.logging_manager import get_logger
from autobot_shared.membership_epoch import (  # noqa: F401 -- the scoped membership counter lives beside this one
    MembershipEpochBumpError,
    bump_membership_epoch,
    membership_epoch_key,
    new_epoch_token,
    read_epoch_token,
    read_membership_epoch,
)
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

#: Redis key of the counter. It lives in the knowledge database beside the ownership indexes.
ACL_EPOCH_KEY = "kb:acl_epoch"
ACL_EPOCH_DATABASE = "knowledge"


def bump_acl_epoch(redis_client) -> str:
    """SET a fresh epoch token through *redis_client* (the sync client ``KnowledgeOwnership`` holds).

    Not swallowed: a revocation that did not invalidate the caches is a disclosure, so a failed
    bump surfaces to the caller instead of being logged and forgotten.
    """
    epoch = new_epoch_token()
    redis_client.set(ACL_EPOCH_KEY, epoch)
    logger.info("KB access-control epoch bumped to %s", epoch)
    return epoch


class AclEpochBumpError(RuntimeError):
    """The epoch could not be bumped after an ownership rewrite: the caches may serve stale access."""


async def bump_acl_epoch_async(redis_client) -> str:
    """SET a fresh epoch token through an async *redis_client*; any failure raises ``AclEpochBumpError``.

    For writers that already hold the async client (ownership reassignment). ``None`` -- an
    unavailable client -- is a failure too: the rewrite happened and nothing invalidated the caches.
    """
    if redis_client is None:
        raise AclEpochBumpError("KB access-control epoch not bumped: no Redis client")
    try:
        epoch = new_epoch_token()
        await redis_client.set(ACL_EPOCH_KEY, epoch)
    except Exception as exc:
        raise AclEpochBumpError(f"KB access-control epoch not bumped: {exc}") from exc
    logger.info("KB access-control epoch bumped to %s", epoch)
    return epoch


async def read_acl_epoch() -> str | None:
    """The current epoch token, minted on first use or after an eviction, or ``None`` if unreadable.

    ``None`` means "do not serve or fill a cache": an unreadable epoch cannot prove that a
    cached entry predates no revocation. The value is never ``"0"``: a token that could repeat
    would let an entry cached before an ``allkeys-lru`` eviction be served again.
    """
    try:
        client = await get_async_redis_client(database=ACL_EPOCH_DATABASE)
        if client is None:
            return None
        return await read_epoch_token(client, ACL_EPOCH_KEY)
    except Exception as exc:
        logger.warning("KB access-control epoch unreadable; RAG caches are skipped: %s", exc)
        return None
