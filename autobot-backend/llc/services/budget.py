# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC per-agent budget service (GH#8215).

Provides cost ingest with atomic DB update, hard-stop via BudgetExhausted,
and soft alert via Redis publish on threshold crossing.

GH#6630: integrates AgentBudgetTracker (SharedRuntimeBag-backed) so all
uvicorn workers share live budget state without extra DB round-trips.
"""

import json
import logging
import uuid
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_constants import MODEL_PRICING_PER_1M_TOKENS
from llc.config import DEFAULT_BUDGET_LIMIT
from llc.exceptions import BudgetExhausted
from llc.models.budget import LLCAgentBudget

from .agent_budget_tracker import AgentBudgetState, AgentBudgetTracker
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_tracker = AgentBudgetTracker()  # noqa: SRB001 — canonical SharedRuntimeBag consumer


class BudgetService(LLCServiceBase):
    """Per-agent budget enforcement: cost ingest, hard stop, soft alert."""

    async def provision_budget(
        self,
        session: AsyncSession,
        agent_id: str,
        company_id: str,
        budget_limit: Optional[Decimal] = None,
    ) -> Tuple[LLCAgentBudget, bool]:
        """Create a default LLCAgentBudget row for an agent if one does not exist (GH#9901).

        Idempotent: if a row already exists, returns it with ``created=False``.
        Returns ``(row, created)`` where ``created`` is True only for new rows.
        """
        existing = (
            await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.agent_id == agent_id))
        ).scalar_one_or_none()
        if existing is not None:
            logger.debug("Budget row already exists for agent %s — skipping provision", agent_id)
            return existing, False

        limit = budget_limit if budget_limit is not None else DEFAULT_BUDGET_LIMIT
        row = LLCAgentBudget(
            id=uuid.uuid4(),
            company_id=company_id,
            agent_id=agent_id,
            budget_mode="dollars",
            budget_limit=limit,
            budget_spent=Decimal("0"),
            tokens_spent=0,
            alert_threshold=0.8,
        )
        session.add(row)
        logger.info("Provisioned budget for agent %s (company=%s limit=%s)", agent_id, company_id, limit)
        return row, True

    async def ingest_cost_event(
        self,
        session: AsyncSession,
        agent_id: str,
        tokens_in: int,
        tokens_out: int,
        model: str,
    ) -> Decimal:
        """Record token cost for an agent and enforce budget limits (GH#8215, GH#8997).

        Supports two budget modes:
        - DOLLARS: tracks cost in USD, enforces budget_limit
        - TOKENS: tracks token counts, enforces token_limit

        Both modes track tokens_spent for analytics; only TOKENS mode enforces on tokens.

        Uses atomic UPDATE to avoid read-modify-write races across 4 uvicorn workers.

        Returns the dollar cost added this call (always calculated for analytics).
        Raises BudgetExhausted if spending exceeds the active budget mode limit.
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

        total_tokens = tokens_in + tokens_out

        # Atomic increment — prevents lost-update across concurrent workers
        # Always update both dollar and token counters for analytics (GH#8997)
        await session.execute(
            text(
                "UPDATE llc_agent_budgets"
                " SET budget_spent = budget_spent + :cost,"
                "     tokens_spent = tokens_spent + :tokens"
                " WHERE agent_id = :agent_id"
            ),
            {"cost": str(cost), "tokens": total_tokens, "agent_id": agent_id},
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
        tokens_spent = int(row.tokens_spent)
        token_limit = int(row.token_limit) if row.token_limit is not None else None
        budget_mode = str(row.budget_mode)

        # Push updated state into cross-worker cache (GH#6630, GH#8997).
        await _tracker.record_state(
            AgentBudgetState(
                agent_id=agent_id,
                budget_mode=budget_mode,
                budget_spent=float(spent),
                budget_limit=float(limit),
                tokens_spent=tokens_spent,
                token_limit=token_limit,
                alert_threshold=float(threshold),
            )
        )

        # Enforce budget based on mode (GH#8997)
        if budget_mode == "tokens" and token_limit is not None:
            if tokens_spent > token_limit:
                raise BudgetExhausted(agent_id=agent_id, spent=tokens_spent, limit=token_limit)
            if token_limit > 0 and tokens_spent / token_limit >= threshold:
                await self._emit_alert(agent_id, tokens_spent, token_limit)
        else:
            # Default DOLLARS mode
            if spent > limit:
                raise BudgetExhausted(agent_id=agent_id, spent=float(spent), limit=float(limit))
            if limit > Decimal("0") and spent / limit >= threshold:
                await self._emit_alert(agent_id, float(spent), float(limit))

        return cost

    async def check_budget(self, session: AsyncSession, agent_id: str) -> Tuple[Decimal, bool, bool]:
        """Return (remaining, is_over_limit, alert_triggered) for an agent (GH#6630, GH#8997).

        remaining can be negative when spent exceeds limit.

        For TOKENS mode, remaining is in token count.
        For DOLLARS mode, remaining is in USD.

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

        budget_mode = str(row.budget_mode)
        spent = Decimal(str(row.budget_spent))
        limit = Decimal(str(row.budget_limit))
        tokens_spent = int(row.tokens_spent)
        token_limit = int(row.token_limit) if row.token_limit is not None else None
        threshold = Decimal(str(row.alert_threshold))

        # Calculate based on budget mode (GH#8997)
        if budget_mode == "tokens" and token_limit is not None:
            remaining = Decimal(str(token_limit - tokens_spent))
            is_over_limit = tokens_spent > token_limit
            alert_triggered = token_limit > 0 and tokens_spent / token_limit >= threshold
        else:
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
