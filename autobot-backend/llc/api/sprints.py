# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC sprint hierarchy API routes (GH#8219, GH#8224, GH#8220).

Routes:
  GET  /llc/companies/{company_id}/portfolios   — list portfolios
  POST /llc/companies/{company_id}/portfolios   — create portfolio
  GET  /llc/portfolios/{id}                     — get portfolio
  PATCH/DELETE /llc/portfolios/{id}

  GET  /llc/portfolios/{portfolio_id}/programs  — list programs
  POST /llc/portfolios/{portfolio_id}/programs  — create program
  GET/PATCH/DELETE /llc/programs/{id}

  GET  /llc/programs/{program_id}/projects      — list projects
  POST /llc/programs/{program_id}/projects      — create project
  GET/PATCH/DELETE /llc/projects/{id}

  GET  /llc/projects/{project_id}/sprints       — list sprints
  POST /llc/projects/{project_id}/sprints       — create sprint
  GET/PATCH/DELETE /llc/sprints/{id}

  POST /llc/sprints/{id}/close                  — manual close trigger (board only)

  Sprint planning analytics (GH#8220):
  GET /llc/sprints/{sprint_id}/capacity         — assigned story-point totals
  GET /llc/projects/{project_id}/velocity       — velocity history for N closed sprints
  GET /llc/sprints/{sprint_id}/burndown         — day-by-day burndown series
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.logging_manager import get_logger
from llc.deps import get_session
from user_management.services import TenantContext

from ..kb.collections import KbCollectionManager
from ..models.enums import SprintStatus, WorkItemRelationType
from ..models.sprint import LLCPortfolio, LLCProgram, LLCProject, LLCSprint
from ..models.work_item import LLCWorkItem, LLCWorkItemRelation
from ..services.approval import ApprovalNotFoundError, ApprovalService, ApprovalStateError
from ..services.sprint_autoclose import SprintAutoCloseService
from ..services.sprint_planning import SprintNotFound, SprintPlanningService
from ..services.timeline import compute_critical_path, duration_days

logger = get_logger(__name__)
router = APIRouter(tags=["llc-sprints"])

_approval_svc = ApprovalService()
_autoclose_svc = SprintAutoCloseService(approval_service=_approval_svc)
_kb_manager = KbCollectionManager()


# ------------------------------------------------------------------ Schemas


class PortfolioCreate(BaseModel):
    company_id: uuid.UUID
    name: str
    description: Optional[str] = None


class PortfolioUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class PortfolioResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProgramCreate(BaseModel):
    company_id: uuid.UUID
    portfolio_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None


class ProgramUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    portfolio_id: Optional[uuid.UUID] = None


class ProgramResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    portfolio_id: Optional[uuid.UUID]
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectCreate(BaseModel):
    company_id: uuid.UUID
    program_id: Optional[uuid.UUID] = None
    goal_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    lead_agent_id: Optional[uuid.UUID] = None
    lead_user_id: Optional[uuid.UUID] = None
    target_date: Optional[date] = None
    env: Optional[dict] = None
    auto_rollover: Optional[bool] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    lead_agent_id: Optional[uuid.UUID] = None
    lead_user_id: Optional[uuid.UUID] = None
    target_date: Optional[date] = None
    env: Optional[dict] = None
    auto_rollover: Optional[bool] = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    program_id: Optional[uuid.UUID]
    goal_id: Optional[uuid.UUID]
    name: str
    description: Optional[str]
    status: str
    lead_agent_id: Optional[uuid.UUID]
    lead_user_id: Optional[uuid.UUID]
    target_date: Optional[date]
    auto_rollover: Optional[bool]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SprintCreate(BaseModel):
    company_id: uuid.UUID
    name: str
    goal_description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    committed_points: int = 0
    # GH#8474: sprint planning analytics fields
    capacity_points: Optional[int] = None


class SprintUpdate(BaseModel):
    name: Optional[str] = None
    goal_description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # status is intentionally absent: use POST /sprints/{id}/start or /close
    committed_points: Optional[int] = None
    # GH#8474: sprint planning analytics fields
    velocity_actual: Optional[float] = None
    capacity_points: Optional[int] = None


class SprintResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    goal_description: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    status: str
    committed_points: int
    actual_points: int
    velocity_actual: int = 0
    capacity_points: int = 0
    projection: Optional[float] = None
    pending_close_approval_id: Optional[uuid.UUID]
    kb_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SprintCloseRequest(BaseModel):
    approval_id: uuid.UUID
    decided_by: uuid.UUID


# ------------------------------------------------------------------ Portfolio routes


@router.get("/companies/{company_id}/portfolios", response_model=List[PortfolioResponse])
async def list_portfolios(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[LLCPortfolio]:
    # IDOR guard (#10148): reject callers accessing another company's portfolios.
    if str(company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Company not found")
    result = await session.execute(select(LLCPortfolio).where(LLCPortfolio.company_id == company_id))
    return list(result.scalars().all())


@router.post("/companies/{company_id}/portfolios", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(
    company_id: uuid.UUID,
    body: PortfolioCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCPortfolio:
    # IDOR guard (#10148): reject callers creating portfolios in another company.
    if str(company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Company not found")
    portfolio = LLCPortfolio(company_id=company_id, name=body.name, description=body.description)
    session.add(portfolio)
    await session.commit()
    await session.refresh(portfolio)
    return portfolio


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCPortfolio:
    result = await session.execute(select(LLCPortfolio).where(LLCPortfolio.id == portfolio_id))
    portfolio = result.scalar_one_or_none()
    # IDOR guard (#10148): 404 on missing OR cross-tenant to avoid existence disclosure.
    if portfolio is None or str(portfolio.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


@router.patch("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: uuid.UUID,
    body: PortfolioUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCPortfolio:
    result = await session.execute(select(LLCPortfolio).where(LLCPortfolio.id == portfolio_id))
    portfolio = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if portfolio is None or str(portfolio.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(portfolio, field, value)
    await session.commit()
    await session.refresh(portfolio)
    return portfolio


@router.delete("/portfolios/{portfolio_id}", status_code=204)
async def delete_portfolio(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    result = await session.execute(select(LLCPortfolio).where(LLCPortfolio.id == portfolio_id))
    portfolio = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if portfolio is None or str(portfolio.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    await session.delete(portfolio)
    await session.commit()


# ------------------------------------------------------------------ Program routes


@router.get("/portfolios/{portfolio_id}/programs", response_model=List[ProgramResponse])
async def list_programs(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[LLCProgram]:
    # IDOR guard (#10148): verify the portfolio belongs to the caller's org before listing.
    pf_row = (await session.execute(select(LLCPortfolio).where(LLCPortfolio.id == portfolio_id))).scalar_one_or_none()
    if pf_row is None or str(pf_row.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    result = await session.execute(select(LLCProgram).where(LLCProgram.portfolio_id == portfolio_id))
    return list(result.scalars().all())


@router.post("/portfolios/{portfolio_id}/programs", response_model=ProgramResponse, status_code=201)
async def create_program(
    portfolio_id: uuid.UUID,
    body: ProgramCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCProgram:
    # IDOR guard (#10148): verify the portfolio belongs to the caller's org before creating.
    pf_row = (await session.execute(select(LLCPortfolio).where(LLCPortfolio.id == portfolio_id))).scalar_one_or_none()
    if pf_row is None or str(pf_row.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    program = LLCProgram(
        company_id=body.company_id,
        portfolio_id=portfolio_id,
        name=body.name,
        description=body.description,
    )
    session.add(program)
    await session.commit()
    await session.refresh(program)
    return program


@router.get("/programs/{program_id}", response_model=ProgramResponse)
async def get_program(
    program_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCProgram:
    result = await session.execute(select(LLCProgram).where(LLCProgram.id == program_id))
    program = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if program is None or str(program.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Program not found")
    return program


@router.patch("/programs/{program_id}", response_model=ProgramResponse)
async def update_program(
    program_id: uuid.UUID,
    body: ProgramUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCProgram:
    result = await session.execute(select(LLCProgram).where(LLCProgram.id == program_id))
    program = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if program is None or str(program.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Program not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(program, field, value)
    await session.commit()
    await session.refresh(program)
    return program


@router.delete("/programs/{program_id}", status_code=204)
async def delete_program(
    program_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    result = await session.execute(select(LLCProgram).where(LLCProgram.id == program_id))
    program = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if program is None or str(program.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Program not found")
    await session.delete(program)
    await session.commit()


# ------------------------------------------------------------------ Project routes


@router.get("/programs/{program_id}/projects", response_model=List[ProjectResponse])
async def list_projects(
    program_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[LLCProject]:
    # IDOR guard (#10148): verify the program belongs to the caller's org before listing.
    prog = (await session.execute(select(LLCProgram).where(LLCProgram.id == program_id))).scalar_one_or_none()
    if prog is None or str(prog.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Program not found")
    result = await session.execute(select(LLCProject).where(LLCProject.program_id == program_id))
    return list(result.scalars().all())


@router.get("/companies/{company_id}/projects", response_model=List[ProjectResponse])
async def list_company_projects(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[LLCProject]:
    """Flat list of all projects in a company (GH#9020 — drives the timeline
    project picker; also reused by the project browser)."""
    # IDOR guard (#10148): reject callers accessing another company's projects.
    if str(company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Company not found")
    result = await session.execute(
        select(LLCProject).where(LLCProject.company_id == company_id).order_by(LLCProject.name)
    )
    return list(result.scalars().all())


@router.post("/programs/{program_id}/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    program_id: uuid.UUID,
    body: ProjectCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCProject:
    # IDOR guard (#10148): verify the program belongs to the caller's org before creating.
    prog = (await session.execute(select(LLCProgram).where(LLCProgram.id == program_id))).scalar_one_or_none()
    if prog is None or str(prog.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Program not found")
    project = LLCProject(
        company_id=body.company_id,
        program_id=program_id,
        goal_id=body.goal_id,
        name=body.name,
        description=body.description,
        lead_agent_id=body.lead_agent_id,
        lead_user_id=body.lead_user_id,
        target_date=body.target_date,
        env=body.env,
        auto_rollover=body.auto_rollover,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    await _kb_manager.ensure_collection(KbCollectionManager.PROJECT_PREFIX, project.id)
    return project


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCProject:
    result = await session.execute(select(LLCProject).where(LLCProject.id == project_id))
    project = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if project is None or str(project.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCProject:
    result = await session.execute(select(LLCProject).where(LLCProject.id == project_id))
    project = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if project is None or str(project.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    result = await session.execute(select(LLCProject).where(LLCProject.id == project_id))
    project = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if project is None or str(project.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Project not found")
    await session.delete(project)
    await session.commit()


# ------------------------------------------------------------------ Sprint routes


@router.get("/projects/{project_id}/sprints", response_model=List[SprintResponse])
async def list_sprints(
    project_id: uuid.UUID,
    status: Optional[SprintStatus] = Query(None),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[LLCSprint]:
    # IDOR guard (#10148): verify the project belongs to the caller's org before listing sprints.
    proj = (await session.execute(select(LLCProject).where(LLCProject.id == project_id))).scalar_one_or_none()
    if proj is None or str(proj.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Project not found")
    stmt = select(LLCSprint).where(LLCSprint.project_id == project_id)
    if status is not None:
        stmt = stmt.where(LLCSprint.status == status.value)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/projects/{project_id}/sprints", response_model=SprintResponse, status_code=201)
async def create_sprint(
    project_id: uuid.UUID,
    body: SprintCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCSprint:
    # IDOR guard (#10148): verify the project belongs to the caller's org before creating a sprint.
    proj = (await session.execute(select(LLCProject).where(LLCProject.id == project_id))).scalar_one_or_none()
    if proj is None or str(proj.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Project not found")
    sprint = LLCSprint(
        company_id=body.company_id,
        project_id=project_id,
        name=body.name,
        goal_description=body.goal_description,
        start_date=body.start_date,
        end_date=body.end_date,
        committed_points=body.committed_points,
        capacity_points=body.capacity_points,  # GH#8474
    )
    session.add(sprint)
    await session.commit()
    await session.refresh(sprint)
    await _kb_manager.ensure_collection(KbCollectionManager.SPRINT_PREFIX, sprint.id)
    return sprint


@router.get("/sprints/{sprint_id}", response_model=SprintResponse)
async def get_sprint(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCSprint:
    result = await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id))
    sprint = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if sprint is None or str(sprint.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Sprint not found")
    return sprint


_LIFECYCLE_STATUSES = frozenset([SprintStatus.ACTIVE, SprintStatus.CLOSED])


@router.patch("/sprints/{sprint_id}", response_model=SprintResponse)
async def update_sprint(
    sprint_id: uuid.UUID,
    body: SprintUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCSprint:
    result = await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id).with_for_update())
    sprint = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if sprint is None or str(sprint.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Sprint not found")
    if body.status is not None and body.status in _LIFECYCLE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Status '{body.status.value}' is managed by the sprint lifecycle. "
                "Use POST /sprints/{id}/close (with an approved SprintCloseRequest) instead."
            ),
        )
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(sprint, field, value if not hasattr(value, "value") else value.value)
    await session.commit()
    await session.refresh(sprint)
    return sprint


@router.delete("/sprints/{sprint_id}", status_code=204)
async def delete_sprint(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    result = await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id))
    sprint = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if sprint is None or str(sprint.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Sprint not found")
    await session.delete(sprint)
    await session.commit()


@router.post("/sprints/{sprint_id}/close", response_model=SprintResponse)
async def close_sprint(
    sprint_id: uuid.UUID,
    body: SprintCloseRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> LLCSprint:
    """Manual sprint close trigger — board only, requires an APPROVED approval.

    Flow:
      1. Caller must first request a SPRINT_CLOSE approval via ApprovalService
         (or let the scheduler do it automatically).
      2. Board approves the approval record.
      3. This endpoint is called with the approval_id to execute the close.
    """
    # IDOR guard (#10148): verify the sprint belongs to the caller's org before closing.
    _sprint_check = (await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id))).scalar_one_or_none()
    if _sprint_check is None or str(_sprint_check.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Sprint not found")
    try:
        sprint = await _autoclose_svc.execute_close(
            session,
            sprint_id=sprint_id,
            approval_id=body.approval_id,
            decided_by=body.decided_by,
        )
        await session.commit()
        await session.refresh(sprint)
        return sprint
    except (ApprovalNotFoundError, ApprovalStateError) as exc:
        raise HTTPException(status_code=422, detail="Internal server error") from exc
    except ValueError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Internal server error") from exc


# ------------------------------------------------------------------ Sprint planning analytics (GH#8220)

_planning_svc = SprintPlanningService()


@router.get("/sprints/{sprint_id}/capacity")
async def get_sprint_capacity(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> dict:
    """Return total and per-agent assigned story points for a sprint."""
    # IDOR guard (#10148).
    sprint = (await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id))).scalar_one_or_none()
    if sprint is None or str(sprint.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Sprint not found")
    try:
        return await _planning_svc.get_capacity(session, sprint_id)
    except SprintNotFound as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=404, detail="Internal server error") from exc


@router.get("/projects/{project_id}/velocity")
async def get_project_velocity(
    project_id: uuid.UUID,
    n_sprints: int = Query(default=5, ge=1, le=52, description="Number of closed sprints to include"),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> dict:
    """Return velocity history for the last N closed sprints in a project."""
    # IDOR guard (#10148).
    proj = (await session.execute(select(LLCProject).where(LLCProject.id == project_id))).scalar_one_or_none()
    if proj is None or str(proj.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return await _planning_svc.get_velocity_history(session, project_id, n_sprints)


class TimelineItem(BaseModel):
    id: uuid.UUID
    identifier: str
    title: str
    type: str
    status: str
    assignee_agent_id: Optional[uuid.UUID]
    assignee_user_id: Optional[uuid.UUID]
    scheduled_start: Optional[datetime]
    scheduled_end: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    on_critical_path: bool


class TimelineEdge(BaseModel):
    # ``from`` finishes before ``to`` starts (a blocked_by dependency).
    from_id: uuid.UUID
    to_id: uuid.UUID


class ProjectTimelineResponse(BaseModel):
    project_id: uuid.UUID
    items: List[TimelineItem]
    edges: List[TimelineEdge]


@router.get("/projects/{project_id}/timeline", response_model=ProjectTimelineResponse)
async def get_project_timeline(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ProjectTimelineResponse:
    """Return the project's work items with blocked-by dependency edges and
    critical-path flags for the Gantt/timeline view (GH#9020)."""
    project = (await session.execute(select(LLCProject).where(LLCProject.id == project_id))).scalar_one_or_none()
    # IDOR guard (#10148): 404 on missing OR cross-tenant to avoid existence disclosure.
    if project is None or str(project.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Project not found")

    items = list((await session.execute(select(LLCWorkItem).where(LLCWorkItem.project_id == project_id))).scalars())
    item_ids = {item.id for item in items}

    # Dependency edges among these items: blocked_by means source is blocked by
    # target, so target must finish before source — edge (target → source).
    relations = list(
        (
            await session.execute(
                select(LLCWorkItemRelation).where(
                    LLCWorkItemRelation.relation_type == WorkItemRelationType.BLOCKED_BY,
                    LLCWorkItemRelation.source_id.in_(item_ids or {uuid.uuid4()}),
                )
            )
        ).scalars()
    )
    edges = [
        (rel.target_id, rel.source_id) for rel in relations if rel.target_id in item_ids and rel.source_id in item_ids
    ]

    durations = {str(item.id): duration_days(item.scheduled_start, item.scheduled_end) for item in items}
    critical = compute_critical_path(durations, [(str(a), str(b)) for a, b in edges])

    return ProjectTimelineResponse(
        project_id=project_id,
        items=[
            TimelineItem(
                id=item.id,
                identifier=item.identifier,
                title=item.title,
                type=item.type,
                status=item.status,
                assignee_agent_id=item.assignee_agent_id,
                assignee_user_id=item.assignee_user_id,
                scheduled_start=item.scheduled_start,
                scheduled_end=item.scheduled_end,
                started_at=item.started_at,
                completed_at=item.completed_at,
                on_critical_path=str(item.id) in critical,
            )
            for item in items
        ],
        edges=[TimelineEdge(from_id=a, to_id=b) for a, b in edges],
    )


@router.get("/sprints/{sprint_id}/burndown")
async def get_sprint_burndown(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> dict:
    """Return day-by-day burndown series for a sprint."""
    # IDOR guard (#10148).
    sprint = (await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id))).scalar_one_or_none()
    if sprint is None or str(sprint.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Sprint not found")
    try:
        return await _planning_svc.get_burndown(session, sprint_id)
    except SprintNotFound as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=404, detail="Internal server error") from exc


@router.get("/projects/{project_id}/knowledge")
async def get_project_knowledge(
    project_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> dict:
    """Return recently indexed work product artifacts for a project (GH#8242).

    Queries the ``project:{project_id}`` ChromaDB collection — available
    once ArtifactIngestor has indexed at least one work product.
    """
    # IDOR guard (#10148): verify the project belongs to the caller's org before reading KB.
    proj = (await session.execute(select(LLCProject).where(LLCProject.id == project_id))).scalar_one_or_none()
    if proj is None or str(proj.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Project not found")
    from autobot_shared.singleton_factory import lazy_singleton

    from ..services.work_product_service import WorkProductService

    svc = lazy_singleton(WorkProductService)()
    artifacts = await svc.list_indexed_by_project(
        session=None,  # type: ignore[arg-type]  — no DB needed, reads ChromaDB directly
        project_id=str(project_id),
        limit=limit,
        offset=offset,
    )
    return {
        "project_id": str(project_id),
        "artifacts": artifacts,
        "total": len(artifacts),
    }


class SprintSummaryResponse(BaseModel):
    sprint_id: uuid.UUID
    sprint_name: str
    status: str
    kb_summary: Optional[str]


@router.get("/sprints/{sprint_id}/summary", response_model=SprintSummaryResponse)
async def get_sprint_summary(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> SprintSummaryResponse:
    """Return the LLM-generated KB summary for a closed sprint (GH#8238).

    The summary is populated when the sprint is closed; NULL until then.
    """
    result = await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id))
    sprint = result.scalar_one_or_none()
    # IDOR guard (#10148).
    if sprint is None or str(sprint.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Sprint not found")
    return SprintSummaryResponse(
        sprint_id=sprint.id,
        sprint_name=sprint.name,
        status=sprint.status,
        kb_summary=sprint.kb_summary,
    )
