"""Tests for HandoffService.human_to_agent (GH#8232).

Verifies:
  1. human_to_agent sets status=ready and assigns to target agent.
  2. human_to_agent raises HandoffNotAuthorized when human does not hold item.
  3. human_to_agent raises HandoffNotAuthorized when item is agent-assigned.
  4. human_to_agent raises ValueError when item not found.
  5. human_notes are ingested into KB (WorkItemKB.ingest_notes called).
  6. Text attachments are ingested; binary attachments are skipped.
  7. review_brief is written with correct keys.
  8. Redis notification is published to llc:notifications:{company_id}.
  9. Redis checkout key is released after handoff.
  10. Activity log is recorded when activity_log is injected.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem
from llc.services.handoff import HandoffAttachment, HandoffNotAuthorized, HandoffService


def _make_item(**kwargs) -> MagicMock:
    user_id = str(uuid.uuid4())
    defaults = {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "identifier": "WI-200",
        "type": WorkItemType.TASK,
        "title": "Handoff task",
        "status": WorkItemStatus.IN_PROGRESS,
        "priority": WorkItemPriority.MEDIUM,
        "version": 1,
        "labels": [],
        "checkout_run_id": None,
        "checkout_locked_at": None,
        "assignee_agent_id": None,
        "assignee_user_id": uuid.UUID(user_id),
        "assignee_type": "user",
        "review_brief": None,
        "started_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "created_at": None,
        "updated_at": None,
        "_user_id": user_id,
    }
    defaults.update(kwargs)
    item = MagicMock(spec=LLCWorkItem)
    for k, v in defaults.items():
        if not k.startswith("_"):
            setattr(item, k, v)
    return item, defaults.get("_user_id", user_id)


@pytest.fixture
def service():
    return HandoffService()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    db_result = MagicMock()
    session.execute = AsyncMock(return_value=db_result)
    session._db_result = db_result
    return session


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()
    redis.publish = AsyncMock()
    return redis


def _patch_kb(ingest_notes_return="notes:wi-1", ingest_attachment_return="attachment:att-1"):
    kb_mock = AsyncMock()
    kb_mock.ingest_notes = AsyncMock(return_value=ingest_notes_return)
    kb_mock.ingest_attachment = AsyncMock(return_value=ingest_attachment_return)
    return kb_mock


class TestHumanToAgent:
    async def test_sets_status_ready_and_assigns_agent(self, service, mock_session, mock_redis):
        item, user_id = _make_item()
        target_agent = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        mock_session._db_result.scalar_one_or_none.return_value = item
        kb_mock = _patch_kb()

        with (
            patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
            patch("llc.kb.work_item_kb.WorkItemKB", return_value=kb_mock),
        ):
            result = await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=target_agent,
                user_id=user_id,
                company_id=company_id,
                human_notes="Please finish the migration",
                user_display="Alice",
            )

        assert item.status == WorkItemStatus.READY
        assert item.assignee_type == "agent"
        assert str(item.assignee_agent_id) == target_agent
        assert item.assignee_user_id is None
        assert item.version == 2
        assert result.target_agent_id == target_agent

    async def test_raises_not_authorized_when_no_holder(self, service, mock_session):
        item, _ = _make_item(assignee_type=None, assignee_user_id=None)
        mock_session._db_result.scalar_one_or_none.return_value = item

        with pytest.raises(HandoffNotAuthorized):
            await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
                human_notes="notes",
            )

    async def test_raises_not_authorized_when_agent_holds_item(self, service, mock_session):
        item, _ = _make_item(
            assignee_type="agent",
            assignee_agent_id=uuid.uuid4(),
            assignee_user_id=None,
        )
        mock_session._db_result.scalar_one_or_none.return_value = item

        with pytest.raises(HandoffNotAuthorized):
            await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
                human_notes="notes",
            )

    async def test_raises_not_authorized_when_different_user_holds(self, service, mock_session):
        item, _ = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item
        wrong_user = str(uuid.uuid4())

        with pytest.raises(HandoffNotAuthorized):
            await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=str(uuid.uuid4()),
                user_id=wrong_user,
                company_id=str(uuid.uuid4()),
                human_notes="notes",
            )

    async def test_raises_value_error_when_not_found(self, service, mock_session):
        mock_session._db_result.scalar_one_or_none.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.human_to_agent(
                mock_session,
                work_item_id=str(uuid.uuid4()),
                target_agent_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
                human_notes="notes",
            )

    async def test_kb_notes_ingested(self, service, mock_session, mock_redis):
        item, user_id = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item
        kb_mock = _patch_kb(ingest_notes_return=f"notes:{item.id}")

        with (
            patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
            patch("llc.kb.work_item_kb.WorkItemKB", return_value=kb_mock),
        ):
            result = await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=str(uuid.uuid4()),
                user_id=user_id,
                company_id=str(uuid.uuid4()),
                human_notes="Please migrate the table schema",
            )

        kb_mock.ingest_notes.assert_called_once_with(
            work_item_id=str(item.id),
            notes="Please migrate the table schema",
            source_user_id=user_id,
        )
        assert f"notes:{item.id}" in result.kb_doc_ids

    async def test_text_attachment_indexed_binary_skipped(self, service, mock_session, mock_redis):
        item, user_id = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item
        kb_mock = _patch_kb()
        kb_mock.ingest_attachment = AsyncMock(side_effect=["attachment:att-text", None])

        text_att = HandoffAttachment(
            attachment_id="att-text",
            filename="schema.sql",
            content="ALTER TABLE ...",
            mime_type="text/plain",
        )
        binary_att = HandoffAttachment(
            attachment_id="att-bin",
            filename="image.png",
            content="<binary>",
            mime_type="image/png",
        )

        with (
            patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
            patch("llc.kb.work_item_kb.WorkItemKB", return_value=kb_mock),
        ):
            result = await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=str(uuid.uuid4()),
                user_id=user_id,
                company_id=str(uuid.uuid4()),
                human_notes="See attachments",
                attachments=[text_att, binary_att],
            )

        assert "attachment:att-text" in result.kb_doc_ids
        assert None not in result.kb_doc_ids

    async def test_review_brief_written_correctly(self, service, mock_session, mock_redis):
        item, user_id = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item
        kb_mock = _patch_kb()

        with (
            patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
            patch("llc.kb.work_item_kb.WorkItemKB", return_value=kb_mock),
        ):
            result = await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=str(uuid.uuid4()),
                user_id=user_id,
                company_id=str(uuid.uuid4()),
                human_notes="Important context",
                user_display="Bob",
            )

        assert result.review_brief["handed_off_by"] == "Bob"
        assert result.review_brief["notes"] == "Important context"
        assert result.review_brief["kb_indexed"] is True
        assert item.review_brief == result.review_brief

    async def test_redis_notification_published(self, service, mock_session, mock_redis):
        item, user_id = _make_item()
        company_id = str(uuid.uuid4())
        target_agent = str(uuid.uuid4())
        mock_session._db_result.scalar_one_or_none.return_value = item
        kb_mock = _patch_kb()

        with (
            patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
            patch("llc.kb.work_item_kb.WorkItemKB", return_value=kb_mock),
        ):
            await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=target_agent,
                user_id=user_id,
                company_id=company_id,
                human_notes="Notes",
            )

        mock_redis.publish.assert_called_once()
        channel, payload_json = mock_redis.publish.call_args[0]
        assert channel == f"llc:notifications:{company_id}"
        import json

        payload = json.loads(payload_json)
        assert payload["event"] == "work_item.handoff_ready"
        assert payload["work_item_id"] == str(item.id)
        assert payload["target_agent_id"] == target_agent
        assert payload["has_human_handoff_context"] is True

    async def test_redis_checkout_key_released(self, service, mock_session, mock_redis):
        item, user_id = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item
        mock_redis.get = AsyncMock(return_value=f"user:{user_id}")
        kb_mock = _patch_kb()

        with (
            patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
            patch("llc.kb.work_item_kb.WorkItemKB", return_value=kb_mock),
        ):
            await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=str(uuid.uuid4()),
                user_id=user_id,
                company_id=str(uuid.uuid4()),
                human_notes="Notes",
            )

        mock_redis.delete.assert_called_once_with(f"llc:checkout:{item.id}")

    async def test_activity_log_recorded_when_injected(self, service, mock_session, mock_redis):
        item, user_id = _make_item()
        company_id = str(uuid.uuid4())
        mock_session._db_result.scalar_one_or_none.return_value = item
        kb_mock = _patch_kb()

        activity_log = AsyncMock()
        activity_log.record = AsyncMock()
        service.activity_log = activity_log

        with (
            patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=mock_redis)),
            patch("llc.kb.work_item_kb.WorkItemKB", return_value=kb_mock),
        ):
            await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=str(uuid.uuid4()),
                user_id=user_id,
                company_id=company_id,
                human_notes="Notes",
            )

        activity_log.record.assert_called_once()
        call_kwargs = activity_log.record.call_args[1]
        assert call_kwargs["actor_type"] == "user"
        assert call_kwargs["actor_id"] == user_id
        assert call_kwargs["entity_id"] == str(item.id)

    async def test_no_redis_does_not_raise(self, service, mock_session):
        item, user_id = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item
        kb_mock = _patch_kb()

        with (
            patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=None)),
            patch("llc.kb.work_item_kb.WorkItemKB", return_value=kb_mock),
        ):
            result = await service.human_to_agent(
                mock_session,
                work_item_id=str(item.id),
                target_agent_id=str(uuid.uuid4()),
                user_id=user_id,
                company_id=str(uuid.uuid4()),
                human_notes="Notes without redis",
            )

        assert result.work_item_id == str(item.id)
