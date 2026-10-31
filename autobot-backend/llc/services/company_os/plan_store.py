# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Load and save a plan revision, and own its status (#19934).

``save_plan`` is the only place a status is set: it runs ``evaluate_plan_gate`` over the document, writes the
result to both the document and the ``status`` column, and appends a ``StatusChange`` when it
moved. Every write path ends here, so no route can store a status the gate does not support.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from llc.models.company_os_plan import CompanyOsWorkflowPlan

from .errors import CompanyOsConflict, CompanyOsNotFound
from .plan_gate import GateReport, evaluate_plan_gate
from .plan_types import CompanyWorkflowPlan, ConversionStatus, StatusChange, WorkflowPlanStatus

logger = get_logger(__name__)

STATUS_CHANGED_EVENT = "workflow_plan.status_changed"
FROZEN_MESSAGE = "this revision is converted and read-only: start a new revision"


def _scope(company_id: uuid.UUID, plan_key: str):
    return select(CompanyOsWorkflowPlan).where(
        CompanyOsWorkflowPlan.company_id == company_id, CompanyOsWorkflowPlan.plan_key == plan_key
    )


async def load_row(
    session: AsyncSession, company_id: uuid.UUID, plan_key: str, revision: Optional[int] = None, *, lock: bool = False
) -> CompanyOsWorkflowPlan:
    """The given revision, or the latest one. Another company's plan is a 404, like a missing one."""
    stmt = _scope(company_id, plan_key)
    stmt = stmt.where(CompanyOsWorkflowPlan.revision == revision) if revision is not None else stmt
    stmt = stmt.order_by(CompanyOsWorkflowPlan.revision.desc()).limit(1)
    row = (await session.execute(stmt.with_for_update() if lock else stmt)).scalar_one_or_none()
    if row is None:
        raise CompanyOsNotFound(f"workflow plan {plan_key!r} does not exist in this company")
    return row


async def load_writable(session: AsyncSession, company_id: uuid.UUID, plan_key: str) -> CompanyOsWorkflowPlan:
    """The latest revision, locked for update; a converted one is read-only (FR-0.4)."""
    row = await load_row(session, company_id, plan_key, lock=True)
    if row.status == WorkflowPlanStatus.CONVERTED.value:
        raise CompanyOsConflict(FROZEN_MESSAGE)
    return row


async def plan_key_taken(session: AsyncSession, company_id: uuid.UUID, plan_key: str) -> bool:
    count = (
        await session.execute(
            select(func.count())
            .select_from(CompanyOsWorkflowPlan)
            .where(CompanyOsWorkflowPlan.company_id == company_id, CompanyOsWorkflowPlan.plan_key == plan_key)
        )
    ).scalar_one()
    return count > 0


def read_plan(row: CompanyOsWorkflowPlan) -> CompanyWorkflowPlan:
    return CompanyWorkflowPlan.model_validate(row.document)


def _reason(prev: Optional[WorkflowPlanStatus], report: GateReport) -> str:
    if prev is None:
        return "plan created"
    ladder = list(WorkflowPlanStatus)
    if ladder.index(report.status) < ladder.index(prev) and report.missing:
        first = report.missing[0]
        return f"{first.gate}: {first.message}"
    return f"gates for {report.status.value} pass"


def _record_status(plan: CompanyWorkflowPlan, report: GateReport, actor: Optional[uuid.UUID]) -> bool:
    prev = plan.status_history[-1].to_status if plan.status_history else None
    plan.status = report.status
    if prev == report.status:
        return False
    plan.status_history.append(
        StatusChange(
            from_status=prev,
            to_status=report.status,
            at=datetime.now(timezone.utc),
            by=actor,
            reason=_reason(prev, report),
        )
    )
    return True


async def save_plan(
    session: AsyncSession,
    row: CompanyOsWorkflowPlan,
    plan: CompanyWorkflowPlan,
    *,
    actor: Optional[uuid.UUID],
    clears_approval: bool = True,
) -> CompanyWorkflowPlan:
    """Recompute the status, store the document and the status column together."""
    if clears_approval:
        plan.approved_at, plan.approved_by = None, None
        # An acknowledgement covers the plan the owner saw: any ordinary edit voids it (#20187).
        plan.by_hand_acknowledged_at = None
        # A preview describes the plan it was built from; an edit makes it stale. A committed one is history.
        if plan.conversion is not None and plan.conversion.status is ConversionStatus.PREVIEW:
            plan.conversion = None
    changed = _record_status(plan, evaluate_plan_gate(plan), actor)
    row.document = plan.model_dump(mode="json")
    row.status, row.name = plan.status.value, plan.name
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise CompanyOsConflict(f"workflow plan {plan.key!r} already has an open revision") from exc
    if changed:
        logger.info("%s plan=%s status=%s", STATUS_CHANGED_EVENT, plan.key, plan.status.value)
    return plan
