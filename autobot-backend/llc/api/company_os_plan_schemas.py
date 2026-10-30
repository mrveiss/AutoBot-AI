# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request/response models for the Workflow Planner API (#19934).

The plan document itself (``CompanyWorkflowPlan``) lives in ``llc/services/company_os/
plan_types.py`` beside ``graph_types.py``, so the service layer never imports the API layer.
Every body forbids unknown fields: a PATCH carrying ``status`` is a 422, because the server
owns status (FR-0.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from llc.services.company_os.plan_types import (
    DURATION_UNITS,
    CompanyWorkflowPlan,
    Direction,
    Edge,
    EntryPoint,
    Label,
    Lane,
    ReturnKind,
    Step,
    SubStepState,
    Unit,
    WorkflowPlanStatus,
)

from .company_os_schemas import GraphValidation


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MapBody(_Body):
    """Lanes, steps and edges in authoring order. Handoffs are never sent: the server derives them."""

    lanes: List[Lane] = Field(default_factory=list, max_length=100)
    steps: List[Step] = Field(default_factory=list, max_length=500)
    edges: List[Edge] = Field(default_factory=list, max_length=2000)


class PlanCreate(MapBody):
    key: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(..., min_length=1, max_length=255)
    entry_point: EntryPoint
    starts_at: str = Field(..., min_length=1, max_length=500)
    ends_at: str = Field(..., min_length=1, max_length=500)
    industry: Optional[str] = Field(None, max_length=255)
    headcount: Optional[int] = Field(None, ge=0)


class PlanUpdate(_Body):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    industry: Optional[str] = Field(None, max_length=255)
    headcount: Optional[int] = Field(None, ge=0)
    starts_at: Optional[str] = Field(None, min_length=1, max_length=500)
    ends_at: Optional[str] = Field(None, min_length=1, max_length=500)


class PlanSummary(BaseModel):
    plan_key: str
    revision: int
    name: str
    status: WorkflowPlanStatus
    updated_at: datetime

    model_config = {"from_attributes": True}


class MapResponse(BaseModel):
    plan: CompanyWorkflowPlan
    validation: GraphValidation


class HandoffPatch(_Body):
    wait_note: Optional[str] = Field(None, max_length=2000)


class QuantityBody(_Body):
    value: float = Field(..., ge=0)
    unit: Unit


class MetricBody(_Body):
    """Self-reported only: the server stamps the source, time and author."""

    frequency: QuantityBody
    duration: QuantityBody

    @model_validator(mode="after")
    def _units(self) -> "MetricBody":
        if self.frequency.unit is not Unit.PER_WEEK:
            raise ValueError("frequency must be per_week")
        if self.duration.unit not in DURATION_UNITS:
            raise ValueError("duration must be in minutes, hours or days")
        return self


class OneNumberBody(_Body):
    title: str = Field(..., min_length=1, max_length=255)
    step_key: str = Field(..., min_length=1, max_length=64)
    return_kind: ReturnKind
    direction: Direction
    unit: Unit
    baseline_value: float = Field(..., ge=0)
    target_value: Optional[float] = None
    goal_id: Optional[uuid.UUID] = None
    why_this_one: Optional[str] = Field(None, max_length=2000)


class SubStepBody(_Body):
    key: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    label: str = Field(..., min_length=1, max_length=255)
    state: SubStepState
    classification: Optional[Label] = None
    rationale: Optional[str] = Field(None, max_length=2000)
    tool_action: Optional[str] = Field(None, max_length=255)
    replaces: List[str] = Field(default_factory=list, max_length=100)


class EdgeCaseBody(_Body):
    key: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    description: str = Field(..., min_length=1, max_length=2000)
    classification: Label
    handling: Optional[str] = Field(None, max_length=2000)
    sub_step_key: Optional[str] = None


class BreakdownBody(_Body):
    sub_steps: List[SubStepBody] = Field(default_factory=list, max_length=200)
    edge_cases: List[EdgeCaseBody] = Field(default_factory=list, max_length=200)


class SubStepPatch(_Body):
    classification: Optional[Label] = None
    rationale: Optional[str] = Field(None, max_length=2000)


class GateItem(BaseModel):
    gate: str
    message: str
    step: Optional[str] = None


class GateResponse(BaseModel):
    status: WorkflowPlanStatus
    next_status: Optional[WorkflowPlanStatus]
    missing: List[GateItem]
