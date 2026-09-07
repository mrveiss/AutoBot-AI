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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import timedelta
from enum import Enum
from typing import Any

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


class HolderError(ValueError):
    """An agent or task identity that reentrancy could not safely compare.

    Validated here because **nothing else validates it**. `Scope.parse` rejects
    seven malformed shapes, so *what* is claimed is checked to seven rules while
    *who owns it* was any string at all -- and the storage layer cannot make up
    the difference: a claim is JSON in Redis, with no column type and no
    constraint to fall back on. Two callers passing ``task_id=""`` would compare
    equal, become one holder, and silently take over each other's claims through
    the reentrancy path that exists to stop an agent deadlocking against itself.
    """


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
    def parse(cls, raw: str | Scope) -> Scope:
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

    def overlaps(self, other: Scope) -> bool:
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
local mine = path .. '|' .. agent .. '|' .. task
local members = redis.call('SMEMBERS', idx)
local renewing = false
for i = 1, #members do
  local member = members[i]
  local raw = redis.call('GET', prefix .. member)
  if not raw then
    redis.call('SREM', idx, member)
  else
    local sep = string.find(member, '|', 1, true)
    local held_path = string.sub(member, 1, sep - 1)
    local overlaps = held_path == path
      or string.sub(path, 1, #held_path + 1) == held_path .. '/'
      or string.sub(held_path, 1, #path + 1) == path .. '/'
    if overlaps then
      if member == mine then
        renewing = true
      else
        local held = cjson.decode(raw)
        local same_holder = held.agent_id == agent and held.task_id == task
        local both_shared = mode == 'shared' and held.mode == 'shared'
        if not same_holder and not both_shared then
          return {'conflict', raw}
        end
      end
    end
  end
end
redis.call('SET', prefix .. mine, payload, 'EX', ttl)
redis.call('SADD', idx, mine)
if renewing then return {'renewed', payload} end
return {'acquired', payload}
"""

# Ownership is now STRUCTURAL, not checked: a holder's key contains its own
# identity, so there is no key another holder could delete by mistake. The
# owner-check these scripts used to carry is gone because it became a
# tautology, not because the property was dropped.
_RELEASE_LUA = """
local idx, prefix = KEYS[1], ARGV[1]
local mine = ARGV[2] .. '|' .. ARGV[3] .. '|' .. ARGV[4]
redis.call('SREM', idx, mine)
return redis.call('DEL', prefix .. mine)
"""

# Renew rewrites the payload rather than only calling EXPIRE: `expires_at` is
# read by `list_claims` and by every `ClaimConflict`, so a TTL extended without
# it leaves a live claim advertising a time in the past, and a refused agent
# retries immediately against a holder it was told had expired.
_RENEW_LUA = """
local prefix, ttl, expires = ARGV[1], tonumber(ARGV[2]), ARGV[3]
local key = prefix .. ARGV[4] .. '|' .. ARGV[5] .. '|' .. ARGV[6]
local raw = redis.call('GET', key)
if not raw then return 0 end
local held = cjson.decode(raw)
held.expires_at = expires
redis.call('SET', key, cjson.encode(held), 'EX', ttl)
return 1
"""


def _require_holder(agent_id: str, task_id: str) -> None:
    """Reject a holder identity that reentrancy could not safely compare.

    Load-bearing, not belt-and-braces, and the reason is the storage layer.
    Elsewhere in this codebase an unguarded coercion of a tenant id turned out
    to be unfalsifiable because the column was ``UUID(as_uuid=True),
    nullable=False`` -- the schema already refused what the code did not. Here
    the opposite holds: a claim is JSON in Redis, with no column type and no
    constraint anywhere behind it. Nothing else can catch a blank identity.

    And a blank one is not merely untidy. Reentrancy compares ``(agent_id,
    task_id)``, so two callers that both passed ``task_id=""`` would compare
    equal, become one holder, and silently take over each other's claims
    through the path that exists to stop an agent deadlocking against itself.
    """
    for label, value in (("agent_id", agent_id), ("task_id", task_id)):
        if not isinstance(value, str) or not value.strip():
            raise HolderError(f"{label} must be a non-empty string; got {value!r}")


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


async def _acquire(
    scope: str | Scope,
    *,
    agent_id: str,
    task_id: str,
    mode: ClaimMode,
    intent: str,
    ttl_s: int | None,
) -> tuple[str, Claim | ClaimConflict]:
    """Acquire, returning the verdict alongside the result.

    The verdict distinguishes a fresh ``acquired`` from a ``renewed`` -- a
    re-acquisition by a holder that already had this exact scope. Only the
    caller that acquired it fresh may release it, which is what stops a nested
    :func:`work_claim` from releasing the scope its outer block is still using.
    """
    parsed = Scope.parse(scope)
    _require_holder(agent_id, task_id)
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
        return verdict, ClaimConflict(requested=str(parsed), holder=_decode(outcome[1]))
    return verdict, claim


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
    _, result = await _acquire(scope, agent_id=agent_id, task_id=task_id, mode=mode, intent=intent, ttl_s=ttl_s)
    return result


async def release(scope: str | Scope, *, agent_id: str, task_id: str) -> bool:
    """Release this holder's claim on *scope*. True when one went.

    A holder can only ever address its own key, so releasing another agent's
    claim is not refused -- it is unaddressable. Passing someone else's scope
    deletes nothing and returns False.
    """
    parsed = Scope.parse(scope)
    _require_holder(agent_id, task_id)
    client = await _redis()
    removed = int(
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
    return removed == 1


async def renew(scope: str | Scope, *, agent_id: str, task_id: str, ttl_s: int | None = None) -> bool:
    """Extend a held claim's TTL **and** its advertised expiry. False once gone."""
    parsed = Scope.parse(scope)
    _require_holder(agent_id, task_id)
    ttl = CLAIM_TTL_S if ttl_s is None else ttl_s
    expires = (now_utc() + timedelta(seconds=ttl)).isoformat()
    client = await _redis()
    result = int(
        await client.eval(
            _RENEW_LUA,
            0,
            _CLAIM_PREFIX.format(kind=parsed.kind),
            str(ttl),
            expires,
            parsed.path,
            agent_id,
            task_id,
        )
    )
    return result == 1


async def list_claims(kind: str | None = None) -> list[Claim]:
    """Every live claim, expired entries pruned from the index as they are found.

    One ``MGET`` and at most one ``SREM`` per kind rather than a round trip per
    member: #15949 reads this path to render the projection, so it is read far
    more often than it is written.
    """
    client = await _redis()
    kinds = sorted(VALID_KINDS) if kind is None else [kind]
    claims: list[Claim] = []
    for k in kinds:
        if k not in VALID_KINDS:
            raise ScopeError(f"unknown scope kind {k!r}; kinds are {sorted(VALID_KINDS)}")
        index, prefix = _INDEX_KEY.format(kind=k), _CLAIM_PREFIX.format(kind=k)
        members = [m.decode() if isinstance(m, bytes) else m for m in await client.smembers(index)]
        if not members:
            continue
        payloads = await client.mget([f"{prefix}{m}" for m in members])
        vanished = [m for m, raw in zip(members, payloads) if raw is None]
        if vanished:
            await client.srem(index, *vanished)
        claims.extend(_decode(raw) for raw in payloads if raw is not None)
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
    verdict, outcome = await _acquire(scope, agent_id=agent_id, task_id=tid, mode=mode, intent=intent, ttl_s=ttl_s)
    if isinstance(outcome, ClaimConflict):
        raise ClaimConflictError(outcome)
    try:
        yield outcome
    finally:
        # Only the block that acquired the scope fresh releases it. Reentrancy
        # makes a nested `work_claim` over the same scope succeed as a renew, so
        # an unconditional release here would delete the claim on the inner
        # block's exit while the outer block was still writing -- and the scope
        # would be free for another agent mid-write, which is the exact
        # collision this module exists to prevent.
        if verdict == "acquired":
            await release(scope, agent_id=agent_id, task_id=tid)
