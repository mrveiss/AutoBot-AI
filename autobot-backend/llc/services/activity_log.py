# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC activity log service (GH#8216).

Single injectable service for all LLC mutations. All callers inject this
via LLCServiceBase.activity_log — never write to llc_activity_log directly.

Append-only guarantee: this service exposes no update() or delete() methods.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from autobot_shared.redis_client import get_async_redis_client

from ..models.activity import ActorType, LLCActivityLog
from ..models.enums import ActivityEventType
from .actor import ActivityRecordError, require_actor_id

logger = logging.getLogger(__name__)

_PUBSUB_CHANNEL_PREFIX = "llc:activity"
#: ``session.info`` key: rows written in the open transaction whose live event waits for its commit.
_ACTIVITY_PENDING_KEY = "llc_activity_pending_publish"
_ACTIVITY_HOOKED_KEY = "llc_activity_publish_hooked"
#: Strong references so a publish task is not collected before it runs.
_publish_tasks: set["asyncio.Task[None]"] = set()


def _spawn_publish(service: "LLCActivityLogService", company_id: str, payload: dict[str, Any]) -> None:
    task = asyncio.get_running_loop().create_task(service._deliver(company_id, payload))
    _publish_tasks.add(task)
    task.add_done_callback(_publish_tasks.discard)


def _send_committed_activity(sync_session: Session) -> None:
    """``after_commit``: publish each row that is now durable; a row since expunged is skipped.

    This event also fires when a SAVEPOINT is released, and that row can still be rolled back.
    """
    if sync_session.in_nested_transaction():
        return
    for service, company_id, entry, payload in sync_session.info.pop(_ACTIVITY_PENDING_KEY, []):
        if sa_inspect(entry).persistent:
            _spawn_publish(service, company_id, payload)


def _drop_undone(sync_session: Session) -> None:
    """``after_rollback`` (a SAVEPOINT's too): keep only rows still in the session; the rest were undone."""
    pending = sync_session.info.get(_ACTIVITY_PENDING_KEY, [])
    pending[:] = [item for item in pending if sa_inspect(item[2]).persistent]


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

        The live event is published after the caller's transaction commits and never for a
        rolled-back one (see :meth:`_publish_after_commit`).

        Returns:
            The persisted LLCActivityLog row (id and occurred_at populated).

        Raises:
            ValueError: ``actor_id`` is not a UUID -- the caller's input, checked before any write.
            ActivityRecordError: the row could not be built or flushed (a bad company or entity id,
                a failed flush). Deliberately not a ``ValueError``, which a route reads as the
                caller's error; every service's audit write fails the same way.
        """
        require_actor_id(actor_id)
        try:
            entry = self._build_entry(
                company_id, actor_type, actor_id, event_type, entity_type, entity_id, before, after, metadata
            )
            session.add(entry)
            await session.flush()
        except Exception as exc:
            raise ActivityRecordError(f"activity record failed: {exc}") from exc

        await self._publish_after_commit(session, company_id, entry)
        return entry

    @staticmethod
    def _parse_uuid(value: Any, label: str) -> uuid.UUID:
        try:
            return uuid.UUID(value) if isinstance(value, str) else value
        except ValueError as exc:
            raise ValueError(f"Invalid {label} UUID: {value!r}") from exc

    def _build_entry(
        self,
        company_id: str,
        actor_type: "ActorType | str",
        actor_id: str | None,
        event_type: "ActivityEventType | str",
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
    ) -> LLCActivityLog:
        actor_type_str = actor_type.value if isinstance(actor_type, ActorType) else actor_type
        actor = self._parse_uuid(actor_id, "actor_id") if actor_id is not None else None
        return LLCActivityLog(
            company_id=self._parse_uuid(company_id, "company_id"),
            actor_type=actor_type_str,
            actor_agent_id=actor if actor_type_str == ActorType.AGENT.value else None,
            actor_user_id=actor if actor_type_str == ActorType.USER.value else None,
            entity_type=entity_type,
            entity_id=self._parse_uuid(entity_id, "entity_id"),
            action=event_type.value if isinstance(event_type, ActivityEventType) else event_type,
            before_state=before,
            after_state=after or {},
            log_metadata=metadata,
            occurred_at=datetime.now(tz=timezone.utc),
        )

    async def record_bulk(
        self,
        session: AsyncSession,
        entries: list[dict[str, Any]],
    ) -> list[LLCActivityLog]:
        """Insert multiple activity log entries, one flush per entry.

        Each dict in ``entries`` must match the record() kwarg signature.
        All rows share the caller-owned session and transaction. Each call to
        record() flushes independently; every live event waits for the commit, so a
        rollback after record_bulk() returns publishes none of them.

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

    @staticmethod
    def _event_payload(entry: LLCActivityLog) -> dict[str, Any]:
        return {
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

    async def _publish_after_commit(self, session: AsyncSession, company_id: str, entry: LLCActivityLog) -> None:
        """Publish the live event once the caller's transaction commits; never for a rollback.

        The payload is captured now, while the row is loaded. The event is queued on the session
        and sent from its ``after_commit`` hook, which fires for any commit (``llc`` sessions are
        opened with ``get_session`` or ``get_async_session_factory()`` and committed by the caller,
        not through ``async_session_scope``, so ``run_after_commit`` has no list to queue on).
        A rollback clears the queue. An object that is not a real SQLAlchemy session has no
        commit to follow, so the event goes out at once, best-effort as always.
        """
        sync = getattr(session, "sync_session", None)
        if not isinstance(sync, Session):
            await self._publish(company_id, entry)
            return
        if not sync.info.get(_ACTIVITY_HOOKED_KEY):
            event.listen(sync, "after_commit", _send_committed_activity)
            event.listen(sync, "after_rollback", _drop_undone)
            sync.info[_ACTIVITY_HOOKED_KEY] = True
        sync.info.setdefault(_ACTIVITY_PENDING_KEY, []).append((self, company_id, entry, self._event_payload(entry)))

    async def _publish(self, company_id: str, entry: LLCActivityLog) -> None:
        """Publish *entry* now: see :meth:`_deliver`."""
        await self._deliver(company_id, self._event_payload(entry))

    async def _deliver(self, company_id: str, payload: dict[str, Any]) -> None:
        """Publish to /ws/live and Redis pub/sub channel llc:activity:{company_id}.

        Failures are logged but never raised -- publishing must not break writes. Called only
        after the commit (:meth:`_publish_after_commit`), so a rolled-back write publishes nothing.
        Subscribers should still treat events as hints: the commit can succeed and the publish fail.
        """
        channel = f"{_PUBSUB_CHANNEL_PREFIX}:{company_id}"
        # In-process fan-out to /ws/live subscribers on the valid channel
        # company:{id} (the raw-Redis channel below is not bridged into
        # LiveEventManager, so the CompanyDashboard feed needs this).
        try:
            from live_event_manager import publish_live_event

            await publish_live_event(f"company:{company_id}", "llc:activity_created", payload)
        except Exception:
            logger.exception("Failed to publish activity live event for company %s", company_id)

        try:
            redis = await get_async_redis_client()
            if redis is None:
                return
            await redis.publish(channel, json.dumps(payload))
        except Exception:
            logger.exception("Failed to publish activity log event to Redis channel %s", channel)
