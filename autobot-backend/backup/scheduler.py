# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge-base daily backup scheduler (Issue #3294).

Runs a background asyncio task that wakes once per day at the configured
UTC hour and calls KnowledgeBase.create_backup().  Referenced in:
  - initialization/lifespan.py::_init_backup_scheduler
  - api/system.py::get_backup_status
  - services/scheduler_registry.py (registry entry)

Configuration:
  AUTOBOT_BACKUP_SCHEDULE_HOUR  int 0-23, default 2 (02:00 UTC)
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_DEFAULT_SCHEDULE_HOUR = 2


def _schedule_hour_from_env() -> int:
    raw = os.environ.get("AUTOBOT_BACKUP_SCHEDULE_HOUR", str(_DEFAULT_SCHEDULE_HOUR))
    try:
        hour = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_BACKUP_SCHEDULE_HOUR=%r is not an integer; using default %d",
            raw,
            _DEFAULT_SCHEDULE_HOUR,
        )
        return _DEFAULT_SCHEDULE_HOUR
    if not 0 <= hour <= 23:
        logger.warning(
            "AUTOBOT_BACKUP_SCHEDULE_HOUR=%d out of range 0-23; using default %d",
            hour,
            _DEFAULT_SCHEDULE_HOUR,
        )
        return _DEFAULT_SCHEDULE_HOUR
    return hour


class BackupScheduler:
    """Daily knowledge-base backup scheduler.

    Usage::
        scheduler = BackupScheduler()
        await scheduler.start()
        ...
        await scheduler.stop()
    """

    def __init__(self) -> None:
        self._schedule_hour: int = _schedule_hour_from_env()
        self._task: asyncio.Task | None = None
        self._last_backup_at: datetime | None = None
        self._last_backup_result: Dict[str, Any] | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="backup-scheduler")
        logger.info("BackupScheduler started (daily at %02d:00 UTC)", self._schedule_hour)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("BackupScheduler stopped")

    def get_status(self) -> Dict[str, Any]:
        now = datetime.now(tz=timezone.utc)
        next_run = now.replace(hour=self._schedule_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run.replace(day=next_run.day + 1)
        return {
            "status": "running" if self._running else "stopped",
            "schedule_hour_utc": self._schedule_hour,
            "last_backup_at": self._last_backup_at.isoformat() if self._last_backup_at else None,
            "last_backup_result": self._last_backup_result,
            "next_run_at": next_run.isoformat(),
        }

    async def _loop(self) -> None:
        while self._running:
            now = datetime.now(tz=timezone.utc)
            seconds_until = _seconds_until_hour(now, self._schedule_hour)
            logger.debug("BackupScheduler sleeping %.0f s until %02d:00 UTC", seconds_until, self._schedule_hour)
            try:
                await asyncio.sleep(seconds_until)
            except asyncio.CancelledError:
                return
            if not self._running:
                return
            await self._run_backup()

    async def _run_backup(self) -> None:
        logger.info("BackupScheduler: starting scheduled knowledge-base backup")
        try:
            from knowledge._composed import get_knowledge_base

            kb = await get_knowledge_base()
            result = await kb.create_backup()
            self._last_backup_at = datetime.now(tz=timezone.utc)
            self._last_backup_result = result
            status = result.get("status", "unknown")
            logger.info("BackupScheduler: backup completed with status=%s", status)
        except Exception as exc:
            logger.error("BackupScheduler: backup failed: %s", exc)
            self._last_backup_result = {"status": "error", "message": str(exc)}


def _seconds_until_hour(now: datetime, target_hour: int) -> float:
    """Return seconds from *now* until the next occurrence of *target_hour*:00 UTC."""
    next_run = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    if next_run <= now:
        # Already past today's slot — schedule for tomorrow.
        next_run = next_run.replace(day=next_run.day + 1)
    return max((next_run - now).total_seconds(), 1.0)
