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
from ..exceptions import AdapterAuthFailed, AdapterRunFailed
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
