# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What a claude_code authentication failure does to a run and its agent (#20202).

The run itself is recorded by the ordinary FAILED path, with the adapter's reason in its
``error``. Pausing the agent is a separate, best-effort step afterwards: an expired Claude
login fails every wake the same way, but a failed pause must never cost the FAILED row.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from autobot_shared.logging_manager import get_logger
from user_management.database import get_async_session_factory

from ..adapters.base import AdapterRunStatus
from ..adapters.claude_code_adapter import AUTH_FAILED_REASON
from ..exceptions import AdapterAuthFailed, AdapterRunFailed, ProviderRateLimited, SubscriptionQuotaExhausted
from ..models.enums import LLCRunStatus
from ..services.controls_service import ControlsService

logger = get_logger(__name__)

_PAUSE_REASON = "Claude login needs re-authentication (run {run_id}); resume the agent manually after signing in again"


def adapter_run_failure(agent: Dict[str, Any], external_run_id: Any, result: AdapterRunStatus) -> AdapterRunFailed:
    """The exception for a non-success registry run.

    ``AUTH_FAILED_REASON`` is only ever produced by the Claude CLI adapters (plain and subscription),
    so equality with it is what makes a run an auth failure; other adapters' failures stay plain (#20883).
    """
    failed = AdapterAuthFailed if result.error == AUTH_FAILED_REASON else AdapterRunFailed
    return failed(agent.get("adapter_type") or "", str(external_run_id), result.status, result.error)


def raise_for_scheduler_internal_status(agent: Dict[str, Any], external_run_id: Any, result: AdapterRunStatus) -> None:
    """Translate the two scheduler-internal terminal statuses of a registry run into their exceptions.

    GH#9773: RATE_LIMITED becomes ``ProviderRateLimited`` so the GH#8204 backoff path applies uniformly
    for registry adapters. ``_run_adapter`` catches it and calls ``_handle_rate_limited``; the status
    never reaches the DB as a RATE_LIMITED terminal adapter status.

    GH#10218: subscription quota exhausted is terminal-with-no-retry; surfacing it lets ``_run_adapter``
    auto-pause the agent and notify the board rather than record a generic FAILED that the liveness
    monitor would try to recover.
    """
    agent_id: str = agent["agent_id"]
    if result.status == LLCRunStatus.RATE_LIMITED:
        logger.warning(
            "agent %s: registry adapter signalled RATE_LIMITED for run %s — raising ProviderRateLimited",
            agent_id,
            external_run_id,
        )
        raise ProviderRateLimited(provider=agent.get("adapter_type") or "registry", retry_after_seconds=0)
    if result.status == LLCRunStatus.QUOTA_EXHAUSTED:
        raise SubscriptionQuotaExhausted(agent_id, str(result.error or "subscription quota exhausted"))


async def pause_after_auth_failure(failure: Optional[Exception], agent: Dict[str, Any], run_id: uuid.UUID) -> None:
    """Pause the agent when *failure* is an auth failure; a pause that cannot happen is logged, not raised."""
    if not isinstance(failure, AdapterAuthFailed):
        return
    agent_id = agent["agent_id"]
    company_id = str(agent.get("company_id") or "")
    if not company_id:
        logger.warning("Agent %s failed authentication but has no company_id - not auto-paused", agent_id)
        return
    try:
        async with get_async_session_factory()() as session:
            reason = _PAUSE_REASON.format(run_id=run_id)
            await ControlsService().pause_agent(
                session, company_id, agent_id, actor_user_id=None, reason=reason, actor_type="system"
            )
            await session.commit()
        logger.warning("Agent %s auto-paused after a Claude authentication failure (run %s)", agent_id, run_id)
    except Exception:
        logger.warning(
            "Could not auto-pause agent %s after an authentication failure (run %s)", agent_id, run_id, exc_info=True
        )
