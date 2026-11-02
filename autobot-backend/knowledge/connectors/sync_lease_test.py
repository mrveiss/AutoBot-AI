# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20556: a connector runs one sync at a time, and other connectors are unaffected."""

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
    with (
        patch.object(sync_lease, "get_async_redis_client", AsyncMock(return_value=None)),
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
