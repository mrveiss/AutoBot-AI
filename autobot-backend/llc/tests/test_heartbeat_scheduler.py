"""Tests for HeartbeatScheduler (GH#8225).

Covers:
  1. _next_fire computes correct next epoch from a cron expression.
  2. repopulate_schedule adds enabled agents to Redis sorted set (NX).
  3. dispatch_due triggers _handle_due_agent for each due member.
  4. handle_due_agent creates a run record and advances the sorted-set score.
  5. trigger_manual creates a QUEUED run and returns it.
  6. Removed/disabled agent is dropped from the sorted set on next tick.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import HeartbeatRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.scheduler.heartbeat_scheduler import (
    _SCHEDULE_KEY,
    HeartbeatScheduler,
    _next_fire,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_COMPANY_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _make_agent(**kwargs):
    defaults = {
        "agent_id": "agent-abc",
        "company_id": _COMPANY_UUID,
        "name": "Test Agent",
        "heartbeat_cron": "*/5 * * * *",
        "heartbeat_enabled": True,
        "adapter_type": "noop",
        "adapter_config": None,
        "context_mode": "thin",
    }
    defaults.update(kwargs)
    return defaults


def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.zadd = AsyncMock(return_value=1)
    redis.zrangebyscore = AsyncMock(return_value=[])
    redis.zrem = AsyncMock(return_value=1)
    return redis


# ---------------------------------------------------------------------------
# _next_fire unit tests
# ---------------------------------------------------------------------------


class TestNextFire:
    def test_returns_float_in_future(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        result = _next_fire("*/5 * * * *", now)
        assert isinstance(result, float)
        assert result > now

    def test_every_5_min_lands_on_boundary(self):
        # 12:00:00 UTC — next boundary is 12:05
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        result = _next_fire("*/5 * * * *", base)
        dt = datetime.fromtimestamp(result, tz=timezone.utc)
        assert dt.minute == 5
        assert dt.second == 0

    def test_daily_midnight(self):
        base = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp()
        result = _next_fire("0 0 * * *", base)
        dt = datetime.fromtimestamp(result, tz=timezone.utc)
        assert dt.hour == 0 and dt.minute == 0
        assert dt > datetime.fromtimestamp(base, tz=timezone.utc)


# ---------------------------------------------------------------------------
# HeartbeatScheduler — schedule population
# ---------------------------------------------------------------------------


class TestRepopulateSchedule:
    @pytest.mark.asyncio
    async def test_adds_enabled_agents_to_sorted_set(self):
        scheduler = HeartbeatScheduler()
        agent = _make_agent()
        mock_redis = _make_redis()

        with (
            patch.object(scheduler, "_load_enabled_agents", new=AsyncMock(return_value=[agent])),
            patch.object(scheduler, "_restore_rate_limited_agents", new=AsyncMock()),
            patch(
                "llc.scheduler.heartbeat_scheduler.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
        ):
            await scheduler._repopulate_schedule()

        mock_redis.zadd.assert_called_once()
        call_kwargs = mock_redis.zadd.call_args
        assert call_kwargs[0][0] == _SCHEDULE_KEY
        assert "agent-abc" in call_kwargs[0][1]
        # GH#8498 changed NX to GT so cron-expression updates take effect.
        assert call_kwargs[1].get("gt") is True

    @pytest.mark.asyncio
    async def test_skips_invalid_cron(self):
        scheduler = HeartbeatScheduler()
        agent = _make_agent(heartbeat_cron="not-a-cron")
        mock_redis = _make_redis()

        with (
            patch.object(scheduler, "_load_enabled_agents", new=AsyncMock(return_value=[agent])),
            patch.object(scheduler, "_restore_rate_limited_agents", new=AsyncMock()),
            patch(
                "llc.scheduler.heartbeat_scheduler.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
        ):
            await scheduler._repopulate_schedule()

        mock_redis.zadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_noop_when_redis_unavailable(self):
        scheduler = HeartbeatScheduler()

        with patch(
            "llc.scheduler.heartbeat_scheduler.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            await scheduler._repopulate_schedule()  # should not raise


# ---------------------------------------------------------------------------
# HeartbeatScheduler — dispatch loop
# ---------------------------------------------------------------------------


class TestDispatchDue:
    @pytest.mark.asyncio
    async def test_calls_handle_for_each_due_agent(self):
        scheduler = HeartbeatScheduler()
        mock_redis = _make_redis()
        mock_redis.zrangebyscore = AsyncMock(return_value=[b"agent-abc", b"agent-def"])

        with (
            patch(
                "llc.scheduler.heartbeat_scheduler.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch.object(scheduler, "_handle_due_agent", new=AsyncMock()) as mock_handle,
        ):
            await scheduler._dispatch_due()

        assert mock_handle.call_count == 2
        agent_ids = {call[0][0] for call in mock_handle.call_args_list}
        assert agent_ids == {"agent-abc", "agent-def"}

    @pytest.mark.asyncio
    async def test_noop_when_no_due_agents(self):
        scheduler = HeartbeatScheduler()
        mock_redis = _make_redis()

        with (
            patch(
                "llc.scheduler.heartbeat_scheduler.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch.object(scheduler, "_handle_due_agent", new=AsyncMock()) as mock_handle,
        ):
            await scheduler._dispatch_due()

        mock_handle.assert_not_called()


# ---------------------------------------------------------------------------
# HeartbeatScheduler — handle_due_agent
# ---------------------------------------------------------------------------


class TestHandleDueAgent:
    @pytest.mark.asyncio
    async def test_creates_run_and_advances_score(self):
        scheduler = HeartbeatScheduler()
        agent = _make_agent()
        mock_redis = _make_redis()

        mock_run = MagicMock(spec=LLCHeartbeatRun)
        mock_run.id = uuid.uuid4()

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(scheduler, "_get_agent_config", new=AsyncMock(return_value=agent)),
            patch.object(scheduler, "_find_rate_limited_run", new=AsyncMock(return_value=None)),
            patch.object(scheduler, "_create_run", new=AsyncMock(return_value=mock_run)),
            patch.object(scheduler, "_run_adapter", new=AsyncMock()),
            patch(
                "llc.scheduler.heartbeat_scheduler.get_async_session_factory",
                return_value=mock_factory,
            ),
        ):
            await scheduler._handle_due_agent("agent-abc", mock_redis)

        mock_redis.zadd.assert_called_once()
        call_args = mock_redis.zadd.call_args
        assert call_args[0][0] == _SCHEDULE_KEY
        assert "agent-abc" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_removes_disabled_agent_from_set(self):
        scheduler = HeartbeatScheduler()
        mock_redis = _make_redis()

        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(scheduler, "_get_agent_config", new=AsyncMock(return_value=None)),
            patch(
                "llc.scheduler.heartbeat_scheduler.get_async_session_factory",
                return_value=mock_factory,
            ),
        ):
            await scheduler._handle_due_agent("agent-gone", mock_redis)

        mock_redis.zrem.assert_called_once_with(_SCHEDULE_KEY, "agent-gone")


# ---------------------------------------------------------------------------
# HeartbeatScheduler — trigger_manual
# ---------------------------------------------------------------------------


class TestTriggerManual:
    @pytest.mark.asyncio
    async def test_returns_queued_run(self):
        scheduler = HeartbeatScheduler()
        agent = _make_agent()

        mock_run = MagicMock(spec=LLCHeartbeatRun)
        mock_run.id = uuid.uuid4()
        mock_run.status = HeartbeatRunStatus.QUEUED.value

        mock_session = AsyncMock()
        mock_session.flush = AsyncMock()

        with (
            patch.object(scheduler, "_get_agent_config", new=AsyncMock(return_value=agent)),
            patch.object(scheduler, "_create_run", new=AsyncMock(return_value=mock_run)),
            patch.object(scheduler, "_run_adapter", new=AsyncMock()),
        ):
            run, agent_cfg = await scheduler.trigger_manual(mock_session, "agent-abc")

        assert run.id == mock_run.id
        assert run.status == HeartbeatRunStatus.QUEUED.value
        assert agent_cfg == agent

    @pytest.mark.asyncio
    async def test_raises_for_unknown_agent(self):
        scheduler = HeartbeatScheduler()
        mock_session = AsyncMock()

        with patch.object(scheduler, "_get_agent_config", new=AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="not found"):
                await scheduler.trigger_manual(mock_session, "agent-unknown")
