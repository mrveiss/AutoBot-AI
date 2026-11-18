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

RELATIONSHIP TO ``services/task_claim.py`` (GH#6468): that module claims **task ids**
-- flat, exclusive-only, ``SET NX EX`` -- and guards double pickup in
`distributed_management.py`. It is the special case of this primitive; merging
them is #15957's job, not this module's. Nobody adds a third: **task identity
stays ``task_claim``'s**, which is why ``task`` is not one of :data:`VALID_KINDS`.

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
from types import MappingProxyType
from typing import Any

from autobot_shared.coordination.claim_company import resolve_company
from autobot_shared.coordination.ledger_events import cap_text, note_refused_release, record_expired_members
from autobot_shared.coordination.work_claims_lua import _ACQUIRE_LUA, _RELEASE_LUA, _RENEW_LUA
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
#:
#: ``provider``, ``cpu`` and ``queue`` (#16951) claim a shared, contended
#: RESOURCE rather than a filesystem-shaped tree -- a provider's account-wide
#: quota, a CPU-time slot, a generic queue's concurrency slot. Each is a flat,
#: single-segment scope (e.g. ``provider:anthropic``), which needs no special
#: case: the existing subtree-overlap rule degrades correctly to exact-match
#: when a scope has no sub-segments, the same way ``project:acme`` already
#: behaves. No new overlap semantics, no new kind of kind.
#:
#: ``issue`` (#17091): a GitHub issue number, flat -- ``issue:17091`` has no
#: subtree, so the segment is always exactly one. It is the extension point for
#: "the same claim registry the agents use" applied to AutoBot's own dev-loop
#: participation. It is deliberately not a ``task``: an issue outlives any
#: single run that acts on it, and #15957's ``task`` refusal is about task
#: IDENTITY, so this belongs here rather than in ``services/task_claim.py``.
VALID_KINDS = frozenset({"path", "kb", "device", "project", "config", "provider", "cpu", "queue", "issue"})

#: Kinds this module deliberately refuses, and where each belongs instead.
#:
#: Being absent from :data:`VALID_KINDS` is not the same as being reserved.
#: Absent produces "unknown scope kind", which is what a typo produces, so a
#: caller reaching for ``task:`` here was told only that it had not been heard
#: of -- and could not tell a decision from a gap. The owner ruling on #15957
#: made the split permanent, so the refusal now names the reason and the
#: destination.
#:
#: Read-only, as :data:`VALID_KINDS` is a frozenset: a plain dict would let any
#: caller ``pop("task")`` and silently un-reserve it at runtime.
RESERVED_KINDS = MappingProxyType(
    {
        "task": "task identity belongs to services.task_claim, not to work_claims: "
        "a claim on the task is not a claim on the work the task touches, and one "
        "agent can hold a task while touching scopes it never claimed (#15957)",
    }
)


#: Kinds that name a single thing rather than a tree, so a claim on one is an
#: exact match and nothing else (#16951, #17091). Enforced at PARSE time
#: (review finding on #17380): `overlaps` compares segment-aligned prefixes, so
#: `issue:42/a` and `issue:42/b` are NOT overlapping and BOTH exclusive claims
#: succeed -- on the same issue, which is precisely the collision the registry
#: exists to prevent. The module already documented `issue` as "flat ... the
#: segment is always exactly one"; parsing simply did not enforce it.
#:
#: All four flat kinds, not just the one the review named: `provider:x/y` and
#: `provider:x/z` have the identical hole. Nothing in the tree uses a
#: multi-segment flat scope, checked before enforcing.
FLAT_KINDS = frozenset({"issue", "provider", "cpu", "queue"})


def _require_kind(kind: str) -> None:
    """Refuse a kind reserved for another module, or one that is not a kind.

    One function for every entry point that names a kind, so no two of them can
    drift into giving ``task`` different answers. It deliberately does not list
    its callers: such a list goes stale the moment one is added, which is how
    ``branch_stewardship.prune_closed_branches`` came to be missing from it (#15957). Reserved
    is checked first: reaching that arm means the caller had a real concept in
    mind, and "unknown kind" would answer a question they did not ask.
    """
    if kind in RESERVED_KINDS:
        raise ScopeError(f"scope kind {kind!r} is reserved: {RESERVED_KINDS[kind]}")
    if kind not in VALID_KINDS:
        raise ScopeError(f"unknown scope kind {kind!r}; kinds are {sorted(VALID_KINDS)}")


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
            ScopeError: a kind reserved for another module (see
                :data:`RESERVED_KINDS`), an unknown kind, empty or malformed
                path, ``.``/``..`` or empty segments, or characters outside
                ``[A-Za-z0-9._@+-]``.
        """
        if isinstance(raw, Scope):
            return raw
        kind, sep, path = raw.partition(":")
        if not sep:
            raise ScopeError(f"scope {raw!r} has no '<kind>:' prefix; kinds are {sorted(VALID_KINDS)}")
        _require_kind(kind)
        segments = path.split("/")
        if not path or any(not s for s in segments):
            raise ScopeError(f"scope {raw!r} has an empty path segment")
        for segment in segments:
            if segment in (".", ".."):
                raise ScopeError(f"scope {raw!r} contains a relative segment {segment!r}")
            if not _SEGMENT.match(segment):
                raise ScopeError(f"scope {raw!r} has an unusable segment {segment!r}")
        if kind in FLAT_KINDS and len(segments) > 1:
            raise ScopeError(f"scope {raw!r} has {len(segments)} segments; {kind!r} is flat and takes exactly one")
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
class WorkClaim:
    """A held scope: who holds it, why, and when it expires without a renew."""

    scope: str
    agent_id: str
    task_id: str
    mode: str
    intent: str
    acquired_at: str
    expires_at: str
    #: How many times the holder extended this claim with :func:`renew` (#18391).
    renewals: int = 0
    #: The authenticated writer's company; None = install-wide or legacy (#18391).
    company_id: str | None = None

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
    holder: WorkClaim

    def __str__(self) -> str:
        return (
            f"{self.requested} is held by agent {self.holder.agent_id} "
            f"(task {self.holder.task_id}, {self.holder.mode}) until "
            f"{self.holder.expires_at}: {self.holder.intent}"
        )


def claim_payload(claim: WorkClaim) -> dict[str, Any]:
    """The wire shape of a held scope: one row of ``GET /api/coordination/claims``.

    Every field is already user-facing. Scope paths are repo-relative by
    construction -- `Scope.parse` rejects an empty leading segment, so an
    absolute path cannot become a scope in the first place, and no internal
    filesystem path can reach a payload through here.
    """
    return {
        "scope": claim.scope,
        "kind": claim.parsed_scope.kind,
        "agent_id": claim.agent_id,
        "task_id": claim.task_id,
        "mode": claim.mode,
        "intent": claim.intent,
        "acquired_at": claim.acquired_at,
        "expires_at": claim.expires_at,
        "renewals": claim.renewals,
        "company_id": claim.company_id,
    }


def conflict_payload(conflict: ClaimConflict) -> dict[str, Any]:
    """The one wire shape of a refusal, whichever layer reports it (#16208).

    The holder is a :func:`claim_payload` row, identical to that claim's row in
    the claims table, so a client parses a holder once rather than once per
    layer. ``reason`` is the rendered conflict, for a reader that wants a line.
    """
    return {"requested": conflict.requested, "holder": claim_payload(conflict.holder), "reason": str(conflict)}


class ClaimConflictError(RuntimeError):
    """Raised by :func:`work_claim` when the scope is held by someone else."""

    def __init__(self, conflict: ClaimConflict) -> None:
        super().__init__(str(conflict))
        self.conflict = conflict


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


def _text(raw: bytes | str) -> str:
    return raw.decode() if isinstance(raw, bytes) else raw


def _decode(raw: bytes | str) -> WorkClaim:
    if isinstance(raw, bytes):
        raw = raw.decode()
    return WorkClaim(**json.loads(raw))


def _build(
    scope: Scope, agent_id: str, task_id: str, mode: ClaimMode, intent: str, ttl_s: int, company_id: str | None = None
) -> WorkClaim:
    acquired = now_utc()
    return WorkClaim(
        scope=str(scope),
        agent_id=agent_id,
        task_id=task_id,
        mode=mode.value,
        intent=cap_text(intent),
        acquired_at=acquired.isoformat(),
        expires_at=(acquired + timedelta(seconds=ttl_s)).isoformat(),
        company_id=resolve_company(company_id),
    )


async def _acquire(
    scope: str | Scope,
    *,
    agent_id: str,
    task_id: str,
    mode: ClaimMode,
    intent: str,
    ttl_s: int | None,
    company_id: str | None = None,
) -> tuple[str, WorkClaim | ClaimConflict]:
    """Acquire, returning the verdict alongside the result.

    The verdict separates a fresh ``acquired`` from a ``renewed`` re-acquisition;
    only a fresh acquirer may release, so a nested :func:`work_claim` cannot free
    the scope its outer block still uses.
    """
    parsed = Scope.parse(scope)
    _require_holder(agent_id, task_id)
    ttl = CLAIM_TTL_S if ttl_s is None else ttl_s
    claim = _build(parsed, agent_id, task_id, mode, intent, ttl, company_id)
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
    if len(outcome) > 2 and outcome[2]:  # index members whose TTL ran out unreleased (#18391)
        await record_expired_members(client, parsed.kind, [_text(m) for m in outcome[2]])
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
    company_id: str | None = None,
) -> WorkClaim | ClaimConflict:
    """WorkClaim *scope*, or return the conflict naming who holds it.

    Never raises on contention: the caller decides whether to wait, queue, ask or
    pick other work (#15948). Re-acquiring a scope this ``(agent_id, task_id)``
    already holds is a renew, not a conflict.
    """
    _, result = await _acquire(
        scope, agent_id=agent_id, task_id=task_id, mode=mode, intent=intent, ttl_s=ttl_s, company_id=company_id
    )
    return result


async def release_scope(scope: str | Scope, *, agent_id: str, task_id: str) -> bool:
    """Release this holder's claim on *scope*. True when one went.

    Another holder's claim is unaddressable: nothing is deleted, False returns,
    and the attempt is recorded in the ledger (#18391).
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
    if removed == 0:
        await note_refused_release(client, str(parsed), agent_id, task_id, lambda: list_claims(parsed.kind))
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


async def list_claims(kind: str | None = None) -> list[WorkClaim]:
    """Every live claim; expired entries are pruned from the index (and recorded) as found.

    One ``MGET`` and at most one ``SREM`` per kind: #15949 reads this path far more than it is written.
    """
    client = await _redis()
    kinds = sorted(VALID_KINDS) if kind is None else [kind]
    claims: list[WorkClaim] = []
    for k in kinds:
        _require_kind(k)
        index, prefix = _INDEX_KEY.format(kind=k), _CLAIM_PREFIX.format(kind=k)
        members = [m.decode() if isinstance(m, bytes) else m for m in await client.smembers(index)]
        if not members:
            continue
        payloads = await client.mget([f"{prefix}{m}" for m in members])
        vanished = [m for m, raw in zip(members, payloads) if raw is None]
        if vanished:
            await client.srem(index, *vanished)
            await record_expired_members(client, k, [_text(m) for m in vanished])
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
    company_id: str | None = None,
) -> AsyncIterator[WorkClaim]:
    """Hold *scope* for the block, releasing it however the block exits.

    ``task_id`` defaults to a fresh id so an ad-hoc caller still gets
    reentrancy within its own block rather than sharing an identity with every
    other caller that omitted it.

    Raises:
        ClaimConflictError: the scope is held by someone else; the holder is on
            the exception as ``.conflict``.
    """
    tid = task_id or f"adhoc-{uuid.uuid4()}"
    verdict, outcome = await _acquire(
        scope, agent_id=agent_id, task_id=tid, mode=mode, intent=intent, ttl_s=ttl_s, company_id=company_id
    )
    if isinstance(outcome, ClaimConflict):
        raise ClaimConflictError(outcome)
    try:
        yield outcome
    finally:
        # Only the block that acquired fresh releases: a nested block's renew must
        # not free the scope while the outer block is still writing.
        if verdict == "acquired":
            await release_scope(scope, agent_id=agent_id, task_id=tid)
