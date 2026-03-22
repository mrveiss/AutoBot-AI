# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Fleet sync concurrency guard (Issue #1979).

Provides the shared asyncio lock and guard function used by both the
API layer (code_sync.py) and the background schedule executor
(schedule_executor.py) to prevent overlapping fleet sync jobs.

The lock and guard live here — in the services layer — so both callers
can import them without creating a circular dependency.
"""

import asyncio

from fastapi import HTTPException, status
from models.database import FleetSyncJob as FleetSyncJobModel
from sqlalchemy import select

# Serialise check-and-insert across all fleet sync entry points to prevent
# TOCTOU races (#1730, #1937, #1979).
fleet_sync_lock = asyncio.Lock()


async def assert_no_running_sync(db) -> None:
    """Raise 409 if a fleet sync is already running (#1730).

    Shared guard for sync_fleet, run_schedule, and execute_schedule.
    Must be called while holding ``fleet_sync_lock`` to prevent TOCTOU races.
    """
    running_result = await db.execute(
        select(FleetSyncJobModel).where(FleetSyncJobModel.status == "running")
    )
    if running_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Fleet sync already in progress",
        )
