# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Terminal session state lives in Redis; a worker's copy is a cache (#20674).

Each uvicorn worker keeps its own ``AgentTerminalSession``. Redis holds the record, so a decision, or a
save, from a worker's older copy must be checked against it first:

* ``read_record`` / ``apply_record`` refresh the copy from Redis before anything reads it.
* ``persist_if_current`` writes only while the stored record is still the version the copy was read at,
  so an older copy cannot replace a newer approval (or make a held claim from #20059 look abandoned).
* ``claim_decision`` lets exactly one decision per approval through, whichever worker it is routed to.

Reads for display may fall back to the worker's cached copy (``SessionManager.get_session``). A decision
never does: ``read_authoritative_record`` and ``claim_decision`` raise ``ApprovalStateUnavailableError``
when Redis cannot confirm the approval, so a stale cached copy cannot authorise anything.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from services.command_approval_manager import AgentRole

from .models import AgentSessionState, AgentTerminalSession
from .redis_usability import usable_redis

logger = get_logger(__name__)

READ_TIMEOUT_SECONDS: float = 2.0

#: How long a decision claim is held. It must outlast the longest command a decision can start
#: (``AUTOBOT_SECURE_COMMAND_TIMEOUT_S``, at most 3600 s) plus the retries that persist the cleared record
#: (~160 s), or a second worker could win the claim while the command still runs (#20674). It is also the
#: crash safety net: a worker that dies holding a claim frees it after this long. A run that fails releases
#: its claim at once (``release_decision``); a successful one keeps it. No heartbeat exists to refresh it.
DECISION_TTL_SECONDS: int = env_int("AUTOBOT_APPROVAL_DECISION_TTL_SECONDS", default=2 * 60 * 60)

#: How long a session holding a pending approval survives in Redis (#13478). Deliberately long: the thing it is
#: waiting for is a person, and #13481 established that an approval does not expire on a timer. This bounds the
#: stored session, not the approval's validity.
APPROVAL_PENDING_SESSION_TTL: int = env_int("AUTOBOT_APPROVAL_PENDING_SESSION_TTL_SECONDS", default=7 * 24 * 60 * 60)

#: The shortest the decided marker may live: it must outlast the session record, so a rebuild can never meet an
#: approval whose marker has gone, and the claim that guards a running command (#21174).
DECIDED_MARKER_MIN_TTL_SECONDS: int = APPROVAL_PENDING_SESSION_TTL + DECISION_TTL_SECONDS

#: The durable "decided" marker outlives the session record (``APPROVAL_PENDING_SESSION_TTL``), the claim and the
#: chat-history window the rebuild reads, so a decided approval is never decidable again (#21174). A configured
#: value below ``DECIDED_MARKER_MIN_TTL_SECONDS`` is raised to it, never honoured.
DECIDED_MARKER_TTL_SECONDS: int = max(
    env_int("AUTOBOT_APPROVAL_DECIDED_MARKER_TTL_SECONDS", default=30 * 24 * 60 * 60), DECIDED_MARKER_MIN_TTL_SECONDS
)

#: Take the claim and write the decided marker as one step: both, or neither. An approval whose marker exists was
#: decided already, even if its claim has lapsed, so it is never granted again.
CLAIM_AND_MARK_LUA = """
if redis.call('EXISTS', KEYS[2]) == 1 then
  return 0
end
if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', tonumber(ARGV[2])) then
  redis.call('SET', KEYS[2], ARGV[1], 'EX', tonumber(ARGV[3]))
  return 1
end
return 0
"""

#: Give a failed run's approval back: drop the claim and the marker, each only while it still holds the token.
RELEASE_CLAIM_AND_MARK_LUA = """
local released = 0
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('DEL', KEYS[1])
  released = 1
end
if redis.call('GET', KEYS[2]) == ARGV[1] then
  redis.call('DEL', KEYS[2])
end
return released
"""

#: Write the record only while the stored one is still at the caller's version. Atomic in Redis.
PERSIST_IF_VERSION_LUA = """
local stored = redis.call('GET', KEYS[1])
if stored then
  local current = cjson.decode(stored)['version'] or 0
  if current ~= tonumber(ARGV[1]) then
    return 0
  end
end
redis.call('SETEX', KEYS[1], tonumber(ARGV[2]), ARGV[3])
return 1
"""


APPROVAL_STATE_UNAVAILABLE = "Approval state unavailable, retry"


class ApprovalStateUnavailableError(RuntimeError):
    """Redis cannot confirm the approval's state, so no decision may be made on it."""


def session_key(session_id: str) -> str:
    return f"agent_terminal:session:{session_id}"


def pending_decision_id(pending: dict | None) -> str | None:
    """What identifies one approval for its decision claim: its command id, else a digest of the request.

    An approval restored from chat history has no command id; its request timestamp and command tell it
    apart from the next restored approval of the same session.
    """
    if not pending:
        return None
    if pending.get("command_id"):
        return pending["command_id"]
    seed = f"{pending.get('timestamp')}|{pending.get('command')}"
    return "restored-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def decided_key(decision_id: str | None) -> str:
    """The durable marker of one approval, by its original command id (else the request digest)."""
    return f"agent_terminal:decided:{decision_id or 'unidentified'}"


def decision_key(session_id: str, decision_id: str | None) -> str:
    return f"agent_terminal:decision:{session_id}:{decision_id or 'unidentified'}"


async def read_record(redis, session_id: str) -> dict | None:
    """The session's record in Redis; ``None`` if absent. Raises on a timeout or a Redis error."""
    raw = await asyncio.wait_for(redis.get(session_key(session_id)), timeout=READ_TIMEOUT_SECONDS)
    return json.loads(raw) if raw else None


async def read_authoritative_record(redis, session_id: str) -> dict | None:
    """The record a decision acts on: ``None`` if Redis says it is absent, an error if Redis cannot say."""
    if not usable_redis(redis):
        raise ApprovalStateUnavailableError("no usable Redis client")
    try:
        return await read_record(redis, session_id)
    except Exception as exc:  # noqa: BLE001 - any failure to read means the approval is unconfirmed
        raise ApprovalStateUnavailableError(f"could not read session {session_id}: {exc}") from exc


def apply_record(session: AgentTerminalSession, data: dict) -> None:
    """Refresh *session*'s shared state in place from its Redis record, keeping its local handles."""
    session.state = AgentSessionState(data["state"])
    session.last_activity = data["last_activity"]
    session.pending_approval = data.get("pending_approval")
    session.version = data.get("version", 0)


def session_from_record(data: dict) -> AgentTerminalSession:
    """Build a session object from its Redis record."""
    session = AgentTerminalSession(
        session_id=data["session_id"],
        agent_id=data["agent_id"],
        agent_role=AgentRole(data["agent_role"]),
        conversation_id=data.get("conversation_id"),
        tenant_id=data.get("tenant_id"),
        host=data.get("host"),
        metadata=data.get("metadata", {}),
        pty_session_id=data.get("pty_session_id"),
        owner=data.get("owner"),
    )
    session.created_at = data["created_at"]
    apply_record(session, data)
    return session


async def persist_if_current(redis, session: AgentTerminalSession, ttl: int) -> bool:
    """Save *session* if Redis still holds the version it was read at; ``False`` on a stale copy."""
    expected = session.version
    payload = session.to_persist_dict()
    payload["version"] = expected + 1
    saved = await redis.eval(
        PERSIST_IF_VERSION_LUA, 1, session_key(session.session_id), expected, ttl, json.dumps(payload)
    )
    if saved:
        session.version = expected + 1
    return bool(saved)


async def claim_decision(redis, session_id: str, decision_id: str | None) -> str | None:
    """Win the one decision on this approval; return the claim's token, or ``None`` if it was already taken.

    Fails closed: without a usable Redis the claim cannot be made, so ``ApprovalStateUnavailableError``.
    """
    if not usable_redis(redis):
        raise ApprovalStateUnavailableError("no usable Redis client")
    token = uuid.uuid4().hex
    try:
        won = await redis.eval(
            CLAIM_AND_MARK_LUA,
            2,
            decision_key(session_id, decision_id),
            decided_key(decision_id),
            token,
            DECISION_TTL_SECONDS,
            DECIDED_MARKER_TTL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - an unconfirmed claim is a refused decision
        raise ApprovalStateUnavailableError(f"could not claim approval {decision_id}: {exc}") from exc
    if won:
        return token
    logger.warning("Approval %s of session %s was already decided", decision_id, session_id)
    return None


async def release_decision(redis, session_id: str, decision_id: str | None, token: str) -> bool:
    """Give the decision back after a run that failed, so the approval can be answered again.

    Releases the claim and the decided marker, each only while it carries *token*, so the approval is
    decidable again and a rebuild may restore it. A successful or still-running command never calls this:
    its claim and marker stay and refuse a second run, here and after a rebuild.
    """
    return bool(
        await redis.eval(
            RELEASE_CLAIM_AND_MARK_LUA, 2, decision_key(session_id, decision_id), decided_key(decision_id), token
        )
    )


async def decided_marker_exists(redis, decision_id: str | None) -> bool:
    """Whether the approval was ever claimed. Fails closed: an unreadable marker raises, never reads as absent."""
    if not usable_redis(redis):
        raise ApprovalStateUnavailableError("no usable Redis client")
    try:
        return bool(await asyncio.wait_for(redis.exists(decided_key(decision_id)), timeout=READ_TIMEOUT_SECONDS))
    except Exception as exc:  # noqa: BLE001 - an unconfirmed marker is a refused rebuild
        raise ApprovalStateUnavailableError(f"could not read decided marker {decision_id}: {exc}") from exc
