# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-agent heartbeat switch of the board controls (split from controls_service for size, #15907)."""

import uuid
from typing import Optional

from sqlalchemy import false, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.agent_org import AgentOrgNode

from ..models.enums import UNDISPATCHABLE_AGENT_STATUSES, LLCAgentStatus
from .company import CompanyService
from .controls_errors import AgentNotFoundError, AgentNotSchedulableError
from .heartbeat_activity import record_heartbeat_set

#: Statuses no heartbeat may wake: the terminal pair ``llc/api/replay.py`` rejects,
#: and the one migration 090 writes for a node that is not a company's CEO.
NEVER_SCHEDULED_STATUSES = UNDISPATCHABLE_AGENT_STATUSES - {LLCAgentStatus.PAUSED.value}


def _agent_in_company(company_id: str, agent_id: str) -> tuple:
    """One agent, by slug, only within *company_id* -- the tenant scope of every heartbeat write.

    A malformed company id matches nothing rather than raising, exactly as an
    unknown one does.
    """
    try:
        company = uuid.UUID(company_id)
    except ValueError:
        return (false(),)
    return (AgentOrgNode.company_id == company, AgentOrgNode.agent_id == agent_id)


class HeartbeatControlsMixin:
    """``set_agent_heartbeat`` for :class:`ControlsService`; needs ``self._activity_log``."""

    async def set_agent_heartbeat(
        self,
        session: AsyncSession,
        company_id: str,
        agent_id: str,
        enabled: bool,
        actor_user_id: str,
        default_cron: str,
    ) -> dict:
        """Switch one agent's periodic heartbeat on or off (#15907).

        Writes ``heartbeat_enabled``, the column the scheduler selects on. Enabling
        an agent that has no cron (a provisioned CEO) also gives it *default_cron*:
        the scheduler requires ``heartbeat_cron IS NOT NULL`` as well, so the flag
        alone would read as on and never fire. A cron already set is kept.
        """
        if enabled:
            await self._require_live_company(session, company_id)
        row = await self._get_heartbeat_row(session, company_id, agent_id)
        if row is None:
            raise AgentNotFoundError(agent_id)
        if enabled and row["status"] in NEVER_SCHEDULED_STATUSES:
            raise AgentNotSchedulableError(agent_id, row["status"])

        cron = row["heartbeat_cron"] or (default_cron if enabled else None)
        await session.execute(
            update(AgentOrgNode)
            .where(*_agent_in_company(company_id, agent_id))
            .values(heartbeat_enabled=enabled, heartbeat_cron=cron)
        )
        await record_heartbeat_set(
            self._activity_log,
            session,
            company_id,
            row["id"],
            actor_user_id,
            before={"heartbeat_enabled": row["heartbeat_enabled"], "heartbeat_cron": row["heartbeat_cron"]},
            after={"heartbeat_enabled": enabled, "heartbeat_cron": cron},
        )
        return {"agent_id": agent_id, "heartbeat_enabled": enabled, "heartbeat_cron": cron}

    async def _require_live_company(self, session: AsyncSession, company_id: str) -> None:
        """Lock the organization row and refuse a soft-deleted one (#15907).

        The company delete takes the same lock (``CompanyService._get_or_404(for_update=True)``)
        before it switches heartbeats off, so an enable either commits first (and the delete then
        switches it off) or sees the delete as a ``CompanyNotFoundError``.
        """
        await CompanyService(session).get_live_for_update(uuid.UUID(company_id))

    async def _get_heartbeat_row(self, session: AsyncSession, company_id: str, agent_id: str) -> Optional[dict]:
        result = await session.execute(
            select(
                AgentOrgNode.status, AgentOrgNode.heartbeat_enabled, AgentOrgNode.heartbeat_cron, AgentOrgNode.id
            ).where(*_agent_in_company(company_id, agent_id))
        )
        row = result.first()
        return (
            {"status": row[0], "heartbeat_enabled": bool(row[1]), "heartbeat_cron": row[2], "id": row[3]}
            if row
            else None
        )
