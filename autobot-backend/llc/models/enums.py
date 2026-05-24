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

    Replaces the originally separate HeartbeatRunStatus (#8225) and
    AdapterRunStatus (#8226) — both had identical values so they are collapsed
    into a single enum to avoid enum-drift.
    """

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


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
