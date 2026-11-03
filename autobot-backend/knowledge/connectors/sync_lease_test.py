# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20556: a connector runs one sync at a time, and other connectors are unaffected."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.connectors import sync_lease


class _Redis:
    """The Redis calls the lease makes, against a dict."""

    def __init__(self) -> None:
        self.keys: dict = {}

    async def set(self, key, value, nx=False, px=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    async def ping(self):
        return True

    async def eval(self, _script, _count, key, value, _ttl):
        return int(self.keys.get(key) == value)


@pytest.fixture
def redis():
    fake = _Redis()

    async def delete_if_value(client, key, value):
        if client.keys.get(key) == value:
            del client.keys[key]

    client = AsyncMock(return_value=fake)
    with (
        patch.object(sync_lease, "get_async_redis_client", client),
        patch("autobot_shared.leader_lease.get_async_redis_client", client),
        patch.object(sync_lease, "delete_if_value", delete_if_value),
    ):
        yield fake


@pytest.mark.asyncio
async def test_a_second_sync_of_the_same_connector_does_not_start(redis) -> None:
    async with sync_lease.connector_sync_lease("a"):
        with pytest.raises(sync_lease.ConnectorSyncBusy):
            async with sync_lease.connector_sync_lease("a"):
                pytest.fail("a second sync started")


@pytest.mark.asyncio
async def test_two_different_connectors_sync_at_once(redis) -> None:
    async with sync_lease.connector_sync_lease("a"), sync_lease.connector_sync_lease("b"):
        assert redis.keys.keys() == {"connector:sync:a", "connector:sync:b"}


@pytest.mark.asyncio
async def test_a_failed_sync_frees_the_connector(redis) -> None:
    with pytest.raises(ValueError):
        async with sync_lease.connector_sync_lease("a"):
            raise ValueError("sync failed")
    assert redis.keys == {}


@pytest.mark.asyncio
async def test_the_background_job_is_skipped_while_one_runs(redis) -> None:
    job = AsyncMock()
    wrapped = sync_lease.one_sync_per_connector(job)
    async with sync_lease.connector_sync_lease("a"):
        await wrapped("a", True)
    job.assert_not_awaited()
    await wrapped("a", True)
    job.assert_awaited_once_with("a", True)


@pytest.mark.asyncio
async def test_without_redis_nothing_starts_and_it_is_not_called_busy() -> None:
    none = AsyncMock(return_value=None)
    with (
        patch.object(sync_lease, "get_async_redis_client", none),
        patch("autobot_shared.leader_lease.get_async_redis_client", none),
        pytest.raises(sync_lease.ConnectorSyncUnavailable),
    ):
        async with sync_lease.connector_sync_lease("a"):
            pytest.fail("started without a lease")


@pytest.mark.asyncio
async def test_a_failed_release_does_not_replace_the_syncs_result(redis) -> None:
    async def fails(*_args):
        raise ConnectionError("gone")

    job = AsyncMock(return_value="result")
    with patch.object(sync_lease, "delete_if_value", fails):
        assert await sync_lease.one_sync_per_connector(job)("a") == "result"


async def _trigger(route, tasks, error=None):
    with patch.object(route, "_load_connector", AsyncMock(return_value=object())):
        if error is None:
            return await route.trigger_sync("a", tasks)
        with patch("api._connector_sync_claim.claim_connector_sync", AsyncMock(side_effect=error("a"))):
            return await route.trigger_sync("a", tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, code", [(sync_lease.ConnectorSyncBusy, 409), (sync_lease.ConnectorSyncUnavailable, 503)]
)
async def test_the_route_answers_for_a_lost_race_or_no_redis(error, code) -> None:
    from fastapi import HTTPException

    from api import knowledge_connectors as route

    tasks = MagicMock()
    with pytest.raises(HTTPException) as refused:
        await _trigger(route, tasks, error=error)
    assert refused.value.status_code == code
    tasks.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_the_route_holds_the_lease_it_claimed_for_the_run(redis) -> None:
    from api import knowledge_connectors as route

    tasks = MagicMock()
    await _trigger(route, tasks)
    assert list(redis.keys) == ["connector:sync:a"], "the lease is taken before the 200"
    job, run, connector_id, lease, incremental = tasks.add_task.call_args.args
    assert run is route._run_sync_background.__wrapped__, "the job must not try to take the lease again"
    stand_in = AsyncMock()
    await job(stand_in, connector_id, lease, incremental)
    stand_in.assert_awaited_once_with("a", True)
    assert redis.keys == {}


def _one_refresh_per_tick(monkeypatch) -> None:
    """A clock that moves one refresh per sleep, so the renewal loop runs without waiting."""
    loop = asyncio.get_running_loop()
    now = [loop.time()]
    monkeypatch.setattr(loop, "time", lambda: now[0])

    async def tick(seconds):
        now[0] += seconds

    monkeypatch.setattr(sync_lease.asyncio, "sleep", tick)


@pytest.mark.asyncio
async def test_a_redis_blip_still_extends_the_lease_it_holds(redis, monkeypatch) -> None:
    """A real lease: the retry after an error must extend this run's key, not try to take it again."""
    lease = await sync_lease.claim_connector_sync("a")
    key = sync_lease._key("a")
    real_eval, evals = redis.eval, []

    async def flaky_eval(*args):
        evals.append(args)
        if len(evals) == 1:
            raise ConnectionError("blip")
        if len(evals) == 2:
            return await real_eval(*args)  # extends: held, so the failure's clock resets
        redis.keys[key] = "another-run"  # the lease lapsed and someone else took it
        return await real_eval(*args)

    monkeypatch.setattr(redis, "eval", flaky_eval)
    _one_refresh_per_tick(monkeypatch)
    lost = asyncio.Event()
    await asyncio.wait_for(sync_lease._keep_renewing(lease, lost), timeout=5)

    assert len(evals) == 3, "1 blip, 1 extend, then one refusal: another owner is a loss at once"
    assert lost.is_set(), "the sync is told, so it stops before its next source"
    assert redis.keys[key] == "another-run", "a lease held by another run is never taken back"


@pytest.mark.asyncio
async def test_redis_errors_keep_the_lease_until_a_full_lifetime_passes(redis, monkeypatch) -> None:
    """An error is unknown, not lost: the key still names this run until its TTL runs out."""
    lease = await sync_lease.claim_connector_sync("a")

    async def down(*_args):
        raise ConnectionError("down")

    monkeypatch.setattr(redis, "eval", down)
    _one_refresh_per_tick(monkeypatch)
    lost = asyncio.Event()
    await asyncio.wait_for(sync_lease._keep_renewing(lease, lost), timeout=5)
    ticks = sync_lease.DEFAULT_TTL_MS / 1000 / sync_lease.DEFAULT_REFRESH_S
    assert lost.is_set() and lease.is_leader, "lost only once a lifetime has passed, never on the first error"
    assert ticks >= 2, "the TTL leaves room for more than one retry"


@pytest.mark.asyncio
async def test_a_redis_error_on_the_claim_is_unavailable_not_busy(redis, monkeypatch) -> None:
    """'Couldn't check' is not 'already running': the route answers 503 and the scheduler skips, alike."""

    async def fails(*_args, **_kwargs):
        raise ConnectionError("down")

    monkeypatch.setattr(redis, "set", fails)
    with pytest.raises(sync_lease.ConnectorSyncUnavailable):
        await sync_lease.claim_connector_sync("a")
    job = AsyncMock()
    assert await sync_lease.one_sync_per_connector(job)("a") is None
    job.assert_not_awaited()


def _three_source_connector(concurrency: int):
    """A real AbstractConnector sync loop over three sources, with its Redis-backed state stubbed."""
    from datetime import datetime, timezone

    from knowledge.connectors.base import AbstractConnector
    from knowledge.connectors.models import ChangeInfo, ConnectorConfig

    class _Three(AbstractConnector):
        connector_type = "lease-test"
        max_concurrency = concurrency

        async def test_connection(self):
            return True

        async def discover_sources(self):
            return []

        async def fetch_content(self, source_id):
            return None

        async def detect_changes(self, since=None):
            when = datetime.now(timezone.utc)
            return [ChangeInfo(source_id=f"s{i}", change_type="deleted", timestamp=when) for i in range(3)]

    connector = _Three(ConnectorConfig(connector_id="a", connector_type="lease-test", name="a", config={}))
    for name in ("_read_checkpoint", "_write_checkpoint", "_clear_checkpoint"):
        setattr(connector, name, AsyncMock(return_value=set()))
    return connector


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency, started", [(1, 1), (2, 2)], ids=["sequential", "concurrent"])
async def test_a_sync_that_lost_its_lease_stops_before_the_next_source(redis, concurrency, started) -> None:
    """The lease is lost after the first source's progress write: no further source starts."""
    connector = _three_source_connector(concurrency)
    lease = await sync_lease.claim_connector_sync("a")
    async with sync_lease.holding_connector_sync(lease):
        lost = sync_lease._LEASE_LOST.get()

        async def progress(**state):
            if state["status"] == "running" and state["sources_done"]:
                lost.set()

        connector._write_job_state = progress
        result = await connector.sync(incremental=False)
    # At most the sources already in flight finish (one per concurrency slot); never all three.
    assert 1 <= result.sources_done <= started < result.sources_total and result.status == "failed"
    assert "no longer holds the connector's sync lease" in result.errors[-1]


@pytest.mark.asyncio
async def test_outside_a_held_lease_there_is_nothing_to_lose() -> None:
    sync_lease.raise_if_sync_lease_lost()


@pytest.mark.asyncio
async def test_a_late_start_after_the_lease_lapsed_does_not_run(redis) -> None:
    """The route's claim can outlive its TTL before the job starts: no run, and the new owner's key stays."""
    from api._connector_sync_claim import run_claimed_sync

    lease = await sync_lease.claim_connector_sync("a")
    redis.keys[sync_lease._key("a")] = "another-run"  # lapsed, and another run claimed it
    run = AsyncMock()
    await run_claimed_sync(run, "a", lease, True)
    run.assert_not_awaited()
    assert redis.keys[sync_lease._key("a")] == "another-run"


@pytest.mark.asyncio
async def test_a_late_start_that_still_owns_the_lease_runs(redis) -> None:
    from api._connector_sync_claim import run_claimed_sync

    lease = await sync_lease.claim_connector_sync("a")
    run = AsyncMock()
    await run_claimed_sync(run, "a", lease, False)
    run.assert_awaited_once_with("a", False)
    assert redis.keys == {}, "released after the run"
