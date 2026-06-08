# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AgentBudgetTracker — SharedRuntimeBag-backed cross-worker budget cache.

GH#6630 / GH#6470: Canonical first consumer of SharedRuntimeBag.

Problem solved:
  BudgetService previously hit the DB on every check_budget() call.
  Under 4 uvicorn workers the budget state was invisible across processes
  until the next DB round-trip.  This class caches the authoritative DB
  row in SharedRuntimeBag so any worker can read current spend without a
  DB query, and so the hard-stop check is consistent across workers.

Write path:
  After every ingest_cost_event DB commit, call record_state() to push the
  latest row into the bag (TTL 5 min — short enough to stay fresh, long
  enough to survive a watchdog cycle).

Read path:
  Call get_state() before issuing a DB read.  On cache miss fall through to
  the DB as normal.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from decimal import Decimal

from pydantic import BaseModel

from autobot_shared.coordination.shared_runtime_bag import ChangeEvent, SharedRuntimeBag

logger = logging.getLogger(__name__)

_NAMESPACE = "agent_budget"
_TTL_S = 300  # 5 minutes


class AgentBudgetState(BaseModel):
    """Serialisable snapshot of an agent's budget row (GH#6630, GH#8997)."""

    agent_id: str
    budget_mode: str  # "dollars" or "tokens"

    # Dollar-based fields
    budget_spent: float
    budget_limit: float

    # Token-based fields (GH#8997)
    tokens_spent: int
    token_limit: int | None

    alert_threshold: float

    @property
    def remaining(self) -> Decimal:
        """Return remaining budget in the active mode."""
        if self.budget_mode == "tokens" and self.token_limit is not None:
            return Decimal(str(self.token_limit - self.tokens_spent))
        return Decimal(str(self.budget_limit)) - Decimal(str(self.budget_spent))

    @property
    def is_over_limit(self) -> bool:
        """Check if budget is exceeded in the active mode."""
        if self.budget_mode == "tokens" and self.token_limit is not None:
            return self.tokens_spent > self.token_limit
        return self.budget_spent > self.budget_limit

    @property
    def alert_triggered(self) -> bool:
        """Check if alert threshold crossed in the active mode."""
        if self.budget_mode == "tokens" and self.token_limit is not None:
            if self.token_limit <= 0:
                return False
            return (self.tokens_spent / self.token_limit) >= self.alert_threshold
        if self.budget_limit <= 0:
            return False
        return (self.budget_spent / self.budget_limit) >= self.alert_threshold


class AgentBudgetTracker:
    """Cross-worker budget state cache backed by SharedRuntimeBag.

    Instantiate once per process (or inject via dependency container).
    The underlying bag is safe to share across coroutines.

    Example::

        tracker = AgentBudgetTracker()

        # After DB write:
        await tracker.record_state(AgentBudgetState(
            agent_id=agent_id,
            budget_spent=float(row.budget_spent),
            budget_limit=float(row.budget_limit),
            alert_threshold=float(row.alert_threshold),
        ))

        # Before an expensive DB read:
        state = await tracker.get_state(agent_id)
        if state and state.is_over_limit:
            raise BudgetExhausted(...)
    """

    def __init__(self, ttl_s: int = _TTL_S) -> None:
        self._bag: SharedRuntimeBag[AgentBudgetState] = SharedRuntimeBag(
            _NAMESPACE, AgentBudgetState, default_ttl_s=ttl_s
        )

    async def record_state(self, state: AgentBudgetState) -> None:
        """Push *state* into the cross-worker cache.

        Called after every successful DB commit in BudgetService so all
        workers see the updated spend immediately.
        """
        try:
            await self._bag.set(state.agent_id, state)
        except Exception:
            # Cache write is best-effort — never block the caller.
            logger.warning(
                "AgentBudgetTracker.record_state failed for %s (swallowed)",
                state.agent_id,
            )

    async def get_state(self, agent_id: str) -> AgentBudgetState | None:
        """Return cached budget state for *agent_id*, or None on miss."""
        try:
            return await self._bag.get(agent_id)
        except Exception:
            logger.warning(
                "AgentBudgetTracker.get_state failed for %s (swallowed)",
                agent_id,
            )
            return None

    async def invalidate(self, agent_id: str) -> None:
        """Remove the cached entry (e.g. after a budget reset)."""
        try:
            await self._bag.delete(agent_id)
        except Exception:
            logger.warning(
                "AgentBudgetTracker.invalidate failed for %s (swallowed)",
                agent_id,
            )

    async def subscribe_changes(self) -> AsyncIterator[ChangeEvent]:
        """Yield AgentBudgetState change events for all agents.

        Useful for the BudgetWatchdog to react to cross-worker budget updates
        without polling.
        """
        async for event in self._bag.subscribe_changes():
            yield event
