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
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client

from ..models.enums import ActivityEventType, LLCAgentStatus
from .activity_log import LLCActivityLogService

logger = logging.getLogger(__name__)

_COMPANY_PAUSED_KEY = "llc:company:{company_id}:paused"
_AGENT_PAUSED_KEY = "llc:agent:{agent_id}:paused"


class AgentNotFoundError(Exception):
    pass


class SprintNotFoundError(Exception):
    pass


class CompanyNotFoundError(Exception):
    pass


class ControlsService:
    """Board instant controls — FR-GOV-05.

    All methods are synchronous from the caller's perspective: the state change
    is committed before the method returns. Redis flags are best-effort (failures
    are logged, not raised) because the DB state is authoritative.
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
        actor_user_id: str,
        reason: Optional[str] = None,
    ) -> dict:
        """Set agent status=paused and set Redis pause flag."""
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

        await self._set_redis_flag(_AGENT_PAUSED_KEY.format(agent_id=agent_id), "1")

        await self._activity_log.record(
            session=session,
            company_id=company_id,
            actor_type="user",
            actor_id=actor_user_id,
            event_type=ActivityEventType.CONTROL_AGENT_PAUSED,
            entity_type="agent",
            entity_id=agent_id,
            before={"status": before_status},
            after={"status": LLCAgentStatus.PAUSED.value, "pause_reason": reason},
        )

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

        await self._del_redis_flag(_AGENT_PAUSED_KEY.format(agent_id=agent_id))

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

        # Terminated agents also get the Redis pause flag so heartbeat skips them
        await self._set_redis_flag(_AGENT_PAUSED_KEY.format(agent_id=agent_id), "terminated")

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

        return {"agent_id": agent_id, "status": LLCAgentStatus.TERMINATED.value}

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
        await self._set_redis_flag(_COMPANY_PAUSED_KEY.format(company_id=company_id), reason or "1")

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
        await self._del_redis_flag(_COMPANY_PAUSED_KEY.format(company_id=company_id))

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

    async def _get_company_row(self, session: AsyncSession, company_id: str) -> Optional[dict]:
        result = await session.execute(
            text("SELECT id FROM llc_companies WHERE id = :id LIMIT 1"),
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
        """Agent IDs with in_progress work items in this sprint."""
        result = await session.execute(
            text(
                "SELECT DISTINCT assignee_agent_id FROM llc_work_items"
                " WHERE sprint_id = :sprint_id AND company_id = :company_id"
                "  AND status = 'in_progress' AND assignee_agent_id IS NOT NULL"
            ),
            {"sprint_id": sprint_id, "company_id": company_id},
        )
        return [str(row[0]) for row in result.fetchall()]

    async def _paused_agents_in_sprint(self, session: AsyncSession, company_id: str, sprint_id: str) -> list:
        """Agent IDs paused due to this sprint."""
        result = await session.execute(
            text(
                "SELECT DISTINCT wi.assignee_agent_id FROM llc_work_items wi"
                " JOIN agent_org_nodes a ON a.agent_id = wi.assignee_agent_id"
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
