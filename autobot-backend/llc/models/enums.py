# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC module enum SSOT (GH#8261).

All LLC enums are defined here and imported everywhere — never redefined in
service or API files. This prevents the 23+ *Status enum duplication pattern
found in GH#7265 and GH#7504.

LLCAgentStatus decision: define a separate LLC-scoped enum (not extending the
canonical AgentStatus) because LLC agents have lifecycle states specific to
sprint/work-item assignment that don't map cleanly to the system-level
AgentStatus values. Cross-reference: GH#7504.
"""

from enum import Enum


class WorkItemType(str, Enum):
    """Type of LLC work item (GH#8213).

    Hierarchy: epic → feature → pbi → task/bug/subtask/spike/risk.
    """

    EPIC = "epic"
    FEATURE = "feature"
    PBI = "pbi"
    TASK = "task"
    BUG = "bug"
    SUBTASK = "subtask"
    SPIKE = "spike"
    RISK = "risk"


class WorkItemStatus(str, Enum):
    """Status of an LLC work item (GH#8213)."""

    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class WorkItemPriority(str, Enum):
    """Priority of an LLC work item (GH#8213)."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BudgetMode(str, Enum):
    """Budget tracking mode for LLC agents (GH#8997).

    DOLLARS: track spend in USD (default, uses MODEL_PRICING_PER_1M_TOKENS)
    TOKENS: track spend in token counts (for subscription/free-tier users)
    """

    DOLLARS = "dollars"
    TOKENS = "tokens"


class LLCCompanyStatus(str, Enum):
    """Lifecycle status of a company within the LLC module (GH#8211)."""

    ONBOARDING = "onboarding"
    ACTIVE = "active"
    PAUSED = "paused"
    OFFBOARDING = "offboarding"
    ARCHIVED = "archived"


class LLCAgentStatus(str, Enum):
    """LLC-scoped agent lifecycle status (GH#8225).

    Separate from canonical AgentStatus — LLC agents have sprint/work-item
    assignment states that don't exist at the system level. See module docstring
    for the rationale.
    """

    AVAILABLE = "available"
    ASSIGNED = "assigned"
    IN_SPRINT = "in_sprint"
    ON_LEAVE = "on_leave"
    ONBOARDING = "onboarding"
    OFFBOARDING = "offboarding"
    INACTIVE = "inactive"
    PAUSED = "paused"
    TERMINATED = "terminated"


class SprintStatus(str, Enum):
    """Status of a sprint (GH#8219)."""

    PLANNING = "planning"
    ACTIVE = "active"
    REVIEW = "review"
    RETROSPECTIVE = "retrospective"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ApprovalType(str, Enum):
    """Gate type for a board approval request (GH#8214)."""

    HIRE = "hire"
    STRATEGY = "strategy"
    BUDGET_OVERRIDE = "budget_override"
    SPRINT_CLOSE = "sprint_close"


class ApprovalStatus(str, Enum):
    """Status of an LLC approval request (GH#8214)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class LLCRunStatus(str, Enum):
    """Unified run status for heartbeat and adapter runs (GH#8261).

    Consolidates both heartbeat-specific states (QUEUED) and adapter-common states.
    Maps SUCCEEDED (heartbeat language) to COMPLETED (adapter language).
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    RATE_LIMITED = "rate_limited"


class HeartbeatInvocationSource(str, Enum):
    """How a heartbeat run was triggered (GH#8225, GH#9624)."""

    SCHEDULER = "scheduler"
    MANUAL = "manual"
    CALLBACK = "callback"
    WORK_ITEM_COMMENTED = "work_item_commented"


class ContextMode(str, Enum):
    """Context window loading mode for heartbeat runs."""

    THIN = "thin"
    FAT = "fat"


class CoWorkerType(str, Enum):
    """Identifies whether the co-worker is an agent or human (GH#8230)."""

    AGENT = "agent"
    HUMAN = "human"


class AssignmentType(str, Enum):
    """How a work item was assigned to an agent (GH#8230)."""

    MANUAL = "manual"
    AUTO = "auto"
    DELEGATED = "delegated"
    INHERITED = "inherited"


class BoardType(str, Enum):
    """Type of LLC board (GH#8221)."""

    KANBAN = "kanban"
    SPRINT = "sprint"


class MembershipRole(str, Enum):
    """Role of a human user within an LLC company (GH#8223)."""

    OWNER = "owner"
    ADMIN = "admin"
    LEAD = "lead"
    MEMBER = "member"
    GUEST = "guest"


class RoutineStatus(str, Enum):
    """Lifecycle status of an LLC routine (GH#8229)."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class RoutineProduces(str, Enum):
    """What a routine creates on each fire (GH#8229)."""

    NEW_WORK_ITEM = "new_work_item"
    UPDATES_RECURRING = "updates_recurring"


class ExternalPMType(str, Enum):
    """External project management system type (GH#8257)."""

    JIRA = "jira"
    AZURE_DEVOPS = "azure_devops"
    TRELLO = "trello"
    ASANA = "asana"
    NONE = "none"


class LLCSyncEvent(str, Enum):
    """LLC work item events published to Redis pub/sub (GH#8257)."""

    CREATED = "created"
    TRANSITIONED = "transitioned"
    COMMENTED = "commented"
    COMPLETED = "completed"


class WorkProductType(str, Enum):
    """Type of work product artifact produced by an agent (GH#8242)."""

    CODE = "code"
    DOCUMENT = "document"
    REPORT = "report"
    PLAN = "plan"
    SCREENSHOT = "screenshot"
    PR_LINK = "pr_link"
    OTHER = "other"


class WorkItemRelationType(str, Enum):
    """Relation type between two LLC work items (GH#8252).
    ``blocks`` and ``blocked_by`` are mirrors: adding A→B blocks creates B→A blocked_by.
    """

    BLOCKS = "blocks"
    BLOCKED_BY = "blocked_by"
    DUPLICATES = "duplicates"
    RELATES_TO = "relates_to"


class ActivityEventType(str, Enum):
    """Typed enum for all LLC activity log event_type strings.

    Using an enum prevents bare string literals scattered across 13+ issues
    and catches misspellings at import time rather than at query time.
    """

    # Company lifecycle
    COMPANY_CREATED = "company.created"
    COMPANY_UPDATED = "company.updated"
    COMPANY_STATUS_CHANGED = "company.status_changed"
    COMPANY_ARCHIVED = "company.archived"
    COMPANY_EXPORT_TEMPLATE = "company.export_template"
    COMPANY_EXPORT_SNAPSHOT = "company.export_snapshot"

    # Agent lifecycle
    AGENT_HIRED = "agent.hired"
    AGENT_ASSIGNED = "agent.assigned"
    AGENT_UNASSIGNED = "agent.unassigned"
    AGENT_STATUS_CHANGED = "agent.status_changed"
    AGENT_OFFBOARDED = "agent.offboarded"

    # Work item lifecycle
    WORK_ITEM_CREATED = "work_item.created"
    WORK_ITEM_UPDATED = "work_item.updated"
    WORK_ITEM_STATUS_CHANGED = "work_item.status_changed"
    WORK_ITEM_ASSIGNED = "work_item.assigned"
    WORK_ITEM_COMPLETED = "work_item.completed"
    WORK_ITEM_CANCELLED = "work_item.cancelled"
    WORK_ITEM_HANDOFF = "work_item.handoff"
    WORK_ITEM_REVIEW_APPROVED = "work_item.review_approved"
    WORK_ITEM_REVIEW_CHANGES_REQUESTED = "work_item.review_changes_requested"
    WORK_ITEM_COWORKER_SET = "work_item.coworker_set"
    WORK_ITEM_COWORKER_CLEARED = "work_item.coworker_cleared"
    WORK_ITEM_RELATION_ADDED = "work_item.relation_added"
    WORK_ITEM_RELATION_REMOVED = "work_item.relation_removed"

    # Sprint lifecycle
    SPRINT_CREATED = "sprint.created"
    SPRINT_STARTED = "sprint.started"
    SPRINT_COMPLETED = "sprint.completed"
    SPRINT_CANCELLED = "sprint.cancelled"
    SPRINT_ITEM_ADDED = "sprint.item_added"
    SPRINT_ITEM_REMOVED = "sprint.item_removed"

    # Approval lifecycle
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_WITHDRAWN = "approval.withdrawn"

    # Board instant controls (GH#8256 — FR-GOV-05)
    CONTROL_AGENT_PAUSED = "control.agent_paused"
    CONTROL_AGENT_RESUMED = "control.agent_resumed"
    CONTROL_AGENT_TERMINATED = "control.agent_terminated"
    CONTROL_SPRINT_PAUSED = "control.sprint_paused"
    CONTROL_SPRINT_RESUMED = "control.sprint_resumed"
    CONTROL_COMPANY_PAUSED = "control.company_paused"
    CONTROL_COMPANY_RESUMED = "control.company_resumed"

    # Heartbeat / run
    HEARTBEAT_STARTED = "heartbeat.started"
    HEARTBEAT_COMPLETED = "heartbeat.completed"
    HEARTBEAT_FAILED = "heartbeat.failed"

    # Adapter
    ADAPTER_RUN_STARTED = "adapter_run.started"
    ADAPTER_RUN_COMPLETED = "adapter_run.completed"
    ADAPTER_RUN_FAILED = "adapter_run.failed"

    # Notification
    NOTIFICATION_SENT = "notification.sent"
