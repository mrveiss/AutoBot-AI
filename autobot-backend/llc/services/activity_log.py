"""LLC activity log service (GH#8261).

Single injectable service for all 13+ issues that write to llc_activity_log.
Callers must inject rather than write to the table directly, ensuring
consistent event_type strings and required field presence.
"""

from enum import Enum
from typing import Any, Dict, Optional


class ActivityEventType(str, Enum):
    """Typed enum for all LLC activity log event_type strings.

    Using an enum prevents bare string literals scattered across 13 issues
    and catches misspellings at import time rather than at query time.
    """

    # Company lifecycle
    COMPANY_CREATED = "company.created"
    COMPANY_UPDATED = "company.updated"
    COMPANY_STATUS_CHANGED = "company.status_changed"
    COMPANY_ARCHIVED = "company.archived"

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
    NOTIFICATION_FAILED = "notification.failed"


class LLCActivityLogService:
    """Injectable service for writing to llc_activity_log.

    All LLC services that need to record activity must inject this via the
    ``activity_log`` slot on LLCServiceBase — never call the table directly.

    Concrete implementation is built in GH#8216. This file provides the
    interface contract so dependents can type-check against it.
    """

    async def record(
        self,
        session: Any,
        company_id: str,
        actor_id: str,
        event_type: ActivityEventType,
        entity_type: str,
        entity_id: str,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a single activity log entry.

        Args:
            session: Async SQLAlchemy session.
            company_id: Tenant company identifier.
            actor_id: Agent or user that triggered the event.
            event_type: Typed event kind — use ActivityEventType enum values.
            entity_type: Table/resource name (e.g. "work_item", "sprint").
            entity_id: PK of the affected row.
            before: State snapshot before the change (optional).
            after: State snapshot after the change (optional).
            metadata: Arbitrary extra context (optional).
        """
        raise NotImplementedError(
            "LLCActivityLogService.record() — concrete impl in GH#8216"
        )

    async def record_bulk(
        self,
        session: Any,
        entries: list,
    ) -> None:
        """Insert multiple activity log entries in a single transaction.

        Args:
            session: Async SQLAlchemy session.
            entries: List of dicts matching the ``record()`` kwarg signature.
        """
        raise NotImplementedError(
            "LLCActivityLogService.record_bulk() — concrete impl in GH#8216"
        )
