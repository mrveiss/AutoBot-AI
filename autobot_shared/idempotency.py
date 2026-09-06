# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Replay store for idempotent creations (#15778).

A retried ``POST`` that already committed server-side creates a second resource.
Agents retry constantly -- a timeout, a dropped WebSocket, a provider 502
mid-request, a recovery-resume -- and the caller cannot tell "the create failed"
from "the response was lost", because those look identical from outside.

The per-site half of this problem is a SAVEPOINT at the insert, which turns a
concurrent duplicate into the same answer a sequential one gets
(``user_service_conflict.py``, #15772). This is the general half: it does not
need to know which column collided, because it never lets the second write
happen at all.

THREE STATES, NOT TWO
---------------------
A key is unseen, **in flight**, or completed. Collapsing the middle state into
"unseen" is the bug this store exists to prevent: two retries racing would both
claim, both execute, and both create. ``SET NX`` makes the claim atomic, so
exactly one caller proceeds and the other is told the work is already running
rather than being handed a wrong answer.

The stored response is what makes a replay honest. Returning 200 with an empty
body, or a fresh 201 for a resource that already exists, both lie about what
happened; replaying the original status and body says "you already did this, and
here is what it produced".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: How long a completed response stays replayable. Long enough to outlive any
#: retry an agent or a proxy will make, short enough that the keyspace does not
#: grow without bound. Env-var-backed per the repository's TTL rule.
IDEMPOTENCY_TTL_SECONDS = env_int_clamped("AUTOBOT_IDEMPOTENCY_TTL_SECONDS", 24 * 60 * 60, min_v=60)

#: How long a claim may stay in flight before another caller may retry it. A
#: request that dies between claiming and completing would otherwise wedge the
#: key for the full TTL -- the caller could never retry the thing that failed.
IDEMPOTENCY_CLAIM_TTL_SECONDS = env_int_clamped("AUTOBOT_IDEMPOTENCY_CLAIM_TTL_SECONDS", 300, min_v=5)

_KEY_PREFIX = "idempotency:"
_IN_FLIGHT = "__in_flight__"


@dataclass(frozen=True)
class ReplayedResponse:
    """A completed response, stored verbatim for replay."""

    status_code: int
    body: str
    resource_id: str | None = None


def storage_key(actor: str, method: str, path: str, client_key: str) -> str:
    """Namespace the caller's key by actor and route.

    Two callers may legitimately choose the same key, and one caller may reuse a
    key across endpoints without meaning to; either would otherwise replay a
    response belonging to a different request. The digest keeps a caller-supplied
    value out of the keyspace, which is also what stops a long or malformed
    header becoming a Redis key.
    """
    material = "\x1f".join((actor, method.upper(), path, client_key))
    return _KEY_PREFIX + hashlib.sha256(material.encode("utf-8")).hexdigest()


async def claim(redis: Any, key: str) -> ReplayedResponse | None | str:
    """Claim *key*, or report what is already there.

    Returns ``None`` when the claim succeeded and the caller should proceed,
    :data:`_IN_FLIGHT` when another request holds it, or a
    :class:`ReplayedResponse` when the original already completed.
    """
    claimed = await redis.set(key, _IN_FLIGHT, nx=True, ex=IDEMPOTENCY_CLAIM_TTL_SECONDS)
    if claimed:
        return None
    existing = await redis.get(key)
    if existing is None:
        # The claim expired between SET NX and GET. Treat it as unseen rather
        # than as in-flight: refusing here would strand a caller behind a key
        # that no longer exists.
        return None
    return _decode(existing)


async def complete(redis: Any, key: str, response: ReplayedResponse) -> None:
    """Record the response a claimed key produced, making it replayable."""
    payload = json.dumps(
        {"status_code": response.status_code, "body": response.body, "resource_id": response.resource_id}
    )
    await redis.set(key, payload, ex=IDEMPOTENCY_TTL_SECONDS)


async def release(redis: Any, key: str) -> None:
    """Drop a claim whose request failed, so the caller may retry it.

    A failed create is not a completed one: holding the key would make the retry
    -- the thing the caller must do -- impossible for the length of the TTL.
    """
    await redis.delete(key)


def _decode(raw: Any) -> ReplayedResponse | str:
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    if text == _IN_FLIGHT:
        return _IN_FLIGHT
    try:
        data = json.loads(text)
        return ReplayedResponse(
            status_code=int(data["status_code"]), body=data["body"], resource_id=data.get("resource_id")
        )
    except (ValueError, KeyError, TypeError):
        # A malformed record must not resurrect as a wrong replay; treat it as
        # in flight so the caller retries rather than receiving nonsense.
        logger.warning("discarding malformed idempotency record")
        return _IN_FLIGHT


IN_FLIGHT = _IN_FLIGHT
