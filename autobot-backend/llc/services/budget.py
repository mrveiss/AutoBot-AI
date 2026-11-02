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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.local_models import is_local_model
from autobot_shared.redis_client import get_async_redis_client
from llc.config import DEFAULT_BUDGET_LIMIT
from llc.exceptions import BudgetExhausted, UnpricedModel, WorkItemNotInCompany
from llc.models.budget import LLCAgentBudget
from llc.models.company_os_cost import CompanyOsCostEvent
from llc.models.work_item import LLCWorkItem
from llm_shared.pricing.sync_cache import PricingCacheCold, get_cached_price

from .agent_budget_tracker import AgentBudgetState, AgentBudgetTracker
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

#: The constraint a cost event breaks when its work item no longer exists (``CompanyOsCostEvent.work_item_id``).
WORK_ITEM_FK = "fk_company_os_cost_events_work_item"

_tracker = AgentBudgetTracker()  # noqa: SRB001 — canonical SharedRuntimeBag consumer


def _for_agent(agent_id: str, company_id: str):
    """Select one agent's budget row, scoped to its company.

    Every lookup goes through this rather than filtering on ``agent_id`` alone.
    The slug is unique per company, not globally (#15812), so a bare
    ``WHERE agent_id = :slug`` returns *whichever* company's row the database
    happens to hold — and reads, writes and spend enforcement would all cross
    the tenant boundary silently, because the query still returns exactly one
    row and nothing looks wrong.
    """
    return select(LLCAgentBudget).where(
        LLCAgentBudget.agent_id == agent_id,
        LLCAgentBudget.company_id == company_id,
    )


async def _record_event(
    session: AsyncSession, agent_id: str, company_id: str, work_item_id: Optional[str], usage: tuple
) -> None:
    """Add the per-event cost row (#16016); a work item must be in ``company_id``.

    Refuses rather than recording unattributed: a caller that names an item and gets
    a ``200`` believes the cost landed on it. Unknown and foreign ids are
    indistinguishable on purpose, so the refusal does not confirm another company's id.
    """
    item_id = None
    if work_item_id is not None:
        try:
            item_id = uuid.UUID(str(work_item_id))
        except ValueError:
            raise WorkItemNotInCompany(work_item_id) from None
        owner = (
            await session.execute(select(LLCWorkItem.company_id).where(LLCWorkItem.id == item_id))
        ).scalar_one_or_none()
        if owner is None or str(owner) != str(company_id):
            raise WorkItemNotInCompany(work_item_id)
    model, tokens_in, tokens_out, cost = usage
    event = CompanyOsCostEvent(
        company_id=uuid.UUID(str(company_id)),
        agent_id=agent_id,
        work_item_id=item_id,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
    )
    if item_id is None:
        session.add(event)
    else:
        await _add_event(session, event, work_item_id)


async def _add_event(session: AsyncSession, event: CompanyOsCostEvent, work_item_id: str) -> None:
    """Insert the event now, so an item deleted since the ownership check is a refusal, not a 500 later (#20168).

    The foreign key would otherwise fail on the caller's next statement. The add and flush sit in one savepoint,
    so a refusal leaves the caller's transaction usable. Only that foreign key is mapped; any other integrity
    error is a real fault and propagates.
    """
    try:
        async with session.begin_nested():
            session.add(event)
            await session.flush()
    except IntegrityError as exc:
        if WORK_ITEM_FK not in str(exc.orig):
            raise
        logger.info("cost event refused: work item %s was deleted after the ownership check", work_item_id)
        raise WorkItemNotInCompany(work_item_id) from None


def _cost_of(model: str, agent_id: str, tokens_in: int, tokens_out: int) -> Decimal:
    """Dollar cost of one call; ``UnpricedModel`` if it cannot be priced (moved out of ``ingest_cost_event``)."""
    if is_local_model(model):
        # #16316: free by construction -- a local model was never going to
        # appear in a hosted-API price catalogue, and that absence is not
        # the same fact as "nobody has priced this yet". Checked before the
        # cache is consulted at all, so a cold or unpopulated snapshot can
        # never affect a local model's cost.
        return Decimal("0")
    try:
        pricing = get_cached_price(model)
    except PricingCacheCold:
        # #16316: the local mirror has not completed its first read from
        # Redis yet. "Cannot compute right now" and "genuinely unpriced"
        # both mean the same thing to a caller -- refuse, do not guess --
        # so both raise the same exception; only the log line differs,
        # because this one is transient and the other is not.
        logger.warning(
            "ingest_cost_event: pricing cache cold for model=%r agent=%s -- refusing rather than guessing",
            model,
            agent_id,
        )
        raise UnpricedModel(model=model, agent_id=agent_id) from None
    if pricing is None:
        # #15860: this used to log and charge zero. A cost of 0 and a cost
        # that could not be computed are the same number, and only one of
        # them is a fact -- so an unpriced model made dollar budgets
        # silently inapplicable rather than visibly broken.
        raise UnpricedModel(model=model, agent_id=agent_id)
    return Decimal(str((tokens_in * pricing.input_per_1m + tokens_out * pricing.output_per_1m) / 1_000_000))


class BudgetService(LLCServiceBase):
    """Per-agent budget enforcement: cost ingest, hard stop, soft alert."""

    @staticmethod
    async def invalidate_cache(agent_id: str, company_id: str) -> None:
        """Drop the tracker cache for an agent after its limits/mode change."""
        await _tracker.invalidate(company_id, agent_id)

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
        existing = (await session.execute(_for_agent(agent_id, company_id))).scalar_one_or_none()
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
        try:
            async with session.begin_nested():
                await session.flush()
        except IntegrityError:
            # Concurrent provision won the race — re-select and return existing row.
            existing = (await session.execute(_for_agent(agent_id, company_id))).scalar_one_or_none()
            logger.debug("Race on provision_budget for agent %s — returning existing row", agent_id)
            return existing, False

        logger.info("Provisioned budget for agent %s (company=%s limit=%s)", agent_id, company_id, limit)
        return row, True

    async def ingest_cost_event(
        self,
        session: AsyncSession,
        agent_id: str,
        company_id: str,
        tokens_in: int,
        tokens_out: int,
        model: str,
        work_item_id: Optional[str] = None,
        bill_dollars: bool = True,
    ) -> Decimal:
        """Record token cost for an agent and enforce budget limits (GH#8215, GH#8997).

        ``bill_dollars=False`` is a run on a subscription login (#20266): it spent tokens, not
        dollars. Its event row and ``tokens_spent`` are recorded, but the event's cost is 0, so
        ``budget_spent`` is untouched and no dollar limit can be crossed; a token limit still holds.

        Also writes one ``company_os_cost_events`` row (#16016), tied to ``work_item_id``
        when given. Raises ``WorkItemNotInCompany`` if that item is not in ``company_id``.

        Supports two budget modes:
        - DOLLARS: tracks cost in USD, enforces budget_limit
        - TOKENS: tracks token counts, enforces token_limit

        Both modes track tokens_spent for analytics; only TOKENS mode enforces on tokens.

        Uses atomic UPDATE to avoid read-modify-write races across 4 uvicorn workers.

        Returns the dollar cost added this call (always calculated for analytics).
        Raises BudgetExhausted if spending exceeds the active budget mode limit,
        and UnpricedModel if the model is neither local nor in the live catalogue.
        """
        cost = _cost_of(model, agent_id, tokens_in, tokens_out) if bill_dollars else Decimal("0")

        total_tokens = tokens_in + tokens_out
        await _record_event(session, agent_id, company_id, work_item_id, (model, tokens_in, tokens_out, cost))

        # Atomic increment — prevents lost-update across concurrent workers
        # Always update both dollar and token counters for analytics (GH#8997)
        await session.execute(
            text(
                "UPDATE llc_agent_budgets"
                " SET budget_spent = budget_spent + :cost,"
                "     tokens_spent = tokens_spent + :tokens"
                " WHERE agent_id = :agent_id AND company_id = :company_id"
            ),
            {
                "cost": str(cost),
                "tokens": total_tokens,
                "agent_id": agent_id,
                "company_id": company_id,
            },
        )

        # `populate_existing`: this read is what enforcement is decided on, so it
        # must reflect the UPDATE just issued rather than the caller's session
        # state. Without it SQLAlchemy's identity map returns the object the
        # caller already loaded, carrying its pre-UPDATE `budget_spent` -- a
        # plain SELECT does not overwrite already-loaded attributes.
        #
        # Not hypothetical, and not symmetrical between the two callers.
        # `POST /agent/cost-events` opens its own session and never pre-loads the
        # row, so its first read was fresh and the hard stop worked.
        # `POST /budgets/{agent_id}/ingest` calls `load_authorized` first -- which
        # puts the row in the identity map by design, that being the IDOR guard --
        # and then hands the SAME session here. Enforcement compared the
        # PRE-UPDATE spend against the limit, so `BudgetExhausted` could not fire
        # on that route at all. The hard stop #15859 exists for was inoperative on
        # one of its two callers, and nothing looked wrong: both routes returned a
        # correct cost, and only the enforcement that follows was reading a stale
        # number.
        #
        # Fixed in the service, not in the route: a service whose correctness
        # depends on whether its caller happened to load a row first breaks again
        # the next time someone adds a caller. There are four.
        result = await session.execute(_for_agent(agent_id, company_id).execution_options(populate_existing=True))
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
                company_id=company_id,
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
        elif bill_dollars:
            # Default DOLLARS mode
            if spent > limit:
                raise BudgetExhausted(agent_id=agent_id, spent=float(spent), limit=float(limit))
            if limit > Decimal("0") and spent / limit >= threshold:
                await self._emit_alert(agent_id, float(spent), float(limit))

        return cost

    async def check_budget(self, session: AsyncSession, agent_id: str, company_id: str) -> Tuple[Decimal, bool, bool]:
        """Return (remaining, is_over_limit, alert_triggered) for an agent (GH#6630, GH#8997).

        remaining can be negative when spent exceeds limit.

        For TOKENS mode, remaining is in token count.
        For DOLLARS mode, remaining is in USD.

        Reads from SharedRuntimeBag cache first (GH#6630); falls back to DB
        on cache miss so correctness is preserved.
        """
        cached = await _tracker.get_state(company_id, agent_id)
        if cached is not None:
            return cached.remaining, cached.is_over_limit, cached.alert_triggered

        result = await session.execute(_for_agent(agent_id, company_id))
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
