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
"""

from __future__ import annotations

import asyncio
import json
import uuid

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_utils import delete_if_value
from services.command_approval_manager import AgentRole

from .models import AgentSessionState, AgentTerminalSession

logger = get_logger(__name__)

READ_TIMEOUT_SECONDS: float = 2.0

#: Crash safety net only: a worker that dies holding a decision claim frees it after this long. A run that
#: fails releases its claim at once (``release_decision``); a successful one keeps it.
DECISION_TTL_SECONDS: int = env_int("AUTOBOT_APPROVAL_DECISION_TTL_SECONDS", default=600)

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


def session_key(session_id: str) -> str:
    return f"agent_terminal:session:{session_id}"


def decision_key(session_id: str, command_id: str | None) -> str:
    return f"agent_terminal:decision:{session_id}:{command_id or 'restored'}"


async def read_record(redis, session_id: str) -> dict | None:
    """The session's record in Redis; ``None`` if absent. Raises on a timeout or a Redis error."""
    raw = await asyncio.wait_for(redis.get(session_key(session_id)), timeout=READ_TIMEOUT_SECONDS)
    return json.loads(raw) if raw else None


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


async def claim_decision(redis, session_id: str, command_id: str | None) -> str | None:
    """Win the one decision on this approval; return the claim's token, or ``None`` if it was already taken."""
    token = uuid.uuid4().hex
    if await redis.set(decision_key(session_id, command_id), token, nx=True, ex=DECISION_TTL_SECONDS):
        return token
    logger.warning("Approval %s of session %s was already decided", command_id, session_id)
    return None


async def release_decision(redis, session_id: str, command_id: str | None, token: str) -> bool:
    """Give the decision back after a run that failed, so the approval can be answered again.

    Releases only the claim that carries *token*. A successful or still-running command never calls this,
    so its claim stays and refuses a second run.
    """
    return await delete_if_value(redis, decision_key(session_id, command_id), token)
