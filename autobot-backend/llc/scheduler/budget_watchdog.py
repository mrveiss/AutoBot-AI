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

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client
from models.agent_org import AgentOrgNode
from user_management.database import get_async_session_factory
from user_management.models.organization import Organization

from ..models.budget import LLCAgentBudget
from ..services.budget import BudgetService
from .base import PollLoopScheduler

logger = logging.getLogger(__name__)

_SOFT_THRESHOLD = Decimal("0.80")
_HARD_THRESHOLD = Decimal("1.00")
_POLL_INTERVAL_SECONDS = 300  # 5 minutes


class BudgetWatchdog(PollLoopScheduler):
    """Periodic watchdog that enforces company and agent budget limits."""

    _task_name = "llc-budget-watchdog"

    def __init__(self, poll_interval: int = _POLL_INTERVAL_SECONDS) -> None:
        super().__init__(poll_interval)
        self._budget_svc = BudgetService()

    def start(self) -> None:
        """Start the background polling loop."""
        if super().start():
            logger.info("BudgetWatchdog started (poll interval: %ds)", self._poll_interval)

    async def _tick(self) -> None:
        await self._check_once()

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
        - TOKENS: ratio = tokens_spent / token_limit; a tokens-mode row with no
          token_limit falls back to dollar enforcement, matching
          BudgetService.check_budget / _derive_status semantics.
        """
        result = await session.execute(
            select(LLCAgentBudget).where(or_(LLCAgentBudget.budget_limit > 0, LLCAgentBudget.token_limit > 0))
        )
        rows = list(result.scalars().all())

        for row in rows:
            budget_mode = str(row.budget_mode)
            token_limit = int(row.token_limit) if row.token_limit is not None else 0
            if budget_mode == "tokens" and token_limit > 0:
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
            _, is_over, _ = await self._budget_svc.check_budget(session, row.agent_id, row.company_id)
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
            await self._pause_agent(row.agent_id, row.company_id)
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

    async def _pause_agent(self, agent_id: str, company_id: str) -> None:
        """Best-effort: mark agent inactive in agent_org_nodes, within its company.

        Scoped by company: the slug is unique per company on the budget side
        (#15812), so an unscoped UPDATE would let one company's exhausted budget
        pause another company's agent the moment two of them share a slug.

        Built through the ORM rather than raw SQL because the two sides are
        different types — this column is ``UUID`` and the budget row carries the
        company as text — and hand-writing the conversion gets it wrong. A
        ``CAST(company_id AS TEXT)`` comparison renders as unhyphenated hex on
        SQLite and never matches ``str(uuid)``, so the UPDATE silently pauses
        nothing: the scoping fix would have been a scoping-shaped no-op.
        SQLAlchemy binds a ``uuid.UUID`` correctly on both backends.
        """
        try:
            company_uuid = uuid.UUID(str(company_id))
        except (TypeError, ValueError):
            logger.warning(
                "_pause_agent: agent %s has an unparseable company_id %r — not pausing, "
                "because an unscoped pause could stop another company's agent (#15812)",
                agent_id,
                company_id,
            )
            return

        factory = get_async_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(
                    update(AgentOrgNode)
                    .where(
                        AgentOrgNode.agent_id == agent_id,
                        # NULL-company rows predate the #15858 backfill: 037 added
                        # the column nullable on purpose ("operators must set it")
                        # and nothing since backfills it. Excluding them would make
                        # `NULL = :uuid` evaluate NULL, match no row, and silently
                        # disable the budget hard stop for every agent an operator
                        # has not yet scoped -- the agent would keep spending.
                        # Over-pausing an unattributed row is the safer error, and
                        # is what this code did before #15812. Drop the is_(None)
                        # arm when #15858 makes the column NOT NULL.
                        or_(AgentOrgNode.company_id == company_uuid, AgentOrgNode.company_id.is_(None)),
                        AgentOrgNode.status != "inactive",
                    )
                    .values(status="inactive")
                )
                await session.commit()
                if result.rowcount == 0:
                    # A zero-row UPDATE raises nothing, so without this the hard
                    # stop failing and the hard stop succeeding look identical.
                    logger.warning(
                        "_pause_agent: no org node matched agent %s in company %s — "
                        "the budget hard stop paused nothing",
                        agent_id,
                        company_id,
                    )
        except Exception:
            logger.debug("_pause_agent for %s failed (swallowed)", agent_id)
