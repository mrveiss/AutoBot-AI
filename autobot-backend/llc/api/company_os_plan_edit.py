# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflow Planner: edit one lane, step, edge or edge case; rank One Number candidates (#20086, #20037).

Same route group, flag, tenancy and error rules as ``company_os_plans.py`` (its helpers are reused, not
copied), split out so that file stays under its size ceiling. Every write returns the whole plan, as the
other writes do: status and derived handoffs are recomputed on the server, so a client reads them back from
the response. A converted revision answers 409, and another company's plan, lane, step, edge, edge case or
role is a 404. Every write needs company owner/admin. An ``edge`` has no key: it is named by its two steps.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from llc.deps import get_session
from llc.services.company_os.plan_candidates import rank_candidates
from llc.services.company_os.plan_edit import PlanEditService
from llc.services.company_os.plan_types import CompanyWorkflowPlan, Edge, EdgeCase, Lane, ReturnKind, Step
from user_management.services import TenantContext

from ._common import actor_id
from .company_os_plan_schemas import (
    CandidateItem,
    CandidatesResponse,
    EdgeCaseBody,
    EdgeCasePatch,
    EdgePatch,
    LanePatch,
    StepPatch,
)
from .company_os_plans import _plans, _read, _write, require_planner_enabled

router = APIRouter(
    prefix="/company-os/workflow-plans",
    tags=["llc-company-os-workflow-plans"],
    dependencies=[Depends(require_planner_enabled)],
)
_edit = PlanEditService()


@router.post("/{plan_key}/lanes", response_model=CompanyWorkflowPlan, status_code=status.HTTP_201_CREATED)
async def add_lane(
    plan_key: str,
    body: Lane,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    return await _write(session, _edit.add_lane(session, ctx.org_id, plan_key, body, actor=actor_id(user)))


@router.patch("/{plan_key}/lanes/{lane_key}", response_model=CompanyWorkflowPlan)
async def patch_lane(
    plan_key: str,
    lane_key: str,
    body: LanePatch,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    fields = body.model_dump(exclude_unset=True)
    return await _write(
        session, _edit.patch_lane(session, ctx.org_id, plan_key, lane_key, fields, actor=actor_id(user))
    )


@router.delete("/{plan_key}/lanes/{lane_key}", response_model=CompanyWorkflowPlan)
async def delete_lane(
    plan_key: str,
    lane_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    return await _write(session, _edit.delete_lane(session, ctx.org_id, plan_key, lane_key, actor=actor_id(user)))


@router.post("/{plan_key}/steps", response_model=CompanyWorkflowPlan, status_code=status.HTTP_201_CREATED)
async def add_step(
    plan_key: str,
    body: Step,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    return await _write(session, _edit.add_step(session, ctx.org_id, plan_key, body, actor=actor_id(user)))


@router.patch("/{plan_key}/steps/{step_key}", response_model=CompanyWorkflowPlan)
async def patch_step(
    plan_key: str,
    step_key: str,
    body: StepPatch,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    fields = body.model_dump(exclude_unset=True)
    return await _write(
        session, _edit.patch_step(session, ctx.org_id, plan_key, step_key, fields, actor=actor_id(user))
    )


@router.delete("/{plan_key}/steps/{step_key}", response_model=CompanyWorkflowPlan)
async def delete_step(
    plan_key: str,
    step_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    """The step and every edge that touches it. The One Number's step is refused (409): change the One Number first."""
    return await _write(session, _edit.delete_step(session, ctx.org_id, plan_key, step_key, actor=actor_id(user)))


@router.post("/{plan_key}/edges", response_model=CompanyWorkflowPlan, status_code=status.HTTP_201_CREATED)
async def add_edge(
    plan_key: str,
    body: Edge,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    return await _write(session, _edit.add_edge(session, ctx.org_id, plan_key, body, actor=actor_id(user)))


@router.patch("/{plan_key}/edges/{from_step}/{to_step}", response_model=CompanyWorkflowPlan)
async def patch_edge(
    plan_key: str,
    from_step: str,
    to_step: str,
    body: EdgePatch,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    fields = body.model_dump(exclude_unset=True)
    call = _edit.patch_edge(session, ctx.org_id, plan_key, from_step, to_step, fields, actor=actor_id(user))
    return await _write(session, call)


@router.delete("/{plan_key}/edges/{from_step}/{to_step}", response_model=CompanyWorkflowPlan)
async def delete_edge(
    plan_key: str,
    from_step: str,
    to_step: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    call = _edit.delete_edge(session, ctx.org_id, plan_key, from_step, to_step, actor=actor_id(user))
    return await _write(session, call)


@router.post(
    "/{plan_key}/steps/{step_key}/edge-cases", response_model=CompanyWorkflowPlan, status_code=status.HTTP_201_CREATED
)
async def add_edge_case(
    plan_key: str,
    step_key: str,
    body: EdgeCaseBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    case = EdgeCase(step_key=step_key, **body.model_dump())
    return await _write(
        session, _edit.add_edge_case(session, ctx.org_id, plan_key, step_key, case, actor=actor_id(user))
    )


@router.patch("/{plan_key}/edge-cases/{edge_case_key}", response_model=CompanyWorkflowPlan)
async def patch_edge_case(
    plan_key: str,
    edge_case_key: str,
    body: EdgeCasePatch,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    fields = body.model_dump(exclude_unset=True)
    call = _edit.patch_edge_case(session, ctx.org_id, plan_key, edge_case_key, fields, actor=actor_id(user))
    return await _write(session, call)


@router.delete("/{plan_key}/edge-cases/{edge_case_key}", response_model=CompanyWorkflowPlan)
async def delete_edge_case(
    plan_key: str,
    edge_case_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    return await _write(
        session, _edit.delete_edge_case(session, ctx.org_id, plan_key, edge_case_key, actor=actor_id(user))
    )


@router.get("/{plan_key}/one-number/candidates", response_model=CandidatesResponse)
async def get_one_number_candidates(
    plan_key: str,
    return_kind: ReturnKind,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CandidatesResponse:
    """Steps ranked by frequency x duration for the owner's ``return_kind`` (FR-3.1). Reads only: sets no One Number."""
    found = rank_candidates(await _read(_plans.get(session, ctx.org_id, plan_key)), return_kind)
    items = [CandidateItem(**vars(c)) for c in found.ranked]
    return CandidatesResponse(return_kind=found.return_kind, candidates=items, unmeasured=found.unmeasured)
