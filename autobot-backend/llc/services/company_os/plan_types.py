# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Workflow Planner plan document (#19934).

One ``CompanyWorkflowPlan`` is the JSONB document of one plan revision. The root is not
called ``WorkflowPlan`` (``orchestration/types.py``) or the deprecated planner class beside it
(``orchestration/workflow_planner.py``): both exist and mean something else.

Wire style mirrors ``graph_types.py``: keys on the wire, UUIDs only for role references.
Plan creation, the self-reported measure, the One Number, the breakdown and the labels live
here, with the approval policies and the conversion contract (#19936). Re-plans belong to the
issue that delivers them and are added to this document there.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.approval import ApprovalType

from .graph_types import NodeSpec, TransitionSpec

KEY_PATTERN = r"^[A-Za-z0-9_.-]+$"
SCHEMA_VERSION = "0.2.0"
DURATION_DEFINITION = "landing_to_done"
#: The issue tracking a workflow executor: "Turn on" stays unavailable until it lands (FR-6.7).
TURN_ON_TRACKING_ISSUE = 16763


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


#: The one kind of approval a plan may ask for: it waits in Approvals (FR-6.2). The value is the canonical
#: ``ApprovalType`` member (#20115), narrowed to one so a policy cannot name another kind.
PlanApprovalType = Literal[ApprovalType.WORKFLOW_GATE]


class PlanApprovalTimeout(str, Enum):
    """What an unanswered approval does. There is no ``send``: a wait never sends on its own (FR-6.2)."""

    HOLD = "hold"
    REMIND = "remind"
    ESCALATE = "escalate"


class PlanApprovalPolicy(_Doc):
    """Covers the AI sub-steps it names. ``wait_limit`` adds a timeout whose length is a setting, never a literal.

    The gate is recorded, not enforced: nothing executes workflows yet and no approval-gate model exists, so G5
    only checks that the plan carries a policy for every AI sub-step. It is enforced once an executor reads the
    policies kept in the committed conversion. ``hold`` waits indefinitely, so it never yields a timeout
    transition; ``remind`` and ``escalate`` do, when ``wait_limit`` is set.
    """

    key: str = Field(..., min_length=1, max_length=64, pattern=KEY_PATTERN)
    approval_type: PlanApprovalType = ApprovalType.WORKFLOW_GATE
    sub_step_keys: List[str] = Field(default_factory=list, max_length=200)
    on_timeout: PlanApprovalTimeout = PlanApprovalTimeout.HOLD
    wait_limit: bool = False


class PolicyEnforcement(str, Enum):
    """Whether the approval policies of a plan are enforced. Nothing executes workflows yet (#16763)."""

    NOT_ENFORCED = "not_enforced"


class ConversionStatus(str, Enum):
    PREVIEW = "preview"
    COMMITTED = "committed"


class TurnOn(str, Enum):
    """Whether a created workflow can be switched on. Nothing executes workflows yet (FR-6.7)."""

    NOT_AVAILABLE = "not_available"


class HandoffTreatmentKind(str, Enum):
    HANDOFF_TRANSITION = "handoff_transition"
    TRIGGER = "trigger"
    END = "end"
    OUT_OF_SCOPE = "out_of_scope"


class EdgeCaseTreatmentKind(str, Enum):
    BRANCH = "branch"
    HANDLED_IN_STEP = "handled_in_step"
    DOCUMENTATION = "documentation"


class ProcessExecutor(str, Enum):
    """Who carries a process out. A By Hand sub-step is always ``person`` (FR-6.4)."""

    PERSON = "person"
    ROLE = "role"


class ProcessDraft(_Doc):
    process_key: str
    name: str
    owner_lane_key: str
    sub_step_key: str
    required_skills: List[str] = Field(default_factory=list)
    executor: ProcessExecutor


class WorkflowDraft(_Doc):
    workflow_id: str
    name: str
    owner_lane_key: str
    trigger_type: str
    trigger_config: dict = Field(default_factory=dict)
    nodes: List[NodeSpec] = Field(default_factory=list)
    transitions: List[TransitionSpec] = Field(default_factory=list)
    approval_policy_keys: List[str] = Field(default_factory=list)


class DocumentationOnly(_Doc):
    sub_step_key: str
    reason: str


class HandoffTreatment(_Doc):
    handoff_key: str
    treatment: HandoffTreatmentKind


class EdgeCaseTreatment(_Doc):
    edge_case_key: str
    treatment: EdgeCaseTreatmentKind


class ProposalOutcome(str, Enum):
    UNFILED = "unfiled"
    FILED = "filed"
    #: The request exists and a person turned it down or sent it back: the line did not change (#20115).
    DECLINED = "declined"
    FAILED = "failed"


class AiLineProposal(_Doc):
    """One proposed AI-line change and what happened when it was filed in Approvals (after the commit)."""

    tool_action: str
    line: str
    sub_step_key: str
    outcome: ProposalOutcome = ProposalOutcome.UNFILED
    approval_id: Optional[str] = None
    error: Optional[str] = Field(None, max_length=500)


class PlanConversion(_Doc):
    """What crosses from the planner to Company OS (section 7A.2).

    ``preview_errors`` and ``preview_warnings`` are the graph validator's own strings, unchanged.
    ``contract_errors`` are what the builder found before any graph exists (a lane with no role, a
    tool action that is not a key). Either one non-empty keeps G6 open.
    """

    processes: List[ProcessDraft] = Field(default_factory=list)
    workflows: List[WorkflowDraft] = Field(default_factory=list)
    creation_order: List[str] = Field(default_factory=list)
    documentation_only: List[DocumentationOnly] = Field(default_factory=list)
    handoff_treatments: List[HandoffTreatment] = Field(default_factory=list)
    edge_case_treatments: List[EdgeCaseTreatment] = Field(default_factory=list)
    ai_line_proposals: List[AiLineProposal] = Field(default_factory=list)
    #: The approval policies this conversion was built under, kept for a future executor to read (D13).
    approval_policies: List[PlanApprovalPolicy] = Field(default_factory=list)
    contract_errors: List[str] = Field(default_factory=list)
    preview_errors: List[str] = Field(default_factory=list)
    preview_warnings: List[str] = Field(default_factory=list)
    status: ConversionStatus = ConversionStatus.PREVIEW
    converted_at: Optional[datetime] = None
    converted_by: Optional[uuid.UUID] = None
    turn_on: TurnOn = TurnOn.NOT_AVAILABLE
    turn_on_tracking_issue: int = TURN_ON_TRACKING_ISSUE


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
    approval_policies: List[PlanApprovalPolicy] = Field(default_factory=list)
    by_hand_acknowledged_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[uuid.UUID] = None
    conversion: Optional[PlanConversion] = None
    #: Set by the server on an ``approved`` or ``converted`` plan, so a client can say the policies wait for an
    #: executor without parsing text; ``None`` below that (#20115).
    policy_enforcement: Optional[PolicyEnforcement] = None
    policy_enforcement_tracking_issue: Optional[int] = None
