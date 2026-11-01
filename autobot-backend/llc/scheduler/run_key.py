# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ephemeral LLC API key one heartbeat run holds, and the wait it must outlive."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from autobot_shared.env_utils import env_float
from user_management.database import get_async_session_factory

from ..services.api_key import ApiKeyService

logger = logging.getLogger(__name__)

ADAPTER_MAX_WAIT_SECONDS = env_float("LLC_ADAPTER_MAX_WAIT_SECONDS", 7200.0)
_RUN_KEY_TTL_MARGIN_SECONDS = 600.0


def _run_key_ttl(configured: float, max_wait: float) -> float:
    """The key's lifetime: a shorter configured value would expire the key mid-run, so it never wins."""
    return max(configured, max_wait + _RUN_KEY_TTL_MARGIN_SECONDS)


# Ephemeral run-key TTL backstop — must exceed the max wait so a key never
# expires mid-run; revocation still happens promptly when the run finishes.
_RUN_KEY_TTL_SECONDS = _run_key_ttl(env_float("LLC_RUN_KEY_TTL_SECONDS", 0.0), ADAPTER_MAX_WAIT_SECONDS)


async def issue_run_key(agent_id: str, company_id: str) -> tuple[Any, Optional[str]]:
    """Issue an ephemeral run-scoped LLC API key. Returns (record, plaintext).

    Best-effort: on failure the agent still runs, just without a key (returns
    ``(None, None)``) — the run is logged rather than blocked.
    """
    factory = get_async_session_factory()
    try:
        async with factory() as session:
            record, raw = await ApiKeyService().issue_key(
                session,
                agent_id=agent_id,
                company_id=company_id,
                name=f"heartbeat-{agent_id}-{uuid.uuid4().hex[:8]}",
                expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=_RUN_KEY_TTL_SECONDS),
            )
        return record, raw
    except Exception:
        logger.exception("Failed to issue ephemeral heartbeat key for agent %s", agent_id)
        return None, None


async def revoke_run_key(agent_id: str, key_id: uuid.UUID, company_id: Optional[str] = None) -> None:
    """Revoke an ephemeral run-scoped key, company-scoped (#13771, #15930)."""
    factory = get_async_session_factory()
    try:
        async with factory() as session:
            await ApiKeyService().revoke_key(session, agent_id=agent_id, key_id=key_id, company_id=company_id)
    except Exception:
        logger.exception("Failed to revoke ephemeral heartbeat key %s for agent %s", key_id, agent_id)
