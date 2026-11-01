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

from typing import Any

from autobot_shared.logging_manager import get_logger
from llc.adapters.base import BILLING_SUBSCRIPTION, AdapterRunStatus
from llc.exceptions import BudgetExhausted

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
