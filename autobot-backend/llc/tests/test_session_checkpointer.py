# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for SessionCheckpointer (GH#9026)."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.scheduler.session_checkpointer import SessionCheckpointer, recover_incomplete_runs


def _lease(*answers: bool | None) -> MagicMock:
    """The startup-recovery lease, answering each ask in turn: True this worker holds it, False another one does,
    None Redis did not answer. No answer given means held."""
    return MagicMock(hold_or_refresh=AsyncMock(side_effect=list(answers)) if answers else AsyncMock(return_value=True))


def _make_run(
    status: str = "running",
    work_item_id: str | None = None,
    agent_id: str = "agent-001",
    age: timedelta = timedelta(hours=1),
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
    run.started_at = datetime.now(timezone.utc) - age
    return run


def _make_factory(runs: list) -> MagicMock:
    from llc.tests._run_checkout_world import RoutedSession

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=RoutedSession(runs, []))
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
async def test_recover_incomplete_runs_marks_interrupted_releases_checkouts_requeues() -> None:
    """Startup recovery interrupts the run, gives back every checkout it made (#19601), and re-queues the agent."""
    import fakeredis

    from llc.tests._run_checkout_world import Item, RoutedSession

    run = _make_run(status="running")
    mine, theirs = Item(run.company_id, run.id), Item(run.company_id, uuid.uuid4())
    session = RoutedSession([run], [mine, theirs])
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    fences = fakeredis.aioredis.FakeRedis(decode_responses=True)
    for item in (mine, theirs):
        await fences.set(f"llc:checkout:{item.id}", item.fence)
    mock_redis = AsyncMock()
    mock_redis.zadd = AsyncMock()

    with (
        patch("llc.scheduler.session_checkpointer.recovery_lease", return_value=_lease()),
        patch("llc.scheduler.session_checkpointer.get_async_session_factory", return_value=factory),
        patch("llc.scheduler.session_checkpointer.get_async_redis_client", AsyncMock(return_value=mock_redis)),
        patch("llc.services.run_checkouts.get_async_redis_client", AsyncMock(return_value=fences)),
        patch("llc.services.run_checkouts._activity_log", MagicMock(record=AsyncMock())),
    ):
        await recover_incomplete_runs()

    assert run.status == "interrupted"
    assert run.finished_at is not None
    assert mine.checkout_run_id is None and mine.checkout_locked_at is None
    assert mine.status == "ready", "an interrupted run's unfinished item is claimable again"
    assert await fences.get(f"llc:checkout:{mine.id}") is None
    assert theirs.checkout_run_id is not None
    assert await fences.get(f"llc:checkout:{theirs.id}") == theirs.fence
    mock_redis.zadd.assert_called_once()
    zadd_args = mock_redis.zadd.call_args[0]
    assert zadd_args[0] == "llc:heartbeat:schedule"
    assert run.agent_id in zadd_args[1]


async def _recover_with(runs: list, items: list) -> tuple:
    """Run startup recovery over *runs*/*items* ; return the Redis re-queue mock."""
    import fakeredis

    from llc.tests._run_checkout_world import RoutedSession

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=RoutedSession(runs, items))
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    queue = AsyncMock()
    with (
        patch("llc.scheduler.session_checkpointer.recovery_lease", return_value=_lease()),
        patch("llc.scheduler.session_checkpointer.get_async_session_factory", return_value=factory),
        patch("llc.scheduler.session_checkpointer.get_async_redis_client", AsyncMock(return_value=queue)),
        patch(
            "llc.services.run_checkouts.get_async_redis_client",
            AsyncMock(return_value=fakeredis.aioredis.FakeRedis(decode_responses=True)),
        ),
        patch("llc.services.run_checkouts._activity_log", MagicMock(record=AsyncMock())),
    ):
        await recover_incomplete_runs()
    return queue


@pytest.mark.asyncio
async def test_a_full_restart_recovers_every_running_run_young_or_old() -> None:
    """Every in-flight run died with the workers: a run started a minute ago is recovered at once, not after 30."""
    from llc.tests._run_checkout_world import Item

    young = _make_run(age=timedelta(minutes=1))
    old = _make_run(age=timedelta(hours=1), agent_id="agent-old")
    held, theirs = Item(young.company_id, young.id), Item(old.company_id, old.id)

    queue = await _recover_with([young, old], [held, theirs])

    for run, item in ((young, held), (old, theirs)):
        assert run.status == "interrupted" and run.finished_at is not None
        assert item.checkout_run_id is None and item.status == "ready"
    requeued = {agent for call in queue.zadd.call_args_list for agent in call.args[1]}
    assert requeued == {young.agent_id, "agent-old"}


@pytest.mark.asyncio
async def test_a_worker_that_does_not_hold_the_recovery_lease_recovers_nothing() -> None:
    """Several uvicorn workers start; only the lease holder interrupts runs and clears their checkouts."""
    run = _make_run(status="running")
    factory = _make_factory([run])
    with (
        patch("llc.scheduler.session_checkpointer.recovery_lease", return_value=_lease(False)),
        patch("llc.scheduler.session_checkpointer.get_async_session_factory", return_value=factory),
    ):
        await recover_incomplete_runs()

    factory.assert_not_called()
    assert run.status == "running"


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
        patch("llc.scheduler.session_checkpointer.recovery_lease", return_value=_lease()),
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

    # #13113: asyncio.run() — pytest-asyncio owns the loop lifecycle, so a sync test
    # running before any async test on its worker had no current loop for get_event_loop().
    asyncio.run(_run())


@pytest.mark.asyncio
async def test_recovery_asks_again_while_redis_does_not_answer_and_then_recovers() -> None:
    """Redis down at boot is not "another worker holds the lease": the ask is repeated until it is answered."""
    run = _make_run(status="running")
    lease = _lease(None, None, True)
    with (
        patch("llc.scheduler.session_checkpointer.recovery_lease", return_value=lease),
        patch("llc.scheduler.session_checkpointer.asyncio.sleep", AsyncMock()),
        patch("llc.scheduler.session_checkpointer.get_async_session_factory", return_value=_make_factory([run])),
        patch("llc.scheduler.session_checkpointer.get_async_redis_client", AsyncMock(return_value=AsyncMock())),
    ):
        await recover_incomplete_runs()

    assert lease.hold_or_refresh.await_count == 3
    assert run.status == "interrupted"


@pytest.mark.asyncio
async def test_another_holder_ends_the_wait_at_once_and_an_unanswering_redis_gives_up_after_the_bound() -> None:
    from llc.scheduler import session_checkpointer as module

    other, silent = _lease(False), _lease(*[None] * module.RECOVERY_LEASE_ATTEMPTS)
    run = _make_run(status="running")
    factory = _make_factory([run])
    with (
        patch("llc.scheduler.session_checkpointer.asyncio.sleep", AsyncMock()),
        patch("llc.scheduler.session_checkpointer.get_async_session_factory", return_value=factory),
    ):
        for lease in (other, silent):
            with patch("llc.scheduler.session_checkpointer.recovery_lease", return_value=lease):
                await recover_incomplete_runs()

    assert other.hold_or_refresh.await_count == 1
    assert silent.hold_or_refresh.await_count == module.RECOVERY_LEASE_ATTEMPTS
    factory.assert_not_called()
    assert run.status == "running"


@pytest.mark.asyncio
async def test_a_run_whose_release_fails_is_rolled_back_and_not_requeued_or_unfenced() -> None:
    """One run's failed release leaves that run for the next recovery; the other runs still recover."""
    from llc.tests._run_checkout_world import RoutedSession

    bad, good = _make_run(agent_id="agent-bad"), _make_run(agent_id="agent-good")
    session = RoutedSession([bad, good], [])
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    queue, dropped = AsyncMock(), AsyncMock()

    async def release(_session, run, _why):  # noqa: ANN001
        if run is bad:
            raise RuntimeError("audit write failed")
        return []

    with (
        patch("llc.scheduler.session_checkpointer.recovery_lease", return_value=_lease()),
        patch("llc.scheduler.session_checkpointer.get_async_session_factory", return_value=factory),
        patch("llc.scheduler.session_checkpointer.get_async_redis_client", AsyncMock(return_value=queue)),
        patch("llc.scheduler.session_checkpointer.release_checkouts_for_run", release),
        patch("llc.scheduler.session_checkpointer.drop_released_fences", dropped),
    ):
        await recover_incomplete_runs()

    assert session.rollbacks == 1, "the failed run's work is undone to its savepoint"
    requeued = {agent for call in queue.zadd.call_args_list for agent in call.args[1]}
    assert requeued == {"agent-good"}
    assert good.status == "interrupted"
