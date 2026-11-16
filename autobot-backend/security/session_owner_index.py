# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A user's owned session ids: the Redis owner index, rebuilt from the session files on a miss (#21664).

``user_chat_sessions:<username>`` is a Redis set with a TTL. Per THREAT_MODEL.md section 2, Redis
is a cache and the session file's ``metadata.owner`` is the record of truth, so an empty set
means "not cached", never "owns nothing". On a miss the owners are read from disk and the set
is re-cached for each session's real owner (the same rehydration ``_owner_when_cache_is_empty``
does for a single session). Unowned legacy sessions match nobody and stay unlisted.

Its own module because ``security/session_ownership.py`` is at its recorded size ceiling.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Iterable

from autobot_shared.logging_manager import get_logger
from security.session_owner_errors import SessionOwnerUnreadable

logger = get_logger(__name__)

OwnerReader = Callable[[str], Awaitable["str | None"]]


async def owned_session_ids(validator, username: str, candidate_ids: Iterable[str], read_owner: OwnerReader) -> set:
    """Ids of *candidate_ids* owned by *username*; a Redis error propagates (never read as "owns nothing")."""
    cached = await validator.get_user_sessions(username)
    if cached:
        return set(cached)
    owned = {sid for sid in candidate_ids if await _durable_owner(read_owner, sid) == username}
    for session_id in owned:
        await validator.set_session_owner(session_id, username)
    if owned:
        logger.info("Rebuilt the owner index for %s from %d session file(s)", username, len(owned))
    return owned


async def _durable_owner(read_owner: OwnerReader, session_id: str) -> str | None:
    """The owner recorded in the session file; an unreadable one is unknown, so it is not listed."""
    try:
        return await read_owner(session_id)
    except SessionOwnerUnreadable:
        logger.warning("Owner of session %s... is unreadable; it is left out of the listing", session_id[:8])
        return None
