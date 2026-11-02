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

    async def exists(self, key):
        return int(key in self.keys)

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
        assert await sync_lease.connector_sync_running("a") is True
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
    assert await sync_lease.connector_sync_running("a") is False


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
async def test_without_redis_nothing_starts() -> None:
    with (
        patch("autobot_shared.leader_lease.get_async_redis_client", AsyncMock(return_value=None)),
        pytest.raises(sync_lease.ConnectorSyncBusy),
    ):
        async with sync_lease.connector_sync_lease("a"):
            pytest.fail("started without a lease")


@pytest.mark.asyncio
async def test_the_sync_route_refuses_while_one_runs() -> None:
    from fastapi import HTTPException

    from api import knowledge_connectors as route

    tasks = MagicMock()
    with (
        patch.object(route, "_load_connector", AsyncMock(return_value=object())),
        patch.object(route, "connector_sync_running", AsyncMock(return_value=True)),
        pytest.raises(HTTPException) as refused,
    ):
        await route.trigger_sync("a", tasks)
    assert refused.value.status_code == 409
    tasks.add_task.assert_not_called()
