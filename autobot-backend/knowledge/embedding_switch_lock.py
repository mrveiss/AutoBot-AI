# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one-build-at-a-time claim of the embedding switch, held in the work-claim registry (#19379).

The switch is a claim on the whole knowledge base: one exclusive ``kb`` scope whose TTL is the
build's heartbeat. It goes through ``autobot_shared.coordination.work_claims`` (#16653), the one
claim registry, rather than a lock of its own, so the holder is visible to everything that reads
claims and a refusal names who is rebuilding.
"""

from __future__ import annotations

from autobot_shared.coordination import work_claims

#: One exclusive claim: no other switch may run while this one is held.
SWITCH_SCOPE = "kb:embedding-switch"
#: The holder's task identity; the per-process ``owner`` is the agent id, so two builds never compare equal.
SWITCH_TASK_ID = "embedding-switch"
_INTENT = "rebuild the knowledge base into a new embedding space"


async def acquire(owner: str, ttl_s: int) -> bool:
    """Claim the switch for *owner*; False when another build holds it."""
    result = await work_claims.try_acquire(
        SWITCH_SCOPE, agent_id=owner, task_id=SWITCH_TASK_ID, intent=_INTENT, ttl_s=ttl_s
    )
    return isinstance(result, work_claims.WorkClaim)


async def extend_claim(owner: str, ttl_s: int) -> bool:
    """Extend *owner*'s claim; False once it expired or another owner holds it."""
    return await work_claims.renew(SWITCH_SCOPE, agent_id=owner, task_id=SWITCH_TASK_ID, ttl_s=ttl_s)


async def release(owner: str) -> bool:
    """Release *owner*'s claim; another owner's is untouched."""
    return await work_claims.release_scope(SWITCH_SCOPE, agent_id=owner, task_id=SWITCH_TASK_ID)


async def holder() -> str | None:
    """The agent id holding the switch claim, or None when nobody does (a dead build's claim expired)."""
    for claim in await work_claims.list_claims("kb"):
        if claim.scope == SWITCH_SCOPE:
            return claim.agent_id
    return None


async def force_release() -> None:
    """Release whoever holds the claim: the force-close of a build whose worker is gone."""
    current = await holder()
    if current is not None:
        await release(current)
