# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Correlating an approval delivered to a chat channel with the reply (#14068).

An approval can only be answered by a human looking at the app. For a platform
that runs unattended loops that makes an approval nobody can answer a stall, and
the only workaround — lowering the guard profile — grants the agent *more*
autonomy when what was needed was a different way to reach the person.

This module is the correlation half: embed a token in the delivered message,
recognise it in a reply, and map it back to the pending approval. Delivery
itself and the per-session routing flag are the next change in the stack; this
one has no side effects beyond its own Redis keys.

Fail-closed throughout. An unparseable reply, an unknown token, or a reply with
no clear decision resolves **nothing** — silence is not consent, and neither is
a thumbs-up on a message we cannot tie to a request.

Not built on ``services/slack_approval_integration.py``: that store is keyed by
workflow node and named for one platform, and bending a node-shaped, Slack-named
record into a channel-agnostic approval correlation would consolidate by
contortion. Its Slack thread tracking is still the right thing for the Slack
adapter's ``thread_ts`` and is wired in the delivery change, not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

#: Redis key prefix for a pending approval's delivery record.
_DELIVERY_KEY_PREFIX = "approval:delivery:"

#: How long a delivered approval stays correlatable. Beyond this the reply can
#: no longer be tied to a request, and fail-closed means it resolves nothing.
REMOTE_APPROVAL_TTL_SECONDS = env_int("AUTOBOT_REMOTE_APPROVAL_TTL_SECONDS", 86400)

#: The correlation token, embedded in the delivered message.
#: Deliberately narrow: the id charset is bounded so a token cannot be forged by
#: pasting arbitrary text, and the pattern cannot span lines.
_TOKEN_RE = re.compile(r"\[ab:([A-Za-z0-9][A-Za-z0-9._-]{0,63})\]")

_APPROVE_WORDS = frozenset({"approve", "approved", "yes", "ok", "okay", "lgtm", "go", "allow"})
_DENY_WORDS = frozenset({"deny", "denied", "no", "reject", "rejected", "stop", "block"})
_APPROVE_EMOJI = ("👍", "✅", "☑️", "✔️")
_DENY_EMOJI = ("👎", "❌", "🛑", "✖️")


def embed_token(body: str, approval_id: str) -> str:
    """Append the correlation token to *body*.

    The token is what makes a reply resolvable. A delivered message without one
    is undeliverable rather than best-effort: a human answering a message we
    cannot correlate would believe they had approved something.
    """
    if not approval_id or not _TOKEN_RE.fullmatch(f"[ab:{approval_id}]"):
        raise ValueError(f"approval id is not token-safe: {approval_id!r}")
    return f"{body}\n\n[ab:{approval_id}]"


def extract_token(text: str) -> Optional[str]:
    """The approval id referenced by *text*, or None.

    Returns None when the text carries more than one token: a reply quoting two
    approvals names no single decision, and guessing which one would resolve the
    wrong request.
    """
    if not isinstance(text, str):
        return None
    found = _TOKEN_RE.findall(text)
    if len(found) != 1:
        return None
    return found[0]


def parse_decision(text: str) -> Optional[bool]:
    """True to approve, False to deny, None when the reply says neither.

    A reply containing both an approve and a deny signal returns None rather
    than picking one — "no, don't approve" must not read as approval because it
    contains the word.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    lowered = text.lower()
    approve = any(e in text for e in _APPROVE_EMOJI) or bool(_APPROVE_WORDS & set(re.findall(r"[a-z]+", lowered)))
    deny = any(e in text for e in _DENY_EMOJI) or bool(_DENY_WORDS & set(re.findall(r"[a-z]+", lowered)))

    if approve == deny:  # neither, or contradictory
        return None
    return approve


@dataclass(frozen=True)
class DeliveredApproval:
    """Where a pending approval was sent, so a reply can be tied back to it."""

    approval_id: str
    platform: str
    channel_id: str


@dataclass(frozen=True)
class ResolvedReply:
    """A reply that named exactly one known approval and one clear decision."""

    approval_id: str
    approved: bool
    platform: str
    channel_id: str


class RemoteApprovalStore:
    """Redis-backed record of which approvals were delivered where."""

    async def record_delivery(self, delivery: DeliveredApproval) -> bool:
        """Remember that *delivery* went out. False when Redis is unavailable."""
        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("Redis unavailable — approval %s delivered uncorrelated", delivery.approval_id)
            return False
        try:
            await redis.hset(
                f"{_DELIVERY_KEY_PREFIX}{delivery.approval_id}",
                mapping={"platform": delivery.platform, "channel_id": delivery.channel_id},
            )
            await redis.expire(f"{_DELIVERY_KEY_PREFIX}{delivery.approval_id}", REMOTE_APPROVAL_TTL_SECONDS)
            return True
        except Exception as exc:  # noqa: BLE001 - a correlation we cannot store is not a crash
            logger.error("Failed to record approval delivery %s: %s", delivery.approval_id, exc)
            return False

    async def get_delivery(self, approval_id: str) -> Optional[DeliveredApproval]:
        """The recorded delivery for *approval_id*, or None if unknown/expired."""
        redis = await get_async_redis_client()
        if redis is None:
            return None
        try:
            data = await redis.hgetall(f"{_DELIVERY_KEY_PREFIX}{approval_id}")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to read approval delivery %s: %s", approval_id, exc)
            return None
        if not data:
            return None
        platform = _decoded(data, "platform")
        channel_id = _decoded(data, "channel_id")
        if not platform or not channel_id:
            return None
        return DeliveredApproval(approval_id=approval_id, platform=platform, channel_id=channel_id)

    async def forget(self, approval_id: str) -> None:
        """Drop the correlation once the approval is resolved."""
        redis = await get_async_redis_client()
        if redis is None:
            return
        try:
            await redis.delete(f"{_DELIVERY_KEY_PREFIX}{approval_id}")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to clear approval delivery %s: %s", approval_id, exc)


def _decoded(mapping: dict, key: str) -> str:
    """Field from a Redis hash, tolerating bytes or str keys and values."""
    value = mapping.get(key)
    if value is None:
        value = mapping.get(key.encode("utf-8"))
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else ""


async def resolve_from_reply(
    text: str,
    *,
    platform: str,
    channel_id: str,
    store: Optional[RemoteApprovalStore] = None,
) -> Optional[ResolvedReply]:
    """Tie a channel reply back to a pending approval, or return None.

    Every rejection path is deliberate and silent-by-design at the caller:

    * no token, or more than one — nothing to resolve;
    * no clear decision, or a contradictory one — the human has not answered;
    * a token we never delivered, or one that expired — not ours to act on;
    * a reply arriving on a different platform or channel than the delivery —
      the reply must come back where the question was asked, or anyone able to
      post the token anywhere could answer for the operator.
    """
    approval_id = extract_token(text)
    if approval_id is None:
        return None

    decision = parse_decision(text)
    if decision is None:
        logger.info("Approval reply for %s carried no clear decision", approval_id)
        return None

    delivery = await (store or RemoteApprovalStore()).get_delivery(approval_id)
    if delivery is None:
        logger.info("Approval reply names unknown or expired approval %s", approval_id)
        return None

    if delivery.platform != platform or delivery.channel_id != channel_id:
        logger.warning(
            "Approval reply for %s arrived on %s:%s but was delivered to %s:%s — ignored",
            approval_id,
            platform,
            channel_id,
            delivery.platform,
            delivery.channel_id,
        )
        return None

    return ResolvedReply(approval_id=approval_id, approved=decision, platform=platform, channel_id=channel_id)


__all__ = [
    "DeliveredApproval",
    "RemoteApprovalStore",
    "ResolvedReply",
    "REMOTE_APPROVAL_TTL_SECONDS",
    "embed_token",
    "extract_token",
    "parse_decision",
    "resolve_from_reply",
]
