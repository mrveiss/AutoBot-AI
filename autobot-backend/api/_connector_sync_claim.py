# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Sync button's side of the per-connector lease (#20556).

The route takes the lease before answering, not the job after it, so the answer says whether this
run will happen.
"""

from fastapi import HTTPException

from autobot_shared.leader_lease import LeaderLease
from autobot_shared.logging_manager import get_logger
from knowledge.connectors.sync_lease import (
    ConnectorSyncBusy,
    ConnectorSyncUnavailable,
    claim_connector_sync,
    holding_connector_sync,
)

logger = get_logger(__name__)


async def claim_or_refuse(connector_id: str) -> LeaderLease:
    try:
        return await claim_connector_sync(connector_id)
    except ConnectorSyncBusy as exc:
        raise HTTPException(status_code=409, detail="This connector is already syncing") from exc
    except ConnectorSyncUnavailable as exc:
        raise HTTPException(status_code=503, detail="Sync is unavailable: Redis cannot be reached") from exc


async def run_claimed_sync(run, connector_id: str, lease: LeaderLease, incremental: bool) -> None:
    """Run under the lease the route claimed, if this run still owns it once it starts.

    The start can lag the claim past the lease's lifetime, so ownership is refreshed first: an
    owner-checked extend, never a fresh SET. A key that has lapsed, changed hands, or can't be
    checked means no run, and the key is left alone (another run may hold it now).
    """
    if await lease.hold_or_refresh() is not True:
        logger.warning("Connector %s did not sync: its claimed lease is gone or can't be checked", connector_id)
        return
    async with holding_connector_sync(lease):
        await run(connector_id, incremental)
