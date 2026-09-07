# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Work claims -- which agent is holding which scope, and for how long (#15947).

Several agents can work one project at once. `a2a/task_manager.py` tracks
*tasks* and `agents/agent_orchestration/coordinator.py` routes *requests*;
neither records the resource an agent is currently holding, so two agents given
overlapping work overwrite each other and the loser's work is lost with no error
anywhere.

A claim answers three questions and no others:

* **who** holds a scope -- ``agent_id`` and ``task_id``,
* **why** -- a human-readable ``intent``, so a refusal is actionable rather than
  a bare boolean,
* **until when** -- every claim has a TTL, so a crashed agent frees its scope.

THE TTL IS THE POINT, not a detail. A lock that can outlive its holder turns one
dead agent into a permanently blocked project, which is worse than the collision
it prevents. Nothing here is durable: Redis is the system of record for
``agent_work_claims`` (see :mod:`autobot_shared.store_authority`) precisely
because a claim is meant to evaporate.

SCOPE GRAMMAR is ``<kind>:<segment>/<segment>/...``. A claim covers its
**subtree**: ``path:autobot-backend/llc`` overlaps
``path:autobot-backend/llc/budget.py``, and prefixes are segment-aligned, so
``path:a/b`` does not overlap ``path:a/bc.py``.

There is deliberately no separate ``dir`` kind. Two kinds sharing one namespace
-- a file scope and a directory scope over the same tree -- would need the
overlap rule to know that ``dir`` and ``file`` are the same namespace while
``kb`` and ``device`` are not, and a rule with an exception table is the kind
nobody applies correctly at the next call site. One ``path`` kind whose claims
are subtrees says the same thing with no exception.

RELATIONSHIP TO ``services/task_claim.py`` (GH#6468), which must be understood
before anything here is extended. That module already claims **task ids** --
flat, exclusive-only, ``SET NX EX`` with owner-checked Lua release and renew --
and `distributed_management.py` uses it to stop two agents picking up one task.
It is the special case of this primitive: one scope kind, no hierarchy, no
shared mode. The two are deliberately *not* merged here, because collapsing them
means changing a live double-pickup guard, and that belongs in its own issue with
its own tests rather than riding a new primitive's first commit -- filed as #15957.

What matters is that nobody adds a third: **task identity stays
``task_claim``'s**, which is why ``task`` is not one of :data:`VALID_KINDS`. A
claim on the work a task will touch is this module's; a claim on the task itself
is that module's.

WHAT THIS IS NOT: not a distributed transaction manager, not a substitute for
database constraints, and not an enforcement mechanism on its own. Layer 1 is
advisory by contract -- #15950 is what makes declared write sites acquire before
they write. The negotiation that follows a refusal (waitlist, yield,
arbitration) is #15948; the user-visible projection of who holds what is #15949.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import timedelta
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, AsyncIterator

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

#: How long a claim survives without a renew. Short enough that a crashed agent
#: frees its scope within a work step, long enough that a slow one does not lose
#: it mid-write. Renewed by :func:`renew` for the life of a running task
#: (#15950), so the ceiling is not a limit on task duration.
CLAIM_TTL_S = env_int_clamped("AUTOBOT_WORK_CLAIM_TTL_S", 300, min_v=10, max_v=3600)

#: Namespaces a scope can name. A claim never spans two of them.
VALID_KINDS = frozenset({"path", "kb", "device", "project", "config"})

_SEGMENT = re.compile(r"^[A-Za-z0-9._@+-]+$")
_CLAIM_PREFIX = "work_claims:c:{kind}:"
_INDEX_KEY = "work_claims:idx:{kind}"


class ClaimMode(str, Enum):
    """Whether a holder intends to write the scope or only to read it."""

    EXCLUSIVE = "exclusive"  # write intent -- conflicts with any overlap
    SHARED = "shared"  # read intent -- coexists with other SHARED holders


class ScopeError(ValueError):
    """A scope string that cannot be parsed, with the reason stated."""


class ClaimUnavailable(RuntimeError):
    """Redis is not reachable, so no claim can be made or trusted."""


@dataclass(frozen=True)
class Scope:
    """A ``<kind>:<path>`` resource identifier whose claims cover its subtree."""

    kind: str
    path: str

    def __str__(self) -> str:
        return f"{self.kind}:{self.path}"

    @classmethod
    def parse(cls, raw: str | "Scope") -> "Scope":
        """Parse *raw*, rejecting anything the overlap rule could not compare.

        Raises:
            ScopeError: unknown kind, empty or malformed path, ``.``/``..`` or
                empty segments, or characters outside ``[A-Za-z0-9._@+-]``.
        """
        if isinstance(raw, Scope):
            return raw
        kind, sep, path = raw.partition(":")
        if not sep:
            raise ScopeError(f"scope {raw!r} has no '<kind>:' prefix; kinds are {sorted(VALID_KINDS)}")
        if kind not in VALID_KINDS:
            raise ScopeError(f"unknown scope kind {kind!r}; kinds are {sorted(VALID_KINDS)}")
        segments = path.split("/")
        if not path or any(not s for s in segments):
            raise ScopeError(f"scope {raw!r} has an empty path segment")
        for segment in segments:
            if segment in (".", ".."):
                raise ScopeError(f"scope {raw!r} contains a relative segment {segment!r}")
            if not _SEGMENT.match(segment):
                raise ScopeError(f"scope {raw!r} has an unusable segment {segment!r}")
        return cls(kind=kind, path="/".join(segments))

    def overlaps(self, other: "Scope") -> bool:
        """True when a claim on one would cover the other.

        Same kind, and one path is a **segment-aligned** prefix of the other, so
        ``path:a/b`` covers ``path:a/b/c`` but not ``path:a/bc``.
        """
        if self.kind != other.kind:
            return False
        if self.path == other.path:
            return True
        return other.path.startswith(f"{self.path}/") or self.path.startswith(f"{other.path}/")


@dataclass(frozen=True)
class Claim:
    """A held scope: who holds it, why, and when it expires without a renew."""

    scope: str
    agent_id: str
    task_id: str
    mode: str
    intent: str
    acquired_at: str
    expires_at: str

    @property
    def parsed_scope(self) -> Scope:
        return Scope.parse(self.scope)


@dataclass(frozen=True)
class ClaimConflict:
    """A refusal that names its holder, so the loser can act on it.

    Returned by :func:`try_acquire` and raised by :func:`work_claim`. Carrying
    the holder is the whole point -- a bare ``False`` leaves the second agent
    with nothing to wait for, ask, or escalate (#15948).
    """

    requested: str
    holder: Claim

    def __str__(self) -> str:
        return (
            f"{self.requested} is held by agent {self.holder.agent_id} "
            f"(task {self.holder.task_id}, {self.holder.mode}) until "
            f"{self.holder.expires_at}: {self.holder.intent}"
        )


class ClaimConflictError(RuntimeError):
    """Raised by :func:`work_claim` when the scope is held by someone else."""

    def __init__(self, conflict: ClaimConflict) -> None:
        super().__init__(str(conflict))
        self.conflict = conflict


# ``cjson`` is available in Redis Lua. Each script is one round trip and runs
# atomically, which is what makes "no two overlapping exclusive claims" true
# across uvicorn workers -- a read-then-write in Python cannot promise it.
_ACQUIRE_LUA = """
local idx, prefix, path = KEYS[1], ARGV[1], ARGV[2]
local mode, payload, ttl = ARGV[3], ARGV[4], tonumber(ARGV[5])
local agent, task = ARGV[6], ARGV[7]
local members = redis.call('SMEMBERS', idx)
for i = 1, #members do
  local held_path = members[i]
  local raw = redis.call('GET', prefix .. held_path)
  if not raw then
    redis.call('SREM', idx, held_path)
  else
    local overlaps = held_path == path
      or string.sub(path, 1, #held_path + 1) == held_path .. '/'
      or string.sub(held_path, 1, #path + 1) == path .. '/'
    if overlaps then
      local held = cjson.decode(raw)
      local mine = held.agent_id == agent and held.task_id == task
      local both_shared = mode == 'shared' and held.mode == 'shared'
      if not mine and not both_shared then
        return {'conflict', raw}
      end
    end
  end
end
redis.call('SET', prefix .. path, payload, 'EX', ttl)
redis.call('SADD', idx, path)
return {'acquired', payload}
"""

# Ownership-checked on purpose: releasing or renewing someone else's claim is
# how a coordination primitive becomes the collision it exists to prevent.
_RELEASE_LUA = """
local idx, prefix, path = KEYS[1], ARGV[1], ARGV[2]
local agent, task = ARGV[3], ARGV[4]
local raw = redis.call('GET', prefix .. path)
if not raw then
  redis.call('SREM', idx, path)
  return 0
end
local held = cjson.decode(raw)
if held.agent_id ~= agent or held.task_id ~= task then
  return -1
end
redis.call('DEL', prefix .. path)
redis.call('SREM', idx, path)
return 1
"""

_RENEW_LUA = """
local prefix, path, ttl = ARGV[1], ARGV[2], tonumber(ARGV[3])
local agent, task = ARGV[4], ARGV[5]
local raw = redis.call('GET', prefix .. path)
if not raw then return 0 end
local held = cjson.decode(raw)
if held.agent_id ~= agent or held.task_id ~= task then return -1 end
redis.call('EXPIRE', prefix .. path, ttl)
return 1
"""


async def _redis() -> Any:
    """The async Redis client, or a stated failure -- never a silent no-op."""
    client = await get_async_redis_client(database="main")
    if client is None:
        raise ClaimUnavailable("work_claims: Redis client unavailable; no claim can be made or trusted")
    return client


def _decode(raw: bytes | str) -> Claim:
    if isinstance(raw, bytes):
        raw = raw.decode()
    return Claim(**json.loads(raw))


def _build(scope: Scope, agent_id: str, task_id: str, mode: ClaimMode, intent: str, ttl_s: int) -> Claim:
    acquired = now_utc()
    return Claim(
        scope=str(scope),
        agent_id=agent_id,
        task_id=task_id,
        mode=mode.value,
        intent=intent,
        acquired_at=acquired.isoformat(),
        expires_at=(acquired + timedelta(seconds=ttl_s)).isoformat(),
    )


async def try_acquire(
    scope: str | Scope,
    *,
    agent_id: str,
    task_id: str,
    mode: ClaimMode = ClaimMode.EXCLUSIVE,
    intent: str,
    ttl_s: int | None = None,
) -> Claim | ClaimConflict:
    """Claim *scope*, or return the conflict naming who holds it.

    Never raises on contention -- a refusal is an ordinary answer here, and the
    caller decides whether to wait, queue, ask, or pick different work (#15948).

    Re-acquiring a scope this ``(agent_id, task_id)`` already holds is a renew,
    not a conflict: an agent that deadlocks against itself is a bug in the
    primitive, not in the caller.
    """
    parsed = Scope.parse(scope)
    ttl = CLAIM_TTL_S if ttl_s is None else ttl_s
    claim = _build(parsed, agent_id, task_id, mode, intent, ttl)
    client = await _redis()
    outcome = await client.eval(
        _ACQUIRE_LUA,
        1,
        _INDEX_KEY.format(kind=parsed.kind),
        _CLAIM_PREFIX.format(kind=parsed.kind),
        parsed.path,
        mode.value,
        json.dumps(asdict(claim)),
        str(ttl),
        agent_id,
        task_id,
    )
    verdict = outcome[0].decode() if isinstance(outcome[0], bytes) else outcome[0]
    if verdict == "conflict":
        return ClaimConflict(requested=str(parsed), holder=_decode(outcome[1]))
    return claim


async def release(scope: str | Scope, *, agent_id: str, task_id: str) -> bool:
    """Release a claim this ``(agent_id, task_id)`` holds. True when one went.

    Releasing a scope held by someone else is refused rather than obeyed, and
    logged: it means two agents disagree about who owns the work.
    """
    parsed = Scope.parse(scope)
    client = await _redis()
    result = int(
        await client.eval(
            _RELEASE_LUA,
            1,
            _INDEX_KEY.format(kind=parsed.kind),
            _CLAIM_PREFIX.format(kind=parsed.kind),
            parsed.path,
            agent_id,
            task_id,
        )
    )
    if result == -1:
        logger.warning("work_claims: agent %s tried to release %s held by another holder", agent_id, parsed)
        return False
    return result == 1


async def renew(scope: str | Scope, *, agent_id: str, task_id: str, ttl_s: int | None = None) -> bool:
    """Extend a held claim's TTL. False when it has already expired or moved on."""
    parsed = Scope.parse(scope)
    client = await _redis()
    result = int(
        await client.eval(
            _RENEW_LUA,
            0,
            _CLAIM_PREFIX.format(kind=parsed.kind),
            parsed.path,
            str(CLAIM_TTL_S if ttl_s is None else ttl_s),
            agent_id,
            task_id,
        )
    )
    if result == -1:
        logger.warning("work_claims: agent %s tried to renew %s held by another holder", agent_id, parsed)
    return result == 1


async def list_claims(kind: str | None = None) -> list[Claim]:
    """Every live claim, expired entries pruned from the index as they are found.

    Expiry is Redis's job; the index is a list of paths that *had* a claim, so a
    read is where a vanished one gets cleaned up.
    """
    client = await _redis()
    kinds = sorted(VALID_KINDS) if kind is None else [kind]
    claims: list[Claim] = []
    for k in kinds:
        if k not in VALID_KINDS:
            raise ScopeError(f"unknown scope kind {k!r}; kinds are {sorted(VALID_KINDS)}")
        index, prefix = _INDEX_KEY.format(kind=k), _CLAIM_PREFIX.format(kind=k)
        for member in await client.smembers(index):
            path = member.decode() if isinstance(member, bytes) else member
            raw = await client.get(f"{prefix}{path}")
            if raw is None:
                await client.srem(index, path)
                continue
            claims.append(_decode(raw))
    return claims


@asynccontextmanager
async def work_claim(
    scope: str | Scope,
    *,
    agent_id: str,
    task_id: str | None = None,
    mode: ClaimMode = ClaimMode.EXCLUSIVE,
    intent: str,
    ttl_s: int | None = None,
) -> AsyncIterator[Claim]:
    """Hold *scope* for the block, releasing it however the block exits.

    ``task_id`` defaults to a fresh id so an ad-hoc caller still gets
    reentrancy within its own block rather than sharing an identity with every
    other caller that omitted it.

    Raises:
        ClaimConflictError: the scope is held by someone else; the holder is on
            the exception as ``.conflict``.
    """
    tid = task_id or f"adhoc-{uuid.uuid4()}"
    outcome = await try_acquire(scope, agent_id=agent_id, task_id=tid, mode=mode, intent=intent, ttl_s=ttl_s)
    if isinstance(outcome, ClaimConflict):
        raise ClaimConflictError(outcome)
    try:
        yield outcome
    finally:
        await release(scope, agent_id=agent_id, task_id=tid)
