# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
from sqlalchemy import select, text

from models.database import FleetSyncJob as FleetSyncJobModel

# Serialise check-and-insert across all fleet sync entry points to prevent
# TOCTOU races (#1730, #1937, #1979).
fleet_sync_lock = asyncio.Lock()

# Stable advisory lock ID for the fleet sync guard.  The value is arbitrary
# but must be unique across the application.  Using a named constant makes
# it easy to audit all callers.
_FLEET_SYNC_ADVISORY_LOCK_ID = 2401  # matches issue #2401


async def assert_no_running_sync(db) -> None:
    """Raise 409 if a fleet sync is already running (#1730).

    Shared guard for sync_fleet, run_schedule, and execute_schedule.
    Must be called while holding ``fleet_sync_lock`` to prevent TOCTOU races.

    Two complementary locks prevent the TOCTOU race described in #2401:

    1. ``pg_advisory_xact_lock`` — transaction-scoped advisory lock acquired
       before the SELECT.  Serialises concurrent callers even when the
       FleetSyncJob table is empty (i.e. when FOR UPDATE would lock zero rows
       and therefore provide no protection).

    2. ``.with_for_update()`` — row-level lock kept as defence-in-depth for
       the case where a running job row already exists.  Prevents a second
       transaction from reading a stale "no running job" snapshot after the
       advisory lock is released.
    """
    # Acquire a transaction-scoped advisory lock before reading.  This
    # serialises all concurrent callers regardless of whether any rows exist
    # in the table, closing the zero-row TOCTOU window identified in #2401.
    await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)").bindparams(lock_id=_FLEET_SYNC_ADVISORY_LOCK_ID))

    running_result = await db.execute(
        select(FleetSyncJobModel)
        .where(FleetSyncJobModel.status == "running")
        .with_for_update()  # Defence-in-depth: row-level lock when rows exist (#1937)
    )
    if running_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Fleet sync already in progress",
        )
