# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Run status transitions for a heartbeat run (#16818, #620).

Sits beside `run_context` and `run_workspace`: one small module per per-run concern,
rather than another few dozen lines inside the scheduler.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, update

from ..models.enums import LLCRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun

logger = logging.getLogger(__name__)


async def mark_running(factory: Any, run_id: UUID) -> Optional[int]:
    """Read `retry_count`, then mark the run RUNNING. ``None`` if that failed.

        The read comes first so backoff is computed from the count before this attempt.
        On failure the run is marked FAILED here -- the status write belongs with the
        attempt that failed -- but the workspace release does NOT: the caller owns that,
        so that every exit from `_run_adapter` has its release where a reader of
        `_run_adapter` can see it. Extracted from that function to keep it inside the
        65-line limit (#620), and placed beside `run_context` and `run_workspace`, which hold the
    other per-run concerns.
    """
    try:
        async with factory() as session:
            result = await session.execute(select(LLCHeartbeatRun.retry_count).where(LLCHeartbeatRun.id == run_id))
            retry_count: int = result.scalar_one_or_none() or 0
            await session.execute(
                update(LLCHeartbeatRun)
                .where(LLCHeartbeatRun.id == run_id)
                .values(status=LLCRunStatus.RUNNING.value, started_at=datetime.now(tz=timezone.utc))
            )
            await session.commit()
        return retry_count
    except Exception as exc:
        logger.exception("Failed to mark run %s as RUNNING — marking FAILED", run_id)
        try:
            async with factory() as session:
                await session.execute(
                    update(LLCHeartbeatRun)
                    .where(LLCHeartbeatRun.id == run_id)
                    .values(
                        status=LLCRunStatus.FAILED.value,
                        finished_at=datetime.now(tz=timezone.utc),
                        error=str(exc),
                    )
                )
                await session.commit()
        except Exception:
            logger.exception("Could not write FAILED status for run %s", run_id)
        return None
