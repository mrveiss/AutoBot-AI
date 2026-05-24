# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for provider rate-limit recovery in HeartbeatScheduler (GH#8502).

Covers:
  1. ProviderRateLimited exception carries provider name and retry hint.
  2. _handle_rate_limited writes rate_limited status + computed backoff.
  3. _handle_rate_limited uses provider retry_after_seconds hint when given.
  4. Exponential backoff is capped at _RL_MAX_SECONDS.
  5. After _MAX_RATE_LIMIT_RETRIES the run is demoted to FAILED.
  6. _handle_rate_limited re-queues the agent in Redis at retry_after.
  7. Redis score is NOT advanced past an earlier existing score (LT semantics).
  8. _handle_due_agent resumes a rate_limited run rather than creating a new one.
  9. _handle_due_agent creates a fresh run when no rate_limited run exists.
  10. _restore_rate_limited_agents re-queues active rate-limited agents on restart.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.exceptions import ProviderRateLimited
from llc.models.enums import HeartbeatRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.scheduler.heartbeat_scheduler import (
    HeartbeatScheduler,
    _MAX_RATE_LIMIT_RETRIES,
    _RL_BASE_SECONDS,
    _RL_MAX_SECONDS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPANY_UUID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_AGENT_ID = "agent-rl-test"
_RUN_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_agent(**kwargs):
    defaults = {
        "agent_id": _AGENT_ID,
        "company_id": _COMPANY_UUID,
        "name": "RL Test Agent",
        "heartbeat_cron": "*/5 * * * *",
        "heartbeat_enabled": True,
        "adapter_type": "noop",
        "adapter_config": None,
        "context_mode": "thin",
    }
    defaults.update(kwargs)
    return defaults


def _make_run(status=HeartbeatRunStatus.RATE_LIMITED.value, retry_count=1, retry_after=None):
    run = MagicMock(spec=LLCHeartbeatRun)
    run.id = _RUN_ID
    run.agent_id = _AGENT_ID
    run.company_id = _COMPANY_UUID
    run.status = status
    run.retry_count = retry_count
    run.retry_after = retry_after
    run.context_snapshot = {"work_item_id": "wi-123", "title": "Fix the thing"}
    run.created_at = datetime.now(tz=timezone.utc)
    return run


def _make_redis():
    redis = AsyncMock()
    redis.zadd = AsyncMock(return_value=1)
    redis.zrangebyscore = AsyncMock(return_value=[])
    redis.zrem = AsyncMock(return_value=1)
    redis.zscore = AsyncMock(return_value=None)
    return redis


# ---------------------------------------------------------------------------
# 1. ProviderRateLimited exception
# ---------------------------------------------------------------------------


def test_provider_rate_limited_no_hint():
    exc = ProviderRateLimited(provider="anthropic")
    assert exc.provider == "anthropic"
    assert exc.retry_after_seconds == 0
    assert "anthropic" in str(exc)


def test_provider_rate_limited_with_hint():
    exc = ProviderRateLimited(provider="openai", retry_after_seconds=120)
    assert exc.retry_after_seconds == 120
    assert "120s" in str(exc)


# ---------------------------------------------------------------------------
# 2–5. _handle_rate_limited backoff and demotion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_rate_limited_writes_status_and_requeues():
    """Verify rate_limited status is written and agent re-queued in Redis."""
    scheduler = HeartbeatScheduler()
    agent = _make_agent()
    exc = ProviderRateLimited(provider="anthropic")
    redis = _make_redis()

    session_mock = AsyncMock()
    session_mock.execute = AsyncMock()
    session_mock.commit = AsyncMock()

    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=session_mock)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("llc.scheduler.heartbeat_scheduler.get_async_session_factory", return_value=lambda: ctx_mgr),
        patch("llc.scheduler.heartbeat_scheduler.get_async_redis_client", AsyncMock(return_value=redis)),
    ):
        await scheduler._handle_rate_limited(agent, _RUN_ID, retry_count=0, exc=exc)

    # Status update was executed
    session_mock.execute.assert_called_once()
    call_args = session_mock.execute.call_args[0][0]
    compiled = call_args.compile(compile_kwargs={"literal_binds": True})
    assert HeartbeatRunStatus.RATE_LIMITED.value in str(compiled)

    # Agent re-queued in Redis
    redis.zadd.assert_called_once()
    zadd_mapping = redis.zadd.call_args[0][1]
    assert _AGENT_ID in zadd_mapping


@pytest.mark.asyncio
async def test_handle_rate_limited_uses_provider_hint():
    """Provider retry_after_seconds hint is used verbatim when > 0."""
    scheduler = HeartbeatScheduler()
    agent = _make_agent()
    exc = ProviderRateLimited(provider="anthropic", retry_after_seconds=7200)
    redis = _make_redis()

    session_mock = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=session_mock)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    now_ts = datetime.now(tz=timezone.utc).timestamp()

    with (
        patch("llc.scheduler.heartbeat_scheduler.get_async_session_factory", return_value=lambda: ctx_mgr),
        patch("llc.scheduler.heartbeat_scheduler.get_async_redis_client", AsyncMock(return_value=redis)),
    ):
        await scheduler._handle_rate_limited(agent, _RUN_ID, retry_count=0, exc=exc)

    zadd_mapping = redis.zadd.call_args[0][1]
    retry_ts = zadd_mapping[_AGENT_ID]
    assert abs(retry_ts - (now_ts + 7200)) < 5  # within 5s of expected


@pytest.mark.asyncio
async def test_handle_rate_limited_exponential_backoff():
    """Backoff doubles with retry_count and is capped at _RL_MAX_SECONDS."""
    scheduler = HeartbeatScheduler()
    agent = _make_agent()
    exc = ProviderRateLimited(provider="anthropic")
    redis = _make_redis()

    session_mock = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=session_mock)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    now_ts = datetime.now(tz=timezone.utc).timestamp()

    # retry_count=2 → delay = min(300 * 4, 14400) = 1200s
    with (
        patch("llc.scheduler.heartbeat_scheduler.get_async_session_factory", return_value=lambda: ctx_mgr),
        patch("llc.scheduler.heartbeat_scheduler.get_async_redis_client", AsyncMock(return_value=redis)),
    ):
        await scheduler._handle_rate_limited(agent, _RUN_ID, retry_count=2, exc=exc)

    zadd_mapping = redis.zadd.call_args[0][1]
    retry_ts = zadd_mapping[_AGENT_ID]
    expected_delay = min(_RL_BASE_SECONDS * (2**2), _RL_MAX_SECONDS)
    assert abs(retry_ts - (now_ts + expected_delay)) < 5


@pytest.mark.asyncio
async def test_handle_rate_limited_cap_at_max():
    """Backoff is capped at _RL_MAX_SECONDS regardless of retry_count."""
    scheduler = HeartbeatScheduler()
    agent = _make_agent()
    exc = ProviderRateLimited(provider="anthropic")
    redis = _make_redis()

    session_mock = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=session_mock)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    now_ts = datetime.now(tz=timezone.utc).timestamp()

    # retry_count=6 → uncapped = 300 * 2^6 = 19200 > _RL_MAX_SECONDS (14400)
    # Must be below _MAX_RATE_LIMIT_RETRIES so we don't hit the demotion path.
    assert 6 < _MAX_RATE_LIMIT_RETRIES
    with (
        patch("llc.scheduler.heartbeat_scheduler.get_async_session_factory", return_value=lambda: ctx_mgr),
        patch("llc.scheduler.heartbeat_scheduler.get_async_redis_client", AsyncMock(return_value=redis)),
    ):
        await scheduler._handle_rate_limited(agent, _RUN_ID, retry_count=6, exc=exc)

    zadd_mapping = redis.zadd.call_args[0][1]
    retry_ts = zadd_mapping[_AGENT_ID]
    assert abs(retry_ts - (now_ts + _RL_MAX_SECONDS)) < 5


@pytest.mark.asyncio
async def test_handle_rate_limited_demotes_after_max_retries():
    """After _MAX_RATE_LIMIT_RETRIES the run is demoted to FAILED, not re-queued."""
    scheduler = HeartbeatScheduler()
    agent = _make_agent()
    exc = ProviderRateLimited(provider="anthropic")
    redis = _make_redis()

    session_mock = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=session_mock)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("llc.scheduler.heartbeat_scheduler.get_async_session_factory", return_value=lambda: ctx_mgr),
        patch("llc.scheduler.heartbeat_scheduler.get_async_redis_client", AsyncMock(return_value=redis)),
    ):
        await scheduler._handle_rate_limited(
            agent, _RUN_ID, retry_count=_MAX_RATE_LIMIT_RETRIES, exc=exc
        )

    # FAILED written, not re-queued
    compiled = str(session_mock.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True}))
    assert HeartbeatRunStatus.FAILED.value in compiled
    redis.zadd.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Redis LT semantics — don't push retry further into the future
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_rate_limited_does_not_overwrite_earlier_redis_score():
    """If an earlier score already exists in Redis, zadd is skipped."""
    scheduler = HeartbeatScheduler()
    agent = _make_agent()
    exc = ProviderRateLimited(provider="anthropic")

    # Existing Redis score is 60s in the future (earlier than computed backoff)
    early_ts = datetime.now(tz=timezone.utc).timestamp() + 60
    redis = _make_redis()
    redis.zscore = AsyncMock(return_value=early_ts)

    session_mock = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=session_mock)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("llc.scheduler.heartbeat_scheduler.get_async_session_factory", return_value=lambda: ctx_mgr),
        patch("llc.scheduler.heartbeat_scheduler.get_async_redis_client", AsyncMock(return_value=redis)),
    ):
        await scheduler._handle_rate_limited(agent, _RUN_ID, retry_count=0, exc=exc)

    # Backoff (300s) > existing score (60s) — should NOT zadd
    redis.zadd.assert_not_called()


# ---------------------------------------------------------------------------
# 8–9. _handle_due_agent: resume vs fresh run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_due_agent_resumes_rate_limited_run():
    """When a rate_limited run exists, _handle_due_agent resumes it."""
    scheduler = HeartbeatScheduler()
    agent = _make_agent()
    redis = _make_redis()
    rate_limited_run = _make_run()

    session_mock = AsyncMock()
    session_mock.execute = AsyncMock()
    session_mock.commit = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=session_mock)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    mock_get_agent = AsyncMock(return_value=agent)
    mock_find_rl = AsyncMock(return_value=rate_limited_run)
    mock_create_run = AsyncMock()
    mock_run_adapter = AsyncMock()

    with (
        patch.object(scheduler, "_get_agent_config", mock_get_agent),
        patch.object(scheduler, "_find_rate_limited_run", mock_find_rl),
        patch.object(scheduler, "_create_run", mock_create_run),
        patch.object(scheduler, "_run_adapter", mock_run_adapter),
        patch("llc.scheduler.heartbeat_scheduler.get_async_session_factory", return_value=lambda: ctx_mgr),
    ):
        await scheduler._handle_due_agent(_AGENT_ID, redis)

        # _create_run must NOT have been called — we resumed the existing run
        mock_create_run.assert_not_called()

        # The resumed run's context_snapshot is passed to _run_adapter
        run_adapter_call = mock_run_adapter.call_args
        passed_context = run_adapter_call[0][2]  # third positional arg is context
        assert passed_context == rate_limited_run.context_snapshot


@pytest.mark.asyncio
async def test_handle_due_agent_creates_fresh_run_when_no_rate_limited():
    """When no rate_limited run exists, _handle_due_agent creates a new run."""
    scheduler = HeartbeatScheduler()
    agent = _make_agent()
    redis = _make_redis()
    fresh_run = _make_run(status=HeartbeatRunStatus.QUEUED.value, retry_count=0)
    fresh_run.context_snapshot = None

    session_mock = AsyncMock()
    session_mock.execute = AsyncMock()
    session_mock.commit = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=session_mock)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    mock_get_agent = AsyncMock(return_value=agent)
    mock_find_rl = AsyncMock(return_value=None)
    mock_create_run = AsyncMock(return_value=fresh_run)
    mock_run_adapter = AsyncMock()

    with (
        patch.object(scheduler, "_get_agent_config", mock_get_agent),
        patch.object(scheduler, "_find_rate_limited_run", mock_find_rl),
        patch.object(scheduler, "_create_run", mock_create_run),
        patch.object(scheduler, "_run_adapter", mock_run_adapter),
        patch("llc.scheduler.heartbeat_scheduler.get_async_session_factory", return_value=lambda: ctx_mgr),
    ):
        await scheduler._handle_due_agent(_AGENT_ID, redis)

        mock_create_run.assert_called_once()

        # Empty context passed when no rate_limited run exists
        run_adapter_call = mock_run_adapter.call_args
        passed_context = run_adapter_call[0][2]
        assert passed_context == {}


# ---------------------------------------------------------------------------
# 10. _restore_rate_limited_agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_rate_limited_agents_requeues_on_restart():
    """On restart, agents with active rate_limited runs are re-queued in Redis."""
    scheduler = HeartbeatScheduler()
    redis = _make_redis()

    future_dt = datetime(2099, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    rl_run = _make_run(retry_after=future_dt)

    session_mock = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [rl_run]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session_mock.execute = AsyncMock(return_value=result_mock)
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=session_mock)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "llc.scheduler.heartbeat_scheduler.get_async_session_factory",
        return_value=lambda: ctx_mgr,
    ):
        await scheduler._restore_rate_limited_agents(redis)

    redis.zadd.assert_called_once()
    zadd_mapping = redis.zadd.call_args[0][1]
    assert _AGENT_ID in zadd_mapping
    assert abs(zadd_mapping[_AGENT_ID] - future_dt.timestamp()) < 1
    # NX flag must be set so we don't overwrite an earlier score
    zadd_kwargs = redis.zadd.call_args[1]
    assert zadd_kwargs.get("nx") is True
