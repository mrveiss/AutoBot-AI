# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Charging a finished registry run's usage, by how it was billed (#20266).

A run on a subscription login spent tokens, not dollars: its usage is recorded in
full, and a dollar limit it crosses does not fail the finished run. The accrued
spend still trips the dispatch gate, so an enforced budget stops the NEXT run
(#19240). A run whose billing is API, or unknown, keeps the hard stop (GH#8215).
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
    """``service.ingest_cost_event`` for one run; a subscription run is never failed over its limit."""
    tokens_in, tokens_out = usage
    try:
        await service.ingest_cost_event(session, agent_id, company_id, tokens_in, tokens_out, model)
    except BudgetExhausted as exc:
        if result.billing != BILLING_SUBSCRIPTION:
            raise
        logger.warning(
            "agent %s: subscription run crossed its budget (%s); recorded, next dispatch is gated", agent_id, exc
        )
