# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A user's owned session ids: the Redis owner index, trusted only behind a completeness marker (#21664).

``user_chat_sessions:<username>`` is a Redis set with a TTL. Per THREAT_MODEL.md section 2, Redis
is a cache and the session file's ``metadata.owner`` is the record of truth. The set alone
cannot say whether it is complete: after it expires, one new ``sadd`` makes it ``{that one}``.
So the set is read only while ``user_chat_sessions_complete:<username>`` exists. Without the
marker, the owners are read from the session files, each owned session is re-cached for its
real owner through ``set_session_owner``, and the marker is written -- also when nothing is
owned, so a principal that owns nothing does not rescan on every call. A failed re-cache or an
unreadable session file leaves the index unmarked. The marker expires before the set can
(``OWNER_INDEX_COMPLETE_TTL`` < ``TTL_30_DAYS``).

Invariant: a marked set holds every session its user owns. The paths that stamp a new owner on
disk (session create, conversation import) index it through ``index_owner_or_unmark``, which
adds the session to the owner's set or, if that fails, removes the owner's marker so the next
list call rebuilds from the files. A forced transfer and an approved owner proposal go through
``set_session_owner`` directly, which ``srem``s the session from its previous owner's set.

Its own module because ``security/session_ownership.py`` is at its recorded size ceiling.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Iterable

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import TTL_24_HOURS, TTL_30_DAYS
from security.session_owner_errors import SessionOwnerUnreadable

logger = get_logger(__name__)

OwnerReader = Callable[[str], Awaitable["str | None"]]
_UNREADABLE = object()  # an owner that could not be read: never a username, and never "complete"

#: Prefix of the per-user marker that says the owner set is complete.
OWNER_INDEX_COMPLETE_KEY_PREFIX = "user_chat_sessions_complete:"
#: Seconds the marker lives; clamped below the set's own TTL so it can never outlive the set.
OWNER_INDEX_COMPLETE_TTL: int = env_int_clamped(
    "AUTOBOT_CHAT_OWNER_INDEX_COMPLETE_TTL", TTL_24_HOURS, min_v=1, max_v=TTL_30_DAYS - 1
)


def complete_key(username: str) -> str:
    """Redis key of *username*'s completeness marker."""
    return f"{OWNER_INDEX_COMPLETE_KEY_PREFIX}{username}"


async def index_owner_or_unmark(validator, session_id: str, owner: str, **context) -> bool:
    """Add *session_id* to *owner*'s index; if that fails, unmark the index so the next list rebuilds."""
    if await validator.set_session_owner(session_id, owner, **context):
        return True
    logger.error(
        "Session %s... is not in %s's owner index; unmarking it so the next list rebuilds", session_id[:8], owner
    )
    try:
        await validator.redis.delete(complete_key(owner))
    except Exception as e:
        logger.error("Could not unmark %s's owner index either; it stays incomplete until it expires: %s", owner, e)
    return False


async def owned_session_ids(validator, username: str, candidate_ids: Iterable[str], read_owner: OwnerReader) -> set:
    """Ids owned by *username*; a Redis error propagates (never read as "owns nothing")."""
    if await validator.redis.exists(complete_key(username)):
        return set(await validator.get_user_sessions(username))
    owned, complete = await _rebuild(validator, username, candidate_ids, read_owner)
    if complete:  # an unread owner or a session the set failed to take must not sit behind the marker
        await validator.redis.set(complete_key(username), "1", ex=OWNER_INDEX_COMPLETE_TTL)
    return owned


async def _rebuild(validator, username: str, candidate_ids: Iterable[str], read_owner: OwnerReader):
    """Owned ids per the session files, each re-cached for its real owner; and whether the result is complete."""
    owners = {sid: await _durable_owner(read_owner, sid) for sid in candidate_ids}
    owned = {sid for sid, owner in owners.items() if owner == username}
    recached = [await validator.set_session_owner(session_id, username) for session_id in owned]
    logger.info("Rebuilt the owner index for %s from the session files: %d owned", username, len(owned))
    return owned, all(recached) and _UNREADABLE not in owners.values()


async def _durable_owner(read_owner: OwnerReader, session_id: str):
    """The owner recorded in the session file; an unreadable one is unknown: not listed, and blocks the marker."""
    try:
        return await read_owner(session_id)
    except SessionOwnerUnreadable:
        logger.warning("Owner of session %s... is unreadable; it is left out of the listing", session_id[:8])
        return _UNREADABLE
