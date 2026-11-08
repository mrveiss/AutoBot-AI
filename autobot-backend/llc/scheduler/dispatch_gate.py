# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one gate every Company OS agent run passes before it starts (#19240).

Heartbeat, manual and event wakes, routines and the liveness monitor all ask here.
The answer is a reason string, or ``None`` when the agent may run. Budget is read
before the run because cost is only ingested after it: without the pre-run check,
an exhausted agent keeps spending until the watchdog next sweeps.

Agents have two id keyspaces (see ``models/reporting_line.py``). Pause flags and
budgets are keyed by the slug, routines hold the node's UUID, so a reference is
resolved to its node before either is read.
"""

import uuid
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from models.agent_org import AgentOrgNode

from ..adapters import get_adapter
from ..adapters.subprocess_base import is_subprocess_adapter
from ..models.activity import ActorType
from ..models.enums import UNDISPATCHABLE_AGENT_STATUSES, ActivityEventType, LLCAgentStatus
from ..org_role_authority import describe_role_bound, role_bound_refusal
from ..services.accessors import get_budget_service
from ..services.activity_log import LLCActivityLogService
from ..services.actor import audit

logger = get_logger(__name__)

#: The reason text a caller may need to tell apart: replay answers it with a 402.
BUDGET_EXHAUSTED = "budget is exhausted"
BUDGET_REFUSAL_DEDUP_TTL_SECONDS = max(1, env_int("AUTOBOT_LLC_BUDGET_REFUSAL_DEDUP_TTL_SECONDS", 86400))
_activity_log = LLCActivityLogService()

#: What the board did on purpose. ``inactive`` is left out: the budget watchdog
#: writes it, and a dead run of an over-budget agent must still release its claims.
_DELIBERATE_STOP_STATUSES = frozenset({LLCAgentStatus.PAUSED.value, LLCAgentStatus.TERMINATED.value})


class AgentNotDispatchable(ValueError):
    """A run was requested for an agent the gate refuses."""

    def __init__(self, agent_id: str, company_id: Any, reason: str) -> None:
        super().__init__(f"Agent {agent_id} cannot run: {reason}")
        self.company_id = company_id
        self.reason = reason


def as_uuid(value: Any) -> Optional[uuid.UUID]:
    """*value* as a UUID, or ``None`` when it is not one (a slug, say)."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def resolve_agent(session: AsyncSession, company_id: Any, agent_ref: Any) -> Any:
    """The ``(agent_id, status)`` row for a slug or node PK within *company_id*, or ``None``.

    A reference matching two agents (one's slug is another's PK) names neither.
    """
    match = AgentOrgNode.agent_id == str(agent_ref)
    node_pk = as_uuid(agent_ref)
    if node_pk is not None:
        match = or_(match, AgentOrgNode.id == node_pk)
    result = await session.execute(
        select(AgentOrgNode.agent_id, AgentOrgNode.status).where(AgentOrgNode.company_id == company_id, match).limit(2)
    )
    rows = result.all()
    if len(rows) > 1:
        logger.warning("Agent reference %s in company %s matches two agents", agent_ref, company_id)
    return rows[0] if len(rows) == 1 else None


def agent_pause_flag_key(slug: Any) -> str:
    """The Redis flag that pauses one agent."""
    return f"llc:agent:{slug}:paused"


def company_pause_flag_key(company_id: Any) -> str:
    """The Redis flag that pauses a whole company."""
    return f"llc:company:{company_id}:paused"


def adapter_block_reason(adapter_type: Optional[str], adapter_config: Optional[dict]) -> Optional[str]:
    """Why an agent's adapter cannot start a run, or ``None`` (#20519, #20507).

    The one answer for "can this agent run" that needs no I/O beyond the local CLI
    lookup: the dispatcher refuses with it, and the agent lists show it. Both would
    otherwise drift, and a list that says "ready" for an agent whose run is skipped
    is the failure #20507 reported.
    """
    kind = adapter_type or "autobot_agent"
    if kind == "autobot_agent":
        if not (adapter_config or {}).get("agent_class"):
            return "no adapter_config.agent_class configured"
        return None
    try:
        adapter = get_adapter(kind)
    except KeyError:
        return f"no LLC adapter registered for type {kind!r}"
    if is_subprocess_adapter(adapter) and not adapter.is_cli_available():  # type: ignore[union-attr]
        return adapter.cli_not_found_message()  # type: ignore[union-attr]
    return None


def run_block_reason(
    status: Optional[str], adapter_type: Optional[str], adapter_config: Optional[dict], *, org_role: Optional[str]
) -> Optional[str]:
    """The reason an agent cannot run from its own row alone (status, adapter, role bound), or ``None``.

    Pause flags and budget live in Redis and the budget tables; they are enforced at
    dispatch by :func:`dispatch_block_reason` and not read per row for a list. The
    role bound refuses only while it is enforced (#20706).
    """
    if status in UNDISPATCHABLE_AGENT_STATUSES:
        return f"agent status is {status}"
    # Same order as dispatch: a role-bound refusal is the reason it will not run, even when the
    # adapter is also unavailable -- fixing the adapter alone would not make it runnable.
    return role_bound_refusal(describe_role_bound(org_role, adapter_type)) or adapter_block_reason(
        adapter_type, adapter_config
    )


async def _pause_flag_reason(slug: Optional[str], company_id: Optional[Any]) -> Optional[str]:
    """The controls keys. A company pause is written only here, so an unread flag is not "not paused"."""
    redis = await get_async_redis_client()
    if redis is None:
        return "pause state is unreadable" if company_id else None
    if company_id and await redis.exists(company_pause_flag_key(company_id)):
        return "company is paused"
    if slug and await redis.exists(agent_pause_flag_key(slug)):
        return "agent is paused"
    return None


async def dispatch_block_reason(
    session: AsyncSession,
    agent_id: str,
    company_id: Any,
    status: Optional[str],
    *,
    deliberate_only: bool = False,
) -> Optional[str]:
    """Why this resolved agent must not run, or ``None``.

    ``deliberate_only`` is the liveness monitor's question: was this one agent stopped
    on purpose? A budget stop and a company pause are not that. A company pause writes
    only its Redis key and leaves dead runs holding their claims unless they are recovered.
    An exception, from Redis or the budget read, propagates: unknown is not "may run".
    """
    blocked = _DELIBERATE_STOP_STATUSES if deliberate_only else UNDISPATCHABLE_AGENT_STATUSES
    if status in blocked:
        return f"agent status is {status}"
    reason = await _pause_flag_reason(agent_id, None if deliberate_only else company_id)
    if reason is None and not deliberate_only and not company_id:
        return "agent has no company, so its budget cannot be read"
    if reason is None and not deliberate_only:
        _, over_limit, _ = await get_budget_service().check_budget(session, agent_id, str(company_id))
        reason = BUDGET_EXHAUSTED if over_limit else None
    return reason


async def agent_ref_block_reason(
    session: AsyncSession,
    agent_ref: Any,
    company_id: Any,
    *,
    deliberate_only: bool = False,
) -> Optional[str]:
    """:func:`dispatch_block_reason` for a caller holding a slug, a node PK, or no agent at all."""
    company_uuid = as_uuid(company_id)
    row = await resolve_agent(session, company_uuid, agent_ref) if agent_ref and company_uuid else None
    if row is None and agent_ref and not deliberate_only:
        return "assigned agent was not found in this company"
    if row is None:  # no agent to judge: only the flags remain
        slug = str(agent_ref) if agent_ref else None
        return await _pause_flag_reason(slug, None if deliberate_only else company_id)
    return await dispatch_block_reason(session, row[0], company_id, row[1], deliberate_only=deliberate_only)


async def require_dispatchable(session: AsyncSession, agent: dict) -> None:
    """Raise :class:`AgentNotDispatchable` when *agent*'s config row may not run."""
    company_id = agent.get("company_id")
    try:
        reason = await dispatch_block_reason(session, agent["agent_id"], company_id, agent.get("status"))
    except SQLAlchemyError:  # the caller's transaction is gone: pretending otherwise loses its write silently
        raise
    except Exception:
        logger.exception("Dispatch state of agent %s could not be read", agent["agent_id"])
        reason = "dispatch state could not be read"
    if reason is not None:
        raise AgentNotDispatchable(agent["agent_id"], company_id, reason)


# --- #21212: a budget refusal is visible to the company, once per exhaustion episode ---
# Which refusals are recorded, and the de-duplication, are documented on :func:`note_refused_wake`.


def budget_refusal_key(company_id: Any, node_id: Any, remaining: Any) -> str:
    """The Redis key marking one exhaustion episode of one agent.

    The budget's remaining amount is part of the key, so a changed amount (the limit was raised and spent
    again) is a new episode and a new key, while one atomic ``SET NX`` decides the single winner of each.
    """
    return f"llc:budget_refusal:{company_id}:{node_id}:{remaining}"


async def _already_recorded(key: str) -> bool:
    """True when this episode's refusal is on record; otherwise mark it recorded, atomically (one winner).

    Fails OPEN: a dedup store that is down or errors means "not recorded yet", so the record is still
    written, only without de-duplication. Losing the record is worse than a duplicate.
    """
    try:
        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("Redis unavailable: budget refusal written without de-duplication")
            return False
        return not await redis.set(key, "1", nx=True, ex=BUDGET_REFUSAL_DEDUP_TTL_SECONDS)
    except Exception:
        logger.exception("Budget refusal de-duplication failed: writing the record without it")
        return False


async def _resolve_node(session: Any, company_id: Any, agent_ref: Any) -> Any:
    """The ``(node PK, slug)`` of *agent_ref* (a slug or a node PK) in the company, or ``None``."""
    company, node_pk = as_uuid(company_id), as_uuid(agent_ref)
    match = AgentOrgNode.agent_id == str(agent_ref)
    if node_pk is not None:
        match = match | (AgentOrgNode.id == node_pk)
    rows = (
        await session.execute(
            select(AgentOrgNode.id, AgentOrgNode.agent_id).where(AgentOrgNode.company_id == company, match).limit(2)
        )
    ).all()
    return rows[0] if len(rows) == 1 else None


async def _write_refusal(session: Any, company_id: Any, node_id: Any, slug: str, remaining: Any) -> None:
    """Append the ``budget.dispatch_refused`` row and commit it, which publishes the live event."""
    await audit(
        _activity_log,
        session,
        company_id=str(company_id),
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        event_type=ActivityEventType.BUDGET_DISPATCH_REFUSED,
        entity_type="agent",
        entity_id=str(node_id),
        after={"remaining": str(remaining)},
        metadata={"agent_id": slug, "reason": BUDGET_EXHAUSTED},
    )
    await session.commit()


async def record_budget_refusal(session: Any, company_id: Any, agent_ref: Any, reason: Optional[str]) -> bool:
    """Write the company-scoped ``budget.dispatch_refused`` row once per episode; True when written.

    Never raises: a failed record must not stop the wake being rescheduled. The failure is logged
    with its traceback, the session is rolled back and the dedup mark dropped, so the next wake tries again.
    """
    if reason != BUDGET_EXHAUSTED or not agent_ref or as_uuid(company_id) is None:
        return False
    key = None
    try:
        node = await _resolve_node(session, company_id, agent_ref)
        if node is None:
            return False
        node_id, slug = node[0], str(node[1])
        remaining, _, _ = await get_budget_service().check_budget(session, slug, str(company_id))
        key = budget_refusal_key(company_id, node_id, remaining)
        if await _already_recorded(key):
            return False
        await _write_refusal(session, company_id, node_id, slug, remaining)
        return True
    except Exception:
        logger.exception("Could not record the budget refusal of agent %s", agent_ref)
        await _abandon(session, key)
        return False


async def _abandon(session: Any, key: Optional[str]) -> None:
    """After a failed record: roll the session back and drop the dedup mark so the next wake records it."""
    try:
        await session.rollback()
    except Exception:
        logger.exception("Could not roll back the session after a failed budget refusal record")
    if key is None:
        return
    try:
        redis = await get_async_redis_client()
        if redis is not None:
            await redis.delete(key)
    except Exception:
        logger.exception("Could not clear the budget refusal mark %s", key)


async def note_refused_wake(session: AsyncSession, company_id: Any, agent_ref: Any, reason: str) -> None:
    """Log a skipped heartbeat wake and, for an exhausted budget, leave the visible record (#21212).

    Recorded: ``budget is exhausted`` (``budget.dispatch_refused``): only a user can fix it, by raising the limit.

    Log-only, each with its reason:

    * ``agent status is ...``, ``agent is paused``, ``company is paused``: the board did it on purpose and
      the ``control.*`` rows already record it.
    * ``pause state is unreadable``, ``dispatch state could not be read``: transient faults that clear
      themselves and have no company-visible cause.
    * ``agent has no company ...``: there is no company to scope a record to.
    * ``assigned agent was not found ...``: a routine's own configuration fault, not the refusal of a known agent.

    De-duplication is one record per exhaustion episode, not per wake. A short Redis key per agent and
    remaining amount, set with one atomic ``SET NX EX``, marks the episode. A later refusal is written
    only when the amount differs (the limit was raised and spent again, so a new key) or the key
    expired (``AUTOBOT_LLC_BUDGET_REFUSAL_DEDUP_TTL_SECONDS``, default one day, so a long episode is
    restated daily). No schema change, and a budget that stays exhausted writes nothing further.
    """
    logger.info("Heartbeat skipped for agent %s: %s", agent_ref, reason)
    await record_budget_refusal(session, company_id, agent_ref, reason)
