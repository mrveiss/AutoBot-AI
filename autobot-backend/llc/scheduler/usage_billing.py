# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Charging a finished registry run's usage, by how it was billed (#20266).

A run on a subscription login spent tokens, not dollars: its tokens and cost event are
recorded, it adds nothing to ``budget_spent``, and so no dollar limit can fail it or stop
the next run (``bill_dollars=False``). Only a token limit or ``SubscriptionQuotaExhausted``
can. A run whose billing is API, or unknown, is charged and keeps the hard stop (GH#8215).
"""

from __future__ import annotations

from typing import Any, AsyncContextManager

from autobot_shared.db_session import async_session_scope
from autobot_shared.logging_manager import get_logger
from llc.adapters.base import BILLING_SUBSCRIPTION, AdapterRunStatus
from llc.exceptions import BudgetExhausted
from user_management.database import get_async_session_factory

logger = get_logger(__name__)


async def ingest_run_cost(
    service: Any, session: Any, result: AdapterRunStatus, agent_id: str, company_id: str, usage: tuple, model: str
) -> None:
    """``service.ingest_cost_event`` for one run, charging dollars only when it was API-billed.

    A subscription run adds no dollars, so only a token limit can be crossed; that finished
    run is still recorded, and the gate stops the NEXT one. API and unknown billing raise.
    """
    tokens_in, tokens_out = usage
    subscription = result.billing == BILLING_SUBSCRIPTION
    try:
        await service.ingest_cost_event(
            session, agent_id, company_id, tokens_in, tokens_out, model, bill_dollars=not subscription
        )
    except BudgetExhausted as exc:
        if not subscription:
            raise
        logger.warning("agent %s: subscription run crossed its token limit (%s); next dispatch is gated", agent_id, exc)


def budget_session_scope() -> AsyncContextManager[Any]:
    """The session a native AutoBot-agent run's cost is ingested in: commits on success (#20883).

    ``AutoBotAgentAdapter`` forwards a run's usage itself and has no commit of its own;
    ``BudgetService.ingest_cost_event`` commits only on its hard-stop path, so without this
    scope the spend of a run that stays under its limit was rolled back on exit. A registry
    run is charged by the scheduler's ``_ingest_adapter_usage`` instead; a run takes exactly
    one of the two, so nothing is charged twice.
    """
    return async_session_scope(get_async_session_factory())
