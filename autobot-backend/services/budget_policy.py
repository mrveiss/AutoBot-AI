# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Budget policy service — hard-stop auto-pause for runaway agent spend (GH#6470).

Scoped budget policies with warning + hard-stop thresholds.
Scope chain: task -> agent -> project -> tenant — first hard-stop wins.
"""

import asyncio
import uuid
from datetime import timedelta
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import RedisDatabase, get_async_redis_client
from autobot_shared.time_utils import now_utc
from models.heartbeat import AgentRuntimeState, AgentWakeupRequest

logger = get_logger(__name__)

_POLICY_NS = "budget_policy"
_POLICY_IDX_NS = "budget_policy:idx"
_POLICY_TTL = 365 * 24 * 3600

# Matches LLMCostTracker.AGENT_TOTALS_KEY prefix
_AGENT_COST_NS = "llm_cost:by_agent"

_session_factory: Optional[async_sessionmaker] = None


def configure_session_factory(factory: async_sessionmaker) -> None:
    """Inject DB session factory for pause/resume operations (GH#6470)."""
    global _session_factory
    _session_factory = factory


# ---------------------------------------------------------------------------
# Literal scope / period / action constants (not Enum to avoid pydantic issues)
# ---------------------------------------------------------------------------

SCOPE_AGENT = "agent"
SCOPE_PROJECT = "project"
SCOPE_TENANT = "tenant"
SCOPE_TASK = "task"

PERIOD_HOUR = "hour"
PERIOD_DAY = "day"
PERIOD_MONTH = "month"

ACTION_ALERT = "alert"
ACTION_PAUSE = "pause"
ACTION_ALERT_THEN_PAUSE = "alert_then_pause"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class BudgetPolicy(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scope: str
    scope_id: str
    period: str
    threshold_usd: float
    warning_pct: float = 0.8
    action: str = ACTION_ALERT_THEN_PAUSE
    enabled: bool = True
    name: str = ""
    description: str = ""
    created_at: str = Field(default_factory=lambda: now_utc().isoformat())
    updated_at: str = Field(default_factory=lambda: now_utc().isoformat())


class PolicyEvalResult(BaseModel):
    policy: BudgetPolicy
    current_spend_usd: float
    pct_used: float
    is_hard_stop: bool
    is_warning: bool


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------


async def _get_redis():
    return await get_async_redis_client(RedisDatabase.ANALYTICS)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_policy(policy: BudgetPolicy) -> BudgetPolicy:
    r = await _get_redis()
    key = f"{_POLICY_NS}:{policy.id}"
    idx_key = f"{_POLICY_IDX_NS}:{policy.scope}:{policy.scope_id}"
    await r.set(key, policy.model_dump_json(), ex=_POLICY_TTL)
    await r.sadd(idx_key, policy.id)
    await r.expire(idx_key, _POLICY_TTL)
    return policy


async def get_policy(policy_id: str) -> Optional[BudgetPolicy]:
    r = await _get_redis()
    data = await r.get(f"{_POLICY_NS}:{policy_id}")
    if data is None:
        return None
    return BudgetPolicy.model_validate_json(data)


async def list_policies_for_scope(scope: str, scope_id: str) -> List[BudgetPolicy]:
    r = await _get_redis()
    idx_key = f"{_POLICY_IDX_NS}:{scope}:{scope_id}"
    raw_ids = await r.smembers(idx_key)
    results: List[BudgetPolicy] = []
    for raw_id in raw_ids:
        pid = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
        p = await get_policy(pid)
        if p and p.enabled:
            results.append(p)
    return results


async def list_all_policies() -> List[BudgetPolicy]:
    r = await _get_redis()
    results: List[BudgetPolicy] = []
    async for raw_key in r.scan_iter(f"{_POLICY_NS}:*"):
        key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
        # Skip index keys
        if not key.startswith(f"{_POLICY_NS}:") or key.startswith(f"{_POLICY_IDX_NS}"):
            continue
        pid = key[len(f"{_POLICY_NS}:") :]
        # Index entries have extra colons — skip them
        if ":" in pid:
            continue
        data = await r.get(key)
        if data:
            results.append(BudgetPolicy.model_validate_json(data))
    return results


async def patch_policy(policy_id: str, updates: dict) -> Optional[BudgetPolicy]:
    policy = await get_policy(policy_id)
    if policy is None:
        return None
    updated = policy.model_copy(update={**updates, "updated_at": now_utc().isoformat()})
    r = await _get_redis()
    await r.set(f"{_POLICY_NS}:{policy_id}", updated.model_dump_json(), ex=_POLICY_TTL)
    return updated


async def delete_policy(policy_id: str) -> bool:
    policy = await get_policy(policy_id)
    if policy is None:
        return False
    r = await _get_redis()
    await r.delete(f"{_POLICY_NS}:{policy_id}")
    idx_key = f"{_POLICY_IDX_NS}:{policy.scope}:{policy.scope_id}"
    await r.srem(idx_key, policy_id)
    return True


# ---------------------------------------------------------------------------
# Spend lookup
# ---------------------------------------------------------------------------


async def get_period_spend(agent_id: str, period: str) -> float:
    """
    Read accumulated agent spend for the given period from cost tracker Redis keys.

    DAY/HOUR -> llm_cost:by_agent:{agent_id}:daily:{YYYY-MM-DD}
    MONTH    -> sum of daily keys for current calendar month
    """
    r = await _get_redis()
    today = now_utc()

    if period in (PERIOD_DAY, PERIOD_HOUR):
        date_str = today.strftime("%Y-%m-%d")
        val = await r.get(f"{_AGENT_COST_NS}:{agent_id}:daily:{date_str}")
        return float(val) if val else 0.0

    if period == PERIOD_MONTH:
        first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        keys: List[str] = []
        cursor = first_day
        while cursor <= today:
            keys.append(f"{_AGENT_COST_NS}:{agent_id}:daily:{cursor.strftime('%Y-%m-%d')}")
            cursor += timedelta(days=1)
        if not keys:
            return 0.0
        pipe = r.pipeline()
        for k in keys:
            pipe.get(k)
        vals = await pipe.execute()
        return sum(float(v) for v in vals if v)

    return 0.0


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


async def evaluate_policies(
    agent_id: str,
    project_id: Optional[str],
    tenant_id: str,
    task_id: Optional[str] = None,
) -> Optional[PolicyEvalResult]:
    """
    Evaluate matching policies in scope-chain order.

    Returns first hard-stop result that warrants an action,
    or the most severe warning if no hard-stop.
    """
    scope_chain: List[Tuple[str, str]] = []
    if task_id:
        scope_chain.append((SCOPE_TASK, task_id))
    scope_chain.append((SCOPE_AGENT, agent_id))
    if project_id:
        scope_chain.append((SCOPE_PROJECT, project_id))
    scope_chain.append((SCOPE_TENANT, tenant_id))

    best_warning: Optional[PolicyEvalResult] = None

    for scope, scope_id in scope_chain:
        policies = await list_policies_for_scope(scope, scope_id)
        for policy in policies:
            spend = await get_period_spend(agent_id, policy.period)
            if spend <= 0:
                continue

            pct = spend / policy.threshold_usd if policy.threshold_usd > 0 else 0.0
            is_hard_stop = pct >= 1.0
            is_warning = (pct >= policy.warning_pct) and not is_hard_stop

            if not (is_hard_stop or is_warning):
                continue

            res = PolicyEvalResult(
                policy=policy,
                current_spend_usd=spend,
                pct_used=pct,
                is_hard_stop=is_hard_stop,
                is_warning=is_warning,
            )

            if is_hard_stop and policy.action in (ACTION_PAUSE, ACTION_ALERT_THEN_PAUSE):
                return res

            if best_warning is None or res.pct_used > best_warning.pct_used:
                best_warning = res

    return best_warning


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------


async def apply_action(result: PolicyEvalResult, agent_id: str) -> None:
    """Emit audit event and pause agent if the policy demands it."""
    await _emit_breach_audit(result, agent_id)

    if result.is_hard_stop and result.policy.action in (ACTION_PAUSE, ACTION_ALERT_THEN_PAUSE):
        reason = (
            f"Budget hard-stop: {result.policy.name or result.policy.id} "
            f"(${result.current_spend_usd:.4f} / ${result.policy.threshold_usd:.2f} "
            f"for {result.policy.period} {result.policy.scope} scope)"
        )
        await pause_agent(agent_id, reason=reason, paused_by=f"budget_policy:{result.policy.id}")
    elif result.is_warning:
        logger.warning(
            "Budget warning: agent=%s %.1f%% of %s %s cap ($%.4f / $%.2f)",
            agent_id,
            result.pct_used * 100,
            result.policy.period,
            result.policy.scope,
            result.current_spend_usd,
            result.policy.threshold_usd,
        )


async def _emit_breach_audit(result: PolicyEvalResult, agent_id: str) -> None:
    try:
        from services.audit.unified_audit import AuditCategory, AuditEvent
        from services.audit.unified_audit import record as record_unified_event

        event = AuditEvent(
            category=AuditCategory.GOVERNANCE,
            action="budget.threshold_breach",
            actor_id="budget_policy_service",
            resource_type="agent",
            resource_id=agent_id,
            metadata={
                "policy_id": result.policy.id,
                "policy_name": result.policy.name,
                "scope": result.policy.scope,
                "scope_id": result.policy.scope_id,
                "period": result.policy.period,
                "current_spend_usd": result.current_spend_usd,
                "threshold_usd": result.policy.threshold_usd,
                "pct_used": round(result.pct_used * 100, 2),
                "is_hard_stop": result.is_hard_stop,
            },
        )
        await record_unified_event(event)
    except Exception:
        logger.exception("Failed to emit budget breach audit for agent=%s", agent_id)


# ---------------------------------------------------------------------------
# Pause / resume
# ---------------------------------------------------------------------------


async def pause_agent(agent_id: str, reason: str, paused_by: str = "budget_policy") -> None:
    """
    Pause an agent: set AgentRuntimeState.status='paused', drain wakeup queue,
    and emit governance audit event (GH#6470).
    """
    if _session_factory is None:
        logger.error("pause_agent called before configure_session_factory; cannot pause agent=%s", agent_id)
        return

    try:
        async with _session_factory() as session:
            state_result = await session.execute(
                select(AgentRuntimeState).where(AgentRuntimeState.agent_id == agent_id)
            )
            state = state_result.scalar_one_or_none()

            if state is None:
                state = AgentRuntimeState(
                    id=uuid.uuid4(),
                    agent_id=agent_id,
                    status="paused",
                    paused_reason=reason,
                    paused_at=now_utc(),
                    paused_by=paused_by,
                )
                session.add(state)
            else:
                state.status = "paused"
                state.paused_reason = reason
                state.paused_at = now_utc()
                state.paused_by = paused_by

            # Drain un-consumed wakeup requests so the agent doesn't wake immediately
            await session.execute(
                delete(AgentWakeupRequest).where(
                    AgentWakeupRequest.agent_id == agent_id,
                    AgentWakeupRequest.consumed_at.is_(None),
                )
            )
            await session.commit()

        logger.warning("Agent %s PAUSED — %s", agent_id, reason)

        try:
            from services.audit.unified_audit import AuditCategory, AuditEvent
            from services.audit.unified_audit import record as record_unified_event

            await record_unified_event(
                AuditEvent(
                    category=AuditCategory.GOVERNANCE,
                    action="agent.budget_paused",
                    actor_id=paused_by,
                    resource_type="agent",
                    resource_id=agent_id,
                    metadata={"reason": reason, "paused_by": paused_by},
                )
            )
        except Exception:
            logger.exception("Failed to emit agent.budget_paused audit for agent=%s", agent_id)

    except Exception:
        logger.exception("pause_agent failed for agent=%s", agent_id)


async def resume_agent(agent_id: str, approved_by: str) -> bool:
    """
    Resume a budget-paused agent.

    Callers must verify human authorization before calling.
    Returns True if the agent was paused and is now active.
    """
    if _session_factory is None:
        logger.error("resume_agent called before configure_session_factory; cannot resume agent=%s", agent_id)
        return False

    try:
        async with _session_factory() as session:
            state_result = await session.execute(
                select(AgentRuntimeState).where(AgentRuntimeState.agent_id == agent_id)
            )
            state = state_result.scalar_one_or_none()
            if state is None or state.status != "paused":
                return False

            state.status = "active"
            state.paused_reason = None
            state.paused_at = None
            state.paused_by = None
            await session.commit()

        logger.info("Agent %s RESUMED by %s", agent_id, approved_by)

        try:
            from services.audit.unified_audit import AuditCategory, AuditEvent
            from services.audit.unified_audit import record as record_unified_event

            await record_unified_event(
                AuditEvent(
                    category=AuditCategory.GOVERNANCE,
                    action="agent.budget_resumed",
                    actor_id=approved_by,
                    resource_type="agent",
                    resource_id=agent_id,
                    metadata={"approved_by": approved_by},
                )
            )
        except Exception:
            logger.exception("Failed to emit agent.budget_resumed audit for agent=%s", agent_id)

        return True

    except Exception:
        logger.exception("resume_agent failed for agent=%s", agent_id)
        return False


# ---------------------------------------------------------------------------
# Fire-and-forget hook for LLMCostTracker
# ---------------------------------------------------------------------------


def trigger_budget_evaluation(
    agent_id: str,
    project_id: Optional[str] = None,
    tenant_id: str = "default",
) -> None:
    """
    Schedule budget evaluation as a background asyncio task after each cost event.

    Non-blocking — never raises. Called from LLMCostTracker._build_and_persist_record.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run():
        try:
            result = await evaluate_policies(agent_id, project_id, tenant_id)
            if result is not None:
                await apply_action(result, agent_id)
        except Exception:
            logger.exception("Budget evaluation failed for agent=%s", agent_id)

    loop.create_task(_run(), name=f"budget-eval-{agent_id}")


# ---------------------------------------------------------------------------
# Default policy seeding
# ---------------------------------------------------------------------------


async def seed_default_policies(tenant_id: str = "default") -> None:
    """
    Create default policies if none exist for the tenant (GH#6470).

    - Per-tenant monthly $500 hard-stop (alert_then_pause)
    """
    existing = await list_policies_for_scope(SCOPE_TENANT, tenant_id)
    monthly_exists = any(p.period == PERIOD_MONTH for p in existing)
    if not monthly_exists:
        await create_policy(
            BudgetPolicy(
                scope=SCOPE_TENANT,
                scope_id=tenant_id,
                period=PERIOD_MONTH,
                threshold_usd=500.0,
                warning_pct=0.8,
                action=ACTION_ALERT_THEN_PAUSE,
                name="Default tenant monthly $500 hard-stop",
                description="Auto-seeded default. Adjust threshold in budget policies admin.",
            )
        )
        logger.info("Seeded default tenant monthly $500 budget policy for tenant=%s", tenant_id)
