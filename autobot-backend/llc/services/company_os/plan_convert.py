# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Preview, approve and convert a Workflow Plan into Company OS rows (#19936, FR-6).

Creation goes only through ``ProcessService``, ``CompanyOsWorkflowService`` and ``GraphService``, on the
caller's one session, so a failure anywhere leaves no row and the plan unconverted: the route commits
once at the end and rolls back on any error. AI-line changes are only PROPOSED, through the function the
``POST /llc/ai-lines/{company_id}/changes`` route calls; nothing here writes ``llc_ai_lines``.

Those proposals are the one step outside the transaction: they file an approval in the approvals store's own
session, so they run last, after every row is flushed. A proposal is idempotent (a pending identical
one is reused), so a failure after them and a retry files nothing twice.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.ai_lines import SCOPE_COMPANY, AiLine, LineScope
from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from constants.ttl_constants import TTL_24_HOURS
from llc.models.company_os import LLCProcess
from llc.models.company_os_plan import CompanyOsWorkflowPlan as PlanRow
from llc.models.enums import RoleHolderType
from llc.models.role_assignment import LLCRoleAssignment
from llc.services._role_guard import role_exists_in_company
from llc.services.authz import require_company_admin
from llc.services.base import LLCServiceBase
from models.workflow import Workflow
from services.ai_line_change_proposal import propose_line_change

from . import plan_store
from .errors import ConversionBlocked
from .graph_types import GraphContext, GraphSpec, HandoffTarget
from .graph_validation import validate_graph
from .graphs import GraphService
from .plan_convert_build import ConversionFacts, build_conversion
from .plan_gate import Missing, evaluate_plan_gate
from .plan_types import CompanyWorkflowPlan, ConversionStatus, PlanConversion, WorkflowPlanStatus
from .processes import ProcessService
from .role_skills import RoleSkillService
from .workflows import CompanyOsWorkflowService

logger = get_logger(__name__)

#: How long an approval waits before its timeout transition fires, for a policy with ``wait_limit``.
APPROVAL_WAIT_SECONDS = env_int("AUTOBOT_COMPANY_OS_WORKFLOW_PLANNER_APPROVAL_WAIT_SECONDS", TTL_24_HOURS)
_PERSON_HOLDERS = (RoleHolderType.USER.value, RoleHolderType.CONTACT.value)
_PREVIEW_ONLY = {"status", "converted_at", "converted_by", "turn_on", "turn_on_tracking_issue"}
_AT_LEAST_LABELED = (WorkflowPlanStatus.LABELED, WorkflowPlanStatus.APPROVED)


def _same_preview(a: Optional[PlanConversion], b: Optional[PlanConversion]) -> bool:
    if a is None or b is None:
        return a is b
    return a.model_dump(exclude=_PREVIEW_ONLY) == b.model_dump(exclude=_PREVIEW_ONLY)


def _blocked_g6(message: str, plan: CompanyWorkflowPlan) -> ConversionBlocked:
    return ConversionBlocked([Missing("G6", message, plan.one_number.step_key if plan.one_number else None)])


class PlanConversionService(LLCServiceBase):
    def __init__(self, activity_log=None) -> None:  # noqa: ANN001
        super().__init__(activity_log)
        self._processes = ProcessService(activity_log)
        self._workflows = CompanyOsWorkflowService(activity_log)
        self._graphs = GraphService(activity_log)

    async def _locked(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, actor: Optional[uuid.UUID]
    ) -> Tuple[PlanRow, CompanyWorkflowPlan]:
        await require_company_admin(session, company_id, actor)
        row = await plan_store.load_writable(session, company_id, plan_key)
        return row, plan_store.read_plan(row)

    # ------------------------------------------------------------ the facts and the preview

    async def _facts(self, session: AsyncSession, company_id: uuid.UUID, plan: CompanyWorkflowPlan) -> ConversionFacts:
        role_ids = {ln.role_id for ln in plan.lanes if ln.role_id is not None}
        known = frozenset([r for r in role_ids if await role_exists_in_company(session, company_id, r)])
        held = await session.execute(
            select(LLCRoleAssignment.role_id).where(
                LLCRoleAssignment.company_id == company_id,
                LLCRoleAssignment.role_id.in_(role_ids),
                LLCRoleAssignment.holder_type.in_(_PERSON_HOLDERS),
                LLCRoleAssignment.ended_at.is_(None),
            )
        )
        prefix = f"{plan.key}."
        procs = await session.execute(
            select(LLCProcess.process_key).where(
                LLCProcess.company_id == company_id, LLCProcess.process_key.startswith(prefix, autoescape=True)
            )
        )
        wfs = await session.execute(
            select(Workflow.workflow_id).where(
                Workflow.company_id == company_id, Workflow.workflow_id.startswith(prefix, autoescape=True)
            )
        )
        return ConversionFacts(
            known,
            frozenset(held.scalars()),
            frozenset(procs.scalars()),
            frozenset(wfs.scalars()),
            APPROVAL_WAIT_SECONDS,
        )

    async def _validate(
        self, session: AsyncSession, company_id: uuid.UUID, plan: CompanyWorkflowPlan, conv: PlanConversion
    ) -> None:
        """Run the existing graph validator over every drafted workflow; its strings are kept unchanged."""
        role_of = {ln.key: ln.role_id for ln in plan.lanes}
        targets = {w.workflow_id: HandoffTarget("workflow", role_of.get(w.owner_lane_key)) for w in conv.workflows}
        procs = {p.process_key: list(p.required_skills) for p in conv.processes}
        for w in conv.workflows:
            role = role_of.get(w.owner_lane_key)
            held = await RoleSkillService().held_skill_names(session, company_id, role) if role else frozenset()
            ctx = GraphContext(w.workflow_id, role, processes=procs, handoff_targets=targets, held_skills=held)
            report = validate_graph(GraphSpec(nodes=w.nodes, transitions=w.transitions), ctx)
            conv.preview_errors += report.errors
            conv.preview_warnings += report.warnings

    async def build_preview(
        self, session: AsyncSession, company_id: uuid.UUID, plan: CompanyWorkflowPlan
    ) -> PlanConversion:
        conv = build_conversion(plan, await self._facts(session, company_id, plan))
        if not conv.contract_errors:
            await self._validate(session, company_id, plan, conv)
        return conv

    def _require_labeled(self, plan: CompanyWorkflowPlan) -> None:
        report = evaluate_plan_gate(plan)
        if report.status not in _AT_LEAST_LABELED:
            raise ConversionBlocked(report.missing)

    # ------------------------------------------------------------ the three actions

    async def preview(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, *, actor: Optional[uuid.UUID]
    ) -> PlanConversion:
        """Build and store the preview. A preview that differs from the stored one drops an approval."""
        row, plan = await self._locked(session, company_id, plan_key, actor)
        self._require_labeled(plan)
        conv = await self.build_preview(session, company_id, plan)
        if not _same_preview(conv, plan.conversion):
            plan.approved_at, plan.approved_by = None, None
        plan.conversion = conv
        saved = await plan_store.save_plan(session, row, plan, actor=actor, clears_approval=False)
        return saved.conversion  # type: ignore[return-value]

    async def approve(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, *, actor: Optional[uuid.UUID]
    ) -> CompanyWorkflowPlan:
        """G7: an owner or admin approves THIS preview. A preview the database has outgrown is refused."""
        row, plan = await self._locked(session, company_id, plan_key, actor)
        self._require_labeled(plan)
        if plan.conversion is None:
            raise _blocked_g6("no conversion preview exists yet: request one", plan)
        if not _same_preview(await self.build_preview(session, company_id, plan), plan.conversion):
            raise _blocked_g6("the preview is out of date: request a new one", plan)
        plan.approved_at, plan.approved_by = datetime.now(timezone.utc), actor
        report = evaluate_plan_gate(plan)
        if report.status is not WorkflowPlanStatus.APPROVED:
            raise ConversionBlocked(report.missing)
        return await plan_store.save_plan(session, row, plan, actor=actor, clears_approval=False)

    async def convert(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, *, actor: Optional[uuid.UUID]
    ) -> CompanyWorkflowPlan:
        """Create the rows. Raises :class:`ConversionBlocked` before any write when a gate is open."""
        row, plan = await self._locked(session, company_id, plan_key, actor)
        report = evaluate_plan_gate(plan)
        if report.status is not WorkflowPlanStatus.APPROVED:
            raise ConversionBlocked(report.missing)
        fresh = await self.build_preview(session, company_id, plan)
        if fresh.contract_errors or fresh.preview_errors or not _same_preview(fresh, plan.conversion):
            raise _blocked_g6(
                "the approved preview no longer matches this company: request and approve a new one", plan
            )
        try:
            await self._create_rows(session, company_id, plan, fresh, actor)
            await self._propose_lines(company_id, plan, fresh, actor)
            fresh.status, fresh.converted_at, fresh.converted_by = (
                ConversionStatus.COMMITTED,
                datetime.now(timezone.utc),
                actor,
            )
            plan.conversion = fresh
            return await plan_store.save_plan(session, row, plan, actor=actor, clears_approval=False)
        except Exception:
            await session.rollback()
            raise

    # ------------------------------------------------------------ the writes

    async def _create_rows(
        self, session: AsyncSession, company_id: uuid.UUID, plan: CompanyWorkflowPlan, conv: PlanConversion, actor
    ) -> None:  # noqa: ANN001
        role_of = {ln.key: ln.role_id for ln in plan.lanes}
        for p in conv.processes:
            await self._processes.create(
                session,
                company_id,
                process_key=p.process_key,
                name=p.name,
                owner_role_id=role_of[p.owner_lane_key],
                actor=actor,
                required_skills=p.required_skills,
            )
        drafts = {w.workflow_id: w for w in conv.workflows}
        for wid in conv.creation_order:
            w = drafts[wid]
            await self._workflows.create(
                session,
                company_id,
                workflow_id=wid,
                actor=actor,
                name=w.name,
                owner_role_id=role_of[w.owner_lane_key],
                trigger_type=w.trigger_type,
                trigger_config=w.trigger_config,
            )
        for wid in conv.creation_order:
            spec = GraphSpec(nodes=drafts[wid].nodes, transitions=drafts[wid].transitions)
            await self._graphs.replace(session, company_id, wid, spec, actor=actor)

    async def _propose_lines(
        self, company_id: uuid.UUID, plan: CompanyWorkflowPlan, conv: PlanConversion, actor: Optional[uuid.UUID]
    ) -> None:
        for prop in conv.ai_line_proposals:
            await propose_line_change(
                scope=LineScope(SCOPE_COMPANY, company_id),
                key=prop.tool_action,
                line=AiLine(prop.line),
                requested_by=str(actor),
                reason=f"Workflow plan {plan.key!r}, sub-step {prop.sub_step_key!r}",
            )
            logger.info(
                "workflow_plan.ai_line_proposed plan=%s action=%s line=%s", plan.key, prop.tool_action, prop.line
            )
