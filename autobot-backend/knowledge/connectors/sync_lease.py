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

from autobot_shared.leader_lease import DEFAULT_REFRESH_S, DEFAULT_TTL_MS, LeaderLease
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import delete_if_value

logger = get_logger(__name__)

_DATABASE = "knowledge"


class ConnectorSyncBusy(Exception):
    """This connector already has a sync running."""


class ConnectorSyncUnavailable(Exception):
    """Redis can't be reached, so whether a sync is running can't be told, and none starts."""


def _key(connector_id: str) -> str:
    return f"connector:sync:{connector_id}"


async def claim_connector_sync(connector_id: str) -> LeaderLease:
    """Take the connector's lease now, for a run that may start later. It lapses if never held."""
    try:
        redis = await get_async_redis_client(database=_DATABASE)
        if redis is None:
            raise ConnectorSyncUnavailable(connector_id)
        await redis.ping()
    except ConnectorSyncUnavailable:
        raise
    except Exception as exc:
        raise ConnectorSyncUnavailable(connector_id) from exc
    lease = LeaderLease(_key(connector_id), database=_DATABASE, worker_id=uuid.uuid4().hex)
    if not await lease.update_leadership():
        raise ConnectorSyncBusy(connector_id)
    return lease


async def _keep_renewing(lease: LeaderLease) -> None:
    """Retry a failed renewal while the lease can still be alive: a Redis blip isn't a lost lease.

    Not ``update_leadership``: it marks the lease lost on one failure, and the next try would then
    be a SET NX that fails against this run's own key, leaving its TTL to run out.
    """
    loop = asyncio.get_running_loop()
    renewed_at = loop.time()
    while True:
        await asyncio.sleep(DEFAULT_REFRESH_S)
        if await lease.try_acquire_or_refresh():
            renewed_at = loop.time()
        elif loop.time() - renewed_at >= DEFAULT_TTL_MS / 1000:
            logger.error("Lost the sync lease %s mid-run; a second sync could now start", lease.key)
            return
        else:
            logger.warning("Could not renew the sync lease %s; retrying", lease.key)


async def _release(lease: LeaderLease) -> None:
    """A failed release must not replace the sync's own result; the lease expires by itself."""
    try:
        redis = await get_async_redis_client(database=_DATABASE)
        if redis is not None:
            await delete_if_value(redis, lease.key, lease.worker_id)
    except Exception as exc:
        logger.warning("Could not release the sync lease %s: %s", lease.key, exc)


@asynccontextmanager
async def holding_connector_sync(lease: LeaderLease) -> AsyncIterator[None]:
    """Keep a claimed lease renewed for the block, then release it."""
    renewing = asyncio.create_task(_keep_renewing(lease))
    try:
        yield
    finally:
        renewing.cancel()
        await asyncio.gather(renewing, return_exceptions=True)
        await _release(lease)


@asynccontextmanager
async def connector_sync_lease(connector_id: str) -> AsyncIterator[None]:
    """Claim and hold the lease. Raises ConnectorSyncBusy or ConnectorSyncUnavailable."""
    lease = await claim_connector_sync(connector_id)
    async with holding_connector_sync(lease):
        yield


def one_sync_per_connector(func):
    """For a background job taking connector_id first: skip the run if it can't take the lease."""

    @functools.wraps(func)
    async def wrapper(connector_id: str, *args, **kwargs):
        try:
            async with connector_sync_lease(connector_id):
                return await func(connector_id, *args, **kwargs)
        except ConnectorSyncBusy:
            logger.info("Connector %s already has a sync running; this one did not start", connector_id)
        except ConnectorSyncUnavailable:
            logger.warning("Connector %s did not sync: Redis is unavailable", connector_id)
        return None

    return wrapper
