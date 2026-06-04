"""Tests for LLC activity log service and API (GH#8216).

Covers:
- record() persists a row with correct fields
- record() resolves actor_agent_id / actor_user_id by actor_type
- record() publishes to Redis pub/sub
- record_bulk() inserts all entries
- No UPDATE or DELETE exposed by LLCActivityLogService
- query() filters by entity_type, entity_id, action, actor_type, actor_id, date range
- query() paginates correctly
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.activity import ActorType, LLCActivityLog
from llc.services.activity_log import (
    ActivityEventType,
    ActivityLogQuery,
    LLCActivityLogService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> LLCActivityLogService:
    return LLCActivityLogService()


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Unit tests (in-memory, mocked session)
# ---------------------------------------------------------------------------


class TestRecordUnit:
    """Unit tests with a mocked AsyncSession — no DB required."""

    def _mocked_session(self) -> AsyncSession:
        session = AsyncMock(spec=AsyncSession)
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_record_sets_actor_agent_id_for_agent_type(self) -> None:
        svc = _make_service()
        session = self._mocked_session()
        company_id = _uuid()
        agent_id = _uuid()

        with patch.object(svc, "_publish", AsyncMock()):
            row = await svc.record(
                session=session,
                company_id=company_id,
                actor_type=ActorType.AGENT,
                actor_id=agent_id,
                event_type=ActivityEventType.WORK_ITEM_CREATED,
                entity_type="work_item",
                entity_id=_uuid(),
                after={"status": "todo"},
            )

        assert str(row.actor_agent_id) == agent_id
        assert row.actor_user_id is None
        assert row.actor_type == "agent"

    @pytest.mark.asyncio
    async def test_record_sets_actor_user_id_for_user_type(self) -> None:
        svc = _make_service()
        session = self._mocked_session()
        user_id = _uuid()

        with patch.object(svc, "_publish", AsyncMock()):
            row = await svc.record(
                session=session,
                company_id=_uuid(),
                actor_type=ActorType.USER,
                actor_id=user_id,
                event_type=ActivityEventType.COMPANY_UPDATED,
                entity_type="company",
                entity_id=_uuid(),
                after={"name": "NewName"},
            )

        assert str(row.actor_user_id) == user_id
        assert row.actor_agent_id is None
        assert row.actor_type == "user"

    @pytest.mark.asyncio
    async def test_record_system_has_no_actor_ids(self) -> None:
        svc = _make_service()
        session = self._mocked_session()

        with patch.object(svc, "_publish", AsyncMock()):
            row = await svc.record(
                session=session,
                company_id=_uuid(),
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                event_type=ActivityEventType.HEARTBEAT_STARTED,
                entity_type="heartbeat",
                entity_id=_uuid(),
                after={},
            )

        assert row.actor_agent_id is None
        assert row.actor_user_id is None
        assert row.actor_type == "system"

    @pytest.mark.asyncio
    async def test_record_action_stored_as_string(self) -> None:
        svc = _make_service()
        session = self._mocked_session()

        with patch.object(svc, "_publish", AsyncMock()):
            row = await svc.record(
                session=session,
                company_id=_uuid(),
                actor_type=ActorType.AGENT,
                actor_id=_uuid(),
                event_type=ActivityEventType.SPRINT_STARTED,
                entity_type="sprint",
                entity_id=_uuid(),
                after={"status": "active"},
            )

        assert row.action == "sprint.started"

    @pytest.mark.asyncio
    async def test_record_publishes_to_redis_on_success(self) -> None:
        svc = _make_service()
        session = self._mocked_session()
        company_id = _uuid()

        published_calls: list = []

        async def fake_publish(cid: str, row: LLCActivityLog) -> None:
            published_calls.append((cid, row))

        with patch.object(svc, "_publish", side_effect=fake_publish):
            await svc.record(
                session=session,
                company_id=company_id,
                actor_type=ActorType.AGENT,
                actor_id=_uuid(),
                event_type=ActivityEventType.AGENT_HIRED,
                entity_type="agent",
                entity_id=_uuid(),
                after={"status": "active"},
            )

        assert len(published_calls) == 1
        assert published_calls[0][0] == company_id

    @pytest.mark.asyncio
    async def test_record_bulk_returns_all_rows(self) -> None:
        svc = _make_service()
        session = self._mocked_session()
        company_id = _uuid()

        entries = [
            {
                "company_id": company_id,
                "actor_type": ActorType.AGENT,
                "actor_id": _uuid(),
                "event_type": ActivityEventType.WORK_ITEM_CREATED,
                "entity_type": "work_item",
                "entity_id": _uuid(),
                "after": {"status": "todo"},
            },
            {
                "company_id": company_id,
                "actor_type": ActorType.AGENT,
                "actor_id": _uuid(),
                "event_type": ActivityEventType.WORK_ITEM_STATUS_CHANGED,
                "entity_type": "work_item",
                "entity_id": _uuid(),
                "before": {"status": "todo"},
                "after": {"status": "in_progress"},
            },
        ]

        with patch.object(svc, "_publish", AsyncMock()):
            rows = await svc.record_bulk(session=session, entries=entries)

        assert len(rows) == 2
        assert rows[0].action == "work_item.created"
        assert rows[1].action == "work_item.status_changed"

    @pytest.mark.asyncio
    async def test_record_does_not_expose_update_or_delete(self) -> None:
        svc = LLCActivityLogService()
        assert not hasattr(svc, "update"), "update() must not exist on LLCActivityLogService"
        assert not hasattr(svc, "delete"), "delete() must not exist on LLCActivityLogService"
        assert not hasattr(svc, "bulk_delete"), "bulk_delete() must not exist on LLCActivityLogService"

    @pytest.mark.asyncio
    async def test_publish_swallows_redis_errors(self) -> None:
        svc = _make_service()
        company_id = _uuid()
        entry = LLCActivityLog(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            actor_type="agent",
            entity_type="work_item",
            entity_id=uuid.uuid4(),
            action="work_item.created",
            after_state={},
            occurred_at=datetime.now(tz=timezone.utc),
        )

        with patch(
            "llc.services.activity_log.get_async_redis_client",
            AsyncMock(side_effect=Exception("Redis down")),
        ):
            # Must not raise
            await svc._publish(company_id, entry)

    @pytest.mark.asyncio
    async def test_publish_sends_correct_channel(self) -> None:
        svc = _make_service()
        company_id = _uuid()
        entry = LLCActivityLog(
            id=uuid.uuid4(),
            company_id=uuid.UUID(company_id),
            actor_type="agent",
            actor_agent_id=uuid.uuid4(),
            entity_type="work_item",
            entity_id=uuid.uuid4(),
            action="work_item.created",
            after_state={"status": "todo"},
            occurred_at=datetime.now(tz=timezone.utc),
        )

        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        with patch(
            "llc.services.activity_log.get_async_redis_client",
            AsyncMock(return_value=mock_redis),
        ):
            await svc._publish(company_id, entry)

        mock_redis.publish.assert_called_once()
        channel_arg = mock_redis.publish.call_args[0][0]
        assert channel_arg == f"llc:activity:{company_id}"

        payload_arg = json.loads(mock_redis.publish.call_args[0][1])
        assert payload_arg["action"] == "work_item.created"
        assert payload_arg["company_id"] == company_id


# ---------------------------------------------------------------------------
# Query unit tests (mocked execute)
# ---------------------------------------------------------------------------


class TestQueryUnit:
    """Unit tests for query() with mocked DB execute."""

    def _mocked_session_with_rows(self, rows: list[LLCActivityLog], total: int) -> AsyncSession:
        session = AsyncMock(spec=AsyncSession)

        count_result = MagicMock()
        count_result.scalar_one.return_value = total

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = rows

        session.execute = AsyncMock(side_effect=[count_result, rows_result])
        return session

    @pytest.mark.asyncio
    async def test_query_returns_page_with_correct_total(self) -> None:
        svc = _make_service()
        fake_row = LLCActivityLog(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            actor_type="agent",
            entity_type="work_item",
            entity_id=uuid.uuid4(),
            action="work_item.created",
            after_state={},
            occurred_at=datetime.now(tz=timezone.utc),
        )
        session = self._mocked_session_with_rows([fake_row], total=1)
        company_id = _uuid()

        page = await svc.query(session=session, company_id=company_id)

        assert page.total == 1
        assert page.page == 1
        assert len(page.items) == 1
        assert not page.has_next

    @pytest.mark.asyncio
    async def test_query_has_next_when_more_pages(self) -> None:
        svc = _make_service()
        session = self._mocked_session_with_rows([], total=200)

        page = await svc.query(
            session=session,
            company_id=_uuid(),
            params=ActivityLogQuery(page=1, page_size=50),
        )

        assert page.has_next is True

    @pytest.mark.asyncio
    async def test_query_page_size_capped_at_200(self) -> None:
        params = ActivityLogQuery(page_size=999)
        assert params.page_size == 200

    @pytest.mark.asyncio
    async def test_query_page_minimum_is_1(self) -> None:
        params = ActivityLogQuery(page=0)
        assert params.page == 1

    @pytest.mark.asyncio
    async def test_query_raises_on_invalid_company_uuid(self) -> None:
        svc = _make_service()
        session = AsyncMock(spec=AsyncSession)
        with pytest.raises(ValueError, match="Invalid company_id UUID"):
            await svc.query(session=session, company_id="not-a-uuid")

    @pytest.mark.asyncio
    async def test_query_raises_on_invalid_entity_uuid(self) -> None:
        svc = _make_service()
        session = AsyncMock(spec=AsyncSession)
        with pytest.raises(ValueError, match="Invalid entity_id UUID"):
            await svc.query(
                session=session,
                company_id=_uuid(),
                params=ActivityLogQuery(entity_id="not-a-uuid"),
            )


class TestRecordUUIDValidation:
    """Unit tests for UUID validation in record()."""

    def _mocked_session(self) -> AsyncSession:
        session = AsyncMock(spec=AsyncSession)
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_record_raises_on_invalid_company_uuid(self) -> None:
        svc = _make_service()
        with pytest.raises(ValueError, match="Invalid company_id UUID"):
            await svc.record(
                session=self._mocked_session(),
                company_id="bad-uuid",
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                event_type="heartbeat.started",
                entity_type="heartbeat",
                entity_id=_uuid(),
            )

    @pytest.mark.asyncio
    async def test_record_raises_on_invalid_entity_uuid(self) -> None:
        svc = _make_service()
        with pytest.raises(ValueError, match="Invalid entity_id UUID"):
            await svc.record(
                session=self._mocked_session(),
                company_id=_uuid(),
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                event_type="heartbeat.started",
                entity_type="heartbeat",
                entity_id="bad-uuid",
            )
