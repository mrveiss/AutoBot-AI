"""LLC activity log service (GH#8216).

Single injectable service for all LLC mutations. All callers inject this
via LLCServiceBase.activity_log — never write to llc_activity_log directly.

Append-only guarantee: this service exposes no update() or delete() methods.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client

from ..models.activity import ActorType, LLCActivityLog

logger = logging.getLogger(__name__)

_PUBSUB_CHANNEL_PREFIX = "llc:activity"


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


class ActivityLogQuery:
    """Filter + pagination parameters for LLCActivityLogService.query()."""

    def __init__(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        actor_type: "ActorType | str | None" = None,
        actor_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.action = action
        self.actor_type = actor_type
        self.actor_id = actor_id
        self.from_date = from_date
        self.to_date = to_date
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), 200)


class ActivityLogPage:
    """Paginated result returned by LLCActivityLogService.query()."""

    def __init__(
        self,
        items: list[LLCActivityLog],
        page: int,
        page_size: int,
        total: int,
    ) -> None:
        self.items = items
        self.page = page
        self.page_size = page_size
        self.total = total
        self.has_next = (page * page_size) < total


class LLCActivityLogService:
    """Concrete append-only activity log service (GH#8216).

    Inject via LLCServiceBase.activity_log — never call llc_activity_log directly.
    No update() or delete() methods exist on this class by design.
    """

    async def record(
        self,
        session: AsyncSession,
        company_id: str,
        actor_type: "ActorType | str",
        actor_id: str | None,
        event_type: "ActivityEventType | str",
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLCActivityLog:
        """Append a single activity log entry and publish to Redis pub/sub.

        Args:
            session: Async SQLAlchemy session (caller-owned transaction).
            company_id: Tenant scope.
            actor_type: Who triggered the action (agent/user/system).
            actor_id: UUID of the agent or user; None for system events.
            event_type: Typed event kind — use ActivityEventType values.
            entity_type: Resource name (e.g. "work_item", "sprint").
            entity_id: PK of the affected row.
            before: State snapshot before the change (optional).
            after: State snapshot after the change (defaults to empty dict).
            metadata: Arbitrary extra context (optional).

        Returns:
            The persisted LLCActivityLog row (id and occurred_at populated).
        """
        actor_type_str = actor_type.value if isinstance(actor_type, ActorType) else actor_type
        action_str = event_type.value if isinstance(event_type, ActivityEventType) else event_type

        actor_agent_id: uuid.UUID | None = None
        actor_user_id: uuid.UUID | None = None

        if actor_id is not None:
            try:
                parsed_actor = uuid.UUID(actor_id) if isinstance(actor_id, str) else actor_id
            except ValueError as exc:
                raise ValueError(f"Invalid actor_id UUID: {actor_id!r}") from exc
            if actor_type_str == ActorType.AGENT.value:
                actor_agent_id = parsed_actor
            elif actor_type_str == ActorType.USER.value:
                actor_user_id = parsed_actor

        try:
            company_uuid = uuid.UUID(company_id) if isinstance(company_id, str) else company_id
        except ValueError as exc:
            raise ValueError(f"Invalid company_id UUID: {company_id!r}") from exc
        try:
            entity_uuid = uuid.UUID(entity_id) if isinstance(entity_id, str) else entity_id
        except ValueError as exc:
            raise ValueError(f"Invalid entity_id UUID: {entity_id!r}") from exc

        entry = LLCActivityLog(
            company_id=company_uuid,
            actor_type=actor_type_str,
            actor_agent_id=actor_agent_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_uuid,
            action=action_str,
            before_state=before,
            after_state=after or {},
            log_metadata=metadata,
            occurred_at=datetime.now(tz=timezone.utc),
        )

        session.add(entry)
        await session.flush()

        await self._publish(company_id, entry)
        return entry

    async def record_bulk(
        self,
        session: AsyncSession,
        entries: list[dict[str, Any]],
    ) -> list[LLCActivityLog]:
        """Insert multiple activity log entries, one flush per entry.

        Each dict in ``entries`` must match the record() kwarg signature.
        All rows share the caller-owned session and transaction. Each call to
        record() flushes and publishes independently; a rollback on the outer
        transaction after record_bulk() returns may result in phantom Redis
        events for already-published entries.

        Returns:
            List of persisted LLCActivityLog rows in insertion order.
        """
        rows: list[LLCActivityLog] = []
        for entry_kwargs in entries:
            row = await self.record(session=session, **entry_kwargs)
            rows.append(row)
        return rows

    async def query(
        self,
        session: AsyncSession,
        company_id: str,
        params: ActivityLogQuery | None = None,
    ) -> ActivityLogPage:
        """Return a paginated, filtered slice of activity log rows.

        company_id is always applied first (mandatory tenant isolation).

        Args:
            session: Async SQLAlchemy session.
            company_id: Tenant scope — always applied.
            params: Optional filters and pagination settings.

        Returns:
            ActivityLogPage with items and pagination metadata.
        """
        if params is None:
            params = ActivityLogQuery()

        try:
            company_uuid = uuid.UUID(company_id) if isinstance(company_id, str) else company_id
        except ValueError as exc:
            raise ValueError(f"Invalid company_id UUID: {company_id!r}") from exc
        stmt = select(LLCActivityLog).where(LLCActivityLog.company_id == company_uuid)

        if params.entity_type:
            stmt = stmt.where(LLCActivityLog.entity_type == params.entity_type)
        if params.entity_id:
            try:
                entity_uuid = uuid.UUID(params.entity_id)
            except ValueError as exc:
                raise ValueError(f"Invalid entity_id UUID: {params.entity_id!r}") from exc
            stmt = stmt.where(LLCActivityLog.entity_id == entity_uuid)
        if params.action:
            stmt = stmt.where(LLCActivityLog.action == params.action)
        if params.actor_type:
            actor_type_str = params.actor_type.value if isinstance(params.actor_type, ActorType) else params.actor_type
            stmt = stmt.where(LLCActivityLog.actor_type == actor_type_str)
        if params.actor_id:
            try:
                actor_uuid = uuid.UUID(params.actor_id)
            except ValueError as exc:
                raise ValueError(f"Invalid actor_id UUID: {params.actor_id!r}") from exc
            stmt = stmt.where(
                (LLCActivityLog.actor_agent_id == actor_uuid) | (LLCActivityLog.actor_user_id == actor_uuid)
            )
        if params.from_date:
            from_date = (
                params.from_date.replace(tzinfo=timezone.utc) if params.from_date.tzinfo is None else params.from_date
            )
            stmt = stmt.where(LLCActivityLog.occurred_at >= from_date)
        if params.to_date:
            to_date = params.to_date.replace(tzinfo=timezone.utc) if params.to_date.tzinfo is None else params.to_date
            stmt = stmt.where(LLCActivityLog.occurred_at <= to_date)

        count_stmt = select(sa.func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (params.page - 1) * params.page_size
        stmt = stmt.order_by(LLCActivityLog.occurred_at.desc()).offset(offset).limit(params.page_size)

        result = await session.execute(stmt)
        items = list(result.scalars().all())

        return ActivityLogPage(
            items=items,
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    async def _publish(self, company_id: str, entry: LLCActivityLog) -> None:
        """Publish to Redis pub/sub channel llc:activity:{company_id}.

        Failures are logged but never raised — publishing must not break writes.
        Note: publish happens after flush but before the caller's commit; a
        rollback on the outer transaction will leave a phantom event on the
        channel. Subscribers must treat events as hints and requery on doubt.
        """
        channel = f"{_PUBSUB_CHANNEL_PREFIX}:{company_id}"
        payload = {
            "id": str(entry.id),
            "company_id": str(entry.company_id),
            "actor_type": entry.actor_type,
            "actor_agent_id": str(entry.actor_agent_id) if entry.actor_agent_id else None,
            "actor_user_id": str(entry.actor_user_id) if entry.actor_user_id else None,
            "entity_type": entry.entity_type,
            "entity_id": str(entry.entity_id),
            "action": entry.action,
            "occurred_at": entry.occurred_at.isoformat(),
        }
        try:
            redis = await get_async_redis_client()
            if redis is None:
                return
            await redis.publish(channel, json.dumps(payload))
        except Exception:
            logger.exception("Failed to publish activity log event to Redis channel %s", channel)
