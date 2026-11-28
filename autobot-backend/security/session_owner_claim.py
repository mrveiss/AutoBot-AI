# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one place an unowned session's ownership key is first written (#20030)."""

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def take_or_refresh(validator, session_id: str, existing: str | None, username: str, force: bool) -> bool:
    """Write the ownership key; an unowned session goes to ONE first writer.

    ``set_session_owner`` reads the owner and then writes, so two writers can both have seen none.
    ``SET NX`` lets exactly one win; the other is refused unless it is the same user, or *force*.
    A Redis failure raises: "could not check" must not read as "free".
    """
    key, ttl = validator._get_ownership_key(session_id), validator.ownership_ttl
    if existing is None and await validator.redis.set(key, username, nx=True, ex=ttl):
        return True
    if existing is None and not force:
        winner = await validator.get_session_owner(session_id)
        if winner and winner != username:
            logger.warning("Session %s... was taken by %s first; refusing %s", session_id[:8], winner, username)
            return False
    await validator.redis.set(key, username, ex=ttl)
    return True
