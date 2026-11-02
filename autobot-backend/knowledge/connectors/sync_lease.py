# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One sync at a time per connector, across the scheduler and the Sync button (#20556).

Each run holds its own Redis lease, renewed while it runs, so a crashed run frees the connector
within the lease's lifetime. Different connectors have different keys and sync side by side.
"""

import asyncio
import functools
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from autobot_shared.leader_lease import DEFAULT_REFRESH_S, LeaderLease
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import delete_if_value

logger = get_logger(__name__)

_DATABASE = "knowledge"


class ConnectorSyncBusy(Exception):
    """This connector already has a sync running, or Redis could not say otherwise."""


def _key(connector_id: str) -> str:
    return f"connector:sync:{connector_id}"


async def connector_sync_running(connector_id: str) -> bool:
    redis = await get_async_redis_client(database=_DATABASE)
    return redis is not None and bool(await redis.exists(_key(connector_id)))


async def _keep_renewing(lease: LeaderLease) -> None:
    while True:
        await asyncio.sleep(DEFAULT_REFRESH_S)
        await lease.update_leadership()


@asynccontextmanager
async def connector_sync_lease(connector_id: str) -> AsyncIterator[None]:
    """Hold the connector's lease for the block. Raises ConnectorSyncBusy if it can't be taken."""
    lease = LeaderLease(_key(connector_id), database=_DATABASE, worker_id=uuid.uuid4().hex)
    if not await lease.update_leadership():
        raise ConnectorSyncBusy(connector_id)
    renewing = asyncio.create_task(_keep_renewing(lease))
    try:
        yield
    finally:
        renewing.cancel()
        redis = await get_async_redis_client(database=_DATABASE)
        if redis is not None:
            await delete_if_value(redis, lease.key, lease.worker_id)


def one_sync_per_connector(func):
    """For a background job taking connector_id first: skip the run if one is already going."""

    @functools.wraps(func)
    async def wrapper(connector_id: str, *args, **kwargs):
        try:
            async with connector_sync_lease(connector_id):
                return await func(connector_id, *args, **kwargs)
        except ConnectorSyncBusy:
            logger.info("Connector %s already has a sync running; this one did not start", connector_id)
            return None

    return wrapper
