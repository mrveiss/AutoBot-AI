# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SprintPlanningService — capacity, velocity history, burndown (GH#8220)."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from llc.models.enums import SprintStatus, WorkItemStatus
from llc.models.sprint import LLCSprint
from llc.models.work_item import LLCWorkItem
from llc.services.sprint_planning import SprintNotFound, SprintPlanningService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)
_SPRINT_ID = uuid.uuid4()
_PROJECT_ID = uuid.uuid4()
_COMPANY_ID = uuid.uuid4()
_AGENT_A = uuid.uuid4()
_AGENT_B = uuid.uuid4()


def _make_sprint(**kwargs) -> LLCSprint:
    defaults = {
        "id": _SPRINT_ID,
        "company_id": _COMPANY_ID,
        "project_id": _PROJECT_ID,
        "name": "Sprint 1",
        "goal": "Ship planning APIs",
        "status": SprintStatus.ACTIVE,
        "start_date": _NOW - timedelta(days=7),
        "end_date": _NOW + timedelta(days=7),
        "committed_points": 40,
    }
    defaults.update(kwargs)
    obj = MagicMock(spec=LLCSprint)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_item(**kwargs) -> LLCWorkItem:
    defaults = {
        "id": uuid.uuid4(),
        "sprint_id": _SPRINT_ID,
        "story_points": 5,
        "status": WorkItemStatus.IN_PROGRESS,
        "assignee_agent_id": None,
        "completed_at": None,
    }
    defaults.update(kwargs)
    obj = MagicMock(spec=LLCWorkItem)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _mock_session_returning(sprint=None, items=None, scalar_value=None):
    """Build a minimal AsyncMock session for service queries."""
    session = AsyncMock()

    async def _execute(stmt):
        result = MagicMock()
        if sprint is not None:
            result.scalar_one_or_none.return_value = sprint
        if items is not None:
            result.scalars.return_value.all.return_value = items
        if scalar_value is not None:
            result.scalar_one.return_value = scalar_value
        return result

    session.execute = _execute
    return session


@pytest.fixture
def service():
    return SprintPlanningService()


# ---------------------------------------------------------------------------
# get_capacity
# ---------------------------------------------------------------------------


class TestGetCapacity:
    async def test_sums_assigned_agent_points(self, service):
        sprint = _make_sprint()
        items = [
            _make_item(story_points=8, assignee_agent_id=_AGENT_A),
            _make_item(story_points=5, assignee_agent_id=_AGENT_B),
            _make_item(story_points=3, assignee_agent_id=_AGENT_A),
            _make_item(story_points=2, assignee_agent_id=None),
        ]

        calls = iter([sprint, items])

        async def _execute(stmt):
            r = MagicMock()
            val = next(calls)
            if isinstance(val, LLCSprint) or hasattr(val, "name"):
                r.scalar_one_or_none.return_value = val
            else:
                r.scalars.return_value.all.return_value = val
            return r

        session = AsyncMock()
        session.execute = _execute

        result = await service.get_capacity(session, str(_SPRINT_ID))

        assert result["total_points"] == 18
        assert result["assigned_points"] == 16
        assert result["unassigned_points"] == 2
        assert result["per_agent_points"][str(_AGENT_A)] == 11
        assert result["per_agent_points"][str(_AGENT_B)] == 5
        assert result["committed_points"] == 40
        assert result["item_count"] == 4

    async def test_sprint_not_found_raises(self, service):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with pytest.raises(SprintNotFound):
            await service.get_capacity(session, str(uuid.uuid4()))

    async def test_no_story_points_counts_zero(self, service):
        sprint = _make_sprint()
        items = [
            _make_item(story_points=None, assignee_agent_id=_AGENT_A),
            _make_item(story_points=0, assignee_agent_id=_AGENT_A),
        ]

        calls = iter([sprint, items])

        async def _execute(stmt):
            r = MagicMock()
            val = next(calls)
            if hasattr(val, "name"):
                r.scalar_one_or_none.return_value = val
            else:
                r.scalars.return_value.all.return_value = val
            return r

        session = AsyncMock()
        session.execute = _execute

        result = await service.get_capacity(session, str(_SPRINT_ID))
        assert result["total_points"] == 0
        assert result["assigned_points"] == 0


# ---------------------------------------------------------------------------
# get_velocity_history
# ---------------------------------------------------------------------------


class TestGetVelocityHistory:
    async def test_returns_velocity_per_sprint(self, service):
        s1 = _make_sprint(
            id=uuid.uuid4(),
            name="Sprint 3",
            status=SprintStatus.CLOSED,
            end_date=_NOW - timedelta(days=1),
        )
        s2 = _make_sprint(
            id=uuid.uuid4(),
            name="Sprint 2",
            status=SprintStatus.CLOSED,
            end_date=_NOW - timedelta(days=15),
        )

        # First call returns sprint list; second call returns GROUP BY velocity rows
        call_count = 0

        def _make_velocity_row(sprint_id, velocity):
            row = MagicMock()
            row.sprint_id = sprint_id
            row.velocity = velocity
            return row

        async def _execute(stmt):
            nonlocal call_count
            r = MagicMock()
            if call_count == 0:
                r.scalars.return_value.all.return_value = [s1, s2]
            else:
                # GROUP BY result — iterable rows with sprint_id + velocity
                r.__iter__ = MagicMock(
                    return_value=iter(
                        [
                            _make_velocity_row(s1.id, 30),
                            _make_velocity_row(s2.id, 20),
                        ]
                    )
                )
            call_count += 1
            return r

        session = AsyncMock()
        session.execute = _execute

        result = await service.get_velocity_history(session, str(_PROJECT_ID), n_sprints=2)

        assert result["n_sprints_returned"] == 2
        assert result["sprints"][0]["velocity"] == 30
        assert result["sprints"][1]["velocity"] == 20
        assert result["average_velocity"] == 25.0

    async def test_empty_history_when_no_closed_sprints(self, service):
        async def _execute(stmt):
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            return r

        session = AsyncMock()
        session.execute = _execute

        result = await service.get_velocity_history(session, str(_PROJECT_ID), n_sprints=5)

        assert result["n_sprints_returned"] == 0
        assert result["average_velocity"] is None
        assert result["sprints"] == []

    async def test_invalid_n_sprints_raises(self, service):
        session = AsyncMock()
        with pytest.raises(ValueError):
            await service.get_velocity_history(session, str(_PROJECT_ID), n_sprints=0)

        with pytest.raises(ValueError):
            await service.get_velocity_history(session, str(_PROJECT_ID), n_sprints=53)


# ---------------------------------------------------------------------------
# get_burndown
# ---------------------------------------------------------------------------


class TestGetBurndown:
    async def test_full_series_from_start_to_today(self, service):
        start = _NOW - timedelta(days=3)
        end = _NOW + timedelta(days=4)
        sprint = _make_sprint(start_date=start, end_date=end, status=SprintStatus.ACTIVE)

        # 3 items: 10 pts (completed day-1), 5 pts (completed day-2), 5 pts (open)
        items = [
            _make_item(
                story_points=10,
                status=WorkItemStatus.DONE,
                completed_at=start + timedelta(days=1),
            ),
            _make_item(
                story_points=5,
                status=WorkItemStatus.DONE,
                completed_at=start + timedelta(days=2),
            ),
            _make_item(story_points=5, status=WorkItemStatus.IN_PROGRESS, completed_at=None),
        ]

        calls = iter([sprint, items])

        async def _execute(stmt):
            r = MagicMock()
            val = next(calls)
            if hasattr(val, "name"):
                r.scalar_one_or_none.return_value = val
            else:
                r.scalars.return_value.all.return_value = val
            return r

        session = AsyncMock()
        session.execute = _execute

        result = await service.get_burndown(session, str(_SPRINT_ID))

        assert result["total_points"] == 20
        series = {entry["date"]: entry["remaining"] for entry in result["series"]}

        # Day 0 (start): 0 done → 20 remaining
        assert series[start.date().isoformat()] == 20
        # Day 1: 10 done → 10 remaining
        assert series[(start + timedelta(days=1)).date().isoformat()] == 10
        # Day 2: 15 done → 5 remaining
        assert series[(start + timedelta(days=2)).date().isoformat()] == 5
        # Day 3 (today): still 5 remaining (open item)
        assert series[(start + timedelta(days=3)).date().isoformat()] == 5

    async def test_no_start_date_returns_error(self, service):
        sprint = _make_sprint(start_date=None)

        async def _execute(stmt):
            r = MagicMock()
            r.scalar_one_or_none.return_value = sprint
            return r

        session = AsyncMock()
        session.execute = _execute

        result = await service.get_burndown(session, str(_SPRINT_ID))
        assert "error" in result
        assert result["series"] == []

    async def test_sprint_not_found_raises(self, service):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with pytest.raises(SprintNotFound):
            await service.get_burndown(session, str(uuid.uuid4()))

    async def test_remaining_never_goes_below_zero(self, service):
        start = _NOW - timedelta(days=1)
        end = _NOW + timedelta(days=1)
        sprint = _make_sprint(start_date=start, end_date=end)

        # Item completed before sprint started (anomaly) — should not produce negative
        items = [
            _make_item(
                story_points=5,
                status=WorkItemStatus.DONE,
                completed_at=start,
            ),
            _make_item(
                story_points=3,
                status=WorkItemStatus.DONE,
                completed_at=start,
            ),
        ]

        calls = iter([sprint, items])

        async def _execute(stmt):
            r = MagicMock()
            val = next(calls)
            if hasattr(val, "name"):
                r.scalar_one_or_none.return_value = val
            else:
                r.scalars.return_value.all.return_value = val
            return r

        session = AsyncMock()
        session.execute = _execute

        result = await service.get_burndown(session, str(_SPRINT_ID))
        for entry in result["series"]:
            assert entry["remaining"] >= 0
