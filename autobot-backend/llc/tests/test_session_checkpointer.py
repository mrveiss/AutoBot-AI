# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for SessionCheckpointer (GH#9026)."""

import json
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.scheduler.session_checkpointer import SessionCheckpointer, recover_incomplete_runs


def _make_run(
    status: str = "running",
    work_item_id: str | None = None,
    agent_id: str = "agent-001",
) -> MagicMock:
    run = MagicMock()
    run.id = uuid.uuid4()
    run.agent_id = agent_id
    run.company_id = uuid.uuid4()
    run.status = status
    run.work_item_id = uuid.UUID(work_item_id) if work_item_id else None
    run.external_run_id = None
    run.context_snapshot = None
    run.finished_at = None
    return run


def _make_factory(runs: list) -> MagicMock:
    session = AsyncMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = runs
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    session.execute.return_value = execute_result
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


@pytest.mark.asyncio
async def test_write_checkpoint_correct_key_ttl_payload() -> None:
    """_write_checkpoint writes the correct key, TTL, and payload to Redis."""
    run = _make_run()
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()

    checkpointer = SessionCheckpointer(poll_interval=9999)

    with patch(
        "llc.scheduler.session_checkpointer.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis,
    ):
        await checkpointer._write_checkpoint(run)

    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    key = call_args[0][0]
    raw_payload = call_args[0][1]
    ex = call_args[1]["ex"]

    assert key == f"llc:session:checkpoint:{run.id}"
    assert ex > 0

    payload = json.loads(raw_payload)
    assert payload["run_id"] == str(run.id)
    assert payload["agent_id"] == run.agent_id
    assert payload["company_id"] == str(run.company_id)
    assert payload["work_item_id"] is None
    assert "checkpoint_at" in payload


@pytest.mark.asyncio
async def test_recover_incomplete_runs_marks_interrupted_releases_lock_requeues() -> None:
    """recover_incomplete_runs marks run interrupted, releases checkout lock, re-queues agent."""
    wid = str(uuid.uuid4())
    run = _make_run(status="running", work_item_id=wid)
    factory = _make_factory([run])

    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock()
    mock_redis.zadd = AsyncMock()

    with (
        patch("llc.scheduler.session_checkpointer.get_async_session_factory", return_value=factory),
        patch(
            "llc.scheduler.session_checkpointer.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ),
    ):
        await recover_incomplete_runs()

    assert run.status == "interrupted"
    assert run.finished_at is not None
    mock_redis.delete.assert_called_once_with(f"llc:checkout:{wid}")
    mock_redis.zadd.assert_called_once()
    zadd_args = mock_redis.zadd.call_args[0]
    assert zadd_args[0] == "llc:heartbeat:schedule"
    assert run.agent_id in zadd_args[1]


@pytest.mark.asyncio
async def test_recover_incomplete_runs_idempotent() -> None:
    """recover_incomplete_runs is safe to call twice — second call is a no-op."""
    run = _make_run(status="running")
    factory_first = _make_factory([run])
    factory_second = _make_factory([])  # second call finds no running runs

    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock()
    mock_redis.zadd = AsyncMock()

    with (
        patch(
            "llc.scheduler.session_checkpointer.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ),
    ):
        with patch(
            "llc.scheduler.session_checkpointer.get_async_session_factory",
            return_value=factory_first,
        ):
            await recover_incomplete_runs()

        assert run.status == "interrupted"
        first_zadd_count = mock_redis.zadd.call_count

        with patch(
            "llc.scheduler.session_checkpointer.get_async_session_factory",
            return_value=factory_second,
        ):
            await recover_incomplete_runs()

    # Second call found no runs; zadd count unchanged
    assert mock_redis.zadd.call_count == first_zadd_count


@pytest.mark.asyncio
async def test_session_recovery_available_true_when_checkpoint_key_exists() -> None:
    """_session_recovery_available returns True when a checkpoint key is present."""
    from llc.health.probe import _session_recovery_available

    mock_redis = AsyncMock()
    mock_redis.scan = AsyncMock(return_value=(0, [b"llc:session:checkpoint:abc123"]))

    with patch(
        "llc.health.probe.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis,
    ):
        result = await _session_recovery_available()

    assert result is True


@pytest.mark.asyncio
async def test_session_recovery_available_false_when_no_keys() -> None:
    """_session_recovery_available returns False when no checkpoint keys exist."""
    from llc.health.probe import _session_recovery_available

    mock_redis = AsyncMock()
    mock_redis.scan = AsyncMock(return_value=(0, []))

    with patch(
        "llc.health.probe.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis,
    ):
        result = await _session_recovery_available()

    assert result is False


def test_checkpointer_start_stop() -> None:
    """SessionCheckpointer.start() creates a task; stop() cancels it."""
    import asyncio

    async def _run():
        checkpointer = SessionCheckpointer(poll_interval=9999)
        with patch("llc.scheduler.session_checkpointer.get_async_session_factory"):
            checkpointer.start()
            assert checkpointer._task is not None
            assert not checkpointer._task.done()
            checkpointer.stop()
            assert not checkpointer._running

    asyncio.get_event_loop().run_until_complete(_run())
