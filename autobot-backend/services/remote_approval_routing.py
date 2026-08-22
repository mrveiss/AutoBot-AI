# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Routing an approval to a human who is not at the screen (#14068).

PR 2 of 2. The correlation half is ``services/remote_approval``; this decides
*where* the question is asked and delivers it.

The separation this module exists to preserve
---------------------------------------------
``remote`` changes **where the human is contacted**. It does not change **what
the agent may do**. The autonomy ceiling stays entirely with
``agent_loop/guard_profile`` and its ``require_approval_for_sensitive`` field.

That is the whole point of #14068. Today an operator stepping away has two
options: leave approvals on and let the run block until
``approval_timeout_seconds`` expires, or drop to the ``minimal`` guard profile
and remove the gate. The second is the one people actually take, so "nobody is
watching" silently becomes "the agent may do more" — the exact conflation this
separates. A future edit that lets this flag widen permissions has reproduced
the bug, and there is a test asserting every guard-profile field is byte
identical with the flag on and off.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from services.remote_approval import DeliveredApproval, RemoteApprovalStore, embed_token

logger = get_logger(__name__)

_REMOTE_FLAG_KEY_PREFIX = "approval:remote:"

#: How long a session stays flagged remote without being refreshed.
REMOTE_FLAG_TTL_SECONDS = int(os.getenv("AUTOBOT_REMOTE_APPROVAL_FLAG_TTL_SECONDS", "604800"))


class ApprovalSender(Protocol):
    """Sends one already-composed approval message to a channel.

    Deliberately narrow: this module must not know how any platform sends. The
    Gateway's egress seam and each live adapter already do, and #14270 put the
    governance there.
    """

    async def __call__(self, *, platform: str, channel_id: str, body: str) -> bool: ...


@dataclass(frozen=True)
class RemoteTarget:
    """Where a given session's approvals should be asked."""

    platform: str
    channel_id: str


class RemoteApprovalRouting:
    """Per-session 'the human is elsewhere' flag.

    Storage mirrors the flag's meaning: it is session state, not policy, so it
    lives in Redis beside other session flags rather than in the guard config.
    """

    async def set_remote(self, session_id: str, target: Optional[RemoteTarget]) -> bool:
        """Route this session's approvals to *target*, or clear with ``None``."""
        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("Redis unavailable — cannot change remote routing for %s", session_id)
            return False
        key = f"{_REMOTE_FLAG_KEY_PREFIX}{session_id}"
        try:
            if target is None:
                await redis.delete(key)
                return True
            await redis.hset(key, mapping={"platform": target.platform, "channel_id": target.channel_id})
            await redis.expire(key, REMOTE_FLAG_TTL_SECONDS)
            return True
        except Exception as exc:  # noqa: BLE001 - a routing change is not worth crashing a turn
            logger.error("Failed to set remote routing for %s: %s", session_id, exc)
            return False

    async def target_for(self, session_id: str) -> Optional[RemoteTarget]:
        """Where *session_id*'s approvals go, or None to ask inline as today.

        None on any failure. An unreachable routing store must leave the
        approval on the screen it would already have used, never suppress it.
        """
        redis = await get_async_redis_client()
        if redis is None:
            return None
        try:
            data = await redis.hgetall(f"{_REMOTE_FLAG_KEY_PREFIX}{session_id}")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to read remote routing for %s: %s", session_id, exc)
            return None
        platform = _field(data, "platform")
        channel_id = _field(data, "channel_id")
        if not platform or not channel_id:
            return None
        return RemoteTarget(platform=platform, channel_id=channel_id)


def _field(mapping: dict, key: str) -> str:
    value = mapping.get(key)
    if value is None:
        value = mapping.get(key.encode("utf-8"))
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else ""


async def deliver_approval(
    *,
    session_id: str,
    approval_id: str,
    body: str,
    send: ApprovalSender,
    routing: Optional[RemoteApprovalRouting] = None,
    store: Optional[RemoteApprovalStore] = None,
) -> bool:
    """Ask *session_id*'s human for a decision, wherever they are.

    Returns True only when the message was sent **and** the correlation was
    recorded. Both matter: an approval delivered without a recorded correlation
    is one whose reply can never resolve it, so the human answers into a void.
    The correlation is therefore written **before** the send — a recorded
    delivery that never went out costs one stale Redis key, while a send whose
    correlation failed to persist costs the operator's answer.

    Returns False when the session is not routed remotely; the caller then asks
    inline exactly as it does today. This function never decides *whether*
    approval is required — only where the question goes.
    """
    target = await (routing or RemoteApprovalRouting()).target_for(session_id)
    if target is None:
        return False

    delivery_store = store or RemoteApprovalStore()
    recorded = await delivery_store.record_delivery(
        DeliveredApproval(approval_id=approval_id, platform=target.platform, channel_id=target.channel_id)
    )
    if not recorded:
        logger.warning("Not delivering approval %s: correlation could not be recorded", approval_id)
        return False

    try:
        sent = await send(platform=target.platform, channel_id=target.channel_id, body=embed_token(body, approval_id))
    except Exception as exc:  # noqa: BLE001 - a channel failure must not kill the run
        logger.error("Failed to deliver approval %s to %s: %s", approval_id, target.platform, exc)
        await delivery_store.forget(approval_id)
        return False

    if not sent:
        await delivery_store.forget(approval_id)
        return False
    return True


__all__ = [
    "ApprovalSender",
    "RemoteApprovalRouting",
    "RemoteTarget",
    "REMOTE_FLAG_TTL_SECONDS",
    "deliver_approval",
]
