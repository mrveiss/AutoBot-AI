# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Self-reported metrics and the One Number (#19934, FR-2, FR-3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.goal import GoalLevel, LLCGoal
from llc.models.membership import LLCCompanyMembership
from llc.models.role_assignment import LLCRoleAssignment
from llc.services.authz import NotAuthorisedError, require_company_admin
from llc.services.goal import GoalService

from .errors import CompanyOsConflict, CompanyOsNotFound
from .plan_types import (
    CompanyWorkflowPlan,
    Direction,
    Measurement,
    MetricSource,
    OneNumber,
    ReturnKind,
    Step,
    StepMetric,
    Unit,
)


def find_step(plan: CompanyWorkflowPlan, step_key: str) -> Step:
    for step in plan.steps:
        if step.key == step_key:
            return step
    raise CompanyOsNotFound(f"step {step_key!r} does not exist in this plan")


async def _holds_lane_role(
    session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID
) -> bool:
    member = await session.execute(
        select(LLCCompanyMembership.id).where(
            LLCCompanyMembership.company_id == company_id, LLCCompanyMembership.user_id == user_id
        )
    )
    if member.scalar_one_or_none() is None:
        return False
    held = await session.execute(
        select(LLCRoleAssignment.id).where(
            LLCRoleAssignment.company_id == company_id,
            LLCRoleAssignment.role_id == role_id,
            LLCRoleAssignment.holder_user_id == user_id,
            LLCRoleAssignment.ended_at.is_(None),
        )
    )
    return held.first() is not None


async def require_metric_writer(
    session: AsyncSession, company_id: uuid.UUID, actor: Optional[uuid.UUID], lane_role_id: Optional[uuid.UUID]
) -> None:
    """Company admin, or a member currently holding the step's lane role (D10)."""
    try:
        await require_company_admin(session, company_id, actor)
    except NotAuthorisedError:
        if (
            actor is None
            or lane_role_id is None
            or not await _holds_lane_role(session, company_id, actor, lane_role_id)
        ):
            raise


def _self_reported(value: float, unit: Unit, actor: Optional[uuid.UUID]) -> Measurement:
    return Measurement(
        value=value,
        unit=unit,
        source=MetricSource.SELF_REPORTED,
        recorded_at=datetime.now(timezone.utc),
        recorded_by=actor,
    )


def set_metric(
    plan: CompanyWorkflowPlan, step_key: str, frequency: tuple, duration: tuple, actor: Optional[uuid.UUID]
) -> None:
    """Store (or replace) the self-reported metric of one step."""
    find_step(plan, step_key)
    metric = StepMetric(
        step_key=step_key, frequency=_self_reported(*frequency, actor), duration=_self_reported(*duration, actor)
    )
    plan.step_metrics = [m for m in plan.step_metrics if m.step_key != step_key] + [metric]


async def _goal_for(
    session: AsyncSession, company_id: uuid.UUID, plan: CompanyWorkflowPlan, title: str, goal_id: Optional[uuid.UUID]
) -> uuid.UUID:
    """Link an existing key-result goal of this company, update the one already linked, or create one (FR-3.3)."""
    goals = GoalService()
    target = goal_id or (plan.one_number.goal_id if plan.one_number else None)
    if target is None:
        return (await goals.create(session, str(company_id), title, GoalLevel.KEY_RESULT)).id
    goal = (await session.execute(select(LLCGoal).where(LLCGoal.id == target))).scalar_one_or_none()
    if goal is None or str(goal.company_id) != str(company_id):
        raise CompanyOsNotFound(f"goal {target} does not exist in this company")
    if goal.level != GoalLevel.KEY_RESULT.value:
        raise CompanyOsConflict("the One Number links a key_result goal")
    # Follow a rename only on a goal still carrying this plan's title: a goal someone linked keeps its own.
    in_sync = goal_id is None and plan.one_number is not None and goal.title == plan.one_number.title
    if in_sync and goal.title != title:
        await goals.update(session, goal.id, title=title)
    return goal.id


async def set_one_number(
    session: AsyncSession,
    company_id: uuid.UUID,
    plan: CompanyWorkflowPlan,
    *,
    title: str,
    step_key: str,
    return_kind: ReturnKind,
    direction: Direction,
    unit: Unit,
    baseline_value: float,
    actor: Optional[uuid.UUID],
    target_value: Optional[float] = None,
    goal_id: Optional[uuid.UUID] = None,
    why_this_one: Optional[str] = None,
) -> None:
    """The owner's explicit pick; ``target_value`` stays ``None`` unless given (FR-3.2)."""
    find_step(plan, step_key)
    linked = await _goal_for(session, company_id, plan, title, goal_id)
    plan.one_number = OneNumber(
        title=title,
        step_key=step_key,
        return_kind=return_kind,
        direction=direction,
        unit=unit,
        baseline=_self_reported(baseline_value, unit, actor),
        target_value=target_value,
        goal_id=linked,
        why_this_one=why_this_one,
    )
