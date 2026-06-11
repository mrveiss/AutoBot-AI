# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC budget watchdog — soft alert + hard stop for over-budget agents (GH#8228).

Runs every 5 minutes. Queries agents where:
  spent_monthly_cents >= budget_monthly_cents * 0.80 (soft threshold)

For soft-threshold agents: publishes a notification to
  Redis pub/sub channel: llc:notifications:{company_id}

For agents at or over 100%: calls BudgetService hard stop (idempotent).
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client
from user_management.database import get_async_session_factory
from user_management.models.organization import Organization

from ..models.budget import LLCAgentBudget
from ..services.budget import BudgetService

logger = logging.getLogger(__name__)

_SOFT_THRESHOLD = Decimal("0.80")
_HARD_THRESHOLD = Decimal("1.00")
_POLL_INTERVAL_SECONDS = 300  # 5 minutes


class BudgetWatchdog:
    """Periodic watchdog that enforces company and agent budget limits."""

    def __init__(self, poll_interval: int = _POLL_INTERVAL_SECONDS) -> None:
        self._poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._budget_svc = BudgetService()

    def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="llc-budget-watchdog")
        logger.info("BudgetWatchdog started (poll interval: %ds)", self._poll_interval)

    def stop(self) -> None:
        """Stop the background polling loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("BudgetWatchdog._check_once failed")
            await asyncio.sleep(self._poll_interval)

    async def _check_once(self) -> None:
        """Single scan — find over-threshold agents and notify / hard-stop."""
        factory = get_async_session_factory()
        async with factory() as session:
            await self._check_agent_budgets(session)
            await self._check_company_budgets(session)

    # ------------------------------------------------------------------
    # Per-agent budget checks
    # ------------------------------------------------------------------

    async def _check_agent_budgets(self, session: AsyncSession) -> None:
        """Check all agent budget rows for threshold violations (GH#8997).

        Evaluates each agent in its active budget mode:
        - DOLLARS: ratio = budget_spent / budget_limit
        - TOKENS: ratio = tokens_spent / token_limit (only when token_limit > 0)
        """
        result = await session.execute(select(LLCAgentBudget))
        rows = list(result.scalars().all())

        for row in rows:
            budget_mode = str(row.budget_mode)
            if budget_mode == "tokens":
                token_limit = int(row.token_limit) if row.token_limit is not None else 0
                if token_limit <= 0:
                    continue
                tokens_spent = int(row.tokens_spent)
                ratio = Decimal(str(tokens_spent)) / Decimal(str(token_limit))
            else:
                limit = Decimal(str(row.budget_limit))
                if limit <= Decimal("0"):
                    continue
                ratio = Decimal(str(row.budget_spent)) / limit

            if ratio >= _HARD_THRESHOLD:
                await self._hard_stop_agent(session, row)
            elif ratio >= _SOFT_THRESHOLD:
                await self._notify_agent_soft(row, ratio)

    async def _hard_stop_agent(self, session: AsyncSession, row: LLCAgentBudget) -> None:
        """Idempotent hard stop: pause the agent if not already paused (GH#8997)."""
        try:
            # BudgetService.check_budget returns (remaining, is_over, alert)
            _, is_over, _ = await self._budget_svc.check_budget(session, row.agent_id)
            if not is_over:
                return  # race condition — already under limit, skip
            budget_mode = str(row.budget_mode)
            if budget_mode == "tokens":
                spent_val = int(row.tokens_spent)
                limit_val = int(row.token_limit) if row.token_limit is not None else 0
                logger.warning(
                    "BudgetWatchdog: agent %s exhausted token budget (%d / %d) — hard stop",
                    row.agent_id,
                    spent_val,
                    limit_val,
                )
            else:
                spent_val = float(row.budget_spent)
                limit_val = float(row.budget_limit)
                logger.warning(
                    "BudgetWatchdog: agent %s exhausted dollar budget (%.2f / %.2f) — hard stop",
                    row.agent_id,
                    spent_val,
                    limit_val,
                )
            await self._notify(
                company_id=row.company_id,
                event_type="budget.hard_stop",
                payload={
                    "agent_id": row.agent_id,
                    "budget_mode": budget_mode,
                    "spent": spent_val,
                    "limit": limit_val,
                    "shadow_cost_usd": float(row.budget_spent) if budget_mode == "tokens" else None,
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
            # Mark agent as paused in agent_org_nodes (best-effort)
            await self._pause_agent(row.agent_id)
        except Exception:
            logger.exception("hard_stop_agent failed for %s (swallowed)", row.agent_id)

    async def _notify_agent_soft(self, row: LLCAgentBudget, ratio: Decimal) -> None:
        """Publish soft-threshold notification (GH#8997)."""
        try:
            logger.info(
                "BudgetWatchdog: agent %s at %.0f%% of budget — soft alert",
                row.agent_id,
                float(ratio) * 100,
            )
            budget_mode = str(row.budget_mode)
            if budget_mode == "tokens":
                spent_val = int(row.tokens_spent)
                limit_val = int(row.token_limit) if row.token_limit is not None else 0
            else:
                spent_val = float(row.budget_spent)
                limit_val = float(row.budget_limit)
            await self._notify(
                company_id=row.company_id,
                event_type="budget.soft_alert",
                payload={
                    "agent_id": row.agent_id,
                    "budget_mode": budget_mode,
                    "spent": spent_val,
                    "limit": limit_val,
                    "ratio": float(ratio),
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
        except Exception:
            logger.debug("notify_agent_soft failed for %s (swallowed)", row.agent_id)

    # ------------------------------------------------------------------
    # Per-company budget checks
    # ------------------------------------------------------------------

    async def _check_company_budgets(self, session: AsyncSession) -> None:
        """Check organization-level monthly budget thresholds."""
        try:
            result = await session.execute(select(Organization).where(Organization.budget_monthly_cents > 0))
            orgs = list(result.scalars().all())
        except Exception:
            logger.debug("_check_company_budgets org query failed (swallowed)")
            return

        for org in orgs:
            if org.budget_monthly_cents <= 0:
                continue
            ratio = Decimal(str(org.spent_monthly_cents)) / Decimal(str(org.budget_monthly_cents))
            company_id = str(org.id)

            if ratio >= _HARD_THRESHOLD:
                logger.warning(
                    "BudgetWatchdog: company %s at %.0f%% — hard stop notification",
                    company_id,
                    float(ratio) * 100,
                )
                await self._notify(
                    company_id=company_id,
                    event_type="budget.company_hard_stop",
                    payload={
                        "company_id": company_id,
                        "spent_cents": org.spent_monthly_cents,
                        "budget_cents": org.budget_monthly_cents,
                        "ts": datetime.now(tz=timezone.utc).isoformat(),
                    },
                )
            elif ratio >= _SOFT_THRESHOLD:
                await self._notify(
                    company_id=company_id,
                    event_type="budget.company_soft_alert",
                    payload={
                        "company_id": company_id,
                        "spent_cents": org.spent_monthly_cents,
                        "budget_cents": org.budget_monthly_cents,
                        "ratio": float(ratio),
                        "ts": datetime.now(tz=timezone.utc).isoformat(),
                    },
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _notify(self, company_id: str, event_type: str, payload: dict) -> None:
        """Publish a notification to llc:notifications:{company_id}."""
        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("BudgetWatchdog: Redis unavailable, dropping %s", event_type)
            return
        try:
            channel = f"llc:notifications:{company_id}"
            await redis.publish(
                channel,
                json.dumps({"event_type": event_type, **payload}),
            )
        except Exception:
            logger.debug("_notify(%s) publish failed (swallowed)", event_type)

    async def _pause_agent(self, agent_id: str) -> None:
        """Best-effort: mark agent inactive in agent_org_nodes."""
        factory = get_async_session_factory()
        try:
            async with factory() as session:
                await session.execute(
                    text(
                        "UPDATE agent_org_nodes SET status = 'inactive'"
                        " WHERE agent_id = :agent_id AND status != 'inactive'"
                    ),
                    {"agent_id": agent_id},
                )
                await session.commit()
        except Exception:
            logger.debug("_pause_agent for %s failed (swallowed)", agent_id)
