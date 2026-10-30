# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflow Planner plan API (#19934).

Route group: /llc/company-os/workflow-plans, behind the master switch
``AUTOBOT_FEATURE_COMPANY_OS_WORKFLOW_PLANNER`` (default off: every route is a 404).

Same tenancy and error rules as ``company_os.py``: the company comes from the org context
only, writes need company owner/admin (a step's metric also accepts a member holding that
lane's role), and another company's id is a 404. Status is computed by the server on every
write; no body can carry one. Evidence import and re-planning are not here (#19935, #19937). The approval policies, the
conversion preview, its approval and the conversion itself are (#19936); every one of them
needs company owner/admin.
"""

from __future__ import annotations

from typing import Any, Awaitable, List, Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from api.user_management.human_decider import require_interactive_human
from autobot_shared.feature_flags import is_feature_enabled
from llc.deps import get_session
from llc.services.authz import NotAuthorisedError
from llc.services.company_os.errors import CompanyOsError, ConversionBlocked
from llc.services.company_os.plan_convert import PlanConversionService
from llc.services.company_os.plan_gate import map_warnings
from llc.services.company_os.plan_types import (
    CompanyWorkflowPlan,
    EdgeCase,
    PlanConversion,
    SubStep,
    WorkflowPlanStatus,
)
from llc.services.company_os.plans import CompanyOsPlanService
from user_management.services import TenantContext

from ._common import actor_id
from .company_os import http_error
from .company_os_plan_schemas import (
    ApprovalPoliciesBody,
    BreakdownBody,
    GateItem,
    GateResponse,
    HandoffPatch,
    MapBody,
    MapResponse,
    MetricBody,
    OneNumberBody,
    PlanCreate,
    PlanSummary,
    PlanUpdate,
    SubStepPatch,
)
from .company_os_schemas import GraphValidation

T = TypeVar("T")
FLAG = "company_os_workflow_planner"


def require_planner_enabled() -> None:
    if not is_feature_enabled(FLAG):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(
    prefix="/company-os/workflow-plans",
    tags=["llc-company-os-workflow-plans"],
    dependencies=[Depends(require_planner_enabled)],
)
_plans = CompanyOsPlanService()
_conversion = PlanConversionService()


def _gate_error(exc: Exception) -> HTTPException:
    """409 with ``{missing:[{gate, message, step}]}`` while a gate is open (FR-6.3); else the usual mapping."""
    if isinstance(exc, ConversionBlocked):
        items = [GateItem(gate=m.gate, message=m.message, step=m.step).model_dump() for m in exc.missing]
        return HTTPException(status.HTTP_409_CONFLICT, detail={"missing": items})
    return http_error(exc)


async def _write(session: AsyncSession, call: Awaitable[T]) -> T:
    """Run a service write, map its errors, commit. A refused write leaves nothing behind."""
    try:
        result = await call
    except (CompanyOsError, NotAuthorisedError) as exc:
        await session.rollback()
        raise _gate_error(exc) from exc
    await session.commit()
    return result


async def _read(call: Awaitable[T]) -> T:
    try:
        return await call
    except CompanyOsError as exc:
        raise http_error(exc) from exc


@router.get("", response_model=List[PlanSummary])
async def list_plans(
    status_filter: Optional[WorkflowPlanStatus] = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[PlanSummary]:
    rows = await _plans.list(session, ctx.org_id, status_filter)
    return [PlanSummary.model_validate(r) for r in rows]


@router.post("", response_model=CompanyWorkflowPlan, status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: PlanCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    fields = body.model_dump(exclude={"lanes", "steps", "edges"})
    call = _plans.create(
        session, ctx.org_id, actor=actor_id(user), lanes=body.lanes, steps=body.steps, edges=body.edges, **fields
    )
    return await _write(session, call)


@router.get("/{plan_key}", response_model=CompanyWorkflowPlan)
async def get_plan(
    plan_key: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    return await _read(_plans.get(session, ctx.org_id, plan_key))


@router.patch("/{plan_key}", response_model=CompanyWorkflowPlan)
async def update_plan(
    plan_key: str,
    body: PlanUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    call = _plans.update_meta(
        session, ctx.org_id, plan_key, actor=actor_id(user), **body.model_dump(exclude_unset=True)
    )
    return await _write(session, call)


@router.delete("/{plan_key}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_plan(
    plan_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    await _write(session, _plans.delete(session, ctx.org_id, plan_key, actor=actor_id(user)))


@router.get("/{plan_key}/revisions/{revision}", response_model=CompanyWorkflowPlan)
async def get_revision(
    plan_key: str,
    revision: int,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    return await _read(_plans.get(session, ctx.org_id, plan_key, revision))


@router.get("/{plan_key}/gate", response_model=GateResponse)
async def get_gate(
    plan_key: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> GateResponse:
    report = await _read(_plans.gate_report(session, ctx.org_id, plan_key))
    items = [GateItem(gate=m.gate, message=m.message, step=m.step) for m in report.missing]
    return GateResponse(status=report.status, next_status=report.next_status, missing=items)


@router.put("/{plan_key}/map", response_model=MapResponse)
async def put_map(
    plan_key: str,
    body: MapBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> MapResponse:
    call = _plans.replace_map(
        session, ctx.org_id, plan_key, actor=actor_id(user), lanes=body.lanes, steps=body.steps, edges=body.edges
    )
    plan = await _write(session, call)
    warnings = map_warnings(plan.steps, plan.edges)
    return MapResponse(plan=plan, validation=GraphValidation(errors=[], warnings=warnings))


@router.post("/{plan_key}/map/validate", response_model=GraphValidation)
async def validate_map(
    plan_key: str,
    body: MapBody,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> GraphValidation:
    await _read(_plans.get(session, ctx.org_id, plan_key))
    errors, warnings = await _read(_plans.validate_map(session, ctx.org_id, body.lanes, body.steps, body.edges))
    return GraphValidation(errors=errors, warnings=warnings)


@router.patch("/{plan_key}/handoffs/{handoff_key}", response_model=CompanyWorkflowPlan)
async def patch_handoff(
    plan_key: str,
    handoff_key: str,
    body: HandoffPatch,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    call = _plans.set_wait_note(session, ctx.org_id, plan_key, handoff_key, body.wait_note, actor=actor_id(user))
    return await _write(session, call)


@router.put("/{plan_key}/steps/{step_key}/metric", response_model=CompanyWorkflowPlan)
async def put_metric(
    plan_key: str,
    step_key: str,
    body: MetricBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    call = _plans.put_metric(
        session,
        ctx.org_id,
        plan_key,
        step_key,
        actor=actor_id(user),
        frequency=(body.frequency.value, body.frequency.unit),
        duration=(body.duration.value, body.duration.unit),
    )
    return await _write(session, call)


@router.delete("/{plan_key}/steps/{step_key}/metric", response_model=CompanyWorkflowPlan)
async def delete_metric(
    plan_key: str,
    step_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    return await _write(session, _plans.delete_metric(session, ctx.org_id, plan_key, step_key, actor=actor_id(user)))


@router.put("/{plan_key}/one-number", response_model=CompanyWorkflowPlan)
async def put_one_number(
    plan_key: str,
    body: OneNumberBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    call = _plans.put_one_number(session, ctx.org_id, plan_key, actor=actor_id(user), **body.model_dump())
    return await _write(session, call)


@router.put("/{plan_key}/steps/{step_key}/breakdown", response_model=CompanyWorkflowPlan)
async def put_breakdown(
    plan_key: str,
    step_key: str,
    body: BreakdownBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    sub_steps = [SubStep(step_key=step_key, lane_key="", **s.model_dump()) for s in body.sub_steps]
    edge_cases = [EdgeCase(step_key=step_key, **c.model_dump()) for c in body.edge_cases]
    call = _plans.put_breakdown(
        session, ctx.org_id, plan_key, step_key, actor=actor_id(user), sub_steps=sub_steps, edge_cases=edge_cases
    )
    return await _write(session, call)


@router.patch("/{plan_key}/sub-steps/{sub_step_key}", response_model=CompanyWorkflowPlan)
async def patch_sub_step(
    plan_key: str,
    sub_step_key: str,
    body: SubStepPatch,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    fields: dict[str, Any] = body.model_dump(exclude_unset=True)
    call = _plans.patch_sub_step(session, ctx.org_id, plan_key, sub_step_key, actor=actor_id(user), **fields)
    return await _write(session, call)


@router.post("/{plan_key}/by-hand-acknowledgement", response_model=CompanyWorkflowPlan)
async def acknowledge_by_hand(
    plan_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    return await _write(session, _plans.acknowledge_by_hand(session, ctx.org_id, plan_key, actor=actor_id(user)))


@router.put("/{plan_key}/approval-policies", response_model=CompanyWorkflowPlan)
async def put_approval_policies(
    plan_key: str,
    body: ApprovalPoliciesBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    call = _plans.put_approval_policies(session, ctx.org_id, plan_key, actor=actor_id(user), policies=body.policies)
    return await _write(session, call)


@router.post("/{plan_key}/convert/preview", response_model=PlanConversion)
async def preview_conversion(
    plan_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> PlanConversion:
    """Build the rows a conversion would create and run the graph validator over each; writes only the preview."""
    return await _write(session, _conversion.preview(session, ctx.org_id, plan_key, actor=actor_id(user)))


@router.post("/{plan_key}/approve", response_model=CompanyWorkflowPlan)
async def approve_conversion(
    plan_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    """G7: an owner or admin approves the stored preview. Any later edit clears it. A person, not an agent."""
    require_interactive_human(user, "workflow plan approval")
    return await _write(session, _conversion.approve(session, ctx.org_id, plan_key, actor=actor_id(user)))


@router.post("/{plan_key}/convert", response_model=CompanyWorkflowPlan)
async def convert_plan(
    plan_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    """Create the processes, workflows and graphs in one transaction. 409 with the unmet gates until G1-G7 pass.

    Filing AI-line proposals is what an interactive person may do (as ``POST /ai-lines/{id}/changes``), so a
    run or service credential is refused.
    """
    require_interactive_human(user, "workflow plan conversion")
    return await _write(session, _conversion.convert(session, ctx.org_id, plan_key, actor=actor_id(user)))


@router.post("/{plan_key}/convert/retry-ai-line-proposals", response_model=CompanyWorkflowPlan)
async def retry_ai_line_proposals(
    plan_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowPlan:
    """File the AI-line proposals that failed or were never filed. The only write a converted plan accepts."""
    require_interactive_human(user, "workflow plan AI-line proposals")
    return await _write(
        session, _conversion.retry_ai_line_proposals(session, ctx.org_id, plan_key, actor=actor_id(user))
    )
