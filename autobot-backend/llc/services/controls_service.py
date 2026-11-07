# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC Board instant controls service (GH#8256 — FR-GOV-05).

Provides synchronous pause/resume/terminate for agents, sprints, and company.
Every action is recorded in llc_activity_log and (where relevant) sets a
Redis flag that the heartbeat scheduler checks before firing.

Redis keys:
  llc:company:{company_id}:paused       — SETEX, TTL unlimited (DEL on resume)
  llc:agent:{agent_id}:paused           — SET, no TTL (DEL on resume/terminate)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import false, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client
from models.agent_org import AgentOrgNode

from ..models.enums import UNDISPATCHABLE_AGENT_STATUSES, ActivityEventType, LLCAgentStatus
from .activity_log import LLCActivityLogService
from .company import CompanyNotFoundError

logger = logging.getLogger(__name__)

_COMPANY_PAUSED_KEY = "llc:company:{company_id}:paused"
_AGENT_PAUSED_KEY = "llc:agent:{agent_id}:paused"


class AgentNotFoundError(Exception):
    pass


class SprintNotFoundError(Exception):
    pass


class AgentNotSchedulableError(Exception):
    """Enabling a heartbeat on an agent whose status means it must never run (#15907)."""

    def __init__(self, agent_id: str, status: str) -> None:
        super().__init__(f"Agent {agent_id} is {status}; its heartbeat cannot be enabled")
        self.status = status


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


class ControlsService:
    """Board instant controls — FR-GOV-05.

    All methods are synchronous from the caller's perspective: the state change
    is committed before the method returns. Redis flags are best-effort (failures
    are logged, not raised) because the DB state is authoritative.
    A flag follows the activity write, so a failed write leaves no flag behind (#20150).
    """

    def __init__(self, activity_log: Optional[LLCActivityLogService] = None) -> None:
        self._activity_log = activity_log or LLCActivityLogService()

    # ------------------------------------------------------------------
    # Agent controls
    # ------------------------------------------------------------------

    async def pause_agent(
        self,
        session: AsyncSession,
        company_id: str,
        agent_id: str,
        actor_user_id: Optional[str] = None,
        reason: Optional[str] = None,
        actor_type: str = "user",
    ) -> dict:
        """Set agent status=paused and set Redis pause flag.

        ``actor_type="system"`` (with ``actor_user_id=None``) records the pause
        as a system-initiated board event — used by the auto-pause on
        subscription-quota exhaustion (GH#10218).
        """
        row = await self._get_agent_row(session, company_id, agent_id)
        if row is None:
            raise AgentNotFoundError(agent_id)
        before_status = row["status"]

        await session.execute(
            text(
                "UPDATE agent_org_nodes"
                " SET status = :status, pause_reason = :reason, paused_at = :now,"
                " pre_pause_status = :before_status"
                " WHERE company_id = :company_id AND agent_id = :agent_id"
            ),
            {
                "status": LLCAgentStatus.PAUSED.value,
                "reason": reason,
                "now": datetime.now(tz=timezone.utc),
                "before_status": before_status,
                "company_id": company_id,
                "agent_id": agent_id,
            },
        )

        await self._activity_log.record(
            session=session,
            company_id=company_id,
            actor_type=actor_type,
            actor_id=actor_user_id,
            event_type=ActivityEventType.CONTROL_AGENT_PAUSED,
            entity_type="agent",
            entity_id=agent_id,
            before={"status": before_status},
            after={"status": LLCAgentStatus.PAUSED.value, "pause_reason": reason},
        )

        await self._set_redis_flag(_AGENT_PAUSED_KEY.format(agent_id=agent_id), "1")

        return {"agent_id": agent_id, "status": LLCAgentStatus.PAUSED.value, "pause_reason": reason}

    async def resume_agent(
        self,
        session: AsyncSession,
        company_id: str,
        agent_id: str,
        actor_user_id: str,
    ) -> dict:
        """Clear agent pause, re-enable heartbeat."""
        row = await self._get_agent_row(session, company_id, agent_id)
        if row is None:
            raise AgentNotFoundError(agent_id)
        before_status = row["status"]

        restore_status = (
            LLCAgentStatus(row["pre_pause_status"]).value
            if row.get("pre_pause_status")
            else LLCAgentStatus.AVAILABLE.value
        )

        await session.execute(
            text(
                "UPDATE agent_org_nodes"
                " SET status = :status, pause_reason = NULL, paused_at = NULL,"
                " pre_pause_status = NULL"
                " WHERE company_id = :company_id AND agent_id = :agent_id"
            ),
            {
                "status": restore_status,
                "company_id": company_id,
                "agent_id": agent_id,
            },
        )

        await self._activity_log.record(
            session=session,
            company_id=company_id,
            actor_type="user",
            actor_id=actor_user_id,
            event_type=ActivityEventType.CONTROL_AGENT_RESUMED,
            entity_type="agent",
            entity_id=agent_id,
            before={"status": before_status},
            after={"status": restore_status},
        )

        await self._del_redis_flag(_AGENT_PAUSED_KEY.format(agent_id=agent_id))

        return {"agent_id": agent_id, "status": restore_status}

    async def terminate_agent(
        self,
        session: AsyncSession,
        company_id: str,
        agent_id: str,
        actor_user_id: str,
        reason: Optional[str] = None,
    ) -> dict:
        """Set agent status=terminated — no recovery path."""
        row = await self._get_agent_row(session, company_id, agent_id)
        if row is None:
            raise AgentNotFoundError(agent_id)
        before_status = row["status"]

        await session.execute(
            text(
                "UPDATE agent_org_nodes SET status = :status, pause_reason = :reason,"
                " paused_at = :now"
                " WHERE company_id = :company_id AND agent_id = :agent_id"
            ),
            {
                "status": LLCAgentStatus.TERMINATED.value,
                "reason": reason,
                "now": datetime.now(tz=timezone.utc),
                "company_id": company_id,
                "agent_id": agent_id,
            },
        )

        await self._activity_log.record(
            session=session,
            company_id=company_id,
            actor_type="user",
            actor_id=actor_user_id,
            event_type=ActivityEventType.CONTROL_AGENT_TERMINATED,
            entity_type="agent",
            entity_id=agent_id,
            before={"status": before_status},
            after={"status": LLCAgentStatus.TERMINATED.value, "reason": reason},
        )

        # Terminated agents also get the Redis pause flag so heartbeat skips them
        await self._set_redis_flag(_AGENT_PAUSED_KEY.format(agent_id=agent_id), "terminated")

        return {"agent_id": agent_id, "status": LLCAgentStatus.TERMINATED.value}

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
        await self._activity_log.record(
            session=session,
            company_id=company_id,
            actor_type="user",
            actor_id=actor_user_id,
            event_type=ActivityEventType.CONTROL_AGENT_HEARTBEAT_SET,
            entity_type="agent",
            entity_id=agent_id,
            before={"heartbeat_enabled": row["heartbeat_enabled"], "heartbeat_cron": row["heartbeat_cron"]},
            after={"heartbeat_enabled": enabled, "heartbeat_cron": cron},
        )
        return {"agent_id": agent_id, "heartbeat_enabled": enabled, "heartbeat_cron": cron}

    # ------------------------------------------------------------------
    # Sprint controls
    # ------------------------------------------------------------------

    async def pause_sprint(
        self,
        session: AsyncSession,
        company_id: str,
        sprint_id: str,
        actor_user_id: str,
        reason: Optional[str] = None,
    ) -> dict:
        """Pause all agents with active work items in this sprint."""
        sprint = await self._get_sprint(session, company_id, sprint_id)
        if sprint is None:
            raise SprintNotFoundError(sprint_id)

        agent_ids = await self._agents_in_sprint(session, company_id, sprint_id)

        for agent_id in agent_ids:
            await self.pause_agent(
                session, company_id, str(agent_id), actor_user_id, reason=f"sprint_pause:{sprint_id}"
            )

        await self._activity_log.record(
            session=session,
            company_id=company_id,
            actor_type="user",
            actor_id=actor_user_id,
            event_type=ActivityEventType.CONTROL_SPRINT_PAUSED,
            entity_type="sprint",
            entity_id=sprint_id,
            after={"reason": reason, "agents_paused": len(agent_ids)},
        )

        return {"sprint_id": sprint_id, "agents_paused": len(agent_ids)}

    async def resume_sprint(
        self,
        session: AsyncSession,
        company_id: str,
        sprint_id: str,
        actor_user_id: str,
    ) -> dict:
        """Resume all agents paused due to this sprint's pause."""
        sprint = await self._get_sprint(session, company_id, sprint_id)
        if sprint is None:
            raise SprintNotFoundError(sprint_id)

        agent_ids = await self._paused_agents_in_sprint(session, company_id, sprint_id)

        for agent_id in agent_ids:
            await self.resume_agent(session, company_id, str(agent_id), actor_user_id)

        await self._activity_log.record(
            session=session,
            company_id=company_id,
            actor_type="user",
            actor_id=actor_user_id,
            event_type=ActivityEventType.CONTROL_SPRINT_RESUMED,
            entity_type="sprint",
            entity_id=sprint_id,
            after={"agents_resumed": len(agent_ids)},
        )

        return {"sprint_id": sprint_id, "agents_resumed": len(agent_ids)}

    # ------------------------------------------------------------------
    # Company-wide controls
    # ------------------------------------------------------------------

    async def pause_company(
        self,
        session: AsyncSession,
        company_id: str,
        actor_user_id: str,
        reason: Optional[str] = None,
    ) -> dict:
        """Set company-wide Redis pause flag — blocks all new heartbeat runs."""
        if await self._get_company_row(session, company_id) is None:
            raise CompanyNotFoundError(company_id)
        await self._activity_log.record(
            session=session,
            company_id=company_id,
            actor_type="user",
            actor_id=actor_user_id,
            event_type=ActivityEventType.CONTROL_COMPANY_PAUSED,
            entity_type="company",
            entity_id=company_id,
            after={"reason": reason},
        )

        await self._set_redis_flag(_COMPANY_PAUSED_KEY.format(company_id=company_id), reason or "1")

        return {"company_id": company_id, "paused": True}

    async def resume_company(
        self,
        session: AsyncSession,
        company_id: str,
        actor_user_id: str,
    ) -> dict:
        """Lift company-wide pause flag."""
        if await self._get_company_row(session, company_id) is None:
            raise CompanyNotFoundError(company_id)
        await self._activity_log.record(
            session=session,
            company_id=company_id,
            actor_type="user",
            actor_id=actor_user_id,
            event_type=ActivityEventType.CONTROL_COMPANY_RESUMED,
            entity_type="company",
            entity_id=company_id,
            after={"paused": False},
        )

        await self._del_redis_flag(_COMPANY_PAUSED_KEY.format(company_id=company_id))

        return {"company_id": company_id, "paused": False}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_agent_row(self, session: AsyncSession, company_id: str, agent_id: str) -> Optional[dict]:
        result = await session.execute(
            text(
                "SELECT status, pre_pause_status FROM agent_org_nodes"
                " WHERE company_id = :company_id AND agent_id = :agent_id LIMIT 1"
            ),
            {"company_id": company_id, "agent_id": agent_id},
        )
        row = result.fetchone()
        return {"status": row[0], "pre_pause_status": row[1]} if row else None

    async def _get_heartbeat_row(self, session: AsyncSession, company_id: str, agent_id: str) -> Optional[dict]:
        result = await session.execute(
            select(AgentOrgNode.status, AgentOrgNode.heartbeat_enabled, AgentOrgNode.heartbeat_cron).where(
                *_agent_in_company(company_id, agent_id)
            )
        )
        row = result.first()
        return {"status": row[0], "heartbeat_enabled": bool(row[1]), "heartbeat_cron": row[2]} if row else None

    async def _get_company_row(self, session: AsyncSession, company_id: str) -> Optional[dict]:
        result = await session.execute(
            # #11675: companies are Organization rows in `organizations`; the
            # legacy `llc_companies` table never existed.
            text("SELECT id FROM organizations WHERE id = :id LIMIT 1"),
            {"id": company_id},
        )
        row = result.fetchone()
        return {"id": str(row[0])} if row else None

    async def _get_sprint(self, session: AsyncSession, company_id: str, sprint_id: str) -> Optional[dict]:
        result = await session.execute(
            text("SELECT id FROM llc_sprints WHERE id = :id AND company_id = :cid LIMIT 1"),
            {"id": sprint_id, "cid": company_id},
        )
        row = result.fetchone()
        return {"id": str(row[0])} if row else None

    async def _agents_in_sprint(self, session: AsyncSession, company_id: str, sprint_id: str) -> list:
        """Agent slugs with in_progress work items in this sprint.

        ``llc_work_items.assignee_agent_id`` holds the AgentOrgNode UUID PK
        (#10032); resolve it to the ``agent_id`` slug that pause_agent keys on.
        """
        result = await session.execute(
            text(
                "SELECT DISTINCT a.agent_id FROM llc_work_items wi"
                " JOIN agent_org_nodes a ON a.id = wi.assignee_agent_id"
                "  AND a.company_id = wi.company_id"
                " WHERE wi.sprint_id = :sprint_id AND wi.company_id = :company_id"
                "  AND wi.status = 'in_progress' AND wi.assignee_agent_id IS NOT NULL"
            ),
            {"sprint_id": sprint_id, "company_id": company_id},
        )
        return [str(row[0]) for row in result.fetchall()]

    async def _paused_agents_in_sprint(self, session: AsyncSession, company_id: str, sprint_id: str) -> list:
        """Agent slugs paused due to this sprint.

        Join on the AgentOrgNode UUID PK (#10032: ``assignee_agent_id`` is the PK,
        NOT the ``agent_id`` slug) and return the slug that resume_agent keys on.
        """
        result = await session.execute(
            text(
                "SELECT DISTINCT a.agent_id FROM llc_work_items wi"
                " JOIN agent_org_nodes a ON a.id = wi.assignee_agent_id"
                "  AND a.company_id = wi.company_id"
                " WHERE wi.sprint_id = :sprint_id AND wi.company_id = :company_id"
                "  AND a.status = 'paused'"
                "  AND a.pause_reason LIKE :prefix"
                "  AND wi.assignee_agent_id IS NOT NULL"
            ),
            {
                "sprint_id": sprint_id,
                "company_id": company_id,
                "prefix": f"sprint_pause:{sprint_id}%",
            },
        )
        return [str(row[0]) for row in result.fetchall()]

    async def _set_redis_flag(self, key: str, value: str) -> None:
        try:
            redis = await get_async_redis_client()
            if redis is None:
                return
            await redis.set(key, value)
        except Exception:
            logger.exception("Failed to set Redis flag %s", key)

    async def _del_redis_flag(self, key: str) -> None:
        try:
            redis = await get_async_redis_client()
            if redis is None:
                return
            await redis.delete(key)
        except Exception:
            logger.exception("Failed to delete Redis flag %s", key)
