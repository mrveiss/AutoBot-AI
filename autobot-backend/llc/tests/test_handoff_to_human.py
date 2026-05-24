"""Tests for HandoffService — agent-to-human handoff (GH#8231)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem, LLCWorkItemComment
from llc.services.handoff import HandoffNotAllowed, HandoffService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_item(**kwargs) -> LLCWorkItem:
    item_id = uuid.uuid4()
    defaults = {
        "id": item_id,
        "company_id": uuid.uuid4(),
        "identifier": "WI-001",
        "type": WorkItemType.TASK,
        "title": "Test task",
        "description": "Some description text",
        "status": WorkItemStatus.IN_PROGRESS,
        "priority": WorkItemPriority.MEDIUM,
        "version": 1,
        "labels": [],
        "acceptance_criteria": ["AC-1", "AC-2"],
        "checkout_run_id": "run-123",
        "checkout_locked_at": datetime.now(timezone.utc),
        "assignee_agent_id": None,
        "assignee_user_id": None,
        "reviewer_user_id": None,
        "reviewer_agent_id": None,
        "review_brief": None,
        "assignee_type": "agent",
        "started_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "created_at": None,
        "updated_at": None,
        "comments": [],
    }
    defaults.update(kwargs)
    item = MagicMock(spec=LLCWorkItem)
    for k, v in defaults.items():
        setattr(item, k, v)
    return item


@pytest.fixture
def service():
    return HandoffService()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    _db_result = MagicMock()
    session.execute = AsyncMock(return_value=_db_result)
    session._db_result = _db_result
    return session


# ---------------------------------------------------------------------------
# agent_to_human
# ---------------------------------------------------------------------------


class TestAgentToHuman:
    async def test_raises_if_work_item_not_found(self, service, mock_session):
        mock_session._db_result.scalar_one_or_none.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await service.agent_to_human(
                mock_session,
                work_item_id=str(uuid.uuid4()),
                agent_id=str(uuid.uuid4()),
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
            )

    async def test_raises_if_agent_does_not_hold_checkout(self, service, mock_session):
        agent_id = uuid.uuid4()
        other_agent_id = uuid.uuid4()
        item = _make_item(assignee_agent_id=other_agent_id)
        mock_session._db_result.scalar_one_or_none.return_value = item

        with pytest.raises(HandoffNotAllowed, match="does not hold checkout"):
            await service.agent_to_human(
                mock_session,
                work_item_id=str(item.id),
                agent_id=str(agent_id),
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(item.company_id),
            )

    async def test_raises_if_no_agent_assigned(self, service, mock_session):
        item = _make_item(assignee_agent_id=None)
        mock_session._db_result.scalar_one_or_none.return_value = item

        with pytest.raises(HandoffNotAllowed):
            await service.agent_to_human(
                mock_session,
                work_item_id=str(item.id),
                agent_id=str(uuid.uuid4()),
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(item.company_id),
            )

    async def test_sets_status_in_review_and_reviewer(self, service, mock_session):
        agent_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()
        item = _make_item(assignee_agent_id=agent_id)
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=None)):
            result = await service.agent_to_human(
                mock_session,
                work_item_id=str(item.id),
                agent_id=str(agent_id),
                reviewer_user_id=str(reviewer_id),
                company_id=str(item.company_id),
            )

        assert result.status == WorkItemStatus.IN_REVIEW
        assert str(result.reviewer_user_id) == str(reviewer_id)
        assert str(result.assignee_user_id) == str(reviewer_id)
        assert result.assignee_agent_id is None
        assert result.checkout_run_id is None

    async def test_generates_brief_with_required_fields(self, service, mock_session):
        agent_id = uuid.uuid4()
        item = _make_item(assignee_agent_id=agent_id, title="My work item")
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=None)):
            result = await service.agent_to_human(
                mock_session,
                work_item_id=str(item.id),
                agent_id=str(agent_id),
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(item.company_id),
                agent_notes="Work is done, please review",
            )

        brief = result.review_brief
        assert brief is not None
        assert brief["title"] == "My work item"
        assert brief["agent_notes"] == "Work is done, please review"
        assert brief["generator"] == "stub-phase4"
        assert "generated_at" in brief
        assert "acceptance_criteria" in brief

    async def test_increments_version(self, service, mock_session):
        agent_id = uuid.uuid4()
        item = _make_item(assignee_agent_id=agent_id, version=3)
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=None)):
            await service.agent_to_human(
                mock_session,
                work_item_id=str(item.id),
                agent_id=str(agent_id),
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(item.company_id),
            )

        assert item.version == 4

    async def test_deletes_redis_checkout_key(self, service, mock_session):
        agent_id = uuid.uuid4()
        item = _make_item(assignee_agent_id=agent_id)
        mock_session._db_result.scalar_one_or_none.return_value = item

        redis_mock = AsyncMock()
        with patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=redis_mock)):
            await service.agent_to_human(
                mock_session,
                work_item_id=str(item.id),
                agent_id=str(agent_id),
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(item.company_id),
            )

        redis_mock.delete.assert_called_once_with(f"llc:checkout:{item.id}")

    async def test_publishes_notification(self, service, mock_session):
        agent_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()
        company_id = uuid.uuid4()
        item = _make_item(assignee_agent_id=agent_id, company_id=company_id)
        mock_session._db_result.scalar_one_or_none.return_value = item

        redis_mock = AsyncMock()
        with patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=redis_mock)):
            await service.agent_to_human(
                mock_session,
                work_item_id=str(item.id),
                agent_id=str(agent_id),
                reviewer_user_id=str(reviewer_id),
                company_id=str(company_id),
            )

        redis_mock.publish.assert_called_once()
        channel, payload_str = redis_mock.publish.call_args[0]
        assert channel == f"llc:notifications:{company_id}"
        import json

        payload = json.loads(payload_str)
        assert payload["event_type"] == "work_item.handoff"
        assert payload["reviewer_user_id"] == str(reviewer_id)

    async def test_flushes_session(self, service, mock_session):
        agent_id = uuid.uuid4()
        item = _make_item(assignee_agent_id=agent_id)
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=None)):
            await service.agent_to_human(
                mock_session,
                work_item_id=str(item.id),
                agent_id=str(agent_id),
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(item.company_id),
            )

        mock_session.flush.assert_called()


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------


class TestApprove:
    async def test_raises_if_not_found(self, service, mock_session):
        mock_session._db_result.scalar_one_or_none.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await service.approve(
                mock_session,
                work_item_id=str(uuid.uuid4()),
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
            )

    async def test_raises_if_not_reviewer(self, service, mock_session):
        real_reviewer = uuid.uuid4()
        caller = uuid.uuid4()
        item = _make_item(reviewer_user_id=real_reviewer, status=WorkItemStatus.IN_REVIEW)
        mock_session._db_result.scalar_one_or_none.return_value = item

        with pytest.raises(HandoffNotAllowed, match="not the reviewer"):
            await service.approve(
                mock_session,
                work_item_id=str(item.id),
                reviewer_user_id=str(caller),
                company_id=str(item.company_id),
            )

    async def test_sets_status_done_and_completed_at(self, service, mock_session):
        reviewer_id = uuid.uuid4()
        item = _make_item(reviewer_user_id=reviewer_id, status=WorkItemStatus.IN_REVIEW)
        mock_session._db_result.scalar_one_or_none.return_value = item

        await service.approve(
            mock_session,
            work_item_id=str(item.id),
            reviewer_user_id=str(reviewer_id),
            company_id=str(item.company_id),
        )

        assert item.status == WorkItemStatus.DONE
        assert item.completed_at is not None
        assert item.assignee_user_id is None
        assert item.assignee_agent_id is None


# ---------------------------------------------------------------------------
# request_changes
# ---------------------------------------------------------------------------


class TestRequestChanges:
    async def test_raises_if_not_found(self, service, mock_session):
        mock_session._db_result.scalar_one_or_none.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await service.request_changes(
                mock_session,
                work_item_id=str(uuid.uuid4()),
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
                change_request="Please fix X",
            )

    async def test_raises_if_not_reviewer(self, service, mock_session):
        real_reviewer = uuid.uuid4()
        item = _make_item(reviewer_user_id=real_reviewer, status=WorkItemStatus.IN_REVIEW)
        mock_session._db_result.scalar_one_or_none.return_value = item

        with pytest.raises(HandoffNotAllowed):
            await service.request_changes(
                mock_session,
                work_item_id=str(item.id),
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(item.company_id),
                change_request="Fix Y",
            )

    async def test_sets_in_progress_and_clears_reviewer(self, service, mock_session):
        reviewer_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        item = _make_item(reviewer_user_id=reviewer_id, status=WorkItemStatus.IN_REVIEW)
        mock_session._db_result.scalar_one_or_none.return_value = item

        await service.request_changes(
            mock_session,
            work_item_id=str(item.id),
            reviewer_user_id=str(reviewer_id),
            company_id=str(item.company_id),
            change_request="Please refactor this",
            return_to_agent_id=str(agent_id),
        )

        assert item.status == WorkItemStatus.IN_PROGRESS
        assert item.reviewer_user_id is None
        assert item.review_brief is None
        assert str(item.assignee_agent_id) == str(agent_id)

    async def test_adds_comment_with_change_request(self, service, mock_session):
        reviewer_id = uuid.uuid4()
        item = _make_item(reviewer_user_id=reviewer_id, status=WorkItemStatus.IN_REVIEW)
        mock_session._db_result.scalar_one_or_none.return_value = item

        added_objects = []
        mock_session.add.side_effect = lambda obj: added_objects.append(obj)

        await service.request_changes(
            mock_session,
            work_item_id=str(item.id),
            reviewer_user_id=str(reviewer_id),
            company_id=str(item.company_id),
            change_request="Need more tests",
        )

        assert any(isinstance(obj, LLCWorkItemComment) and obj.body == "Need more tests" for obj in added_objects)


# ---------------------------------------------------------------------------
# get_brief
# ---------------------------------------------------------------------------


class TestGetBrief:
    async def test_returns_none_when_no_brief(self, service, mock_session):
        item = _make_item(review_brief=None)
        mock_session._db_result.scalar_one_or_none.return_value = item

        result = await service.get_brief(mock_session, str(item.id))
        assert result is None

    async def test_returns_brief_when_set(self, service, mock_session):
        brief = {"title": "Test", "generator": "stub-phase4"}
        item = _make_item(review_brief=brief)
        mock_session._db_result.scalar_one_or_none.return_value = item

        result = await service.get_brief(mock_session, str(item.id))
        assert result == brief

    async def test_raises_if_not_found(self, service, mock_session):
        mock_session._db_result.scalar_one_or_none.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await service.get_brief(mock_session, str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# _generate_brief
# ---------------------------------------------------------------------------


class TestGenerateBrief:
    def test_includes_all_required_fields(self):
        service = HandoffService()
        agent_id = uuid.uuid4()
        item = _make_item(
            assignee_agent_id=agent_id,
            title="My task",
            description="Some desc",
            acceptance_criteria=["AC-1"],
            comments=[],
        )
        brief = service._generate_brief(item, "notes here")

        assert brief["title"] == "My task"
        assert brief["agent_notes"] == "notes here"
        assert brief["generator"] == "stub-phase4"
        assert brief["acceptance_criteria"] == ["AC-1"]
        assert "generated_at" in brief

    def test_truncates_description_at_500(self):
        service = HandoffService()
        item = _make_item(description="x" * 1000)
        brief = service._generate_brief(item, None)
        assert len(brief["description_excerpt"]) <= 500

    def test_includes_recent_comments_up_to_5(self):
        service = HandoffService()
        comments = []
        for i in range(8):
            c = MagicMock(spec=LLCWorkItemComment)
            c.body = f"comment {i}"
            c.author_agent_id = None
            c.author_user_id = None
            comments.append(c)
        item = _make_item(comments=comments)
        brief = service._generate_brief(item, None)
        assert len(brief["recent_comments"]) == 5
        assert brief["comment_count"] == 8
