# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attach an agent's role credentials to a run's context (#20533).

Kept out of ``heartbeat_scheduler``, which sits at its size ceiling.
"""

import uuid
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from user_management.database import get_async_session_factory

from ..credential_env import ROLE_CREDENTIALS_KEY
from ..services.role_credential_env import RoleCredentialEnvResolver

logger = get_logger(__name__)


async def attach_role_credentials(adapter: Any, agent: Dict[str, Any], context: Dict[str, Any]) -> None:
    """Put the agent's role credentials in *context* when *adapter* can place them in a child env.

    Adapters that send the context elsewhere (an HTTP body, an in-process agent)
    never get them: only ``injects_role_credentials`` adapters do. A failure to
    resolve raises, so the run fails visibly rather than starting without them.
    """
    if getattr(adapter, "injects_role_credentials", False) is not True or not context.get("company_id"):
        return
    try:
        company_id, agent_id = (
            uuid.UUID(str(context["company_id"])),
            uuid.UUID(str(agent["agent_id"])),
        )
    except ValueError:
        # role tenure is keyed by UUID; a non-UUID agent id cannot hold a role
        logger.warning(
            "role credentials skipped: non-UUID id (agent_id=%s company_id=%s)",
            agent.get("agent_id"),
            context.get("company_id"),
        )
        return
    async with get_async_session_factory()() as session:
        creds = await RoleCredentialEnvResolver().resolve_for_agent(session, company_id, agent_id)
        await session.commit()  # the refusal audit rows
    if creds:
        context[ROLE_CREDENTIALS_KEY] = creds
