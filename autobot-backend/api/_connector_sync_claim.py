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
from knowledge.connectors.sync_lease import (
    ConnectorSyncBusy,
    ConnectorSyncUnavailable,
    claim_connector_sync,
    holding_connector_sync,
)


async def claim_or_refuse(connector_id: str) -> LeaderLease:
    try:
        return await claim_connector_sync(connector_id)
    except ConnectorSyncBusy as exc:
        raise HTTPException(status_code=409, detail="This connector is already syncing") from exc
    except ConnectorSyncUnavailable as exc:
        raise HTTPException(status_code=503, detail="Sync is unavailable: Redis cannot be reached") from exc


async def run_claimed_sync(run, connector_id: str, lease: LeaderLease, incremental: bool) -> None:
    async with holding_connector_sync(lease):
        await run(connector_id, incremental)
