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

EVERY EXIT FROM THE CLAIM IS ATOMIC
-----------------------------------
Two interleavings defeat a store that only reasons about the happy path, and
both end in the duplicate creation the store exists to stop:

*Expiry between SET and GET.* Both callers lose ``SET NX`` to a claim that then
expires, both read an empty key, and a store that reports "unseen" there has
just told both of them to proceed. The only honest read of a vanished record is
to re-run the atomic claim, which exactly one of them wins.

*A request outliving its claim.* ``IDEMPOTENCY_CLAIM_TTL_SECONDS`` is a bound on
how long a claim is honoured, not on how long a request may take. Once it
lapses a second caller legitimately claims the key -- and the first, still
running, would then overwrite that caller's response or delete its claim, after
which a third caller creates yet another resource. Each claim therefore carries
an opaque fencing token, and ``complete``/``release`` change Redis only while
the stored marker is still the one that request wrote. A late writer finds a
token that is not its own and is refused, which is the whole point of the
token: being slow must not let a request corrupt a successor's state.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import secrets
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

#: How many times :func:`claim` re-runs the atomic claim after finding the
#: record it lost to has already expired. Bounded so a key expiring on every
#: pass cannot spin forever; losing that race repeatedly is already pathological,
#: and the bounded exit reports "in flight", which costs a retry rather than a
#: duplicate resource.
IDEMPOTENCY_CLAIM_ATTEMPTS = env_int_clamped("AUTOBOT_IDEMPOTENCY_CLAIM_ATTEMPTS", 3, min_v=1, max_v=10)

_KEY_PREFIX = "idempotency:"
_IN_FLIGHT = "__in_flight__"

#: Compare-and-set: store the completed response only while the key still holds
#: the marker this request wrote. Redis runs a script atomically, so no second
#: caller can claim the key between the read and the write.
_COMPLETE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
  return 1
end
return 0
"""

#: Compare-and-delete, for the same reason: a request whose claim already
#: lapsed must not delete the claim its successor now holds.
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class ReplayedResponse:
    """A completed response, stored verbatim for replay.

    ``body`` is **bytes**, base64 in the record. It was a ``str`` and decoded as
    UTF-8 on the way in, which made a successful non-UTF-8 response wedge its own
    key: the decode raised after the handler had already committed, so the claim
    was neither completed nor released and every retry got 409 until the TTL
    (#15778 review). Bytes also make the replay byte-exact rather than
    round-tripped.

    ``media_type`` is carried because replaying every response as
    ``application/json`` misdescribes a handler that returned anything else --
    the replay must be indistinguishable from the original, or it is a different
    answer wearing the same status code.
    """

    status_code: int
    body: bytes
    media_type: str | None = None
    resource_id: str | None = None


@dataclass(frozen=True)
class Claim:
    """What claiming a key produced -- exactly one of the three states.

    ``token`` set means the caller holds the claim and must proceed; it is the
    fencing token :func:`complete` and :func:`release` check before touching the
    key. ``in_flight`` means another request holds it. ``replay`` means the
    original already completed and its response is here.
    """

    token: str | None = None
    in_flight: bool = False
    replay: ReplayedResponse | None = None


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


def _marker(token: str) -> str:
    """The in-flight value a claim writes: the state, plus who holds it."""
    return f"{_IN_FLIGHT}:{token}"


async def claim(redis: Any, key: str) -> Claim:
    """Claim *key*, or report what is already there.

    Retries the atomic claim -- rather than reporting "unseen" -- when the
    record it lost to has expired by the time it is read. Reporting unseen there
    hands the same verdict to every loser of the race, and they all create.
    """
    for _ in range(IDEMPOTENCY_CLAIM_ATTEMPTS):
        token = secrets.token_hex(16)
        if await redis.set(key, _marker(token), nx=True, ex=IDEMPOTENCY_CLAIM_TTL_SECONDS):
            return Claim(token=token)
        existing = await redis.get(key)
        if existing is not None:
            return _decode(existing)
    logger.warning("idempotency claim lost %d races to an expiring key", IDEMPOTENCY_CLAIM_ATTEMPTS)
    return Claim(in_flight=True)


async def complete(redis: Any, key: str, token: str, response: ReplayedResponse) -> bool:
    """Record the response a claimed key produced, making it replayable.

    Only while *token* still holds the key: a request that outlived its claim
    would otherwise publish its own response under a successor's claim, and the
    successor's caller would be handed the wrong resource.
    """
    payload = json.dumps(
        {
            "status_code": response.status_code,
            "body_b64": base64.b64encode(response.body).decode("ascii"),
            "media_type": response.media_type,
            "resource_id": response.resource_id,
        }
    )
    stored = await redis.eval(_COMPLETE_SCRIPT, 1, key, _marker(token), payload, str(IDEMPOTENCY_TTL_SECONDS))
    if not _truthy(stored):
        logger.warning("idempotency claim was no longer held at completion; response not stored")
        return False
    return True


async def release(redis: Any, key: str, token: str) -> bool:
    """Drop a claim whose request failed, so the caller may retry it.

    A failed create is not a completed one: holding the key would make the retry
    -- the thing the caller must do -- impossible for the length of the TTL.
    Bounded by the same fencing token, so a lapsed request cannot delete the
    claim a live one now holds.
    """
    dropped = await redis.eval(_RELEASE_SCRIPT, 1, key, _marker(token))
    return _truthy(dropped)


def _truthy(reply: Any) -> bool:
    """Redis returns integers for these scripts; clients type them loosely."""
    try:
        return int(reply or 0) > 0
    except (TypeError, ValueError):
        return bool(reply)


def _decode(raw: Any) -> Claim:
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    if text.startswith(_IN_FLIGHT):
        return Claim(in_flight=True)
    try:
        data = json.loads(text)
        return Claim(
            replay=ReplayedResponse(
                status_code=int(data["status_code"]),
                body=base64.b64decode(data["body_b64"]),
                media_type=data.get("media_type"),
                resource_id=data.get("resource_id"),
            )
        )
    except (ValueError, KeyError, TypeError, binascii.Error):
        # A malformed record must not resurrect as a wrong replay; treat it as
        # in flight so the caller retries rather than receiving nonsense.
        logger.warning("discarding malformed idempotency record")
        return Claim(in_flight=True)


IN_FLIGHT = _IN_FLIGHT
