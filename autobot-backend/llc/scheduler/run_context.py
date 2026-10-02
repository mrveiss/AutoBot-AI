# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Context enrichment for a heartbeat run (GH#8243).

Moved out of ``heartbeat_scheduler`` in #16818: the scheduler is at its size ceiling,
and this is the piece with no scheduling in it -- it answers "what should the agent
know?", not "when should it run?". Extracted rather than the ceiling raised.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def fetch_recent_decisions(company_id: str, n: int = 5) -> list[Dict[str, Any]]:
    """The most recent decisions from the decisions KB, for ``context_mode=fat``.

    Best-effort: returns an empty list on any failure rather than blocking the
    heartbeat. The empty list is therefore ambiguous by design here -- a company with
    no decisions and an unreachable KB look alike -- so the failure is logged, which
    is what separates them for anyone asking why a context arrived thin.
    """
    try:
        from ..kb.decision_log import DecisionLogReader

        reader = DecisionLogReader()
        return await reader.list_decisions(company_id=company_id, limit=n)
    except Exception as exc:
        logger.warning("Failed to fetch recent decisions for company %s: %s", company_id, exc)
        return []


async def enrich_run_context(agent: Dict[str, Any], context: Dict[str, Any], run: Any) -> None:
    """Fill *context* for this run and record on *run* which mode produced it.

    ``context_snapshot`` is written in both branches (GH#8499) so the field is never
    NULL: a run whose context cannot be reconstructed afterwards cannot be diagnosed
    afterwards either, and "slim" and "nobody wrote anything" would otherwise look
    identical in the column.
    """
    context_mode = agent.get("context_mode") or "slim"
    if context_mode == "fat":
        company_id_val = agent.get("company_id")
        if company_id_val:
            context["recent_decisions"] = await fetch_recent_decisions(str(company_id_val))
        run.context_snapshot = {"mode": "fat", "generated_at": datetime.now(tz=timezone.utc).isoformat()}
    else:
        run.context_snapshot = {"mode": context_mode}


__all__ = ["enrich_run_context", "fetch_recent_decisions"]
