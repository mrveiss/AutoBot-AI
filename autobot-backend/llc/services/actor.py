# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who acted, for an activity record (GH#13999).

``LLCActivityLogService.record`` requires an actor type and parses the actor id as a UUID,
raising ``ValueError`` otherwise. A service that is handed the caller's identity states it
here, in one place, so no call site can fail the write it is auditing: an identity that is
not a UUID (a service principal, say) is recorded as the system's act, and the identity as
given is kept in ``metadata`` rather than lost.
"""

import uuid
from typing import Any, NamedTuple, Optional

from ..models.activity import ActorType


class Actor(NamedTuple):
    """The resolved actor: what ``record`` is told, plus any identity it could not store."""

    type: ActorType
    id: Optional[str]
    claimed: Optional[dict[str, str]] = None

    def metadata(self, extra: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        """``record``'s ``metadata``: *extra* plus the identity that could not be stored as the actor."""
        merged = {**(extra or {}), **(self.claimed or {})}
        return merged or None


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def resolve_actor(agent_id: Optional[str] = None, user_id: Optional[str] = None) -> Actor:
    """Return the actor for the identity the caller supplied.

    A user wins over an agent (a human acting through an agent is still the human's act);
    with neither, the act is the system's and carries no actor id. A non-UUID identity is
    the system's act too, with the identity kept as ``claimed_actor``.
    """
    kind, ident = (ActorType.USER, user_id) if user_id else (ActorType.AGENT, agent_id)
    if not ident:
        return Actor(ActorType.SYSTEM, None)
    if not _is_uuid(ident):
        return Actor(ActorType.SYSTEM, None, {"claimed_actor": str(ident), "claimed_actor_type": kind.value})
    return Actor(kind, str(ident))


def resolve_actor_as(actor_type: str, actor_id: Optional[str]) -> Actor:
    """As :func:`resolve_actor`, for a caller that states the kind (``"user"``/``"agent"``) itself."""
    if actor_type == ActorType.USER.value:
        return resolve_actor(user_id=actor_id)
    return resolve_actor(agent_id=actor_id)


class ActivityRecordError(RuntimeError):
    """The audit write failed. Deliberately not a ``ValueError``: routes read that as the caller's error."""


async def audit(log: Optional[Any], session: Any, **entry: Any) -> None:
    """Write one activity record in the caller's transaction, if there is a log.

    A failure propagates as :class:`ActivityRecordError` so the operation fails with it and the
    caller's transaction is rolled back, rather than surfacing as a not-found or bad-request.
    """
    if not log:
        return
    try:
        await log.record(session, **entry)
    except Exception as exc:
        raise ActivityRecordError(f"activity record failed: {exc}") from exc
