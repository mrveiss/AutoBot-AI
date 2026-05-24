# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC Board instant controls API (GH#8256 — FR-GOV-05).

Routes (all under /llc/companies/{company_id}/controls):
  POST /agents/{agent_id}/pause       — immediately pause agent
  POST /agents/{agent_id}/resume      — re-enable agent heartbeat
  POST /agents/{agent_id}/terminate   — permanently terminate agent
  POST /sprints/{sprint_id}/pause     — pause all agents in sprint
  POST /sprints/{sprint_id}/resume    — resume all paused agents in sprint
  POST /pause-all                     — company-wide pause (Redis flag)
  POST /resume-all                    — lift company-wide pause

Authorization: board_member (MembershipRole.ADMIN/OWNER) or company_admin only.
These routes bypass the approval workflow entirely (FR-GOV-05).
"""

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user
from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session_factory

from ..models.enums import MembershipRole
from ..services.controls_service import (
    AgentNotFoundError,
    CompanyNotFoundError,
    ControlsService,
    SprintNotFoundError,
)
from ..services.membership_service import MembershipService

router = APIRouter(tags=["llc-controls"])

_get_controls = lazy_singleton(ControlsService)
_get_membership = lazy_singleton(MembershipService)

_ALLOWED_ROLES = {MembershipRole.OWNER, MembershipRole.ADMIN}


async def get_session() -> AsyncSession:
    factory = get_async_session_factory()
    async with factory() as session:
        yield session


def _controls_svc() -> ControlsService:
    return _get_controls()


def _membership_svc() -> MembershipService:
    return _get_membership()


async def _require_board_role(
    company_id: uuid.UUID,
    current_user: dict,
    membership_svc: MembershipService,
    session: AsyncSession,
) -> str:
    """Raise 403 if the user is not OWNER or ADMIN of the company.

    Returns actor_user_id for activity log.
    """
    user_id = current_user.get("id") or current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        members = await membership_svc.list_members(session, str(company_id))
        role = next(
            (m.role for m in members if str(m.user_id) == str(user_id)),
            None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Membership lookup failed: {exc}") from exc

    if role not in _ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only board members (owner/admin) can use instant controls",
        )
    return str(user_id)


# ------------------------------------------------------------------
# Request schemas
# ------------------------------------------------------------------


class PauseRequest(BaseModel):
    reason: Optional[str] = None


class TerminateRequest(BaseModel):
    reason: Optional[str] = None


# ------------------------------------------------------------------
# Agent control endpoints
# ------------------------------------------------------------------


@router.post("/companies/{company_id}/controls/agents/{agent_id}/pause")
async def pause_agent(
    company_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: PauseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    actor_id = await _require_board_role(company_id, current_user, _membership_svc(), session)
    try:
        result = await _controls_svc().pause_agent(
            session, str(company_id), str(agent_id), actor_id, reason=body.reason
        )
        await session.commit()
        return result
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


@router.post("/companies/{company_id}/controls/agents/{agent_id}/resume")
async def resume_agent(
    company_id: uuid.UUID,
    agent_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    actor_id = await _require_board_role(company_id, current_user, _membership_svc(), session)
    try:
        result = await _controls_svc().resume_agent(
            session, str(company_id), str(agent_id), actor_id
        )
        await session.commit()
        return result
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


@router.post("/companies/{company_id}/controls/agents/{agent_id}/terminate")
async def terminate_agent(
    company_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: TerminateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    actor_id = await _require_board_role(company_id, current_user, _membership_svc(), session)
    try:
        result = await _controls_svc().terminate_agent(
            session, str(company_id), str(agent_id), actor_id, reason=body.reason
        )
        await session.commit()
        return result
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


# ------------------------------------------------------------------
# Sprint control endpoints
# ------------------------------------------------------------------


@router.post("/companies/{company_id}/controls/sprints/{sprint_id}/pause")
async def pause_sprint(
    company_id: uuid.UUID,
    sprint_id: uuid.UUID,
    body: PauseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    actor_id = await _require_board_role(company_id, current_user, _membership_svc(), session)
    try:
        result = await _controls_svc().pause_sprint(
            session, str(company_id), str(sprint_id), actor_id, reason=body.reason
        )
        await session.commit()
        return result
    except SprintNotFoundError:
        raise HTTPException(status_code=404, detail=f"Sprint {sprint_id} not found")


@router.post("/companies/{company_id}/controls/sprints/{sprint_id}/resume")
async def resume_sprint(
    company_id: uuid.UUID,
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    actor_id = await _require_board_role(company_id, current_user, _membership_svc(), session)
    try:
        result = await _controls_svc().resume_sprint(
            session, str(company_id), str(sprint_id), actor_id
        )
        await session.commit()
        return result
    except SprintNotFoundError:
        raise HTTPException(status_code=404, detail=f"Sprint {sprint_id} not found")


# ------------------------------------------------------------------
# Company-wide controls
# ------------------------------------------------------------------


@router.post("/companies/{company_id}/controls/pause-all")
async def pause_all(
    company_id: uuid.UUID,
    body: PauseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    actor_id = await _require_board_role(company_id, current_user, _membership_svc(), session)
    result = await _controls_svc().pause_company(
        session, str(company_id), actor_id, reason=body.reason
    )
    await session.commit()
    return result


@router.post("/companies/{company_id}/controls/resume-all")
async def resume_all(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    actor_id = await _require_board_role(company_id, current_user, _membership_svc(), session)
    result = await _controls_svc().resume_company(session, str(company_id), actor_id)
    await session.commit()
    return result


__all__ = ["router"]
