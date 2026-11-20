# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Blocking face of the work-claims registry, for code that runs in a worker thread (#20992).

``work_claims`` is async; a Chroma write made through the synchronous client runs in an
``asyncio.to_thread`` worker with no event loop of its own. This module is the same registry --
the same Lua, the same keys, the same SHARED/EXCLUSIVE rule -- reached through the synchronous Redis
client, so a claim taken here conflicts with one taken from the async side. It is not a second registry.

One difference: an index member pruned because its TTL ran out is not written to the ledger from here
(that recorder is async); the registry itself still prunes it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from autobot_shared.coordination.claim_company import resolve_company
from autobot_shared.coordination.ledger_events import cap_text
from autobot_shared.coordination.work_claims import (
    CLAIM_PREFIX,
    CLAIM_TTL_S,
    INDEX_KEY,
    ClaimConflict,
    ClaimMode,
    ClaimUnavailable,
    Scope,
    WorkClaim,
    acquire_eval_args,
    build_claim,
    decode_claim,
    require_holder,
)
from autobot_shared.coordination.work_claims_lua import _ACQUIRE_LUA, _RELEASE_LUA, _RENEW_LUA
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc


def _redis() -> Any:
    client = get_redis_client(async_client=False, database="main")
    if client is None:
        raise ClaimUnavailable("work_claims: Redis client unavailable; no claim can be made or trusted")
    return client


def try_acquire_sync(
    scope: str | Scope, *, agent_id: str, task_id: str, mode: ClaimMode, intent: str, ttl_s: int | None = None
) -> WorkClaim | ClaimConflict:
    """Blocking :func:`work_claims.try_acquire`: the claim, or the conflict naming its holder."""
    parsed = Scope.parse(scope)
    require_holder(agent_id, task_id)
    ttl = CLAIM_TTL_S if ttl_s is None else ttl_s
    claim = build_claim(parsed, agent_id, task_id, mode, cap_text(intent), ttl, resolve_company(None))
    outcome = _redis().eval(_ACQUIRE_LUA, 1, *acquire_eval_args(parsed, claim, mode, ttl))
    verdict = outcome[0].decode() if isinstance(outcome[0], bytes) else outcome[0]
    if verdict == "conflict":
        return ClaimConflict(requested=str(parsed), holder=decode_claim(outcome[1]))
    return claim


def release_sync(scope: str | Scope, *, agent_id: str, task_id: str) -> bool:
    """Blocking :func:`work_claims.release_scope`; True when this holder's claim went."""
    parsed = Scope.parse(scope)
    require_holder(agent_id, task_id)
    removed = _redis().eval(
        _RELEASE_LUA, 1, INDEX_KEY.format(kind=parsed.kind), CLAIM_PREFIX.format(kind=parsed.kind), parsed.path,
        agent_id, task_id,
    )  # fmt: skip
    return int(removed) == 1


def renew_sync(scope: str | Scope, *, agent_id: str, task_id: str, ttl_s: int | None = None) -> bool:
    """Blocking :func:`work_claims.renew`; False once the claim is gone (expired or released)."""
    parsed = Scope.parse(scope)
    require_holder(agent_id, task_id)
    ttl = CLAIM_TTL_S if ttl_s is None else ttl_s
    expires = (now_utc() + timedelta(seconds=ttl)).isoformat()
    result = _redis().eval(
        _RENEW_LUA, 0, CLAIM_PREFIX.format(kind=parsed.kind), str(ttl), expires, parsed.path, agent_id, task_id
    )
    return int(result) == 1
