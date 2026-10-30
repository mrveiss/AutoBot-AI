# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Workflow Planner plan document (#19934).

One ``CompanyWorkflowPlan`` is the JSONB document of one plan revision. The root is not
called ``WorkflowPlan`` (``orchestration/types.py``) or the deprecated planner class beside it
(``orchestration/workflow_planner.py``): both exist and mean something else.

Wire style mirrors ``graph_types.py``: keys on the wire, UUIDs only for role references.
Only what plan creation, the self-reported measure, the One Number, the breakdown and the
labels need lives here. Approval policies, the conversion and re-plans belong to the issues
that deliver them and are added to this document there.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

KEY_PATTERN = r"^[A-Za-z0-9_.-]+$"
SCHEMA_VERSION = "0.2.0"
DURATION_DEFINITION = "landing_to_done"


class Label(str, Enum):
    AI = "ai"
    AUTOMATION = "automation"
    BY_HAND = "by_hand"


class MetricSource(str, Enum):
    SELF_REPORTED = "self_reported"
    EMAIL = "email"
    CALENDAR = "calendar"


class Unit(str, Enum):
    PER_WEEK = "per_week"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    PERCENT = "percent"
    COUNT = "count"
    CURRENCY = "currency"


DURATION_UNITS = frozenset({Unit.MINUTES, Unit.HOURS, Unit.DAYS})


class ReturnKind(str, Enum):
    HOURS_BACK = "hours_back"
    MORE_YESES = "more_yeses"
    MONEY_SOONER = "money_sooner"


class HolderKind(str, Enum):
    USER = "user"
    AGENT = "agent"
    CONTACT = "contact"
    CUSTOMER = "customer"
    EXTERNAL = "external"


#: Lanes held by someone outside the company: no ``roles`` row, ever (FR-1.2).
NO_ROLE_HOLDERS = frozenset({HolderKind.CUSTOMER, HolderKind.EXTERNAL})


class WorkflowPlanStatus(str, Enum):
    """Server-computed (section 7B); the client never sets it."""

    DRAFT = "draft"
    MEASURED = "measured"
    LABELED = "labeled"
    APPROVED = "approved"
    CONVERTED = "converted"


class EntryPoint(str, Enum):
    ORG_CHART = "org_chart"
    WIZARD_EXIT = "wizard_exit"
    WORKFLOW_AREA = "workflow_area"
    REPLAN = "replan"


class SubStepState(str, Enum):
    CURRENT = "current"
    PROPOSED = "proposed"


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"


class _Doc(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(_Doc):
    """An opaque reference; never a subject, body or attendee list."""

    source: MetricSource
    ref: str = Field(..., min_length=1, max_length=128)
    occurred_at: Optional[datetime] = None


class Measurement(_Doc):
    value: float = Field(..., ge=0)
    unit: Unit
    source: MetricSource
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    sample_size: Optional[int] = Field(None, ge=0)
    statistic: Optional[str] = Field(None, max_length=32)
    evidence: List[EvidenceRef] = Field(default_factory=list, max_length=1000)
    recorded_at: datetime
    recorded_by: Optional[uuid.UUID] = None


class Lane(_Doc):
    key: str = Field(..., min_length=1, max_length=64, pattern=KEY_PATTERN)
    name: str = Field(..., min_length=1, max_length=255)
    holder_kind: HolderKind
    role_id: Optional[uuid.UUID] = None
    position: int = 0

    @model_validator(mode="after")
    def _role_matches_holder(self) -> "Lane":
        if self.holder_kind in NO_ROLE_HOLDERS and self.role_id is not None:
            raise ValueError(f"lane {self.key!r}: a {self.holder_kind.value} lane links no role")
        if self.holder_kind not in NO_ROLE_HOLDERS and self.role_id is None:
            raise ValueError(f"lane {self.key!r}: a {self.holder_kind.value} lane needs a role_id")
        return self


class Step(_Doc):
    key: str = Field(..., min_length=1, max_length=64, pattern=KEY_PATTERN)
    lane_key: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=255)
    position: int = 0
    process_key: Optional[str] = Field(None, max_length=255)
    note: Optional[str] = Field(None, max_length=2000)


class Edge(_Doc):
    from_step: str = Field(..., min_length=1, max_length=64)
    to_step: str = Field(..., min_length=1, max_length=64)
    condition: Optional[str] = Field(None, max_length=2000)


class Handoff(_Doc):
    """Derived by the server from the edges; the client can only annotate ``wait_note``."""

    key: str
    from_step: str
    to_step: str
    from_lane: str
    to_lane: str
    wait_note: Optional[str] = Field(None, max_length=2000)


class StepMetric(_Doc):
    step_key: str
    frequency: Measurement
    duration: Measurement
    duration_definition: str = DURATION_DEFINITION
    verified: bool = False

    @model_validator(mode="after")
    def _units(self) -> "StepMetric":
        if self.frequency.unit is not Unit.PER_WEEK:
            raise ValueError("frequency must be per_week")
        if self.duration.unit not in DURATION_UNITS:
            raise ValueError("duration must be in minutes, hours or days")
        return self


class OneNumber(_Doc):
    key: str = "one-number"
    title: str = Field(..., min_length=1, max_length=255)
    step_key: str
    return_kind: ReturnKind
    direction: Direction
    unit: Unit
    baseline: Measurement
    #: Optional and never defaulted (FR-3.2): the owner sets it or it stays null.
    target_value: Optional[float] = None
    goal_id: Optional[uuid.UUID] = None
    why_this_one: Optional[str] = Field(None, max_length=2000)


class SubStep(_Doc):
    key: str = Field(..., min_length=1, max_length=64, pattern=KEY_PATTERN)
    step_key: str
    label: str = Field(..., min_length=1, max_length=255)
    position: int = 0
    lane_key: str
    state: SubStepState
    classification: Optional[Label] = None
    rationale: Optional[str] = Field(None, max_length=2000)
    tool_action: Optional[str] = Field(None, max_length=255)
    replaces: List[str] = Field(default_factory=list, max_length=100)


class EdgeCase(_Doc):
    key: str = Field(..., min_length=1, max_length=64, pattern=KEY_PATTERN)
    step_key: str
    description: str = Field(..., min_length=1, max_length=2000)
    classification: Label
    handling: Optional[str] = Field(None, max_length=2000)
    sub_step_key: Optional[str] = None


class StatusChange(_Doc):
    from_status: Optional[WorkflowPlanStatus] = None
    to_status: WorkflowPlanStatus
    at: datetime
    by: Optional[uuid.UUID] = None
    reason: Optional[str] = Field(None, max_length=1000)


class CompanyWorkflowPlan(_Doc):
    """The document of one revision (section 9)."""

    schema_version: str = SCHEMA_VERSION
    key: str
    revision: int = 1
    name: str
    industry: Optional[str] = None
    headcount: Optional[int] = None
    entry_point: EntryPoint
    starts_at: str = Field(..., min_length=1, max_length=500)
    ends_at: str = Field(..., min_length=1, max_length=500)
    status: WorkflowPlanStatus = WorkflowPlanStatus.DRAFT
    status_history: List[StatusChange] = Field(default_factory=list)
    lanes: List[Lane] = Field(default_factory=list)
    steps: List[Step] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)
    handoffs: List[Handoff] = Field(default_factory=list)
    step_metrics: List[StepMetric] = Field(default_factory=list)
    one_number: Optional[OneNumber] = None
    sub_steps: List[SubStep] = Field(default_factory=list)
    edge_cases: List[EdgeCase] = Field(default_factory=list)
    by_hand_acknowledged_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[uuid.UUID] = None
