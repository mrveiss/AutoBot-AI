# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC per-agent budget service (GH#8215).

Provides cost ingest with atomic DB update, hard-stop via BudgetExhausted,
and soft alert via Redis publish on threshold crossing.

GH#6630: integrates AgentBudgetTracker (SharedRuntimeBag-backed) so all
uvicorn workers share live budget state without extra DB round-trips.
"""

import json
import logging
from decimal import Decimal
from typing import Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_constants import MODEL_PRICING_PER_1M_TOKENS
from llc.exceptions import BudgetExhausted
from llc.models.budget import LLCAgentBudget

from .agent_budget_tracker import AgentBudgetState, AgentBudgetTracker
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_tracker = AgentBudgetTracker()  # noqa: SRB001 — canonical SharedRuntimeBag consumer


class BudgetService(LLCServiceBase):
    """Per-agent budget enforcement: cost ingest, hard stop, soft alert."""

    async def ingest_cost_event(
        self,
        session: AsyncSession,
        agent_id: str,
        tokens_in: int,
        tokens_out: int,
        model: str,
    ) -> Decimal:
        """Record token cost for an agent and enforce budget limits.

        Uses an atomic UPDATE (budget_spent = budget_spent + cost) to avoid
        read-modify-write races across 4 uvicorn workers sharing one DB.

        Returns the cost added this call.
        Raises BudgetExhausted if spending exceeds budget_limit.
        """
        pricing = MODEL_PRICING_PER_1M_TOKENS.get(model)
        if pricing is None:
            logger.warning(
                "Unknown model %r in ingest_cost_event for agent %s — treating cost as 0",
                model,
                agent_id,
            )
            cost = Decimal("0")
        else:
            cost = Decimal(str((tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000))

        # Atomic increment — prevents lost-update across concurrent workers
        await session.execute(
            text("UPDATE llc_agent_budgets" " SET budget_spent = budget_spent + :cost" " WHERE agent_id = :agent_id"),
            {"cost": str(cost), "agent_id": agent_id},
        )

        result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
        row = result.scalar_one_or_none()

        if row is None:
            logger.warning(
                "No budget row for agent %s after ingest — skipping enforcement",
                agent_id,
            )
            return cost

        spent = Decimal(str(row.budget_spent))
        limit = Decimal(str(row.budget_limit))
        threshold = Decimal(str(row.alert_threshold))

        # Push updated state into cross-worker cache (GH#6630).
        await _tracker.record_state(
            AgentBudgetState(
                agent_id=agent_id,
                budget_spent=float(spent),
                budget_limit=float(limit),
                alert_threshold=float(threshold),
            )
        )

        if spent > limit:
            raise BudgetExhausted(agent_id=agent_id, spent=float(spent), limit=float(limit))

        if limit > Decimal("0") and spent / limit >= threshold:
            await self._emit_alert(agent_id, float(spent), float(limit))

        return cost

    async def check_budget(self, session: AsyncSession, agent_id: str) -> Tuple[Decimal, bool, bool]:
        """Return (remaining, is_over_limit, alert_triggered) for an agent.

        remaining can be negative when spent exceeds limit.

        Reads from SharedRuntimeBag cache first (GH#6630); falls back to DB
        on cache miss so correctness is preserved.
        """
        cached = await _tracker.get_state(agent_id)
        if cached is not None:
            return cached.remaining, cached.is_over_limit, cached.alert_triggered

        result = await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
        row = result.scalar_one_or_none()

        if row is None:
            return Decimal("0"), False, False

        spent = Decimal(str(row.budget_spent))
        limit = Decimal(str(row.budget_limit))
        threshold = Decimal(str(row.alert_threshold))

        remaining = limit - spent
        is_over_limit = spent > limit
        alert_triggered = limit > Decimal("0") and spent / limit >= threshold

        return remaining, is_over_limit, alert_triggered

    async def _emit_alert(self, agent_id: str, spent: float, limit: float) -> None:
        """Publish llc:budget_alert to Redis.

        Swallows all exceptions — Redis failure must NOT roll back the budget
        ingest transaction.
        """
        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("Redis unavailable — skipping llc:budget_alert for %s", agent_id)
            return
        try:
            await redis.publish(
                "llc:budget_alert",
                json.dumps(
                    {
                        "agent_id": agent_id,
                        "spent": spent,
                        "limit": limit,
                    }
                ),
            )
        except Exception:
            logger.exception("Failed to emit llc:budget_alert for %s", agent_id)
