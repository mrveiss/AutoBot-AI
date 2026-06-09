# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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

from llc.adapters.base import AdapterRunStatus
from llc.exceptions import AdapterRunFailed
from llc.models.enums import LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.scheduler.heartbeat_scheduler import (
    _SCHEDULE_KEY,
    HeartbeatScheduler,
    _await_adapter_completion,
    _dispatch_adapter,
    _dispatch_autobot_agent,
    _dispatch_registry_adapter,
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
        mock_run.status = LLCRunStatus.QUEUED.value

        mock_session = AsyncMock()
        mock_session.flush = AsyncMock()

        with (
            patch.object(scheduler, "_get_agent_config", new=AsyncMock(return_value=agent)),
            patch.object(scheduler, "_create_run", new=AsyncMock(return_value=mock_run)),
            patch.object(scheduler, "_run_adapter", new=AsyncMock()),
        ):
            run, agent_cfg = await scheduler.trigger_manual(mock_session, "agent-abc")

        assert run.id == mock_run.id
        assert run.status == LLCRunStatus.QUEUED.value
        assert agent_cfg == agent

    @pytest.mark.asyncio
    async def test_raises_for_unknown_agent(self):
        scheduler = HeartbeatScheduler()
        mock_session = AsyncMock()

        with patch.object(scheduler, "_get_agent_config", new=AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="not found"):
                await scheduler.trigger_manual(mock_session, "agent-unknown")


# ---------------------------------------------------------------------------
# Adapter dispatch routing + run-scoped key lifecycle (GH#9622, GH#9623)
# ---------------------------------------------------------------------------

_HBS = "llc.scheduler.heartbeat_scheduler"


@pytest.mark.asyncio
class TestDispatchAdapterRouting:
    async def test_autobot_agent_routed_to_inproc_path(self):
        agent = _make_agent(adapter_type="autobot_agent")
        with (
            patch(f"{_HBS}._dispatch_autobot_agent", new=AsyncMock()) as mock_inproc,
            patch(f"{_HBS}._dispatch_registry_adapter", new=AsyncMock()) as mock_reg,
        ):
            await _dispatch_adapter(agent, {})
        mock_inproc.assert_awaited_once()
        mock_reg.assert_not_awaited()

    async def test_claude_code_routed_through_registry(self):
        agent = _make_agent(adapter_type="claude_code")
        fake_adapter = MagicMock()
        with (
            patch(f"{_HBS}.get_adapter", return_value=fake_adapter) as mock_get,
            patch(f"{_HBS}._dispatch_registry_adapter", new=AsyncMock()) as mock_reg,
        ):
            await _dispatch_adapter(agent, {})
        mock_get.assert_called_once_with("claude_code")
        mock_reg.assert_awaited_once()

    async def test_unknown_adapter_type_skipped(self):
        agent = _make_agent(adapter_type="does-not-exist")
        with (
            patch(f"{_HBS}.get_adapter", side_effect=KeyError("nope")),
            patch(f"{_HBS}._dispatch_registry_adapter", new=AsyncMock()) as mock_reg,
        ):
            await _dispatch_adapter(agent, {})
        mock_reg.assert_not_awaited()


@pytest.mark.asyncio
class TestRegistryAdapterKeyLifecycle:
    async def test_issues_injects_and_revokes_key(self):
        agent = _make_agent(adapter_type="claude_code")
        key_record = MagicMock()
        key_record.id = uuid.uuid4()
        captured: dict = {}

        async def fake_invoke(agent_config, context):
            captured.update(context)
            return "1234/session"

        fake_adapter = MagicMock()
        fake_adapter.invoke = AsyncMock(side_effect=fake_invoke)

        with (
            patch(f"{_HBS}._issue_run_key", new=AsyncMock(return_value=(key_record, "llc_rawkey"))),
            patch(f"{_HBS}._revoke_run_key", new=AsyncMock()) as mock_revoke,
            patch(f"{_HBS}._await_adapter_completion", new=AsyncMock(return_value=LLCRunStatus.COMPLETED)),
        ):
            await _dispatch_registry_adapter(fake_adapter, agent, {"recent_decisions": []})

        # Key + API base injected into the context handed to the adapter.
        assert captured["agent_api_key"] == "llc_rawkey"
        assert "api_base" in captured
        assert captured["agent_id"] == agent["agent_id"]
        # Key revoked after completion.
        mock_revoke.assert_awaited_once_with(agent["agent_id"], key_record.id)

    async def test_key_revoked_even_when_invoke_raises(self):
        agent = _make_agent(adapter_type="claude_code")
        key_record = MagicMock()
        key_record.id = uuid.uuid4()
        fake_adapter = MagicMock()
        fake_adapter.invoke = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch(f"{_HBS}._issue_run_key", new=AsyncMock(return_value=(key_record, "llc_rawkey"))),
            patch(f"{_HBS}._revoke_run_key", new=AsyncMock()) as mock_revoke,
            patch(f"{_HBS}._await_adapter_completion", new=AsyncMock()),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await _dispatch_registry_adapter(fake_adapter, agent, {})

        mock_revoke.assert_awaited_once_with(agent["agent_id"], key_record.id)

    async def test_no_company_id_dispatches_without_key(self):
        agent = _make_agent(adapter_type="claude_code", company_id=None)
        captured: dict = {}

        async def fake_invoke(agent_config, context):
            captured.update(context)
            return "1/s"

        fake_adapter = MagicMock()
        fake_adapter.invoke = AsyncMock(side_effect=fake_invoke)

        with (
            patch(f"{_HBS}._issue_run_key", new=AsyncMock()) as mock_issue,
            patch(f"{_HBS}._revoke_run_key", new=AsyncMock()) as mock_revoke,
            patch(f"{_HBS}._await_adapter_completion", new=AsyncMock(return_value=LLCRunStatus.COMPLETED)),
        ):
            await _dispatch_registry_adapter(fake_adapter, agent, {})

        mock_issue.assert_not_awaited()
        mock_revoke.assert_not_awaited()
        assert "agent_api_key" not in captured


@pytest.mark.asyncio
class TestAwaitAdapterCompletion:
    async def test_returns_when_terminal(self):
        fake_adapter = MagicMock()
        fake_adapter.status = AsyncMock(
            side_effect=[
                AdapterRunStatus(status=LLCRunStatus.RUNNING),
                AdapterRunStatus(status=LLCRunStatus.COMPLETED),
            ]
        )
        with patch(f"{_HBS}.asyncio.sleep", new=AsyncMock()):
            result = await _await_adapter_completion(fake_adapter, {"agent_id": "a"}, "1/s")
        assert result == LLCRunStatus.COMPLETED
        assert fake_adapter.status.await_count == 2

    async def test_cancels_on_max_wait(self):
        fake_adapter = MagicMock()
        fake_adapter.status = AsyncMock(return_value=AdapterRunStatus(status=LLCRunStatus.RUNNING))
        fake_adapter.cancel = AsyncMock()
        with patch(f"{_HBS}._ADAPTER_MAX_WAIT_SECONDS", 0):
            result = await _await_adapter_completion(fake_adapter, {"agent_id": "a"}, "1/s")
        assert result == LLCRunStatus.TIMEOUT
        fake_adapter.cancel.assert_awaited_once()


@pytest.mark.asyncio
class TestRegistryAdapterTerminalStatus:
    async def test_failed_terminal_status_raises_and_revokes(self):
        agent = _make_agent(adapter_type="claude_code")
        key_record = MagicMock()
        key_record.id = uuid.uuid4()
        fake_adapter = MagicMock()
        fake_adapter.invoke = AsyncMock(return_value="1/s")

        with (
            patch(f"{_HBS}._issue_run_key", new=AsyncMock(return_value=(key_record, "llc_k"))),
            patch(f"{_HBS}._revoke_run_key", new=AsyncMock()) as mock_revoke,
            patch(f"{_HBS}._await_adapter_completion", new=AsyncMock(return_value=LLCRunStatus.FAILED)),
        ):
            with pytest.raises(AdapterRunFailed):
                await _dispatch_registry_adapter(fake_adapter, agent, {})

        mock_revoke.assert_awaited_once_with(agent["agent_id"], key_record.id)

    async def test_completed_terminal_status_does_not_raise(self):
        agent = _make_agent(adapter_type="claude_code")
        fake_adapter = MagicMock()
        fake_adapter.invoke = AsyncMock(return_value="1/s")
        with (
            patch(f"{_HBS}._issue_run_key", new=AsyncMock(return_value=(None, None))),
            patch(f"{_HBS}._revoke_run_key", new=AsyncMock()),
            patch(f"{_HBS}._await_adapter_completion", new=AsyncMock(return_value=LLCRunStatus.COMPLETED)),
        ):
            await _dispatch_registry_adapter(fake_adapter, agent, {})  # no raise

    async def test_cancellation_cancels_run_and_revokes_key(self):
        agent = _make_agent(adapter_type="claude_code")
        key_record = MagicMock()
        key_record.id = uuid.uuid4()
        fake_adapter = MagicMock()
        fake_adapter.invoke = AsyncMock(return_value="9/s")
        fake_adapter.cancel = AsyncMock()

        with (
            patch(f"{_HBS}._issue_run_key", new=AsyncMock(return_value=(key_record, "llc_k"))),
            patch(f"{_HBS}._revoke_run_key", new=AsyncMock()) as mock_revoke,
            patch(
                f"{_HBS}._await_adapter_completion", new=AsyncMock(side_effect=__import__("asyncio").CancelledError())
            ),
        ):
            with pytest.raises(__import__("asyncio").CancelledError):
                await _dispatch_registry_adapter(fake_adapter, agent, {})

        fake_adapter.cancel.assert_awaited_once()
        mock_revoke.assert_awaited_once_with(agent["agent_id"], key_record.id)


@pytest.mark.asyncio
class TestDispatchAutobotAgent:
    async def test_skips_when_no_agent_class(self):
        agent = _make_agent(adapter_type="autobot_agent", adapter_config={})
        # No agent_class → graceful skip, no adapter instantiated.
        with patch(f"{_HBS}.AutoBotAgentAdapter") as mock_cls:
            await _dispatch_autobot_agent(agent, {})
        mock_cls.assert_not_called()

    async def test_runs_when_agent_class_present(self):
        agent = _make_agent(adapter_type="autobot_agent", adapter_config={"agent_class": "X"})
        mock_adapter = MagicMock()
        mock_adapter.run_blocking = AsyncMock()
        with patch(f"{_HBS}.AutoBotAgentAdapter", return_value=mock_adapter):
            await _dispatch_autobot_agent(agent, {})
        mock_adapter.run_blocking.assert_awaited_once()
