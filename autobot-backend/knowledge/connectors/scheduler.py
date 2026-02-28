# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Connector Scheduler

Issue #1254: Manages recurring asyncio sync tasks for connectors.
Parses simple interval expressions (e.g. "*/15" for every 15 minutes,
"@hourly", "@daily") instead of requiring the croniter library.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schedule parsing
# ---------------------------------------------------------------------------

_NAMED_SCHEDULES: Dict[str, int] = {
    "@minutely": 60,
    "@hourly": 3600,
    "@daily": 86400,
    "@weekly": 604800,
}


def _parse_interval_seconds(schedule: str) -> Optional[int]:
    """Return the repeat interval in seconds for a simple schedule string.

    Supported formats:
        ``@minutely``  → 60 s
        ``@hourly``    → 3600 s
        ``@daily``     → 86400 s
        ``@weekly``    → 604800 s
        ``*/N``        → N minutes (e.g. ``*/15`` → 900 s)
        ``N``          → N minutes (plain integer string)

    Returns None for unrecognised schedules.
    """
    schedule = schedule.strip().lower()

    if schedule in _NAMED_SCHEDULES:
        return _NAMED_SCHEDULES[schedule]

    # */N  or  */N * * * *  (first field only)
    m = re.match(r"^\*/(\d+)", schedule)
    if m:
        minutes = int(m.group(1))
        return max(minutes, 1) * 60

    # plain integer = minutes
    if re.match(r"^\d+$", schedule):
        return max(int(schedule), 1) * 60

    return None


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class ConnectorScheduler:
    """Manages scheduled sync jobs for connectors using asyncio tasks.

    Each connector with a non-None ``schedule_cron`` gets an asyncio.Task
    that sleeps until the next run time, triggers a sync, then repeats.

    Usage::

        scheduler = ConnectorScheduler()
        await scheduler.start(connector_id="my-connector", schedule="*/30")
        # … later …
        await scheduler.stop("my-connector")
        await scheduler.stop_all()
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}

    async def start(self, connector_id: str, schedule: str) -> bool:
        """Schedule a connector for recurring syncs.

        Args:
            connector_id: ID of the connector to schedule.
            schedule: Simple interval expression (see ``_parse_interval_seconds``).

        Returns:
            True if the task was started, False on parse error.
        """
        interval = _parse_interval_seconds(schedule)
        if interval is None:
            logger.error(
                "Cannot schedule connector %s: unrecognised schedule '%s'",
                connector_id,
                schedule,
            )
            return False

        # Cancel existing task for this connector if present
        await self.stop(connector_id)

        task = asyncio.create_task(
            self._run_loop(connector_id, interval),
            name="connector-scheduler-%s" % connector_id,
        )
        self._tasks[connector_id] = task
        logger.info(
            "Scheduled connector %s every %d seconds (schedule='%s')",
            connector_id,
            interval,
            schedule,
        )
        return True

    async def stop(self, connector_id: str) -> None:
        """Cancel the scheduled task for *connector_id*, if any."""
        task = self._tasks.pop(connector_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped scheduled connector %s", connector_id)

    async def stop_all(self) -> None:
        """Cancel all running schedule tasks."""
        ids = list(self._tasks.keys())
        for connector_id in ids:
            await self.stop(connector_id)
        logger.info("Stopped all %d scheduled connectors", len(ids))

    def is_running(self, connector_id: str) -> bool:
        """Return True if *connector_id* has an active schedule task."""
        task = self._tasks.get(connector_id)
        return task is not None and not task.done()

    def list_scheduled(self) -> Dict[str, bool]:
        """Return {connector_id: is_running} for all tracked tasks."""
        return {cid: self.is_running(cid) for cid in self._tasks}

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _run_loop(self, connector_id: str, interval_seconds: int) -> None:
        """Sleep → sync → repeat until cancelled (Issue #1254: scheduler core)."""
        logger.info(
            "Scheduler loop started for connector %s (interval=%ds)",
            connector_id,
            interval_seconds,
        )
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self._trigger_sync(connector_id)
            except asyncio.CancelledError:
                logger.info("Scheduler loop cancelled for connector %s", connector_id)
                break
            except Exception as exc:
                logger.error(
                    "Scheduler loop error for connector %s: %s", connector_id, exc
                )
                # Continue loop — a transient error should not stop scheduling

    async def _trigger_sync(self, connector_id: str) -> None:
        """Look up the connector instance and run an incremental sync."""
        from knowledge.connectors.registry import ConnectorRegistry

        connector = ConnectorRegistry.get(connector_id)
        if connector is None:
            logger.warning(
                "Scheduled sync: connector %s not in registry — skipping",
                connector_id,
            )
            return

        logger.info("Scheduler triggering sync for connector %s", connector_id)
        started_at = datetime.utcnow()
        try:
            result = await connector.sync(incremental=True)
            logger.info(
                "Scheduled sync complete: connector=%s status=%s "
                "added=%d updated=%d deleted=%d errors=%d",
                connector_id,
                result.status,
                result.added,
                result.updated,
                result.deleted,
                len(result.errors),
            )
        except Exception as exc:
            elapsed = (datetime.utcnow() - started_at).total_seconds()
            logger.error(
                "Scheduled sync failed: connector=%s elapsed=%.1fs error=%s",
                connector_id,
                elapsed,
                exc,
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_scheduler: Optional[ConnectorScheduler] = None


def get_connector_scheduler() -> ConnectorScheduler:
    """Return the module-level ConnectorScheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ConnectorScheduler()
    return _scheduler
