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
from contextvars import ContextVar
from typing import AsyncIterator, Optional

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


class ConnectorSyncLeaseLost(Exception):
    """The running sync no longer holds its lease, so it stops before the next source."""

    def __str__(self) -> str:
        return "the sync stopped: it no longer holds the connector's sync lease"


#: Set while a block holds a lease: the event fires when the lease is lost (#20556).
_LEASE_LOST: ContextVar[Optional[asyncio.Event]] = ContextVar("connector_sync_lease_lost", default=None)


def raise_if_sync_lease_lost() -> None:
    """For the sync body, between sources: stop once this run's lease is gone, so two runs never overlap."""
    lost = _LEASE_LOST.get()
    if lost is not None and lost.is_set():
        raise ConnectorSyncLeaseLost()


def _key(connector_id: str) -> str:
    return f"connector:sync:{connector_id}"


async def claim_connector_sync(connector_id: str) -> LeaderLease:
    """Take the connector's lease now, for a run that may start later. It lapses if never held.

    "Couldn't check" is never "already running": a Redis error on the SET NX is unavailable, not busy.
    """
    lease = LeaderLease(_key(connector_id), database=_DATABASE, worker_id=uuid.uuid4().hex)
    state = await lease.hold_or_refresh()
    if state is None:
        raise ConnectorSyncUnavailable(connector_id)
    if not state:
        raise ConnectorSyncBusy(connector_id)
    return lease


async def _keep_renewing(lease: LeaderLease, lost: asyncio.Event) -> None:
    """Renew until the lease is lost, then fire *lost* so the sync stops before its next source.

    Another owner on the key is a loss at once. A Redis error is retried while the key can still
    name this run, i.e. until a full TTL has passed since the last renewal.
    """
    loop = asyncio.get_running_loop()
    renewed_at = loop.time()
    while True:
        await asyncio.sleep(DEFAULT_REFRESH_S)
        state = await lease.hold_or_refresh()
        if state:
            renewed_at = loop.time()
            continue
        if state is None and loop.time() - renewed_at < DEFAULT_TTL_MS / 1000:
            logger.warning("Could not renew the sync lease %s; retrying", lease.key)
            continue
        logger.error("Lost the sync lease %s mid-run; the sync stops before its next source", lease.key)
        lost.set()
        return


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
    """Keep a claimed lease renewed for the block, then release it. The block sees a loss via
    :func:`raise_if_sync_lease_lost`."""
    lost = asyncio.Event()
    token = _LEASE_LOST.set(lost)
    renewing = asyncio.create_task(_keep_renewing(lease, lost))
    try:
        yield
    finally:
        _LEASE_LOST.reset(token)
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
